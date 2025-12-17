
import sys
import json
import os
from db import execute_query, execute_one
from vlm_utils import VLMClient

def identify_evidence(loan_id):
    print(f"--- Step 8: Identifying Evidence Documents for Loan {loan_id} ---")
    
    # 1. Identify Truth Document (1008 Transmittal ONLY - Avoid URLA)
    # Priority: 1008 > URLA (only use URLA as last resort)
    truth_doc = execute_one(
        """SELECT * FROM document_analysis 
           WHERE loan_id = %s 
           AND status != 'deleted'
           AND (
               version_metadata->>'doc_type' ILIKE '%%1008%%' 
               OR version_metadata->>'doc_type' ILIKE '%%Transmittal%%'
               OR filename ILIKE '%%1008%%'
           )
           ORDER BY detected_date DESC, id DESC LIMIT 1""",
        (loan_id,)
    )
    
    source_type = '1008'
    source_name = '1008 Transmittal Form'
    
    if not truth_doc:
        print("⚠️  WARNING: No 1008 form found. Falling back to URLA (not recommended)...")
        truth_doc = execute_one(
            """SELECT * FROM document_analysis 
               WHERE loan_id = %s 
               AND status != 'deleted'
               AND (
                   version_metadata->>'doc_type' ILIKE '%%URLA%%' 
                   OR filename ILIKE '%%URLA%%'
               )
               ORDER BY detected_date DESC, id DESC LIMIT 1""",
            (loan_id,)
        )
        source_type = 'URLA'
        source_name = 'URLA (Fallback - Not Preferred)'
        
    if not truth_doc:
        print("CRITICAL: No Truth Document (1008 or URLA) found. Cannot perform evidence matching.")
        return

    print(f"✅ Selected TRUTH SOURCE: {truth_doc['filename']} (ID: {truth_doc['id']}, Type: {source_type})")
    
    # Try individual_analysis first, then vlm_analysis
    truth_json = truth_doc.get('individual_analysis') or truth_doc.get('vlm_analysis') or {}
    truth_content_str = ""
    
    # Handle Broken JSON (Error or Raw)
    if not truth_json:
        print("Truth source has no extracted data (checked individual_analysis and vlm_analysis).")
        return
        
    if 'error' in truth_json:
        print("Truth JSON has parse error. Using 'raw_content' fallback.")
        truth_content_str = truth_json.get('raw_content', "")
        # Strip markdown codes for cleanliness
        truth_content_str = truth_content_str.replace('```json', '').replace('```', '')
    else:
        truth_content_str = json.dumps(truth_json)

    if not truth_content_str:
        print("Truth content is empty. Aborting.")
        return

    # 2. Fetch Candidate Documents (Financial Only, Exclude Truth Doc)
    candidates = execute_query(
        """SELECT id, filename, 
                  COALESCE(individual_analysis, vlm_analysis) as analysis
           FROM document_analysis 
           WHERE loan_id = %s 
           AND id != %s
           AND status != 'deleted'
           AND (version_metadata->>'financial_category' = 'FINANCIAL' OR version_metadata->>'classification' = 'FINANCIAL')
           ORDER BY id""",
        (loan_id, truth_doc['id'])
    )
    
    print(f"Found {len(candidates)} candidate documents for evidence.")
    
    # Prepare Candidates Summary for Claude
    cand_summary = []
    for c in candidates:
        # Use snippet of extraction
        ext = c.get('vlm_analysis') or {}
        if 'error' in ext:
             snippet = ext.get('raw_content', '')[:500]
        else:
             snippet = json.dumps(ext)[:500] # Limit size
             
        cand_summary.append({
            "id": c['id'],
            "filename": c['filename'],
            "extraction_snippet": snippet
        })
        
    client = VLMClient(max_tokens=60000)
    
    TARGET_ATTRIBUTES = [
        "Property Type", "Occupancy Status", "Number of Units", "Sales Price", "Appraised Value",
        "Property Rights Type", "Loan Type", "Mort Amortization Type", "Loan Purpose Type",
        "Mort Original Loan Amount", "Mort Initial P and I Payment Amount", "Mort Interest Rate",
        "Mort Loan Term Months", "Buydown", "Mort This Lien Position First", "Second Mort Present Indicator",
        "Borrower Type", "Borrower Total Income Amount", "CoBorrower Total Income Amount",
        "Combined Base Income Amount", "Combined Other Income Amount", "Combined Total Income Amount",
        "Present Housing Payment Amount", 
        "Proposed Monthly Hazard Insurance Amount", "Proposed Monthly Taxes Amount", 
        "Proposed Monthly Mortgage Insurance Amount", "Proposed Monthly HOA Fees Amount", 
        "Proposed Monthly Other Amount", "Proposed Monthly Total Primary Housing Expense Amount",
        "Proposed Monthly All Other Monthly Payments Amount", "Proposed Monthly Total Monthly Payments Amount",
        "Borrower Funds To Close Verified Assets Amount", "Borrower Funds To Close Number Of Months Reserves",
        "Qualifying Ratios Primary House Expense To Income", "Qualifying Ratios Total Obligations To Income",
        "LTV Ratios LTV", "LTV Ratios CLTV", "LTV Ratios HCLTV",
        "Qualifying Note Rate Amount", "Level Of Property Review Type",
        "Escrow T and I Indicator", "Representative Credit Indicator Score"
    ]

    # 3. Prompt Claude to Find Evidence
    prompt = f"""
    You are a Mortgage Underwriting Auditor.
    
    OBJECTIVE:
    1. EXTRACT specific values from the "Truth Document" ({source_name}) for the attributes listed below.
    2. FIND EVIDENCE in the "Candidate Documents" that proves these values.
    
    IMPORTANT: The truth source is a {source_type} document. This is the authoritative source for 1008 form values.
    {'⚠️  NOTE: Using URLA as fallback - 1008 form is preferred but not available.' if source_type == 'URLA' else '✅ Using 1008 Transmittal Form (preferred source).'}
    
    TRUTH DATA (From {source_name}):
    {truth_content_str}
    
    CANDIDATE DOCUMENTS:
    {json.dumps(cand_summary)}
    
    TARGET ATTRIBUTES TO EXTRACT AND VERIFY:
    {json.dumps(TARGET_ATTRIBUTES)}
    
    OUTPUT FORMAT (JSON):
    {{
      "attributes": [
         {{
            "attribute_name": "Property Type",
            "value": "1 unit",
            "evidence_doc_id": 123, 
            "reason": "Appraisal confirms property type.",
            "source_type": "{source_type}"
         }},
         ...
      ]
    }}
    INSTRUCTIONS:
    - For EACH attribute in the Target List, try to find the value in the Truth Data.
    - If found, then try to find a supporting document in Candidates.
    - If value is missing in Truth Data, you may skip it or return null.
    - Be precise with amounts and percentages.
    - Always set source_type to "{source_type}" for each attribute.
    """
    
    print("Asking Claude to link evidence...")
    res = client.process_text("Evidence Linking", prompt, return_json=True)
    
    if res and 'attributes' in res:
        print(f"Claude returned {len(res['attributes'])} evidence links.")
        
        # 4. Update Database
        # Clear old evidence/data
        execute_query("DELETE FROM extracted_1008_data WHERE loan_id = %s", (loan_id,), fetch=False)
        execute_query("DELETE FROM evidence_files WHERE loan_id = %s", (loan_id,), fetch=False)

        # helpers
        def get_attr_id(name):
            row = execute_one("SELECT id FROM form_1008_attributes WHERE attribute_name = %s", (name,))
            if row: return row['id']
            # Create
            row = execute_one(
                "INSERT INTO form_1008_attributes (attribute_name, attribute_label, section) VALUES (%s, %s, 'Detected') RETURNING id",
                (name, name.replace('_', ' ').title())
            )
            return row['id']

        count = 0
        for item in res['attributes']:
            attr_name = item['attribute_name']
            val = item['value']
            doc_id = item.get('evidence_doc_id')
            item_source_type = item.get('source_type', source_type)
            
            # Get Attribute ID
            attr_id = get_attr_id(attr_name)
            
            # Insert 1008 Value with source tracking
            execute_query(
                """INSERT INTO extracted_1008_data (loan_id, attribute_id, extracted_value, confidence_score)
                   VALUES (%s, %s, %s, 0.99)
                   ON CONFLICT (loan_id, attribute_id) 
                   DO UPDATE SET extracted_value = EXCLUDED.extracted_value""",
                (loan_id, attr_id, str(val)),
                fetch=False
            )
            
            # Insert Evidence Link with source tracking
            if doc_id:
                # Get doc info
                doc = next((d for d in candidates if d['id'] == doc_id), None)
                if doc:
                    notes_dict = {
                        'reason': item.get('reason', ''),
                        'source_document': source_name,
                        'source_type': item_source_type,
                        'extracted_from': truth_doc['filename']
                    }
                    
                    execute_query(
                        """INSERT INTO evidence_files 
                           (loan_id, attribute_id, file_name, file_path, uploaded_at, 
                            source_document, source_type, notes)
                           VALUES (%s, %s, %s, 'linked_by_ai', NOW(), %s, %s, %s)""",
                        (loan_id, attr_id, doc['filename'], source_name, item_source_type, 
                         json.dumps(notes_dict)),
                        fetch=False
                    )
            else:
                # No supporting doc found - mark as self-verified from 1008/URLA
                notes_dict = {
                    'reason': f'Extracted directly from {source_name}',
                    'source_document': source_name,
                    'source_type': item_source_type,
                    'extracted_from': truth_doc['filename'],
                    'self_verified': True
                }
                
                execute_query(
                    """INSERT INTO evidence_files 
                       (loan_id, attribute_id, file_name, file_path, uploaded_at, 
                        source_document, source_type, notes, verification_status)
                       VALUES (%s, %s, %s, 'direct_extraction', NOW(), %s, %s, %s, 'verified')""",
                    (loan_id, attr_id, truth_doc['filename'], source_name, item_source_type, 
                     json.dumps(notes_dict)),
                    fetch=False
                )
                
            count += 1
            
        print(f"Successfully linked {count} attributes with evidence (Source: {source_type}).")
    else:
        print("Evidence linking failed or returned no results.")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        loan_id = sys.argv[1]
    else:
        loan_id = 1
    identify_evidence(loan_id)
