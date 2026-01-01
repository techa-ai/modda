#!/usr/bin/env python3
"""
Stage 1 - Step 2 Substep 2: Retry Failed Extractions
Retry extraction for documents that failed in 1_2_1

Reads the extraction_summary.json to identify failed documents
Retries extraction with potential adjustments:
- Lower DPI for large documents
- Extended timeouts

Naming: 1_2_2 = Stage 1, Step 2, Substep 2
"""

import os
import sys
import json
import time
from pathlib import Path
from datetime import datetime

# Import shared page-wise extraction functions
from llama_pagewise_extractor import (
    LlamaClient,
    extract_document_pagewise
)


def retry_failed_extractions(loan_id: str, stage1_output_dir: Path, documents_dir: Path):
    """Retry all failed extractions from 1_2_1"""
    
    print("\n" + "="*80)
    print(f"🔄 STAGE 1 STEP 2.2: Retry Failed Extractions - {loan_id}")
    print(f"Model: Llama 4 Maverick 17B Instruct (with adjusted parameters)")
    print(f"Format: Page-wise (matching Claude Opus)")
    print("="*80)
    
    # Load extraction summary from 1_2_1
    summary_file = stage1_output_dir / "1_2_1_llama_extractions" / "extraction_summary.json"
    
    if not summary_file.exists():
        print(f"❌ Error: 1_2_1 summary not found: {summary_file}")
        print("   Run 1_2_1_deep_extract_llama.py first!")
        return None
    
    with open(summary_file, 'r') as f:
        previous_summary = json.load(f)
    
    # Find failed extractions
    failed_files = []
    for result in previous_summary['results']:
        if not result['success']:
            failed_files.append(result['filename'])
    
    if not failed_files:
        print("\n✅ No failed extractions to retry!")
        print("   All documents were successfully extracted in 1_2_1")
        return None
    
    print(f"\n📄 Found {len(failed_files)} failed extraction(s) to retry:")
    for f in failed_files:
        print(f"   - {f}")
    print()
    
    # Create output directory
    output_dir = stage1_output_dir / "1_2_2_retry_extractions"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize Llama client
    client = LlamaClient()
    
    # Retry each failed document
    results = []
    successful = 0
    still_failed = 0
    
    for idx, filename in enumerate(failed_files, 1):
        print(f"\n[{idx}/{len(failed_files)}] Retrying: {filename}")
        print("-" * 80)
        
        # Get full path to PDF
        pdf_path = documents_dir / filename
        
        if not pdf_path.exists():
            print(f"  ⚠️ Warning: PDF not found: {pdf_path}")
            results.append({
                'success': False,
                'filename': filename,
                'error': 'File not found',
                'retry_attempt': True
            })
            still_failed += 1
            continue
        
        # Retry extraction with adjusted parameters (lower DPI)
        print(f"  ⚙️  Retry config: Lower DPI (120 instead of 150)")
        result = extract_document_pagewise(str(pdf_path), filename, client, pdf_type="scanned", dpi=120)
        
        # Mark as retry attempt
        if result['success']:
            result['data']['_extraction_metadata']['retry_attempt'] = True
            result['data']['_extraction_metadata']['retry_dpi'] = 120
        
        results.append(result)
        
        # Save individual JSON file if successful
        if result['success']:
            output_file = output_dir / f"{Path(filename).stem}.json"
            with open(output_file, 'w') as f:
                json.dump(result['data'], f, indent=2)
            print(f"  💾 Saved: {output_file.name}")
            successful += 1
        else:
            still_failed += 1
        
        # Delay to avoid rate limiting
        time.sleep(2)
    
    # Save retry summary
    retry_summary = {
        'loan_id': loan_id,
        'retry_timestamp': datetime.now().isoformat(),
        'model': 'llama-4-maverick-17b',
        'extraction_format': 'page_wise',
        'original_failed_count': len(failed_files),
        'retry_successful': successful,
        'still_failed': still_failed,
        'retry_config': {'dpi': 120},
        'results': results
    }
    
    summary_file_retry = output_dir / "retry_summary.json"
    with open(summary_file_retry, 'w') as f:
        json.dump(retry_summary, f, indent=2)
    
    # Print final summary
    print("\n" + "="*80)
    print("📊 RETRY SUMMARY")
    print("="*80)
    print(f"  Original failures: {len(failed_files)}")
    print(f"  ✅ Now successful: {successful}")
    print(f"  ❌ Still failed: {still_failed}")
    if successful > 0:
        print(f"  📁 Output dir: {output_dir}")
        print(f"  💾 Summary: {summary_file_retry.name}")
    print(f"  📄 Format: Page-wise (matching Claude Opus)")
    print("="*80 + "\n")
    
    if successful > 0:
        print("💡 Tip: Merge successful retries back into 1_2_1 output for complete dataset")
    
    return retry_summary


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python 1_2_2_retry_failed.py <loan_id>")
        print("\nExample:")
        print("  python 1_2_2_retry_failed.py loan_1642451")
        print("\nPrerequisites:")
        print("  1. 1_2_1 must be complete (extraction_summary.json must exist)")
        print("  2. Must have failed extractions to retry")
        print("\nOutput:")
        print("  Individual JSON files: backend/stage1/output/<loan_id>/1_2_2_retry_extractions/<filename>.json")
        print("  Summary file: backend/stage1/output/<loan_id>/1_2_2_retry_extractions/retry_summary.json")
        print("  Format: Page-wise JSON matching Claude Opus structure")
        sys.exit(1)
    
    loan_id = sys.argv[1]
    
    # Setup paths
    script_dir = Path(__file__).parent
    stage1_output_dir = script_dir / "output" / loan_id
    documents_dir = script_dir.parent.parent / "documents" / loan_id
    
    # Verify prerequisites
    if not stage1_output_dir.exists():
        print(f"❌ Error: 1_2_1 output not found for {loan_id}")
        print(f"   Expected: {stage1_output_dir}")
        print("   Run 1_2_1_deep_extract_llama.py first!")
        sys.exit(1)
    
    if not documents_dir.exists():
        print(f"❌ Error: Documents folder not found: {documents_dir}")
        sys.exit(1)
    
    # Run retry
    summary = retry_failed_extractions(loan_id, stage1_output_dir, documents_dir)
    
    if summary:
        if summary['retry_successful'] > 0:
            print(f"✅ Successfully recovered {summary['retry_successful']} document(s)!")
            sys.exit(0)
        else:
            print("⚠️ No documents were successfully recovered in retry")
            sys.exit(1)
    else:
        # No failures to retry
        sys.exit(0)
