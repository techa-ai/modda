#!/usr/bin/env python3
"""
Stage 1 - Step 2 Substep 3: Deep JSON Extraction for Text PDFs with Tables
Extract deep JSON from text-based PDFs that have tables using Llama 4 Maverick

Uses Llama 4 Maverick 17B Instruct for document analysis
Processes all text PDFs with tables (both single and multi-table layouts)
Saves individual JSON outputs per document in PAGE-WISE format

Naming: 1_2_3 = Stage 1, Step 2, Substep 3
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


def process_loan_text_with_tables(loan_id: str, stage1_output_dir: Path, documents_dir: Path):
    """Process all text PDFs with tables for a loan"""
    
    print("\n" + "="*80)
    print(f"🚀 STAGE 1 STEP 2.3: Deep JSON Extraction (Page-wise) - Text PDFs with Tables - {loan_id}")
    print(f"Model: Llama 4 Maverick 17B Instruct")
    print(f"Format: Page-wise (matching Claude Opus)")
    print("="*80)
    
    # Load categories from Stage 1 Step 1 Substep 3
    categories_file = stage1_output_dir / "1_1_3_categories.json"
    if not categories_file.exists():
        print(f"❌ Error: Stage 1 Step 1.3 output not found: {categories_file}")
        print("   Run 1_1_3_list_by_category.py first!")
        return None
    
    with open(categories_file, 'r') as f:
        categories = json.load(f)
    
    # Get text PDFs with tables list
    text_with_tables_files = categories['categories']['text_pdfs_with_tables_ocr']['files']
    
    # Exclude large files
    EXCLUDED_FILES = ['tax_returns_65.pdf']
    files_to_process = [f for f in text_with_tables_files if f not in EXCLUDED_FILES]
    
    print(f"\n📄 Found {len(text_with_tables_files)} text PDFs with tables")
    if EXCLUDED_FILES:
        print(f"   Excluding: {EXCLUDED_FILES}")
    print(f"   Processing: {len(files_to_process)} PDFs\n")
    
    # Create output directory
    script_dir = Path(__file__).parent
    output_dir = script_dir / "output" / loan_id / "1_2_3_llama_extractions"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize Llama client
    client = LlamaClient()
    
    # Process each PDF
    results = []
    successful = 0
    failed = 0
    
    for idx, filename in enumerate(files_to_process, 1):
        print(f"\n[{idx}/{len(files_to_process)}] {filename}")
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
        
        # Extract deep JSON in page-wise format
        result = extract_document_pagewise(str(pdf_path), filename, client, pdf_type="text_with_tables", dpi=150)
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
        
        # Small delay between documents
        time.sleep(1)
    
    # Save summary
    summary = {
        'loan_id': loan_id,
        'extraction_timestamp': datetime.now().isoformat(),
        'model': 'llama-4-maverick-17b',
        'extraction_format': 'page_wise',
        'pdf_type': 'text_with_tables',
        'total_files': len(files_to_process),
        'successful': successful,
        'failed': failed,
        'excluded_files': EXCLUDED_FILES,
        'results': results
    }
    
    summary_file = output_dir / "extraction_summary.json"
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)
    
    # Print final summary
    print("\n" + "="*80)
    print("📊 EXTRACTION SUMMARY")
    print("="*80)
    print(f"  Total files: {len(files_to_process)}")
    print(f"  ✅ Successful: {successful}")
    print(f"  ❌ Failed: {failed}")
    print(f"  📁 Output dir: {output_dir}")
    print(f"  💾 Summary: {summary_file.name}")
    print(f"  📄 Format: Page-wise (matching Claude Opus)")
    print("="*80 + "\n")
    
    return summary


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python 1_2_3_deep_extract_text_with_tables.py <loan_id>")
        print("\nExample:")
        print("  python 1_2_3_deep_extract_text_with_tables.py loan_1642451")
        print("\nPrerequisites:")
        print("  1. Stage 1 Step 1 must be complete (1_1_3_categories.json must exist)")
        print("  2. Documents must be in /path/to/documents/<loan_id>/")
        print("\nOutput:")
        print("  Individual JSON files: backend/stage1/output/<loan_id>/1_2_3_llama_extractions/<filename>.json")
        print("  Summary file: backend/stage1/output/<loan_id>/1_2_3_llama_extractions/extraction_summary.json")
        print("  Format: Page-wise JSON matching Claude Opus structure")
        sys.exit(1)
    
    loan_id = sys.argv[1]
    
    # Setup paths
    script_dir = Path(__file__).parent
    stage1_output_dir = script_dir / "output" / loan_id
    documents_dir = script_dir.parent.parent / "documents" / loan_id
    
    # Verify prerequisites
    if not stage1_output_dir.exists():
        print(f"❌ Error: Stage 1 output not found for {loan_id}")
        print(f"   Expected: {stage1_output_dir}")
        print("   Run Stage 1 first!")
        sys.exit(1)
    
    if not documents_dir.exists():
        print(f"❌ Error: Documents folder not found: {documents_dir}")
        sys.exit(1)
    
    # Run extraction
    summary = process_loan_text_with_tables(loan_id, stage1_output_dir, documents_dir)
    
    if summary and summary['successful'] > 0:
        print("✅ Extraction complete!")
        sys.exit(0)
    else:
        print("⚠️ No files were successfully processed")
        sys.exit(1)
