#!/usr/bin/env python3
"""
Deep JSON extraction for a single document
"""

import os
import sys
import json
from pathlib import Path
from pdf2image import convert_from_path
from PyPDF2 import PdfReader

from vlm_utils import VLMClient
from db import execute_one, get_db_connection


def extract_document_deep_json(pdf_path: str, loan_id: int, filename: str):
    """
    Perform deep JSON extraction on a single document using VLM.
    """
    print(f"\n{'='*80}")
    print(f"🔍 DEEP JSON EXTRACTION")
    print(f"{'='*80}")
    print(f"Document: {filename}")
    print(f"Loan ID: {loan_id}")
    print(f"Path: {pdf_path}")
    
    if not os.path.exists(pdf_path):
        print(f"❌ File not found: {pdf_path}")
        return False
    
    # Get page count
    try:
        reader = PdfReader(pdf_path)
        page_count = len(reader.pages)
        print(f"📄 Pages: {page_count}")
    except Exception as e:
        print(f"❌ Error reading PDF: {e}")
        return False
    
    if page_count > 100:
        print(f"⚠️  Document too large ({page_count} pages) - skipping")
        return False
    
    # Initialize VLM client with maximum tokens for large documents
    print(f"\n🤖 Initializing Claude Opus 4.5...")
    # Use Bedrock's max output limit (depending on model, typically 16K-32K)
    client = VLMClient(model='claude-opus-4-5', max_tokens=16000)
    
    # Build focused prompt for appraisal documents - prioritize key valuation data
    prompt = f"""You are a mortgage document analysis expert. Analyze this appraisal document and extract the KEY PROPERTY VALUATION DATA into structured JSON.

# FOCUS ON KEY DATA
This appears to be an APPRAISAL REPORT. Extract the MOST IMPORTANT information needed for property value verification:

CRITICAL DATA TO EXTRACT:
1. **Appraised Value** (MOST IMPORTANT)
2. Property Address
3. Appraisal Date
4. Loan Purpose (Purchase/Refinance)
5. Contract Price (if purchase)
6. Property Details (type, sq ft, bedrooms, bathrooms, year built)
7. Borrower/Appraiser Names
8. Top 3-6 Sales Comparables

# OUTPUT FORMAT (Strict JSON)
{{
  "document_type": "Uniform Residential Appraisal Report" or other type,
  "document_summary": "<2-3 sentence summary>",
  "key_data": {{
    "property_address": "<full address with city, state, zip>",
    "appraised_value": <numeric value without $>,
    "appraisal_date": "<YYYY-MM-DD format>",
    "loan_purpose": "Purchase" or "Refinance" or "Other",
    "contract_price": <numeric value if purchase, else null>,
    "borrower_name": "<full name>",
    "appraiser_name": "<full name>",
    "appraiser_license": "<license#>",
    "property_type": "<Single Family Residence, Condo, etc.>",
    "year_built": <year as number>,
    "gross_living_area_sqft": <numeric>,
    "lot_size_sqft": <numeric or null>,
    "bedrooms": <count>,
    "bathrooms": <count>,
    "rooms_total": <count>
  }},
  "comparables": [
    {{
      "comp_number": 1,
      "address": "<address>",
      "sale_price": <numeric>,
      "sale_date": "<date>",
      "gross_living_area": <sqft>,
      "proximity": "<distance description>"
    }}
  ],
  "page_references": {{
    "appraised_value_page": <page number where final value appears>,
    "subject_property_page": <page number with property details>,
    "comparables_page": <page number with comps>
  }}
}}

CRITICAL RULES:
- Focus on ACCURACY over completeness
- Extract EXACT numeric values (no commas, no $ signs in numbers)
- If unsure about a value, use null
- Prioritize the FINAL APPRAISED VALUE - this is critical
- Include page numbers where key data was found
"""
    
    print(f"\n📤 Sending to Claude for analysis...")
    print(f"⏱️  This will take ~30-60 seconds per page...")
    
    try:
        result = client.process_document(
            pdf_path=pdf_path,
            prompt=prompt,
            dpi=150,
            return_json=True
        )
        
        if not result:
            print(f"❌ Failed to extract JSON from document")
            return False
        
        # Handle case where result is a string (JSON parsing failed)
        if isinstance(result, str):
            print(f"⚠️  Response is text, attempting to extract JSON...")
            # Remove markdown code blocks if present
            import re
            text = result.strip()
            
            # Remove ```json ... ``` wrapper if present
            if text.startswith('```'):
                text = re.sub(r'^```(?:json)?\s*\n', '', text)
                text = re.sub(r'\n```\s*$', '', text)
            
            # Try to parse as JSON
            try:
                result = json.loads(text)
                print(f"✅ Successfully extracted JSON from text response")
            except Exception as e:
                print(f"❌ Could not parse JSON: {e}")
                print(f"Response preview: {text[:500]}...")
                return False
        
        print(f"\n✅ Extraction successful!")
        print(f"   - Document type: {result.get('document_type', 'Unknown')}")
        print(f"   - Pages analyzed: {len(result.get('pages', []))}")
        
        if 'key_data' in result:
            key_data = result['key_data']
            if key_data.get('appraised_value'):
                print(f"   - Appraised Value: ${key_data['appraised_value']:,.0f}")
            if key_data.get('property_address'):
                print(f"   - Property: {key_data['property_address']}")
        
        # Save to database
        print(f"\n💾 Saving to database...")
        save_to_database(loan_id, filename, result)
        print(f"✅ Saved successfully!")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error during extraction: {e}")
        import traceback
        traceback.print_exc()
        return False


def save_to_database(loan_id: int, filename: str, analysis: dict):
    """Save the deep JSON analysis to document_analysis table."""
    
    # Update document_analysis with the extracted JSON
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            UPDATE document_analysis
            SET individual_analysis = %s
            WHERE loan_id = %s AND filename = %s
        """, (json.dumps(analysis), loan_id, filename))
        
        conn.commit()
        print(f"   Updated document_analysis table")
        
    finally:
        cur.close()
        conn.close()


def main():
    if len(sys.argv) < 3:
        print("Usage: python extract_single_document.py <loan_id> <filename>")
        print("\nExample:")
        print("  python extract_single_document.py 2 appraisal_25.pdf")
        return
    
    loan_id = int(sys.argv[1])
    filename = sys.argv[2]
    
    # Find the document path
    doc = execute_one("""
        SELECT file_path, filename
        FROM document_analysis
        WHERE loan_id = %s AND filename = %s
    """, (loan_id, filename))
    
    if not doc:
        print(f"❌ Document not found: {filename} for loan {loan_id}")
        return
    
    pdf_path = doc['file_path']
    
    # Run extraction
    success = extract_document_deep_json(pdf_path, loan_id, filename)
    
    if success:
        print(f"\n{'='*80}")
        print(f"✨ EXTRACTION COMPLETE!")
        print(f"{'='*80}")
        print(f"\nYou can now run property verification for this loan.")
        print(f"The deep JSON is stored in the database and ready to use.\n")
    else:
        print(f"\n{'='*80}")
        print(f"❌ EXTRACTION FAILED")
        print(f"{'='*80}\n")


if __name__ == "__main__":
    main()

