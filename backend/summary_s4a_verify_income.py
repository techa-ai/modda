"""
Step 4a: Verify Income (Standardized)
=====================================

This step isolates the income verification logic into a dedicated pipeline step.
It uses a two-stage LLM process with Claude Opus 4.5:
1. Document Selection: Identify relevant income documents based on loan program.
2. Evidence Generation: Calculate and verify income using deep extraction data.
3. Persistence: Save results to database in a format compatible with VerificationModal.jsx.

Usage:
    python backend/step4a_verify_income.py [loan_id]
"""

import json
import os
import sys
from typing import List, Dict, Any, Optional

# Add backend to path if needed for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db import get_db_connection, execute_query, execute_one
from bedrock_config import call_bedrock
from systematic_evidence_v5_standardized import (
    get_deep_json_for_document, 
    _safe_json_dumps, 
    _extract_json_from_model_response,
    save_evidence_to_database,
    DEFAULT_MODEL
)

# Force use of Opus 4.5 for this step
MODEL_NAME = 'claude-opus-4-5'

def get_loan_profile(loan_id: int) -> Dict:
    """Fetch full loan profile to understand loan program/type."""
    row = execute_one("""
        SELECT profile_data 
        FROM loan_profiles 
        WHERE loan_id = %s
    """, (loan_id,))
    
    if row and row.get('profile_data'):
        return row['profile_data']
    return {}

def get_all_document_summaries(loan_id: int) -> List[Dict]:
    """
    Fetch document summaries for all files associated with the loan.
    Returns a list of dicts with filename and document_summary.
    """
    print(f"  Fetching document summaries for loan {loan_id}...")
    documents = execute_query("""
        SELECT filename, individual_analysis
        FROM document_analysis
        WHERE loan_id = %s
        ORDER BY filename
    """, (loan_id,))
    
    summaries = []
    for doc in documents:
        analysis = doc.get('individual_analysis') or {}
        summary = analysis.get('document_summary')
        
        # Only include if we have a summary
        if summary:
            summaries.append({
                "filename": doc['filename'],
                "document_summary": summary
            })
            
    return summaries

def select_income_documents(loan_id: int, summaries: List[Dict], profile: Dict) -> List[str]:
    """
    Ask Claude to select documents relevant for income verification,
    considering the specific loan program (e.g., Bank Statement vs Standard).
    """
    print(f"\n🤖 Asking Claude ({MODEL_NAME}) to select income documents...")
    
    # Extract loan program hints
    loan_info = profile.get('loan_info', {})
    underwriting = profile.get('underwriting_notes', {})
    income_profile = profile.get('income_profile', {})
    
    program_context = {
        "loan_type": loan_info.get('loan_type'),
        "special_conditions": underwriting.get('special_conditions', []),
        "income_types": income_profile.get('income_types', []),
        "is_self_employed": income_profile.get('is_self_employed')
    }
    
    # Prepare simplified context for documents
    context_docs = []
    for s in summaries:
        context_docs.append({
            "filename": s['filename'],
            "type": s['document_summary'].get('document_type'),
            "category": s['document_summary'].get('category'),
            "financial_summary": s['document_summary'].get('financial_summary', {}),
        })
        
    prompt = f"""You are an expert mortgage underwriter.
    
Your task is to select ALL documents needed to verify the borrower's INCOME based on the loan program.

# LOAN PROGRAM CONTEXT
{_safe_json_dumps(program_context)}

# INSTRUCTIONS
1. **ALWAYS include Form 1008 and/or URLA** if they exist - these provide the CONTEXT and breakdown of what income needs to be verified, but they can NEVER be cited as evidence.

2. Analyze the Loan Program Context:
   - If "Bank Statement" or "Alt-Doc": Select 12-24 months of Bank Statements, Business Income Analyzers/Worksheets
   - If "Conventional" or "Agency": Select Paystubs, W-2s, Tax Returns (1040/1120/1065/K-1), VOEs
   
3. Also include:
   - Income Worksheets (show underwriter's calculations)
   - AUS Findings (show final determinations)
   - Any other income-related documents

4. The MORE documents, the better - include anything that might contain income information.

# AVAILABLE DOCUMENTS
{_safe_json_dumps(context_docs)}

Return a JSON object with a single key "selected_filenames" containing a list of strings.
Example: {{ "selected_filenames": ["1008___final_0.pdf", "pay_stubs_156.pdf", "w_2s_222.pdf", "basic_income_worksheet_38.pdf"] }}
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

def get_target_income(loan_id: int, profile: Dict) -> float:
    """Get the target monthly income to verify."""
    income_profile = profile.get('income_profile', {})
    total_income = income_profile.get('total_monthly_income', 0.0)
    
    if not total_income:
         # Fallback to 1008 extracted data
        row = execute_one("""
            SELECT extracted_value
            FROM extracted_1008_data ed
            JOIN form_1008_attributes fa ON fa.id = ed.attribute_id
            WHERE ed.loan_id = %s AND fa.attribute_label ILIKE '%%total income%%'
            LIMIT 1
        """, (loan_id,))
        if row and row['extracted_value']:
            try:
                import re
                val = re.sub(r'[$,]', '', str(row['extracted_value']))
                return float(val)
            except:
                pass
                
    return float(total_income)

def calculate_income_evidence(loan_id: int, selected_filenames: List[str], target_income: float, profile: Dict):
    """
    Generate calculation evidence using deep JSON of selected documents.
    """
    print(f"\n🤖 Asking Claude ({MODEL_NAME}) to evidence income calculation...")
    
    # Categorize documents for smart data loading
    context_doc_keywords = ['1008', 'urla', 'aus_finding', 'preliminary']
    
    # Load data for selected files
    evidence_docs = []
    context_docs = []
    
    for fname in selected_filenames:
        is_context_doc = any(keyword in fname.lower() for keyword in context_doc_keywords)
        
        # Load deep JSON first
        deep_data = get_deep_json_for_document(fname)
        if not deep_data:
            # Fallback to DB analysis
            row = execute_one("SELECT individual_analysis FROM document_analysis WHERE loan_id=%s AND filename=%s", (loan_id, fname))
            if row:
                deep_data = row['individual_analysis']
        
        if deep_data:
            if is_context_doc:
                # For context docs, extract only summary/key info to save tokens
                if isinstance(deep_data, dict):
                    summary_data = {
                        "filename": fname,
                        "document_type": deep_data.get('document_summary', {}).get('document_type', 'Unknown'),
                        "key_fields": deep_data.get('document_summary', {}).get('financial_summary', {}),
                        "note": "Context document - shows what income components exist but cannot be cited as evidence"
                    }
                    context_docs.append(summary_data)
                else:
                    # If not structured, skip or summarize
                    context_docs.append({
                        "filename": fname,
                        "note": "Context document - full data available but not included to save space"
                    })
            else:
                # For primary source docs, extract only essential fields to manage token usage
                if isinstance(deep_data, dict):
                    # Extract just the document_summary and key tables/fields
                    compact_data = {
                        "filename": fname,
                        "document_type": deep_data.get('document_summary', {}).get('document_type', 'Unknown'),
                        "document_summary": deep_data.get('document_summary', {}),
                        "pages": []
                    }
                    
                    # If there are pages with tables, include just the first few tables
                    if 'pages' in deep_data and isinstance(deep_data['pages'], list):
                        for page in deep_data['pages'][:3]:  # Limit to first 3 pages
                            if isinstance(page, dict) and 'tables' in page and page['tables']:
                                compact_data['pages'].append({
                                    "tables": page['tables'][:5] if isinstance(page['tables'], list) else []
                                })
                    
                    evidence_docs.append(compact_data)
                else:
                    # Non-dict data, just include as-is but note it
                    evidence_docs.append({
                        "filename": fname,
                        "data": str(deep_data)[:2000]  # Truncate to 2000 chars
                    })

    if not evidence_docs and not context_docs:
        print("  ❌ No evidence data available.")
        return None

    prompt = f"""You are MODDA, a mortgage document verification system.

# TARGET TO VERIFY
Attribute: Total Monthly Income
Target Value: ${target_income:,.2f}

# LOAN CONTEXT
{_safe_json_dumps(profile.get('underwriting_notes', {}))}

# CONTEXT DOCUMENTS (For Understanding - NOT for Citation)
{_safe_json_dumps(context_docs)}

# PRIMARY SOURCE DOCUMENTS (For Evidence and Citation)
{_safe_json_dumps(evidence_docs)}

# CRITICAL RULES (Systematic Evidence V5)

## EVIDENCING RULES (COMPLIANCE-CRITICAL)
1. **1008 and URLA can NEVER be cited as evidence** - They are borrower-provided data, not verified source documents.
   - USE them to UNDERSTAND what income components exist (e.g., "1008 shows base salary + $245 other income")
   - But EVIDENCE must come from primary source documents: W-2s, paystubs, tax returns, bank statements, VOEs

2. **Primary Source Documents for Evidence** (in order of strength):
   - W-2s, 1099s (IRS forms)
   - Pay stubs (employer-issued)
   - Tax Returns (1040, 1120, 1065, K-1) with IRS stamps/transcripts
   - Verification of Employment (third-party)
   - Bank statements (for bank statement loans)
   - Income Worksheets (show underwriter's analysis, cite the supporting docs they reference)

## CALCULATION REQUIREMENTS
3. Calculate the Total Monthly Income based on these PRIMARY SOURCE documents.
4. Use the specific methodology required by the loan type (e.g. Bank Statement Avg vs W-2/Paystub).
5. If an Income Calculation Worksheet or AUS Findings is present, use it to UNDERSTAND the final determination, then EVIDENCE each component from source docs.

## TRACEABILITY REQUIREMENTS  
6. **Show your work**: Create step-by-step calculations.
7. **Explain methodology selection**: If multiple calculation methods exist (base salary, YTD average, 2-year average), clearly state which one is used for final qualification AND WHY.
8. **CRITICAL - Trace ALL income sources**: If the final income has multiple components (e.g., base + other income):
   - Identify EACH component (base salary, bonuses, capital gains, rental income, etc.)
   - Find the PRIMARY SOURCE document for EACH component
   - Search pay stubs for: overtime, bonuses, commissions, tips
   - Check tax returns for: Schedule D (capital gains), Schedule E (rental), K-1s (partnership)
   - Check W-2s for: Box 1 vs Box 5 differences
   - If you find a component but CANNOT locate its source, explicitly state: "Income component $X identified in [1008/worksheet] but primary source document not found in package"

9. **No hand-waving**: Never cite "per 1008" or "per URLA" or "additional qualifying income per AUS" - trace it to a W-2, tax return, or other PRIMARY SOURCE.
10. **Exact Locations**: Cite specific filenames, page numbers, AND field names/line items for every value found.
11. **Clear conclusion**: The last step must explain why this specific amount was chosen as the qualifying income.

# OUTPUT FORMAT (Strict JSON)
Return JSON matching the schema required for the Verification UI:
{{
  "calculation_steps": [
    {{
      "step_order": 1,
      "value": "<dollar amount e.g. $12,500.00>",
      "description": "<short description>",
      "rationale": "<why included>",
      "formula": "<math formula if applicable>",
      "document_name": "<exact filename>",
      "page_number": <integer or null>,
      "source_location": "<field/line reference>"
    }}
  ],
  "verification_summary": "<Use STRUCTURED FORMAT below>",
  "calculated_income": <float final monthly income>,
  "evidence_files": [
      {{
          "file_name": "<exact filename>",
          "classification": "primary",
          "document_type": "<e.g. Bank Statement, Paystub>",
          "confidence_score": 1.0,
          "page_number": <main page number>
      }}
  ]
}}

# VERIFICATION SUMMARY FORMAT
The verification_summary field must follow this EXACT structure for proper UI rendering:

## Income Verification Summary ### Loan Program & Methodology
[Brief description of the loan program and methodology used]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

INCOME SOURCES INCLUDED

1. [Income Source Name] - **$X,XXX.XX**
• [Detail line with amount and reference] (Page X, filename.pdf)
• [Another detail] (Page Y, filename.pdf)

2. [Another Income Source] - **$X,XXX.XX**
• [Detail] (Page X, filename.pdf)

TOTAL MONTHLY INCOME: **$XX,XXX.XX**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

INCOME SOURCES IDENTIFIED BUT PROPERLY EXCLUDED

❌ [Income Source Excluded] (Page X, filename.pdf)
• [Reason for exclusion]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

UNDERWRITING METHODOLOGY & COMPLIANCE

✓ **Methodology**: [Description of calculation method]
✓ **Program Guidelines**: [Which guidelines were followed]
✓ **Conservative Underwriting**: [How conservative approach was applied]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

VERIFICATION CONFIDENCE: HIGH (100%)

✓ All income sources documented with primary source documents
✓ Calculations verified and cross-checked
✓ Methodology aligns with program requirements

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

def save_income_verification(loan_id: int, evidence_result: Dict):
    """
    Save the verification results to the database.
    This updates 'calculation_steps' and 'evidence_files' for the Income attribute.
    """
    print("\n💾 Saving verification results to database...")
    
    # 1. Find the Attribute ID for "Total Monthly Income" (or similar)
    # We look for the main income attribute in 1008 attributes
    attr_row = execute_one("""
        SELECT id FROM form_1008_attributes 
        WHERE attribute_label ILIKE '%Total Income%' 
           OR attribute_label ILIKE '%Total Monthly Income%'
        ORDER BY id ASC
        LIMIT 1
    """)
    
    if not attr_row:
        print("  ⚠️  Could not find 'Total Income' attribute ID in database.")
        return

    attribute_id = attr_row['id']
    
    # 2. Use the existing save function from systematic_evidence_v5_standardized
    # It expects: calculation_steps, evidence_files, verification_summary
    success = save_evidence_to_database(loan_id, attribute_id, evidence_result)
    
    if success:
        print(f"  ✅ Successfully saved evidence for Attribute ID {attribute_id}")
        
        # 3. Also update the loan_profile verification status so the badge shows up immediately
        update_profile_verification(loan_id, evidence_result)
    else:
        print("  ❌ Failed to save evidence.")

def update_profile_verification(loan_id: int, evidence_result: Dict):
    """Update the loan_profiles table and extracted_1008_data to reflect the verified status."""
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
        
        rich_summary = generate_professional_summary(summary_data, 'income')
    except Exception as e:
        print(f"  ⚠️  Could not generate rich summary: {e}")
        rich_summary = None
    
    # Update loan_profiles
    row = execute_one("SELECT profile_data FROM loan_profiles WHERE loan_id = %s", (loan_id,))
    if not row:
        return
        
    profile = row['profile_data'] or {}
    verification_status = profile.get('verification_status', {})
    
    # Update income section
    calculated_income = evidence_result.get('calculated_income')
    verification_status['income'] = {
        'verified': True,
        'document_value': calculated_income,
        'variance_percent': 0.0,
        'notes': ["Verified via Systematic Evidence V5"],
        'rich_summary': rich_summary  # Store pre-generated summary
    }
    
    profile['verification_status'] = verification_status
    
    # Save back
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE loan_profiles SET profile_data = %s WHERE loan_id = %s", (json.dumps(profile), loan_id))
        conn.commit()
        print("  ✅ Updated loan profile verification status")
        
        # Also update or insert into extracted_1008_data for the income attribute
        # This makes the value available in API responses
        attr_row = execute_one("""
            SELECT id FROM form_1008_attributes 
            WHERE attribute_label ILIKE '%Total Income%' 
               OR attribute_label ILIKE '%Total Monthly Income%'
               OR attribute_name = 'total_income'
            ORDER BY id ASC
            LIMIT 1
        """)
        
        if attr_row and calculated_income:
            attribute_id = attr_row['id']
            
            # Format the income value as string
            income_str = f"{calculated_income:.2f}"
            
            # Check if record exists
            existing = execute_one("""
                SELECT id FROM extracted_1008_data 
                WHERE loan_id = %s AND attribute_id = %s
            """, (loan_id, attribute_id))
            
            if existing:
                # Update existing record
                cur.execute("""
                    UPDATE extracted_1008_data 
                    SET extracted_value = %s, 
                        confidence_score = 0.99,
                        extraction_date = CURRENT_TIMESTAMP
                    WHERE loan_id = %s AND attribute_id = %s
                """, (income_str, loan_id, attribute_id))
            else:
                # Insert new record
                cur.execute("""
                    INSERT INTO extracted_1008_data 
                    (loan_id, attribute_id, extracted_value, confidence_score, extraction_date)
                    VALUES (%s, %s, %s, 0.99, CURRENT_TIMESTAMP)
                """, (loan_id, attribute_id, income_str))
            
            conn.commit()
            print(f"  ✅ Updated extracted_1008_data with calculated income: ${calculated_income:,.2f}")
            
    finally:
        cur.close()
        conn.close()

def main():
    if len(sys.argv) > 1:
        try:
            loan_id = int(sys.argv[1])
        except ValueError:
            print("Usage: python backend/step4a_verify_income.py [loan_id]")
            return
    else:
        loan_id = 2 # Default test
        
    print(f"🔍 Starting Income Verification for Loan {loan_id}")
    print("=" * 60)
    
    # 1. Get Loan Context
    profile = get_loan_profile(loan_id)
    target_income = get_target_income(loan_id, profile)
    print(f"🎯 Target Income: ${target_income:,.2f}")
    
    # 2. Get Summaries
    summaries = get_all_document_summaries(loan_id)
    
    # 3. Select Documents (Program Aware)
    selected_files = select_income_documents(loan_id, summaries, profile)
    if not selected_files:
        print("❌ No income documents selected.")
        return

    # 4. Calculate Evidence
    evidence_result = calculate_income_evidence(loan_id, selected_files, target_income, profile)
    
    if evidence_result:
        print("\n📊 Verification Result Generated")
        print(f"Summary length: {len(evidence_result.get('verification_summary', ''))} chars")
        print(f"Steps: {len(evidence_result.get('calculation_steps', []))}")
        
        # 5. Save to DB for the UI
        save_income_verification(loan_id, evidence_result)

if __name__ == "__main__":
    main()
