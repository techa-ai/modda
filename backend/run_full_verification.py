#!/usr/bin/env python3
"""
Full Verification Pipeline - Run verification in batches with second pass
Usage: python run_full_verification.py <loan_id>
"""

import json
import sys
import os
import re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import get_db_connection
from vlm_utils import VLMClient

BATCH_SIZE = 40  # Process 40 attributes at a time

# Attribute type definitions
ATTRIBUTE_DEFINITIONS = {
    "Total Obligations/Income": "RATIO: Total Monthly Obligations ÷ Borrower Total Income × 100",
    "Primary Housing Expense/Income": "RATIO: Housing expense ÷ income × 100",
    "Qualifying Ratios Primary House Expense To Income": "RATIO: Housing expense ÷ income × 100",
    "Qualifying Ratios Total Obligations To Income": "RATIO: Total obligations ÷ income × 100",
    "CLTV/TLTV": "RATIO: Combined Loan-to-Value ratio",
    "LTV": "RATIO: Loan-to-Value ratio",
    "First Mortgage P&I": "Monthly Principal and Interest for first mortgage",
    "Monthly Principal and Interest Payment": "Monthly P&I payment amount",
    "Hazard Insurance": "Monthly hazard insurance amount",
    "Total Primary Housing Expense": "Total monthly primary housing expense",
    "Borrower Total Income Amount": "Monthly total income for borrower",
}


def load_all_attributes(loan_id):
    """Load all extracted 1008 attributes for a loan"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT fa.id, fa.attribute_label, ed.extracted_value
        FROM extracted_1008_data ed
        JOIN form_1008_attributes fa ON fa.id = ed.attribute_id
        WHERE ed.loan_id = %s AND ed.extracted_value IS NOT NULL 
        AND ed.extracted_value != 'None' AND TRIM(ed.extracted_value) != ''
        ORDER BY fa.id
    """, (loan_id,))
    
    attrs = []
    for row in cur.fetchall():
        attrs.append({
            'id': row['id'],
            'label': row['attribute_label'],
            'expected': row['extracted_value'],
            'definition': ATTRIBUTE_DEFINITIONS.get(row['attribute_label'], 'Standard 1008 field')
        })
    
    cur.close()
    conn.close()
    return attrs


def load_source_documents(loan_id):
    """Load source documents - FINANCIAL tagged + key document types"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    docs = {}
    
    # Key document patterns to ALWAYS include (regardless of FINANCIAL tag)
    key_patterns = [
        'closing_disclosure', 'mortgage_loan_statement', 'promissory_note',
        'hazard_insurance', 'credit_report', 'settlement_statement',
        'rate_lock', 'appraisal', 'verification_of_employment', 'pay_stub',
        'w_2', 'tax_return', 'bank_statement'
    ]
    
    # First, get all FINANCIAL tagged docs
    cur.execute("""
        SELECT filename, individual_analysis 
        FROM document_analysis 
        WHERE loan_id = %s 
        AND filename NOT LIKE '%%1008%%'
        AND filename NOT LIKE '%%urla%%'
        AND filename NOT LIKE '%%lender_loan_information%%'
        AND individual_analysis IS NOT NULL
        AND version_metadata->>'financial_category' = 'FINANCIAL'
    """, (loan_id,))
    
    for row in cur.fetchall():
        if row['individual_analysis']:
            docs[row['filename']] = json.dumps(row['individual_analysis'])
    
    # Then, add key document types that might be missing
    for pattern in key_patterns:
        cur.execute("""
            SELECT filename, individual_analysis 
            FROM document_analysis 
            WHERE loan_id = %s 
            AND filename LIKE %s
            AND filename NOT LIKE '%%1008%%'
            AND filename NOT LIKE '%%urla%%'
            AND filename NOT LIKE '%%lender_loan_information%%'
            AND filename NOT LIKE '%%preliminary%%'
            AND individual_analysis IS NOT NULL
            LIMIT 2
        """, (loan_id, f'%{pattern}%'))
        
        for row in cur.fetchall():
            if row['filename'] not in docs and row['individual_analysis']:
                docs[row['filename']] = json.dumps(row['individual_analysis'])
    
    cur.close()
    conn.close()
    
    print(f"   Total documents loaded: {len(docs)}")
    total_chars = sum(len(v) for v in docs.values())
    print(f"   Total JSON size: {total_chars:,} chars (~{total_chars//4:,} tokens)")
    
    return docs


def build_batch_prompt(attrs, source_docs):
    """Build prompt for a batch of attributes - sends ALL docs, batches only attributes"""
    prompt = """You are verifying mortgage loan attributes from a 1008 Transmittal Summary.

## CRITICAL RULES:
1. ⚠️ NEVER USE 1008, URLA, or LENDER_LOAN_INFORMATION AS EVIDENCE - these are what we verify
2. Find values in SOURCE documents below only
3. For P&I: Find Principal + Interest in mortgage_loan_statement
4. For Insurance: Find annual premium in hazard_insurance docs, divide by 12
5. For Ratios: Calculate numerator ÷ denominator × 100
6. Small rounding differences ($0.01-$1.00) are acceptable as matches
7. If value not found → verified: false with mismatch_reason

## ALL SOURCE DOCUMENTS (deep extracted JSON):
"""
    # Include ALL documents - no truncation
    for doc_name, doc_json in source_docs.items():
        prompt += f"\n### {doc_name}\n{doc_json}\n"

    prompt += "\n## ATTRIBUTES TO VERIFY IN THIS BATCH:\n"
    for attr in attrs:
        prompt += f"- {attr['label']} (ID:{attr['id']}): Expected = {attr['expected']}\n"

    prompt += """

## OUTPUT FORMAT (JSON):
```json
{
  "verifications": [
    {
      "attribute_id": 123,
      "attribute_label": "Field Name",
      "verified": true,
      "calculation_steps": [
        {"step_order": 1, "description": "Short desc", "value": "$100", "document_name": "doc.pdf", "page_number": 1}
      ],
      "mismatch_reason": null
    }
  ]
}
```

IMPORTANT:
- Keep descriptions SHORT (under 50 chars)
- Verify ALL """ + str(len(attrs)) + """ attributes in this batch
- Return complete JSON - do not truncate"""
    return prompt


def salvage_json(text):
    """Try to salvage partial JSON"""
    # Find all complete verification objects
    verifications = []
    pattern = r'\{\s*"attribute_id":\s*(\d+)[^}]+?"verified":\s*(true|false)[^}]*\}'
    
    for match in re.finditer(pattern, text, re.DOTALL):
        try:
            # Try to extract and parse each verification
            start = match.start()
            # Find the end of this object (matching closing brace)
            depth = 0
            end = start
            for i, c in enumerate(text[start:], start):
                if c == '{':
                    depth += 1
                elif c == '}':
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            
            obj_str = text[start:end]
            # Clean up common issues
            obj_str = re.sub(r',\s*}', '}', obj_str)
            obj_str = re.sub(r',\s*]', ']', obj_str)
            
            obj = json.loads(obj_str)
            verifications.append(obj)
        except:
            continue
    
    return verifications


def save_results(loan_id, verifications):
    """Save verification results"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    verified = 0
    not_verified = 0
    
    for v in verifications:
        attr_id = v.get('attribute_id')
        if not attr_id:
            continue
            
        is_verified = v.get('verified', False)
        steps = v.get('calculation_steps', [])
        reason = v.get('mismatch_reason')
        
        # Delete existing
        cur.execute("DELETE FROM calculation_steps WHERE loan_id = %s AND attribute_id = %s", (loan_id, attr_id))
        cur.execute("DELETE FROM evidence_files WHERE loan_id = %s AND attribute_id = %s", (loan_id, attr_id))
        
        # Insert steps
        for step in steps:
            if isinstance(step, dict):
                cur.execute("""
                    INSERT INTO calculation_steps (loan_id, attribute_id, step_order, description, value, document_name, page_number)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (loan_id, attr_id, step.get('step_order', 1), str(step.get('description', ''))[:200], 
                      step.get('value', ''), step.get('document_name'), step.get('page_number')))
        
        # Insert evidence file
        doc_name = None
        if steps and isinstance(steps[0], dict):
            doc_name = steps[0].get('document_name')
            
        notes = {'verified': is_verified, 'mismatch_reason': reason}
        status = 'verified' if is_verified else 'not_verified'
        
        cur.execute("""
            INSERT INTO evidence_files (loan_id, attribute_id, file_name, file_path, verification_status, notes)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (loan_id, attr_id, doc_name or 'N/A', f'/documents/{doc_name}' if doc_name else '/N/A', 
              status, json.dumps(notes)))
        
        if is_verified:
            verified += 1
        else:
            not_verified += 1
    
    conn.commit()
    cur.close()
    conn.close()
    
    return verified, not_verified


def run_verification(loan_id):
    """Main verification pipeline"""
    print(f"🔄 FULL VERIFICATION FOR LOAN {loan_id}")
    print("=" * 60)
    
    # Load data
    print("\n📋 Loading attributes...")
    all_attrs = load_all_attributes(loan_id)
    print(f"   Found {len(all_attrs)} attributes with values")
    
    print("\n📄 Loading source documents...")
    source_docs = load_source_documents(loan_id)
    print(f"   Loaded {len(source_docs)} documents")
    
    # Process in batches - batch only OUTPUT (attributes), INPUT (docs) stays full
    total_verified = 0
    total_not_verified = 0
    client = VLMClient(model="claude-opus-4-5", max_tokens=16000)
    
    batches = [all_attrs[i:i+BATCH_SIZE] for i in range(0, len(all_attrs), BATCH_SIZE)]
    print(f"\n🔄 Processing {len(batches)} batches...")
    
    for batch_num, batch in enumerate(batches, 1):
        print(f"\n   Batch {batch_num}/{len(batches)} ({len(batch)} attributes)...")
        
        prompt = build_batch_prompt(batch, source_docs)
        response = client.process_text("", prompt)
        
        # Parse response
        verifications = []
        if isinstance(response, dict):
            verifications = response.get('verifications', [])
        elif isinstance(response, str):
            try:
                json_start = response.find('{')
                json_end = response.rfind('}') + 1
                if json_start >= 0:
                    result = json.loads(response[json_start:json_end])
                    verifications = result.get('verifications', [])
            except json.JSONDecodeError:
                # Try salvage
                verifications = salvage_json(response)
                print(f"      Salvaged {len(verifications)} verifications")
        
        if verifications:
            v, nv = save_results(loan_id, verifications)
            total_verified += v
            total_not_verified += nv
            print(f"      ✅ {v} verified, ❌ {nv} not verified")
        else:
            print(f"      ⚠️ No verifications parsed")
    
    print(f"\n" + "=" * 60)
    print(f"📊 FIRST PASS COMPLETE:")
    print(f"   ✅ Verified: {total_verified}")
    print(f"   ❌ Not Verified: {total_not_verified}")
    
    # Second pass for not_verified
    if total_not_verified > 0:
        print(f"\n🔄 SECOND PASS - Re-verifying {total_not_verified} attributes...")
        run_second_pass(loan_id, source_docs, client)
    
    # Final summary
    print_final_summary(loan_id)


def run_second_pass(loan_id, source_docs, client):
    """Re-verify not_verified attributes with enhanced context"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get not verified
    cur.execute("""
        SELECT fa.id, fa.attribute_label, ed.extracted_value, ef.notes
        FROM evidence_files ef
        JOIN form_1008_attributes fa ON fa.id = ef.attribute_id
        JOIN extracted_1008_data ed ON ed.attribute_id = fa.id AND ed.loan_id = %s
        WHERE ef.loan_id = %s AND ef.verification_status = 'not_verified'
    """, (loan_id, loan_id))
    
    attrs = []
    for row in cur.fetchall():
        attrs.append({
            'id': row['id'],
            'label': row['attribute_label'],
            'expected': row['extracted_value'],
            'prior_reason': json.loads(row['notes']).get('mismatch_reason') if row['notes'] else None
        })
    
    cur.close()
    conn.close()
    
    if not attrs:
        return
    
    # Build enhanced prompt with ALL docs
    prompt = """SECOND PASS - Re-verify these attributes that failed first pass.

## RULES:
1. NEVER cite 1008/URLA as evidence
2. For P&I: Find Principal + Interest in mortgage statement
3. For ratios: Calculate from verified values
4. Accept small rounding differences ($0.01-$1.00)
5. Some fields (underwriter name, internal IDs) may not be in source docs - mark verified:false

## ALL SOURCE DOCUMENTS:
"""
    for doc_name, doc_json in source_docs.items():
        prompt += f"\n### {doc_name}\n{doc_json}\n"

    prompt += "\n## ATTRIBUTES TO RE-VERIFY:\n"
    for attr in attrs:
        prompt += f"- {attr['label']} (ID:{attr['id']}): Expected={attr['expected']}"
        if attr['prior_reason']:
            prompt += f" [Prior issue: {attr['prior_reason'][:50]}...]"
        prompt += "\n"

    prompt += """

## OUTPUT:
```json
{"verifications": [{"attribute_id": 123, "attribute_label": "Name", "verified": true/false,
  "calculation_steps": [...], "mismatch_reason": "reason if false"}]}
```"""

    response = client.process_text("", prompt)
    
    verifications = []
    if isinstance(response, dict):
        verifications = response.get('verifications', [])
    elif isinstance(response, str):
        try:
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start >= 0:
                result = json.loads(response[json_start:json_end])
                verifications = result.get('verifications', [])
        except:
            verifications = salvage_json(response)
    
    if verifications:
        v, nv = save_results(loan_id, verifications)
        print(f"   Second pass: ✅ {v} verified, ❌ {nv} still not verified")


def print_final_summary(loan_id):
    """Print final verification summary"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT verification_status, COUNT(*) as cnt
        FROM evidence_files WHERE loan_id = %s
        GROUP BY verification_status
    """, (loan_id,))
    
    print(f"\n" + "=" * 60)
    print(f"📊 FINAL VERIFICATION SUMMARY FOR LOAN {loan_id}:")
    
    for row in cur.fetchall():
        emoji = "✅" if row['verification_status'] == 'verified' else "❌"
        print(f"   {emoji} {row['verification_status']}: {row['cnt']}")
    
    # Show not verified details
    cur.execute("""
        SELECT fa.attribute_label, ed.extracted_value, ef.notes
        FROM evidence_files ef
        JOIN form_1008_attributes fa ON fa.id = ef.attribute_id
        JOIN extracted_1008_data ed ON ed.attribute_id = fa.id AND ed.loan_id = %s
        WHERE ef.loan_id = %s AND ef.verification_status = 'not_verified'
        LIMIT 10
    """, (loan_id, loan_id))
    
    remaining = cur.fetchall()
    if remaining:
        print(f"\n⚠️ NOT VERIFIED (showing first 10):")
        for row in remaining:
            notes = json.loads(row['notes']) if row['notes'] else {}
            reason = notes.get('mismatch_reason', 'Unknown')[:60]
            print(f"   • {row['attribute_label']}: {row['extracted_value']}")
            print(f"     → {reason}...")
    
    cur.close()
    conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python run_full_verification.py <loan_id>")
        sys.exit(1)
    
    loan_id = int(sys.argv[1])
    run_verification(loan_id)

