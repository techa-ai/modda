"""
Step 4c: Verify Credit Score (Standardized)
============================================

This step verifies the credit score reported in the 1008/URLA against the credit report.
It uses Claude Opus 4.5 to analyze the credit report and create a step-by-step narrative
explaining how the representative credit score was determined.

Usage:
    python backend/summary_s4c_verify_credit_score.py [loan_id]
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
    """Fetch full loan profile to understand credit requirements."""
    row = execute_one("""
        SELECT profile_data 
        FROM loan_profiles 
        WHERE loan_id = %s
    """, (loan_id,))
    
    if row and row.get('profile_data'):
        return row['profile_data']
    return {}


def get_reported_credit_score(loan_id: int, profile: Dict) -> Optional[int]:
    """Get the credit score reported in 1008/URLA."""
    # First try from profile
    credit_profile = profile.get('credit_profile', {})
    credit_score = credit_profile.get('credit_score')
    
    if credit_score:
        try:
            return int(credit_score)
        except (ValueError, TypeError):
            pass
    
    # Fallback to 1008 extracted data
    row = execute_one("""
        SELECT extracted_value
        FROM extracted_1008_data ed
        JOIN form_1008_attributes fa ON fa.id = ed.attribute_id
        WHERE ed.loan_id = %s 
        AND (fa.attribute_label ILIKE '%credit%score%' 
             OR fa.attribute_name ILIKE '%credit%score%')
        LIMIT 1
    """, (loan_id,))
    
    if row and row['extracted_value']:
        try:
            import re
            val = re.sub(r'[^0-9]', '', str(row['extracted_value']))
            if val:
                return int(val)
        except:
            pass
    
    return None


def find_credit_report(loan_id: int) -> Optional[Dict]:
    """Find the credit report document for this loan."""
    print(f"  Searching for credit report...")
    
    # Look for credit report document
    doc = execute_one("""
        SELECT filename, individual_analysis
        FROM document_analysis
        WHERE loan_id = %s 
        AND filename ILIKE '%%credit%%report%%'
        AND filename ILIKE '%%final%%'
        ORDER BY filename DESC
        LIMIT 1
    """, (loan_id,))
    
    if not doc:
        # Try without 'final'
        doc = execute_one("""
            SELECT filename, individual_analysis
            FROM document_analysis
            WHERE loan_id = %s 
            AND filename ILIKE '%%credit%%report%%'
            ORDER BY filename DESC
            LIMIT 1
        """, (loan_id,))
    
    if doc:
        print(f"  ✅ Found credit report: {doc['filename']}")
        return {
            'filename': doc['filename'],
            'analysis': doc.get('individual_analysis')
        }
    
    print("  ⚠️  No credit report found")
    return None


def verify_credit_score(loan_id: int, reported_score: int, credit_report: Dict, profile: Dict) -> Optional[Dict]:
    """
    Ask Claude to verify the credit score against the credit report.
    Creates a step-by-step narrative explaining how the score was determined.
    """
    print(f"\n🤖 Asking Claude ({MODEL_NAME}) to verify credit score...")
    
    filename = credit_report['filename']
    
    # Get deep JSON for credit report
    deep_data = get_deep_json_for_document(filename)
    if not deep_data:
        deep_data = credit_report.get('analysis')
    
    if not deep_data:
        print("  ❌ No deep JSON available for credit report")
        return None
    
    # Extract borrower info
    borrower_info = profile.get('borrower_info', {})
    loan_info = profile.get('loan_info', {})
    
    prompt = f"""You are MODDA, a mortgage credit verification system.

# VERIFICATION TARGET
Reported Credit Score: {reported_score}
Borrower: {borrower_info.get('primary_borrower_name', 'Unknown')}
Loan Type: {loan_info.get('loan_type', 'Unknown')}

# CREDIT REPORT DATA
Filename: {filename}
{_safe_json_dumps(deep_data)}

# YOUR TASK
Analyze the credit report and create a step-by-step verification FOCUSED ONLY ON SCORE DETERMINATION:

1. **Credit Bureau Scores**: Extract the exact scores from each bureau (Experian, Equifax, TransUnion)
2. **Borrower Count**: Determine if single or multiple borrowers
3. **Score Ordering**: Arrange the scores in order (low to high)
4. **Representative Score Logic**: Apply the methodology:
   - For single borrower: Middle score of three bureaus
   - For multiple borrowers: Lower of the two middle scores
5. **Score Verification**: Verify the reported score ({reported_score}) matches the calculated representative score

IMPORTANT: 
- STOP at step 6 - do NOT include credit analysis, derogatory items, inquiries, or utilization
- Focus ONLY on extracting bureau scores and determining the representative score
- Each step should cite the exact page and section where the score was found

# CRITICAL RULES
- Extract EXACT scores from each credit bureau
- Cite specific sections and page numbers from the credit report
- If multiple borrowers, identify each borrower's scores clearly
- Explain the representative score selection methodology
- Note any discrepancies between reported and actual scores

# OUTPUT FORMAT (Strict JSON)
{{
  "calculation_steps": [
    {{
      "step_order": 1,
      "value": "<score or description>",
      "description": "<short description e.g., 'Experian Score'>",
      "rationale": "<why this matters>",
      "formula": "<methodology if applicable>",
      "document_name": "{filename}",
      "page_number": <integer or null>,
      "source_location": "<section/field reference>"
    }}
  ],
  "verification_summary": "<Use STRUCTURED FORMAT below>",
  "verified_score": <integer - the verified representative score>,
  "matches_reported": <boolean>,
  "evidence_files": [
    {{
      "file_name": "{filename}",
      "classification": "primary",
      "document_type": "Credit Report",
      "confidence_score": 1.0,
      "page_number": <main page number>
    }}
  ]
}}

# VERIFICATION SUMMARY FORMAT
The verification_summary MUST be a structured JSON object (not plain text!):

{{
  "summary_type": "credit",
  "header": "Primary Borrower: {borrower_info.get('primary_borrower_name', 'Unknown')}. {f'Co-Borrower: {borrower_info.get("co_borrower_name")}.' if borrower_info.get('has_co_borrower') else 'Single Borrower Loan.'} Representative Score Methodology: {f'Lower of two middle scores (multiple borrowers)' if borrower_info.get('has_co_borrower') else 'Middle score of three bureaus (single borrower)'}.",
  "sections": [
    {{
      "title": "Credit Bureau Scores - {borrower_info.get('primary_borrower_name', 'Unknown')}",
      "items": [
        {{
          "description": "Experian Score",
          "score": "<actual score>",
          "document": "{filename}",
          "page": <page_number>
        }},
        {{
          "description": "Equifax Score",
          "score": "<actual score>",
          "document": "{filename}",
          "page": <page_number>
        }},
        {{
          "description": "TransUnion Score",
          "score": "<actual score>",
          "document": "{filename}",
          "page": <page_number>
        }}
      ]
    }}{f''',
    {{
      "title": "Credit Bureau Scores - {borrower_info.get('co_borrower_name')}",
      "items": [
        {{
          "description": "Experian Score",
          "score": "<actual score>",
          "document": "{filename}",
          "page": <page_number>
        }},
        {{
          "description": "Equifax Score",
          "score": "<actual score>",
          "document": "{filename}",
          "page": <page_number>
        }},
        {{
          "description": "TransUnion Score",
          "score": "<actual score>",
          "document": "{filename}",
          "page": <page_number>
        }}
      ]
    }}''' if borrower_info.get('has_co_borrower') else ''},
    {{
      "title": "Representative Score Calculation",
      "items": [
        {{
          "description": "Primary Borrower Score Arrangement",
          "details": "Scores arranged low to high: <low>, <middle>, <high>. Middle score selected: <middle_score>"
        }}{f''',
        {{
          "description": "Co-Borrower Score Arrangement",
          "details": "Scores arranged low to high: <low>, <middle>, <high>. Middle score selected: <middle_score>"
        }},
        {{
          "description": "Final Representative Score",
          "details": "Lower of two middle scores: <final_score>"
        }}''' if borrower_info.get('has_co_borrower') else ''}
      ]
    }},
    {{
      "title": "Verification Result",
      "result": {{
        "reported_score": {reported_score},
        "verified_score": "<verified_score from analysis>",
        "match_status": "VERIFIED or MISMATCH",
        "explanation": "The reported credit score of {reported_score} has been <verified/not verified> against the credit bureau data."
      }}
    }}
  ],
  "confidence": {{
    "level": "HIGH",
    "percentage": 100,
    "checks": [
      "All three bureau scores documented from credit report",
      "Representative score methodology verified",
      "Reported score matches verified representative score"
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


def save_credit_verification(loan_id: int, evidence_result: Dict):
    """Save the credit score verification results to the database."""
    print("\n💾 Saving credit verification results to database...")
    
    # Find the Credit Score attribute - must match what the UI expects
    attr_row = execute_one("""
        SELECT id FROM form_1008_attributes 
        WHERE attribute_name = 'borrower_representative_credit_indicator_score'
        LIMIT 1
    """)
    
    if not attr_row:
        print("  ⚠️  Could not find 'Credit Score' attribute ID in database.")
        return
    
    attribute_id = attr_row['id']
    
    # Save evidence
    success = save_evidence_to_database(loan_id, attribute_id, evidence_result)
    
    if success:
        print(f"  ✅ Successfully saved credit evidence for Attribute ID {attribute_id}")
        update_profile_verification(loan_id, evidence_result)
    else:
        print("  ❌ Failed to save evidence.")


def update_profile_verification(loan_id: int, evidence_result: Dict):
    """Update the loan_profiles table to reflect verified credit score."""
    row = execute_one("SELECT profile_data FROM loan_profiles WHERE loan_id = %s", (loan_id,))
    if not row:
        return
    
    profile = row['profile_data'] or {}
    verification_status = profile.get('verification_status', {})
    
    # Update credit score section
    verified_score = evidence_result.get('verified_score')
    matches_reported = evidence_result.get('matches_reported', True)
    
    verification_status['credit_score'] = {
        'verified': True,
        'document_value': verified_score,
        'matches_reported': matches_reported,
        'notes': ["Verified via Credit Report Analysis"]
    }
    
    profile['verification_status'] = verification_status
    
    # Save back
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE loan_profiles SET profile_data = %s WHERE loan_id = %s", 
                   (json.dumps(profile), loan_id))
        conn.commit()
        print(f"  ✅ Updated loan profile - Credit Score: {verified_score}, Matches: {matches_reported}")
    finally:
        cur.close()
        conn.close()


def main(loan_id=None):
    """
    Main function for credit score verification.
    
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
                print("Usage: python backend/summary_s4c_verify_credit_score.py [loan_id]")
                return False
        else:
            loan_id = 2  # Default test
    
    print(f"🔍 Starting Credit Score Verification for Loan {loan_id}")
    print("=" * 60)
    
    # 1. Get Loan Profile
    profile = get_loan_profile(loan_id)
    
    # 2. Get Reported Credit Score
    reported_score = get_reported_credit_score(loan_id, profile)
    if not reported_score:
        print("⚠️  No credit score found in 1008/URLA - skipping")
        return False
    
    print(f"🎯 Reported Credit Score: {reported_score}")
    
    # 3. Find Credit Report
    credit_report = find_credit_report(loan_id)
    if not credit_report:
        print("⚠️  No credit report found - skipping")
        return False
    
    # 4. Verify Credit Score
    evidence_result = verify_credit_score(loan_id, reported_score, credit_report, profile)
    
    if evidence_result:
        print("\n📊 Verification Result Generated")
        print(f"Verified Score: {evidence_result.get('verified_score')}")
        print(f"Matches Reported: {evidence_result.get('matches_reported')}")
        print(f"Steps: {len(evidence_result.get('calculation_steps', []))}")
        
        # 5. Save to DB
        save_credit_verification(loan_id, evidence_result)
        return True
    else:
        print("❌ Verification failed")
        return False


if __name__ == "__main__":
    main()

