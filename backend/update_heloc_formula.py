import sys
import json
from db import get_db_connection

def update_heloc_formula_clarity(loan_id):
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get Attribute ID for Second Mortgage P&I
    cur.execute("SELECT id FROM form_1008_attributes WHERE attribute_label = 'Second Mortgage P&I'")
    attr_id = cur.fetchone()['id']
    
    # Update the Formula Step
    new_formula = "r = 8.5% / 12 = 0.00708333...; PMT = 300000 * (r * (1+r)^216) / ((1+r)^216 - 1)"
    
    cur.execute("""
        UPDATE calculation_steps 
        SET formula = %s
        WHERE loan_id = %s AND attribute_id = %s AND step_order = 4
    """, (new_formula, loan_id, attr_id))
    
    conn.commit()
    conn.close()
    print("✅ Updated formula for clarity.")

if __name__ == "__main__":
    update_heloc_formula_clarity(30)
