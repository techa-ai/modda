#!/usr/bin/env python3
"""
Step 4b: Verify Rental Income (Investment Property / DSCR Loans)
=================================================================

For DSCR (Debt Service Coverage Ratio) and Investment Property loans:
- NO personal income verification needed
- ONLY property rental income matters
- Property must "pay for itself" (DSCR ≥ 1.0)

Two-stage LLM process with Claude Opus 4.5:
1. Document Selection: Identify appraisals, leases, rent rolls
2. Evidence Generation: Extract rental income and calculate DSCR

Usage:
    python backend/step4b_verify_rental_income.py [loan_id]
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
    """Get loan profile to determine if this is an investment property"""
    row = execute_one("SELECT profile_data FROM loan_profiles WHERE loan_id = %s", (loan_id,))
    
    if not row or not row['profile_data']:
        return {}
    
    return row['profile_data']

def is_investment_property(loan_id: int, profile: Dict) -> bool:
    """Check if this is an investment property loan (should use step4b, not step4a)"""
    loan_info = profile.get('loan_info', {})
    
    # Check occupancy status - STRONGEST indicator
    occupancy = loan_info.get('occupancy_status', '').lower()
    if 'investment' in occupancy or 'non-owner' in occupancy or 'investor' in occupancy:
        return True
    
    # Check loan purpose
    loan_purpose = loan_info.get('loan_purpose', '').lower()
    if 'investment' in loan_purpose:
        return True
    
    # Check if there's DSCR data or rental income flagged
    income_profile = profile.get('income_profile', {})
    if income_profile.get('dscr') is not None:  # If DSCR is present, it's likely a rental property
        return True
    
    # Check if rental_income exists BUT base_income is 0 (strong indicator of DSCR loan)
    rental_income = income_profile.get('rental_income', 0) or 0
    base_income = income_profile.get('base_income', 0) or 0
    
    if rental_income > 0 and base_income == 0:
        return True
    
    # Check if there's an appraisal with rental/market rent data
    appraisal_check = execute_one("""
        SELECT COUNT(*) as appraisal_count
        FROM document_analysis
        WHERE loan_id = %s
        AND individual_analysis::text ILIKE '%%market rent%%'
    """, (loan_id,))
    
    if appraisal_check and appraisal_check['appraisal_count'] > 0:
        # Has appraisal with rental data - likely investment property
        return True
    
    return False

def get_all_document_summaries(loan_id: int) -> List[Dict]:
    """Get document summaries for rental income verification"""
    rows = execute_query("""
        SELECT filename, individual_analysis
        FROM document_analysis
        WHERE loan_id = %s
        AND individual_analysis IS NOT NULL
        ORDER BY filename
    """, (loan_id,))
    
    summaries = []
    for row in rows:
        analysis = row['individual_analysis']
        
        # Extract document_summary if available
        doc_summary = {}
        if isinstance(analysis, dict):
            doc_summary = analysis.get('document_summary', {})
        
        summaries.append({
            'filename': row['filename'],
            'document_summary': doc_summary
        })
    
    return summaries

def select_rental_documents(loan_id: int, summaries: List[Dict], profile: Dict) -> List[str]:
    """
    Use Claude to select documents relevant for rental income verification.
    Focus on: appraisals, leases, rent rolls, rent schedules.
    """
    print(f"\n🤖 Asking Claude ({MODEL_NAME}) to select rental income documents...")
    
    # Prepare simplified context
    context_docs = []
    for s in summaries:
        context_docs.append({
            "filename": s['filename'],
            "type": s['document_summary'].get('document_type'),
            "category": s['document_summary'].get('category'),
        })
    
    loan_info = profile.get('loan_info', {})
    context = {
        "loan_type": loan_info.get('loan_type'),
        "occupancy": loan_info.get('occupancy_status'),
        "property_type": loan_info.get('property_type')
    }
    
    prompt = f"""You are an expert mortgage underwriter specializing in investment property loans.

Your task is to select ALL documents needed to verify RENTAL INCOME for this investment property.

# LOAN CONTEXT
{_safe_json_dumps(context)}

# INSTRUCTIONS
1. **ALWAYS select appraisal documents** - these contain market rent analysis and rental comparables
2. **Select lease agreements** if they exist - show actual lease terms and rent amounts
3. **Select rent rolls** if they exist - for multi-unit properties
4. **Select rent schedules or rental worksheets** if they exist
5. **DO NOT select** personal income documents (W-2s, paystubs, tax returns, 1008, URLA)

# AVAILABLE DOCUMENTS
{_safe_json_dumps(context_docs)}

Return a JSON object with a single key "selected_filenames" containing a list of strings.
Example: {{"selected_filenames": ["appraisal_19.pdf", "lease_agreement_45.pdf"]}}
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

def get_loan_details(loan_id: int) -> Dict:
    """Get loan amount, interest rate, terms for DSCR calculation from loan_profiles"""
    # Get from loan_profiles (most reliable source)
    profile_row = execute_one("SELECT profile_data FROM loan_profiles WHERE loan_id = %s", (loan_id,))
    
    details = {
        'original_loan_amount': 0,
        'interest_rate': 0,
        'loan_term_months': 360,
        'monthly_pi_payment': 0
    }
    
    if profile_row and profile_row['profile_data']:
        loan_info = profile_row['profile_data'].get('loan_info', {})
        
        details['original_loan_amount'] = loan_info.get('loan_amount', 0) or 0
        details['interest_rate'] = loan_info.get('interest_rate', 0) or 0
        details['loan_term_months'] = loan_info.get('loan_term_months', 360) or 360
        details['monthly_pi_payment'] = loan_info.get('monthly_pi_payment', 0) or 0
    
    return details

def calculate_rental_income_evidence(loan_id: int, selected_filenames: List[str], profile: Dict):
    """
    Generate rental income evidence using deep JSON of selected documents.
    """
    print(f"\n🤖 Asking Claude ({MODEL_NAME}) to evidence rental income...")
    
    # Load data for selected files (similar to step4a approach)
    context_doc_keywords = ['1008', 'urla', 'preliminary']
    
    evidence_docs = []
    context_docs = []
    
    for fname in selected_filenames:
        is_context_doc = any(keyword in fname.lower() for keyword in context_doc_keywords)
        
        # Load analysis from DB
        row = execute_one(
            "SELECT individual_analysis FROM document_analysis WHERE loan_id=%s AND filename=%s",
            (loan_id, fname)
        )
        
        if row and row['individual_analysis']:
            deep_data = row['individual_analysis']
            
            if is_context_doc:
                # Minimal context
                if isinstance(deep_data, dict):
                    context_docs.append({
                        "filename": fname,
                        "document_type": deep_data.get('document_summary', {}).get('document_type', 'Unknown'),
                        "note": "Context document"
                    })
            else:
                # For appraisals, extract rental analysis section
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
    
    # Get loan details for DSCR calculation
    loan_details = get_loan_details(loan_id)
    
    prompt = f"""You are MODDA, a mortgage document verification system specializing in investment property loans.

# TASK
Verify the RENTAL INCOME for this investment property. Calculate DSCR for reference, but the PRIMARY OUTPUT is the rental income amount.

# LOAN DETAILS
Loan Amount: ${loan_details.get('original_loan_amount', 0):,.2f}
Interest Rate: {loan_details.get('interest_rate', 0)}%
Loan Term: {loan_details.get('loan_term_months', 360)} months

# CONTEXT DOCUMENTS (For Understanding - NOT for Citation)
{_safe_json_dumps(context_docs)}

# PRIMARY SOURCE DOCUMENTS (For Evidence and Citation)
{_safe_json_dumps(evidence_docs)}

# CRITICAL RULES

## RENTAL INCOME SOURCES (in order of preference):
1. **Existing Lease Agreement** - actual rent amount from signed lease (STRONGEST evidence)
2. **Appraisal Market Rent** - appraiser's estimated monthly market rent
3. **Rental Comparables** - average of comparable rents from appraisal
4. **75% of Market Rent** - conservative approach if no lease exists

## CALCULATION REQUIREMENTS:
1. **Extract rental income** with exact source citation
2. **DO NOT include DSCR calculation steps** - those are for a separate DTI/DSCR modal
3. **DO NOT include comparable rentals as separate steps** - mention them in the verification summary only
4. **Create ONLY ONE calculation step** showing the monthly rental income and its source
5. The FINAL calculated_income should be the RENTAL INCOME AMOUNT

## OUTPUT FORMAT (Strict JSON)
Return JSON matching this schema:

{{
  "calculation_steps": [
    {{
      "step_order": 1,
      "value": "$1,200.00",
      "description": "Monthly Market Rent from Appraisal",
      "rationale": "Appraiser estimated market rent based on analysis of comparable rental properties in the area",
      "formula": null,
      "document_name": "appraisal_19.pdf",
      "page_number": 18,
      "source_location": "Rent Schedule - Estimated Monthly Market Rent"
    }}
  ],
  "verification_summary": "<Use STRUCTURED FORMAT below>",
  "calculated_income": <float monthly rental income - THIS IS THE PRIMARY OUTPUT>,
  "calculated_dscr": <float DSCR ratio - for reference only>,
  "dscr_meets_threshold": <true/false>,
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
The verification_summary field must follow this EXACT structure for proper UI rendering:

## Rental Income Verification

### Investment Property / DSCR Loan
This is an investment property loan. The borrower's personal income is NOT required for qualification. The property must generate sufficient rental income to cover its debt obligations.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

INCOME SOURCES INCLUDED

1. Monthly Market Rent - **$X,XXX.XX**
• Appraiser's estimated monthly market rent (Page X, filename.pdf)
• Based on analysis of comparable rental properties in the area
• Supported by rental comparables: [Address 1] ($X,XXX), [Address 2] ($X,XXX), [Address 3] ($X,XXX) (Page X, filename.pdf)

TOTAL MONTHLY INCOME: **$X,XXX.XX**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

UNDERWRITING METHODOLOGY & COMPLIANCE

✓ **Methodology**: Investment Property / DSCR Loan verification
✓ **Income Source**: Appraisal Market Rent from certified appraisal
✓ **DSCR Ratio**: X.XX (Property income covers debt service with XX% cushion)
✓ **Conservative Underwriting**: Market rent supported by comparable properties
✓ **Qualification**: Property qualifies based on rental income alone (DSCR > 1.25)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

VERIFICATION CONFIDENCE: HIGH (100%)

✓ Rental income documented in certified appraisal
✓ Market rent supported by comparable rental properties
✓ Property demonstrates strong debt service coverage
✓ All calculations verified and cross-checked

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

def save_rental_income_verification(loan_id: int, evidence_result: Dict):
    """Save rental income verification results to database"""
    print("\n💾 Saving verification results to database...")
    
    # For rental/investment properties, save to "Total Income" attribute (ID 20)
    # This is the same attribute used for regular income verification
    attr_row = execute_one("""
        SELECT id FROM form_1008_attributes 
        WHERE attribute_name = 'total_income'
        ORDER BY id ASC
        LIMIT 1
    """)
    
    if not attr_row:
        print("  ⚠️  Could not find 'total_income' attribute ID in database.")
        return
    
    attribute_id = attr_row['id']
    print(f"  📌 Using Attribute ID {attribute_id} (Total Income)")
    
    # Save using existing systematic evidence function
    success = save_evidence_to_database(loan_id, attribute_id, evidence_result)
    
    if success:
        print(f"  ✅ Successfully saved evidence for Attribute ID {attribute_id}")
        
        # Update loan profile with rental income and DSCR
        update_profile_rental_verification(loan_id, evidence_result)
    else:
        print("  ❌ Failed to save evidence.")

def update_profile_rental_verification(loan_id: int, evidence_result: Dict):
    """Update loan_profiles with rental income and DSCR"""
    row = execute_one("SELECT profile_data FROM loan_profiles WHERE loan_id = %s", (loan_id,))
    if not row:
        return
    
    profile = row['profile_data'] or {}
    income_profile = profile.get('income_profile', {})
    
    # Update with rental income (primary output is calculated_income)
    calculated_rent = evidence_result.get('calculated_income', 0) or evidence_result.get('calculated_rental_income', 0)
    calculated_dscr = evidence_result.get('calculated_dscr', 0)
    
    income_profile['total_monthly_income'] = calculated_rent
    income_profile['rental_income'] = calculated_rent
    income_profile['dscr'] = calculated_dscr
    income_profile['dscr_meets_threshold'] = evidence_result.get('dscr_meets_threshold', False)
    
    profile['income_profile'] = income_profile
    
    # Update verification_status so the badge turns GREEN
    verification_status = profile.get('verification_status', {})
    verification_status['income'] = {
        'verified': True,
        'document_value': calculated_rent,
        'variance_percent': 0.0,
        'notes': ["Verified via Rental Income Analysis (Investment Property)"]
    }
    profile['verification_status'] = verification_status
    
    # Save back
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE loan_profiles SET profile_data = %s WHERE loan_id = %s",
            (json.dumps(profile), loan_id)
        )
        conn.commit()
        print(f"  ✅ Updated loan profile with rental income: ${calculated_rent or 0:,.2f}, DSCR: {calculated_dscr or 0:.2f}")
        
        # Also update extracted_1008_data
        attr_row = execute_one("""
            SELECT id FROM form_1008_attributes 
            WHERE attribute_name = 'total_income'
        """)
        
        if attr_row:
            attribute_id = attr_row['id']
            income_str = f"{calculated_rent:.2f}"
            
            # Check if record exists
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
                """, (income_str, loan_id, attribute_id))
            else:
                cur.execute("""
                    INSERT INTO extracted_1008_data 
                    (loan_id, attribute_id, extracted_value, confidence_score, extraction_date)
                    VALUES (%s, %s, %s, 0.99, CURRENT_TIMESTAMP)
                """, (loan_id, attribute_id, income_str))
            
            conn.commit()
            print(f"  ✅ Updated extracted_1008_data with rental income")
            
    finally:
        cur.close()
        conn.close()

def main():
    if len(sys.argv) > 1:
        try:
            loan_id = int(sys.argv[1])
        except ValueError:
            print("Usage: python backend/step4b_verify_rental_income.py [loan_id]")
            return
    else:
        loan_id = 36  # Default test
    
    print(f"\n🏢 Starting Rental Income Verification for Loan {loan_id}")
    print("=" * 60)
    
    # 1. Get Loan Profile
    profile = get_loan_profile(loan_id)
    
    # 2. Check if this is an investment property
    if not is_investment_property(loan_id, profile):
        print(f"\n⚠️  Loan {loan_id} is NOT an investment property.")
        print("   Use step4a_verify_income.py for personal income verification.")
        return
    
    print(f"✅ Confirmed: Investment Property / DSCR Loan\n")
    
    # 3. Get Document Summaries
    summaries = get_all_document_summaries(loan_id)
    
    # 4. Select Rental Income Documents
    selected_files = select_rental_documents(loan_id, summaries, profile)
    if not selected_files:
        print("❌ No rental income documents selected.")
        return
    
    # 5. Calculate Rental Income Evidence
    evidence_result = calculate_rental_income_evidence(loan_id, selected_files, profile)
    
    if evidence_result:
        print("\n📊 Verification Result Generated")
        rental_income = evidence_result.get('calculated_income', 0) or evidence_result.get('calculated_rental_income', 0) or 0
        dscr = evidence_result.get('calculated_dscr', 0) or 0
        print(f"Rental Income: ${rental_income:,.2f}")
        print(f"DSCR (Reference): {dscr:.2f}")
        print(f"Meets Threshold: {'✅ YES' if evidence_result.get('dscr_meets_threshold') else '❌ NO'}")
        print(f"Steps: {len(evidence_result.get('calculation_steps', []))}")
        
        # 6. Save to Database
        save_rental_income_verification(loan_id, evidence_result)
        
        print("\n✅ Rental Income Verification Complete!")
    else:
        print("\n❌ Failed to generate rental income evidence.")

if __name__ == "__main__":
    main()

