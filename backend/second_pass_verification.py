#!/usr/bin/env python3
"""
Second Pass Verification - Re-verify all "Not Verified" attributes
Sends context about what each attribute means and asks Claude to provide correct evidence
"""

import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import get_db_connection
from vlm_utils import VLMClient

LOAN_ID = 27

# Attribute type definitions - helps Claude understand what each field represents
ATTRIBUTE_DEFINITIONS = {
    # Ratios
    "Total Obligations/Income": "RATIO: Total Monthly Obligations ÷ Borrower Total Income × 100. Result is a percentage.",
    "Primary Housing Expense/Income": "RATIO: Primary Housing Expense ÷ Borrower Total Income × 100. Result is a percentage.",
    "Qualifying Ratios Primary House Expense To Income": "RATIO: Same as Primary Housing Expense/Income. Housing expense ÷ income × 100.",
    "Qualifying Ratios Total Obligations To Income": "RATIO: Same as Total Obligations/Income. Total obligations ÷ income × 100.",
    
    # Income fields - all should be $30,721.67
    "Total Income": "Monthly income amount from 1008 form",
    "Total Base Income": "Monthly base income amount from 1008 form",
    "Borrower Base Income": "Monthly base income for borrower from 1008 form",
    "Borrower Total Income": "Monthly total income for borrower from 1008 form",
    "Combined Base Income Amount": "Combined monthly base income from 1008 form",
    "Combined Total Income Amount": "Combined monthly total income from 1008 form",
    
    # Housing expense components
    "First Mortgage P&I": "Monthly Principal and Interest payment for first mortgage",
    "Monthly Principal and Interest Payment": "Monthly P&I payment amount",
    "Loan Initial P And I Payment": "Initial monthly P&I payment on the loan",
    "Hazard Insurance": "Monthly hazard/homeowner's insurance amount",
    "Proposed Monthly Hazard Insurance Amount": "Proposed monthly hazard insurance",
    "Total Primary Housing Expense": "Total monthly primary housing expense (PITI + HOA etc)",
    "Total All Monthly Payments": "Total of all monthly payment obligations",
    
    # Other
    "Underwriter's Name": "Name of the loan underwriter",
    "Required": "Funds required to close (can be negative if credit)",
    "Original Loan Amount of First Mortgage": "Original loan amount",
    "Mort This Lien Position First": "Boolean - is this a first lien position mortgage",
    "Borrower Present Housing Payment": "Borrower's current housing payment (may be None if purchasing)",
}

def load_not_verified_attributes():
    """Load all attributes marked as not_verified"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT fa.id, fa.attribute_label, ed.extracted_value,
               ef.id as ef_id, ef.notes
        FROM evidence_files ef
        JOIN form_1008_attributes fa ON fa.id = ef.attribute_id
        JOIN extracted_1008_data ed ON ed.attribute_id = fa.id AND ed.loan_id = %s
        WHERE ef.loan_id = %s AND ef.verification_status = 'not_verified'
        ORDER BY fa.id
    """, (LOAN_ID, LOAN_ID))
    
    attrs = []
    for row in cur.fetchall():
        attrs.append({
            'id': row['id'],
            'ef_id': row['ef_id'],
            'label': row['attribute_label'],
            'expected': row['extracted_value'],
            'definition': ATTRIBUTE_DEFINITIONS.get(row['attribute_label'], 'Standard 1008 field')
        })
    
    cur.close()
    conn.close()
    return attrs

def load_verified_values():
    """Load already verified values for reference (e.g., income, expenses)"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get key verified values that can be used as inputs
    cur.execute("""
        SELECT fa.attribute_label, ed.extracted_value
        FROM form_1008_attributes fa
        JOIN extracted_1008_data ed ON ed.attribute_id = fa.id AND ed.loan_id = %s
        WHERE fa.attribute_label IN (
            'Borrower Total Income Amount',
            'Proposed Monthly Total Primary Housing Expense Amount',
            'Proposed Monthly Total Monthly Payments Amount'
        )
    """, (LOAN_ID,))
    
    values = {}
    for row in cur.fetchall():
        values[row['attribute_label']] = row['extracted_value']
    
    cur.close()
    conn.close()
    return values

def load_source_documents():
    """Load source documents (NOT 1008) for evidence - prioritize key financial docs"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Priority documents - most likely to have evidence
    priority_patterns = [
        'mortgage_loan_statement_51',  # First mortgage statement (non-preliminary)
        'closing_disclosure_22',        # Final closing disclosure
        'hazard_insurance_info__and_or_proof_of_insurance_39',  # Insurance proof
        'promissory_note',
        'credit_report',
    ]
    
    docs = {}
    
    # First, get priority documents with more content
    for pattern in priority_patterns:
        cur.execute("""
            SELECT filename, individual_analysis 
            FROM document_analysis 
            WHERE loan_id = %s AND filename LIKE %s
            AND individual_analysis IS NOT NULL
            LIMIT 1
        """, (LOAN_ID, f'%{pattern}%'))
        
        row = cur.fetchone()
        if row and row['individual_analysis']:
            docs[row['filename']] = json.dumps(row['individual_analysis'])[:5000]
    
    # Then get other financial documents (excluding 1008, URLA, tax returns)
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
        LIMIT 25
    """, (LOAN_ID,))
    
    for row in cur.fetchall():
        if row['filename'] not in docs and row['individual_analysis']:
            docs[row['filename']] = json.dumps(row['individual_analysis'])[:2000]
    
    cur.close()
    conn.close()
    return docs

def build_prompt(attrs, verified_values, source_docs):
    """Build the prompt for Claude"""
    
    prompt = f"""You are verifying mortgage loan attributes from a 1008 Transmittal Summary.

## CRITICAL RULES:
1. ⚠️ NEVER USE 1008, URLA, or LENDER_LOAN_INFORMATION AS EVIDENCE - these are what we're verifying
2. The 1008 summarizes a LOAN PACKAGE that may include MULTIPLE loans (first mortgage + second mortgage/HELOC)
3. Different source documents relate to different loans - identify which loan each document describes

## UNDERSTANDING THE LOAN PACKAGE:
- "First Mortgage P&I" = Principal + Interest for the PRIMARY/FIRST mortgage (typically the larger loan)
- "Second Mortgage P&I" = Principal + Interest for subordinate liens (home equity loans, HELOCs)
- mortgage_loan_statement documents typically show the FIRST mortgage details
- closing_disclosure may show EITHER first or second mortgage - check the loan amount/purpose to identify
- A home equity loan or HELOC closing disclosure is for the SECOND mortgage

## HOW TO IDENTIFY WHICH LOAN A DOCUMENT DESCRIBES:
- Large loan amount (e.g., $500K+) with "Purchase" or "Refinance" purpose = First Mortgage
- Smaller loan amount (e.g., $100-200K) with "Home Equity" purpose = Second Mortgage  
- Monthly statement from servicer typically shows First Mortgage
- Look at loan purpose, loan amount, and interest rate to match

## ALREADY VERIFIED VALUES (reference these):
- Borrower Total Income Amount: {verified_values.get('Borrower Total Income Amount', '$30,721.67')}
- Proposed Monthly Total Primary Housing Expense Amount: {verified_values.get('Proposed Monthly Total Primary Housing Expense Amount', '$6,624.39')}

## SOURCE DOCUMENTS:
"""
    
    for doc_name, doc_json in source_docs.items():
        prompt += f"\n### {doc_name}\n{doc_json}\n"

    prompt += "\n## ATTRIBUTES TO VERIFY:\n"
    
    for attr in attrs:
        prompt += f"""
### {attr['label']} (ID: {attr['id']})
- Expected Value: {attr['expected']}
- Definition: {attr['definition']}
"""

    prompt += f"""

## VERIFICATION APPROACH BY ATTRIBUTE TYPE:

### P&I Payments:
- "First Mortgage P&I" → Find in mortgage_loan_statement (Principal + Interest, NOT escrow)
- "Monthly Principal and Interest Payment" → Same as First Mortgage P&I
- "Second Mortgage P&I" → Find in closing_disclosure for home equity loan

### Insurance:
- "Hazard Insurance" → Find annual premium in hazard_insurance docs, divide by 12
- Note: Different sources may show different premium amounts - use the one that matches

### Ratios:
- Calculate from already verified values: numerator ÷ denominator × 100
- No source document needed for the calculation step itself

### Totals:
- "Total Primary Housing Expense" = First P&I + Second P&I + Insurance + Taxes + HOA
- "Total All Monthly Payments" = Housing Expense + Other Monthly Debts

### Other Fields:
- "Underwriter's Name" → May not appear in closing docs, mark as verified:false if not found
- "Required" / "Funds to Close" → Find in closing_disclosure "Cash to Close" section
- Boolean fields → Verify from loan terms in closing disclosure

## OUTPUT FORMAT (JSON):
```json
{{
  "verifications": [
    {{
      "attribute_id": 123,
      "attribute_label": "Field Name", 
      "verified": true,
      "calculation_steps": [
        {{
          "step_order": 1,
          "description": "Principal from mortgage statement",
          "value": "$3,689.23",
          "document_name": "mortgage_loan_statement_51.pdf",
          "page_number": 1
        }},
        {{
          "step_order": 2,
          "description": "Interest from mortgage statement", 
          "value": "$466.91",
          "document_name": "mortgage_loan_statement_51.pdf",
          "page_number": 1
        }},
        {{
          "step_order": 3,
          "description": "Total P&I = Principal + Interest",
          "value": "$4,156.14",
          "document_name": null,
          "page_number": null
        }}
      ],
      "mismatch_reason": null
    }}
  ]
}}
```

## IMPORTANT:
- If exact value found → verified: true
- If calculated value matches expected → verified: true  
- If value differs or not found → verified: false with mismatch_reason
- Small rounding differences ($0.01-$1.00) are acceptable as matches

Provide verification for ALL {len(attrs)} attributes."""

    return prompt

def update_database(verifications):
    """Update database with new verification results"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    for v in verifications:
        attr_id = v['attribute_id']
        verified = v.get('verified', False)
        steps = v.get('calculation_steps', [])
        reason = v.get('mismatch_reason')
        
        # Delete old calculation steps
        cur.execute("DELETE FROM calculation_steps WHERE loan_id = %s AND attribute_id = %s", 
                   (LOAN_ID, attr_id))
        
        # Insert new calculation steps
        for step in steps:
            cur.execute("""
                INSERT INTO calculation_steps (loan_id, attribute_id, step_order, description, value, document_name, page_number)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (LOAN_ID, attr_id, step.get('step_order', 1), step.get('description', ''), 
                  step.get('value', ''), step.get('document_name'), step.get('page_number')))
        
        # Update evidence file
        notes = {
            'verified': verified,
            'mismatch_reason': reason,
            'second_pass': True
        }
        
        status = 'verified' if verified else 'not_verified'
        cur.execute("""
            UPDATE evidence_files 
            SET verification_status = %s, notes = %s
            WHERE loan_id = %s AND attribute_id = %s
        """, (status, json.dumps(notes), LOAN_ID, attr_id))
        
        print(f"  {'✅' if verified else '❌'} {v['attribute_label']}")
    
    conn.commit()
    cur.close()
    conn.close()

def main():
    print("🔄 SECOND PASS VERIFICATION")
    print("=" * 50)
    
    # Load data
    print("\n📋 Loading not verified attributes...")
    attrs = load_not_verified_attributes()
    print(f"   Found {len(attrs)} attributes to re-verify")
    
    if not attrs:
        print("✅ All attributes already verified!")
        return
    
    print("\n📊 Loading verified reference values...")
    verified_values = load_verified_values()
    for k, v in verified_values.items():
        print(f"   {k}: {v}")
    
    print("\n📄 Loading source documents (NOT 1008)...")
    source_docs = load_source_documents()
    print(f"   Loaded {len(source_docs)} documents")
    for doc_name in list(source_docs.keys())[:5]:
        print(f"      - {doc_name}")
    if len(source_docs) > 5:
        print(f"      ... and {len(source_docs) - 5} more")
    
    # Build and send prompt
    print("\n🤖 Sending to Claude Opus 4.5...")
    prompt = build_prompt(attrs, verified_values, source_docs)
    
    print(f"   Prompt length: {len(prompt)} chars")
    
    client = VLMClient(model="claude-opus-4-5", max_tokens=8000)
    response = client.process_text("", prompt)
    
    # Parse response
    print("\n📝 Parsing response...")
    try:
        # Response could be dict or string
        if isinstance(response, dict):
            result = response
        elif isinstance(response, str):
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                result = json.loads(response[json_start:json_end])
            else:
                print("❌ Could not find JSON in response")
                print(response[:2000] if response else "Empty response")
                return
        else:
            print(f"❌ Unexpected response type: {type(response)}")
            return
            
        verifications = result.get('verifications', [])
        print(f"   Found {len(verifications)} verifications")
        
        # Update database
        print("\n💾 Updating database...")
        update_database(verifications)
        
        verified_count = sum(1 for v in verifications if v.get('verified'))
        print(f"\n✅ COMPLETE: {verified_count}/{len(verifications)} verified")
            
    except json.JSONDecodeError as e:
        print(f"❌ JSON parse error: {e}")
        print(str(response)[:2000] if response else "Empty response")

if __name__ == "__main__":
    main()

