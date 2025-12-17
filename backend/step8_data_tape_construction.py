#!/usr/bin/env python3
"""
Step 8: Data Tape Construction (Data Tape Validation) - Section Aware

Extracts data from Master 1008/1003 using FORM SECTIONS as the grouping structure.
This ensures the UI reflects the exact structure of the source document.
"""

import os
import json
import re
import traceback
from pdf2image import pdfinfo_from_path

# Import core infrastructure
from db import execute_query, execute_one, get_db_connection
from bedrock_config import call_bedrock
from processing import pdf_to_base64, log_progress

def get_master_document(loan_id):
    """Find master document (1008 or 1003)"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 1. Look for Master 1008
    cur.execute("""
        SELECT filename, file_path, version_metadata
        FROM document_analysis
        WHERE loan_id = %s
        AND is_latest_version = TRUE
        AND (
            version_metadata->>'doc_type' ILIKE %s
            OR version_metadata->>'doc_type' ILIKE %s
            OR filename ILIKE %s
        )
        ORDER BY detected_date DESC, id DESC
        LIMIT 1
    """, (loan_id, '%1008%', '%Transmittal%', '%1008%'))
    
    doc_1008 = cur.fetchone()
    if doc_1008:
        print(f"Found Master 1008: {doc_1008['filename']}")
        cur.close()
        conn.close()
        return doc_1008, '1008'
        
    # 2. Fallback to Master URLA
    cur.execute("""
        SELECT filename, file_path, version_metadata
        FROM document_analysis
        WHERE loan_id = %s
        AND is_latest_version = TRUE
        AND (
            version_metadata->>'doc_type' ILIKE %s
            OR version_metadata->>'doc_type' ILIKE %s
            OR version_metadata->>'doc_type' ILIKE %s
            OR filename ILIKE %s
        )
        ORDER BY detected_date DESC, id DESC
        LIMIT 1
    """, (loan_id, '%1003%', '%URLA%', '%Loan Application%', '%urla%'))
    
    doc_1003 = cur.fetchone()
    if doc_1003:
        print(f"No 1008 found. Using Master URLA: {doc_1003['filename']}")
        cur.close()
        conn.close()
        return doc_1003, '1003'
    
    cur.close()
    conn.close()
    return None, None

def extract_json_from_text(text):
    try:
        if "```json" in text:
            json_str = text.split("```json")[1].split("```")[0]
            return json.loads(json_str)
        elif "{" in text:
            start = text.find("{")
            end = text.rfind("}") + 1
            json_str = text[start:end]
            return json.loads(json_str)
        return None
    except:
        return None

def run_data_tape_construction(loan_id):
    log_progress(loan_id, 'Data Tape', 'running', 'Starting Data Tape Construction (Section Aware)...')
    
    try:
        # 1. Identify Target Document
        target_doc, doc_type = get_master_document(loan_id)
        
        if not target_doc:
            msg = "No 1008 or URLA document found. Data Tape will be empty."
            log_progress(loan_id, 'Data Tape', 'warning', msg)
            return
            
        file_path = target_doc['file_path']
        if not os.path.exists(file_path):
            file_path = os.path.abspath(file_path)
            if not os.path.exists(file_path):
                 log_progress(loan_id, 'Data Tape', 'error', f"Document file missing: {file_path}")
                 return

        # 2. Convert to Image
        print("   🖼️ Converting PDF to Image...")
        log_progress(loan_id, 'Data Tape', 'running', f'Converting {doc_type} to image...')
        import time
        t0 = time.time()
        image_base64, img_dimensions = pdf_to_base64(file_path)
        print(f"   ✓ Image Conversion took {time.time() - t0:.2f}s")
        
        if not image_base64:
             log_progress(loan_id, 'Data Tape', 'error', "Failed to convert PDF to image")
             return
             
        img_width, img_height = img_dimensions
        
        # 3. Build Prompt (Section Aware)
        if doc_type == '1008':
            form_name = "Fannie Mae Form 1008 / Freddie Mac Form 1077"
        else:
            form_name = "URLA Form 1003 (Uniform Residential Loan Application)"
            
        prompt = f"""
You are extracting data from a {form_name}.

CRITICAL: Extract ALL filled field values, grouped by the SECTION HEADERS on the form.
IMAGE SPECIFICATIONS: {img_width}x{img_height} pixels.

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
   "Proposed Monthly Payments": {{
       "First Mortgage P&I": "$558.56",
       "Second Mortgage P&I": "$317.85",
       "Hazard Insurance": "$958.58",
       ...
   }}

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

EXAMPLE OUTPUT:
{{
  "I. Borrower and Property Information": {{
      "Borrower Name": "John Doe",
      "Property Address": "123 Main St"
  }},
  "_meta": {{...}}
}}

INCLUDE "_bbox" for every LEAF value field.
"""

        # 4. Call Claude
        print("   🧠 Calling Claude Opus (this may take 30-60s)...")
        log_progress(loan_id, 'Data Tape', 'running', f'Extracting with section grouping...')
        
        t1 = time.time()
        response_text = call_bedrock(prompt, image_base64=image_base64, model='claude-opus-4-5', max_tokens=60000)
        print(f"   ✓ Claude Response took {time.time() - t1:.2f}s")
        
        # Save raw response for debugging
        with open(f"loan_{loan_id}_claude_response.txt", "w") as f:
            f.write(response_text)
        print(f"   💾 Saved raw response to loan_{loan_id}_claude_response.txt ({len(response_text)} chars)")
        
        print("   📂 Parsing Response...")
        extracted_data = extract_json_from_text(response_text)
        
        if not extracted_data:
            print(f"   ❌ Failed to parse JSON. Raw response length: {len(response_text)}")
            print(f"   ❌ Raw response snippet: {response_text[:200]}...")
            raise Exception("Failed to parse JSON from Claude response")

        # 5. Save Data
        print("   💾 Saving extracted data to database...")
        execute_query("DELETE FROM extracted_1008_data WHERE loan_id = %s", (loan_id,), fetch=False)
        
        count = flatten_and_save(loan_id, extracted_data, file_path)
        log_progress(loan_id, 'Data Tape', 'completed', f'Populated {count} attributes with sections')

    except Exception as e:
        tb = traceback.format_exc()
        log_progress(loan_id, 'Data Tape', 'failed', f'Data Tape Construction failed: {str(e)}')
        print(tb)

def flatten_and_save(loan_id, data, file_path):
    count = 0
    display_counter = 0
    bbox_map = {}
    
    # Pass 1: Collect bboxes (recursive)
    def collect_bboxes(d):
        if not isinstance(d, dict): return
        for k, v in d.items():
            if k.endswith('_bbox') and isinstance(v, dict):
                bbox_map[k[:-5]] = v
            elif isinstance(v, dict):
                collect_bboxes(v)
    
    if isinstance(data, dict):
        collect_bboxes(data)

    # Pass 2: Save values with Section tracking & Ordering
    def save_recursive(d, current_section):
        nonlocal count, display_counter
        for k, v in d.items():
            if k.endswith('_bbox') or k == '_meta':
                continue
            
            # Check for { "value": "...", "_bbox": ... } pattern
            if isinstance(v, dict) and 'value' in v:
                # Treat 'k' as the attribute name, and v['value'] as the value
                val = v['value']
                bbox = v.get('_bbox')
                if k not in bbox_map and bbox:
                    bbox_map[k] = bbox # Store it for saving
                
                # Process as leaf
                process_leaf(k, val, current_section, bbox_map.get(k))
                continue

            if isinstance(v, dict):
                # Nested section! Append to current section path
                # e.g. "III. Underwriting Info" > "Stable Monthly Income"
                new_section = k if not current_section else f"{current_section} > {k}"
                save_recursive(v, new_section)
            elif isinstance(v, list):
                # Try to process lists if they contain dicts
                for item in v:
                    if isinstance(item, dict):
                         save_recursive(item, current_section)
                continue
            else:
                # Leaf node (direct value)
                process_leaf(k, v, current_section, bbox_map.get(k))

    def process_leaf(k, v, current_section, bbox):
        nonlocal count, display_counter
        
        # Filter empty
        if v is None: return
        val_str = str(v).strip()
        if not val_str or val_str.lower() in ['null', 'none', 'false']:
            return
        
        # Increment order
        display_counter += 10
        
        # Attribute Name = snake_case of Label
        attr_name = k.lower().replace(' ', '_').replace('.', '').replace('-', '_')
        
        # Attribute Label = Exact Label (k)
        attr_label = k
        
        # Section = current_section
        section_name = current_section if current_section else "General"
        
        # Check/Create Attribute
        attr = execute_one("SELECT id FROM form_1008_attributes WHERE attribute_name = %s", (attr_name,))
        
        if attr:
            # Update Label & Section AND Order
            execute_query(
                "UPDATE form_1008_attributes SET attribute_label = %s, section = %s, display_order = %s WHERE id = %s",
                (attr_label, section_name, display_counter, attr['id']),
                fetch=False
            )
        else:
            # Create New
            execute_one(
                '''INSERT INTO form_1008_attributes (attribute_name, attribute_label, section, display_order)
                   VALUES (%s, %s, %s, %s) RETURNING id''',
                (attr_name, attr_label, section_name, display_counter)
            )
            attr = execute_one("SELECT id FROM form_1008_attributes WHERE attribute_name = %s", (attr_name,))
        
        if attr:
            bbox_json = json.dumps(bbox) if bbox else None
            execute_query(
                '''INSERT INTO extracted_1008_data (loan_id, attribute_id, extracted_value, confidence_score, document_path, bounding_box)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (loan_id, attribute_id) 
                   DO UPDATE SET extracted_value = EXCLUDED.extracted_value,
                                 confidence_score = EXCLUDED.confidence_score,
                                 document_path = EXCLUDED.document_path,
                                 bounding_box = EXCLUDED.bounding_box''',
                (loan_id, attr['id'], val_str, 0.95, file_path, bbox_json),
                fetch=False
            )
            count += 1

    if isinstance(data, dict):
        # Start recursion with empty section or use keys
        save_recursive(data, "")
        
    return count

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python3 step8_data_tape_construction.py <loan_id>")
    else:
        run_data_tape_construction(int(sys.argv[1]))
