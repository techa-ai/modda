#!/usr/bin/env python3
"""
Batch Process Multiple Loans - Full Pipeline to Deep Extraction

This script:
1. Copies loan folders from source to modda/documents
2. Runs ingestion for each loan
3. Runs deduplication
4. Runs classification
5. Runs deep extraction (with concurrency)

Usage:
    python batch_process_loans.py [--loans LOAN1,LOAN2,...] [--skip-copy] [--concurrency N]
"""

import os
import sys
import shutil
import subprocess
import time
import logging
import argparse
import traceback
from datetime import datetime

# Add backend to path
BACKEND_DIR = "/Users/sunny/Applications/bts/jpmorgan/mortgage/modda/backend"
sys.path.insert(0, BACKEND_DIR)

from db import execute_query, execute_one, get_db_connection

def log_to_db(loan_id, step, status, message):
    """Write log entry to processing_logs table for real-time UI display"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO processing_logs (loan_id, step, status, message)
            VALUES (%s, %s, %s, %s)
        """, (loan_id, step, status, message))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        pass  # Don't fail if logging fails

# Configuration
SOURCE_DIR = "/Users/sunny/Applications/bts/jpmorgan/mortgage/mt360-viewer/public"
TARGET_DIR = "/Users/sunny/Applications/bts/jpmorgan/mortgage/modda/documents"

# All loans to process
ALL_LOANS = [
    "loan_1642451",
    "loan_1642450",
    "loan_1642449",
    "loan_1642448",
    "loan_1598638",
    "loan_1597233",
    "loan_1584069",
    "loan_1573326",
    "loan_1528996",
    "loan_1475076",
    "loan_1448202",
    "loan_1439728",
]

# Setup logging
LOG_DIR = "/tmp/modda_batch"
os.makedirs(LOG_DIR, exist_ok=True)

def setup_logging():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = f"{LOG_DIR}/batch_process_{timestamp}.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)s | %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger(__name__), log_file

def copy_loan(loan_name, logger):
    """Copy loan folder from source to target"""
    source = os.path.join(SOURCE_DIR, loan_name)
    target = os.path.join(TARGET_DIR, loan_name)
    
    if not os.path.exists(source):
        logger.error(f"  Source not found: {source}")
        return False
    
    if os.path.exists(target):
        logger.info(f"  Already exists: {target}")
        return True
    
    logger.info(f"  Copying {source} -> {target}")
    try:
        shutil.copytree(source, target)
        doc_count = len([f for f in os.listdir(target) if f.endswith('.pdf')])
        logger.info(f"  ✅ Copied {doc_count} PDF files")
        return True
    except Exception as e:
        logger.error(f"  ❌ Copy failed: {e}")
        return False

def create_loan_in_db(loan_name, logger):
    """Create loan record in database"""
    # Extract loan number (remove 'loan_' prefix)
    loan_number = loan_name.replace("loan_", "")
    
    try:
        # Check if exists
        existing = execute_one(
            "SELECT id FROM loans WHERE loan_number = %s",
            (loan_number,)
        )
        
        if existing:
            logger.info(f"  Loan already in DB: ID {existing['id']}")
            return existing['id']
        
        # Create new loan
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO loans (loan_number, loan_name, status, created_at)
            VALUES (%s, %s, 'processing', NOW())
            RETURNING id
        """, (loan_number, loan_name))
        result = cur.fetchone()
        # Handle both tuple and dict-like result
        if result:
            loan_id = result['id'] if isinstance(result, dict) or hasattr(result, 'keys') else result[0]
        else:
            loan_id = None
        conn.commit()
        cur.close()
        conn.close()
        
        if loan_id:
            logger.info(f"  Created loan in DB: ID {loan_id}")
            return loan_id
        else:
            logger.error(f"  Failed to create loan in DB")
            return None
            
    except Exception as e:
        logger.error(f"  DB error: {e}")
        traceback.print_exc()
        return None

def run_ingestion(loan_id, loan_name, logger):
    """Run document ingestion for a loan"""
    logger.info(f"  Running ingestion...")
    log_to_db(loan_id, 'ingestion', 'running', 'Starting document ingestion...')
    
    folder_path = os.path.join(TARGET_DIR, loan_name)
    
    try:
        from processing import process_loan
        result = process_loan(loan_id, folder_path)
        
        # Count documents
        doc_count = execute_one(
            "SELECT COUNT(*) as cnt FROM document_analysis WHERE loan_id = %s",
            (loan_id,)
        )
        logger.info(f"  ✅ Ingested {doc_count['cnt']} documents")
        log_to_db(loan_id, 'ingestion', 'completed', f"Ingested {doc_count['cnt']} documents")
        return True
    except Exception as e:
        logger.error(f"  ❌ Ingestion failed: {e}")
        log_to_db(loan_id, 'ingestion', 'failed', str(e)[:200])
        traceback.print_exc()
        return False

def run_deduplication(loan_id, loan_name, logger):
    """Run deduplication for a loan"""
    logger.info(f"  Running deduplication...")
    log_to_db(loan_id, 'deduplication', 'running', 'Finding and removing duplicate documents...')
    
    folder_path = os.path.join(TARGET_DIR, loan_name)
    
    try:
        from dedup_task import run_deduplication_analysis
        run_deduplication_analysis(loan_id, folder_path)
        
        # Count unique docs
        unique = execute_one("""
            SELECT COUNT(*) as cnt FROM document_analysis 
            WHERE loan_id = %s AND status IN ('unique', 'active', 'master')
        """, (loan_id,))
        logger.info(f"  ✅ Dedup complete: {unique['cnt']} unique documents")
        log_to_db(loan_id, 'deduplication', 'completed', f"Found {unique['cnt']} unique documents")
        return True
    except Exception as e:
        logger.error(f"  ❌ Dedup error: {e}")
        log_to_db(loan_id, 'deduplication', 'failed', str(e)[:200])
        traceback.print_exc()
        return False

def run_metadata_extraction(loan_id, logger):
    """Extract metadata from deep JSON"""
    logger.info(f"  Extracting metadata from deep JSON...")
    log_to_db(loan_id, 'metadata_extraction', 'running', 'Extracting metadata from document_summary...')
    
    try:
        result = subprocess.run(
            ["python3", "step4_extract_metadata.py", str(loan_id)],
            cwd=BACKEND_DIR,
            capture_output=True,
            text=True,
            timeout=600
        )
        
        if result.returncode != 0:
            logger.error(f"  ❌ Metadata extraction failed with code {result.returncode}")
            if result.stderr:
                logger.error(f"  Stderr: {result.stderr[:500]}")
            log_to_db(loan_id, 'metadata_extraction', 'failed', f"Subprocess error code {result.returncode}")
            return False
        
        with_metadata = execute_one("""
            SELECT COUNT(*) as cnt FROM document_analysis 
            WHERE loan_id = %s AND version_metadata->>'metadata_extracted_at' IS NOT NULL
        """, (loan_id,))
        logger.info(f"  ✅ Metadata extraction complete: {with_metadata['cnt']} documents")
        log_to_db(loan_id, 'metadata_extraction', 'completed', f"Extracted metadata from {with_metadata['cnt']} documents")
        return True
    except Exception as e:
        logger.warning(f"  ⚠️ Metadata extraction error (continuing): {e}")
        log_to_db(loan_id, 'metadata_extraction', 'failed', str(e)[:200])
        traceback.print_exc()
        return True

def run_global_classification(loan_id, logger):
    """Run global classification + grouping for a loan"""
    logger.info(f"  Running global classification + grouping...")
    log_to_db(loan_id, 'global_classification', 'running', 'Classifying and grouping all documents...')
    
    try:
        result = subprocess.run(
            ["python3", "step6_global_classification.py", str(loan_id)],
            cwd=BACKEND_DIR,
            capture_output=True,
            text=True,
            timeout=3600  # 1 hour - this is comprehensive
        )
        
        if result.returncode != 0:
            logger.error(f"  ❌ Global classification failed with code {result.returncode}")
            if result.stderr:
                logger.error(f"  Stderr: {result.stderr[:500]}")
            log_to_db(loan_id, 'global_classification', 'failed', f"Subprocess error code {result.returncode}")
            return False
        
        financial = execute_one("""
            SELECT COUNT(*) as cnt FROM document_analysis 
            WHERE loan_id = %s AND version_metadata->>'classification' = 'FINANCIAL'
        """, (loan_id,))
        
        grouped = execute_one("""
            SELECT COUNT(DISTINCT version_metadata->>'group_id') as cnt FROM document_analysis 
            WHERE loan_id = %s AND version_metadata->>'group_id' IS NOT NULL
        """, (loan_id,))
        
        logger.info(f"  ✅ Classification complete: {financial['cnt']} financial docs, {grouped['cnt']} groups")
        log_to_db(loan_id, 'global_classification', 'completed', 
                 f"Found {financial['cnt']} financial docs in {grouped['cnt']} groups")
        return True
    except Exception as e:
        logger.warning(f"  ⚠️ Global classification error (continuing): {e}")
        log_to_db(loan_id, 'global_classification', 'failed', str(e)[:200])
        traceback.print_exc()
        return True

def run_ai_grouping(loan_id, logger):
    """Run AI-driven comprehensive document grouping"""
    logger.info(f"  Running AI document grouping...")
    log_to_db(loan_id, 'ai_grouping', 'running', 'Grouping documents with AI understanding...')
    
    try:
        result = subprocess.run(
            ["python3", "step3_comprehensive_grouping.py", str(loan_id)],
            cwd=BACKEND_DIR,
            capture_output=True,
            text=True,
            timeout=7200  # 2 hours - comprehensive AI analysis
        )
        
        if result.returncode != 0:
            logger.error(f"  ❌ AI grouping failed with code {result.returncode}")
            if result.stderr:
                logger.error(f"  Stderr: {result.stderr[:500]}")
            log_to_db(loan_id, 'ai_grouping', 'failed', f"Subprocess error code {result.returncode}")
            return False
        
        grouped = execute_one("""
            SELECT COUNT(DISTINCT version_metadata->>'ai_group_id') as cnt FROM document_analysis 
            WHERE loan_id = %s AND version_metadata->>'ai_group_id' IS NOT NULL
        """, (loan_id,))
        
        logger.info(f"  ✅ AI grouping complete: {grouped['cnt']} AI groups created")
        log_to_db(loan_id, 'ai_grouping', 'completed', f"Created {grouped['cnt']} AI document groups")
        return True
    except Exception as e:
        logger.warning(f"  ⚠️ AI grouping error (continuing): {e}")
        log_to_db(loan_id, 'ai_grouping', 'failed', str(e)[:200])
        traceback.print_exc()
        return True

def run_ai_versioning(loan_id, logger):
    """Run AI-driven versioning to identify latest documents"""
    logger.info(f"  Running AI versioning...")
    log_to_db(loan_id, 'ai_versioning', 'running', 'Identifying latest versions with AI...')
    
    try:
        result = subprocess.run(
            ["python3", "step7_apply_ai_versioning.py", str(loan_id)],
            cwd=BACKEND_DIR,
            capture_output=True,
            text=True,
            timeout=1800  # 30 minutes
        )
        
        if result.returncode != 0:
            logger.error(f"  ❌ AI versioning failed with code {result.returncode}")
            if result.stderr:
                logger.error(f"  Stderr: {result.stderr[:500]}")
            log_to_db(loan_id, 'ai_versioning', 'failed', f"Subprocess error code {result.returncode}")
            return False
        
        latest = execute_one("""
            SELECT COUNT(*) as cnt FROM document_analysis 
            WHERE loan_id = %s AND is_latest_version = true
        """, (loan_id,))
        
        logger.info(f"  ✅ AI versioning complete: {latest['cnt']} latest versions identified")
        log_to_db(loan_id, 'ai_versioning', 'completed', f"Identified {latest['cnt']} latest versions")
        return True
    except Exception as e:
        logger.warning(f"  ⚠️ AI versioning error (continuing): {e}")
        log_to_db(loan_id, 'ai_versioning', 'failed', str(e)[:200])
        traceback.print_exc()
        return True

def run_deep_extraction(loan_id, concurrency, logger):
    """Run deep extraction for a loan"""
    logger.info(f"  Running deep extraction (concurrency={concurrency})...")
    log_to_db(loan_id, 'deep_extraction', 'running', f'Extracting detailed JSON from documents (concurrency={concurrency})...')
    
    try:
        result = subprocess.run(
            ["python3", "step5_deep_extraction.py", str(loan_id), "--concurrency", str(concurrency)],
            cwd=BACKEND_DIR,
            capture_output=True,
            text=True,
            timeout=14400  # 4 hours max (increased from 2)
        )
        
        # Log subprocess output for debugging
        if result.returncode != 0:
            logger.error(f"  ❌ Deep extraction subprocess failed with code {result.returncode}")
            if result.stderr:
                logger.error(f"  Stderr: {result.stderr[:500]}")
            log_to_db(loan_id, 'deep_extraction', 'failed', f"Subprocess error code {result.returncode}")
            return False
        
        # Log last few lines of output
        if result.stdout:
            last_lines = result.stdout.strip().split('\n')[-5:]
            for line in last_lines:
                logger.info(f"    {line}")
        
        # Check results
        deep = execute_one("""
            SELECT SUM(CASE WHEN individual_analysis::jsonb ? 'document_summary' THEN 1 ELSE 0 END) as cnt 
            FROM document_analysis 
            WHERE loan_id = %s
        """, (loan_id,))
        
        total = execute_one("""
            SELECT COUNT(*) as cnt FROM document_analysis 
            WHERE loan_id = %s AND status IN ('unique', 'active', 'master')
        """, (loan_id,))
        
        deep_cnt = deep['cnt'] if deep and deep['cnt'] else 0
        total_cnt = total['cnt'] if total and total['cnt'] else 0
        pct = 100 * deep_cnt // total_cnt if total_cnt > 0 else 0
        
        logger.info(f"  ✅ Deep extraction: {deep_cnt}/{total_cnt} ({pct}%)")
        
        # FAIL if nothing was extracted when there should have been
        if total_cnt > 0 and deep_cnt == 0:
            logger.error(f"  ❌ Deep extraction completed but extracted 0 documents!")
            log_to_db(loan_id, 'deep_extraction', 'failed', f"Extracted 0/{total_cnt} documents - subprocess may have failed silently")
            return False
        
        log_to_db(loan_id, 'deep_extraction', 'completed', f"Deep extracted {deep_cnt}/{total_cnt} documents ({pct}%)")
        return True
    except subprocess.TimeoutExpired:
        logger.warning(f"  ⚠️ Deep extraction timed out after 4 hours")
        log_to_db(loan_id, 'deep_extraction', 'failed', 'Timed out after 4 hours')
        return False  # Changed from True to False - timeout is a failure!
    except Exception as e:
        logger.error(f"  ❌ Deep extraction error: {e}")
        log_to_db(loan_id, 'deep_extraction', 'failed', str(e)[:200])
        traceback.print_exc()
        return False

def process_single_loan(loan_name, skip_copy, concurrency, logger):
    """Process a single loan through the pipeline"""
    logger.info(f"\n{'='*60}")
    logger.info(f"PROCESSING: {loan_name}")
    logger.info(f"{'='*60}")
    
    start_time = datetime.now()
    
    try:
        # Step 1: Copy
        if not skip_copy:
            if not copy_loan(loan_name, logger):
                return False
        
        # Step 2: Create in DB
        loan_id = create_loan_in_db(loan_name, logger)
        if not loan_id:
            logger.error(f"  Failed to get/create loan ID")
            return False
        
        log_to_db(loan_id, 'pipeline', 'running', f'Starting batch pipeline for {loan_name}')
        
        # Step 3: Ingest
        if not run_ingestion(loan_id, loan_name, logger):
            return False
        
        # Step 4: Deduplicate
        if not run_deduplication(loan_id, loan_name, logger):
            return False

        # Step 5: Deep Extract (gate everything else on this)
        # If already deep extracted (>=90%), skip re-run
        try:
            deep_stats = execute_one("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN individual_analysis::jsonb ? 'document_summary' THEN 1 ELSE 0 END) as deep
                FROM document_analysis
                WHERE loan_id = %s
            """, (loan_id,))
            total_docs = deep_stats['total'] if deep_stats else 0
            deep_docs = deep_stats['deep'] if deep_stats else 0
            missing = total_docs - deep_docs

            if missing <= 0:
                # All docs already deep extracted; never rerun
                logger.info(f"  ✅ Deep extraction already complete ({deep_docs}/{total_docs}), skipping")
                log_to_db(loan_id, 'deep_extraction', 'completed', f"Deep extracted {deep_docs}/{total_docs}")
            else:
                run_deep_extraction(loan_id, concurrency, logger)
        except Exception as e:
            logger.error(f"  ❌ Deep extraction gating failed: {e}")
            log_to_db(loan_id, 'deep_extraction', 'failed', f"Gating error: {str(e)[:200]}")
            return False

        # Step 3.1: Retry failed small pages (< 20 pages)
        # TODO: Add step5b_retry_failed_extraction.py call here if needed
        
        # Step 4: Extract Metadata (from deep JSON)
        run_metadata_extraction(loan_id, logger)
        
        # Step 5: Global Classification (Financial + Grouping + Primary Selection)
        run_global_classification(loan_id, logger)
        
        # Step 6: AI Grouping (Semantic document relationships)
        run_ai_grouping(loan_id, logger)
        
        # Step 7: AI Versioning (Latest version identification)
        run_ai_versioning(loan_id, logger)
        
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(f"  ⏱️ Total time: {elapsed/60:.1f} minutes")
        
        log_to_db(loan_id, 'pipeline', 'completed', f'Pipeline completed in {elapsed/60:.1f} minutes')
        
        # Update loan status
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE loans SET status = 'enriched' WHERE id = %s", (loan_id,))
        conn.commit()
        cur.close()
        conn.close()
        
        return True
        
    except Exception as e:
        logger.error(f"  ❌ Error processing loan: {e}")
        log_to_db(loan_id, 'pipeline', 'failed', str(e)[:200]) if loan_id else None
        traceback.print_exc()
        return False

def main():
    parser = argparse.ArgumentParser(description="Batch process loans to deep extraction")
    parser.add_argument("--loans", type=str, help="Comma-separated loan names (default: all)")
    parser.add_argument("--skip-copy", action="store_true", help="Skip copying if already exists")
    parser.add_argument("--concurrency", type=int, default=10, help="Deep extraction concurrency")
    
    args = parser.parse_args()
    
    logger, log_file = setup_logging()
    
    # Determine loans to process
    if args.loans:
        loans = [l.strip() for l in args.loans.split(",")]
    else:
        loans = ALL_LOANS
    
    logger.info("="*70)
    logger.info("BATCH LOAN PROCESSING - PIPELINE TO DEEP EXTRACTION")
    logger.info(f"Started: {datetime.now()}")
    logger.info(f"Loans to process: {len(loans)}")
    logger.info(f"Concurrency: {args.concurrency}")
    logger.info(f"Log file: {log_file}")
    logger.info("="*70)
    
    # Process each loan
    results = {"success": 0, "failed": 0}
    
    for i, loan in enumerate(loans, 1):
        logger.info(f"\n[{i}/{len(loans)}] Starting {loan}")
        
        try:
            if process_single_loan(loan, args.skip_copy, args.concurrency, logger):
                results["success"] += 1
            else:
                results["failed"] += 1
        except Exception as e:
            logger.error(f"❌ Failed to process {loan}: {e}")
            traceback.print_exc()
            results["failed"] += 1
    
    # Final summary
    logger.info("\n" + "="*70)
    logger.info("BATCH PROCESSING COMPLETE")
    logger.info("="*70)
    logger.info(f"  ✅ Success: {results['success']}")
    logger.info(f"  ❌ Failed: {results['failed']}")
    logger.info(f"  📝 Log: {log_file}")
    logger.info("="*70)
    
    return 0 if results["failed"] == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
