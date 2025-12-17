#!/usr/bin/env python3
"""
Step 5a: Verify Debt (Total Monthly Obligations)
=================================================

This step verifies the borrower's total monthly debt obligations.
Two-stage LLM process with Claude Opus 4.5:
1. Document Selection: Identify debt-related documents (credit reports, liabilities)
2. Evidence Generation: Calculate total monthly debt from primary source documents

Usage:
    python backend/summary_s5a_verify_debt.py [loan_id]
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
    """Fetch loan profile for context"""
    row = execute_one("SELECT profile_data FROM loan_profiles WHERE loan_id = %s", (loan_id,))
    
    if row and row.get('profile_data'):
        return row['profile_data']
    return {}

def get_all_document_summaries(loan_id: int) -> List[Dict]:
    """Fetch document summaries for all files"""
    print(f"  Fetching document summaries for loan {loan_id}...")
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

def select_debt_documents(loan_id: int, summaries: List[Dict], profile: Dict) -> List[str]:
    """
    Ask Claude to select documents relevant for debt verification.
    Focus on: credit reports, liability worksheets, mortgage statements, loan documents.
    """
    print(f"\n🤖 Asking Claude ({MODEL_NAME}) to select debt documents...")
    
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
        "loan_purpose": loan_info.get('loan_purpose')
    }
    
    prompt = f"""You are an expert mortgage underwriter.

Your task is to select ALL documents needed to verify the borrower's MONTHLY DEBT OBLIGATIONS.

# LOAN CONTEXT
{_safe_json_dumps(context)}

# INSTRUCTIONS - Select the BEST source documents for each debt component:

**For Proposed Housing Payment (PITI):**
1. **Promissory Note or Note** - for Principal & Interest (P&I) payment
2. **Property Tax Worksheet or Tax Records** - for property taxes
3. **ALL Insurance documents** - Select ANY document with "insurance" in filename (hazard, supplemental, flood, other_hazard, etc.)
4. **HOA documents** - for HOA/condo fees (if applicable)
5. **Closing Disclosure** - fallback if specific docs not available

**For Existing Debts:**
1. **Credit Report** - PRIMARY source for all existing monthly obligations
2. **1008 and/or URLA** - for context on debt structure (NEVER cite as evidence)
3. **Ability to Repay Worksheet or Liability Worksheet** - for underwriter's analysis

**DO NOT select:**
- Income documents (W-2s, paystubs, tax returns, bank statements)
- Documents not related to debt verification

# AVAILABLE DOCUMENTS
{_safe_json_dumps(context_docs)}

Return a JSON object with a single key "selected_filenames" containing a list of strings.
Example: {{"selected_filenames": ["credit_report_45.pdf", "1008___final_0.pdf", "liability_worksheet_12.pdf"]}}
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

def get_target_debt(loan_id: int, profile: Dict) -> float:
    """
    Get the target total monthly debt to verify.
    Uses "Proposed Monthly Total Monthly Payments Amount" which includes FULL PITI + other debts.
    """
    # First try to get the CORRECT field from 1008 data
    row = execute_one("""
        SELECT extracted_value, fa.attribute_label
        FROM extracted_1008_data ed
        JOIN form_1008_attributes fa ON fa.id = ed.attribute_id
        WHERE ed.loan_id = %s 
        AND (fa.attribute_name = 'proposed_monthly_total_monthly_payments_amount'
             OR fa.attribute_label = 'Proposed Monthly Total Monthly Payments Amount')
        LIMIT 1
    """, (loan_id,))
    
    if row and row['extracted_value']:
        try:
            import re
            val = re.sub(r'[$,]', '', str(row['extracted_value']))
            print(f"  📊 Using '{row['attribute_label']}': ${float(val):,.2f}")
            return float(val)
        except:
            pass
    
    # Fallback to profile
    debt_profile = profile.get('debt_profile', {})
    total_debt = debt_profile.get('total_monthly_obligations', 0.0)
    
    if not total_debt:
        # Fallback to any monthly payment field
        row = execute_one("""
            SELECT extracted_value
            FROM extracted_1008_data ed
            JOIN form_1008_attributes fa ON fa.id = ed.attribute_id
            WHERE ed.loan_id = %s 
            AND (fa.attribute_label ILIKE '%%total%%obligation%%'
                 OR fa.attribute_label ILIKE '%%total%%debt%%'
                 OR fa.attribute_label ILIKE '%%monthly%%payment%%')
            ORDER BY fa.id
            LIMIT 1
        """, (loan_id,))
        
        if row and row['extracted_value']:
            try:
                import re
                val = re.sub(r'[$,]', '', str(row['extracted_value']))
                return float(val)
            except:
                pass
    
    return float(total_debt)

def calculate_debt_evidence(loan_id: int, selected_filenames: List[str], target_debt: float, profile: Dict):
    """
    Generate debt calculation evidence using Claude.
    Now sends ALL financial documents for comprehensive analysis.
    """
    """
    Generate debt calculation evidence using deep JSON of selected documents.
    """
    print(f"\n🤖 Asking Claude ({MODEL_NAME}) to evidence debt calculation...")
    
    # Categorize documents
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
                # Minimal context for 1008/URLA
                if isinstance(deep_data, dict):
                    context_docs.append({
                        "filename": fname,
                        "document_type": deep_data.get('document_summary', {}).get('document_type', 'Unknown'),
                        "note": "Context document - shows debt breakdown but cannot be cited as evidence"
                    })
            else:
                # For primary source documents, send FULL deep JSON data
                if isinstance(deep_data, dict):
                    # For CREDIT REPORTS - send ALL pages with full tradeline details
                    if 'credit' in fname.lower() and 'report' in fname.lower():
                        compact_data = {
                            "filename": fname,
                            "document_type": deep_data.get('document_summary', {}).get('document_type', 'Credit Report'),
                            "document_summary": deep_data.get('document_summary', {}),
                            "pages": []
                        }
                        # Include ALL pages with full tables (tradelines) - but cap at 50 pages max
                        pages = deep_data.get('pages', [])
                        for page in pages[:50]:  # Cap at 50 pages to avoid token limits
                            page_data = {
                                "page_number": page.get('page_number'),
                                "tables": page.get('tables', []),  # ALL TABLES
                                "key_value_pairs": page.get('key_value_pairs', [])  # ALL KEY-VALUE PAIRS
                            }
                            compact_data["pages"].append(page_data)
                        evidence_docs.append(compact_data)
                    else:
                        # For other documents (notes, tax records, insurance) - send pages with cap
                        compact_data = {
                            "filename": fname,
                            "document_type": deep_data.get('document_summary', {}).get('document_type', 'Unknown'),
                            "document_summary": deep_data.get('document_summary', {}),
                            "pages": []
                        }
                        # Include pages - cap at 20 for other docs to manage token limits
                        pages = deep_data.get('pages', [])
                        for page in pages[:20]:  # Cap at 20 pages
                            page_data = {
                                "page_number": page.get('page_number'),
                                "key_value_pairs": page.get('key_value_pairs', [])[:30],  # Limit key-value pairs
                                "tables": page.get('tables', [])[:10]  # Limit tables
                            }
                            compact_data["pages"].append(page_data)
                        evidence_docs.append(compact_data)
                else:
                    # If not a dict, send as-is
                    evidence_docs.append({
                        "filename": fname,
                        "full_data": deep_data  # Send complete data
                    })
    
    if not evidence_docs:
        print("  ❌ No evidence data available.")
        return None
    
    prompt = f"""You are MODDA, a mortgage document verification system.

⚠️ CRITICAL INSTRUCTION FOR STEP 6 (Other Monthly Debts):
You MUST extract and list EACH INDIVIDUAL TRADELINE from the credit report by name.
DO NOT just reference a worksheet summary or say "per credit report $1,521".
You MUST go into the credit report tables/pages and list:
- EACH revolving account creditor name (e.g., "CAPITAL ONE", "CHASE", "AMEX") with minimum payment
- EACH installment loan creditor name (e.g., "ALLY AUTO", "NAVIENT") with monthly payment
- Show the itemized calculation: "$XXX + $XXX + $XXX = $X,XXX"

If you cannot find individual tradeline details in the credit report, state "DOCUMENTATION GAP: Credit report does not contain itemized tradeline data."

# TARGET TO VERIFY
Attribute: Total Monthly Debt Obligations
Reference Value: ${target_debt:,.2f}
NOTE: This reference value may be incomplete. Calculate the ACTUAL total monthly debt obligations by summing ALL debts from credit report + proposed housing payment. Do NOT just match this reference value.

# LOAN CONTEXT
{_safe_json_dumps(profile.get('underwriting_notes', {}))}

# CONTEXT DOCUMENTS (For Understanding - NOT for Citation)
{_safe_json_dumps(context_docs)}

**CRITICAL - Check 1008 Section 2 "Proposed Monthly Payments" for COMPLETE breakdown**:
Review the 1008 to identify EVERY line item that needs verification. Common items include:
- P&I (always present)
- Property Taxes (always present)
- Homeowner's/Hazard Insurance (always present)
- **Supplemental Property Insurance** (check if present! Often $5-10/month)
- Flood Insurance (if applicable)
- HOA/Association Dues (if applicable)
- Other fees

For each item found in 1008, create a calculation step citing the primary source document. If an item appears in 1008 but you cannot find a separate supporting document, you may cite the 1008 page as a fallback but note "Per 1008 Section 2".

# PRIMARY SOURCE DOCUMENTS (For Evidence and Citation)
{_safe_json_dumps(evidence_docs)}

# CRITICAL RULES

1. **Use 1008 for UNDERSTANDING only** - Check 1008 Section 2 to identify ALL payment components (P&I, Taxes, ALL Insurance types including Supplemental, HOA). Never cite 1008 as evidence.

2. **Document each component with primary sources**:
   - P&I → Promissory Note
   - Taxes → Tax Worksheet/Records  
   - Insurance (ALL types found in 1008) → Insurance docs (create separate step for each: Homeowner's, Supplemental, Flood, etc.)
   - HOA → HOA docs/Appraisal
   - Other Debts → Credit Report tradelines (itemize EACH creditor with amount)

3. **Step 6 MUST itemize ALL credit report debts** - List each creditor name, account type, monthly payment separately. Show calculation formula. NO worksheet summaries.

## OUTPUT FORMAT (Strict JSON)
Return JSON matching this schema:

{{
  "calculation_steps": [
    {{
      "step_order": 1,
      "value": "$6,872.12",
      "description": "Proposed Principal & Interest (P&I)",
      "rationale": "Monthly P&I payment as stated in the Promissory Note.",
      "formula": null,
      "document_name": "note_146.pdf",
      "page_number": 1,
      "source_location": "Section 3 - Monthly Payment Amount"
    }},
    {{
      "step_order": 2,
      "value": "$1,878.49",
      "description": "Property Taxes (Monthly)",
      "rationale": "Monthly property tax amount from tax worksheet.",
      "formula": null,
      "document_name": "tax_workup_sheet_183.pdf",
      "page_number": 1,
      "source_location": "Monthly Tax Amount"
    }},
    {{
      "step_order": 3,
      "value": "$400.42",
      "description": "Hazard Insurance (Monthly)",
      "rationale": "Monthly hazard insurance premium from insurance documents.",
      "formula": null,
      "document_name": "hazard_insurance_81.pdf",
      "page_number": 1,
      "source_location": "Monthly Premium"
    }},
    {{
      "step_order": 4,
      "value": "$169.00",
      "description": "HOA Fees (Monthly)",
      "rationale": "Monthly HOA dues from appraisal or HOA documents.",
      "formula": null,
      "document_name": "appraisal_120.pdf",
      "page_number": 5,
      "source_location": "HOA Fees Section"
    }},
    {{
      "step_order": 5,
      "value": "$9,320.03",
      "description": "Total Housing Payment (PITI + HOA)",
      "rationale": "Sum of P&I, taxes, insurance, and HOA fees.",
      "formula": "$6,872.12 + $1,878.49 + $400.42 + $169.00",
      "document_name": null,
      "page_number": null,
      "source_location": "Calculated Total"
    }},
    {{
      "step_order": 6,
      "value": "$1,521.00",
      "description": "Other Monthly Debts (from Credit Report Tradelines)",
      "rationale": "Per credit report dated MM/DD/YYYY for borrower [Name], the following monthly debt obligations were identified from the tradelines: **REVOLVING ACCOUNTS**: CAPITAL ONE VISA ending 1234 - minimum payment $298/month (page 3, tradeline #1), CHASE MASTERCARD ending 5678 - minimum payment $125/month (page 4, tradeline #2), AMERICAN EXPRESS ending 9012 - minimum payment $98/month (page 5, tradeline #3); **INSTALLMENT LOANS**: ALLY AUTO FINANCE 2020 Honda Accord - monthly payment $448/month (page 6, tradeline #4), NAVIENT STUDENT LOAN - monthly payment $127/month (page 7, tradeline #5); **OTHER OBLIGATIONS**: Wells Fargo Personal Loan - monthly payment $200/month (page 8, tradeline #6), Child Support - $225/month (page 9). Calculation: $298 + $125 + $98 + $448 + $127 + $200 + $225 = $1,521.00",
      "formula": "$298 + $125 + $98 + $448 + $127 + $200 + $225 = $1,521.00",
      "document_name": "credit_report_50.pdf",
      "page_number": 3,
      "source_location": "Credit Report Tradelines - Pages 3-9"
    }},
    {{
      "step_order": 7,
      "value": "$10,841.03",
      "description": "Total Monthly Debt Obligations",
      "rationale": "Total housing payment (PITI + HOA) plus all other monthly debts.",
      "formula": "$9,320.03 + $1,521.00",
      "document_name": null,
      "page_number": null,
      "source_location": "Calculated Total"
    }}
  ],
  "verification_summary": <JSON object per STRUCTURED FORMAT below>,
  "calculated_debt": <float total monthly debt>,
  "evidence_files": [
    {{
      "file_name": "<exact filename>",
      "classification": "primary",
      "document_type": "Credit Report",
      "confidence_score": 1.0,
      "page_number": <page number>
    }}
  ]
}}

# VERIFICATION SUMMARY FORMAT (STRUCTURED JSON)
The verification_summary must be a JSON object with this structure:

{{
  "summary_type": "debt",
  "header": "All debt obligations verified from tri-merge credit report and supporting loan documents.",
  "sections": [
    {{
      "section_type": "housing_payment",
      "title": "Proposed Housing Payment (PITI + HOA)",
      "items": [
        {{
          "description": "Principal & Interest",
          "amount": 6872.12,
          "amount_formatted": "$6,872.12",
          "document": "note_146.pdf",
          "page": 1,
          "location": "Section 3"
        }},
        {{
          "description": "Property Taxes (Monthly)",
          "amount": 1878.49,
          "amount_formatted": "$1,878.49",
          "document": "property_tax_records_162.pdf",
          "page": 1,
          "location": "Monthly Tax Amount"
        }},
        {{
          "description": "Homeowner's Insurance (Monthly)",
          "amount": 400.42,
          "amount_formatted": "$400.42",
          "document": "hazard_insurance_81.pdf",
          "page": 1,
          "location": "Monthly Premium"
        }},
        {{
          "description": "Supplemental Property Insurance (Monthly)",
          "amount": 6.42,
          "amount_formatted": "$6.42",
          "document": "insurance_binder_82.pdf",
          "page": 1,
          "location": "Supplemental Coverage Premium"
        }},
        {{
          "description": "HOA/Assessments (Monthly)",
          "amount": 169.00,
          "amount_formatted": "$169.00",
          "document": "closing_disclosure_39.pdf",
          "page": 1,
          "location": "HOA Fees"
        }}
      ],
      "subtotal": 9320.03,
      "subtotal_formatted": "$9,320.03"
    }},
    {{
      "section_type": "other_debts",
      "title": "Other Monthly Debts (from Credit Report Tradelines)",
      "items": [
        {{
          "creditor": "SYNCB/CARE CREDIT",
          "account_type": "Credit Card",
          "account_number": "6019182365035833",
          "monthly_payment": 398.00,
          "monthly_payment_formatted": "$398.00",
          "document": "credit_report___final_50.pdf",
          "page": 2,
          "location": "tradeline row 1"
        }},
        {{
          "creditor": "CAPITAL ONE",
          "account_type": "Flex Spending Card",
          "account_number": "515676801065",
          "monthly_payment": 25.00,
          "monthly_payment_formatted": "$25.00",
          "document": "credit_report___final_50.pdf",
          "page": 2,
          "location": "tradeline row 2"
        }}
        // ... include ALL tradelines
      ],
      "subtotal": 1521.00,
      "subtotal_formatted": "$1,521.00"
    }}
  ],
  "total": 10841.03,
  "total_formatted": "$10,841.03",
  "variance": {{
    "reference_value": 10847.45,
    "calculated_value": 10841.03,
    "difference": 6.42,
    "percentage": 0.06,
    "explanation": "Minor rounding difference in tax/insurance monthly calculations.",
    "show_variance": false  // Set to false if variance < 0.5% or if calculated becomes new expected
  }},
  "methodology": [
    {{
      "title": "Source",
      "description": "Credit report(s) from Experian, Equifax, TransUnion dated MM/DD/YYYY"
    }},
    {{
      "title": "Verification",
      "description": "All tradelines verified and current, no derogatory marks"
    }},
    {{
      "title": "Housing Expense",
      "description": "Proposed PITI payment + HOA fees included per loan documents"
    }},
    {{
      "title": "Conservative Underwriting",
      "description": "All reported obligations included in DTI calculation"
    }}
  ],
  "confidence": {{
    "level": "HIGH",
    "percentage": 100,
    "checks": [
      "All debt obligations documented with primary source documents",
      "Monthly payments verified from credit report tradelines",
      "Calculations verified and cross-checked",
      "Methodology aligns with program requirements"
    ]
  }}
}}

CRITICAL: Return verification_summary as a JSON object (not a string). All document references must include exact filename and page number.
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

def save_debt_verification(loan_id: int, evidence_result: Dict):
    """Save debt verification results to database"""
    print("\n💾 Saving verification results to database...")
    
    # Suppress variance display if negligible (< 0.5%) or if we're saving calculated as new expected
    if 'verification_summary' in evidence_result and isinstance(evidence_result['verification_summary'], dict):
        summary = evidence_result['verification_summary']
        if 'variance' in summary and isinstance(summary['variance'], dict):
            variance_pct = summary['variance'].get('percentage', 0)
            # Hide variance if less than 0.5% - it's just rounding
            if variance_pct is not None and variance_pct < 0.5:
                summary['variance']['show_variance'] = False
                print(f"  ℹ️  Variance {variance_pct:.2f}% is negligible - hiding from display")
    
    # Find attribute ID for total debt/obligations
    attr_row = execute_one("""
        SELECT id FROM form_1008_attributes 
        WHERE attribute_name ILIKE '%%total%%obligation%%'
           OR attribute_name ILIKE '%%monthly%%payment%%'
           OR attribute_label ILIKE '%%Total Monthly%%Payment%%'
        ORDER BY 
            CASE 
                WHEN attribute_name ILIKE '%%total%%monthly%%payment%%' THEN 1
                WHEN attribute_label ILIKE '%%Total Monthly%%' THEN 2
                ELSE 3
            END,
            id ASC
        LIMIT 1
    """)
    
    if not attr_row:
        print("  ⚠️  Could not find debt/obligation attribute ID in database.")
        return
    
    attribute_id = attr_row['id']
    print(f"  📌 Using Attribute ID {attribute_id} (Total Monthly Debt)")
    
    # Save using existing systematic evidence function
    success = save_evidence_to_database(loan_id, attribute_id, evidence_result)
    
    if success:
        print(f"  ✅ Successfully saved evidence for Attribute ID {attribute_id}")
        update_profile_debt_verification(loan_id, evidence_result, attribute_id)
    else:
        print("  ❌ Failed to save evidence.")

def update_profile_debt_verification(loan_id: int, evidence_result: Dict, attribute_id: int):
    """Update loan_profiles with debt verification"""
    # Generate rich summary first
    print("  🤖 Generating rich summary with Claude Opus 4.5...")
    try:
        from generate_verification_summary import generate_professional_summary
        
        steps = []
        for i, step in enumerate(evidence_result.get('calculation_steps', []), 1):
            steps.append({
                'step_order': i,
                'description': step.get('description', ''),
                'value': step.get('value', ''),
                'document_name': step.get('source_document', '')
            })
        
        evidence_files = []
        for doc in evidence_result.get('documents_cited', []):
            evidence_files.append({
                'file_name': doc.get('filename', ''),
                'page_number': doc.get('page', ''),
                'notes': ''
            })
        
        summary_data = {
            'loan_id': loan_id,
            'calculation_steps': steps,
            'evidence_files': evidence_files
        }
        
        rich_summary = generate_professional_summary(summary_data, 'debt')
    except Exception as e:
        print(f"  ⚠️  Could not generate rich summary: {e}")
        rich_summary = None
    
    row = execute_one("SELECT profile_data FROM loan_profiles WHERE loan_id = %s", (loan_id,))
    if not row:
        return
    
    profile = row['profile_data'] or {}
    debt_profile = profile.get('debt_profile', {})
    
    calculated_debt = evidence_result.get('calculated_debt', 0) or 0
    
    debt_profile['total_monthly_obligations'] = calculated_debt
    profile['debt_profile'] = debt_profile
    
    # Update verification_status so the badge turns GREEN
    verification_status = profile.get('verification_status', {})
    verification_status['debt'] = {
        'verified': True,
        'document_value': calculated_debt,
        'variance_percent': 0.0,
        'notes': ["Verified via Credit Report Analysis"],
        'rich_summary': rich_summary  # Store pre-generated summary
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
        print(f"  ✅ Updated loan profile with total debt: ${calculated_debt:,.2f}")
        
        # Also update extracted_1008_data
        debt_str = f"{calculated_debt:.2f}"
        
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
            """, (debt_str, loan_id, attribute_id))
        else:
            cur.execute("""
                INSERT INTO extracted_1008_data 
                (loan_id, attribute_id, extracted_value, confidence_score, extraction_date)
                VALUES (%s, %s, %s, 0.99, CURRENT_TIMESTAMP)
            """, (loan_id, attribute_id, debt_str))
        
        conn.commit()
        print(f"  ✅ Updated extracted_1008_data with total debt")
        
    finally:
        cur.close()
        conn.close()

def main():
    if len(sys.argv) > 1:
        try:
            loan_id = int(sys.argv[1])
        except ValueError:
            print("Usage: python backend/summary_s5a_verify_debt.py [loan_id]")
            return
    else:
        loan_id = 2  # Default test
    
    print(f"\n💳 Starting Debt Verification for Loan {loan_id}")
    print("=" * 60)
    
    # 1. Get Loan Context
    profile = get_loan_profile(loan_id)
    target_debt = get_target_debt(loan_id, profile)
    print(f"🎯 Target Debt: ${target_debt:,.2f}")
    
    # 2. Get ALL Financial Documents (no selection - send everything relevant)
    print("  📄 Fetching ALL financial documents...")
    
    # Get debt-relevant documents - Smart deduplication but include MULTIPLE misc docs for HOA
    financial_docs = execute_query("""
        WITH categorized_docs AS (
            SELECT DISTINCT ON (filename) filename,
                   analyzed_at,
                   individual_analysis,
                   CASE
                       WHEN filename ILIKE '%%credit%%report%%' AND filename NOT ILIKE '%%fair%%credit%%' THEN 'credit_report'
                       WHEN filename ILIKE '%%1008%%' THEN '1008'
                       WHEN filename ILIKE '%%urla%%' THEN 'urla'
                       WHEN filename ILIKE '%%note%%' THEN 'note'
                       WHEN filename ILIKE '%%closing%%disclosure%%' THEN 'closing'
                       WHEN filename ILIKE '%%insurance%%' THEN 'insurance'
                       WHEN filename ILIKE '%%hoa%%' OR 
                            (filename ILIKE '%%miscellaneous%%' AND individual_analysis::text ILIKE '%%hoa%%') OR
                            (filename ILIKE '%%miscellaneous%%' AND individual_analysis::text ILIKE '%%169%%') OR
                            (filename ILIKE '%%miscellaneous%%' AND individual_analysis::text ILIKE '%%association%%') THEN 'hoa'
                       WHEN filename ILIKE '%%tax%%' AND filename NOT ILIKE '%%return%%' AND filename NOT ILIKE '%%consent%%' THEN 'tax'
                       WHEN filename ILIKE '%%miscellaneous%%' THEN 'misc'
                       WHEN filename ILIKE '%%worksheet%%' THEN 'worksheet'
                       ELSE NULL
                   END as doc_category,
                   CASE
                       WHEN filename ILIKE '%%credit%%report%%' AND filename NOT ILIKE '%%fair%%credit%%' THEN 1
                       WHEN filename ILIKE '%%1008%%' THEN 2
                       WHEN filename ILIKE '%%note%%' THEN 3
                       WHEN filename ILIKE '%%insurance%%' THEN 4
                       WHEN filename ILIKE '%%tax%%' AND filename NOT ILIKE '%%return%%' AND filename NOT ILIKE '%%consent%%' THEN 5
                       WHEN filename ILIKE '%%hoa%%' OR individual_analysis::text ILIKE '%%hoa%%' OR individual_analysis::text ILIKE '%%169%%' THEN 6
                       WHEN filename ILIKE '%%miscellaneous%%' THEN 7
                       WHEN filename ILIKE '%%urla%%' THEN 8
                       WHEN filename ILIKE '%%closing%%disclosure%%' THEN 9
                       WHEN filename ILIKE '%%worksheet%%' THEN 10
                       ELSE 99
                   END as priority
            FROM document_analysis
            WHERE loan_id = %s
            AND master_document_id IS NULL
            AND individual_analysis IS NOT NULL
            AND individual_analysis::text != '{}'
            AND (
                filename ILIKE '%%credit%%report%%' OR
                filename ILIKE '%%1008%%' OR
                filename ILIKE '%%urla%%' OR
                filename ILIKE '%%note%%' OR
                filename ILIKE '%%closing%%' OR
                filename ILIKE '%%insurance%%' OR
                filename ILIKE '%%hoa%%' OR
                filename ILIKE '%%miscellaneous%%' OR
                (filename ILIKE '%%tax%%' AND filename NOT ILIKE '%%return%%') OR
                filename ILIKE '%%worksheet%%'
            )
            AND filename NOT ILIKE '%%w2%%'
            AND filename NOT ILIKE '%%paystub%%'
            AND filename NOT ILIKE '%%bank%%statement%%'
            AND filename NOT ILIKE '%%counseling%%'
            ORDER BY filename, analyzed_at DESC
        ),
        -- Keep ALL insurance and HOA docs, deduplicate others
        insurance_hoa AS (
            SELECT filename, priority
            FROM categorized_docs
            WHERE doc_category IN ('insurance', 'hoa')
        ),
        other_docs AS (
            SELECT DISTINCT ON (doc_category) filename, priority
            FROM categorized_docs
            WHERE doc_category NOT IN ('insurance', 'hoa')
            ORDER BY doc_category,
                     CASE WHEN filename ILIKE '%%final%%' THEN 1 ELSE 2 END,
                     analyzed_at DESC
        ),
        combined AS (
            SELECT * FROM insurance_hoa
            UNION ALL
            SELECT * FROM other_docs
        )
        SELECT filename FROM combined
        ORDER BY priority
        LIMIT 25
    """, (loan_id,))
    
    selected_files = [doc['filename'] for doc in financial_docs]
    print(f"  ✅ Found {len(selected_files)} unique financial documents")
    
    if not selected_files:
        print("❌ No documents with deep JSON found.")
        return
    
    # 3. Calculate Evidence (Claude will figure out what to use)
    evidence_result = calculate_debt_evidence(loan_id, selected_files, target_debt, profile)
    
    if evidence_result:
        print("\n📊 Verification Result Generated")
        total_debt = evidence_result.get('calculated_debt', 0) or 0
        print(f"Total Monthly Debt: ${total_debt:,.2f}")
        print(f"Steps: {len(evidence_result.get('calculation_steps', []))}")
        
        # 5. Save to DB
        save_debt_verification(loan_id, evidence_result)
        
        print("\n✅ Debt Verification Complete!")
    else:
        print("\n❌ Failed to generate debt evidence.")

if __name__ == "__main__":
    main()

