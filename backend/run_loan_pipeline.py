#!/usr/bin/env python3
"""
Smart Pipeline Orchestrator for Loan Processing (V3)

Runs the complete Data Tape Validation pipeline:
1. Wait for document extraction (Steps 1-7)
2. Construct Data Tape (Step 8) - Extract from Master 1008/1003
3. Systematic Verification (Step 9) - Verify against source docs
"""

import os
import sys
import time
import json
import logging
import argparse
from datetime import datetime, timedelta
from db import execute_query, execute_one, get_db_connection

# Setup logging
LOG_DIR = "/tmp/modda_pipeline"
os.makedirs(LOG_DIR, exist_ok=True)

def setup_logging(loan_id):
    """Setup comprehensive logging"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = f"{LOG_DIR}/loan_{loan_id}_{timestamp}.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)s | %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    logger = logging.getLogger(__name__)
    logger.info(f"="*70)
    logger.info(f"MODDA PIPELINE V3 - Loan {loan_id}")
    logger.info(f"Started: {datetime.now()}")
    logger.info(f"Log file: {log_file}")
    logger.info(f"="*70)
    
    return logger, log_file

def check_extraction_status(loan_id):
    """Check how many documents still need extraction"""
    stats = execute_one("""
        SELECT 
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE individual_analysis IS NOT NULL) as done,
            COUNT(*) FILTER (WHERE individual_analysis IS NULL) as remaining
        FROM document_analysis 
        WHERE loan_id = %s AND status IN ('unique', 'active', 'master')
    """, (loan_id,))
    return stats

def wait_for_extraction(loan_id, logger, timeout_minutes=60, check_interval=30):
    """Wait for deep JSON extraction to complete"""
    logger.info("\n" + "="*50)
    logger.info("STAGE: Waiting for Deep JSON Extraction")
    logger.info("="*50)
    
    start_time = datetime.now()
    timeout = timedelta(minutes=timeout_minutes)
    
    while True:
        stats = check_extraction_status(loan_id)
        elapsed = datetime.now() - start_time
        
        logger.info(f"Extraction: {stats['done']}/{stats['total']} done, {stats['remaining']} remaining (elapsed: {elapsed})")
        
        if stats['remaining'] == 0:
            logger.info("✅ All extractions complete!")
            return True
        
        if elapsed > timeout:
            logger.warning(f"⚠️ Timeout after {timeout_minutes} minutes. Proceeding with {stats['remaining']} documents unextracted.")
            return False
        
        time.sleep(check_interval)

def run_data_tape_construction(loan_id, logger):
    """Run Step 8: Data Tape Construction"""
    logger.info("\n" + "="*50)
    logger.info("STAGE 8: Data Tape Construction")
    logger.info("="*50)
    
    start_time = datetime.now()
    
    try:
        from step8_data_tape_construction import run_data_tape_construction as run_step8
        
        # This function handles 1008/1003 finding and extraction
        run_step8(loan_id)
        
        # Check results
        attr_count = execute_one("""
            SELECT COUNT(*) as cnt FROM extracted_1008_data WHERE loan_id = %s
        """, (loan_id,))
        
        elapsed = datetime.now() - start_time
        logger.info(f"✅ Data Tape Construction complete in {elapsed}")
        logger.info(f"   Attributes populated: {attr_count['cnt']}")
        
        if attr_count['cnt'] == 0:
            logger.warning("⚠️ Data Tape is empty! No attributes extracted.")
            return False
            
        return True
        
    except Exception as e:
        logger.error(f"❌ Data Tape Construction failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

def run_systematic_verification(loan_id, logger):
    """Run Step 9: Systematic Verification (Golden Standard)"""
    logger.info("\n" + "="*50)
    logger.info("STAGE 9: Systematic Verification")
    logger.info("="*50)
    
    start_time = datetime.now()
    
    try:
        from run_full_verification import run_verification
        
        # This runs batch verification + second pass
        run_verification(loan_id)
        
        # Check results
        evidence_stats = execute_one("""
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE verification_status = 'verified') as verified
            FROM evidence_files WHERE loan_id = %s
        """, (loan_id,))
        
        elapsed = datetime.now() - start_time
        logger.info(f"✅ Systematic Verification complete in {elapsed}")
        logger.info(f"   Total Attributes: {evidence_stats['total']}")
        logger.info(f"   Verified: {evidence_stats['verified']}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Verification failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

def generate_summary_report(loan_id, logger):
    """Generate final summary report"""
    logger.info("\n" + "="*50)
    logger.info("PIPELINE SUMMARY REPORT")
    logger.info("="*50)
    
    # Document stats
    doc_stats = execute_one("""
        SELECT 
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE individual_analysis IS NOT NULL) as analyzed
        FROM document_analysis WHERE loan_id = %s
    """, (loan_id,))
    
    # Evidence stats
    evidence_stats = execute_one("""
        SELECT 
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE verification_status = 'verified') as verified,
            COUNT(*) FILTER (WHERE verification_status = 'not_verified') as not_verified
        FROM evidence_files WHERE loan_id = %s
    """, (loan_id,))
    
    # Data Tape stats
    tape_stats = execute_one("""
        SELECT COUNT(*) as total
        FROM extracted_1008_data WHERE loan_id = %s
    """, (loan_id,))
    
    logger.info(f"\n📊 DOCUMENTS")
    logger.info(f"   Total: {doc_stats['total']}")
    logger.info(f"   Analyzed: {doc_stats['analyzed']}")
    
    logger.info(f"\n📋 DATA TAPE")
    logger.info(f"   Attributes: {tape_stats['total']}")
    
    logger.info(f"\n✅ VERIFICATION")
    logger.info(f"   Total: {evidence_stats['total']}")
    logger.info(f"   Verified: {evidence_stats['verified']}")
    logger.info(f"   Not Verified: {evidence_stats['not_verified']}")
    
    return True

def run_loan_pipeline(loan_id, skip_wait=False, timeout_minutes=60):
    """Main entry point for pipeline execution"""
    logger, log_file = setup_logging(loan_id)
    
    pipeline_start = datetime.now()
    success = True
    
    try:
        # Step 1: Wait for extraction (unless skipped)
        if not skip_wait:
            extraction_complete = wait_for_extraction(loan_id, logger, timeout_minutes)
            if not extraction_complete:
                logger.warning("Proceeding despite incomplete extraction")
        
        # Step 8: Data Tape Construction
        if not run_data_tape_construction(loan_id, logger):
            success = False
            logger.error("Data Tape Construction had errors")
        
        # Step 9: Systematic Verification
        if not run_systematic_verification(loan_id, logger):
            success = False
            logger.error("Verification had errors")
        
        # Final Summary
        generate_summary_report(loan_id, logger)
        
        pipeline_end = datetime.now()
        total_time = pipeline_end - pipeline_start
        
        logger.info("\n" + "="*70)
        if success:
            logger.info(f"✅ PIPELINE COMPLETED SUCCESSFULLY")
        else:
            logger.info(f"⚠️ PIPELINE COMPLETED WITH ERRORS")
        logger.info(f"Total time: {total_time}")
        logger.info(f"Log file: {log_file}")
        logger.info("="*70)
        
        return success
        
    except Exception as e:
        logger.error(f"\n❌ PIPELINE FAILED: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run MODDA pipeline for a loan")
    parser.add_argument("loan_id", type=int, help="Loan ID to process")
    parser.add_argument("--skip-wait", action="store_true", help="Skip waiting for extraction")
    parser.add_argument("--timeout", type=int, default=60, help="Extraction timeout in minutes")
    args = parser.parse_args()
    
    success = run_loan_pipeline(args.loan_id, args.skip_wait, args.timeout)
    sys.exit(0 if success else 1)
