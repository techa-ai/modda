#!/usr/bin/env python3
"""
Stage 1 - Step 2 Substep 5: Deep JSON Extraction for Large Files (80+ pages)
Extract deep JSON from large PDFs using Llama 4 Maverick with special handling

Handles large files like tax_returns_65.pdf with optimized batch processing
Saves individual JSON outputs per document in PAGE-WISE format

Naming: 1_2_5 = Stage 1, Step 2, Substep 5
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


def get_large_files(stage1_output_dir: Path, documents_dir: Path, page_threshold: int = 80):
    """Identify files with more than specified pages"""
    
    analysis_file = stage1_output_dir / "1_1_1_analysis.json"
    if not analysis_file.exists():
        return []
    
    with open(analysis_file, 'r') as f:
        analysis = json.load(f)
    
    large_files = []
    for detail in analysis['details']:
        if detail['page_count'] >= page_threshold:
            large_files.append({
                'filename': detail['filename'],
                'page_count': detail['page_count'],
                'pdf_type': detail['pdf_type']
            })
    
    return large_files


def process_large_files(loan_id: str, stage1_output_dir: Path, documents_dir: Path):
    """Process large PDF files for a loan"""
    
    print("\n" + "="*80)
    print(f"🚀 STAGE 1 STEP 2.5: Deep JSON Extraction - Large Files (80+ pages) - {loan_id}")
    print(f"Model: Llama 4 Maverick 17B Instruct")
    print(f"Format: Page-wise (matching Claude Opus)")
    print("="*80)
    
    # Get large files
    large_files = get_large_files(stage1_output_dir, documents_dir, page_threshold=80)
    
    if not large_files:
        print("\n✅ No large files (80+ pages) found to process")
        return None
    
    print(f"\n📄 Found {len(large_files)} large file(s):")
    for f in large_files:
        print(f"   - {f['filename']} ({f['page_count']} pages, {f['pdf_type']})")
    print()
    
    # Create output directory
    script_dir = Path(__file__).parent
    output_dir = script_dir / "output" / loan_id / "1_2_5_llama_extractions"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize Llama client
    client = LlamaClient()
    
    # Process each large PDF with lower DPI to reduce size
    results = []
    successful = 0
    failed = 0
    
    for idx, file_info in enumerate(large_files, 1):
        filename = file_info['filename']
        print(f"\n[{idx}/{len(large_files)}] {filename} ({file_info['page_count']} pages)")
        print("-" * 80)
        
        # Get full path to PDF
        pdf_path = documents_dir / filename
        
        if not pdf_path.exists():
            print(f"  ⚠️ Warning: PDF not found: {pdf_path}")
            results.append({
                'success': False,
                'filename': filename,
                'error': 'File not found'
            })
            failed += 1
            continue
        
        # Extract with lower DPI for large files (100 instead of 150)
        print(f"  ⚙️  Using lower DPI (100) for large file optimization")
        result = extract_document_pagewise(str(pdf_path), filename, client, pdf_type="large_file", dpi=100)
        results.append(result)
        
        # Save individual JSON file
        if result['success']:
            output_file = output_dir / f"{Path(filename).stem}.json"
            with open(output_file, 'w') as f:
                json.dump(result['data'], f, indent=2)
            print(f"  💾 Saved: {output_file.name}")
            successful += 1
        else:
            failed += 1
        
        # Longer delay for large files
        time.sleep(2)
    
    # Save summary
    summary = {
        'loan_id': loan_id,
        'extraction_timestamp': datetime.now().isoformat(),
        'model': 'llama-4-maverick-17b',
        'extraction_format': 'page_wise',
        'pdf_type': 'large_files_80plus_pages',
        'page_threshold': 80,
        'total_files': len(large_files),
        'successful': successful,
        'failed': failed,
        'results': results
    }
    
    summary_file = output_dir / "extraction_summary.json"
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)
    
    # Print final summary
    print("\n" + "="*80)
    print("📊 EXTRACTION SUMMARY")
    print("="*80)
    print(f"  Total files: {len(large_files)}")
    print(f"  ✅ Successful: {successful}")
    print(f"  ❌ Failed: {failed}")
    print(f"  📁 Output dir: {output_dir}")
    print(f"  💾 Summary: {summary_file.name}")
    print(f"  📄 Format: Page-wise (matching Claude Opus)")
    print("="*80 + "\n")
    
    return summary


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python 1_2_5_deep_extract_large_files.py <loan_id>")
        print("\nExample:")
        print("  python 1_2_5_deep_extract_large_files.py loan_1642451")
        print("\nPrerequisites:")
        print("  1. Stage 1 Step 1 must be complete (1_1_1_analysis.json must exist)")
        print("  2. Documents must be in /path/to/documents/<loan_id>/")
        print("\nOutput:")
        print("  Individual JSON files: backend/stage1/output/<loan_id>/1_2_5_llama_extractions/<filename>.json")
        print("  Summary file: backend/stage1/output/<loan_id>/1_2_5_llama_extractions/extraction_summary.json")
        sys.exit(1)
    
    loan_id = sys.argv[1]
    
    # Setup paths
    script_dir = Path(__file__).parent
    stage1_output_dir = script_dir / "output" / loan_id
    documents_dir = script_dir.parent.parent / "documents" / loan_id
    
    # Verify prerequisites
    if not stage1_output_dir.exists():
        print(f"❌ Error: Stage 1 output not found for {loan_id}")
        sys.exit(1)
    
    if not documents_dir.exists():
        print(f"❌ Error: Documents folder not found: {documents_dir}")
        sys.exit(1)
    
    # Run extraction
    summary = process_large_files(loan_id, stage1_output_dir, documents_dir)
    
    if summary and summary['successful'] > 0:
        print("✅ Extraction complete!")
        sys.exit(0)
    elif summary is None:
        print("ℹ️  No large files to process")
        sys.exit(0)
    else:
        print("⚠️ No files were successfully processed")
        sys.exit(1)



