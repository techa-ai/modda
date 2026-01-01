"""
MT360 OCR Validation using AWS Bedrock Claude Opus 4.5
Compares MT360 extracted data with actual PDF content and deep JSON
"""
import os
import json
from pdf2image import convert_from_path
import base64
from io import BytesIO
from bedrock_config import BedrockClient

def validate_mt360_with_opus(loan_id, document_type, mt360_data, deep_json_data, pdf_path):
    """
    Use Claude Opus 4.5 via AWS Bedrock to validate MT360 OCR data against actual PDF and deep JSON
    
    Args:
        loan_id: Database loan ID
        document_type: Type of document (1008, URLA, Note, etc.)
        mt360_data: MT360 extracted JSON
        deep_json_data: Deep JSON from database
        pdf_path: Path to actual PDF
    
    Returns:
        Dict with validation results including field-by-field comparison
    """
    
    # Initialize Bedrock client with Claude Opus 4.5
    client = BedrockClient(model='claude-opus-4-5')
    
    # Convert PDF to images with page limits to avoid context overflow
    # 1004 appraisals: limit to 20 pages (key data is in first pages)
    # Other docs: limit to 30 pages
    max_pages = 20 if document_type == '1004' else 30
    
    pdf_images_base64 = []
    try:
        images = convert_from_path(pdf_path, dpi=150, first_page=1, last_page=max_pages)
        
        for img in images:
            buffered = BytesIO()
            img.save(buffered, format="PNG")
            img_str = base64.b64encode(buffered.getvalue()).decode()
            pdf_images_base64.append(img_str)
        print(f"  ✓ Converted {len(pdf_images_base64)} PDF pages to images (max {max_pages})")
    except Exception as e:
        print(f"  ⚠ Error converting PDF to images: {e}")
        pdf_images_base64 = []
    
    # Build the prompt - ONLY compare MT360 vs PDF (ignore deep JSON)
    # mt360_data is already the fields dict (extracted in app.py)
    mt360_fields = mt360_data if isinstance(mt360_data, dict) and not mt360_data.get('fields') else mt360_data.get('fields', mt360_data)
    
    prompt = f"""You are validating MT360 OCR extraction against the actual PDF document.

**DOCUMENT TYPE:** {document_type}

**MT360 EXTRACTED DATA:**
```json
{json.dumps(mt360_fields, indent=2)}
```

**YOUR TASK:**
For EACH field in the MT360 data above, find the SAME field in the PDF images and verify the value.

**NOTE DOCUMENT GUIDANCE (if document type is Note):**
- MIN (Mortgage Identification Number) is at the TOP of the note, format: XXXX-XXXX-XXXXXXXX-X
- Rate/Interest Rate is in Section 2 "INTEREST" - look for "yearly rate of X.XXX %"
- First Payment Date is in Section 3 "PAYMENTS" - look for "beginning on [DATE]"
- Last Payment/Maturity Date is in Section 3 - look for "on [DATE]" after "Maturity Date"
- Monthly P&I Payment is in Section 3(B) - look for "My Monthly Payment will be...U.S. $X,XXX.XX"
- Loan Amount/Principal is in Section 1 - look for "In return for a loan in the amount of U.S. $XXX,XXX.XX"
- Property Address is below the NOTE header

**1004 APPRAISAL REPORT GUIDANCE (if document type is 1004):**
- Property Address is typically at the top of the form
- Appraised Value is the key valuation field (look for "Opinion of Market Value" or "Appraised Value")
- Property Type (SFR, Condo, etc.) is usually in the Subject section
- Site Area/Lot Size is in the Site section
- GLA (Gross Living Area) is in the Improvements section  
- Number of Rooms, Bedrooms, Bathrooms are in the Improvements section
- Year Built is in the Improvements section
- Condition and Quality ratings may be letter grades (C1-C6, Q1-Q6) or descriptive

**CRITICAL FOR URLA DOCUMENTS:**
- URLA has MULTIPLE sections - use Section 4 "Loan and Property Information" for property values
- "Property Value" in MT360 refers to Section 4's "Property Value $" field
- "Loan Amount" in MT360 refers to Section 4's "Loan Amount $" field  
- Do NOT confuse with Section 3 "Real Estate" which shows OTHER properties owned
- The SUBJECT PROPERTY is in Section 4, not Section 3

**ADDRESS FIELDS - CRITICAL:**
- When MT360 has a combined address field (e.g., "Property Subject Address", "Current Subject Address", "Subject Address", "Mailing Address"):
  - The PDF often splits this across MULTIPLE fields: Street, City, State, ZIP, Country
  - You MUST COMBINE all these PDF fields into one full address for comparison
  - Example: If PDF shows "Street: 1821 CANBY COURT", "City: MARCO ISLAND", "State: FL", "ZIP: 34145"
    Then pdf_value should be: "1821 CANBY COURT, MARCO ISLAND, FL 34145" (combined)
  - Compare the FULL combined address against MT360's combined address
  - If MT360 says "EL" but PDF says "FL", that's a MISMATCH (typo in MT360)
  - If values match after combining, it's a MATCH


- "Mort This Lien Position First" = Is this a First Lien? Look at "First Mortgage" checkbox
- "Second Mort Present Indicator" = Is there a Second Mortgage? Look at "Second Mortgage" checkbox  
- "Mort Original Loan Amount" = Loan Amount field
- "Mort Interest Rate" = Note Rate / Interest Rate
- "Mort Loan Term Months" = Loan Term
- "Mort Initial Pand I Payment Amount" = First P&I Payment (NOT Subordinate Liens P&I)
- "Property Value" = Section 4 "Property Value $" (NOT Section 3 real estate)
- "Present Market Value Total" = Section 4 "Property Value $"

**CHECKBOX INTERPRETATION:**
- If MT360 says "False" for a checkbox field, the checkbox should be UNCHECKED in PDF
- If MT360 says "True", the checkbox should be CHECKED in PDF

**OUTPUT FORMAT - JSON array only:**
```json
[
  {{
    "mt360_field_name": "Exact MT360 field name",
    "mt360_value": "MT360 extracted value",
    "pdf_field_name": "Corresponding field name as shown in PDF",
    "pdf_value": "Actual value from PDF",
    "status": "MATCH or MISMATCH",
    "notes": "Brief explanation"
  }}
]
```

**MATCH RULES (CRITICAL - follow these exactly):**
- MATCH if numeric values are mathematically equal: $2,776.80 = $2,776.80, 8.87500% = 8.8750% = 8.875%
- MATCH if text values differ only in CASE: "QUEENS CRESCENT" = "Queens Crescent"
- MATCH if currency formatting differs but value same: $1,619,967.00 = 1619967
- MATCH if boolean equivalent (True = Yes = Checked, False = No = Unchecked)
- MATCH if trailing zeros differ: 8.375% = 8.37500% = 8.3750000%
- MISMATCH only if actual numeric/text content is DIFFERENT (e.g., 6,624.00 vs 6,624.39)
- DO NOT mark as mismatch if values are identical but formatted differently!

**CRITICAL: You MUST validate ALL {len(mt360_fields)} fields listed above. Do not skip any fields.**
**Include: Declarations, Demographic Information, Employment, Lender Loan Information, Signature sections.**

Analyze the PDF images carefully and output the complete JSON array with ALL {len(mt360_fields)} fields:"""

    # Build message content with text + multiple images
    content = [{"type": "text", "text": prompt}]
    
    for idx, img_base64 in enumerate(pdf_images_base64):
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": img_base64
            }
        })
    
    # If no images, just use text
    if not pdf_images_base64:
        content.append({
            "type": "text", 
            "text": "\n\n[No PDF images available - please validate based on deep JSON comparison only]"
        })
    
    messages = [{"role": "user", "content": content}]
    
    try:
        print(f"  🤖 Calling Claude Opus 4.5 via Bedrock ({len(mt360_fields)} fields to validate)...")
        
        # Call Bedrock with higher token limit to ensure all fields are processed
        response = client.invoke_model(
            messages=messages,
            max_tokens=32000,  # Increased to handle all fields
            temperature=0.0
        )
        
        response_text = response['content']
        print(f"  ✓ Received response from Opus 4.5")
        
        # Parse JSON from response (handle code blocks)
        if "```json" in response_text:
            json_start = response_text.find("```json") + 7
            json_end = response_text.find("```", json_start)
            json_str = response_text[json_start:json_end].strip()
        elif "```" in response_text:
            json_start = response_text.find("```") + 3
            json_end = response_text.find("```", json_start)
            json_str = response_text[json_start:json_end].strip()
        else:
            json_str = response_text.strip()
        
        validation_results = json.loads(json_str)
        
        # Calculate stats
        total_fields = len(validation_results)
        matches = sum(1 for r in validation_results if r.get('status') == 'MATCH')
        mismatches = sum(1 for r in validation_results if r.get('status') == 'MISMATCH')
        accuracy = round(matches / total_fields * 100, 2) if total_fields > 0 else 0
        
        print(f"  ✓ Validation complete: {matches}/{total_fields} matches ({accuracy}% accuracy)")
        
        return {
            'success': True,
            'results': validation_results,
            'total_fields': total_fields,
            'matches': matches,
            'mismatches': mismatches,
            'accuracy': accuracy,
            'model': 'claude-opus-4-5 (Bedrock)'
        }
        
    except json.JSONDecodeError as e:
        print(f"  ✗ JSON parse error: {e}")
        print(f"  Raw response: {response_text[:500]}...")
        return {
            'success': False,
            'error': f'Failed to parse Opus response as JSON: {str(e)}',
            'raw_response': response_text[:2000],
            'results': []
        }
    except Exception as e:
        print(f"  ✗ Error calling Claude Opus 4.5: {e}")
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'error': str(e),
            'results': []
        }


if __name__ == "__main__":
    # Test the validator
    print("Testing MT360 validator with Bedrock Claude Opus 4.5...")
    
    # Sample test data
    mt360_data = {
        "fields": {
            "Property Type": "1 unit",
            "Loan Amount": "$115,000.00"
        }
    }
    deep_json = {
        "Property Type": "1 unit",
        "Loan Amount": "115000"
    }
    
    result = validate_mt360_with_opus(
        loan_id=27,
        document_type="1008",
        mt360_data=mt360_data,
        deep_json_data=deep_json,
        pdf_path="/Users/sunny/Applications/bts/jpmorgan/mortgage/modda/documents/loan_1642451/1008___final_0.pdf"
    )
    
    print(json.dumps(result, indent=2))
