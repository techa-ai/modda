import sys
import json
from db import get_db_connection

def forensic_search(loan_id, target_val_str):
    print(f"🕵️ Forensic Search for '{target_val_str}' in Loan {loan_id}...")
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get all docs
    cur.execute("""
        SELECT filename, individual_analysis FROM document_analysis 
        WHERE loan_id = %s
    """, (loan_id,))
    
    found = False
    
    target_clean = target_val_str.replace('$', '').replace(',', '').strip().split('.')[0] # Search integer part "2744"
    
    def search_json(node, path, matches):
        if isinstance(node, dict):
            for k, v in node.items():
                search_json(v, f"{path}.{k}", matches)
        elif isinstance(node, list):
            for i, item in enumerate(node):
                search_json(item, f"{path}[{i}]", matches)
        elif isinstance(node, (str, int, float)):
            s = str(node)
            s_clean = s.replace('$', '').replace(',', '').strip()
            if target_clean in s_clean:
                 matches.append((path, s))

    rows = cur.fetchall()
    print(f"Scanning {len(rows)} documents for '{target_clean}'...")
    
    for r in rows:
        fname = r['filename'].lower()
        # Only exclude 1008/URLA to see if it exists ANYWHERE
        if '1008' in fname or '1003' in fname or 'urla' in fname:
            continue
            
        json_data = r['individual_analysis']
        if not json_data: continue
        
        matches = []
        search_json(json_data, "root", matches)
        
        if matches:
            print(f"✅ FOUND in {r['filename']}!")
            for path, val in matches:
                print(f"   - Path: {path}")
                print(f"   - Value: {val}")
            found = True

    if not found:
        print("❌ Value NOT found in any valid document.")
    
    cur.close()
    conn.close()

if __name__ == "__main__":
    if len(sys.argv) > 2:
        forensic_search(int(sys.argv[1]), sys.argv[2])
