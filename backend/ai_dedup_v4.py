#!/usr/bin/env python3
"""
Simple Document Deduplication and Versioning V4

Uses pre-grouping by doc_type with simple filename-based version detection.
No AI calls for versioning - just smart heuristics.
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

SCHEMA = "modda_v2"


def get_documents_for_loan(loan_id, max_pages=20):
    """Get documents with deep JSON"""
    query = f"""
        SELECT 
            id, filename, file_path, page_count,
            individual_analysis as full_analysis,
            text_hash, visual_dhash
        FROM {SCHEMA}.document_analysis
        WHERE loan_id = %s
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
    
    if not full_analysis:
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


def is_final(filename):
    """Check if filename indicates final version"""
    fn = filename.lower()
    return 'final' in fn or '_signed' in fn


def is_preliminary(filename):
    """Check if filename indicates preliminary version"""
    fn = filename.lower()
    return 'preliminary' in fn or 'prelim' in fn or 'draft' in fn


def version_sort_key(doc):
    """Sort key for version ordering: final first, then by filename"""
    fn = doc['filename'].lower()
    if 'final' in fn:
        return (0, fn)
    elif 'preliminary' in fn or 'prelim' in fn:
        return (2, fn)
    else:
        return (1, fn)


def run_dedup_v4(loan_id, max_pages=20):
    """Run V4 deduplication pipeline - no AI, just smart heuristics"""
    
    print(f"\n{'='*70}")
    print(f"🔍 DEDUP V4 - Loan {loan_id}")
    print(f"   Strategy: Pre-group by doc type + filename heuristics")
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
            duplicate_count = 0,
            is_latest_version = false,
            version_metadata = NULL
        WHERE loan_id = %s
    """, (loan_id,))
    conn.commit()
    
    # Group by document type
    type_groups = defaultdict(list)
    
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
            'is_final': is_final(doc['filename']),
            'is_preliminary': is_preliminary(doc['filename'])
        }
        
        if normalized:
            type_groups[normalized].append(doc_info)
        else:
            # Ungrouped - mark as unique
            type_groups[f"_unique_{doc['id']}"].append(doc_info)
    
    print(f"📊 Document type groups: {len([g for g in type_groups.values() if len(g) > 1])}")
    for t, docs_list in sorted(type_groups.items(), key=lambda x: -len(x[1])):
        if len(docs_list) > 1:
            print(f"   {t}: {len(docs_list)} docs")
    
    group_num = 0
    total_dups = 0
    total_superseded = 0
    
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
        
        # Multiple docs of same type
        group_num += 1
        group_id = f"G{group_num:03d}"
        
        # Check for duplicates by hash
        hash_groups = defaultdict(list)
        for d in type_docs:
            key = d.get('text_hash') or d.get('visual_dhash') or f"id_{d['id']}"
            hash_groups[key].append(d)
        
        # Process duplicate groups - keep first as master
        masters = []
        for hash_key, hash_docs in hash_groups.items():
            master = hash_docs[0]
            masters.append(master)
            
            # Mark rest as duplicates
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
                        'doc_type': type_name,
                        'duplicate_of': master['filename']
                    }),
                    dup['id']
                ))
                total_dups += 1
        
        # Now version the masters - sort to find latest
        masters.sort(key=version_sort_key)
        latest = masters[0]  # final comes first
        
        for i, m in enumerate(masters):
            is_latest = (m['id'] == latest['id'])
            
            if is_latest:
                status = 'unique' if len(masters) == 1 else 'master'
            else:
                status = 'superseded'
                total_superseded += 1
            
            version_type = 'final' if m['is_final'] else ('preliminary' if m['is_preliminary'] else 'unknown')
            
            cur.execute(f"""
                UPDATE {SCHEMA}.document_analysis
                SET status = %s,
                    version_group_id = %s,
                    is_latest_version = %s,
                    version_metadata = %s
                WHERE id = %s
            """, (
                status,
                group_id if len(masters) > 1 else None,
                is_latest,
                json.dumps({
                    'doc_type': type_name,
                    'version_type': version_type,
                    'group_id': group_id
                }),
                m['id']
            ))
    
    # Mark large docs as unique
    cur.execute(f"""
        UPDATE {SCHEMA}.document_analysis
        SET status = 'unique',
            is_latest_version = true,
            version_metadata = %s::jsonb
        WHERE loan_id = %s 
          AND page_count > %s 
          AND status = 'pending'
    """, (json.dumps({'skip_reason': 'Large document'}), loan_id, max_pages))
    
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
    print(f"   Duplicates: {total_dups}")
    print(f"   Superseded: {total_superseded}")
    
    # Show version groups
    groups = execute_query(f"""
        SELECT 
            version_group_id,
            COUNT(*) as cnt,
            STRING_AGG(filename, ', ' ORDER BY filename) as files
        FROM {SCHEMA}.document_analysis
        WHERE loan_id = %s AND version_group_id IS NOT NULL
        GROUP BY version_group_id
        ORDER BY cnt DESC
        LIMIT 10
    """, (loan_id,))
    
    print(f"\n📋 Version Groups:")
    for g in groups:
        print(f"   {g['version_group_id']}: {g['cnt']} docs")
        # Show first few files
        files = g['files'].split(', ')[:3]
        for f in files:
            print(f"      - {f}")
    
    print(f"{'='*70}\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("loan_id", type=int)
    parser.add_argument("--max-pages", type=int, default=20)
    args = parser.parse_args()
    
    run_dedup_v4(args.loan_id, args.max_pages)
