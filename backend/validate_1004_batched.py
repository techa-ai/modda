"""
1004 Appraisal Validator - Batched Processing
Processes large appraisal PDFs in batches and extracts deep JSON
"""

import json
import os
import base64
from io import BytesIO
from datetime import datetime
from pdf2image import convert_from_path
from bedrock_config import BedrockClient

def extract_1004_deep_json(pdf_path: str, loan_id: str, output_dir: str = None) -> dict:
    """
    Extract structured data from 1004 appraisal PDF using Claude.
    This creates deep JSON for future validation comparisons.
    """
    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(__file__), '..', 'outputs', '1004_deep_json')
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"  📄 Extracting deep JSON from appraisal PDF: {pdf_path}")
    
    client = BedrockClient(model='claude-opus-4-5')
    
    # Convert first 15 pages (where most appraisal data is)
    try:
        images = convert_from_path(pdf_path, dpi=150, first_page=1, last_page=15)
        print(f"  ✓ Converted {len(images)} pages for deep JSON extraction")
    except Exception as e:
        print(f"  ✗ Error converting PDF: {e}")
        return {"error": str(e)}
    
    # Convert to base64
    pdf_images = []
    for img in images:
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        pdf_images.append(base64.b64encode(buffered.getvalue()).decode())
    
    prompt = """Extract ALL data from this 1004 Appraisal Report (URAR - Uniform Residential Appraisal Report).

Return a JSON object with these sections:

{
    "subject": {
        "property_address": "full address",
        "city": "",
        "state": "",
        "zip": "",
        "county": "",
        "legal_description": "",
        "assessor_parcel_number": "",
        "tax_year": "",
        "real_estate_taxes": "",
        "special_assessments": "",
        "borrower": "",
        "owner": "",
        "neighborhood_name": ""
    },
    "contract": {
        "contract_price": "",
        "date_of_contract": "",
        "property_seller": "",
        "seller_concessions": ""
    },
    "neighborhood": {
        "location": "",
        "built_up": "",
        "growth": "",
        "property_values": "",
        "demand_supply": "",
        "marketing_time": "",
        "one_unit_housing_type": "",
        "price_range_low": "",
        "price_range_high": "",
        "age_range_low": "",
        "age_range_high": ""
    },
    "site": {
        "dimensions": "",
        "area_sqft": "",
        "zoning": "",
        "highest_best_use": "",
        "utilities_electric": "",
        "utilities_gas": "",
        "utilities_water": "",
        "utilities_sewer": "",
        "flood_zone": "",
        "fema_map_number": "",
        "fema_map_date": ""
    },
    "improvements": {
        "year_built": "",
        "effective_age": "",
        "foundation_type": "",
        "exterior_walls": "",
        "roof_surface": "",
        "design_style": "",
        "total_rooms": "",
        "bedrooms": "",
        "bathrooms": "",
        "gross_living_area_sqft": "",
        "basement_sqft": "",
        "basement_finished_sqft": "",
        "heating_type": "",
        "cooling_type": "",
        "garage_carport": "",
        "porch_patio_deck": "",
        "fireplace": "",
        "pool": "",
        "condition": "",
        "quality": ""
    },
    "sales_comparison": {
        "comparable_1": {"address": "", "sale_price": "", "date": "", "gla": ""},
        "comparable_2": {"address": "", "sale_price": "", "date": "", "gla": ""},
        "comparable_3": {"address": "", "sale_price": "", "date": "", "gla": ""}
    },
    "reconciliation": {
        "indicated_value_sales_comparison": "",
        "indicated_value_cost": "",
        "indicated_value_income": "",
        "final_opinion_of_value": "",
        "effective_date": ""
    },
    "appraiser": {
        "appraiser_name": "",
        "company_name": "",
        "company_address": "",
        "license_number": "",
        "state": "",
        "signature_date": ""
    },
    "pud_info": {
        "is_pud": "",
        "hoa_fee": "",
        "project_name": ""
    }
}

Fill in ALL values you can find. Use empty string "" if not found.
Return ONLY the JSON object, no markdown."""

    content = [{"type": "text", "text": prompt}]
    for img_b64 in pdf_images:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": img_b64
            }
        })
    
    try:
        response = client.invoke_model(
            messages=[{"role": "user", "content": content}],
            max_tokens=8000,
            temperature=0.0
        )
        
        response_text = response.get('content', '{}')
        
        # Clean up response
        if '```json' in response_text:
            response_text = response_text.split('```json')[1].split('```')[0]
        elif '```' in response_text:
            response_text = response_text.split('```')[1].split('```')[0]
        
        deep_json = json.loads(response_text.strip())
        deep_json['extraction_timestamp'] = datetime.now().isoformat()
        deep_json['source_pdf'] = os.path.basename(pdf_path)
        deep_json['loan_id'] = loan_id
        
        # Save to file
        output_file = os.path.join(output_dir, f'loan_{loan_id}_1004_deep.json')
        with open(output_file, 'w') as f:
            json.dump(deep_json, f, indent=2)
        
        print(f"  ✓ Deep JSON saved to: {output_file}")
        return deep_json
        
    except Exception as e:
        print(f"  ✗ Error extracting deep JSON: {e}")
        return {"error": str(e)}


def validate_1004_batched(loan_id: str, mt360_data: dict, pdf_path: str, batch_size: int = 10) -> dict:
    """
    Validate 1004 appraisal by processing pages in batches.
    Each batch validates the fields it can find.
    """
    print(f"\n{'='*60}")
    print(f"1004 BATCHED VALIDATION - Loan {loan_id}")
    print(f"{'='*60}")
    
    client = BedrockClient(model='claude-opus-4-5')
    
    # Get total pages
    try:
        all_images = convert_from_path(pdf_path, dpi=100, first_page=1, last_page=1)
        from pdf2image.pdf2image import pdfinfo_from_path
        info = pdfinfo_from_path(pdf_path)
        total_pages = info.get('Pages', 50)
        print(f"  📄 PDF has {total_pages} pages, processing in batches of {batch_size}")
    except:
        total_pages = 50  # Assume max
    
    # Limit to first 40 pages for appraisals
    total_pages = min(total_pages, 40)
    
    mt360_fields = mt360_data.get('fields', mt360_data) if isinstance(mt360_data, dict) else mt360_data
    
    all_results = {}
    fields_validated = set()
    
    # Process in batches
    for batch_start in range(1, total_pages + 1, batch_size):
        batch_end = min(batch_start + batch_size - 1, total_pages)
        print(f"\n  📦 Batch: Pages {batch_start}-{batch_end}")
        
        try:
            images = convert_from_path(pdf_path, dpi=150, first_page=batch_start, last_page=batch_end)
        except Exception as e:
            print(f"    ✗ Error converting pages: {e}")
            continue
        
        # Convert to base64
        pdf_images = []
        for img in images:
            buffered = BytesIO()
            img.save(buffered, format="PNG")
            pdf_images.append(base64.b64encode(buffered.getvalue()).decode())
        
        # Fields not yet validated
        remaining_fields = {k: v for k, v in mt360_fields.items() if k not in fields_validated}
        
        if not remaining_fields:
            print(f"    ✓ All fields validated!")
            break
        
        prompt = f"""You are validating MT360 OCR data for a 1004 Appraisal Report (URAR - Uniform Residential Appraisal Report).

**MT360 FIELDS TO VALIDATE:**
```json
{json.dumps(remaining_fields, indent=2)}
```

**PDF PAGES:** {batch_start} to {batch_end}

**IMPORTANT FIELD MAPPINGS - Look for these on Page 1:**
- "Primary" (MT360 True/False) = "Occupant" section → "Owner" checkbox. If Owner is checked (X), Primary = True
- "Is Pud Attached" (MT360 1/0) = SITE section → "PUD" checkbox. If PUD is checked (X), value = 1
- "Pud Attached" (MT360 True/False) = Same as above, True if PUD checkbox marked
- "Flood Zone Indicator" (MT360 True/False) = SITE section → "FEMA Flood Zone". Zone X means NO flood zone = False
- "Project Dwelling Unit Count" (MT360 1) = GENERAL DESCRIPTION → "Units" row → "One" checkbox. If One is marked, value = 1
- "Property Dwelling Unit Eligible Rent Amount" = Usually $0.00 for owner-occupied, check "PUD" section or market rent fields

**CHECKBOX INTERPRETATION:**
- An "X" or checkmark in a box means that option is selected
- For True/False: checked = True, unchecked = False
- For numeric: "One" checked = 1, "Two" checked = 2, etc.

For EACH field you can find on these pages, return a JSON array:
[
  {{
    "mt360_field_name": "field name from above",
    "mt360_value": "the value from MT360 data above",
    "pdf_value": "the value you found in the PDF",
    "pdf_page": {batch_start} to {batch_end},
    "status": "MATCH" or "MISMATCH" or "NOT_FOUND",
    "notes": "explanation if mismatch"
  }}
]

- ONLY include fields you can find on THESE pages
- If a field is not on these pages, do NOT include it
- Be precise with values - include currency symbols, decimals, etc.

Return ONLY the JSON array."""

        content = [{"type": "text", "text": prompt}]
        for img_b64 in pdf_images:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": img_b64
                }
            })
        
        try:
            response = client.invoke_model(
                messages=[{"role": "user", "content": content}],
                max_tokens=8000,
                temperature=0.0
            )
            
            response_text = response.get('content', '[]')
            
            if '```json' in response_text:
                response_text = response_text.split('```json')[1].split('```')[0]
            elif '```' in response_text:
                response_text = response_text.split('```')[1].split('```')[0]
            
            batch_results = json.loads(response_text.strip())
            
            for result in batch_results:
                field_name = result.get('mt360_field_name', '')
                if field_name and field_name not in fields_validated:
                    all_results[field_name] = result
                    fields_validated.add(field_name)
            
            print(f"    ✓ Validated {len(batch_results)} fields in this batch")
            
        except Exception as e:
            print(f"    ✗ Error in batch: {e}")
            continue
    
    # Calculate totals
    results_list = list(all_results.values())
    matches = sum(1 for r in results_list if r.get('status') == 'MATCH')
    mismatches = sum(1 for r in results_list if r.get('status') == 'MISMATCH')
    not_found = sum(1 for r in results_list if r.get('status') == 'NOT_FOUND')
    
    # Add NOT_FOUND for fields that weren't validated at all
    for field_name, field_value in mt360_fields.items():
        if field_name not in fields_validated:
            results_list.append({
                "mt360_field_name": field_name,
                "mt360_value": field_value,
                "pdf_value": "N/A",
                "pdf_page": "N/A",
                "status": "NOT_FOUND",
                "notes": "Field not found in processed pages"
            })
            not_found += 1
    
    total = matches + mismatches
    accuracy = (matches / total * 100) if total > 0 else 0
    
    print(f"\n{'='*60}")
    print(f"VALIDATION COMPLETE")
    print(f"{'='*60}")
    print(f"  Matches: {matches}")
    print(f"  Mismatches: {mismatches}")
    print(f"  Not Found: {not_found}")
    print(f"  Accuracy: {accuracy:.1f}%")
    
    return {
        "success": True,
        "loan_id": loan_id,
        "document_type": "1004",
        "validation_timestamp": datetime.now().isoformat(),
        "matches": matches,
        "mismatches": mismatches,
        "not_found": not_found,
        "total_fields": len(mt360_fields),
        "accuracy": accuracy,
        "results": results_list
    }


if __name__ == "__main__":
    # Test with loan 1584069
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--loan-id', default='1584069')
    parser.add_argument('--extract-deep-json', action='store_true')
    parser.add_argument('--validate', action='store_true')
    args = parser.parse_args()
    
    base_dir = os.path.dirname(os.path.dirname(__file__))
    doc_dir = os.path.join(base_dir, 'documents', f'loan_{args.loan_id}')
    
    # Find appraisal PDF dynamically
    pdf_path = None
    if os.path.exists(doc_dir):
        for f in sorted(os.listdir(doc_dir)):
            f_lower = f.lower()
            if f_lower.endswith('.pdf') and 'appraisal' in f_lower:
                # Skip acknowledgement, disclosure, review, right_to_copy
                if any(skip in f_lower for skip in ['acknowledgement', 'disclosure', 'review', 'right_to_copy', 'preliminary']):
                    continue
                pdf_path = os.path.join(doc_dir, f)
                print(f"Found appraisal PDF: {pdf_path}")
                break
    
    if not pdf_path:
        print(f"No appraisal PDF found in {doc_dir}")
    
    mt360_file = os.path.join(base_dir, 'outputs', 'mt360_complete_extraction', 'data', f'loan_{args.loan_id}_1004.json')
    
    if args.extract_deep_json:
        print("\n" + "="*60)
        print("EXTRACTING DEEP JSON FROM APPRAISAL")
        print("="*60)
        result = extract_1004_deep_json(pdf_path, args.loan_id)
        print(json.dumps(result, indent=2)[:2000])
    
    if args.validate:
        if os.path.exists(mt360_file):
            with open(mt360_file) as f:
                mt360_data = json.load(f)
            result = validate_1004_batched(args.loan_id, mt360_data, pdf_path)
            
            # Save result
            output_file = os.path.join(base_dir, 'outputs', 'mt360_validation_cache', f'loan_{args.loan_id}_1004.json')
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            with open(output_file, 'w') as f:
                json.dump(result, f, indent=2)
            print(f"\n✓ Saved to: {output_file}")
        else:
            print(f"MT360 data not found: {mt360_file}")
