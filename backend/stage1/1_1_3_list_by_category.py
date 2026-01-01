#!/usr/bin/env python3
"""
Stage 1 - Step 1 Substep 3: List PDFs by Category
Quick reference to see which files need which extraction method
Saves categorized file lists as JSON output

Naming: 1_1_3 = Stage 1, Step 1, Substep 3
"""

import sys
import json
from pathlib import Path

def list_by_category(json_file, save_output=True):
    """Load and list PDFs by extraction category"""
    
    with open(json_file, 'r') as f:
        data = json.load(f)
    
    # Group files by category
    categories = {
        'scanned': [],
        'text_with_tables': [],
        'text_no_tables': []
    }
    
    for detail in data['details']:
        filename = detail['filename']
        if not detail['is_text_based']:
            categories['scanned'].append(filename)
        elif detail['needs_ocr'] and detail['ocr_reason'] == 'has_tables':
            categories['text_with_tables'].append(filename)
        else:
            categories['text_no_tables'].append(filename)
    
    print("\n" + "="*80)
    print("📋 PDF FILES BY EXTRACTION STRATEGY")
    print("="*80)
    
    print(f"\n🖼️  SCANNED PDFs → OCR ({len(categories['scanned'])} files)")
    print("-" * 80)
    for i, f in enumerate(sorted(categories['scanned']), 1):
        print(f"  {i:2}. {f}")
    
    print(f"\n📊 TEXT PDFs WITH TABLES → OCR ({len(categories['text_with_tables'])} files)")
    print("-" * 80)
    for i, f in enumerate(sorted(categories['text_with_tables']), 1):
        print(f"  {i:2}. {f}")
    
    print(f"\n📄 TEXT PDFs WITHOUT TABLES → Text Extraction ({len(categories['text_no_tables'])} files)")
    print("-" * 80)
    for i, f in enumerate(sorted(categories['text_no_tables']), 1):
        print(f"  {i:2}. {f}")
    
    print("\n" + "="*80)
    print(f"Total: {len(categories['scanned']) + len(categories['text_with_tables']) + len(categories['text_no_tables'])} files")
    print("="*80 + "\n")
    
    # Prepare output data
    output_data = {
        'loan_folder': data['loan_folder'],
        'analysis_timestamp': data['analysis_timestamp'],
        'total_files': len(categories['scanned']) + len(categories['text_with_tables']) + len(categories['text_no_tables']),
        'categories': {
            'scanned_pdfs_ocr': {
                'count': len(categories['scanned']),
                'files': sorted(categories['scanned'])
            },
            'text_pdfs_with_tables_ocr': {
                'count': len(categories['text_with_tables']),
                'files': sorted(categories['text_with_tables'])
            },
            'text_pdfs_no_tables_text_extraction': {
                'count': len(categories['text_no_tables']),
                'files': sorted(categories['text_no_tables'])
            }
        },
        'extraction_summary': {
            'ocr_required': len(categories['scanned']) + len(categories['text_with_tables']),
            'text_extraction': len(categories['text_no_tables'])
        }
    }
    
    if save_output:
        return output_data
    return None


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python 1_1_3_list_by_category.py <loan_id>")
        print("\nExample:")
        print("  python 1_1_3_list_by_category.py loan_1642451")
        print("\nReads from: backend/stage1/output/<loan_id>/1_1_1_analysis.json")
        print("Saves to: backend/stage1/output/<loan_id>/1_1_3_categories.json")
        sys.exit(1)
    
    loan_id = sys.argv[1]
    
    # Setup paths
    script_dir = Path(__file__).parent
    input_file = script_dir / "output" / loan_id / "1_1_1_analysis.json"
    output_file = script_dir / "output" / loan_id / "1_1_3_categories.json"
    
    if not input_file.exists():
        print(f"❌ Error: Input file not found: {input_file}")
        print(f"   Run 1_1_1_analyze_pdf_structure.py first!")
        sys.exit(1)
    
    # Run categorization and get data
    category_data = list_by_category(str(input_file), save_output=True)
    
    # Save categories JSON
    if category_data:
        with open(output_file, 'w') as f:
            json.dump(category_data, f, indent=2)
        print(f"💾 Categories saved to: {output_file}\n")

