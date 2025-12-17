#!/usr/bin/env python3
"""
Test Llama with production prompt from step8_data_tape_construction.py
"""

import boto3
import json
import sys
from pdf2image import convert_from_path
import io
import base64

def get_production_prompt():
    """The exact production prompt used in step8_data_tape_construction.py"""
    return """You are extracting data from a Fannie Mae Form 1008 / Freddie Mac Form 1077.

CRITICAL: Extract ALL filled field values, grouped by the SECTION HEADERS on the form.

EXTRACTION RULES:
1. Return a NESTED JSON structure.
2. Top-level keys MUST be the SECTION HEADERS (e.g., "I. Borrower and Property Information", "II. Mortgage Information", "III. Underwriting Information").
3. CRITICAL SECTIONS TO EXTRACT:
   - "Stable Monthly Income" (Base Income, Other Income, Positive Cash Flow, Total Income)
   - "Present Housing Payment"
   - "Proposed Monthly Payments" (First Mortgage P&I, Second Mortgage P&I, Hazard Insurance, Taxes, MI, HOA, Other, Total)
   - "Qualifying Ratios" (Primary Housing Expense/Income, Total Obligations/Income, LTV, CLTV, HCLTV)
   - "Loan Type", "Amortization Type", "Loan Purpose", "Lien Position"
   - "Note Information" (Original Loan Amount, Initial Note Rate, Loan Term)
4. Extract values EXACTLY as they appear (preserve $, %).
5. For checkboxes: "True" if checked, "False" if unchecked.
6. IGNORE empty fields/unchecked boxes.
7. FOR SECTION III TABLES: Return as Key-Value pairs, NOT arrays.
   Example:
   "Proposed Monthly Payments": {
       "First Mortgage P&I": "$558.56",
       "Second Mortgage P&I": "$317.85",
       "Hazard Insurance": "$958.58",
       ...
   }

LOGIC & VALIDATION RULES (CRITICAL):
1. Pay attention to semantic logic, not just visual alignment if the form is messy.
2. 'Total All Monthly Payments' MUST be >= 'Total Primary Housing Expense'.
3. AVOID DUPLICATION: Do not assign the same numerical string/value to multiple attributes unless explicitly printed multiple times.
4. SEQUENTIAL MAPPING & MATH OVER ALIGNMENT (Proposed Monthly Payments):
   - Headers (e.g. "Other Obligations") DO NOT have values. If a value (e.g. $0.00) appears next to a header, SHIFT IT DOWN to the first attribute (e.g. "Negative Cash Flow").
   - Perform Math Check: "Total All Monthly Payments" = "Total Primary Housing Expense" + "All Other Monthly Payments" + "Negative Cash Flow".
   - Assign values to satisfy this equation, even if it contradicts visual alignment.
   - Example: If $5,343 + X + Y = $6,389, find which values correspond to X and Y based on the available numbers ($0.00, $1,046.00), ensuring the labels match the likely intent (e.g. Negative Cash Flow is usually 0).
5. Multiline labels (e.g. "Negative Cash Flow (subject property)") belong to the value on the main line or bottom line.
6. **CRITICAL "Other Obligations" SECTION FIX**:
   - "All Other Monthly Payments" is typically a SMALL number (credit cards, car loans, student loans, etc.). It is almost ALWAYS LESS than "Total Primary Housing Expense".
   - If you see a large value (close to or equal to "Total Primary Housing Expense") visually aligned with "All Other Monthly Payments", it is ALMOST CERTAINLY "Total All Monthly Payments" due to visual misalignment.
   - MATH CHECK: If "Total Primary Housing Expense" + "Negative Cash Flow" + your candidate "All Other Monthly Payments" does NOT equal "Total All Monthly Payments", reassign values.
   - Example: If Total Primary = $4,034.42 and you see $4,034.42 aligned with "All Other Monthly Payments", that is WRONG. The $4,034.42 is actually "Total All Monthly Payments", and "All Other Monthly Payments" is likely $0.00 (the value above it).

Return ONLY valid JSON."""

def test_llama_with_production_prompt(pdf_path):
    """Test Llama with production prompt"""
    
    print("="*80)
    print("TESTING LLAMA WITH PRODUCTION PROMPT")
    print("="*80)
    
    # Convert PDF to image
    print("\n📄 Converting PDF...")
    images = convert_from_path(pdf_path, dpi=150, first_page=1, last_page=1)
    img = images[0]
    
    buffered = io.BytesIO()
    img.save(buffered, format="JPEG", quality=85)
    img_b64 = base64.b64encode(buffered.getvalue()).decode()
    
    print(f"✓ Image: {len(img_b64)} chars\n")
    
    # Build prompt with image token
    production_prompt = get_production_prompt()
    
    prompt_with_token = f"""<|begin_of_text|><|start_header_id|>user<|end_header_id|>
<|image|>
{production_prompt}
<|eot_id|>
<|start_header_id|>assistant<|end_header_id|>"""
    
    body = {
        "prompt": prompt_with_token,
        "max_gen_len": 8000,
        "temperature": 0.0,
        "images": [img_b64]
    }
    
    # Call Llama
    client = boto3.client('bedrock-runtime', region_name='us-east-1')
    model_id = 'us.meta.llama4-maverick-17b-instruct-v1:0'
    
    print("🦙 Calling Llama 4 Maverick with production prompt...")
    print("   (This includes detailed \"Other Obligations\" instructions)\n")
    
    try:
        response = client.invoke_model(modelId=model_id, body=json.dumps(body))
        result = json.loads(response['body'].read())
        
        print("✅ SUCCESS!\n")
        
        generation = result.get('generation', '')
        
        # Parse JSON
        try:
            # Extract JSON from response
            if '```json' in generation:
                json_text = generation.split('```json')[1].split('```')[0].strip()
            elif '```' in generation:
                json_text = generation.split('```')[1].split('```')[0].strip()
            else:
                start = generation.find('{')
                end = generation.rfind('}') + 1
                json_text = generation[start:end]
            
            data = json.loads(json_text)
            
            # Save output
            with open('llama_production_prompt_result.json', 'w') as f:
                json.dump(data, f, indent=2)
            
            print("📊 Extracted Data Structure:")
            print(json.dumps(data, indent=2)[:1000] + "...\n")
            
            # Check for Other Obligations
            print("="*80)
            print("CHECKING 'OTHER OBLIGATIONS' EXTRACTION")
            print("="*80)
            
            # Try to find Other Obligations in the nested structure
            for section_key in data.keys():
                if 'underwriting' in section_key.lower() or 'III' in section_key:
                    section = data[section_key]
                    if isinstance(section, dict):
                        for key in section.keys():
                            if 'other' in key.lower() and 'obligation' in key.lower():
                                obligations = section[key]
                                print(f"\nFound in: {section_key} > {key}")
                                print(json.dumps(obligations, indent=2))
                                
                                # Check values
                                if isinstance(obligations, dict):
                                    all_other = None
                                    negative_cash = None
                                    total_all = None
                                    
                                    for k, v in obligations.items():
                                        if 'all other' in k.lower():
                                            all_other = v
                                        elif 'negative' in k.lower():
                                            negative_cash = v
                                        elif 'total' in k.lower():
                                            total_all = v
                                    
                                    print(f"\n📋 Extracted Values:")
                                    print(f"   All Other Monthly Payments: {all_other}")
                                    print(f"   Negative Cash Flow: {negative_cash}")
                                    print(f"   Total All Monthly Payments: {total_all}")
                                    
                                    print(f"\n✅ EXPECTED VALUES (from Claude):")
                                    print(f"   All Other Monthly Payments: $0.00")
                                    print(f"   Negative Cash Flow: $219.00")
                                    print(f"   Total All Monthly Payments: $10,372.74")
                                    
                                    return True
            
            print("\n⚠️  Could not find 'Other Obligations' in output structure")
            return False
            
        except json.JSONDecodeError as e:
            print(f"❌ Failed to parse JSON: {e}")
            print(f"Raw response: {generation[:500]}")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    pdf_path = "../public/loans/loan_1579510/1008___final_0.pdf"
    test_llama_with_production_prompt(pdf_path)

