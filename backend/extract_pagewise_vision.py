#!/usr/bin/env python3
"""
Pagewise extraction using Claude Haiku 4.5 VISION API.
Sends actual PDF page images (not OCR text) for accurate extraction.
Processes 30 pages concurrently for speed.
"""
import json
import os
import sys
import base64
import io
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from pdf2image import convert_from_path
import boto3
from bedrock_config import call_bedrock

def convert_page_to_image(pdf_path: str, page_num: int, dpi: int = 150) -> bytes:
    """Convert a single PDF page to JPEG bytes."""
    images = convert_from_path(
        pdf_path,
        first_page=page_num,
        last_page=page_num,
        dpi=dpi
    )
    if not images:
        raise ValueError(f"Could not convert page {page_num}")
    
    # Convert to JPEG bytes
    img_buffer = io.BytesIO()
    images[0].save(img_buffer, format='JPEG', quality=85)
    return img_buffer.getvalue()

def extract_page_vision(pdf_path: str, page_num: int, model: str = "claude-haiku-4-5", error_dir: str = None) -> Dict[str, Any]:
    """Extract data from a single PDF page using Claude vision API."""
    try:
        # Convert page to image
        img_bytes = convert_page_to_image(pdf_path, page_num)
        img_base64 = base64.b64encode(img_bytes).decode('utf-8')
        
        # Build vision prompt
        prompt = """Extract key information from this tax document page. Provide:

1. form_name: The tax form/schedule name (e.g., "Form 1040", "Schedule K-1", "W-2", "Form 7203")
2. form_type: Category (w2|k1|1040|1120s|state_return|schedule|worksheet|instruction|cover|other)
3. person_name: If a person's name appears, extract it (full name)
4. entity_name: If a business/entity name appears, extract it
5. attributes: List of ALL key fields with numerical values. Examples:
   W-2: [{"field":"Wages","value":158000},{"field":"Federal_tax_withheld","value":20400},{"field":"SS_wages","value":158000},{"field":"SS_tax","value":9796}]
   K-1: [{"field":"Ordinary_income","value":16277.42},{"field":"Distributions","value":400}]
   Form 7203: [{"field":"Stock_basis_beginning","value":10581},{"field":"Ordinary_income","value":2659},{"field":"Stock_basis_before_dist","value":13240},{"field":"Distributions","value":400},{"field":"Stock_basis_after_dist","value":12840},{"field":"Nondeductible_expenses","value":44},{"field":"Stock_basis_end","value":12796}]
6. year: Tax year if visible
7. note: ONE sentence summary (max 100 chars)

IMPORTANT:
- Extract ALL visible numerical values from filled-in fields
- Keep field names SHORT, use underscores (e.g., "Federal_tax" not "Federal income tax withheld")
- Values should be numbers only (no dollar signs, commas)
- If page is blank/illegible/instructions-only, set form_type="other" and attributes=[]
- Output STRICT JSON object

OUTPUT JSON:
"""
        
        # Call Bedrock with vision using existing helper
        response_text = call_bedrock(
            prompt=prompt,
            image_base64=img_base64,
            model=model,
            max_tokens=2000
        )
        
        # Parse JSON response
        try:
            result = json.loads(response_text)
            if isinstance(result, dict):
                result['page'] = page_num
                return result
        except:
            # Try to salvage
            text = response_text
            if '```json' in text:
                text = text.split('```json')[1].split('```')[0]
            elif '```' in text:
                text = text.split('```')[1].split('```')[0]
            try:
                result = json.loads(text.strip())
                if isinstance(result, dict):
                    result['page'] = page_num
                    return result
            except:
                pass
        
        # Save raw response for failed parse
        if error_dir:
            os.makedirs(error_dir, exist_ok=True)
            error_file = os.path.join(error_dir, f"page_{page_num:04d}.txt")
            with open(error_file, 'w', encoding='utf-8') as f:
                f.write(f"=== Page {page_num} - JSON Parse Error ===\n\n")
                f.write(response_text)
        
        # Fallback
        return {
            'page': page_num,
            'form_type': 'other',
            'form_name': 'unknown',
            'attributes': [],
            'note': 'Extraction failed - invalid JSON response',
            'error': 'JSON parse error',
            'raw_response_saved': bool(error_dir)
        }
        
    except Exception as e:
        # Save raw error for exceptions too
        if error_dir:
            os.makedirs(error_dir, exist_ok=True)
            error_file = os.path.join(error_dir, f"page_{page_num:04d}.txt")
            with open(error_file, 'w', encoding='utf-8') as f:
                f.write(f"=== Page {page_num} - Exception ===\n\n")
                f.write(f"Error: {str(e)}\n")
        
        return {
            'page': page_num,
            'form_type': 'other',
            'form_name': 'unknown',
            'attributes': [],
            'note': f'Extraction failed: {str(e)}',
            'error': str(e),
            'raw_response_saved': bool(error_dir)
        }

def main():
    import sys
    
    pdf_path = "/Users/sunny/Applications/bts/jpmorgan/mortgage/modda/documents/loan_1642451/tax_returns_65.pdf"
    output_path = "/Users/sunny/Applications/bts/jpmorgan/mortgage/modda/outputs/ocr/tax_returns_65/pagewise_extract_vision.json"
    error_dir = "/Users/sunny/Applications/bts/jpmorgan/mortgage/modda/outputs/ocr/tax_returns_65/error_responses"
    
    # Check if retry mode
    retry_errors_only = '--retry-errors' in sys.argv
    
    start_page = 1
    end_page = 2271
    concurrency = 30
    
    # Load existing results
    results = {}
    if os.path.exists(output_path):
        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                existing = json.load(f)
                if isinstance(existing, dict) and 'pages' in existing:
                    for p in existing['pages']:
                        results[p['page']] = p
        except Exception as e:
            print(f"⚠️  Could not load existing results: {e}")
    
    # Determine pages to process
    if retry_errors_only:
        # Only retry pages with errors
        error_pages = [p['page'] for p in results.values() if p.get('error')]
        pages_to_process = sorted(error_pages)
        print(f"🔄 RETRY MODE: Re-extracting {len(pages_to_process)} error pages")
        print(f"   Error responses will be saved to: {error_dir}")
    else:
        # Normal mode - resume from last completed
        if results:
            last_page = max(results.keys())
            resume_from = last_page + 1
            print(f"🔁 Resuming from page {resume_from} ({len(results)} pages already extracted)")
        else:
            resume_from = start_page
            print(f"🚀 Starting pagewise VISION extraction: pages {start_page}-{end_page}")
        
        pages_to_process = list(range(resume_from, end_page + 1))
    
    print(f"   Concurrency: {concurrency} pages simultaneously")
    print(f"   Model: claude-haiku-4-5 (vision)")
    print()
    
    total_to_process = len(pages_to_process)
    
    print(f"📄 Processing {total_to_process} pages with {concurrency} concurrent workers...")
    print()
    
    # Process pages concurrently
    completed_count = len(results)
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        # Submit all tasks (with error_dir for saving raw responses)
        future_to_page = {
            executor.submit(extract_page_vision, pdf_path, page_num, "claude-haiku-4-5", error_dir): page_num
            for page_num in pages_to_process
        }
        
        # Process completed tasks
        for future in as_completed(future_to_page):
            page_num = future_to_page[future]
            try:
                result = future.result()
                results[page_num] = result
                completed_count += 1
                
                # Progress indicator
                pct = (completed_count * 100) // end_page
                form_name = result.get('form_name', 'unknown')
                attrs_count = len(result.get('attributes', []))
                error_str = f" ⚠️ {result.get('error', '')[:30]}" if result.get('error') else ""
                print(f"✅ Page {page_num:4d} [{pct:3d}%]: {form_name[:40]:40s} ({attrs_count} attrs){error_str}")
                
                # Save incrementally every 30 pages
                if completed_count % 30 == 0:
                    pages_list = [results[p] for p in sorted(results.keys())]
                    output = {
                        'metadata': {
                            'total_pages': end_page,
                            'extracted_pages': len(pages_list),
                            'last_page': max(results.keys()),
                            'model': 'claude-haiku-4-5',
                            'method': 'vision'
                        },
                        'pages': pages_list
                    }
                    with open(output_path, 'w', encoding='utf-8') as f:
                        json.dump(output, f, indent=2, ensure_ascii=False)
                    print(f"💾 Saved checkpoint: {len(pages_list)} pages")
                    
            except Exception as e:
                print(f"❌ Page {page_num:4d}: {str(e)[:80]}")
    
    # Final save
    pages_list = [results[p] for p in sorted(results.keys())]
    output = {
        'metadata': {
            'total_pages': end_page,
            'extracted_pages': len(pages_list),
            'last_page': max(results.keys()) if results else 0,
            'model': 'claude-haiku-4-5',
            'method': 'vision',
            'concurrency': concurrency
        },
        'pages': pages_list
    }
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print()
    print(f"✅ Extraction complete: {len(pages_list)} pages")
    print(f"   Output: {output_path}")
    
    # Stats
    pages_with_attrs = [p for p in pages_list if p.get('attributes')]
    pages_with_errors = [p for p in pages_list if p.get('error')]
    print()
    print(f"📊 Stats:")
    print(f"   Pages with attributes: {len(pages_with_attrs)} / {len(pages_list)}")
    print(f"   Pages with errors: {len(pages_with_errors)}")

if __name__ == "__main__":
    main()

