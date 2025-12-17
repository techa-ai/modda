import sys
import os
from db import get_db_connection

def validate_links(loan_id):
    print(f"🔗 Validating Document Links for Loan {loan_id}...")
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Load valid mappings
    cur.execute("SELECT filename, file_path FROM document_analysis WHERE loan_id = %s", (loan_id,))
    valid_map = {r['filename']: r['file_path'] for r in cur.fetchall()}
    
    # Fix Evidence Files
    cur.execute("SELECT id, file_name, file_path FROM evidence_files WHERE loan_id = %s", (loan_id,))
    count = 0
    for r in cur.fetchall():
        name = r['file_name']
        path = r['file_path']
        
        if name in valid_map:
            correct_path = valid_map[name]
            # Normalize paths for comparison (optional)
            if path != correct_path:
                print(f"   Fixing {name}: {path} -> {correct_path}")
                cur.execute("UPDATE evidence_files SET file_path = %s WHERE id = %s", (correct_path, r['id']))
                count += 1
        elif name and name not in ['Calculated', 'Calculated (Forensic)']:
            print(f"   ⚠️ Warning: Document '{name}' not found in analysis table.")

    conn.commit()
    conn.close()
    print(f"✅ Fixed {count} broken links.")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        validate_links(int(sys.argv[1]))
