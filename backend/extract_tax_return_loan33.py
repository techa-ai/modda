#!/usr/bin/env python3
"""
Quick extraction of tax_returns_204.pdf for Loan 33 to find Schedule D (Capital Gains)
"""
import json
import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from extract_pagewise_vision import extract_page_vision, process_document
from db import execute_one

def main():
    loan_id = 33
    filename = "tax_returns_204.pdf"
    
    print(f"\n{'='*80}")
    print(f"EXTRACTING {filename} for Loan {loan_id}")
    print(f"{'='*80}\n")
    
    # Get document path
    doc = execute_one(
        "SELECT file_path FROM document_analysis WHERE loan_id = %s AND filename = %s",
        (loan_id, filename)
    )
    
    if not doc or not doc['file_path']:
        print(f"❌ Document not found in database")
        sys.exit(1)
    
    pdf_path = doc['file_path']
    
    if not os.path.exists(pdf_path):
        print(f"❌ File not found: {pdf_path}")
        sys.exit(1)
    
    print(f"📁 PDF: {pdf_path}")
    
    # Output paths
    base_name = filename.replace('.pdf', '')
    output_dir = f"/Users/sunny/Applications/bts/jpmorgan/mortgage/modda/outputs/ocr/{base_name}"
    os.makedirs(output_dir, exist_ok=True)
    
    output_path = os.path.join(output_dir, "pagewise_extraction.json")
    
    print(f"📂 Output: {output_path}\n")
    
    # Process the document
    process_document(
        pdf_path=pdf_path,
        output_path=output_path,
        start_page=1,
        end_page=None,  # Process all pages
        concurrency=20,
        model="claude-haiku-4-5"
    )
    
    print(f"\n✅ Extraction complete!")
    print(f"   JSON saved to: {output_path}")
    print(f"\n📊 Now re-run income verification for Loan 33 to use this data")

if __name__ == "__main__":
    main()

