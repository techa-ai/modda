#!/usr/bin/env python3
"""
AI Document Deduplication and Versioning V3

KEY INSIGHT: We pre-group documents by their extracted doc_type FIRST,
then ask Claude ONLY to identify versions/duplicates within each type group.

This prevents Claude from incorrectly grouping different document types together.
"""

import os
import sys
import json
import re
from datetime import datetime
from collections import defaultdict

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND_DIR)

from db import execute_query, get_db_connection
from vlm_utils import VLMClient

SCHEMA = "modda_v2"


def get_documents_for_loan(loan_id, max_pages=20):
    """Get documents with deep JSON, limited by page count"""
    query = f"""
        SELECT 
            id, filename, file_path, page_count,
            individual_analysis as full_analysis,
            text_hash, visual_dhash
        FROM {SCHEMA}.document_analysis
        WHERE loan_id = %s
          AND individual_analysis IS NOT NULL
          AND (page_count <= %s OR page_count IS NULL)
        ORDER BY filename
    """
    return execute_query(query, (loan_id, max_pages))


def extract_doc_type(full_analysis):
    """Extract document type from individual_analysis"""
    if isinstance(full_analysis, str):
        try:
            full_analysis = json.loads(full_analysis)
        except:
            return None
    
    summary = full_analysis.get('document_summary', {})
    if not summary:
        return None
    
    overview = summary.get('document_overview', {})
    return overview.get('document_type') or overview.get('form_type')


def normalize_doc_type(doc_type):
    """Normalize document type for grouping"""
    if not doc_type:
        return None
    
    dt = doc_type.lower().strip()
    
    # Normalize common patterns
    if '1008' in dt or 'transmittal' in dt:
        return 'form_1008'
    if '1103' in dt or 'scif' in dt:
        return 'form_1103'
    if 'urla' in dt or '1003' in dt:
        if 'lender' in dt:
            return 'form_1003_lender'
        return 'form_1003_borrower'
    if 'closing disclosure' in dt:
        return 'closing_disclosure'
    if 'loan estimate' in dt:
        return 'loan_estimate'
    if 'right to cancel' in dt or 'rescission' in dt:
        return 'right_to_cancel'
    if '4506' in dt:
        return 'form_4506'
    if 'flood' in dt and 'notice' in dt:
        return 'flood_notice'
    if 'rate lock' in dt:
        return 'rate_lock'
    if 'borrower' in dt and 'certification' in dt:
        return 'borrower_certification'
    if 'taxpayer consent' in dt:
        return 'taxpayer_consent'
    
    # Clean up
    return re.sub(r'[^a-z0-9]+', '_', dt).strip('_')[:50]


def analyze_type_group(type_name, docs, client):
    """
    Ask Claude to identify duplicates/versions within a single doc type group.
    Since all docs are the same type, Claude just needs to identify which are versions.
    """
    
    if len(docs) == 1:
        # Single doc - mark as unique
        return [{
            'id': docs[0]['id'],
            'status': 'unique',
            'is_latest_version': True,
            'version_type': 'final' if 'final' in docs[0]['filename'].lower() else 'unknown'
        }]
    
    # Prepare compact data for Claude
    doc_data = []
    for d in docs:
        analysis = d.get('analysis_data', {})
        doc_data.append({
            'id': d['id'],
            'filename': d['filename'],
            'text_hash': d.get('text_hash', ''),
            'visual_dhash': d.get('visual_dhash', ''),
            'summary': analysis.get('document_summary', {})
        })
    
    prompt = f"""You have {len(docs)} documents that are ALL THE SAME TYPE: "{type_name}"

These documents may be:
1. DUPLICATES (exact same content - same text_hash or visual_dhash)
2. VERSIONS (same form but preliminary vs final, or different dates)

DOCUMENT DATA:
{json.dumps(doc_data, indent=2, default=str)}

TASK: Identify the relationships between these documents.

OUTPUT FORMAT (strict JSON):
{{
  "analysis": [
    {{
      "id": <doc_id>,
      "status": "master|unique|duplicate|superseded",
      "master_id": <id of master if duplicate, else null>,
      "is_latest_version": true|false,
      "version_type": "final|preliminary|unknown",
      "reasoning": "Brief explanation"
    }}
  ]
}}

RULES:
1. "master" = the primary document (final version, or first if all same)
2. "duplicate" = exact same content as another doc (needs master_id)
3. "superseded" = older version replaced by newer (e.g., preliminary replaced by final)
4. "unique" = only one doc of this type exists

Return ONLY valid JSON."""

    try:
        result = client.process_text(json.dumps(doc_data, default=str), prompt, return_json=True)
        
        if isinstance(result, str):
            match = re.search(r'\{[\s\S]*\}', result)
            if match:
                result = json.loads(match.group())
        
        if result and 'analysis' in result:
            return result['analysis']
    except Exception as e:
        print(f"    ❌ Error analyzing {type_name}: {e}")
    
    # Fallback: mark all as unique
    return [{'id': d['id'], 'status': 'unique', 'is_latest_version': True} for d in docs]


def run_dedup_v3(loan_id, max_pages=20):
    """Run V3 deduplication pipeline"""
    
    print(f"\n{'='*70}")
    print(f"🔍 AI DEDUP V3 - Loan {loan_id}")
    print(f"   Strategy: Pre-group by doc type, then ask Claude for versions")
    print(f"{'='*70}")
    
    # Get documents
    docs = get_documents_for_loan(loan_id, max_pages)
    print(f"\n📄 Documents for analysis: {len(docs)}")
    
    if not docs:
        print("❌ No documents found")
        return
    
    # Reset documents
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(f"""
        UPDATE {SCHEMA}.document_analysis
        SET status = 'pending',
            version_group_id = NULL,
            master_document_id = NULL,
            is_latest_version = false
        WHERE loan_id = %s AND page_count <= %s
    """, (loan_id, max_pages))
    conn.commit()
    
    # Group by document type
    type_groups = defaultdict(list)
    ungrouped = []
    
    for doc in docs:
        analysis = doc.get('full_analysis') or {}
        if isinstance(analysis, str):
            try:
                analysis = json.loads(analysis)
            except:
                analysis = {}
        
        raw_type = extract_doc_type(analysis)
        normalized = normalize_doc_type(raw_type)
        
        doc_info = {
            'id': doc['id'],
            'filename': doc['filename'],
            'text_hash': doc.get('text_hash'),
            'visual_dhash': doc.get('visual_dhash'),
            'raw_type': raw_type,
            'analysis_data': analysis
        }
        
        if normalized:
            type_groups[normalized].append(doc_info)
        else:
            ungrouped.append(doc_info)
    
    print(f"📊 Document type groups: {len(type_groups)}")
    for t, docs_list in sorted(type_groups.items(), key=lambda x: -len(x[1])):
        if len(docs_list) > 1:
            print(f"   {t}: {len(docs_list)} docs")
    print(f"📦 Ungrouped: {len(ungrouped)}")
    
    # Process each type group
    client = VLMClient(model='claude-opus-4-5', max_tokens=8000)
    group_num = 0
    
    for type_name, type_docs in type_groups.items():
        if len(type_docs) == 1:
            # Single doc - mark as unique
            cur.execute(f"""
                UPDATE {SCHEMA}.document_analysis
                SET status = 'unique',
                    is_latest_version = true,
                    version_metadata = %s
                WHERE id = %s
            """, (json.dumps({'doc_type': type_name}), type_docs[0]['id']))
            continue
        
        # Multiple docs of same type - ask Claude
        group_num += 1
        group_id = f"G{group_num:03d}"
        print(f"  🔍 Analyzing {type_name} ({len(type_docs)} docs)...")
        
        results = analyze_type_group(type_name, type_docs, client)
        
        for res in results:
            doc_id = res.get('id')
            if not doc_id:
                continue
            
            status = res.get('status', 'unique')
            master_id = res.get('master_id')
            is_latest = res.get('is_latest_version', False)
            
            cur.execute(f"""
                UPDATE {SCHEMA}.document_analysis
                SET status = %s,
                    version_group_id = %s,
                    master_document_id = %s,
                    is_latest_version = %s,
                    version_metadata = %s
                WHERE id = %s
            """, (
                status,
                group_id,
                master_id,
                is_latest,
                json.dumps({
                    'doc_type': type_name,
                    'version_type': res.get('version_type'),
                    'reasoning': res.get('reasoning')
                }),
                doc_id
            ))
    
    # Mark ungrouped as unique
    for doc in ungrouped:
        cur.execute(f"""
            UPDATE {SCHEMA}.document_analysis
            SET status = 'unique',
                is_latest_version = true,
                version_metadata = %s
            WHERE id = %s
        """, (json.dumps({'doc_type': 'unknown'}), doc['id']))
    
    # Mark large docs as unique
    cur.execute(f"""
        UPDATE {SCHEMA}.document_analysis
        SET status = 'unique',
            is_latest_version = true
        WHERE loan_id = %s AND page_count > %s AND status = 'pending'
    """, (loan_id, max_pages))
    
    conn.commit()
    cur.close()
    conn.close()
    
    # Show results
    stats = execute_query(f"""
        SELECT status, COUNT(*) as cnt
        FROM {SCHEMA}.document_analysis
        WHERE loan_id = %s
        GROUP BY status
        ORDER BY cnt DESC
    """, (loan_id,))
    
    print(f"\n📊 Final Status:")
    for s in stats:
        print(f"   {s['status']}: {s['cnt']}")
    
    # Show version groups
    groups = execute_query(f"""
        SELECT version_group_id, COUNT(*) as cnt
        FROM {SCHEMA}.document_analysis
        WHERE loan_id = %s AND version_group_id IS NOT NULL
        GROUP BY version_group_id
        ORDER BY cnt DESC
        LIMIT 10
    """, (loan_id,))
    
    print(f"\n📋 Version Groups:")
    for g in groups:
        print(f"   {g['version_group_id']}: {g['cnt']} docs")
    
    print(f"{'='*70}\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("loan_id", type=int)
    parser.add_argument("--max-pages", type=int, default=20)
    args = parser.parse_args()
    
    run_dedup_v3(args.loan_id, args.max_pages)
