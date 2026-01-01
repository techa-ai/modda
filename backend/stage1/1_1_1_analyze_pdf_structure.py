#!/usr/bin/env python3
"""
Stage 1 - Step 1 Substep 1: Analyze PDF Structure
Determine which PDFs are text-based vs scanned, and detect table layouts in text PDFs.

For text-based PDFs, detect:
- Presence of tables
- Single table vs multiple tables per page
- Table complexity (helps decide if OCR is needed for better extraction)

Multi-table layout PDFs often need OCR for better extraction even if they're text-based.

Naming: 1_1_1 = Stage 1, Step 1, Substep 1
"""

import os
import sys
from pathlib import Path
import json
from datetime import datetime

# Core PDF libraries
import PyPDF2

# Table detection - install if needed: pip install pdfplumber
try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False
    print("⚠️  Warning: pdfplumber not available. Table detection will be limited.")
    print("   Install with: pip install pdfplumber")


def detect_tables_in_page(pdf_path, page_num):
    """
    Detect tables in a specific page using pdfplumber
    
    Args:
        pdf_path: Path to PDF file
        page_num: Page number (0-indexed)
        
    Returns:
        dict with table detection results
    """
    if not PDFPLUMBER_AVAILABLE:
        return {
            'has_tables': None,
            'table_count': None,
            'table_layout': 'unknown',
            'error': 'pdfplumber not available'
        }
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if page_num >= len(pdf.pages):
                return {
                    'has_tables': False,
                    'table_count': 0,
                    'table_layout': 'no_tables',
                    'error': None
                }
            
            page = pdf.pages[page_num]
            tables = page.find_tables()
            
            table_count = len(tables)
            
            # Determine layout
            if table_count == 0:
                layout = 'no_tables'
            elif table_count == 1:
                layout = 'single_table'
            else:
                layout = 'multi_table'
            
            # Get table details
            table_details = []
            for idx, table in enumerate(tables):
                table_info = {
                    'table_index': idx,
                    'row_count': len(table.rows) if hasattr(table, 'rows') else None,
                    'bbox': table.bbox if hasattr(table, 'bbox') else None
                }
                table_details.append(table_info)
            
            return {
                'has_tables': table_count > 0,
                'table_count': table_count,
                'table_layout': layout,
                'table_details': table_details,
                'error': None
            }
            
    except Exception as e:
        return {
            'has_tables': None,
            'table_count': None,
            'table_layout': 'error',
            'error': str(e)
        }


def analyze_pdf_structure(pdf_path, sample_pages=3, min_text_threshold=50):
    """
    Comprehensive PDF structure analysis
    
    Args:
        pdf_path: Path to the PDF file
        sample_pages: Number of pages to sample for analysis (default 3)
        min_text_threshold: Minimum characters to consider text-based
        
    Returns:
        dict with complete analysis results
    """
    result = {
        'filename': os.path.basename(pdf_path),
        'path': str(pdf_path),
        'file_size': os.path.getsize(pdf_path),
        'page_count': 0,
        'text_length': 0,
        'is_text_based': False,
        'pdf_type': 'scanned',
        'sample_pages_checked': 0,
        
        # Table detection results
        'has_tables': False,
        'table_analysis': {
            'pages_with_tables': 0,
            'pages_with_single_table': 0,
            'pages_with_multi_table': 0,
            'max_tables_per_page': 0,
            'total_tables_found': 0,
            'page_details': []
        },
        
        # Recommendation
        'needs_ocr': False,
        'ocr_reason': None,
        
        'error': None
    }
    
    try:
        # Step 1: Extract text with PyPDF2 to determine if text-based
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            result['page_count'] = len(reader.pages)
            
            # For very large PDFs, only sample first few pages
            pages_to_check = min(sample_pages, result['page_count'])
            result['sample_pages_checked'] = pages_to_check
            
            text_parts = []
            for i in range(pages_to_check):
                try:
                    text = reader.pages[i].extract_text()
                    if text:
                        text_parts.append(text)
                except Exception as e:
                    result['error'] = f"Error reading page {i}: {str(e)}"
            
            full_text = '\n'.join(text_parts)
            result['text_length'] = len(full_text)
            
            # Determine if text-based or scanned
            if len(full_text.strip()) >= min_text_threshold:
                result['is_text_based'] = True
                result['pdf_type'] = 'text'
            else:
                result['is_text_based'] = False
                result['pdf_type'] = 'scanned'
                result['needs_ocr'] = True
                result['ocr_reason'] = 'scanned_pdf'
        
        # Step 2: If text-based, analyze table structure
        if result['is_text_based'] and PDFPLUMBER_AVAILABLE:
            pages_with_tables = 0
            pages_with_single = 0
            pages_with_multi = 0
            max_tables = 0
            total_tables = 0
            
            for page_idx in range(pages_to_check):
                table_info = detect_tables_in_page(pdf_path, page_idx)
                
                page_detail = {
                    'page_num': page_idx + 1,
                    'has_tables': table_info['has_tables'],
                    'table_count': table_info['table_count'],
                    'table_layout': table_info['table_layout']
                }
                
                result['table_analysis']['page_details'].append(page_detail)
                
                if table_info['table_count'] and table_info['table_count'] > 0:
                    pages_with_tables += 1
                    total_tables += table_info['table_count']
                    
                    if table_info['table_count'] == 1:
                        pages_with_single += 1
                    elif table_info['table_count'] > 1:
                        pages_with_multi += 1
                    
                    max_tables = max(max_tables, table_info['table_count'])
            
            result['has_tables'] = pages_with_tables > 0
            result['table_analysis']['pages_with_tables'] = pages_with_tables
            result['table_analysis']['pages_with_single_table'] = pages_with_single
            result['table_analysis']['pages_with_multi_table'] = pages_with_multi
            result['table_analysis']['max_tables_per_page'] = max_tables
            result['table_analysis']['total_tables_found'] = total_tables
            
            # Recommendation: Any tables in text PDFs benefit from OCR for better extraction
            if pages_with_tables > 0:
                result['needs_ocr'] = True
                result['ocr_reason'] = 'has_tables'
            else:
                result['needs_ocr'] = False
                result['ocr_reason'] = 'no_tables'
                
    except Exception as e:
        result['error'] = f"Error processing PDF: {str(e)}"
    
    return result


def analyze_loan_documents(loan_folder, sample_pages=3):
    """
    Analyze all PDFs in a loan folder for structure and table layout
    
    Args:
        loan_folder: Path to loan folder containing PDFs
        sample_pages: Number of pages to sample per PDF
        
    Returns:
        dict with summary and detailed results
    """
    loan_path = Path(loan_folder)
    
    if not loan_path.exists():
        print(f"❌ Folder not found: {loan_folder}")
        return None
    
    # Find all PDF files
    pdf_files = sorted(loan_path.glob('*.pdf'))
    
    print(f"\n📁 Analyzing PDFs in: {loan_folder}")
    print(f"📄 Found {len(pdf_files)} PDF files")
    if PDFPLUMBER_AVAILABLE:
        print("✅ pdfplumber available - table detection enabled\n")
    else:
        print("⚠️  pdfplumber not available - table detection disabled\n")
    
    results = {
        'loan_folder': str(loan_folder),
        'analysis_timestamp': datetime.now().isoformat(),
        'total_pdfs': len(pdf_files),
        'text_based_count': 0,
        'scanned_count': 0,
        'error_count': 0,
        
        # Table statistics
        'text_pdfs_with_tables': 0,
        'text_pdfs_with_single_table': 0,
        'text_pdfs_with_multi_table': 0,
        'text_pdfs_no_tables': 0,
        
        # OCR recommendations
        'pdfs_need_ocr': 0,
        'pdfs_need_ocr_scanned': 0,
        'pdfs_need_ocr_with_tables': 0,
        
        # File lists
        'text_based_files': [],
        'scanned_files': [],
        'text_with_tables_files': [],
        'text_no_tables_files': [],
        'error_files': [],
        
        'details': []
    }
    
    # Analyze each PDF
    for idx, pdf_path in enumerate(pdf_files, 1):
        filename = pdf_path.name
        print(f"[{idx}/{len(pdf_files)}] {filename}...", end=' ')
        
        # Special handling for large files like tax_returns_65.pdf
        if 'tax_returns' in filename.lower() or pdf_path.stat().st_size > 50_000_000:
            print("(Large file - sampling 3 pages)", end=' ')
            analysis = analyze_pdf_structure(pdf_path, sample_pages=3)
        else:
            analysis = analyze_pdf_structure(pdf_path, sample_pages=sample_pages)
        
        results['details'].append(analysis)
        
        # Categorize
        if analysis['error']:
            results['error_count'] += 1
            results['error_files'].append(filename)
            print(f"❌ Error")
        elif analysis['is_text_based']:
            results['text_based_count'] += 1
            results['text_based_files'].append(filename)
            
            # Table analysis
            table_info = ""
            if analysis['has_tables']:
                results['text_pdfs_with_tables'] += 1
                results['text_with_tables_files'].append(filename)
                
                multi = analysis['table_analysis']['pages_with_multi_table']
                single = analysis['table_analysis']['pages_with_single_table']
                
                if multi > 0:
                    results['text_pdfs_with_multi_table'] += 1
                    table_info = f"📊 TABLES: {analysis['table_analysis']['total_tables_found']} ({multi} multi-table pages)"
                elif single > 0:
                    results['text_pdfs_with_single_table'] += 1
                    table_info = f"📋 TABLES: {analysis['table_analysis']['total_tables_found']} ({single} single-table pages)"
            else:
                results['text_pdfs_no_tables'] += 1
                results['text_no_tables_files'].append(filename)
                table_info = "📄 NO-TABLES"
            
            # OCR recommendation
            if analysis['needs_ocr']:
                results['pdfs_need_ocr'] += 1
                if analysis['ocr_reason'] == 'has_tables':
                    results['pdfs_need_ocr_with_tables'] += 1
                    print(f"✅ TEXT {table_info} → OCR")
                else:
                    print(f"✅ TEXT {table_info} → TEXT-ONLY")
            else:
                print(f"✅ TEXT {table_info} → TEXT-ONLY")
                
        else:
            results['scanned_count'] += 1
            results['scanned_files'].append(filename)
            results['pdfs_need_ocr'] += 1
            results['pdfs_need_ocr_scanned'] += 1
            print(f"🖼️  SCANNED → OCR")
    
    return results


def print_summary(results):
    """Print comprehensive analysis summary"""
    if not results:
        return
    
    print("\n" + "="*80)
    print("📊 PDF STRUCTURE ANALYSIS SUMMARY")
    print("="*80)
    
    print(f"\n📄 TOTAL PDFs: {results['total_pdfs']}")
    print(f"  ✅ Text-based: {results['text_based_count']} ({results['text_based_count']/results['total_pdfs']*100:.1f}%)")
    print(f"  🖼️  Scanned: {results['scanned_count']} ({results['scanned_count']/results['total_pdfs']*100:.1f}%)")
    print(f"  ❌ Errors: {results['error_count']}")
    
    if results['text_based_count'] > 0:
        print(f"\n📊 TABLE ANALYSIS (Text-based PDFs):")
        print(f"  📋 With tables: {results['text_pdfs_with_tables']}")
        print(f"     - Single table layout: {results['text_pdfs_with_single_table']}")
        print(f"     - Multi-table layout: {results['text_pdfs_with_multi_table']}")
        print(f"  📄 No tables: {results['text_pdfs_no_tables']}")
    
    print(f"\n🔍 EXTRACTION STRATEGY:")
    print(f"  📌 OCR Processing:      {results['pdfs_need_ocr']} ({results['pdfs_need_ocr']/results['total_pdfs']*100:.1f}%)")
    print(f"     - Scanned PDFs:      {results['pdfs_need_ocr_scanned']}")
    print(f"     - Text PDFs w/tables: {results['pdfs_need_ocr_with_tables']}")
    print(f"  📌 Text Extraction:     {results['total_pdfs'] - results['pdfs_need_ocr']} ({(results['total_pdfs'] - results['pdfs_need_ocr'])/results['total_pdfs']*100:.1f}%)")
    print(f"     - Text PDFs no tables: {results['text_pdfs_no_tables']}")
    
    if results['text_with_tables_files']:
        print(f"\n📊 TEXT PDFs WITH TABLES ({len(results['text_with_tables_files'])}) → OCR:")
        for f in sorted(results['text_with_tables_files']):
            print(f"   - {f}")
    
    if results['text_no_tables_files']:
        print(f"\n📄 TEXT PDFs WITHOUT TABLES ({len(results['text_no_tables_files'])}) → Text Extraction:")
        for f in sorted(results['text_no_tables_files']):
            print(f"   - {f}")
    
    if results['scanned_files']:
        print(f"\n🖼️  SCANNED PDFs ({len(results['scanned_files'])}) → OCR:")
        for f in sorted(results['scanned_files']):
            print(f"   - {f}")
    
    if results['error_files']:
        print(f"\n❌ ERROR PDFs ({len(results['error_files'])}):")
        for f in sorted(results['error_files']):
            print(f"   - {f}")
    
    print("\n" + "="*80)


def save_results(results, output_file):
    """Save results to JSON file"""
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\n💾 Detailed results saved to: {output_file}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python 1_1_1_analyze_pdf_structure.py <loan_folder> [sample_pages]")
        print("\nExample:")
        print("  python 1_1_1_analyze_pdf_structure.py /path/to/loan_1642451")
        print("  python 1_1_1_analyze_pdf_structure.py /path/to/loan_1642451 5")
        print("\nNote: Install pdfplumber for table detection: pip install pdfplumber")
        print("Output will be saved to: backend/stage1/output/<loan_id>/1_1_1_analysis.json")
        sys.exit(1)
    
    loan_folder = sys.argv[1]
    sample_pages = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    
    # Extract loan_id from folder path
    loan_path = Path(loan_folder)
    loan_id = loan_path.name  # e.g., loan_1642451
    
    # Create output directory
    script_dir = Path(__file__).parent
    output_dir = script_dir / "output" / loan_id
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Define output file
    output_file = output_dir / "1_1_1_analysis.json"
    
    # Run analysis
    results = analyze_loan_documents(loan_folder, sample_pages=sample_pages)
    
    if results:
        # Print summary
        print_summary(results)
        
        # Save results
        save_results(results, str(output_file))

