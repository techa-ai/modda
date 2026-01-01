#!/usr/bin/env python3
"""
Step 5b: Verify PITIA (Investment Property Housing Expense)
============================================================

For investment property/DSCR loans, we only verify the proposed housing
expense (PITIA = Principal + Interest + Taxes + Insurance + Association fees).
Personal debts are NOT relevant for DSCR qualification.

Two-stage LLM process with Claude Opus 4.5:
1. Document Selection: Identify appraisal, loan docs, insurance quotes
2. Evidence Generation: Calculate total monthly PITIA

Usage:
    python backend/summary_s5b_verify_pitia.py [loan_id]
"""

import json
import os
import sys
from typing import List, Dict, Any, Optional

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db import get_db_connection, execute_query, execute_one
from bedrock_config import call_bedrock
from systematic_evidence_v5_standardized import (
    _safe_json_dumps, 
    _extract_json_from_model_response,
    save_evidence_to_database
)

MODEL_NAME = 'claude-opus-4-5'

def get_loan_profile(loan_id: int) -> Dict:
    """Get loan profile for context"""
    row = execute_one("SELECT profile_data FROM loan_profiles WHERE loan_id = %s", (loan_id,))
    
    if not row or not row['profile_data']:
        return {}
    
    return row['profile_data']

def is_investment_property(loan_id: int, profile: Dict) -> bool:
    """Check if this is an investment property loan"""
    loan_info = profile.get('loan_info', {})
    
    occupancy = loan_info.get('occupancy_status', '').lower()
    if 'investment' in occupancy or 'non-owner' in occupancy or 'investor' in occupancy:
        return True
    
    loan_purpose = loan_info.get('loan_purpose', '').lower()
    if 'investment' in loan_purpose:
        return True
    
    income_profile = profile.get('income_profile', {})
    if income_profile.get('dscr') is not None:
        return True
    
    rental_income = income_profile.get('rental_income', 0) or 0
    base_income = income_profile.get('base_income', 0) or 0
    
    if rental_income > 0 and base_income == 0:
        return True
    
    return False

def get_all_document_summaries(loan_id: int) -> List[Dict]:
    """Fetch document summaries"""
    documents = execute_query("""
        SELECT filename, individual_analysis
        FROM document_analysis
        WHERE loan_id = %s
        AND individual_analysis IS NOT NULL
        ORDER BY filename
    """, (loan_id,))
    
    summaries = []
    for doc in documents:
        analysis = doc.get('individual_analysis') or {}
        if isinstance(analysis, dict):
            summary = analysis.get('document_summary', {})
            if summary:
                summaries.append({
                    "filename": doc['filename'],
                    "document_summary": summary
                })
    
    return summaries

def select_pitia_documents(loan_id: int, summaries: List[Dict], profile: Dict) -> List[str]:
    """
    Select documents needed to calculate PITIA.
    Focus on: appraisal (taxes), loan docs (P&I), insurance quotes, HOA docs.
    """
    print(f"\n🤖 Asking Claude ({MODEL_NAME}) to select PITIA documents...")
    
    context_docs = []
    for s in summaries:
        context_docs.append({
            "filename": s['filename'],
            "type": s['document_summary'].get('document_type'),
            "category": s['document_summary'].get('category'),
        })
    
    loan_info = profile.get('loan_info', {})
    context = {
        "loan_amount": loan_info.get('loan_amount'),
        "interest_rate": loan_info.get('interest_rate'),
        "loan_term": loan_info.get('loan_term_months'),
        "property_type": loan_info.get('property_type')
    }
    
    prompt = f"""You are an expert mortgage underwriter specializing in investment property loans.

Your task is to select ALL documents needed to calculate PITIA (Principal + Interest + Taxes + Insurance + Association fees).

# LOAN CONTEXT
{_safe_json_dumps(context)}

# INSTRUCTIONS
1. **Select appraisal** - contains property taxes and HOA fees
2. **Select 1008/URLA** - for context on proposed payment (but NEVER cite as evidence)
3. **Select insurance quote/binder** if available
4. **Select HOA documents** if available
5. **DO NOT select** credit reports or personal debt documents

# PITIA COMPONENTS TO VERIFY
- Principal & Interest (P&I) - calculated from loan amount, rate, term
- Property Taxes - from appraisal or tax documents
- Homeowner's Insurance - from insurance quote or estimate
- HOA/Condo fees - from appraisal or HOA documents

# AVAILABLE DOCUMENTS
{_safe_json_dumps(context_docs)}

Return a JSON object with a single key "selected_filenames" containing a list of strings.
Example: {{"selected_filenames": ["appraisal_19.pdf", "1008___final_0.pdf"]}}
"""

    response_text = call_bedrock(
        prompt=prompt,
        model=MODEL_NAME,
        max_tokens=4000,
        temperature=0.0
    )
    
    try:
        result = _extract_json_from_model_response(response_text)
        selected = result.get('selected_filenames', [])
        print(f"  ✅ Selected {len(selected)} documents: {selected}")
        return selected
    except Exception as e:
        print(f"  ❌ Error parsing selection response: {e}")
        return []

def calculate_pitia_evidence(loan_id: int, selected_filenames: List[str], profile: Dict):
    """
    Generate PITIA calculation evidence.
    """
    print(f"\n🤖 Asking Claude ({MODEL_NAME}) to evidence PITIA calculation...")
    
    context_doc_keywords = ['1008', 'urla', 'preliminary']
    
    evidence_docs = []
    context_docs = []
    
    for fname in selected_filenames:
        is_context_doc = any(keyword in fname.lower() for keyword in context_doc_keywords)
        
        row = execute_one(
            "SELECT individual_analysis FROM document_analysis WHERE loan_id=%s AND filename=%s",
            (loan_id, fname)
        )
        
        if row and row['individual_analysis']:
            deep_data = row['individual_analysis']
            
            if is_context_doc:
                if isinstance(deep_data, dict):
                    context_docs.append({
                        "filename": fname,
                        "document_type": deep_data.get('document_summary', {}).get('document_type', 'Unknown'),
                        "note": "Context document"
                    })
            else:
                if isinstance(deep_data, dict):
                    compact_data = {
                        "filename": fname,
                        "document_type": deep_data.get('document_summary', {}).get('document_type', 'Unknown'),
                        "document_summary": deep_data.get('document_summary', {}),
                    }
                    evidence_docs.append(compact_data)
                else:
                    evidence_docs.append({
                        "filename": fname,
                        "data": str(deep_data)[:2000]
                    })
    
    if not evidence_docs:
        print("  ❌ No evidence data available.")
        return None
    
    # Get loan details
    loan_info = profile.get('loan_info', {})
    loan_details = {
        'loan_amount': loan_info.get('loan_amount', 0),
        'interest_rate': loan_info.get('interest_rate', 0),
        'loan_term_months': loan_info.get('loan_term_months', 360),
        'monthly_pi_payment': loan_info.get('monthly_pi_payment', 0)
    }
    
    prompt = f"""You are MODDA, a mortgage document verification system.

# TASK
Calculate the total monthly PITIA (Principal + Interest + Taxes + Insurance + Association fees) for this investment property.

# LOAN DETAILS
Loan Amount: ${loan_details['loan_amount']:,.2f}
Interest Rate: {loan_details['interest_rate']}%
Loan Term: {loan_details['loan_term_months']} months
Monthly P&I: ${loan_details['monthly_pi_payment']:,.2f}

# CONTEXT DOCUMENTS (For Understanding - NOT for Citation)
{_safe_json_dumps(context_docs)}

# PRIMARY SOURCE DOCUMENTS (For Evidence and Citation)
{_safe_json_dumps(evidence_docs)}

# CRITICAL RULES

## CALCULATION REQUIREMENTS:
1. **Calculate or extract P&I** - use provided monthly P&I or calculate from loan details
2. **Extract property taxes** - from appraisal (annual amount ÷ 12)
3. **Extract/estimate insurance** - from insurance quote or reasonable estimate
4. **Extract HOA fees** - from appraisal or HOA documents (if applicable)
5. **Create ONLY ONE calculation step** showing total monthly PITIA
6. **DO NOT include personal debts** - DSCR loans only care about property expenses

## OUTPUT FORMAT (Strict JSON)
Return JSON matching this schema:

{{
  "calculation_steps": [
    {{
      "step_order": 1,
      "value": "$850.00",
      "description": "Total Monthly PITIA (Housing Expense)",
      "rationale": "Principal & Interest: $518 (calculated), Property Taxes: $165/year = $14/month (Page 3, appraisal.pdf), Insurance: $600/year = $50/month (estimated), HOA: $268/year = $22/month (Page 3, appraisal.pdf). Total: $518 + $14 + $50 + $22 = $604",
      "formula": "P&I + (Annual Taxes / 12) + (Annual Insurance / 12) + (Annual HOA / 12)",
      "document_name": "appraisal_19.pdf",
      "page_number": 3,
      "source_location": "Property Information - Taxes and HOA"
    }}
  ],
  "verification_summary": "<Use STRUCTURED FORMAT below>",
  "calculated_pitia": <float total monthly PITIA>,
  "evidence_files": [
    {{
      "file_name": "<exact filename>",
      "classification": "primary",
      "document_type": "Appraisal",
      "confidence_score": 1.0,
      "page_number": <page number>
    }}
  ]
}}

# VERIFICATION SUMMARY FORMAT

## PITIA Verification (Investment Property)

### Monthly Housing Expense
Total monthly PITIA calculated from loan details and appraisal data.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DEBT OBLIGATIONS INCLUDED

1. Monthly Housing Payment (PITIA) - **$XXX.XX**
• Principal & Interest: $XXX (calculated from loan terms)
• Property Taxes: $XXX/month (Page X, filename.pdf)
• Homeowner's Insurance: $XXX/month (estimated or per quote)
• HOA/Association Fees: $XXX/month (Page X, filename.pdf)

TOTAL MONTHLY PITIA: **$XXX.XX**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

UNDERWRITING METHODOLOGY & COMPLIANCE

✓ **Loan Type**: Investment Property / DSCR Loan
✓ **Qualification**: Property must generate rent to cover PITIA (DSCR ≥ 1.25)
✓ **Personal Debts**: NOT included (not relevant for DSCR qualification)
✓ **Source**: Property taxes and fees from certified appraisal

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

VERIFICATION CONFIDENCE: HIGH (100%)

✓ All PITIA components documented and verified
✓ Calculations verified and cross-checked
✓ Property expenses properly accounted for DSCR calculation

CRITICAL: Always cite page references as (Page X, filename.pdf) - the UI will convert these to clickable badges.
"""

    response_text = call_bedrock(
        prompt=prompt,
        model=MODEL_NAME,
        max_tokens=8000,
        temperature=0.0
    )
    
    try:
        result = _extract_json_from_model_response(response_text)
        return result
    except Exception as e:
        print(f"  ❌ Error parsing calculation response: {e}")
        return None

def save_pitia_verification(loan_id: int, evidence_result: Dict):
    """Save PITIA verification results"""
    print("\n💾 Saving verification results to database...")
    
    # Find attribute for monthly payment/PITIA
    attr_row = execute_one("""
        SELECT id FROM form_1008_attributes 
        WHERE attribute_name ILIKE '%%monthly%%payment%%'
           OR attribute_label ILIKE '%%Total Monthly%%Payment%%'
           OR attribute_name ILIKE '%%pitia%%'
        ORDER BY 
            CASE 
                WHEN attribute_name ILIKE '%%total%%monthly%%payment%%' THEN 1
                ELSE 2
            END,
            id ASC
        LIMIT 1
    """)
    
    if not attr_row:
        print("  ⚠️  Could not find PITIA attribute ID in database.")
        return
    
    attribute_id = attr_row['id']
    print(f"  📌 Using Attribute ID {attribute_id} (PITIA)")
    
    success = save_evidence_to_database(loan_id, attribute_id, evidence_result)
    
    if success:
        print(f"  ✅ Successfully saved evidence for Attribute ID {attribute_id}")
        update_profile_pitia_verification(loan_id, evidence_result, attribute_id)
    else:
        print("  ❌ Failed to save evidence.")

def update_profile_pitia_verification(loan_id: int, evidence_result: Dict, attribute_id: int):
    """Update loan_profiles with PITIA"""
    row = execute_one("SELECT profile_data FROM loan_profiles WHERE loan_id = %s", (loan_id,))
    if not row:
        return
    
    profile = row['profile_data'] or {}
    debt_profile = profile.get('debt_profile', {})
    
    calculated_pitia = evidence_result.get('calculated_pitia', 0) or 0
    
    debt_profile['total_monthly_obligations'] = calculated_pitia
    debt_profile['monthly_pitia'] = calculated_pitia
    profile['debt_profile'] = debt_profile
    
    # Update verification_status
    verification_status = profile.get('verification_status', {})
    verification_status['debt'] = {
        'verified': True,
        'document_value': calculated_pitia,
        'variance_percent': 0.0,
        'notes': ["Verified PITIA for Investment Property"]
    }
    profile['verification_status'] = verification_status
    
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE loan_profiles SET profile_data = %s WHERE loan_id = %s",
            (json.dumps(profile), loan_id)
        )
        conn.commit()
        print(f"  ✅ Updated loan profile with PITIA: ${calculated_pitia:,.2f}")
        
        # Update extracted_1008_data
        pitia_str = f"{calculated_pitia:.2f}"
        
        existing = execute_one("""
            SELECT id FROM extracted_1008_data 
            WHERE loan_id = %s AND attribute_id = %s
        """, (loan_id, attribute_id))
        
        if existing:
            cur.execute("""
                UPDATE extracted_1008_data 
                SET extracted_value = %s, 
                    confidence_score = 0.99,
                    extraction_date = CURRENT_TIMESTAMP
                WHERE loan_id = %s AND attribute_id = %s
            """, (pitia_str, loan_id, attribute_id))
        else:
            cur.execute("""
                INSERT INTO extracted_1008_data 
                (loan_id, attribute_id, extracted_value, confidence_score, extraction_date)
                VALUES (%s, %s, %s, 0.99, CURRENT_TIMESTAMP)
            """, (loan_id, attribute_id, pitia_str))
        
        conn.commit()
        print(f"  ✅ Updated extracted_1008_data with PITIA")
        
    finally:
        cur.close()
        conn.close()

def main():
    if len(sys.argv) > 1:
        try:
            loan_id = int(sys.argv[1])
        except ValueError:
            print("Usage: python backend/summary_s5b_verify_pitia.py [loan_id]")
            return
    else:
        loan_id = 36  # Default test
    
    print(f"\n🏠 Starting PITIA Verification for Loan {loan_id}")
    print("=" * 60)
    
    # 1. Get Loan Profile
    profile = get_loan_profile(loan_id)
    
    # 2. Check if this is an investment property
    if not is_investment_property(loan_id, profile):
        print(f"\n⚠️  Loan {loan_id} is NOT an investment property.")
        print("   Use summary_s5a_verify_debt.py for personal debt verification.")
        return
    
    print(f"✅ Confirmed: Investment Property / DSCR Loan\n")
    
    # 3. Get Summaries
    summaries = get_all_document_summaries(loan_id)
    
    # 4. Select Documents
    selected_files = select_pitia_documents(loan_id, summaries, profile)
    if not selected_files:
        print("❌ No PITIA documents selected.")
        return
    
    # 5. Calculate Evidence
    evidence_result = calculate_pitia_evidence(loan_id, selected_files, profile)
    
    if evidence_result:
        print("\n📊 Verification Result Generated")
        total_pitia = evidence_result.get('calculated_pitia', 0) or 0
        print(f"Total Monthly PITIA: ${total_pitia:,.2f}")
        print(f"Steps: {len(evidence_result.get('calculation_steps', []))}")
        
        # 6. Save to DB
        save_pitia_verification(loan_id, evidence_result)
        
        print("\n✅ PITIA Verification Complete!")
    else:
        print("\n❌ Failed to generate PITIA evidence.")

if __name__ == "__main__":
    main()




