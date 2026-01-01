#!/usr/bin/env python3
"""
Reusable Verification Script - Run evidence verification for any loan
Usage: python run_verification.py <loan_id>
"""

import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import get_db_connection
from vlm_utils import VLMClient

# Attribute type definitions
ATTRIBUTE_DEFINITIONS = {
    # Ratios
    "Total Obligations/Income": "RATIO: Total Monthly Obligations ÷ Borrower Total Income × 100",
    "Primary Housing Expense/Income": "RATIO: Primary Housing Expense ÷ Borrower Total Income × 100",
    "Qualifying Ratios Primary House Expense To Income": "RATIO: Housing expense ÷ income × 100",
    "Qualifying Ratios Total Obligations To Income": "RATIO: Total obligations ÷ income × 100",
    "CLTV/TLTV": "RATIO: Combined Loan-to-Value ratio",
    "HCLTV/HTLTV": "RATIO: High Combined Loan-to-Value ratio",
    "LTV": "RATIO: Loan-to-Value ratio",
    
    # Income fields
    "Total Income": "Monthly income amount",
    "Total Base Income": "Monthly base income amount",
    "Borrower Base Income": "Monthly base income for borrower",
    "Borrower Total Income": "Monthly total income for borrower",
    "Combined Base Income Amount": "Combined monthly base income",
    "Combined Total Income Amount": "Combined monthly total income",
    "Borrower Total Income Amount": "Monthly total income for borrower",
    
    # Housing expense components
    "First Mortgage P&I": "Monthly Principal and Interest for first mortgage",
    "Monthly Principal and Interest Payment": "Monthly P&I payment amount",
    "Loan Initial P And I Payment": "Initial monthly P&I payment",
    "Hazard Insurance": "Monthly hazard insurance amount",
    "Proposed Monthly Hazard Insurance Amount": "Proposed monthly hazard insurance",
    "Total Primary Housing Expense": "Total monthly primary housing expense",
    "Proposed Monthly Total Primary Housing Expense Amount": "Total proposed monthly housing expense",
    "Total All Monthly Payments": "Total of all monthly payment obligations",
    "Taxes": "Monthly property taxes",
    "Mortgage Insurance": "Monthly mortgage insurance",
    
    # Other common fields
    "Underwriter's Name": "Name of the loan underwriter",
    "Required": "Funds required to close",
    "Borrower Funds To Close Required": "Funds borrower needs to close",
    "Borrower Name": "Full name of the borrower",
    "Property Address": "Address of the property",
    "Loan Amount": "Total loan amount",
    "Interest Rate": "Interest rate on the loan",
    "Loan Term": "Term of the loan in months/years",
}


def load_attributes_to_verify(loan_id):
    """Load all extracted 1008 attributes for a loan"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT fa.id, fa.attribute_label, ed.extracted_value
        FROM extracted_1008_data ed
        JOIN form_1008_attributes fa ON fa.id = ed.attribute_id
        WHERE ed.loan_id = %s AND ed.extracted_value IS NOT NULL
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
    """Load source documents for evidence"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Priority document patterns
    priority_patterns = [
        'mortgage_loan_statement',
        'closing_disclosure',
        'hazard_insurance_info',
        'promissory_note',
        'credit_report',
        'appraisal',
    ]
    
    docs = {}
    
    # Get priority documents first
    for pattern in priority_patterns:
        cur.execute("""
            SELECT filename, individual_analysis 
            FROM document_analysis 
            WHERE loan_id = %s AND filename LIKE %s
            AND individual_analysis IS NOT NULL
            AND filename NOT LIKE '%%preliminary%%'
            LIMIT 2
        """, (loan_id, f'%{pattern}%'))
        
        for row in cur.fetchall():
            if row['individual_analysis']:
                docs[row['filename']] = json.dumps(row['individual_analysis'])[:5000]
    
    # Get other financial documents
    cur.execute("""
        SELECT filename, individual_analysis 
        FROM document_analysis 
        WHERE loan_id = %s 
        AND filename NOT LIKE '%%1008%%'
        AND filename NOT LIKE '%%urla%%'
        AND filename NOT LIKE '%%lender_loan_information%%'
        AND filename NOT LIKE '%%tax_returns%%'
        AND filename NOT LIKE '%%preliminary%%'
        AND individual_analysis IS NOT NULL
        LIMIT 30
    """, (loan_id,))
    
    for row in cur.fetchall():
        if row['filename'] not in docs and row['individual_analysis']:
            docs[row['filename']] = json.dumps(row['individual_analysis'])[:2000]
    
    cur.close()
    conn.close()
    return docs


def build_verification_prompt(attrs, source_docs):
    """Build the verification prompt for Claude"""
    
    prompt = """You are verifying mortgage loan attributes from a 1008 Transmittal Summary.

## CRITICAL RULES:
1. ⚠️ NEVER USE 1008, URLA, or LENDER_LOAN_INFORMATION AS EVIDENCE
2. The 1008 summarizes a LOAN PACKAGE that may include MULTIPLE loans
3. Different source documents relate to different loans - identify which

## UNDERSTANDING THE LOAN PACKAGE:
- "First Mortgage P&I" = Principal + Interest for the PRIMARY mortgage
- "Second Mortgage P&I" = Principal + Interest for subordinate liens
- mortgage_loan_statement documents typically show FIRST mortgage details
- closing_disclosure shows loan terms - check loan amount/purpose to identify which loan

## SOURCE DOCUMENTS:
"""
    
    for doc_name, doc_json in source_docs.items():
        prompt += f"\n### {doc_name}\n{doc_json}\n"

    prompt += "\n## ATTRIBUTES TO VERIFY:\n"
    
    for attr in attrs:
        if attr['expected'] and str(attr['expected']).strip().lower() != 'none':
            prompt += f"""
### {attr['label']} (ID: {attr['id']})
- Expected Value: {attr['expected']}
- Definition: {attr['definition']}
"""

    prompt += """

## VERIFICATION RULES:
1. Find the value in source documents
2. For P&I: Find Principal + Interest in mortgage statement or closing disclosure
3. For Insurance: Find in hazard_insurance docs, divide annual by 12
4. For Ratios: Calculate numerator ÷ denominator × 100
5. If value not found in docs → verified: false
6. Small rounding differences ($0.01-$1.00) are acceptable

## OUTPUT FORMAT (JSON):
```json
{
  "verifications": [
    {
      "attribute_id": 123,
      "attribute_label": "Field Name",
      "verified": true,
      "calculation_steps": [
        {
          "step_order": 1,
          "description": "Found in document",
          "value": "$1,234.56",
          "document_name": "closing_disclosure_1.pdf",
          "page_number": 1
        }
      ],
      "mismatch_reason": null
    }
  ]
}
```

Verify ALL attributes. NO 1008 CITATIONS!"""

    return prompt


def save_verification_results(loan_id, verifications):
    """Save verification results to database"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    for v in verifications:
        attr_id = v['attribute_id']
        verified = v.get('verified', False)
        steps = v.get('calculation_steps', [])
        reason = v.get('mismatch_reason')
        
        # Delete existing data
        cur.execute("DELETE FROM calculation_steps WHERE loan_id = %s AND attribute_id = %s", 
                   (loan_id, attr_id))
        cur.execute("DELETE FROM evidence_files WHERE loan_id = %s AND attribute_id = %s",
                   (loan_id, attr_id))
        
        # Insert calculation steps
        for step in steps:
            cur.execute("""
                INSERT INTO calculation_steps (loan_id, attribute_id, step_order, description, value, document_name, page_number)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (loan_id, attr_id, step.get('step_order', 1), step.get('description', ''), 
                  step.get('value', ''), step.get('document_name'), step.get('page_number')))
        
        # Insert evidence file
        doc_name = steps[0].get('document_name') if steps else None
        notes = {
            'verified': verified,
            'mismatch_reason': reason,
            'auto_generated': True
        }
        
        status = 'verified' if verified else 'not_verified'
        cur.execute("""
            INSERT INTO evidence_files (loan_id, attribute_id, file_name, file_path, verification_status, notes)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (loan_id, attr_id, doc_name or 'N/A', f'/documents/{doc_name}' if doc_name else '/N/A', 
              status, json.dumps(notes)))
        
        emoji = "✅" if verified else "❌"
        print(f"  {emoji} {v['attribute_label']}")
    
    conn.commit()
    cur.close()
    conn.close()


def run_verification(loan_id):
    """Main verification function"""
    print(f"🔄 RUNNING VERIFICATION FOR LOAN {loan_id}")
    print("=" * 50)
    
    # Load attributes
    print("\n📋 Loading attributes...")
    attrs = load_attributes_to_verify(loan_id)
    # Filter out None values
    attrs = [a for a in attrs if a['expected'] and str(a['expected']).strip().lower() != 'none']
    print(f"   Found {len(attrs)} attributes with values")
    
    if not attrs:
        print("❌ No attributes to verify!")
        return
    
    # Load documents
    print("\n📄 Loading source documents...")
    source_docs = load_source_documents(loan_id)
    print(f"   Loaded {len(source_docs)} documents")
    for doc in list(source_docs.keys())[:5]:
        print(f"      - {doc}")
    
    if not source_docs:
        print("❌ No source documents found!")
        return
    
    # Build prompt
    print("\n🤖 Sending to Claude Opus 4.5...")
    prompt = build_verification_prompt(attrs, source_docs)
    print(f"   Prompt length: {len(prompt)} chars")
    
    # Call Claude
    client = VLMClient(model="claude-opus-4-5", max_tokens=8000)
    response = client.process_text("", prompt)
    
    # Parse response
    print("\n📝 Parsing response...")
    try:
        if isinstance(response, dict):
            result = response
        elif isinstance(response, str):
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                result = json.loads(response[json_start:json_end])
            else:
                print("❌ Could not find JSON in response")
                return
        else:
            print(f"❌ Unexpected response type: {type(response)}")
            return
            
        verifications = result.get('verifications', [])
        print(f"   Found {len(verifications)} verifications")
        
        # Save results
        print("\n💾 Saving to database...")
        save_verification_results(loan_id, verifications)
        
        verified_count = sum(1 for v in verifications if v.get('verified'))
        print(f"\n✅ COMPLETE: {verified_count}/{len(verifications)} verified")
        
    except json.JSONDecodeError as e:
        print(f"❌ JSON parse error: {e}")
        print(str(response)[:2000] if response else "Empty response")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python run_verification.py <loan_id>")
        sys.exit(1)
    
    loan_id = int(sys.argv[1])
    run_verification(loan_id)




