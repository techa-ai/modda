#!/usr/bin/env python3
"""
Quick OCR-based extraction for Llama comparison
Since Llama vision API format is unclear, use OCR text instead
"""

import sys
from pdf2image import convert_from_path
import pytesseract
from pathlib import Path

def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract text from PDF using OCR"""
    
    print(f"  📄 Converting PDF to images...")
    images = convert_from_path(pdf_path, dpi=300)
    
    print(f"  🔍 Running OCR on {len(images)} page(s)...")
    all_text = []
    
    for i, img in enumerate(images, 1):
        print(f"    Page {i}...")
        text = pytesseract.image_to_string(img)
        all_text.append(f"=== PAGE {i} ===\n{text}")
    
    combined_text = "\n\n".join(all_text)
    print(f"  ✓ Extracted {len(combined_text)} characters")
    
    return combined_text

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 extract_with_ocr.py <pdf_path>")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    text = extract_text_from_pdf(pdf_path)
    
    # Save to file
    output_path = Path(pdf_path).stem + "_ocr.txt"
    with open(output_path, 'w') as f:
        f.write(text)
    
    print(f"\n✓ Saved to: {output_path}")

