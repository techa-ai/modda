#!/usr/bin/env python3
"""
Re-run deep JSON extractions with enhanced metadata
Excludes tax_returns_65.pdf (2271 pages)
"""

import json
import sys
from pathlib import Path

def main():
    loan_id = sys.argv[1] if len(sys.argv) > 1 else "loan_1642451"
    auto_proceed = len(sys.argv) > 2 and sys.argv[2] == '--yes'
    
    script_dir = Path(__file__).parent
    output_dir = script_dir / "output" / loan_id
    
    # Load categories
    categories_file = output_dir / "1_1_3_categories.json"
    with open(categories_file, 'r') as f:
        data = json.load(f)
    
    categories = data['categories']
    
    # Count files per category (excluding large file)
    print("\n" + "="*80)
    print(f"📊 RE-EXTRACTION PLAN FOR {loan_id}")
    print("="*80)
    print("\n🎯 Enhanced Metadata Features:")
    print("  ✅ Visual fingerprint (layout, structure, branding)")
    print("  ✅ Perceptual hashes (pHash, dHash, aHash, wHash)")
    print("  ✅ Document status (signed/unsigned/partially_signed)")
    print("  ✅ Document persons (all parties with signature status)")
    print("  ✅ Document completeness analysis")
    print("  ✅ Content fingerprint for deduplication")
    print("  ✅ Document relationships and references")
    print()
    
    total_to_extract = 0
    excluded_count = 0
    
    # 1_2_1: Scanned PDFs
    scanned_files = categories['scanned_pdfs_ocr']['files']
    scanned_filtered = [f for f in scanned_files if 'tax_returns_65' not in f]
    excluded_count += len(scanned_files) - len(scanned_filtered)
    
    print(f"📂 1_2_1: Scanned PDFs (OCR)")
    print(f"   Total files: {len(scanned_files)}")
    print(f"   Excluding: tax_returns_65.pdf (2271 pages)")
    print(f"   Will process: {len(scanned_filtered)} files")
    total_to_extract += len(scanned_filtered)
    
    # 1_2_3: Text PDFs with tables
    text_tables_files = categories['text_pdfs_with_tables_ocr']['files']
    print(f"\n📂 1_2_3: Text PDFs with Tables (OCR)")
    print(f"   Will process: {len(text_tables_files)} files")
    total_to_extract += len(text_tables_files)
    
    # 1_2_4: Text PDFs without tables
    text_no_tables_files = categories['text_pdfs_no_tables_text_extraction']['files']
    print(f"\n📂 1_2_4: Text PDFs without Tables")
    print(f"   Will process: {len(text_no_tables_files)} files")
    total_to_extract += len(text_no_tables_files)
    
    print("\n" + "="*80)
    print(f"📊 TOTAL TO EXTRACT: {total_to_extract} documents")
    print(f"⏱️  Estimated time: {total_to_extract * 1.5:.0f}-{total_to_extract * 3:.0f} minutes")
    print("="*80)
    
    print("\n⚠️  IMPORTANT:")
    print("  - Existing extractions will be backed up")
    print("  - New extractions will have enhanced metadata")
    print("  - tax_returns_65.pdf will be skipped (too large)")
    print()
    
    if not auto_proceed:
        response = input("Proceed with re-extraction? (yes/no): ").strip().lower()
        if response != 'yes':
            print("❌ Cancelled.")
            return
    else:
        print("🚀 Auto-proceeding with re-extraction...")
    
    print("\n🚀 Starting re-extraction...\n")
    
    # Backup existing extractions
    import shutil
    from datetime import datetime
    
    backup_dir = output_dir / f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    backup_dir.mkdir(exist_ok=True)
    
    print("📦 Backing up existing extractions...")
    for extraction_dir in ['1_2_1_llama_extractions', '1_2_3_llama_extractions', '1_2_4_llama_extractions']:
        src = output_dir / extraction_dir
        if src.exists():
            dst = backup_dir / extraction_dir
            shutil.copytree(src, dst)
            print(f"   ✓ Backed up {extraction_dir}")
    
    print(f"\n✅ Backup saved to: {backup_dir}")
    print("\n" + "="*80)
    print("🔄 RE-RUNNING EXTRACTION SCRIPTS")
    print("="*80)
    
    # Import and run extraction scripts
    import subprocess
    
    scripts = [
        ('1_2_1_deep_extract_llama.py', 'Scanned PDFs'),
        ('1_2_3_deep_extract_text_with_tables.py', 'Text PDFs with Tables'),
        ('1_2_4_deep_extract_text_no_tables.py', 'Text PDFs without Tables')
    ]
    
    for script_name, description in scripts:
        print(f"\n{'='*80}")
        print(f"📝 Running: {description} ({script_name})")
        print(f"{'='*80}")
        
        result = subprocess.run(
            ['python3', script_name, loan_id],
            cwd=script_dir
        )
        
        if result.returncode != 0:
            print(f"\n⚠️  Warning: {script_name} completed with errors")
        else:
            print(f"\n✅ {script_name} completed successfully")
    
    print("\n" + "="*80)
    print("✅ RE-EXTRACTION COMPLETE!")
    print("="*80)
    print(f"\n💾 Backup location: {backup_dir}")
    print(f"📂 New extractions: {output_dir}")
    print("\n📊 Next steps:")
    print("  1. Re-run semantic grouping: python3 1_3_1_semantic_grouping.py")
    print("  2. Compare old vs new metadata quality")
    print("  3. Test duplicate detection with perceptual hashes")
    print()

if __name__ == "__main__":
    main()

