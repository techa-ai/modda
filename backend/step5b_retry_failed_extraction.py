#!/usr/bin/env python3
"""
Step 5b: Retry Failed Deep Extraction for Small Documents

This script finds all documents that:
1. Are missing deep extraction (no document_summary)
2. Have page_count <= threshold (default 20 pages)
3. Are not intentionally skipped (large tax returns, bank statements, etc.)

Usage:
    python step5b_retry_failed_extraction.py [options]
    
Options:
    --loan-id N       Process only specific loan (default: all loans)
    --max-pages N     Only retry docs with <= N pages (default: 20)
    --concurrency N   Number of parallel workers (default: 10)
    --dry-run         Show what would be extracted without doing it
"""

import os
import sys
import json
import time
import logging
import argparse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from db import execute_query, execute_one
from deep_json_extraction import process_evidence_document

# Setup logging
LOG_DIR = "/tmp/modda_pipeline"
os.makedirs(LOG_DIR, exist_ok=True)

# Thread-safe stats
stats_lock = Lock()

def setup_logging():
    """Setup logging for this run"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(LOG_DIR, f"step5b_retry_failed_{timestamp}.log")
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)s | %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__), log_file

def get_failed_documents(loan_id=None, max_pages=20):
    """Get all documents that failed deep extraction and are small enough to retry"""
    
    # Patterns to skip (large documents that aren't worth retrying)
    skip_patterns = [
        'tax_returns',
        'wage_transcript', 
        'bank_statement',
        'property_cda_report'
    ]
    
    if loan_id:
        query = """
            SELECT da.id, da.filename, da.loan_id, da.page_count, l.loan_number
            FROM document_analysis da
            JOIN loans l ON l.id = da.loan_id
            WHERE da.loan_id = %s
            AND da.status IN ('unique', 'master', 'active')
            AND da.page_count <= %s
            AND da.page_count > 0
            AND (da.individual_analysis IS NULL 
                 OR NOT (da.individual_analysis::jsonb ? 'document_summary'))
            ORDER BY da.loan_id, da.page_count
        """
        docs = execute_query(query, (loan_id, max_pages))
    else:
        query = """
            SELECT da.id, da.filename, da.loan_id, da.page_count, l.loan_number
            FROM document_analysis da
            JOIN loans l ON l.id = da.loan_id
            WHERE da.status IN ('unique', 'master', 'active')
            AND da.page_count <= %s
            AND da.page_count > 0
            AND (da.individual_analysis IS NULL 
                 OR NOT (da.individual_analysis::jsonb ? 'document_summary'))
            ORDER BY da.loan_id, da.page_count
        """
        docs = execute_query(query, (max_pages,))
    
    # Filter out known large document types
    filtered = []
    for doc in docs:
        filename_lower = doc['filename'].lower()
        should_skip = any(pattern in filename_lower for pattern in skip_patterns)
        if not should_skip:
            filtered.append(doc)
    
    return filtered

def process_single_document(doc, stats, logger):
    """Process a single document - called by thread pool"""
    doc_id = doc['id']
    filename = doc['filename']
    loan_id = doc['loan_id']
    page_count = doc['page_count'] or 0
    
    try:
        start = time.time()
        result = process_evidence_document(filename, loan_id)
        elapsed = time.time() - start
        
        if result and result.get('success'):
            with stats_lock:
                stats['success'] += 1
            return {'status': 'success', 'filename': filename, 'loan_id': loan_id, 'time': elapsed}
        else:
            error_msg = result.get('error', 'Unknown') if result else 'No result'
            with stats_lock:
                stats['errors'] += 1
            return {'status': 'error', 'filename': filename, 'loan_id': loan_id, 'error': error_msg}
            
    except Exception as e:
        with stats_lock:
            stats['errors'] += 1
        return {'status': 'error', 'filename': filename, 'loan_id': loan_id, 'error': str(e)[:100]}

def run_retry_extraction(loan_id=None, max_pages=20, concurrency=10, dry_run=False):
    """Run retry extraction for failed documents"""
    
    logger, log_file = setup_logging()
    
    logger.info("=" * 70)
    logger.info("STEP 5B: RETRY FAILED DEEP EXTRACTION")
    logger.info(f"Started: {datetime.now()}")
    logger.info(f"Options: loan_id={loan_id or 'ALL'}, max_pages={max_pages}, concurrency={concurrency}")
    logger.info(f"Log file: {log_file}")
    logger.info("=" * 70)
    
    # Get failed documents
    docs = get_failed_documents(loan_id, max_pages)
    
    if not docs:
        logger.info("\n✅ No failed documents found to retry!")
        return {'success': 0, 'errors': 0, 'total': 0}
    
    # Group by loan for display
    by_loan = {}
    for doc in docs:
        lid = doc['loan_id']
        if lid not in by_loan:
            by_loan[lid] = []
        by_loan[lid].append(doc)
    
    logger.info(f"\nFound {len(docs)} documents to retry across {len(by_loan)} loans:")
    for lid, loan_docs in sorted(by_loan.items()):
        loan_num = loan_docs[0]['loan_number']
        logger.info(f"  Loan {lid} ({loan_num}): {len(loan_docs)} docs")
    
    if dry_run:
        logger.info("\n[DRY RUN] Would process these documents:")
        for doc in docs[:20]:  # Show first 20
            logger.info(f"  • {doc['filename']} ({doc['page_count']} pages) - Loan {doc['loan_id']}")
        if len(docs) > 20:
            logger.info(f"  ... and {len(docs) - 20} more")
        return {'success': 0, 'errors': 0, 'total': len(docs), 'dry_run': True}
    
    # Process with thread pool
    stats = {'success': 0, 'errors': 0}
    start_time = time.time()
    
    logger.info(f"\nProcessing {len(docs)} documents with {concurrency} workers...")
    
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {
            executor.submit(process_single_document, doc, stats, logger): doc 
            for doc in docs
        }
        
        completed = 0
        for future in as_completed(futures):
            completed += 1
            result = future.result()
            
            if result['status'] == 'success':
                logger.info(f"[{completed}/{len(docs)}] ✅ {result['filename']} ({result['time']:.1f}s)")
            else:
                logger.warning(f"[{completed}/{len(docs)}] ❌ {result['filename']}: {result.get('error', 'Unknown')}")
            
            # Progress update every 10 docs
            if completed % 10 == 0:
                elapsed = time.time() - start_time
                rate = completed / elapsed * 60 if elapsed > 0 else 0
                eta = (len(docs) - completed) / rate if rate > 0 else 0
                logger.info(f"\n📊 Progress: {completed}/{len(docs)} | Rate: {rate:.1f} docs/min | ETA: {eta:.1f} min\n")
    
    # Final stats
    elapsed = time.time() - start_time
    logger.info("\n" + "=" * 70)
    logger.info("RETRY EXTRACTION COMPLETE")
    logger.info("=" * 70)
    logger.info(f"  📄 Total documents: {len(docs)}")
    logger.info(f"  ✅ Success: {stats['success']}")
    logger.info(f"  ❌ Errors: {stats['errors']}")
    logger.info(f"  ⏱️ Duration: {elapsed/60:.1f} minutes")
    logger.info(f"  🚀 Throughput: {len(docs)/elapsed*60:.1f} docs/min")
    logger.info("=" * 70)
    
    return stats

def main():
    parser = argparse.ArgumentParser(description='Retry failed deep extraction for small documents')
    parser.add_argument('--loan-id', type=int, help='Process only specific loan ID')
    parser.add_argument('--max-pages', type=int, default=20, help='Max pages to retry (default: 20)')
    parser.add_argument('--concurrency', type=int, default=10, help='Number of parallel workers (default: 10)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be processed')
    
    args = parser.parse_args()
    
    run_retry_extraction(
        loan_id=args.loan_id,
        max_pages=args.max_pages,
        concurrency=args.concurrency,
        dry_run=args.dry_run
    )

if __name__ == "__main__":
    main()



