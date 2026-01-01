#!/usr/bin/env python3
"""
Concurrent Document Extraction Orchestrator
Runs multiple extraction tasks in parallel with rate limiting and retry logic

Handles:
- 1_2_1: Scanned PDFs
- 1_2_3: Text PDFs with tables  
- 1_2_4: Text PDFs without tables
- 1_2_5: Large files (80+ pages)

Features:
- Concurrent processing (up to 30 requests at a time)
- Rate limit handling with exponential backoff
- Progress tracking
- Error recovery
"""

import os
import sys
import json
import time
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Semaphore
import traceback

# Import shared extraction functions
from llama_pagewise_extractor import (
    LlamaClient,
    extract_document_pagewise
)


# Global rate limiter
MAX_CONCURRENT_REQUESTS = 30
rate_limiter = Semaphore(MAX_CONCURRENT_REQUESTS)


def extract_with_retry(pdf_path: str, filename: str, client: LlamaClient, pdf_type: str, dpi: int = 150, max_retries: int = 3):
    """Extract document with rate limit handling and retry logic"""
    
    for attempt in range(max_retries):
        try:
            with rate_limiter:
                result = extract_document_pagewise(str(pdf_path), filename, client, pdf_type=pdf_type, dpi=dpi)
                return result
                
        except Exception as e:
            error_msg = str(e)
            
            # Check for rate limit errors
            if "throttl" in error_msg.lower() or "rate" in error_msg.lower() or "limit" in error_msg.lower():
                wait_time = (2 ** attempt) * 5  # Exponential backoff: 5s, 10s, 20s
                print(f"  ⚠️  Rate limit hit for {filename}. Waiting {wait_time}s before retry {attempt+1}/{max_retries}...")
                time.sleep(wait_time)
                continue
            else:
                # Non-rate-limit error
                print(f"  ❌ Error extracting {filename}: {error_msg}")
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                else:
                    return {
                        'success': False,
                        'filename': filename,
                        'error': error_msg
                    }
    
    # All retries failed
    return {
        'success': False,
        'filename': filename,
        'error': f'Failed after {max_retries} retries'
    }


def process_single_document(file_info: dict, documents_dir: Path, output_dir: Path, pdf_type: str, dpi: int = 150):
    """Process a single document and save immediately"""
    
    # Create one client per thread
    client = LlamaClient()
    
    filename = file_info['filename']
    pdf_path = documents_dir / filename
    
    if not pdf_path.exists():
        return {
            'success': False,
            'filename': filename,
            'error': 'File not found'
        }
    
    print(f"  🔄 Processing: {filename}")
    result = extract_with_retry(pdf_path, filename, client, pdf_type, dpi=dpi)
    
    # Save immediately upon completion
    if result.get('success', False):
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"{Path(filename).stem}.json"
        with open(output_file, 'w') as f:
            json.dump(result['data'], f, indent=2)
        print(f"  💾 Saved: {output_file.name}")
    
    return result


def concurrent_extract(loan_id: str, file_groups: dict, documents_dir: Path, output_base_dir: Path, max_workers: int = 10):
    """Extract documents concurrently across all groups, saving as we go"""
    
    print("\n" + "="*80)
    print(f"🚀 CONCURRENT EXTRACTION - {loan_id}")
    print(f"Max concurrent workers: {max_workers}")
    print(f"Max concurrent API requests: {MAX_CONCURRENT_REQUESTS}")
    print("="*80)
    
    # Print summary of work
    total_files = sum(len(group['files']) for group in file_groups.values())
    print(f"\n📊 Total files to process: {total_files}")
    for group_name, group_info in file_groups.items():
        print(f"   {group_name}: {len(group_info['files'])} files")
    print()
    
    start_time = time.time()
    all_results = {group_name: [] for group_name in file_groups.keys()}
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_info = {}
        
        # Submit all individual files for concurrent processing
        for group_name, group_info in file_groups.items():
            files = group_info['files']
            pdf_type = group_info['pdf_type']
            dpi = group_info.get('dpi', 150)
            output_dir = output_base_dir / group_info['output_folder']
            
            for file_info in files:
                future = executor.submit(
                    process_single_document,
                    file_info,
                    documents_dir,
                    output_dir,
                    pdf_type,
                    dpi
                )
                future_to_info[future] = {
                    'group_name': group_name,
                    'filename': file_info['filename']
                }
        
        # Collect results as they complete (files saved immediately in worker)
        completed = 0
        for future in as_completed(future_to_info):
            info = future_to_info[future]
            group_name = info['group_name']
            filename = info['filename']
            
            try:
                result = future.result()
                all_results[group_name].append(result)
                completed += 1
                
                status = "✅" if result.get('success', False) else "❌"
                print(f"  [{completed}/{total_files}] {status} {filename}")
                
            except Exception as e:
                print(f"  [{completed}/{total_files}] ❌ Error {filename}: {e}")
                all_results[group_name].append({
                    'success': False,
                    'filename': filename,
                    'error': str(e)
                })
                completed += 1
    
    duration = time.time() - start_time
    
    # Save summaries for each group
    print("\n" + "="*80)
    print("📊 SAVING SUMMARIES")
    print("="*80)
    
    for group_name, results in all_results.items():
        group_info = file_groups[group_name]
        output_dir = output_base_dir / group_info['output_folder']
        
        successful = sum(1 for r in results if r.get('success', False))
        failed = len(results) - successful
        
        # Save summary
        summary = {
            'loan_id': loan_id,
            'extraction_timestamp': datetime.now().isoformat(),
            'group': group_name,
            'pdf_type': group_info['pdf_type'],
            'total_files': len(results),
            'successful': successful,
            'failed': failed,
            'duration_seconds': round(duration, 2),
            'results': results
        }
        
        summary_file = output_dir / "extraction_summary.json"
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)
        
        print(f"   📁 {group_name}: ✅ {successful} succeeded, ❌ {failed} failed")
    
    # Print final summary
    print("\n" + "="*80)
    print("📊 CONCURRENT EXTRACTION COMPLETE")
    print("="*80)
    print(f"  Total time: {duration/60:.1f} minutes")
    total_successful = sum(sum(1 for r in results if r.get('success', False)) for results in all_results.values())
    total_failed = total_files - total_successful
    print(f"  ✅ Total successful: {total_successful}/{total_files}")
    print(f"  ❌ Total failed: {total_failed}")
    print("="*80 + "\n")
    
    return all_results


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python concurrent_extractor.py <loan_id>")
        print("\nExample:")
        print("  python concurrent_extractor.py loan_1642451")
        sys.exit(1)
    
    loan_id = sys.argv[1]
    
    # Setup paths
    script_dir = Path(__file__).parent
    stage1_output_dir = script_dir / "output" / loan_id
    documents_dir = script_dir.parent.parent / "documents" / loan_id
    
    # Load categories
    categories_file = stage1_output_dir / "1_1_3_categories.json"
    with open(categories_file, 'r') as f:
        categories = json.load(f)
    
    # Prepare file groups
    file_groups = {
        '1_2_3_text_with_tables': {
            'files': [{'filename': f} for f in categories['categories']['text_pdfs_with_tables_ocr']['files'] if f != 'tax_returns_65.pdf'],
            'pdf_type': 'text_with_tables',
            'dpi': 150,
            'output_folder': '1_2_3_llama_extractions'
        },
        '1_2_4_text_no_tables': {
            'files': [{'filename': f} for f in categories['categories']['text_pdfs_no_tables_text_extraction']['files']],
            'pdf_type': 'text_no_tables',
            'dpi': 150,
            'output_folder': '1_2_4_llama_extractions'
        }
    }
    
    # Check for large files
    analysis_file = stage1_output_dir / "1_1_1_analysis.json"
    if analysis_file.exists():
        with open(analysis_file, 'r') as f:
            analysis = json.load(f)
        
        large_files = [
            {'filename': d['filename']} 
            for d in analysis['details'] 
            if d['page_count'] >= 80
        ]
        
        if large_files:
            file_groups['1_2_5_large_files'] = {
                'files': large_files,
                'pdf_type': 'large_file',
                'dpi': 100,
                'output_folder': '1_2_5_llama_extractions'
            }
    
    # Run concurrent extraction
    results = concurrent_extract(loan_id, file_groups, documents_dir, stage1_output_dir, max_workers=10)
    
    print("✅ All extractions complete!")

