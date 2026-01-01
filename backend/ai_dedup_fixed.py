#!/usr/bin/env python3
"""
AI-Powered Document Deduplication and Versioning (V2 - Fixed)

Fixed version that:
1. Groups ONLY same document types together
2. Correctly sets duplicate_count for masters
3. Uses document_type from individual_analysis for accurate grouping
"""

import os
import sys
import json
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND_DIR)

from db import execute_query, get_db_connection
from vlm_utils import VLMClient

SCHEMA = "modda_v2"


def get_documents_for_loan(loan_id, max_pages=40):
    """Get documents with deep JSON summary"""
    query = f"""
        SELECT 
            id, filename, file_path, page_count,
            individual_analysis->'document_summary' as doc_summary,
            text_hash, visual_dhash
        FROM {SCHEMA}.document_analysis
        WHERE loan_id = %s
          AND individual_analysis->'document_summary' IS NOT NULL
          AND (page_count <= %s OR page_count IS NULL)
        ORDER BY filename
    """
    return execute_query(query, (loan_id, max_pages))


def extract_doc_type(doc):
    """Extract document type from individual_analysis summary"""
    summary = doc.get('doc_summary') or {}
    if isinstance(summary, str):
        try:
            summary = json.loads(summary)
        except:
            return None
    
    # Try different paths to get document type
    doc_type = None
    
    # Check document_overview first
    overview = summary.get('document_overview', {})
    if overview:
        doc_type = overview.get('document_type') or overview.get('form_type')
    
    # Check metadata
    if not doc_type:
        meta = summary.get('document_metadata', {})
        doc_type = meta.get('document_type') or meta.get('form_type')
    
    # Check key_identifiers
    if not doc_type:
        key_ids = summary.get('key_identifiers', {})
        doc_type = key_ids.get('form_name') or key_ids.get('document_name')
    
    return doc_type


def normalize_doc_type(doc_type):
    """Normalize document type for grouping"""
    if not doc_type:
        return None
    
    # Lowercase and clean
    dt = doc_type.lower().strip()
    
    # Standard form mappings
    if any(x in dt for x in ['1008', 'transmittal']):
        return '1008_transmittal'
    # URLA variants - distinguish lender vs borrower sections
    if 'lender' in dt and any(x in dt for x in ['1003', 'loan information']):
        return 'urla_1003_lender'
    if any(x in dt for x in ['1003', 'urla', 'uniform residential']):
        return 'urla_1003_borrower'
    if any(x in dt for x in ['1004', 'appraisal']):
        return 'appraisal_1004'
    if any(x in dt for x in ['1103', 'scif', 'supplemental consumer']):
        return 'scif_1103'
    if any(x in dt for x in ['closing disclosure', 'cd ']):
        return 'closing_disclosure'
    if any(x in dt for x in ['loan estimate', 'le ']):
        return 'loan_estimate'
    if any(x in dt for x in ['right to cancel', 'rescission']):
        return 'right_to_cancel'
    if any(x in dt for x in ['note', 'promissory']):
        return 'promissory_note'
    if any(x in dt for x in ['4506', 'irs form 4506']):
        return 'irs_4506'
    if any(x in dt for x in ['rate lock', 'lock agreement']):
        return 'rate_lock'
    if any(x in dt for x in ['credit report']):
        return 'credit_report'
    if any(x in dt for x in ['paystub', 'pay stub', 'payslip']):
        return 'paystub'
    if any(x in dt for x in ['w-2', 'w2 ']):
        return 'w2'
    if any(x in dt for x in ['bank statement']):
        return 'bank_statement'
    if any(x in dt for x in ['deed', 'trust deed']):
        return 'deed'
    if any(x in dt for x in ['title', 'title insurance']):
        return 'title'
    
    # Just return cleaned version
    return re.sub(r'[^a-z0-9]+', '_', dt).strip('_')


def is_preliminary(filename):
    """Check if filename indicates preliminary version"""
    fn = filename.lower()
    return 'preliminary' in fn or 'prelim' in fn or 'draft' in fn


def is_final(filename):
    """Check if filename indicates final version"""
    fn = filename.lower()
    return 'final' in fn


def run_dedup_fixed(loan_id):
    """Run fixed deduplication for a loan"""
    
    print(f"\n{'='*60}")
    print(f"🔧 FIXED DEDUP/VERSIONING - Loan {loan_id}")
    print(f"{'='*60}")
    
    # Get documents
    docs = get_documents_for_loan(loan_id)
    print(f"📄 Documents to analyze: {len(docs)}")
    
    if not docs:
        return
    
    # Reset all documents first
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(f"""
        UPDATE {SCHEMA}.document_analysis
        SET status = 'pending',
            version_group_id = NULL,
            master_document_id = NULL,
            duplicate_count = 0,
            is_latest_version = false,
            version_metadata = NULL
        WHERE loan_id = %s
    """, (loan_id,))
    conn.commit()
    
    # Group by normalized document type
    type_groups = defaultdict(list)
    ungrouped = []
    
    for doc in docs:
        doc_type = extract_doc_type(doc)
        normalized = normalize_doc_type(doc_type)
        
        if normalized:
            type_groups[normalized].append({
                'id': doc['id'],
                'filename': doc['filename'],
                'doc_type': doc_type,
                'text_hash': doc.get('text_hash'),
                'visual_dhash': doc.get('visual_dhash'),
                'is_preliminary': is_preliminary(doc['filename']),
                'is_final': is_final(doc['filename'])
            })
        else:
            ungrouped.append(doc)
    
    print(f"📊 Document type groups: {len(type_groups)}")
    print(f"📦 Ungrouped: {len(ungrouped)}")
    
    group_num = 0
    total_dups = 0
    total_superseded = 0
    
    for doc_type, group_docs in type_groups.items():
        if len(group_docs) == 1:
            # Single doc - mark as unique
            cur.execute(f"""
                UPDATE {SCHEMA}.document_analysis
                SET status = 'unique',
                    is_latest_version = true,
                    version_metadata = %s
                WHERE id = %s
            """, (
                json.dumps({
                    'doc_type': doc_type,
                    'analyzed_at': datetime.now().isoformat()
                }),
                group_docs[0]['id']
            ))
            continue
        
        # Multiple docs of same type
        group_num += 1
        group_id = f"G{group_num:03d}"
        
        # Find duplicates by hash
        hash_map = defaultdict(list)
        for d in group_docs:
            key = d.get('text_hash') or d.get('visual_dhash') or f"id_{d['id']}"
            hash_map[key].append(d)
        
        # Process each hash group
        masters = []
        for hash_key, hash_docs in hash_map.items():
            if len(hash_docs) == 1:
                masters.append(hash_docs[0])
            else:
                # Multiple with same hash - first is master, rest are duplicates
                master = hash_docs[0]
                master['dup_count'] = len(hash_docs) - 1
                masters.append(master)
                
                for dup in hash_docs[1:]:
                    cur.execute(f"""
                        UPDATE {SCHEMA}.document_analysis
                        SET status = 'duplicate',
                            master_document_id = %s,
                            version_group_id = %s,
                            version_metadata = %s
                        WHERE id = %s
                    """, (
                        master['id'],
                        group_id,
                        json.dumps({
                            'doc_type': doc_type,
                            'duplicate_of': master['filename'],
                            'analyzed_at': datetime.now().isoformat()
                        }),
                        dup['id']
                    ))
                    total_dups += 1
        
        # Now version the masters
        if len(masters) == 1:
            # Single unique doc
            m = masters[0]
            cur.execute(f"""
                UPDATE {SCHEMA}.document_analysis
                SET status = %s,
                    is_latest_version = true,
                    version_group_id = %s,
                    duplicate_count = %s,
                    version_metadata = %s
                WHERE id = %s
            """, (
                'master' if m.get('dup_count', 0) > 0 else 'unique',
                group_id,
                m.get('dup_count', 0),
                json.dumps({
                    'doc_type': doc_type,
                    'ai_group_id': group_id,
                    'analyzed_at': datetime.now().isoformat()
                }),
                m['id']
            ))
        else:
            # Multiple versions - determine which is latest
            # Priority: final > no designation > preliminary
            finals = [m for m in masters if m['is_final']]
            prelims = [m for m in masters if m['is_preliminary']]
            others = [m for m in masters if not m['is_final'] and not m['is_preliminary']]
            
            # Latest is: first final, else first other, else first prelim
            if finals:
                latest = finals[0]
            elif others:
                latest = others[0]
            else:
                latest = prelims[0]
            
            for m in masters:
                is_latest = m['id'] == latest['id']
                status = 'superseded'
                if is_latest:
                    status = 'master' if m.get('dup_count', 0) > 0 else 'unique'
                else:
                    total_superseded += 1
                
                cur.execute(f"""
                    UPDATE {SCHEMA}.document_analysis
                    SET status = %s,
                        is_latest_version = %s,
                        version_group_id = %s,
                        duplicate_count = %s,
                        version_metadata = %s
                    WHERE id = %s
                """, (
                    status,
                    is_latest,
                    group_id,
                    m.get('dup_count', 0),
                    json.dumps({
                        'doc_type': doc_type,
                        'ai_group_id': group_id,
                        'version_type': 'final' if m['is_final'] else ('preliminary' if m['is_preliminary'] else 'unknown'),
                        'analyzed_at': datetime.now().isoformat()
                    }),
                    m['id']
                ))
    
    # Mark ungrouped as unique
    for doc in ungrouped:
        cur.execute(f"""
            UPDATE {SCHEMA}.document_analysis
            SET status = 'unique',
                is_latest_version = true,
                version_metadata = %s
            WHERE id = %s
        """, (
            json.dumps({
                'doc_type': 'unknown',
                'analyzed_at': datetime.now().isoformat()
            }),
            doc['id']
        ))
    
    # Mark large documents as unique
    cur.execute(f"""
        UPDATE {SCHEMA}.document_analysis
        SET status = 'unique',
            is_latest_version = true,
            version_metadata = %s::jsonb
        WHERE loan_id = %s
          AND page_count > 40
          AND status = 'pending'
    """, (json.dumps({'skip_reason': 'Large document (40+ pages)'}), loan_id))
    
    conn.commit()
    cur.close()
    conn.close()
    
    # Get final stats
    stats = execute_query(f"""
        SELECT status, COUNT(*) as cnt
        FROM {SCHEMA}.document_analysis
        WHERE loan_id = %s
        GROUP BY status
        ORDER BY cnt DESC
    """, (loan_id,))
    
    print(f"\n📊 Results:")
    for s in stats:
        print(f"   {s['status']}: {s['cnt']}")
    print(f"   Total duplicates: {total_dups}")
    print(f"   Total superseded: {total_superseded}")
    print(f"{'='*60}\n")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("loan_id", type=int, nargs='?')
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    
    if args.all or args.loan_id is None:
        loans = execute_query("SELECT id FROM loans ORDER BY id")
        for loan in loans:
            run_dedup_fixed(loan['id'])
    else:
        run_dedup_fixed(args.loan_id)


if __name__ == "__main__":
    main()
