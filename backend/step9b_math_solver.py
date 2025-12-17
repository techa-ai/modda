import sys
import json
from db import get_db_connection, execute_query
from bedrock_config import call_bedrock
from processing import extract_json_from_text

def run_math_solver(loan_id):
    print(f"🧮 Running Math Solver (Step 9b) for Loan {loan_id}...")
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 1. Identify Unverified Payment Attributes
    # We look for P&I attributes that are Not Verified
    cur.execute("""
        SELECT ef.id as evidence_id, fa.attribute_label, ed.extracted_value, fa.id as attr_id
        FROM evidence_files ef
        JOIN form_1008_attributes fa ON fa.id = ef.attribute_id
        JOIN extracted_1008_data ed ON ed.attribute_id = fa.id AND ed.loan_id = ef.loan_id
        WHERE ef.loan_id = %s 
        AND ef.verification_status = 'not_verified'
        AND (fa.attribute_label ILIKE '%%P&I%%' OR fa.attribute_label ILIKE '%%Payment%%')
        AND ed.extracted_value IS NOT NULL
    """, (loan_id,))
    
    targets = cur.fetchall()
    if not targets:
        print("   No unverified payment attributes found.")
        return

    # 2. Gather Context (Balance, Rate, Terms from VERIFIED or EXTRACTED data)
    # We fetch EVERYTHING extracted to give Claude context
    cur.execute("""
        SELECT fa.attribute_label, ed.extracted_value, fa.id as attr_id
        FROM extracted_1008_data ed
        JOIN form_1008_attributes fa ON fa.id = ed.attribute_id
        WHERE ed.loan_id = %s
    """, (loan_id,))
    
    context_items = {}
    is_second_mortgage_1008 = False
    for row in cur.fetchall():
        label = row['attribute_label']
        val = row['extracted_value']
        attr_id = row['attr_id']
        key = f"{label} (ID: {attr_id})"
        context_items[key] = val
        
        # Check if this is a Second Mortgage 1008 (meaning we don't know First Mortgage terms)
        if label == 'Second Mortgage' and str(val).lower() == 'true':
            is_second_mortgage_1008 = True
    
    # 3. Solve Each Target
    for t in targets:
        label = t['attribute_label']
        val = t['extracted_value']
        
        # SKIP First Mortgage P&I if this is a Second Mortgage 1008
        # We don't know the first mortgage rate/balance to reverse engineer
        if 'First Mortgage' in label and is_second_mortgage_1008:
            print(f"\n   ⏭️ Skipping {label} - this is a Second Mortgage 1008, first mortgage terms unknown")
            continue
            
        print(f"\n   🔍 Attempting to solve: {label} ({val})")
        
        prompt = f"""
You are a Mortgage Mathematics Expert.
The attribute "{label}" with value "{val}" was found in the loan file but could not be directly verified in documents.
It is likely a CALCULATED value derived from other loan parameters (Balance, Rate, Term).

CONTEXT (Known Loan Parameters with IDs):
{json.dumps(context_items, indent=2)}

TASK:
Reverse-engineer the formula that yields exactly "{val}".

INVESTIGATION STEPS:
1. Identify relevant parameters in CONTEXT (e.g. Loan Amount, Note Rate, HELOC Balance, Second Mtg Amount).
   - Note: "Second Mortgage P&I" usually relates to "Amount of Subordinate Financing" or "HELOC Balance".
2. Test Calculation Methods:
   - Interest Only: Balance * Rate / 12
   - Standard Amortization: P * (r(1+r)^n) / ((1+r)^n - 1)
   - Test Terms: 30yr, 20yr, 15yr, 10yr.
   - **CRITICAL**: Test non-standard terms (e.g. 18 years, 22 years) if standard ones fail. Lenders often use "Remaining Term" or specific qualification terms.
   - Percentage of Balance: 1%, 1.5%, etc.
3. If you find a match (within $0.05), report it.

OUTPUT FORMAT (JSON):
{{
  "solved": true,
  "formula_name": "18-Year Amortization",
  "formula_description": "Standard amortization of $300,000 at 8.5% over 216 months.",
  "parameters": {{ "balance": "$300,000", "rate": "8.5%", "term": "216 months" }},
  "steps": [
    {{ "desc": "Identify Balance", "val": "$300,000", "doc": "See ID - 50" }},
    {{ "desc": "Identify Rate", "val": "8.5%", "doc": "See ID - 51" }},
    {{ "desc": "Identify Derived Term", "val": "18 Years", "doc": "Calculated" }},
    {{ "desc": "Calculation", "val": "{val}", "formula": "...", "doc": "Calculated" }}
  ]
}}

If a step uses a value from CONTEXT, set "doc" to "See ID - X". If derived/calculated, set "doc" to "Calculated".

If not solved, return {{ "solved": false }}.
"""
        try:
            response = call_bedrock(prompt, model='claude-opus-4-5', max_tokens=2000)
            result = extract_json_from_text(response)
            
            if result and result.get('solved'):
                print(f"      ✅ SOLVED! {result['formula_name']}")
                
                # Update Evidence
                note = {
                    "verified": True,
                    "mismatch_reason": None,
                    "methodology": result['formula_description'],
                    "auto_solved": True
                }
                cur.execute("""
                    UPDATE evidence_files 
                    SET verification_status = 'verified', notes = %s
                    WHERE id = %s
                """, (json.dumps(note), t['evidence_id']))
                
                # Update Steps
                # First delete old steps
                cur.execute("DELETE FROM calculation_steps WHERE loan_id = %s AND attribute_id = %s", (loan_id, t['attr_id']))
                
                for idx, step in enumerate(result['steps']):
                    formula = step.get('formula')
                    doc_name = step.get('doc', 'Calculated')
                    cur.execute("""
                        INSERT INTO calculation_steps 
                        (loan_id, attribute_id, step_order, description, value, document_name, rationale, formula)
                        VALUES (%s, %s, %s, %s, %s, %s, 'Reverse Engineered', %s)
                    """, (loan_id, t['attr_id'], idx+1, step['desc'], step['val'], doc_name, formula))
                
                print("      💾 Saved verification and steps.")
                
            else:
                print("      ❌ Could not solve.")
                
        except Exception as e:
            print(f"      ⚠️ Error: {e}")

    conn.commit()
    cur.close()
    conn.close()
    print("🏁 Math Solver Complete.")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_math_solver(int(sys.argv[1]))
