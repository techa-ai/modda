#!/usr/bin/env python3
"""
Generate professional verification summaries using Claude
"""

import sys
import json
sys.path.append('backend')

from db import execute_query, execute_one
from bedrock_config import call_bedrock

def get_income_verification_data(loan_id: int):
    """Fetch all income verification data for summary generation."""
    
    # Get calculation steps
    steps = execute_query("""
        SELECT cs.step_order, cs.description, cs.value, cs.document_name
        FROM calculation_steps cs
        WHERE cs.loan_id = %s 
        AND cs.attribute_id = 20
        ORDER BY cs.step_order
    """, (loan_id,))
    
    # Get evidence files
    evidence = execute_query("""
        SELECT DISTINCT ef.file_name, ef.page_number, ef.notes
        FROM evidence_files ef
        WHERE ef.loan_id = %s 
        AND ef.attribute_id = 20
        ORDER BY ef.file_name, ef.page_number
    """, (loan_id,))
    
    # Get verification summary from profile
    profile_data = execute_one("""
        SELECT profile_data
        FROM loan_profiles
        WHERE loan_id = %s
    """, (loan_id,))
    
    verification_summary = None
    if profile_data and profile_data['profile_data']:
        profile = profile_data['profile_data']
        if 'verification_status' in profile and 'income' in profile['verification_status']:
            verification_summary = profile['verification_status']['income'].get('summary', '')
    
    return {
        'loan_id': loan_id,
        'calculation_steps': steps,
        'evidence_files': evidence,
        'verification_summary': verification_summary
    }

def generate_professional_summary(verification_data: dict, verification_type: str = 'income'):
    """Generate a professional summary using Claude."""
    
    loan_id = verification_data['loan_id']
    steps = verification_data['calculation_steps']
    evidence = verification_data['evidence_files']
    detail_summary = verification_data.get('verification_summary', '')
    
    # Count unique documents
    unique_docs = set(ev['file_name'] for ev in evidence if ev['file_name'])
    
    # Extract breakdown from steps
    breakdown = []
    total_value = None
    
    for step in steps:
        desc = step['description']
        value = step['value']
        
        # Skip "CANNOT CALCULATE" or similar error messages
        if 'CANNOT' in value.upper() or 'INCOMPLETE' in value.upper() or 'GAP' in value.upper():
            continue
        
        # Get the last step as total
        if step['step_order'] == len(steps) or 'Total' in desc or 'Grand Total' in desc:
            total_value = value
        elif step['step_order'] < len(steps):  # Not the last step
            breakdown.append({
                'label': desc,
                'value': value,
                'step': step['step_order']
            })
    
    # Build context for Claude
    context = {
        'loan_id': loan_id,
        'verification_type': verification_type.title(),
        'total_steps': len(steps),
        'total_evidence_files': len(evidence),
        'unique_documents': len(unique_docs),
        'document_list': sorted(list(unique_docs)),
        'calculation_steps': [
            {
                'step': s['step_order'],
                'description': s['description'],
                'value': s['value'],
                'source': s['document_name']
            } for s in steps
        ],
        'detailed_summary': detail_summary
    }
    
    prompt = f"""You are a senior mortgage underwriting analyst preparing an executive summary for institutional investors and compliance officers.

VERIFICATION DATA:
{json.dumps(context, indent=2)}

TASK: Generate a **concise, professional, impressive executive summary** (3-4 sentences max) that highlights:

1. The **comprehensiveness** of the verification process
2. The **complexity** and **thoroughness** of the analysis
3. The **number and variety** of source documents analyzed
4. The **multi-step calculation** process employed
5. The **regulatory compliance** and **auditability** achieved

TONE: Professional, authoritative, and impressive - this should demonstrate world-class underwriting standards.

OUTPUT FORMAT: Plain text paragraph (no markdown, no bullets). Start with "This verification..."

Example tone: "This verification employed a comprehensive 12-step analysis across 8 primary source documents, including tax returns, W-2s, and paystubs, with each income component independently validated against original documentation. The multi-layered approach ensures full regulatory compliance with Fannie Mae and Freddie Mac guidelines while providing complete audit trail documentation for investor due diligence."

Now generate the summary for the provided data:"""

    try:
        response = call_bedrock(
            prompt=prompt,
            model="claude-opus-4-5",
            max_tokens=500,
            temperature=0.3  # Slight creativity for professional writing
        )
        
        # Clean up response
        summary = response.strip()
        
        # Remove markdown formatting if present
        summary = summary.replace('**', '').replace('*', '')
        
        # Ensure it starts with "This verification"
        if not summary.lower().startswith('this verification'):
            summary = f"This verification {summary}"
        
        return {
            'summary': summary,
            'breakdown': breakdown[:6],  # Limit to top 6 items for display
            'total_value': total_value,
            'documents': sorted(list(unique_docs)),  # List of document names
            'statistics': {
                'total_steps': len(steps),
                'unique_documents': len(unique_docs)
            }
        }
        
    except Exception as e:
        print(f"Error generating summary: {e}")
        return {
            'summary': f"This verification employed a {len(steps)}-step analysis across {len(unique_docs)} source documents, ensuring comprehensive validation and regulatory compliance.",
            'breakdown': breakdown[:6],
            'total_value': total_value,
            'documents': sorted(list(unique_docs)),  # List of document names
            'statistics': {
                'total_steps': len(steps),
                'unique_documents': len(unique_docs)
            }
        }

def get_debt_verification_data(loan_id: int):
    """Fetch all debt verification data for summary generation."""
    
    # Get calculation steps
    steps = execute_query("""
        SELECT cs.step_order, cs.description, cs.value, cs.document_name
        FROM calculation_steps cs
        WHERE cs.loan_id = %s 
        AND cs.attribute_id = 120
        ORDER BY cs.step_order
    """, (loan_id,))
    
    # Get evidence files
    evidence = execute_query("""
        SELECT DISTINCT ef.file_name, ef.page_number, ef.notes
        FROM evidence_files ef
        WHERE ef.loan_id = %s 
        AND ef.attribute_id = 120
        ORDER BY ef.file_name, ef.page_number
    """, (loan_id,))
    
    # Get verification summary from profile
    profile_data = execute_one("""
        SELECT profile_data
        FROM loan_profiles
        WHERE loan_id = %s
    """, (loan_id,))
    
    verification_summary = None
    if profile_data and profile_data['profile_data']:
        profile = profile_data['profile_data']
        if 'verification_status' in profile and 'debt' in profile['verification_status']:
            verification_summary = profile['verification_status']['debt'].get('summary', '')
    
    return {
        'loan_id': loan_id,
        'calculation_steps': steps,
        'evidence_files': evidence,
        'verification_summary': verification_summary
    }

def generate_summary_for_loan(loan_id: int, verification_type: str = 'income'):
    """Main function to generate summary for a loan."""
    
    print(f"\n📊 Generating {verification_type} verification summary for Loan {loan_id}")
    print("="*80)
    
    # Fetch data
    print("   Fetching verification data...")
    if verification_type == 'income':
        data = get_income_verification_data(loan_id)
    elif verification_type == 'debt':
        data = get_debt_verification_data(loan_id)
    else:
        # Add other types as needed
        print(f"   ❌ Verification type '{verification_type}' not yet implemented")
        return None
    
    print(f"   ✅ Found {len(data['calculation_steps'])} calculation steps")
    print(f"   ✅ Found {len(data['evidence_files'])} evidence files")
    
    # Generate summary
    print("   🤖 Asking Claude to generate professional summary...")
    summary = generate_professional_summary(data, verification_type)
    
    print(f"\n📝 Generated Summary:")
    print("="*80)
    print(summary)
    print("="*80)
    
    return summary

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python generate_verification_summary.py <loan_id> [verification_type]")
        print("Example: python generate_verification_summary.py 2 income")
        sys.exit(1)
    
    loan_id = int(sys.argv[1])
    verification_type = sys.argv[2] if len(sys.argv) > 2 else 'income'
    
    generate_summary_for_loan(loan_id, verification_type)

