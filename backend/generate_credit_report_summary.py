#!/usr/bin/env python3
"""
Generate comprehensive credit report summary with focus on derogatory accounts
using Claude Opus 4.5.
"""

import sys
import json
sys.path.append('backend')

from db import execute_query, execute_one, get_db_connection
from bedrock_config import call_bedrock

def get_credit_report_data(loan_id: int):
    """Fetch credit report documents and their deep JSON analysis."""
    
    # Get credit report documents
    docs = execute_query(f"""
        SELECT 
            id,
            filename,
            individual_analysis,
            file_path
        FROM document_analysis
        WHERE loan_id = {loan_id}
        AND filename ILIKE '%credit%report%'
        AND master_document_id IS NULL
        ORDER BY filename
    """)
    
    if not docs:
        print(f"  ❌ No credit reports found for loan {loan_id}")
        return None
    
    return docs

def get_loan_profile(loan_id: int):
    """Get loan profile for context."""
    row = execute_one("""
        SELECT profile_data FROM loan_profiles WHERE loan_id = %s
    """, (loan_id,))
    
    if row and row['profile_data']:
        return row['profile_data']
    return {}

def generate_credit_summary(loan_id: int, credit_docs: list, profile: dict):
    """Generate comprehensive credit report summary using Claude Opus 4.5."""
    
    credit_profile = profile.get('credit_profile', {})
    credit_score = credit_profile.get('credit_score', 'N/A')
    
    # Prepare document data for Claude
    doc_data = []
    for doc in credit_docs:
        doc_info = {
            'filename': doc['filename'],
            'deep_analysis': doc.get('individual_analysis', {})
        }
        doc_data.append(doc_info)
    
    prompt = f"""You are MODDA, a senior credit risk analyst preparing a comprehensive credit report summary for institutional investors and underwriters.

LOAN CONTEXT:
- Loan ID: {loan_id}
- Reported Credit Score: {credit_score}

CREDIT REPORT DATA:
{json.dumps(doc_data, indent=2)}

TASK: Generate a comprehensive credit report summary that includes:

1. **CREDIT SCORE VERIFICATION**
   - Tri-merge score analysis (Equifax, Experian, TransUnion)
   - Middle score selection methodology
   - Score consistency across bureaus

2. **DEROGATORY ACCOUNTS & RED FLAGS** (CRITICAL FOCUS)
   - Late payments (30/60/90/120+ days)
   - Collections and charge-offs
   - Bankruptcies (Chapter 7, 11, 13)
   - Foreclosures or short sales
   - Tax liens and judgments
   - Repossessions
   - **For each derogatory item, specify:**
     * Type of derogatory
     * Creditor name
     * Amount
     * Date opened/reported
     * Current status
     * Impact on loan qualification

3. **CREDIT UTILIZATION ANALYSIS**
   - Total revolving credit available
   - Total revolving credit used
   - Utilization ratio (% used)
   - High-balance accounts

4. **TRADELINE ANALYSIS**
   - Number of open accounts
   - Number of closed accounts
   - Oldest account age (credit history depth)
   - Recent inquiries (last 6 months)
   - Account mix (revolving, installment, mortgage)

5. **PAYMENT HISTORY PERFORMANCE**
   - Percentage of on-time payments
   - Recent payment patterns (last 12-24 months)
   - Trend analysis (improving/stable/deteriorating)

6. **PUBLIC RECORDS**
   - Bankruptcies, liens, judgments
   - Dates and amounts
   - Current status

7. **UNDERWRITING RISK ASSESSMENT**
   - Overall credit risk rating (Excellent/Good/Fair/Poor)
   - Key compensating factors (if any)
   - Key risk factors requiring explanation
   - Fannie Mae/Freddie Mac guideline compliance
   - Recommendation (Approve/Approve with Conditions/Decline)

8. **COMPLIANCE & DOCUMENTATION**
   - FCRA compliance verification
   - Data completeness assessment
   - Any missing or inconsistent information

FORMATTING REQUIREMENTS:
- Use clear section headers (matching the 8 sections above)
- For derogatory accounts, use a structured table format:
  | Type | Creditor | Amount | Date | Status | Impact |
- Use bullet points for lists
- Include specific dollar amounts and dates
- Cite specific tradeline references from the credit report
- Be objective, thorough, and investor-grade quality
- If NO derogatory accounts exist, explicitly state: "NO DEROGATORY ACCOUNTS FOUND - Clean credit history"

TONE: Professional, analytical, comprehensive, suitable for underwriting review and investor due diligence.

Generate the comprehensive credit report summary:"""

    try:
        print("  🤖 Generating credit summary with Claude Opus 4.5...")
        response = call_bedrock(
            prompt=prompt,
            model="claude-opus-4-5",
            max_tokens=4000,
            temperature=0.3
        )
        return response.strip()
    except Exception as e:
        print(f"  ❌ Error generating credit summary: {e}")
        return None

def generate_executive_summary(loan_id: int, credit_score: int, full_summary: str):
    """Generate a concise executive summary for Risk Assessment display."""
    
    prompt = f"""You are MODDA, summarizing a credit report for executive review.

LOAN ID: {loan_id}
CREDIT SCORE: {credit_score}

FULL CREDIT ANALYSIS:
{full_summary[:2000]}... [truncated]

TASK: Generate a concise 2-3 sentence executive summary for the Risk Assessment section that:
1. States the credit score and its rating (Excellent/Good/Fair/Poor)
2. Highlights the MOST CRITICAL finding (e.g., bankruptcy, high utilization, derogatory accounts)
3. Notes any key mitigating factors (e.g., recent positive payment history, accounts since discharge)

TONE: Professional, concise, executive-level
FORMAT: Plain text, 2-3 sentences only, no markdown

Example: "Credit score of 666 reflects subprime rating primarily due to Chapter 7 bankruptcy discharged in May 2019 with $1.17M in debt including 12 accounts. Post-bankruptcy performance demonstrates strong rehabilitation with 6 years of perfect payment history on new accounts, though current 73% credit utilization remains a concern."

Generate the executive summary:"""

    try:
        response = call_bedrock(
            prompt=prompt,
            model="claude-opus-4-5",
            max_tokens=300,
            temperature=0.3
        )
        return response.strip()
    except Exception as e:
        print(f"  ❌ Error generating executive summary: {e}")
        return None

def save_credit_summary(loan_id: int, summary: str, executive_summary: str = None):
    """Save credit summary to loan profiles."""
    
    # Get existing profile
    row = execute_one("""
        SELECT profile_data FROM loan_profiles WHERE loan_id = %s
    """, (loan_id,))
    
    if not row or not row['profile_data']:
        print(f"  ❌ No profile found for loan {loan_id}")
        return False
    
    profile = row['profile_data']
    
    # Update verification status with credit summary
    if 'verification_status' not in profile:
        profile['verification_status'] = {}
    
    if 'credit_score' not in profile['verification_status']:
        profile['verification_status']['credit_score'] = {}
    
    profile['verification_status']['credit_score']['detailed_summary'] = summary
    profile['verification_status']['credit_score']['executive_summary'] = executive_summary
    profile['verification_status']['credit_score']['summary_generated'] = True
    
    # Save to database
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE loan_profiles 
            SET profile_data = %s
            WHERE loan_id = %s
        """, (json.dumps(profile), loan_id))
        conn.commit()
        print(f"  ✅ Credit summary saved to database")
        return True
    except Exception as e:
        print(f"  ❌ Error saving credit summary: {e}")
        return False
    finally:
        cur.close()
        conn.close()

def generate_credit_report_summary_for_loan(loan_id: int):
    """Main function to generate credit report summary."""
    
    print(f"\n🔍 Generating Credit Report Summary for Loan {loan_id}")
    print("="*80)
    
    # Get credit report data
    print("  📄 Fetching credit report documents...")
    credit_docs = get_credit_report_data(loan_id)
    if not credit_docs:
        return
    
    print(f"  ✅ Found {len(credit_docs)} credit report document(s)")
    
    # Get loan profile
    print("  📊 Fetching loan profile...")
    profile = get_loan_profile(loan_id)
    
    # Generate summary
    summary = generate_credit_summary(loan_id, credit_docs, profile)
    
    if not summary:
        return
    
    print(f"\n📝 Credit Report Summary:")
    print("="*80)
    print(summary)
    print("="*80)
    
    # Generate executive summary
    print(f"\n📋 Generating executive summary...")
    credit_score = profile.get('credit_profile', {}).get('credit_score', 0)
    executive_summary = generate_executive_summary(loan_id, credit_score, summary)
    
    if executive_summary:
        print(f"\n📋 Executive Summary:")
        print("="*80)
        print(executive_summary)
        print("="*80)
    
    # Save to database
    print(f"\n💾 Saving to database...")
    save_credit_summary(loan_id, summary, executive_summary)
    
    print(f"\n✅ Credit report summary generated successfully!")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python generate_credit_report_summary.py <loan_id>")
        sys.exit(1)
    
    loan_id = int(sys.argv[1])
    generate_credit_report_summary_for_loan(loan_id)

