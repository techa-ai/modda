#!/usr/bin/env python3
"""
Batch Evidence Generator - Process ALL attributes in ONE Claude call
Much more efficient than one-by-one processing!
"""

import json
import os
from datetime import datetime
from db import get_db_connection
from bedrock_config import call_bedrock

def load_financial_documents(loan_id: int) -> list[dict]:
    """Load FINANCIAL documents only (excluding 1008, URLA, tax_returns)"""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT filename, version_metadata, individual_analysis
            FROM document_analysis
            WHERE loan_id = %s
            ORDER BY filename
        """, (loan_id,))
        
        docs = []
        for r in cur.fetchall():
            fn = (r.get("filename") or "").lower()
            md = r.get("version_metadata") or {}
            
            # Skip non-evidence docs
            if "1008" in fn or "urla" in fn or "tax_return" in fn or "lender_loan_information" in fn:
                continue
            
            # Skip documents that should NEVER be used as evidence
            # NOTE: Don't exclude miscellaneous_docs - some contain important data like Income Summary Reports!
            if "rate_lock" in fn or "loan_estimate" in fn or "closing_disclosure" in fn:
                continue
            
            # Only FINANCIAL docs
            if md.get("financial_category") == "FINANCIAL":
                analysis = r.get("individual_analysis")
                analysis_str = json.dumps(analysis) if analysis else ""
                # Truncate to 8K per doc
                if len(analysis_str) > 8000:
                    analysis_str = analysis_str[:8000] + "...[truncated]"
                docs.append({
                    "filename": r.get("filename"),
                    "analysis": analysis_str
                })
        
        return docs
    finally:
        cur.close()
        conn.close()


def load_pending_attributes(loan_id: int) -> list[dict]:
    """Load all attributes that don't have calculation steps yet"""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT fa.id, fa.attribute_label, fa.section, ed.extracted_value
            FROM extracted_1008_data ed
            JOIN form_1008_attributes fa ON fa.id = ed.attribute_id
            WHERE ed.loan_id = %s
            AND ed.extracted_value IS NOT NULL
            AND TRIM(ed.extracted_value::text) != ''
            AND NOT EXISTS (
                SELECT 1 FROM calculation_steps cs WHERE cs.loan_id = %s AND cs.attribute_id = fa.id
            )
            ORDER BY fa.display_order
        """, (loan_id, loan_id))
        
        results = []
        for r in cur.fetchall():
            # Include section in the label for context
            full_label = f"{r['section']} > {r['attribute_label']}" if r['section'] else r['attribute_label']
            results.append({
                'id': r['id'],
                'attribute_label': r['attribute_label'],
                'full_context': full_label,
                'extracted_value': r['extracted_value']
            })
        return results
    finally:
        cur.close()
        conn.close()


def generate_batch_evidence(loan_id: int, model: str = "claude-opus-4-5"):
    """Generate evidence for ALL pending attributes in ONE call"""
    
    # Load data
    docs = load_financial_documents(loan_id)
    attrs = load_pending_attributes(loan_id)
    
    print(f"📄 Loaded {len(docs)} FINANCIAL documents")
    print(f"📋 Processing {len(attrs)} attributes in ONE call")
    
    if not attrs:
        print("✅ All attributes already have evidence!")
        return
    
    # Build prompt
    prompt = f"""You are MODDA, a mortgage document verification system.

# TASK
Generate evidence for ALL {len(attrs)} attributes below. For EACH attribute, find the value in the documents and cite the source.

# ATTRIBUTES TO VERIFY
Each attribute has:
- id: Database ID
- attribute_label: Short name
- full_context: Full path showing which section of the 1008 form this belongs to
- extracted_value: The value we need to verify

{json.dumps(attrs, indent=2)}

# DOCUMENT EVIDENCE
{json.dumps(docs, indent=2)}

# DOCUMENT PRIORITY (Use in this order - higher = more authoritative)
1. **GOLDEN SOURCES** (use first if available):
   - promissory_note / note_2nd_lien - For loan terms, interest rate, loan amount, payment amounts
   - mortgage_loan_statement - For P&I breakdown, existing mortgage payments
   - credit_report - For existing debts, credit score, payment history
   - tax_workup_sheet - For property taxes
   - hazard_insurance / flood_policy - For insurance amounts
   - w_9 / 4506 - For borrower identity verification

2. **INCOME SOURCES** (REQUIRED for any income/employment attributes):
   - pay_stubs / paystub - For current income, gross pay, YTD earnings
   - w2 - For annual wages
   - tax_returns / 1040 / 1099 - For self-employment or other income
   - verbal_verification_of_employment / voe - For employment confirmation
   - **Income Summary Report** (may be in miscellaneous_docs) - Shows calculation methodology for bonus/variable income!
   
   **INCOME VERIFICATION RULE**: For monthly income amounts, if you find:
   - Per-period pay × pay frequency (bi-weekly×26/12, semi-monthly×2, monthly×1) produces a value within 5% of expected, OR
   - YTD earnings annualized produces a value within 5% of expected, OR
   - W-2 annual wages / 12 produces a value within 5% of expected
   Then mark as VERIFIED. Small differences are due to underwriting calculation methodology (rounding, averaging, bonus allocation), NOT missing evidence.

3. **SECONDARY SOURCES** (use if golden source not available):
   - avm_report / appraisal - For property value
   - title_policy - For property ownership

4. **BANNED SOURCES** (NEVER use these for evidence):
   - rate_lock_confirmation - Preliminary/conditional document
   - loan_estimate - Preliminary estimates
   - closing_disclosure - Summary document, not authoritative
   - first_payment_letter - Derived from other sources
   
   NOTE: Some miscellaneous_docs contain important reports like "Income Summary Report" - check content before dismissing!

# RULES
1. For EACH attribute, find the value in ONE document (prefer GOLDEN SOURCE)
2. For AMOUNT fields (dollar values): May need multiple steps showing calculation
3. For NON-AMOUNT fields (text, boolean, names): Just ONE step with ONE document reference
4. Cite document_name and page_number where you found it
5. NEVER cite URLA or 1008 as evidence (that's what we're verifying!)
6. NEVER use rate_lock_confirmation or loan_estimate as evidence (these are preliminary/conditional documents)
7. Keep descriptions SHORT (<50 chars)

# VERIFICATION LOGIC (CRITICAL!)
- verified: true → If you FOUND the NUMERICAL VALUE in a document (even if label differs)
- verified: false → ONLY if:
  a) Value NOT FOUND in any document, OR
  b) Numerical value is DIFFERENT (e.g., expected $100 but found $95)
- DO NOT mark as "not verified" just because the label/description differs!
- Example: Expected "Positive Cash Flow = $194,882" and found "HELOC Balance = $194,882" → verified: TRUE (numbers match)

# OUTPUT FORMAT
Return a JSON object with this structure:
{{
  "results": [
    {{
      "attribute_id": <id>,
      "attribute_label": "<name>",
      "expected_value": "<the value from attribute>",
      "verified": true/false,
      "mismatch_reason": "<ONLY if verified=false: explain what's different or missing>",
      "calculation_steps": [
        {{
          "step_order": 1,
          "value": "<value found in document>",
          "description": "<what this value represents>",
          "rationale": "<why this document is authoritative>",
          "document_name": "<exact filename.pdf>",
          "page_number": <integer page number>
        }}
      ]
    }}
  ]
}}

IMPORTANT:
- verified: true if numerical value matches (ignore semantic label differences)
- verified: false ONLY if value not found or numerical mismatch
- For text/boolean fields: Return exactly 1 calculation_step
- For amount fields: Return multiple steps if it's a sum/calculation
- document_name MUST be exact filename (e.g., "note_2nd_lien_54.pdf")
- page_number MUST be an integer (e.g., 1, 2, 3)

Generate evidence for ALL {len(attrs)} attributes now."""

    prompt_tokens = len(prompt) // 4
    print(f"📊 Prompt: {len(prompt):,} chars (~{prompt_tokens:,} tokens)")
    
    # Call Claude
    print(f"🤖 Calling Claude ({model}) for ALL attributes...")
    
    try:
        response = call_bedrock(
            prompt=prompt,
            model=model,
            max_tokens=30000,  # Need more output for batch
            temperature=0.0
        )
        
        # Save raw response
        debug_dir = '/Users/sunny/Applications/bts/jpmorgan/mortgage/modda/outputs/systematic_evidence'
        os.makedirs(debug_dir, exist_ok=True)
        debug_file = f'{debug_dir}/batch_response_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt'
        with open(debug_file, 'w') as f:
            f.write(response)
        print(f"💾 Saved raw response to: {debug_file}")
        
        # Parse response
        # Find JSON in response
        start = response.find('{')
        end = response.rfind('}') + 1
        if start >= 0 and end > start:
            json_str = response[start:end]
            result = json.loads(json_str)
        else:
            print("❌ No JSON found in response")
            return
        
        # Save to database
        results = result.get('results', [])
        print(f"✅ Got evidence for {len(results)} attributes")
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        saved_count = 0
        verified_count = 0
        not_verified_count = 0
        
        for attr_result in results:
            attr_id = attr_result.get('attribute_id')
            steps = attr_result.get('calculation_steps', [])
            is_verified = attr_result.get('verified', True)
            mismatch_reason = attr_result.get('mismatch_reason', '')
            
            if is_verified:
                verified_count += 1
            else:
                not_verified_count += 1
            
            for step in steps:
                cur.execute("""
                    INSERT INTO calculation_steps 
                    (loan_id, attribute_id, step_order, value, description, rationale, document_name, page_number)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    loan_id,
                    attr_id,
                    step.get('step_order', 1),
                    step.get('value'),
                    step.get('description'),
                    step.get('rationale'),
                    step.get('document_name'),
                    step.get('page_number')
                ))
                saved_count += 1
            
            # Add evidence_file entry with verification status
            if steps:
                first_step = steps[0]
                doc_name = first_step.get('document_name')
                if doc_name:
                    # Get file_path
                    cur.execute("""
                        SELECT file_path FROM document_analysis 
                        WHERE loan_id = %s AND filename = %s
                    """, (loan_id, doc_name))
                    da = cur.fetchone()
                    file_path = da['file_path'] if da else f"documents/loan_1642451/{doc_name}"
                    
                    # Build notes JSON
                    notes = {
                        'verified': is_verified,
                        'mismatch_reason': mismatch_reason if not is_verified else None
                    }
                    
                    cur.execute("""
                        INSERT INTO evidence_files 
                        (loan_id, attribute_id, file_name, file_path, page_number, 
                         verification_status, notes, uploaded_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                        ON CONFLICT DO NOTHING
                    """, (
                        loan_id, attr_id, doc_name, file_path,
                        first_step.get('page_number'),
                        'verified' if is_verified else 'not_verified',
                        json.dumps(notes)
                    ))
        
        conn.commit()
        cur.close()
        conn.close()
        
        print(f"\n✅ BATCH COMPLETE!")
        print(f"   Calculation steps saved: {saved_count}")
        print(f"   ✅ Verified: {verified_count}")
        print(f"   ❌ Not Verified: {not_verified_count}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    import sys
    loan_id = None
    
    if len(sys.argv) > 1:
        loan_id = int(sys.argv[1])
    else:
        # Get default loan ID
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id FROM loans WHERE loan_number = '1642451'")
        res = cur.fetchone()
        if res:
            loan_id = res['id']
        cur.close()
        conn.close()

    if loan_id:
        print(f"🚀 BATCH EVIDENCE GENERATOR")
        print(f"=" * 60)
        print(f"Loan ID: {loan_id}")
        print(f"=" * 60)
        
        generate_batch_evidence(loan_id, model="claude-opus-4-5")

