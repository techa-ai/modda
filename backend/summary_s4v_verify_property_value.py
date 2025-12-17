"""
Step 4v: Verify Property Value & CLTV (Standardized)
====================================================

This step verifies the property value and CLTV calculation reported in the 1008/URLA.
For refinances: Uses appraised value from appraisal report
For purchases: Uses purchase price from purchase agreement

It uses Claude Opus 4.5 to analyze the appraisal/purchase docs and verify CLTV logic.

Usage:
    python backend/summary_s4v_verify_property_value.py [loan_id]
"""

import json
import os
import sys
from typing import Dict, Any, Optional

# Add backend to path if needed for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db import get_db_connection, execute_query, execute_one
from bedrock_config import call_bedrock
from systematic_evidence_v5_standardized import (
    get_deep_json_for_document, 
    _safe_json_dumps, 
    _extract_json_from_model_response,
    save_evidence_to_database
)

# Force use of Opus 4.5 for this step
MODEL_NAME = 'claude-opus-4-5'


def get_loan_profile(loan_id: int) -> Dict:
    """Fetch full loan profile."""
    row = execute_one("""
        SELECT profile_data 
        FROM loan_profiles 
        WHERE loan_id = %s
    """, (loan_id,))
    
    if row and row.get('profile_data'):
        return row['profile_data']
    return {}


def select_appraisal_document(candidates: list) -> Optional[str]:
    """
    Use Claude to identify the actual appraisal report from candidate documents.
    Returns the filename of the selected document.
    """
    if not candidates:
        return None
    
    if len(candidates) == 1:
        return candidates[0]['filename']
    
    # Build document list for Claude
    doc_list = []
    for idx, doc in enumerate(candidates, 1):
        doc_list.append({
            'index': idx,
            'filename': doc['filename'],
            'summary': doc.get('summary', 'No summary available')
        })
    
    prompt = f"""You are a mortgage document classification expert. Your task is to identify the ACTUAL UNIFORM RESIDENTIAL APPRAISAL REPORT from a list of appraisal-related documents.

# CANDIDATE DOCUMENTS
{json.dumps(doc_list, indent=2)}

# YOUR TASK
Review the filenames and summaries above and identify which document is the ACTUAL UNIFORM RESIDENTIAL APPRAISAL REPORT (URAR / Form 1004).

**IMPORTANT RULES:**
- The actual appraisal report typically has terms like "appraisal", "uniform residential", "1004", or "valuation report"
- EXCLUDE disclosure documents like "right to copy of appraisal", "appraisal acknowledgement", "appraisal notice"
- EXCLUDE AVM reports, BPO reports, or automated valuation documents
- If multiple appraisals exist, prefer the one with "final" in the name
- The actual appraisal report is usually one of the larger documents with detailed property analysis

# OUTPUT FORMAT (Strict JSON)
{{
  "selected_filename": "<exact filename of the actual appraisal report>",
  "reasoning": "<brief explanation why this document was selected>"
}}

If NO actual appraisal report is found, return:
{{
  "selected_filename": null,
  "reasoning": "No actual uniform residential appraisal report found - only disclosure/acknowledgement documents"
}}
"""
    
    try:
        response_text = call_bedrock(
            prompt=prompt,
            model=MODEL_NAME,
            max_tokens=1000,
            temperature=0.0
        )
        
        result = _extract_json_from_model_response(response_text)
        selected = result.get('selected_filename')
        reasoning = result.get('reasoning', '')
        
        if selected:
            print(f"  🤖 Claude selected: {selected}")
            print(f"     Reasoning: {reasoning}")
            return selected
        else:
            print(f"  ⚠️  Claude could not identify actual appraisal: {reasoning}")
            return None
            
    except Exception as e:
        print(f"  ⚠️  Error in document selection: {e}")
        # Fallback: return the first document
        return candidates[0]['filename'] if candidates else None


def get_reported_values(loan_id: int, profile: Dict) -> Dict:
    """Get the property value, loan amounts, and CLTV reported in 1008/URLA."""
    property_info = profile.get('property_info', {})
    loan_info = profile.get('loan_info', {})
    ratios = profile.get('ratios', {})
    
    return {
        'appraised_value': property_info.get('appraised_value'),
        'purchase_price': property_info.get('purchase_price'),
        'loan_purpose': loan_info.get('loan_purpose'),
        'loan_amount': loan_info.get('loan_amount'),
        'ltv_percent': ratios.get('ltv_percent'),
        'cltv_percent': ratios.get('cltv_percent')
    }


def find_property_documents(loan_id: int, loan_purpose: str) -> Dict:
    """Find appraisal report and/or purchase agreement using two-phase selection."""
    print(f"  Searching for property documents...")
    
    is_purchase = 'purchase' in str(loan_purpose).lower()
    docs = {}
    
    # PHASE 1: Get ALL documents that might be appraisal-related with their summaries
    print(f"  Phase 1: Gathering all appraisal-related documents...")
    appraisal_candidates = execute_query("""
        SELECT filename, 
               individual_analysis->>'document_summary' as summary
        FROM document_analysis
        WHERE loan_id = %s 
        AND (
            filename ILIKE '%%appraisal%%'
            OR filename ILIKE '%%avm%%'
            OR filename ILIKE '%%valuation%%'
        )
        ORDER BY filename
    """, (loan_id,))
    
    if not appraisal_candidates:
        print(f"  ⚠️  No appraisal-related documents found")
    else:
        print(f"  Found {len(appraisal_candidates)} appraisal-related documents")
        
        # Use Claude to identify the actual appraisal report
        selected_appraisal = select_appraisal_document(appraisal_candidates)
        
        if selected_appraisal:
            # Get the full analysis for the selected document
            appraisal = execute_one("""
                SELECT filename, individual_analysis
                FROM document_analysis
                WHERE loan_id = %s AND filename = %s
            """, (loan_id, selected_appraisal))
            
            if appraisal:
                print(f"  ✅ Selected appraisal: {appraisal['filename']}")
                docs['appraisal'] = {
                    'filename': appraisal['filename'],
                    'analysis': appraisal.get('individual_analysis')
                }
    
    # For purchases, also get purchase agreement
    if is_purchase:
        purchase_doc = execute_one("""
            SELECT filename, individual_analysis
            FROM document_analysis
            WHERE loan_id = %s 
            AND (
                filename ILIKE '%%purchase%%agreement%%'
                OR filename ILIKE '%%sales%%contract%%'
                OR filename ILIKE '%%purchase%%contract%%'
            )
            ORDER BY filename DESC
            LIMIT 1
        """, (loan_id,))
        
        if purchase_doc:
            print(f"  ✅ Found purchase agreement: {purchase_doc['filename']}")
            docs['purchase_agreement'] = {
                'filename': purchase_doc['filename'],
                'analysis': purchase_doc.get('individual_analysis')
            }
    
    # Also check for subordinate lien documents (for CLTV)
    subordinate = execute_one("""
        SELECT filename, individual_analysis
        FROM document_analysis
        WHERE loan_id = %s 
        AND (
            filename ILIKE '%%note%%2nd%%lien%%'
            OR filename ILIKE '%%second%%mortgage%%'
            OR filename ILIKE '%%subordinate%%'
            OR filename ILIKE '%%heloc%%agreement%%'
        )
        ORDER BY filename DESC
        LIMIT 1
    """, (loan_id,))
    
    if subordinate:
        print(f"  ✅ Found subordinate lien: {subordinate['filename']}")
        docs['subordinate_lien'] = {
            'filename': subordinate['filename'],
            'analysis': subordinate.get('individual_analysis')
        }
    
    return docs


def verify_property_value_and_cltv(loan_id: int, reported_values: Dict, property_docs: Dict, profile: Dict) -> Optional[Dict]:
    """
    Ask Claude to verify property value and CLTV calculation.
    """
    print(f"\n🤖 Asking Claude ({MODEL_NAME}) to verify property value and CLTV...")
    
    loan_purpose = reported_values['loan_purpose']
    is_purchase = 'purchase' in str(loan_purpose).lower()
    
    # Load deep JSON for all available documents
    doc_data = {}
    for doc_type, doc_info in property_docs.items():
        filename = doc_info['filename']
        deep_data = get_deep_json_for_document(filename)
        
        if not deep_data:
            deep_data = doc_info.get('analysis')
        
        if not deep_data:
            # Try to load from document_analysis if available
            from db import execute_one
            doc_row = execute_one("""
                SELECT individual_analysis
                FROM document_analysis
                WHERE filename = %s
                LIMIT 1
            """, (filename,))
            
            if doc_row and doc_row.get('individual_analysis'):
                deep_data = doc_row['individual_analysis']
        
        if deep_data:
            doc_data[doc_type] = {
                'filename': filename,
                'data': deep_data
            }
        else:
            print(f"  ⚠️  No deep analysis available for {filename} - deep extraction needed")
    
    if not doc_data:
        print("  ❌ No property document data available")
        print("  💡 Tip: Run deep extraction on the appraisal document first")
        return None
    
    # Extract property info
    property_info = profile.get('property_info', {})
    
    prompt = f"""You are MODDA, a mortgage property valuation verification system.

# VERIFICATION TARGET
Loan Purpose: {loan_purpose}
Property Address: {property_info.get('address', 'Unknown')}

Reported Values:
• Property Value: ${reported_values.get('appraised_value') or 0:,.2f}
• Purchase Price: ${reported_values.get('purchase_price') or 0:,.2f}
• Loan Amount: ${reported_values.get('loan_amount') or 0:,.2f}
• LTV: {reported_values.get('ltv_percent') or 'N/A'}%
• CLTV: {reported_values.get('cltv_percent') or 'N/A'}%

# PROPERTY DOCUMENTS
{_safe_json_dumps(doc_data)}

# YOUR TASK
Analyze the property documents and create a detailed verification of:

1. **Property Value Determination**:
   {"- For Purchase: Verify purchase price from purchase agreement" if is_purchase else "- For Refinance: Verify appraised value from appraisal report"}
   - Extract the exact value from the source document
   - Note the appraisal date and appraiser information
   - Check for any adjustments or conditions

2. **LTV Calculation**:
   - Formula: (First Mortgage Amount / Property Value) × 100
   - Verify the calculation is correct
   - Document all components

3. **CLTV Calculation** (if subordinate liens exist):
   - Formula: (Total of All Liens / Property Value) × 100
   - Identify all lien amounts (first + second + HELOC, etc.)
   - Verify the calculation is correct

4. **Property Analysis**:
   - Property type and condition
   - Comparable sales used (if appraisal)
   - Any red flags or concerns

# CRITICAL RULES
- Extract EXACT values from source documents with page references
- {"Use purchase price as the property value for LTV/CLTV" if is_purchase else "Use appraised value as the property value for LTV/CLTV"}
- Show step-by-step calculations for LTV and CLTV
- Note any discrepancies between reported and actual values
- For CLTV, identify ALL liens (first, second, HELOC, etc.)

# OUTPUT FORMAT (Strict JSON)
{{
  "calculation_steps": [
    {{
      "step_order": 1,
      "value": "<dollar amount or percentage>",
      "description": "<short description e.g., 'Appraised Value'>",
      "rationale": "<why this matters>",
      "formula": "<calculation formula if applicable>",
      "document_name": "<filename>",
      "page_number": <integer or null>,
      "source_location": "<section/field reference>"
    }}
  ],
  "verification_summary": "<Use STRUCTURED FORMAT below>",
  "verified_property_value": <float>,
  "verified_ltv": <float>,
  "verified_cltv": <float>,
  "matches_reported": <boolean>,
  "evidence_files": [
    {{
      "file_name": "<filename>",
      "classification": "primary",
      "document_type": "Appraisal Report" or "Purchase Agreement",
      "confidence_score": 1.0,
      "page_number": <main page number>
    }}
  ]
}}

# VERIFICATION SUMMARY FORMAT
The verification_summary MUST be a structured JSON object (not plain text!):

{{
  "summary_type": "property",
  "header": "Property: {property_info.get('address', 'Unknown')}. Property Type: {property_info.get('property_type', 'Unknown')}. Loan Purpose: {loan_purpose}.",
  "sections": [
    {{
      "title": "Property Value Determination",
      "items": [
        {{
          "description": "{"Purchase Price" if is_purchase else "Appraised Value"}",
          "amount": "<actual dollar amount>",
          "amount_formatted": "$XXX,XXX",
          "document": "<filename>",
          "page": <page_number>
        }},
        {{
          "description": "Appraisal Date",
          "details": "<date>"
        }},
        {{
          "description": "Appraiser",
          "details": "<name/company>"
        }}
      ]
    }},
    {{
      "title": "LTV Calculation",
      "items": [
        {{
          "description": "First Mortgage Amount",
          "amount_formatted": "$XXX,XXX",
          "document": "<filename>",
          "page": <page_number>
        }},
        {{
          "description": "Property Value",
          "amount_formatted": "$XXX,XXX"
        }},
        {{
          "description": "LTV Formula",
          "details": "(Loan Amount / Property Value) × 100"
        }},
        {{
          "description": "Calculated LTV",
          "details": "XX.XX%"
        }},
        {{
          "description": "Reported LTV",
          "details": "{reported_values.get('ltv_percent', 'N/A')}%"
        }}
      ]
    }},
    {{
      "title": "CLTV Calculation",
      "items": [
        {{
          "description": "First Mortgage",
          "amount_formatted": "$XXX,XXX"
        }},
        {{
          "description": "Second Lien/HELOC",
          "amount_formatted": "$XXX,XXX (if exists)",
          "document": "<filename if exists>",
          "page": <page_number if exists>
        }},
        {{
          "description": "Total Liens",
          "amount_formatted": "$XXX,XXX"
        }},
        {{
          "description": "CLTV Formula",
          "details": "(Total Liens / Property Value) × 100"
        }},
        {{
          "description": "Calculated CLTV",
          "details": "XX.XX%"
        }},
        {{
          "description": "Reported CLTV",
          "details": "{reported_values.get('cltv_percent', 'N/A')}%"
        }}
      ]
    }},
    {{
      "title": "Verification Result",
      "result": {{
        "property_value": "<verified value>",
        "ltv_calculated": "<calculated LTV>",
        "ltv_reported": "{reported_values.get('ltv_percent', 'N/A')}",
        "cltv_calculated": "<calculated CLTV>",
        "cltv_reported": "{reported_values.get('cltv_percent', 'N/A')}",
        "match_status": "VERIFIED or MISMATCH",
        "explanation": "Property value and LTV/CLTV calculations have been <verified/not verified>."
      }}
    }}
  ],
  "confidence": {{
    "level": "HIGH",
    "percentage": 100,
    "checks": [
      "Property value documented from authoritative source",
      "LTV/CLTV calculations verified",
      "All lien amounts documented",
      "Reported values match calculations"
    ]
  }}
}}
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
        print(f"  ❌ Error parsing verification response: {e}")
        return None


def save_property_verification(loan_id: int, evidence_result: Dict):
    """Save the property value verification results to the database."""
    print("\n💾 Saving property verification results to database...")
    
    # Find the Property Value attribute - must match what the UI expects
    attr_row = execute_one("""
        SELECT id FROM form_1008_attributes 
        WHERE attribute_name = 'property_appraised_value'
        LIMIT 1
    """)
    
    if not attr_row:
        print("  ⚠️  Could not find 'Property Value' attribute ID in database.")
        return
    
    attribute_id = attr_row['id']
    
    # Save evidence
    success = save_evidence_to_database(loan_id, attribute_id, evidence_result)
    
    if success:
        print(f"  ✅ Successfully saved property evidence for Attribute ID {attribute_id}")
        update_profile_verification(loan_id, evidence_result)
    else:
        print("  ❌ Failed to save evidence.")


def update_profile_verification(loan_id: int, evidence_result: Dict):
    """Update the loan_profiles table to reflect verified property value."""
    row = execute_one("SELECT profile_data FROM loan_profiles WHERE loan_id = %s", (loan_id,))
    if not row:
        return
    
    profile = row['profile_data'] or {}
    verification_status = profile.get('verification_status', {})
    
    # Update property value section
    verified_value = evidence_result.get('verified_property_value')
    verified_ltv = evidence_result.get('verified_ltv')
    verified_cltv = evidence_result.get('verified_cltv')
    matches_reported = evidence_result.get('matches_reported', True)
    
    verification_status['property_value'] = {
        'verified': True,
        'document_value': verified_value,
        'verified_ltv': verified_ltv,
        'verified_cltv': verified_cltv,
        'matches_reported': matches_reported,
        'notes': ["Verified via Appraisal/Purchase Document Analysis"]
    }
    
    profile['verification_status'] = verification_status
    
    # Save back
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE loan_profiles SET profile_data = %s WHERE loan_id = %s", 
                   (json.dumps(profile), loan_id))
        conn.commit()
        
        # Format output safely
        val_str = f"${verified_value:,.2f}" if verified_value else "N/A"
        ltv_str = f"{verified_ltv}%" if verified_ltv else "N/A"
        cltv_str = f"{verified_cltv}%" if verified_cltv else "N/A"
        print(f"  ✅ Updated loan profile - Property Value: {val_str}, LTV: {ltv_str}, CLTV: {cltv_str}")
    finally:
        cur.close()
        conn.close()


def main(loan_id=None):
    """
    Main function for property value and CLTV verification.
    
    Args:
        loan_id: Loan ID to verify. If None, will use command line arg or default to 2.
        
    Returns:
        bool: True if verification succeeded, False if skipped/failed.
    """
    if loan_id is None:
        if len(sys.argv) > 1:
            try:
                loan_id = int(sys.argv[1])
            except ValueError:
                print("Usage: python backend/summary_s4v_verify_property_value.py [loan_id]")
                return False
        else:
            loan_id = 2  # Default test
    
    print(f"🔍 Starting Property Value & CLTV Verification for Loan {loan_id}")
    print("=" * 60)
    
    # 1. Get Loan Profile
    profile = get_loan_profile(loan_id)
    
    # 2. Get Reported Values
    reported_values = get_reported_values(loan_id, profile)
    prop_value = reported_values.get('appraised_value') or 0
    print(f"🎯 Reported Property Value: ${prop_value:,.2f}")
    print(f"🎯 Reported CLTV: {reported_values.get('cltv_percent', 'N/A')}%")
    
    # 3. Find Property Documents
    property_docs = find_property_documents(loan_id, reported_values['loan_purpose'])
    if not property_docs:
        print("⚠️  No property documents found - skipping")
        return False
    
    # 4. Verify Property Value and CLTV
    evidence_result = verify_property_value_and_cltv(loan_id, reported_values, property_docs, profile)
    
    if evidence_result:
        print("\n📊 Verification Result Generated")
        prop_val = evidence_result.get('verified_property_value')
        ltv = evidence_result.get('verified_ltv')
        cltv = evidence_result.get('verified_cltv')
        
        if prop_val:
            print(f"Verified Property Value: ${prop_val:,.2f}")
        else:
            print(f"Verified Property Value: N/A")
        
        if ltv:
            print(f"Verified LTV: {ltv}%")
        else:
            print(f"Verified LTV: N/A")
            
        if cltv:
            print(f"Verified CLTV: {cltv}%")
        else:
            print(f"Verified CLTV: N/A")
            
        print(f"Matches Reported: {evidence_result.get('matches_reported', 'Unknown')}")
        print(f"Steps: {len(evidence_result.get('calculation_steps', []))}")
        
        # 5. Save to DB
        save_property_verification(loan_id, evidence_result)
        return True
    else:
        print("❌ Verification failed")
        return False


if __name__ == "__main__":
    main()

