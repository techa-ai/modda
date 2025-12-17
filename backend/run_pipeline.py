#!/usr/bin/env python3
"""
MODDA Document Processing Pipeline Orchestrator

This script runs the complete pipeline from raw documents to 1008 evidencing.
All values are extracted systematically from source documents via Claude - no hardcoding.

Usage:
    python run_pipeline.py --loan-id 1 --stages all
    python run_pipeline.py --loan-id 1 --stages deep-extract,evidence,calculations
    python run_pipeline.py --loan-id 1 --stages calculations --force
"""

import argparse
import sys
import time
from datetime import datetime
from db import execute_query, execute_one, get_db_connection

# Stage definitions
STAGES = {
    'ingest': {
        'name': 'Document Ingestion',
        'description': 'Load raw documents into database',
        'script': None,  # Handled by API upload
    },
    'dedup': {
        'name': 'Deduplication',
        'description': 'Identify and flag duplicate documents',
        'script': 'dedup_task.py',
        'function': 'run_deduplication'
    },
    'classify': {
        'name': 'LLM Classification',
        'description': 'Classify documents using Claude',
        'script': 'step2_llm_analysis.py',
        'function': 'run_llm_version_analysis'
    },
    'group': {
        'name': 'Document Grouping',
        'description': 'Group similar documents together',
        'script': 'step3_comprehensive_grouping.py',
        'function': 'run_grouping'
    },
    'enrich': {
        'name': 'Enrich Groups',
        'description': 'Add metadata to document groups',
        'script': 'step4_enrich_groups.py',
        'function': 'enrich_groups'
    },
    'financial': {
        'name': 'Financial Classification',
        'description': 'Classify as financial/non-financial',
        'script': 'step5_financial_classification.py',
        'function': 'classify_financial'
    },
    'global-class': {
        'name': 'Global Classification',
        'description': 'Apply global document type classification',
        'script': 'step6_global_classification.py',
        'function': 'run_global_classification'
    },
    'version': {
        'name': 'Version Detection',
        'description': 'Identify document versions and mark latest',
        'script': 'step7_apply_ai_versioning.py',
        'function': 'apply_versioning'
    },
    'deep-extract': {
        'name': 'Deep JSON Extraction',
        'description': 'Extract page-wise JSON from important documents',
        'script': 'batch_deep_extraction.py',
        'function': 'run_batch_extraction'
    },
    'evidence': {
        'name': 'Evidence Identification',
        'description': 'Match 1008 attributes to evidence documents',
        'script': 'step8_identify_evidence.py',
        'function': 'identify_evidence'
    },
    'calculations': {
        'name': 'Generate Calculations',
        'description': 'Create multi-step calculations with document references',
        'script': 'step9_generate_calculations.py',
        'function': 'generate_all_calculations'
    }
}

# Stage order for 'all'
STAGE_ORDER = [
    'dedup', 'classify', 'group', 'enrich', 'financial', 
    'global-class', 'version', 'deep-extract', 'evidence', 'calculations'
]


def log(message, level='INFO'):
    """Print timestamped log message"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] [{level}] {message}")


def get_loan_stats(loan_id):
    """Get current loan processing statistics"""
    stats = {}
    
    # Total documents
    result = execute_one(
        "SELECT COUNT(*) as cnt FROM document_analysis WHERE loan_id = %s",
        (loan_id,)
    )
    stats['total_docs'] = result['cnt'] if result else 0
    
    # Unique (non-duplicate) documents
    result = execute_one(
        "SELECT COUNT(*) as cnt FROM document_analysis WHERE loan_id = %s AND status != 'duplicate'",
        (loan_id,)
    )
    stats['unique_docs'] = result['cnt'] if result else 0
    
    # Documents with VLM analysis
    result = execute_one(
        "SELECT COUNT(*) as cnt FROM document_analysis WHERE loan_id = %s AND vlm_analysis IS NOT NULL",
        (loan_id,)
    )
    stats['docs_with_vlm'] = result['cnt'] if result else 0
    
    # Important documents (financial)
    result = execute_one(
        """SELECT COUNT(*) as cnt FROM document_analysis 
           WHERE loan_id = %s AND status != 'duplicate'
           AND (version_metadata->>'financial_category' = 'FINANCIAL' 
                OR version_metadata->>'classification' = 'FINANCIAL')""",
        (loan_id,)
    )
    stats['financial_docs'] = result['cnt'] if result else 0
    
    # 1008 attributes
    result = execute_one(
        "SELECT COUNT(*) as cnt FROM form_1008_attributes"
    )
    stats['total_1008_attrs'] = result['cnt'] if result else 0
    
    # Evidence mappings
    result = execute_one(
        "SELECT COUNT(*) as cnt FROM evidence_files WHERE loan_id = %s",
        (loan_id,)
    )
    stats['evidence_mappings'] = result['cnt'] if result else 0
    
    # Calculation steps
    result = execute_one(
        "SELECT COUNT(*) as cnt FROM calculation_steps WHERE loan_id = %s",
        (loan_id,)
    )
    stats['calculation_steps'] = result['cnt'] if result else 0
    
    # Attributes with calculation steps
    result = execute_one(
        "SELECT COUNT(DISTINCT attribute_id) as cnt FROM calculation_steps WHERE loan_id = %s",
        (loan_id,)
    )
    stats['attrs_with_steps'] = result['cnt'] if result else 0
    
    return stats


def run_stage(loan_id, stage_name, force=False):
    """Run a single pipeline stage"""
    if stage_name not in STAGES:
        log(f"Unknown stage: {stage_name}", 'ERROR')
        return False
    
    stage = STAGES[stage_name]
    log(f"Starting stage: {stage['name']}")
    log(f"  Description: {stage['description']}")
    
    if stage['script'] is None:
        log(f"  Stage '{stage_name}' requires manual action or API call", 'WARN')
        return True
    
    try:
        # Import and run the stage script
        script_name = stage['script'].replace('.py', '')
        module = __import__(script_name)
        
        if hasattr(module, stage['function']):
            func = getattr(module, stage['function'])
            result = func(loan_id)
            log(f"  ✅ Stage '{stage['name']}' completed")
            return True
        else:
            log(f"  Function '{stage['function']}' not found in {stage['script']}", 'ERROR')
            return False
            
    except ImportError as e:
        log(f"  Could not import {stage['script']}: {e}", 'ERROR')
        return False
    except Exception as e:
        log(f"  Error in stage '{stage['name']}': {e}", 'ERROR')
        import traceback
        traceback.print_exc()
        return False


def run_pipeline(loan_id, stages, force=False):
    """Run the full pipeline or specific stages"""
    log(f"=" * 60)
    log(f"MODDA Pipeline - Loan ID: {loan_id}")
    log(f"=" * 60)
    
    # Get initial stats
    log("Initial loan statistics:")
    stats = get_loan_stats(loan_id)
    for key, value in stats.items():
        log(f"  {key}: {value}")
    
    # Determine which stages to run
    if stages == ['all']:
        stages_to_run = STAGE_ORDER
    else:
        stages_to_run = stages
    
    log(f"\nStages to run: {', '.join(stages_to_run)}")
    log("-" * 60)
    
    # Run each stage
    start_time = time.time()
    results = {}
    
    for stage_name in stages_to_run:
        stage_start = time.time()
        success = run_stage(loan_id, stage_name, force)
        stage_duration = time.time() - stage_start
        
        results[stage_name] = {
            'success': success,
            'duration': stage_duration
        }
        
        log(f"  Duration: {stage_duration:.1f}s")
        
        if not success and not force:
            log(f"Stage '{stage_name}' failed. Stopping pipeline.", 'ERROR')
            break
    
    # Final stats
    total_duration = time.time() - start_time
    log("-" * 60)
    log(f"Pipeline completed in {total_duration:.1f}s")
    
    log("\nFinal loan statistics:")
    stats = get_loan_stats(loan_id)
    for key, value in stats.items():
        log(f"  {key}: {value}")
    
    # Summary
    log("\nStage Results:")
    for stage_name, result in results.items():
        status = "✅" if result['success'] else "❌"
        log(f"  {status} {stage_name}: {result['duration']:.1f}s")
    
    return all(r['success'] for r in results.values())


def main():
    parser = argparse.ArgumentParser(description='MODDA Document Processing Pipeline')
    parser.add_argument('--loan-id', type=int, required=True, help='Loan ID to process')
    parser.add_argument('--stages', type=str, default='all', 
                        help='Comma-separated list of stages or "all"')
    parser.add_argument('--force', action='store_true', 
                        help='Continue even if a stage fails')
    parser.add_argument('--list-stages', action='store_true',
                        help='List all available stages')
    
    args = parser.parse_args()
    
    if args.list_stages:
        print("\nAvailable Pipeline Stages:")
        print("-" * 60)
        for i, stage_name in enumerate(STAGE_ORDER, 1):
            stage = STAGES[stage_name]
            print(f"{i}. {stage_name}: {stage['name']}")
            print(f"   {stage['description']}")
        print()
        return
    
    # Parse stages
    if args.stages == 'all':
        stages = ['all']
    else:
        stages = [s.strip() for s in args.stages.split(',')]
    
    # Validate stages
    for stage in stages:
        if stage != 'all' and stage not in STAGES:
            print(f"Error: Unknown stage '{stage}'")
            print(f"Available stages: {', '.join(STAGES.keys())}")
            sys.exit(1)
    
    # Run pipeline
    success = run_pipeline(args.loan_id, stages, args.force)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()

