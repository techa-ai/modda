#!/usr/bin/env python3
"""
Process Large Documents with Llama 4 Maverick
Uses Llama instead of Opus to avoid rate limits on large documents (80+ pages)
"""

import os
import sys
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from datetime import datetime

# Add paths
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
STAGE1_DIR = os.path.join(BACKEND_DIR, 'stage1')
sys.path.insert(0, BACKEND_DIR)
sys.path.insert(0, STAGE1_DIR)

from db import execute_query, get_db_connection
from llama_pagewise_extractor import LlamaClient, extract_document_pagewise

# Thread-safe stats
stats_lock = Lock()


def get_large_docs_needing_extraction():
    """Get all documents >50 pages that need deep extraction"""
    query = """
        SELECT 
            l.id as loan_id,
            l.loan_number,
            da.id as doc_id,
            da.filename,
            da.file_path,
            da.page_count
        FROM document_analysis da
        JOIN loans l ON l.id = da.loan_id
        WHERE (da.individual_analysis->'pages' IS NULL 
               OR jsonb_array_length(da.individual_analysis->'pages') = 0 
               OR da.individual_analysis->'document_summary' IS NULL)
        AND da.page_count > 50
        ORDER BY da.page_count ASC
    """
    return execute_query(query)


def process_single_document(doc, stats):
    """Process a single document using Llama"""
    loan_id = doc['loan_id']
    filename = doc['filename']
    file_path = doc['file_path']
    page_count = doc['page_count']
    
    print(f"\n🦙 Processing: {filename} ({page_count} pages)")
    
    try:
        # Create Llama client
        client = LlamaClient()
        
        # Extract using Llama page-wise
        result = extract_document_pagewise(file_path, filename, client, pdf_type="mixed", dpi=100)
        
        if result.get('success') and result.get('data'):
            # Save to database
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("""
                UPDATE document_analysis 
                SET individual_analysis = %s 
                WHERE loan_id = %s AND filename = %s
            """, (json.dumps(result['data']), loan_id, filename))
            conn.commit()
            cur.close()
            conn.close()
            
            with stats_lock:
                stats['success'] += 1
            
            print(f"✅ {filename} - {page_count} pages extracted in {result.get('duration', 0):.1f}s")
            return {'success': True, 'filename': filename, 'pages': page_count}
        else:
            with stats_lock:
                stats['failed'] += 1
            print(f"❌ {filename} - {result.get('error', 'Unknown error')}")
            return {'success': False, 'filename': filename, 'error': result.get('error')}
            
    except Exception as e:
        with stats_lock:
            stats['failed'] += 1
        print(f"❌ {filename} - Exception: {str(e)[:100]}")
        return {'success': False, 'filename': filename, 'error': str(e)}


def main():
    print(f"\n{'='*70}")
    print(f"🦙 LLAMA LARGE DOCUMENT EXTRACTION")
    print(f"   Processing documents >50 pages with Llama 4 Maverick")
    print(f"   Concurrency: 30 (Llama has higher rate limits)")
    print(f"{'='*70}")
    
    # Get documents
    docs = get_large_docs_needing_extraction()
    
    if not docs:
        print("\n✅ No large documents need extraction!")
        return 0
    
    total_pages = sum(d['page_count'] for d in docs)
    
    print(f"\n📋 Documents to process: {len(docs)}")
    print(f"📄 Total pages: {total_pages}")
    print(f"\nDocuments:")
    for d in docs:
        print(f"   - {d['loan_number']}: {d['filename']} ({d['page_count']} pages)")
    
    print(f"\n{'='*70}")
    print(f"🚀 Starting extraction...")
    print(f"{'='*70}\n")
    
    stats = {'success': 0, 'failed': 0}
    start_time = time.time()
    
    # Process with high concurrency (Llama allows more)
    with ThreadPoolExecutor(max_workers=30) as executor:
        futures = {
            executor.submit(process_single_document, doc, stats): doc 
            for doc in docs
        }
        
        for i, future in enumerate(as_completed(futures), 1):
            doc = futures[future]
            try:
                result = future.result()
            except Exception as e:
                print(f"[{i}/{len(docs)}] ❌ {doc['filename']}: {e}")
    
    elapsed = time.time() - start_time
    
    print(f"\n{'='*70}")
    print(f"📊 EXTRACTION COMPLETE")
    print(f"{'='*70}")
    print(f"   ✅ Success: {stats['success']}")
    print(f"   ❌ Failed: {stats['failed']}")
    print(f"   ⏱️ Time: {elapsed/60:.1f} minutes")
    print(f"{'='*70}\n")
    
    return 0 if stats['failed'] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
