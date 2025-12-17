#!/usr/bin/env python3
"""
Step 5: Deep JSON Extraction for Loan Documents (CONCURRENT)

This step performs page-wise deep extraction using Claude Opus 4.5.
It creates:
  1. Page-by-page detailed JSON
  2. Document-level summary with document_summary node

IMPORTANT: Documents are considered "deep extracted" only if they have:
  - individual_analysis with 'document_summary' key
  
Documents with just basic metadata (from step2) will be re-processed.

Usage:
    python step5_deep_extraction.py <loan_id> [options]
    
Options:
    --limit N         Process max N documents (default: all)
    --skip-large N    Skip documents with > N pages (default: 50)
    --concurrency N   Number of parallel workers (default: 30)
    --force           Re-extract even if already has document_summary
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
from db import execute_query, execute_one, get_db_connection
from deep_json_extraction import process_evidence_document

# Setup logging
LOG_DIR = "/tmp/modda_pipeline"
os.makedirs(LOG_DIR, exist_ok=True)

# Thread-safe stats
stats_lock = Lock()

def setup_logging(loan_id):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = f"{LOG_DIR}/step5_deep_extraction_loan{loan_id}_{timestamp}.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)s | %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger(__name__), log_file

def get_documents_needing_deep_extraction(loan_id, skip_large=50, force=False):
    """
    Get documents that need deep extraction.
    A document needs deep extraction if:
    - individual_analysis is NULL, OR
    - individual_analysis exists but doesn't have 'document_summary' key
    """
    
    if force:
        query = """
            SELECT id, filename, file_path, page_count
            FROM document_analysis
            WHERE loan_id = %s
              AND status IN ('unique', 'active', 'master')
              AND page_count <= %s
            ORDER BY page_count ASC
        """
    else:
        query = """
            SELECT id, filename, file_path, page_count
            FROM document_analysis
            WHERE loan_id = %s
              AND status IN ('unique', 'active', 'master')
              AND page_count <= %s
              AND (
                  individual_analysis IS NULL 
                  OR individual_analysis->'document_summary' IS NULL
              )
            ORDER BY page_count ASC
        """
    
    return execute_query(query, (loan_id, skip_large))

def process_single_document(doc, loan_id, stats, logger, skip_large):
    """Process a single document - called by thread pool"""
    doc_id = doc['id']
    filename = doc['filename']
    page_count = doc['page_count'] or 0
    
    # Skip very large documents
    if page_count > skip_large:
        with stats_lock:
            stats['skipped'] += 1
        return {'status': 'skipped', 'filename': filename, 'reason': f'>{skip_large} pages'}
    
    # Skip large bank statements
    if 'bank_statement' in filename.lower() and page_count > 20:
        with stats_lock:
            stats['skipped'] += 1
        return {'status': 'skipped', 'filename': filename, 'reason': 'Large bank statement'}
    
    try:
        start = time.time()
        result = process_evidence_document(filename, loan_id)
        elapsed = time.time() - start
        
        if result and result.get('success'):
            with stats_lock:
                stats['success'] += 1
            return {'status': 'success', 'filename': filename, 'time': elapsed}
        else:
            error_msg = result.get('error', 'Unknown') if result else 'No result'
            with stats_lock:
                stats['errors'] += 1
            return {'status': 'error', 'filename': filename, 'error': error_msg}
            
    except Exception as e:
        with stats_lock:
            stats['errors'] += 1
        return {'status': 'error', 'filename': filename, 'error': str(e)[:100]}

def run_deep_extraction(loan_id, limit=None, skip_large=50, concurrency=30, force=False, dry_run=False):
    """Run deep extraction for a loan with concurrency"""
    
    logger, log_file = setup_logging(loan_id)
    
    logger.info("="*70)
    logger.info(f"STEP 5: DEEP JSON EXTRACTION - LOAN {loan_id}")
    logger.info(f"Started: {datetime.now()}")
    logger.info(f"Options: skip_large={skip_large}, concurrency={concurrency}, force={force}")
    logger.info(f"Log file: {log_file}")
    logger.info("="*70)
    
    # Get documents needing extraction
    docs = get_documents_needing_deep_extraction(loan_id, skip_large, force)
    
    if limit:
        docs = docs[:limit]
    
    logger.info(f"\nFound {len(docs)} documents needing deep extraction")
    logger.info(f"Running with {concurrency} parallel workers")
    
    if dry_run:
        logger.info("\n[DRY RUN] Would extract these documents:")
        for d in docs[:20]:
            logger.info(f"  - {d['filename']} ({d['page_count']} pages)")
        if len(docs) > 20:
            logger.info(f"  ... and {len(docs) - 20} more")
        return {'total': len(docs), 'processed': 0, 'errors': 0, 'dry_run': True}
    
    # Thread-safe statistics
    stats = {
        'total': len(docs),
        'success': 0,
        'errors': 0,
        'skipped': 0,
        'start_time': datetime.now()
    }
    
    # Process documents concurrently
    completed = 0
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        # Submit all tasks
        future_to_doc = {
            executor.submit(process_single_document, doc, loan_id, stats, logger, skip_large): doc 
            for doc in docs
        }
        
        # Process results as they complete
        for future in as_completed(future_to_doc):
            doc = future_to_doc[future]
            completed += 1
            
            try:
                result = future.result()
                status = result['status']
                filename = result['filename']
                
                if status == 'success':
                    logger.info(f"[{completed}/{len(docs)}] ✅ {filename} ({result.get('time', 0):.1f}s)")
                elif status == 'skipped':
                    logger.info(f"[{completed}/{len(docs)}] ⏭️ {filename} - {result.get('reason')}")
                else:
                    logger.error(f"[{completed}/{len(docs)}] ❌ {filename} - {result.get('error', 'Unknown')}")
                    
            except Exception as e:
                logger.error(f"[{completed}/{len(docs)}] ❌ {doc['filename']} - Exception: {e}")
            
            # Progress update every 20 documents
            if completed % 20 == 0:
                elapsed = (datetime.now() - stats['start_time']).total_seconds()
                rate = completed / elapsed * 60 if elapsed > 0 else 0
                remaining = (len(docs) - completed) / (rate / 60) if rate > 0 else 0
                logger.info(f"\n📊 Progress: {completed}/{len(docs)} | Rate: {rate:.1f} docs/min | ETA: {remaining/60:.1f} min\n")
    
    # Final summary
    stats['end_time'] = datetime.now()
    stats['duration'] = (stats['end_time'] - stats['start_time']).total_seconds()
    
    logger.info("\n" + "="*70)
    logger.info("DEEP EXTRACTION COMPLETE")
    logger.info("="*70)
    logger.info(f"  📄 Total documents: {stats['total']}")
    logger.info(f"  ✅ Success: {stats['success']}")
    logger.info(f"  ❌ Errors: {stats['errors']}")
    logger.info(f"  ⏭️ Skipped: {stats['skipped']}")
    logger.info(f"  ⏱️ Duration: {stats['duration']/60:.1f} minutes")
    logger.info(f"  🚀 Throughput: {stats['success'] / (stats['duration']/60):.1f} docs/min")
    logger.info(f"  📝 Log: {log_file}")
    logger.info("="*70)
    
    # Verify results
    deep_count = execute_one("""
        SELECT COUNT(*) as cnt FROM document_analysis 
        WHERE loan_id = %s AND individual_analysis->'document_summary' IS NOT NULL
    """, (loan_id,))
    logger.info(f"\n✅ Documents with deep extraction: {deep_count['cnt']}")
    
    return stats

def main():
    parser = argparse.ArgumentParser(description="Step 5: Deep JSON Extraction (Concurrent)")
    parser.add_argument("loan_id", type=int, help="Loan ID to process")
    parser.add_argument("--limit", type=int, help="Max documents to process")
    parser.add_argument("--skip-large", type=int, default=50, help="Skip docs with > N pages (default: 50)")
    parser.add_argument("--concurrency", type=int, default=30, help="Number of parallel workers (default: 30)")
    parser.add_argument("--force", action="store_true", help="Re-extract even if already done")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    
    args = parser.parse_args()
    
    stats = run_deep_extraction(
        loan_id=args.loan_id,
        limit=args.limit,
        skip_large=args.skip_large,
        concurrency=args.concurrency,
        force=args.force,
        dry_run=args.dry_run
    )
    
    return 0 if stats['errors'] == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
