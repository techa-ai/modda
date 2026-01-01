#!/usr/bin/env python3
"""
AI-Powered Document Deduplication and Versioning (V2)

Uses Claude Opus to analyze document_summary from deep JSON to:
1. Identify exact duplicates (same content, different files)
2. Group related documents by type/content
3. Identify versions (preliminary vs final, signed vs unsigned)
4. Determine master/latest version for each group

Skips documents >40 pages to avoid token limits.
Works on modda_v2 schema for A/B testing.
"""

import os
import sys
import json
import hashlib
import argparse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from collections import defaultdict

# Add backend to path
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND_DIR)

from db import execute_query, get_db_connection
from vlm_utils import VLMClient

# Thread-safe stats
stats_lock = Lock()

# Schema to use (for A/B testing)
SCHEMA = "modda_v2"


def get_documents_for_loan(loan_id, max_pages=20):
    """Get documents with FULL deep JSON (page-wise), limited by page count"""
    query = f"""
        SELECT 
            id, filename, file_path, page_count,
            individual_analysis as full_analysis,
            text_hash, visual_dhash, visual_phash
        FROM {SCHEMA}.document_analysis
        WHERE loan_id = %s
          AND individual_analysis IS NOT NULL
          AND (page_count <= %s OR page_count IS NULL)
        ORDER BY filename
    """
    return execute_query(query, (loan_id, max_pages))


def get_large_documents(loan_id, min_pages=21):
    """Get documents too large for AI analysis (>20 pages)"""
    query = f"""
        SELECT id, filename, page_count
        FROM {SCHEMA}.document_analysis
        WHERE loan_id = %s
          AND page_count > %s
        ORDER BY filename
    """
    return execute_query(query, (loan_id, min_pages))


def create_document_fingerprint(doc):
    """Create a compact fingerprint from document summary for duplicate detection"""
    summary = doc.get('doc_summary') or {}
    if isinstance(summary, str):
        try:
            summary = json.loads(summary)
        except:
            summary = {}
    
    # Extract key identifying fields
    metadata = summary.get('document_metadata', {})
    overview = summary.get('document_overview', {})
    key_ids = metadata.get('key_identifiers', {})
    form_ids = metadata.get('form_identifiers', {})
    
    fingerprint = {
        'doc_type': metadata.get('document_metadata', {}).get('document_type') or overview.get('document_type', ''),
        'doc_status': metadata.get('document_status', ''),
        'doc_version': metadata.get('document_version', ''),
        'property_address': key_ids.get('property_address', ''),
        'loan_amount': key_ids.get('loan_amount', ''),
        'borrower_names': key_ids.get('borrower_names', []),
        'form_number': form_ids.get('form_number', ''),
        'loan_number': form_ids.get('loan_number', ''),
        'all_dates': metadata.get('all_dates', []),
        'has_signature': metadata.get('signature_analysis', {}).get('has_any_signature', False),
        'page_count': doc.get('page_count', 0),
        # Hashes for exact match detection
        'text_hash': doc.get('text_hash', ''),
        'visual_dhash': doc.get('visual_dhash', ''),
    }
    return fingerprint


def batch_analyze_documents(loan_id, documents, batch_size=10):
    """
    Use Claude to analyze documents in batches and identify:
    - Duplicates
    - Related groups
    - Versions (preliminary/final, signed/unsigned)
    - Master document for each group
    
    Sends FULL page-wise individual_analysis for accurate analysis.
    Pre-groups documents by type to ensure versions stay together.
    """
    
    print(f"\n📊 Analyzing {len(documents)} documents for loan {loan_id}...")
    
    # Prepare document data with full analysis and extract doc_type for grouping
    doc_data = []
    for doc in documents:
        full_analysis = doc.get('full_analysis') or {}
        if isinstance(full_analysis, str):
            try:
                full_analysis = json.loads(full_analysis)
            except:
                full_analysis = {}
        
        # Extract doc_type for pre-grouping
        doc_type = None
        summary = full_analysis.get('document_summary', {})
        if summary:
            overview = summary.get('document_overview', {})
            doc_type = overview.get('document_type') or overview.get('form_type')
        
        doc_data.append({
            'id': doc['id'],
            'filename': doc['filename'],
            'page_count': doc.get('page_count', 0),
            'text_hash': doc.get('text_hash', ''),
            'visual_dhash': doc.get('visual_dhash', ''),
            'doc_type_hint': doc_type,  # For smart batching
            'individual_analysis': full_analysis
        })
    
    # Smart batching: sort by doc_type so similar docs are in same batch
    doc_data.sort(key=lambda x: (x.get('doc_type_hint') or 'zzz_unknown', x['filename']))
    
    # Process in batches
    all_results = []
    client = VLMClient(model='claude-opus-4-5', max_tokens=32000)
    
    for i in range(0, len(doc_data), batch_size):
        batch = doc_data[i:i+batch_size]
        print(f"  Processing batch {i//batch_size + 1}/{(len(doc_data) + batch_size - 1)//batch_size} ({len(batch)} docs)...")
        
        prompt = f"""You are analyzing {len(batch)} mortgage documents to identify duplicates, versions, and groupings.

DOCUMENT DATA (with full page-wise analysis):
{json.dumps(batch, indent=2, default=str)}

ANALYSIS TASKS:

**CRITICAL: STRICT GROUPING RULES**
- ONLY group documents that are TRULY VERSIONS of THE EXACT SAME DOCUMENT
- A "version" means: same form type, same borrower, same property - but different dates or preliminary/final status
- DIFFERENT document types MUST NEVER be grouped together!
- Example: 1008 and 1003 are DIFFERENT forms - NEVER group them
- Example: Right to Cancel and Closing Disclosure are DIFFERENT forms - NEVER group them
- Example: "1008_final.pdf" and "1008_preliminary.pdf" ARE versions - group them

1. **DUPLICATE DETECTION**: Documents with same text_hash or visual_dhash are duplicates

2. **VERSION DETECTION**: ONLY group if:
   - SAME form type (e.g., both are "Right to Cancel" or both are "1008")
   - One is preliminary/draft and another is final
   - One is unsigned and another is signed
   - SAME borrower and property info

3. **WHEN IN DOUBT: Mark as UNIQUE**
   - Most documents should be UNIQUE (standalone)
   - Only create groups when you are 100% certain they are versions of the same doc

OUTPUT FORMAT (strict JSON):
{{
  "groups": [
    {{
      "group_id": "G001",
      "group_name": "Right to Cancel",
      "documents": [
        {{
          "id": 123,
          "filename": "right_to_cancel_final.pdf",
          "status": "master",
          "master_id": null,
          "is_latest_version": true,
          "version_type": "final",
          "reasoning": "Final signed version of Right to Cancel"
        }},
        {{
          "id": 124,
          "filename": "right_to_cancel_preliminary.pdf",
          "status": "superseded",
          "master_id": 123,
          "is_latest_version": false,
          "version_type": "preliminary",
          "reasoning": "Preliminary version, superseded by final"
        }}
      ]
    }}
  ],
  "ungrouped": [
    {{
      "id": 456,
      "filename": "1008_final.pdf",
      "status": "unique",
      "reasoning": "Standalone document, no other versions found"
    }}
  ]
}}

RULES:
1. Each document must appear EXACTLY ONCE
2. NEVER mix different form types in the same group
3. Group size should typically be 2-4 (preliminary + final, or with duplicates)
4. Groups with 5+ documents are EXTREMELY RARE - verify carefully
5. Most documents should be in "ungrouped" as "unique"

Return ONLY valid JSON."""

        try:
            result = client.process_text(json.dumps(batch, default=str), prompt, return_json=True)
            
            if isinstance(result, str):
                # Try to extract JSON
                import re
                match = re.search(r'\{[\s\S]*\}', result)
                if match:
                    result = json.loads(match.group())
                else:
                    print(f"  ⚠️ Failed to parse batch response")
                    continue
            
            if result:
                all_results.append(result)
                
        except Exception as e:
            print(f"  ❌ Error processing batch: {e}")
            continue
    
    return all_results


def apply_analysis_results(loan_id, results):
    """Apply the AI analysis results to the database"""
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    updates = 0
    
    for result in results:
        groups = result.get('groups', [])
        ungrouped = result.get('ungrouped', [])
        
        # Process groups
        for group in groups:
            group_id = group.get('group_id', '')
            group_name = group.get('group_name', '')
            
            for doc in group.get('documents', []):
                doc_id = doc.get('id')
                if not doc_id:
                    continue
                
                status = doc.get('status', 'unique')
                master_id = doc.get('master_id')
                is_latest = doc.get('is_latest_version', False)
                version_type = doc.get('version_type', 'unknown')
                signature_status = doc.get('signature_status', 'unknown')
                reasoning = doc.get('reasoning', '')
                
                version_metadata = {
                    'ai_group_id': group_id,
                    'ai_group_name': group_name,
                    'version_type': version_type,
                    'signature_status': signature_status,
                    'reasoning': reasoning,
                    'analyzed_at': datetime.now().isoformat()
                }
                
                cur.execute(f"""
                    UPDATE {SCHEMA}.document_analysis
                    SET status = %s,
                        master_document_id = %s,
                        version_group_id = %s,
                        is_latest_version = %s,
                        version_metadata = %s
                    WHERE id = %s
                """, (
                    status,
                    master_id,
                    group_id,
                    is_latest,
                    json.dumps(version_metadata),
                    doc_id
                ))
                updates += 1
        
        # Process ungrouped documents
        for doc in ungrouped:
            doc_id = doc.get('id')
            if not doc_id:
                continue
            
            cur.execute(f"""
                UPDATE {SCHEMA}.document_analysis
                SET status = 'unique',
                    is_latest_version = true,
                    version_metadata = %s
                WHERE id = %s
            """, (
                json.dumps({
                    'ai_group_id': None,
                    'version_type': 'unknown',
                    'signature_status': doc.get('signature_status', 'unknown'),
                    'analyzed_at': datetime.now().isoformat()
                }),
                doc_id
            ))
            updates += 1
    
    conn.commit()
    cur.close()
    conn.close()
    
    return updates


def mark_large_documents_unique(loan_id, min_pages=41):
    """Mark large documents as unique (no dedup/version analysis possible)"""
    
    large_docs = get_large_documents(loan_id, min_pages)
    
    if not large_docs:
        return 0
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    for doc in large_docs:
        cur.execute(f"""
            UPDATE {SCHEMA}.document_analysis
            SET status = 'unique',
                is_latest_version = true,
                version_metadata = %s
            WHERE id = %s
        """, (
            json.dumps({
                'ai_group_id': None,
                'version_type': 'unknown',
                'signature_status': 'unknown',
                'skip_reason': f'Document too large ({doc["page_count"]} pages)',
                'analyzed_at': datetime.now().isoformat()
            }),
            doc['id']
        ))
    
    conn.commit()
    cur.close()
    conn.close()
    
    return len(large_docs)


def run_dedup_versioning(loan_id, max_pages=20, batch_size=10):
    """Run the full deduplication and versioning pipeline for a loan"""
    
    print(f"\n{'='*70}")
    print(f"🔍 AI DEDUPLICATION & VERSIONING - Loan {loan_id}")
    print(f"   Schema: {SCHEMA}")
    print(f"   Max pages for analysis: {max_pages}")
    print(f"{'='*70}")
    
    # Get documents
    documents = get_documents_for_loan(loan_id, max_pages)
    print(f"\n📄 Documents for analysis: {len(documents)}")
    
    # Mark large documents as unique first
    large_count = mark_large_documents_unique(loan_id, max_pages + 1)
    print(f"📦 Large documents (>{max_pages} pages) marked unique: {large_count}")
    
    if not documents:
        print("❌ No documents found for analysis")
        return
    
    # Run AI analysis
    results = batch_analyze_documents(loan_id, documents, batch_size)
    
    if not results:
        print("❌ No analysis results")
        return
    
    # Apply results
    updates = apply_analysis_results(loan_id, results)
    print(f"\n✅ Applied {updates} document updates")
    
    # Show summary
    summary_query = f"""
        SELECT 
            status,
            COUNT(*) as count
        FROM {SCHEMA}.document_analysis
        WHERE loan_id = %s
        GROUP BY status
        ORDER BY count DESC
    """
    summary = execute_query(summary_query, (loan_id,))
    
    print(f"\n📊 Final Status Distribution:")
    for row in summary:
        print(f"   {row['status']}: {row['count']}")
    
    # Count duplicates and versions
    dup_count = execute_query(f"""
        SELECT COUNT(*) as cnt 
        FROM {SCHEMA}.document_analysis 
        WHERE loan_id = %s AND status = 'duplicate'
    """, (loan_id,))[0]['cnt']
    
    version_count = execute_query(f"""
        SELECT COUNT(DISTINCT version_group_id) as cnt 
        FROM {SCHEMA}.document_analysis 
        WHERE loan_id = %s AND version_group_id IS NOT NULL
    """, (loan_id,))[0]['cnt']
    
    print(f"\n📋 Results:")
    print(f"   Duplicates identified: {dup_count}")
    print(f"   Version groups: {version_count}")
    print(f"{'='*70}\n")


def run_all_loans(max_pages=20):
    """Run dedup/versioning for all loans"""
    
    loans = execute_query("SELECT id, loan_number FROM loans ORDER BY id")
    
    print(f"\n{'='*70}")
    print(f"🚀 RUNNING AI DEDUP/VERSIONING FOR ALL {len(loans)} LOANS")
    print(f"{'='*70}")
    
    for loan in loans:
        run_dedup_versioning(loan['id'], max_pages)


def main():
    parser = argparse.ArgumentParser(description="AI-Powered Document Deduplication and Versioning")
    parser.add_argument("loan_id", type=int, nargs='?', help="Loan ID to process (omit for all)")
    parser.add_argument("--max-pages", type=int, default=20, help="Max pages for AI analysis (default: 20)")
    parser.add_argument("--batch-size", type=int, default=10, help="Documents per AI batch (default: 10)")
    parser.add_argument("--all", action="store_true", help="Process all loans")
    
    args = parser.parse_args()
    
    if args.all or args.loan_id is None:
        run_all_loans(args.max_pages)
    else:
        run_dedup_versioning(args.loan_id, args.max_pages, args.batch_size)


if __name__ == "__main__":
    main()
