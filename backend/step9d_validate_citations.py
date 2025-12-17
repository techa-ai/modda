import sys
import json
import re
from db import get_db_connection

def normalize(text):
    """Normalize text for searching: remove special chars, lowercase"""
    if not text: return ""
    return re.sub(r'[^\w\s\.]', '', str(text).lower())

def find_value_in_json(target_val_str, current_node):
    """Recursively search for value in JSON object"""
    if current_node is None: return False
    
    # Check if current node matches
    if isinstance(current_node, (str, int, float)):
        s = str(current_node)
        # Normalize comparison
        norm_s = normalize(s)
        norm_t = normalize(target_val_str)
        
        if norm_t in norm_s: return True
        
        # Currency check
        try:
            # Check 46 vs 46.00
            if float(str(target_val_str).replace(',','').replace('$','')) == float(str(s).replace(',','').replace('$','')):
                return True
        except:
            pass
            
        return False
        
    # Recursive search
    if isinstance(current_node, dict):
        for k, v in current_node.items():
            if find_value_in_json(target_val_str, v): return True
    elif isinstance(current_node, list):
        for item in current_node:
            if find_value_in_json(target_val_str, item): return True
            
    return False

def find_value_on_page(value, page_data):
    if not value or not page_data: return False
    
    # Clean value
    val_str = str(value).replace('$', '').replace(',', '').strip()
    if not val_str: return False
    
    # Search the whole page object
    return find_value_in_json(val_str, page_data)

def validate_citations(loan_id):
    print(f"🕵️ Validating Citations for Loan {loan_id} (Deep JSON Search)...")
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 1. Load Document Cache
    doc_cache = {}
    
    def get_doc_pages(filename):
        if filename in doc_cache: return doc_cache[filename]
        
        cur.execute("""
            SELECT individual_analysis FROM document_analysis 
            WHERE loan_id = %s AND filename ILIKE %s
        """, (loan_id, filename))
        row = cur.fetchone()
        
        if row and row['individual_analysis']:
            pages = row['individual_analysis'].get('pages', [])
            page_map = {}
            for p in pages:
                p_num = p.get('page_number')
                # Store WHOLE page object for deep search
                if p_num: page_map[p_num] = p
            doc_cache[filename] = page_map
            return page_map
        else:
            doc_cache[filename] = None
            return None

    # 2. Check Evidence Files (for Verified Leaf Attributes)
    cur.execute("""
        SELECT ef.id, ef.attribute_id, ef.file_name, ef.page_number, ed.extracted_value, fa.attribute_label
        FROM evidence_files ef
        JOIN extracted_1008_data ed ON ed.loan_id = ef.loan_id AND ed.attribute_id = ef.attribute_id
        JOIN form_1008_attributes fa ON fa.id = ef.attribute_id
        WHERE ef.loan_id = %s AND ef.verification_status = 'verified' 
        AND ef.file_name != 'Calculated' AND ef.file_name IS NOT NULL
    """, (loan_id,))
    
    evidence_rows = cur.fetchall()
    print(f"Checking {len(evidence_rows)} verified evidence records...")
    
    corrections = 0
    
    for row in evidence_rows:
        ev_id = row['id']
        filename = row['file_name']
        cited_page = row['page_number']
        value = row['extracted_value']
        label = row['attribute_label']
        
        if not filename or not cited_page: continue
        
        pages = get_doc_pages(filename)
        if not pages: continue
            
        # Check Cited Page
        cited_text = pages.get(cited_page, "")
        if find_value_on_page(value, cited_text):
            continue
            
        # Not found on cited page! Search others.
        print(f"❌ Mismatch: {label} ({value}) NOT found on {filename} p{cited_page}")
        
        found_page = None
        # Try adjacent first
        for offset in [-1, 1, -2, 2]:
            p = cited_page + offset
            if p in pages and find_value_on_page(value, pages[p]):
                found_page = p
                break
        
        # Try all pages if not adjacent
        if not found_page:
            for p, text in pages.items():
                if find_value_on_page(value, text):
                    found_page = p
                    break
        
        if found_page:
            print(f"   ✨ FOUND on Page {found_page}! Updating DB...")
            cur.execute("UPDATE evidence_files SET page_number = %s WHERE id = %s", (found_page, ev_id))
            corrections += 1
        else:
            print(f"   ⚠️ Value not found in document text.")

    # 3. Check Calculation Steps (Constituents)
    cur.execute("""
        SELECT cs.id, cs.document_name, cs.page_number, cs.value, cs.description
        FROM calculation_steps cs
        WHERE cs.loan_id = %s AND cs.document_name IS NOT NULL AND cs.page_number IS NOT NULL
    """, (loan_id,))
    
    step_rows = cur.fetchall()
    print(f"Checking {len(step_rows)} calculation steps...")
    
    for row in step_rows:
        step_id = row['id']
        filename = row['document_name']
        cited_page = row['page_number']
        value = row['value']
        desc = row['description']
        
        if not filename or not cited_page: continue
        if filename == 'Calculated': continue
        
        pages = get_doc_pages(filename)
        if not pages: continue
        
        cited_text = pages.get(cited_page, "")
        if find_value_on_page(value, cited_text):
            continue
            
        print(f"❌ Step Mismatch: {desc} ({value}) NOT found on {filename} p{cited_page}")
        
        found_page = None
        # Try adjacent
        for offset in [-1, 1, -2, 2]:
            p = cited_page + offset
            if p in pages and find_value_on_page(value, pages[p]):
                found_page = p
                break

        if not found_page:
            for p, text in pages.items():
                if find_value_on_page(value, text):
                    found_page = p
                    break
        
        if found_page:
            print(f"   ✨ FOUND on Page {found_page}! Updating Step...")
            cur.execute("UPDATE calculation_steps SET page_number = %s WHERE id = %s", (found_page, step_id))
            corrections += 1

    conn.commit()
    conn.close()
    print(f"🏁 Done. Corrected {corrections} citations.")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        validate_citations(int(sys.argv[1]))
