import json
from db import execute_query, execute_one, get_db_connection

def promote_fields():
    conn = get_db_connection()
    cur = conn.cursor()
    
    print("Promoting Detected Fields to Core Sections...")
    
    # 1. Get all attributes currently populated in Data Tape (Loan ID from args or all)
    loan_filter = ""
    import sys
    if len(sys.argv) > 1:
        loan_filter = f"WHERE ed.loan_id = {sys.argv[1]}"
    
    cur.execute(f"""
        SELECT DISTINCT fa.id, fa.attribute_name, fa.attribute_label, fa.section
        FROM form_1008_attributes fa
        JOIN extracted_1008_data ed ON fa.id = ed.attribute_id
        {loan_filter}
    """)
    
    active_attrs = cur.fetchall()
    print(f"Found {len(active_attrs)} active attributes to organize.")
    
    # 2. Define Section Mapping Rules (Keyword based)
    def get_section(name, label):
        n = name.lower()
        l = label.lower()
        
        if 'borrower' in n and 'co' not in n: return 'Borrower Info'
        if 'co_borrower' in n or 'co' in n: return 'Co-Borrower Info'
        if 'property' in n or 'address' in n or 'units' in n: return 'Property Info'
        if 'loan' in n or 'mortgage' in n or 'rate' in n or 'amortization' in n: return 'Loan Information'
        if 'income' in n: return 'Income Information'
        if 'housing' in n or 'payment' in n or 'obligation' in n: return 'Housing Expense Information'
        if 'underwrit' in n or 'qualifying' in n or 'ratio' in n: return 'Underwriting Info'
        if 'ltv' in n: return 'Underwriting Info'
        
        return 'Other Information'

    for attr in active_attrs:
        curr_section = attr['section']
        if curr_section == 'Detected Field' or curr_section == 'Detected':
            new_section = get_section(attr['attribute_name'], attr['attribute_label'])
            
            print(f"Moving {attr['attribute_name']} from '{curr_section}' to '{new_section}'")
            
            execute_query(
                "UPDATE form_1008_attributes SET section = %s WHERE id = %s",
                (new_section, attr['id']),
                fetch=False
            )
            
    # 3. Clean up Unused Attributes (Optional but recommended)
    # Be careful not to delete things needed for other loans if this wasn't a full extraction
    # But for now, we want to clean the UI.
    
    # Let's just mark the unused ones as 'Legacy' section so they hide?
    # Or delete if they are clearly duplicates.
    
    print("\nCleanup complete. Refresh UI.")

if __name__ == "__main__":
    promote_fields()

