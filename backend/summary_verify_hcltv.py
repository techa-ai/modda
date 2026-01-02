#!/usr/bin/env python3
"""
Step: Verify HCLTV (High Combined Loan-to-Value)
=================================================

This step verifies the HCLTV ratio by analyzing loan documents.
Two-stage LLM process with Claude:

Stage 1: Document Selection
  - Identify documents needed for HCLTV calculation
  - Focus on: 1008, appraisal, HUD-1/Closing Disclosure, mortgage statements

Stage 2: HCLTV Calculation with Evidence
  - Extract: subject loan amount, existing mortgage balances, HELOC limits, appraised value
  - Calculate HCLTV with full document citations
"""

import sys
import os
import json
from typing import Dict, List

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
    rows = execute_query("""
        SELECT filename, individual_analysis 
        FROM document_analysis 
        WHERE loan_id = %s AND individual_analysis IS NOT NULL
    """, (loan_id,))
    
    summaries = []
    for row in rows:
        if row['individual_analysis'] and isinstance(row['individual_analysis'], dict):
            doc_summary = row['individual_analysis'].get('document_summary', {})
            summaries.append({
                'filename': row['filename'],
                'document_summary': doc_summary
            })
    
    return summaries

def select_hcltv_documents(loan_id: int, summaries: List[Dict], profile: Dict) -> List[str]:
    """
    Ask Claude to select documents relevant for HCLTV verification.
    Focus on: 1008/URLA, appraisal, closing disclosure, mortgage statements.
    """
    print(f"\n🤖 Asking Claude ({MODEL_NAME}) to select HCLTV documents...")
    
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
        "loan_purpose": loan_info.get('loan_purpose'),
        "loan_amount": loan_info.get('loan_amount'),
    }
    
    prompt = f"""You are an expert mortgage underwriter.

Your task is to select ALL documents needed to verify the HCLTV (High Combined Loan-to-Value) ratio.

# LOAN CONTEXT
{_safe_json_dumps(context)}

# HCLTV CALCULATION REQUIRES:
1. **Subject Loan Amount** - from Note, Loan Estimate, or 1008
2. **Existing First Mortgage Balance** (if any) - from Credit Report, Mortgage Statement
3. **Existing Second Mortgage/HELOC Balance** (if any) - from Credit Report
4. **HELOC Credit Limits** (if any) - from Credit Report, HELOC Agreement
5. **Appraised Value** - from Appraisal Report (1004), or AVM

# DOCUMENTS TO SELECT:
- 1008 Form (has loan amounts and property value)
- Appraisal/1004 (for property value)
- Closing Disclosure (for loan amounts)
- Note (for subject loan amount)
- Credit Report (for existing mortgages and HELOCs)
- Any mortgage statements

# AVAILABLE DOCUMENTS
{_safe_json_dumps(context_docs)}

Return a JSON object with a single key "selected_filenames" containing a list of strings.
Example: {{"selected_filenames": ["1008___final_0.pdf", "appraisal_45.pdf", "credit_report_12.pdf"]}}
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

def calculate_hcltv_evidence(loan_id: int, selected_filenames: List[str], profile: Dict) -> Dict:
    """
    Generate HCLTV calculation evidence using deep JSON of selected documents.
    """
    print(f"\n🤖 Asking Claude ({MODEL_NAME}) to evidence HCLTV calculation...")
    
    evidence_docs = []
    
    for fname in selected_filenames:
        # Load analysis from DB
        row = execute_one(
            "SELECT individual_analysis FROM document_analysis WHERE loan_id=%s AND filename=%s",
            (loan_id, fname)
        )
        
        if row and row['individual_analysis']:
            deep_data = row['individual_analysis']
            
            if isinstance(deep_data, dict):
                compact_data = {
                    "filename": fname,
                    "document_type": deep_data.get('document_summary', {}).get('document_type', 'Unknown'),
                    "document_summary": deep_data.get('document_summary', {}),
                    "pages": []
                }
                # Include pages with key-value pairs and tables
                pages = deep_data.get('pages', [])
                for page in pages[:30]:  # Cap at 30 pages
                    page_data = {
                        "page_number": page.get('page_number'),
                        "key_value_pairs": page.get('key_value_pairs', [])[:50],
                        "tables": page.get('tables', [])[:20]
                    }
                    compact_data["pages"].append(page_data)
                evidence_docs.append(compact_data)
    
    if not evidence_docs:
        print("  ❌ No evidence data available.")
        return None
    
    loan_info = profile.get('loan_info', {})
    property_info = profile.get('property_info', {})
    
    prompt = f"""You are MODDA, a mortgage document verification system.

# TASK: Calculate and Verify HCLTV (High Combined Loan-to-Value) Ratio

## HCLTV FORMULA:
HCLTV = (Subject Loan Amount + All Existing Mortgage Balances + HELOC Credit Limits) / Property Value × 100

## WHAT TO EXTRACT (with exact page and document citations):

1. **Subject Loan Amount** - The new loan being originated
   - Look in: Note, 1008 Section 1, Closing Disclosure
   
2. **Existing First Mortgage Balance** (if refinance or second lien)
   - Look in: Credit Report (mortgage tradelines), Mortgage Statements
   - If this is a first mortgage purchase, this should be $0
   
3. **Existing Second Mortgage/HELOC Balance**
   - Look in: Credit Report (HELOC/second mortgage tradelines)
   
4. **HELOC Credit Limits** (for HCLTV, use the full credit limit, not just balance)
   - Look in: Credit Report, HELOC agreements
   
5. **Property Value** (Appraised Value)
   - Look in: Appraisal/1004, AVM report, 1008

## REFERENCE VALUES FROM PROFILE
- Loan Amount: {loan_info.get('loan_amount', 'N/A')}
- Property Value: {property_info.get('appraised_value', 'N/A')}
- Loan Purpose: {loan_info.get('loan_purpose', 'N/A')}

## EVIDENCE DOCUMENTS
{_safe_json_dumps(evidence_docs)}

## REQUIRED OUTPUT FORMAT
Return a JSON object with this exact structure:

{{
  "calculation_steps": [
    {{
      "step": 1,
      "description": "Subject Loan Amount",
      "value": "$XXX,XXX.XX",
      "source": "document_name.pdf",
      "page": X,
      "location": "Field name or location description"
    }},
    {{
      "step": 2,
      "description": "Existing First Mortgage Balance",
      "value": "$XXX,XXX.XX",
      "source": "document_name.pdf",
      "page": X,
      "location": "Tradeline/Section name"
    }},
    {{
      "step": 3,
      "description": "Existing HELOC/Second Mortgage Balance",
      "value": "$X,XXX.XX",
      "source": "document_name.pdf",
      "page": X,
      "location": "Tradeline name"
    }},
    {{
      "step": 4,
      "description": "HELOC Credit Limit (if applicable)",
      "value": "$X,XXX.XX",
      "source": "document_name.pdf",
      "page": X,
      "location": "Credit limit field"
    }},
    {{
      "step": 5,
      "description": "Property Appraised Value",
      "value": "$X,XXX,XXX.XX",
      "source": "document_name.pdf",
      "page": X,
      "location": "Appraised value field"
    }},
    {{
      "step": 6,
      "description": "Total Liens (Subject + Existing)",
      "value": "$XXX,XXX.XX",
      "source": "Calculated",
      "page": null,
      "location": "Sum of steps 1-4"
    }},
    {{
      "step": 7,
      "description": "HCLTV Calculation",
      "value": "XX.XXX%",
      "source": "Calculated",
      "page": null,
      "location": "(Total Liens / Property Value) × 100"
    }}
  ],
  "verification_summary": {{
    "summary_type": "hcltv",
    "header": "HCLTV verified from [document sources]",
    "sections": [
      {{
        "section_type": "liens",
        "title": "Total Liens on Property",
        "items": [
          {{
            "description": "Subject Loan",
            "amount": XXX,
            "amount_formatted": "$XXX,XXX.XX",
            "document": "filename.pdf",
            "page": X,
            "location": "description"
          }}
        ],
        "subtotal": XXX,
        "subtotal_formatted": "$XXX,XXX.XX"
      }},
      {{
        "section_type": "property_value",
        "title": "Property Value",
        "items": [
          {{
            "description": "Appraised Value",
            "amount": XXX,
            "document": "filename.pdf",
            "page": X
          }}
        ],
        "subtotal": XXX,
        "subtotal_formatted": "$X,XXX,XXX.XX"
      }}
    ],
    "total": XX.XXX,
    "total_formatted": "XX.XXX%",
    "assessment": {{
      "status": "Excellent|Acceptable|High",
      "explanation": "HCLTV of XX.XXX% is [assessment explanation]"
    }},
    "methodology": [
      {{
        "title": "Source Documents",
        "description": "List of documents used"
      }}
    ]
  }},
  "evidence_files": [
    {{
      "filename": "document.pdf",
      "page": X,
      "field": "Field name",
      "value": "value found",
      "confidence": 0.99
    }}
  ]
}}

CRITICAL: Every value MUST have a document citation with filename, page number, and field location.
If a value is $0 or not applicable, still document why (e.g., "No existing mortgage - purchase transaction").
"""

    response_text = call_bedrock(
        prompt=prompt,
        model=MODEL_NAME,
        max_tokens=8000,
        temperature=0.0
    )
    
    try:
        result = _extract_json_from_model_response(response_text)
        print(f"  ✅ Generated HCLTV evidence")
        return result
    except Exception as e:
        print(f"  ❌ Error parsing evidence response: {e}")
        return None

def save_hcltv_verification(loan_id: int, evidence_result: Dict) -> bool:
    """Save HCLTV verification results - just log success since we save to profile"""
    if not evidence_result:
        return False
    
    # The verification is saved in the profile, so just log success
    verification_summary = evidence_result.get('verification_summary', {})
    hcltv_value = verification_summary.get('total', 0)
    
    print(f"  ✅ HCLTV calculation complete: {hcltv_value}%")
    return True

def update_profile_hcltv(loan_id: int, evidence_result: Dict) -> bool:
    """Update loan_profiles with HCLTV verification"""
    if not evidence_result:
        return False
    
    # Get current profile
    row = execute_one("SELECT profile_data FROM loan_profiles WHERE loan_id = %s", (loan_id,))
    if not row or not row.get('profile_data'):
        return False
    
    profile = row['profile_data']
    
    # Update ratios with calculated HCLTV
    verification_summary = evidence_result.get('verification_summary', {})
    hcltv_value = verification_summary.get('total', 0)
    
    if 'ratios' not in profile:
        profile['ratios'] = {}
    
    profile['ratios']['hcltv_percent'] = hcltv_value
    
    # Add verification status
    if 'verification_status' not in profile:
        profile['verification_status'] = {}
    
    profile['verification_status']['hcltv'] = {
        'verified': True,
        'value': hcltv_value,
        'summary': verification_summary,
        'calculation_steps': evidence_result.get('calculation_steps', [])
    }
    
    # Save back to database
    from db import get_db_connection
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE loan_profiles SET profile_data = %s WHERE loan_id = %s",
        (json.dumps(profile), loan_id)
    )
    conn.commit()
    cur.close()
    conn.close()
    
    print(f"  ✅ Updated profile with HCLTV: {hcltv_value}%")
    return True

def main():
    if len(sys.argv) < 2:
        print("Usage: python summary_verify_hcltv.py <loan_id>")
        sys.exit(1)
    
    loan_id = int(sys.argv[1])
    print(f"\n{'='*60}")
    print(f"HCLTV VERIFICATION - Loan {loan_id}")
    print(f"{'='*60}")
    
    # Step 1: Get loan profile
    profile = get_loan_profile(loan_id)
    if not profile:
        print(f"❌ Could not load profile for loan {loan_id}")
        sys.exit(1)
    print(f"✅ Loaded loan profile")
    
    # Step 2: Get document summaries
    summaries = get_all_document_summaries(loan_id)
    print(f"✅ Found {len(summaries)} documents with analysis")
    
    # Step 3: Ask Claude to select relevant documents
    selected_files = select_hcltv_documents(loan_id, summaries, profile)
    if not selected_files:
        print("❌ No documents selected for HCLTV verification")
        sys.exit(1)
    
    # Step 4: Calculate HCLTV with evidence
    evidence_result = calculate_hcltv_evidence(loan_id, selected_files, profile)
    if not evidence_result:
        print("❌ Failed to calculate HCLTV evidence")
        sys.exit(1)
    
    # Step 5: Save to database
    save_hcltv_verification(loan_id, evidence_result)
    
    # Step 6: Update profile
    update_profile_hcltv(loan_id, evidence_result)
    
    # Print summary
    verification_summary = evidence_result.get('verification_summary', {})
    print(f"\n{'='*60}")
    print(f"HCLTV VERIFICATION COMPLETE")
    print(f"{'='*60}")
    print(f"  HCLTV: {verification_summary.get('total_formatted', 'N/A')}")
    print(f"  Status: {verification_summary.get('assessment', {}).get('status', 'N/A')}")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()
