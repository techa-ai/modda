#!/usr/bin/env python3
"""
PROPER Deep JSON Extraction for tax_returns_204.pdf (Loan 33)
- Uses Claude Opus 4.5
- High concurrency batch processing
- Full page-by-page extraction
- Saves to individual_analysis format
"""
import json
import os
import sys
import base64
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed
from pdf2image import convert_from_path
from PyPDF2 import PdfReader

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from db import execute_one, get_db_connection
from bedrock_config import call_bedrock

MODEL = "claude-opus-4-5"
CONCURRENCY = 15  # Process 15 pages in parallel

def convert_page_to_base64(pdf_path, page_num, dpi=150):
    """Convert a single PDF page to base64 JPEG"""
    images = convert_from_path(pdf_path, first_page=page_num, last_page=page_num, dpi=dpi)
    if not images:
        return None
    
    buffered = BytesIO()
    images[0].save(buffered, format="JPEG", quality=85)
    return base64.b64encode(buffered.getvalue()).decode('utf-8')

def extract_page_deep(pdf_path, page_num):
    """Deep extract a single page with Claude Opus 4.5"""
    print(f"  📄 Processing page {page_num}...")
    
    try:
        img_base64 = convert_page_to_base64(pdf_path, page_num)
        if not img_base64:
            return {"page": page_num, "error": "Could not convert page"}
        
        prompt = """You are analyzing a tax return document page. Extract ALL financial information in detail.

For EVERY page, provide:

1. **form_identification**:
   - form_name: Exact form/schedule name (e.g., "Form 1040", "Schedule D", "Schedule K-1", "W-2")
   - form_type: category (1040|schedule_d|schedule_e|k1|w2|1120s|1099|state_return|worksheet|cover|other)
   - tax_year: Tax year if visible

2. **entities**: List all people and businesses mentioned
   - person_name: Full name if present
   - entity_name: Business/entity name if present
   - ssn: SSN/EIN if visible (last 4 digits only)

3. **tables**: Extract ALL tables with headers and rows
   Example:
   [
     {
       "table_name": "Capital Gains and Losses",
       "headers": ["Description", "Date Acquired", "Date Sold", "Proceeds", "Cost Basis", "Gain/Loss"],
       "rows": [
         {"Description": "ABC Stock", "Date_Acquired": "01/15/2023", "Date_Sold": "06/30/2024", "Proceeds": 15000, "Cost_Basis": 12000, "Gain_Loss": 3000}
       ]
     }
   ]

4. **line_items**: ALL filled-in fields with labels and values
   Example:
   [
     {"line": "1", "label": "Short-term capital gain", "value": 3000, "note": "From Schedule D Part I"},
     {"line": "2", "label": "Long-term capital gain", "value": 0}
   ]

5. **key_amounts**: List ALL significant dollar amounts found
   [
     {"field": "Total_Capital_Gain", "amount": 3000, "location": "Line 21"},
     {"field": "Net_Income", "amount": 133981, "location": "Line 7"}
   ]

6. **summary**: One paragraph describing what's on this page

CRITICAL:
- Extract EVERY number, table, and field
- For Schedule D: capture ALL capital gains/losses with dates and amounts
- For income pages: capture ALL income sources
- If blank page: set form_type="other" and summary="Blank page"

Return STRICT JSON."""

        response = call_bedrock(
            prompt=prompt,
            image_base64=img_base64,
            model=MODEL,
            max_tokens=4000,
            temperature=0
        )
        
        # Parse response
        try:
            data = json.loads(response)
            data['page'] = page_num
            print(f"  ✅ Page {page_num} complete")
            return data
        except:
            # Try to extract JSON from markdown
            if '```json' in response:
                json_str = response.split('```json')[1].split('```')[0].strip()
                data = json.loads(json_str)
                data['page'] = page_num
                print(f"  ✅ Page {page_num} complete")
                return data
            else:
                print(f"  ⚠️  Page {page_num}: Could not parse JSON")
                return {"page": page_num, "error": "JSON parse error", "raw_response": response[:500]}
                
    except Exception as e:
        print(f"  ❌ Page {page_num}: {str(e)[:100]}")
        return {"page": page_num, "error": str(e)}

def main():
    loan_id = 33
    filename = "tax_returns_204.pdf"
    
    print(f"\n{'='*80}")
    print(f"DEEP JSON EXTRACTION - {filename} (Loan {loan_id})")
    print(f"Model: {MODEL}")
    print(f"Concurrency: {CONCURRENCY} pages in parallel")
    print(f"{'='*80}\n")
    
    # Get document
    doc = execute_one(
        "SELECT file_path FROM document_analysis WHERE loan_id = %s AND filename = %s",
        (loan_id, filename)
    )
    
    if not doc or not doc['file_path']:
        print(f"❌ Document not found")
        sys.exit(1)
    
    pdf_path = doc['file_path']
    if not os.path.exists(pdf_path):
        print(f"❌ File not found: {pdf_path}")
        sys.exit(1)
    
    # Get page count
    reader = PdfReader(pdf_path)
    total_pages = len(reader.pages)
    
    print(f"📁 PDF: {pdf_path}")
    print(f"📄 Pages: {total_pages}\n")
    print(f"⏱️  Estimated time: {(total_pages / CONCURRENCY) * 15:.1f} minutes\n")
    
    # Process pages in parallel
    print(f"🚀 Starting extraction...\n")
    
    pages_data = {}
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
        futures = {
            executor.submit(extract_page_deep, pdf_path, page_num): page_num 
            for page_num in range(1, total_pages + 1)
        }
        
        for future in as_completed(futures):
            result = future.result()
            if result:
                pages_data[result['page']] = result
    
    # Sort pages and create output
    sorted_pages = [pages_data[p] for p in sorted(pages_data.keys())]
    
    output = {
        "model": MODEL,
        "filename": filename,
        "total_pages": total_pages,
        "processing_date": "2025-12-16",
        "pages": sorted_pages,
        "document_summary": {
            "document_type": "Tax Returns",
            "category": "Income Documentation",
            "key_contents": [f"Page {p['page']}: {p.get('summary', 'N/A')[:100]}" for p in sorted_pages[:10]]
        }
    }
    
    # Save to outputs/ocr/{filename}/pagewise_extraction.json
    base_name = filename.replace('.pdf', '')
    output_dir = f"/Users/sunny/Applications/bts/jpmorgan/mortgage/modda/outputs/ocr/{base_name}"
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "pagewise_extraction.json")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f"\n{'='*80}")
    print(f"✅ EXTRACTION COMPLETE")
    print(f"{'='*80}")
    print(f"📊 Processed: {len(sorted_pages)} / {total_pages} pages")
    print(f"📁 Output: {output_path}")
    
    # Update database
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE document_analysis 
            SET individual_analysis = %s,
                analyzed_at = CURRENT_TIMESTAMP
            WHERE loan_id = %s AND filename = %s
        """, (json.dumps(output), loan_id, filename))
        conn.commit()
        print(f"💾 Updated database: document_analysis.individual_analysis")
    finally:
        cur.close()
        conn.close()
    
    # Check for Schedule D
    schedule_d_pages = [p for p in sorted_pages if 'schedule' in p.get('form_identification', {}).get('form_name', '').lower() and 'd' in p.get('form_identification', {}).get('form_name', '').lower()]
    
    if schedule_d_pages:
        print(f"\n🎯 Found Schedule D (Capital Gains): {len(schedule_d_pages)} page(s)")
        for p in schedule_d_pages:
            print(f"   Page {p['page']}: {p.get('summary', 'N/A')[:80]}")
    
    print(f"\n✅ Now re-run: python3 backend/step4a_verify_income.py 33")

if __name__ == "__main__":
    main()

