"""
Generate comprehensive loan summary using Claude via Bedrock.
Collects all document summaries and synthesizes a comprehensive overview.
"""

import os
import json
from db import execute_query, execute_one
from bedrock_config import call_bedrock

def get_document_summaries(loan_id):
    """Fetch all document summaries for a loan"""
    # Get active schema
    schema = os.getenv('ACTIVE_SCHEMA', 'public')
    doc_table = f"{schema}.document_analysis" if schema != 'public' else "document_analysis"
    
    # Get individual document analyses/summaries
    docs = execute_query(f"""
        SELECT filename, individual_analysis, vlm_analysis
        FROM {doc_table}
        WHERE loan_id = %s
        AND status IN ('unique', 'master')
        AND (individual_analysis IS NOT NULL OR vlm_analysis IS NOT NULL)
        ORDER BY filename
    """, (loan_id,))
    
    summaries = []
    for doc in docs:
        summary = doc.get('individual_analysis') or doc.get('vlm_analysis') or ''
        if summary:
            # Convert to string if it's a dict
            if isinstance(summary, dict):
                summary = json.dumps(summary, default=str)
            summary_str = str(summary)[:2000]  # Truncate very long summaries
            summaries.append({
                'filename': doc['filename'],
                'summary': summary_str
            })
    
    return summaries


def get_loan_profile(loan_id):
    """Get loan profile data"""
    profile = execute_one("""
        SELECT profile_data
        FROM loan_profiles
        WHERE loan_id = %s
    """, (loan_id,))
    
    return profile['profile_data'] if profile else None


def generate_loan_summary(loan_id):
    """Generate comprehensive loan summary using Claude via Bedrock"""
    
    # Get loan info
    loan = execute_one("SELECT loan_number FROM loans WHERE id = %s", (loan_id,))
    if not loan:
        return None
    
    # Get all document summaries
    doc_summaries = get_document_summaries(loan_id)
    
    # Get loan profile
    profile = get_loan_profile(loan_id)
    
    # Build prompt
    prompt = f"""You are an expert mortgage underwriter. Analyze the following loan documentation and provide a comprehensive loan summary.

## Loan Number: {loan['loan_number']}

"""
    
    # Add profile if available
    if profile:
        prompt += """## Loan Profile Data
```json
"""
        prompt += json.dumps(profile, indent=2, default=str)[:4000]  # Truncate if too long
        prompt += """
```

"""
    
    # Add document summaries
    if doc_summaries:
        prompt += "## Document Summaries\n\n"
        for doc in doc_summaries:
            prompt += f"### {doc['filename']}\n"
            prompt += f"{doc['summary']}\n\n"
    
    prompt += """
## Instructions
Create a comprehensive loan summary covering:

1. **Loan Overview**: Key details (loan amount, type, purpose, term, rate)
2. **Borrower Profile**: Income sources, employment, assets, credit score
3. **Property Details**: Address, type, value, appraisal findings
4. **Key Ratios**: DTI, LTV, CLTV, HCLTV with assessment
5. **Risk Factors**: Any concerns or flags identified
6. **Document Completeness**: Missing or incomplete documentation
7. **Underwriting Notes**: Special considerations or exceptions

Format your response in markdown with clear sections and bullet points for easy readability.
Be concise but thorough - aim for 500-800 words.
"""

    try:
        # Use Bedrock via call_bedrock function (using Claude Haiku 4.5 for speed)
        summary = call_bedrock(prompt, model='claude-haiku-4-5', max_tokens=2000)
        
        # Try to save to database (column may not exist)
        try:
            execute_query("""
                UPDATE loans
                SET kg_summary = %s
                WHERE id = %s
            """, (summary, loan_id), fetch=False)
        except Exception as db_err:
            print(f"Could not save summary to DB: {db_err}")
        
        return summary
        
    except Exception as e:
        print(f"Error generating loan summary: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        loan_id = int(sys.argv[1])
        summary = generate_loan_summary(loan_id)
        if summary:
            print(summary)
        else:
            print("Failed to generate summary")
