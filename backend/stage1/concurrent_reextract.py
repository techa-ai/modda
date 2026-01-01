#!/usr/bin/env python3
"""
Concurrent re-extraction with enhanced metadata
Processes all categories (1_2_1, 1_2_3, 1_2_4) concurrently
Excludes tax_returns_65.pdf (2271 pages)
"""

import asyncio
import json
import sys
import time
import shutil
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# Import the extraction function
from llama_pagewise_extractor import LlamaClient, extract_document_pagewise

class ProgressTracker:
    """Track extraction progress across categories"""
    
    def __init__(self):
        self.stats = defaultdict(lambda: {'total': 0, 'completed': 0, 'failed': 0})
        self.lock = asyncio.Lock()
    
    async def increment_completed(self, category):
        async with self.lock:
            self.stats[category]['completed'] += 1
    
    async def increment_failed(self, category):
        async with self.lock:
            self.stats[category]['failed'] += 1
    
    def set_total(self, category, total):
        self.stats[category]['total'] = total
    
    def get_summary(self):
        return dict(self.stats)


async def extract_document_async(pdf_path: Path, filename: str, output_dir: Path, 
                                  category_name: str, progress: ProgressTracker, 
                                  semaphore: asyncio.Semaphore):
    """Extract a single document asynchronously"""
    
    async with semaphore:
        try:
            # Run the extraction (blocking, but limited by semaphore)
            loop = asyncio.get_event_loop()
            client = LlamaClient()
            
            result = await loop.run_in_executor(
                None,
                extract_document_pagewise,
                str(pdf_path),
                filename,
                client,
                "scanned",  # pdf_type
                150  # dpi
            )
            
            if result['success']:
                # Save immediately
                output_file = output_dir / f"{Path(filename).stem}.json"
                with open(output_file, 'w') as f:
                    json.dump(result['data'], f, indent=2)
                
                await progress.increment_completed(category_name)
                print(f"✅ [{category_name}] {filename} ({result['duration']:.1f}s)")
                return {'success': True, 'filename': filename, 'category': category_name}
            else:
                await progress.increment_failed(category_name)
                print(f"❌ [{category_name}] {filename}: {result.get('error', 'Unknown error')}")
                return {'success': False, 'filename': filename, 'category': category_name, 'error': result.get('error')}
                
        except Exception as e:
            await progress.increment_failed(category_name)
            print(f"❌ [{category_name}] {filename}: {str(e)}")
            return {'success': False, 'filename': filename, 'category': category_name, 'error': str(e)}


async def process_category(category_name: str, files: list, documents_dir: Path, 
                           output_dir: Path, progress: ProgressTracker, semaphore: asyncio.Semaphore):
    """Process all documents in a category concurrently"""
    
    # Filter out excluded files
    EXCLUDED = ['tax_returns_65.pdf']
    files_to_process = [f for f in files if f not in EXCLUDED]
    
    progress.set_total(category_name, len(files_to_process))
    
    print(f"\n📂 {category_name}: Processing {len(files_to_process)}/{len(files)} files")
    if len(files) > len(files_to_process):
        print(f"   ⏭️  Excluding: {', '.join(EXCLUDED)}")
    
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create all extraction tasks
    tasks = []
    for filename in files_to_process:
        pdf_path = documents_dir / filename
        if pdf_path.exists():
            task = extract_document_async(
                pdf_path, filename, output_dir, 
                category_name, progress, semaphore
            )
            tasks.append(task)
        else:
            print(f"⚠️  File not found: {filename}")
    
    # Run all tasks concurrently
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    return results


async def main_async(loan_id: str):
    """Main async extraction function"""
    
    script_dir = Path(__file__).parent
    output_base = script_dir / "output" / loan_id
    
    # Load categories
    categories_file = output_base / "1_1_3_categories.json"
    with open(categories_file, 'r') as f:
        data = json.load(f)
    
    categories_data = data['categories']
    documents_dir = Path(data['loan_folder'])
    
    # Backup existing extractions
    print("\n📦 Backing up existing extractions...")
    backup_dir = output_base / f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    backup_dir.mkdir(exist_ok=True)
    
    for extraction_dir in ['1_2_1_llama_extractions', '1_2_3_llama_extractions', '1_2_4_llama_extractions']:
        src = output_base / extraction_dir
        if src.exists():
            dst = backup_dir / extraction_dir
            shutil.copytree(src, dst)
            print(f"   ✓ Backed up {extraction_dir}")
    
    print(f"✅ Backup saved to: {backup_dir}")
    
    # Set up concurrent processing
    MAX_CONCURRENT = 30  # Rate limit
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    progress = ProgressTracker()
    
    print("\n" + "="*80)
    print(f"🚀 CONCURRENT RE-EXTRACTION - Max {MAX_CONCURRENT} parallel requests")
    print("="*80)
    
    start_time = time.time()
    
    # Process all categories concurrently
    category_tasks = []
    
    # 1_2_1: Scanned PDFs
    category_tasks.append(
        process_category(
            "1_2_1_scanned",
            categories_data['scanned_pdfs_ocr']['files'],
            documents_dir,
            output_base / "1_2_1_llama_extractions",
            progress,
            semaphore
        )
    )
    
    # 1_2_3: Text PDFs with tables
    category_tasks.append(
        process_category(
            "1_2_3_text_tables",
            categories_data['text_pdfs_with_tables_ocr']['files'],
            documents_dir,
            output_base / "1_2_3_llama_extractions",
            progress,
            semaphore
        )
    )
    
    # 1_2_4: Text PDFs without tables
    category_tasks.append(
        process_category(
            "1_2_4_text_no_tables",
            categories_data['text_pdfs_no_tables_text_extraction']['files'],
            documents_dir,
            output_base / "1_2_4_llama_extractions",
            progress,
            semaphore
        )
    )
    
    # Run all categories concurrently
    all_results = await asyncio.gather(*category_tasks)
    
    duration = time.time() - start_time
    
    # Print summary
    print("\n" + "="*80)
    print("✅ RE-EXTRACTION COMPLETE!")
    print("="*80)
    
    summary = progress.get_summary()
    total_completed = sum(s['completed'] for s in summary.values())
    total_failed = sum(s['failed'] for s in summary.values())
    total_docs = sum(s['total'] for s in summary.values())
    
    print(f"\n📊 Summary:")
    print(f"   Total documents: {total_docs}")
    print(f"   ✅ Successful: {total_completed}")
    print(f"   ❌ Failed: {total_failed}")
    print(f"   ⏱️  Duration: {duration/60:.1f} minutes")
    print(f"   ⚡ Avg: {duration/total_docs:.1f}s per document")
    
    print(f"\n📂 By category:")
    for cat_name, stats in summary.items():
        print(f"   {cat_name}: {stats['completed']}/{stats['total']} (failed: {stats['failed']})")
    
    print(f"\n💾 Output location: {output_base}")
    print(f"💾 Backup location: {backup_dir}")
    
    print("\n📊 Next steps:")
    print("  1. Verify new extractions have 'document_metadata' field")
    print("  2. Check perceptual_hashes are present")
    print("  3. Re-run semantic grouping: python3 1_3_1_semantic_grouping.py loan_1642451")
    print()


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 concurrent_reextract.py <loan_id>")
        sys.exit(1)
    
    loan_id = sys.argv[1]
    
    print("\n" + "="*80)
    print("🎯 CONCURRENT RE-EXTRACTION WITH ENHANCED METADATA")
    print("="*80)
    print("\n✨ New Features:")
    print("  • Visual fingerprint (layout, structure, branding)")
    print("  • Perceptual hashes (pHash, dHash, aHash, wHash)")
    print("  • Document status (signed/unsigned/partially_signed)")
    print("  • Document persons (all parties with signature status)")
    print("  • Document completeness analysis")
    print("  • Content fingerprint for deduplication")
    print("  • Document relationships and references")
    print("\n⚡ Concurrent processing up to 30 requests at a time")
    print()
    
    # Run async main
    asyncio.run(main_async(loan_id))


if __name__ == "__main__":
    main()



