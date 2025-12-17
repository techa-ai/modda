import sys
import json
import traceback
from db import get_db_connection
from bedrock_config import call_bedrock
from processing import extract_json_from_text

def analyze_amortization(loan_id, attribute_label):
    print(f"🧮 Running Math Forensics for '{attribute_label}' (Loan {loan_id})...")
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # 1. Get Target Value
        cur.execute("""
            SELECT ed.extracted_value, fa.id as attr_id
            FROM extracted_1008_data ed
            JOIN form_1008_attributes fa ON fa.id = ed.attribute_id
            WHERE ed.loan_id = %s AND fa.attribute_label = %s
        """, (loan_id, attribute_label))
        res = cur.fetchone()
        if not res:
            print("Attribute not found.")
            return
            
        target_val_str = res['extracted_value']
        attr_id = res['attr_id']
        
        # 2. Get Context (Balance, Rate, Term) from other extracted data
        cur.execute("""
            SELECT fa.attribute_label, ed.extracted_value 
            FROM extracted_1008_data ed
            JOIN form_1008_attributes fa ON fa.id = ed.attribute_id
            WHERE ed.loan_id = %s
        """, (loan_id,))
        context_data = {r['attribute_label']: r['extracted_value'] for r in cur.fetchall()}
        
        prompt = f"""
You are a Financial Forensics Expert.
We have a mortgage payment amount that DOES NOT match standard calculations based on the documents.
Your goal is to reverse-engineer the formula used to derive this specific number.

TARGET ATTRIBUTE: {attribute_label}
TARGET VALUE: {target_val_str}

AVAILABLE CONTEXT (Extracted from 1008):
{json.dumps(context_data, indent=2)}

TASK:
1. Identify the likely components (Balance, Rate, Term).
2. If Balance/Rate are not explicit, look for "Original Loan Amount", "Unpaid Balance", "Note Rate".
3. Try these calculation methods to match the TARGET VALUE exactly (within $0.05):
   - Interest Only (Balance * Rate / 12)
   - Standard Amortization (30yr, 20yr, 15yr, 10yr)
   - Non-Standard Amortization (e.g. 18yr, 25yr, 22yr) - HELOCs often use "Repayment Period" only.
   - Bi-weekly payments?
   - Rate variations (e.g. Rate + Margin, or Qualifying Rate = Rate + 2%)

OUTPUT FORMAT (JSON):
{{
  "match_found": boolean,
  "methodology": "Name of method (e.g. 18-Year Amortization)",
  "calculated_value": "Number",
  "formula_description": "Explanation of formula",
  "formula_math": "Mathematical string (e.g. P*r...)",
  "parameters": {{ "balance": "...", "rate": "...", "term_months": "..." }},
  "confidence": "high|medium|low"
}}
"""

        response = call_bedrock(prompt, model='claude-opus-4-5', max_tokens=2000)
        result = extract_json_from_text(response)
        
        if result and result.get('match_found'):
            print(f"✅ MATCH FOUND: {result['methodology']}")
            print(f"   Value: {result['calculated_value']}")
            print(f"   Params: {result['parameters']}")
            
            # Save to DB (Update Evidence)
            notes = {
                "verified": True,
                "mismatch_reason": None,
                "methodology": result['methodology'],
                "forensic_analysis": result
            }
            
            # Update Evidence Status
            cur.execute("""
                UPDATE evidence_files 
                SET verification_status='verified', notes=%s, file_name='Calculated (Forensic)'
                WHERE loan_id=%s AND attribute_id=%s
            """, (json.dumps(notes), loan_id, attr_id))
            
            # Update Steps
            cur.execute("DELETE FROM calculation_steps WHERE loan_id=%s AND attribute_id=%s", (loan_id, attr_id))
            
            steps = [
                {'desc': 'Loan Balance', 'val': str(result['parameters'].get('balance'))},
                {'desc': 'Interest Rate', 'val': str(result['parameters'].get('rate'))},
                {'desc': 'Derived Term/Method', 'val': result['methodology'], 'rationale': 'Reverse-engineered to match target.'},
                {'desc': 'Calculated Payment', 'val': str(result['calculated_value']), 'formula': result.get('formula_math')}
            ]
            
            for idx, s in enumerate(steps):
                cur.execute("""
                    INSERT INTO calculation_steps (loan_id, attribute_id, step_order, description, value, formula, rationale, document_name)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'Calculated')
                """, (loan_id, attr_id, idx+1, s['desc'], s['val'], s.get('formula'), s.get('rationale')))
                
            conn.commit()
            print("   ✨ Database updated with forensic evidence.")
        else:
            print("❌ No match found by Claude.")
            
    except Exception as e:
        print(f"Error: {e}")
        traceback.print_exc()
        
    conn.close()

if __name__ == "__main__":
    if len(sys.argv) > 2:
        analyze_amortization(int(sys.argv[1]), sys.argv[2])
