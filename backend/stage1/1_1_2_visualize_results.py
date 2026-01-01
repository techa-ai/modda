#!/usr/bin/env python3
"""
Stage 1 - Step 1 Substep 2: Visualize PDF Structure Analysis Results
Generate a detailed breakdown and statistics from the analysis JSON
Saves statistics as JSON output

Naming: 1_1_2 = Stage 1, Step 1, Substep 2
"""

import sys
import json
from pathlib import Path
from collections import Counter

def visualize_results(json_file, save_output=True):
    """Load and visualize analysis results"""
    
    with open(json_file, 'r') as f:
        data = json.load(f)
    
    print("\n" + "="*80)
    print("📊 PDF STRUCTURE ANALYSIS - DETAILED BREAKDOWN")
    print("="*80)
    
    # Basic stats
    print(f"\n📁 Loan Folder: {data['loan_folder']}")
    print(f"⏰ Analysis Time: {data['analysis_timestamp']}")
    print(f"📄 Total PDFs: {data['total_pdfs']}")
    
    # PDF Type Distribution
    print(f"\n{'='*80}")
    print("1️⃣  PDF TYPE DISTRIBUTION")
    print(f"{'='*80}")
    print(f"  ✅ Text-based: {data['text_based_count']:>3} ({data['text_based_count']/data['total_pdfs']*100:>5.1f}%)")
    print(f"  🖼️  Scanned:    {data['scanned_count']:>3} ({data['scanned_count']/data['total_pdfs']*100:>5.1f}%)")
    print(f"  ❌ Errors:     {data['error_count']:>3}")
    
    # Table Analysis
    if data['text_based_count'] > 0:
        print(f"\n{'='*80}")
        print("2️⃣  TABLE LAYOUT ANALYSIS (Text-based PDFs only)")
        print(f"{'='*80}")
        print(f"  📋 With Tables:      {data['text_pdfs_with_tables']:>3}")
        print(f"     • Single-table:   {data['text_pdfs_with_single_table']:>3} ({data['text_pdfs_with_single_table']/data['text_based_count']*100:>5.1f}%)")
        print(f"     • Multi-table:    {data['text_pdfs_with_multi_table']:>3} ({data['text_pdfs_with_multi_table']/data['text_based_count']*100:>5.1f}%)")
        print(f"  📄 No Tables:        {data['text_pdfs_no_tables']:>3} ({data['text_pdfs_no_tables']/data['text_based_count']*100:>5.1f}%)")
    
    # Extraction Strategy
    print(f"\n{'='*80}")
    print("3️⃣  EXTRACTION STRATEGY")
    print(f"{'='*80}")
    print(f"  📌 OCR Processing:        {data['pdfs_need_ocr']:>3} ({data['pdfs_need_ocr']/data['total_pdfs']*100:>5.1f}%)")
    print(f"     • Scanned PDFs:        {data['pdfs_need_ocr_scanned']:>3}")
    print(f"     • Text PDFs w/tables:  {data['pdfs_need_ocr_with_tables']:>3}")
    print(f"  📌 Text Extraction:       {data['total_pdfs'] - data['pdfs_need_ocr']:>3} ({(data['total_pdfs'] - data['pdfs_need_ocr'])/data['total_pdfs']*100:>5.1f}%)")
    print(f"     • Text PDFs no tables: {data['text_pdfs_no_tables']:>3}")
    print(f"  ✅ Simple text extraction:   {data['total_pdfs'] - data['pdfs_need_ocr']:>3} ({(data['total_pdfs'] - data['pdfs_need_ocr'])/data['total_pdfs']*100:>5.1f}%)")
    
    # Detailed breakdown by category
    print(f"\n{'='*80}")
    print("4️⃣  EXTRACTION STRATEGY BREAKDOWN")
    print(f"{'='*80}")
    
    # Analyze details
    details = data['details']
    
    # Group by extraction strategy
    strategies = {
        'scanned_ocr': [],
        'text_with_tables_ocr': [],
        'text_no_tables': []
    }
    
    for detail in details:
        filename = detail['filename']
        if not detail['is_text_based']:
            strategies['scanned_ocr'].append(filename)
        elif detail['needs_ocr'] and detail['ocr_reason'] == 'has_tables':
            strategies['text_with_tables_ocr'].append(filename)
        else:
            strategies['text_no_tables'].append(filename)
    
    print(f"\n  🖼️  SCANNED PDFs → OCR Required ({len(strategies['scanned_ocr'])} files)")
    print(f"      Image-based PDFs with no extractable text")
    
    print(f"\n  📊 TEXT PDFs WITH TABLES → OCR Required ({len(strategies['text_with_tables_ocr'])} files)")
    print(f"      Tables need OCR for proper structure and alignment")
    
    print(f"\n  📄 TEXT PDFs NO TABLES → Text Extraction ({len(strategies['text_no_tables'])} files)")
    print(f"      Plain text documents without tables")
    
    # File size analysis
    print(f"\n{'='*80}")
    print("5️⃣  FILE SIZE ANALYSIS")
    print(f"{'='*80}")
    
    file_sizes = [d['file_size'] for d in details]
    page_counts = [d['page_count'] for d in details]
    
    total_size = sum(file_sizes)
    avg_size = total_size / len(file_sizes)
    max_size = max(file_sizes)
    min_size = min(file_sizes)
    
    max_file = next(d for d in details if d['file_size'] == max_size)
    
    print(f"  Total Size:    {total_size / (1024*1024):>8.1f} MB")
    print(f"  Average Size:  {avg_size / 1024:>8.1f} KB")
    print(f"  Largest File:  {max_size / (1024*1024):>8.1f} MB - {max_file['filename']}")
    print(f"  Smallest File: {min_size / 1024:>8.1f} KB")
    
    # Page count analysis
    print(f"\n{'='*80}")
    print("6️⃣  PAGE COUNT ANALYSIS")
    print(f"{'='*80}")
    
    total_pages = sum(page_counts)
    avg_pages = total_pages / len(page_counts)
    max_pages = max(page_counts)
    
    max_page_file = next(d for d in details if d['page_count'] == max_pages)
    
    print(f"  Total Pages:   {total_pages:>6}")
    print(f"  Average Pages: {avg_pages:>6.1f}")
    print(f"  Largest Doc:   {max_pages:>6} pages - {max_page_file['filename']}")
    
    # Table statistics for text PDFs
    text_pdfs = [d for d in details if d['is_text_based']]
    if text_pdfs:
        print(f"\n{'='*80}")
        print("7️⃣  TABLE STATISTICS (Text-based PDFs)")
        print(f"{'='*80}")
        
        total_tables = sum(d['table_analysis']['total_tables_found'] for d in text_pdfs)
        pdfs_with_tables = [d for d in text_pdfs if d['has_tables']]
        
        if pdfs_with_tables:
            max_tables = max(d['table_analysis']['max_tables_per_page'] for d in pdfs_with_tables)
            max_table_file = next(d for d in pdfs_with_tables if d['table_analysis']['max_tables_per_page'] == max_tables)
            
            print(f"  Total Tables Found:     {total_tables:>6}")
            print(f"  Avg Tables per PDF:     {total_tables/len(pdfs_with_tables):>6.1f}")
            print(f"  Max Tables on One Page: {max_tables:>6} - {max_table_file['filename']}")
    
    # Processing time estimates
    print(f"\n{'='*80}")
    print("8️⃣  PROCESSING TIME ESTIMATES")
    print(f"{'='*80}")
    
    # Rough estimates based on typical processing times
    text_extraction_time = len(strategies['text_no_tables']) * 2  # 2 sec per doc
    ocr_time = (len(strategies['scanned_ocr']) + len(strategies['text_with_tables_ocr'])) * 30  # 30 sec per doc
    
    total_time = text_extraction_time + ocr_time
    
    print(f"  Text Extraction: {text_extraction_time:>6} seconds ({len(strategies['text_no_tables'])} docs × ~2s)")
    print(f"  OCR Processing:  {ocr_time:>6} seconds ({len(strategies['scanned_ocr']) + len(strategies['text_with_tables_ocr'])} docs × ~30s)")
    print(f"  Total Estimated: {total_time:>6} seconds (~{total_time/60:.1f} minutes)")
    
    print("\n" + "="*80)
    print("✅ Analysis complete!")
    print("="*80 + "\n")
    
    # Compile statistics for JSON export
    stats = {
        'loan_folder': data['loan_folder'],
        'analysis_timestamp': data['analysis_timestamp'],
        'summary': {
            'total_pdfs': data['total_pdfs'],
            'text_based_count': data['text_based_count'],
            'scanned_count': data['scanned_count'],
            'error_count': data['error_count']
        },
        'table_analysis': {
            'text_pdfs_with_tables': data['text_pdfs_with_tables'],
            'text_pdfs_with_single_table': data['text_pdfs_with_single_table'],
            'text_pdfs_with_multi_table': data['text_pdfs_with_multi_table'],
            'text_pdfs_no_tables': data['text_pdfs_no_tables']
        },
        'extraction_strategy': {
            'pdfs_need_ocr': data['pdfs_need_ocr'],
            'pdfs_need_ocr_scanned': data['pdfs_need_ocr_scanned'],
            'pdfs_need_ocr_with_tables': data['pdfs_need_ocr_with_tables'],
            'pdfs_text_extraction': data['total_pdfs'] - data['pdfs_need_ocr']
        },
        'file_size_analysis': {
            'total_size_mb': round(sum(d['file_size'] for d in details) / (1024*1024), 2),
            'average_size_kb': round(sum(d['file_size'] for d in details) / len(details) / 1024, 2),
            'largest_file': {
                'filename': max(details, key=lambda d: d['file_size'])['filename'],
                'size_mb': round(max(d['file_size'] for d in details) / (1024*1024), 2)
            },
            'smallest_file': {
                'filename': min(details, key=lambda d: d['file_size'])['filename'],
                'size_kb': round(min(d['file_size'] for d in details) / 1024, 2)
            }
        },
        'page_count_analysis': {
            'total_pages': sum(d['page_count'] for d in details),
            'average_pages': round(sum(d['page_count'] for d in details) / len(details), 1),
            'largest_doc': {
                'filename': max(details, key=lambda d: d['page_count'])['filename'],
                'pages': max(d['page_count'] for d in details)
            }
        },
        'table_statistics': {},
        'processing_estimates': {
            'text_extraction_seconds': text_extraction_time,
            'ocr_processing_seconds': ocr_time,
            'total_seconds': total_time,
            'total_minutes': round(total_time/60, 1)
        },
        'file_categories': strategies
    }
    
    # Add table statistics
    text_pdfs = [d for d in details if d['is_text_based']]
    if text_pdfs:
        total_tables = sum(d['table_analysis']['total_tables_found'] for d in text_pdfs)
        pdfs_with_tables = [d for d in text_pdfs if d['has_tables']]
        
        if pdfs_with_tables:
            max_tables = max(d['table_analysis']['max_tables_per_page'] for d in pdfs_with_tables)
            max_table_file = next(d for d in pdfs_with_tables if d['table_analysis']['max_tables_per_page'] == max_tables)
            
            stats['table_statistics'] = {
                'total_tables_found': total_tables,
                'avg_tables_per_pdf': round(total_tables/len(pdfs_with_tables), 1),
                'max_tables_on_one_page': {
                    'count': max_tables,
                    'filename': max_table_file['filename']
                }
            }
    
    # Save if requested
    if save_output:
        return stats
    return None


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python 1_1_2_visualize_results.py <loan_id>")
        print("\nExample:")
        print("  python 1_1_2_visualize_results.py loan_1642451")
        print("\nReads from: backend/stage1/output/<loan_id>/1_1_1_analysis.json")
        print("Saves to: backend/stage1/output/<loan_id>/1_1_2_statistics.json")
        sys.exit(1)
    
    loan_id = sys.argv[1]
    
    # Setup paths
    script_dir = Path(__file__).parent
    input_file = script_dir / "output" / loan_id / "1_1_1_analysis.json"
    output_file = script_dir / "output" / loan_id / "1_1_2_statistics.json"
    
    if not input_file.exists():
        print(f"❌ Error: Input file not found: {input_file}")
        print(f"   Run 1_1_1_analyze_pdf_structure.py first!")
        sys.exit(1)
    
    # Run visualization and get statistics
    stats = visualize_results(str(input_file), save_output=True)
    
    # Save statistics JSON
    if stats:
        with open(output_file, 'w') as f:
            json.dump(stats, f, indent=2)
        print(f"💾 Statistics saved to: {output_file}\n")

