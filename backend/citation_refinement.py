import sys
import json
import os
from db import get_db_connection, execute_query
from bedrock_config import call_bedrock
from processing import extract_json_from_text

def refine_citations(loan_id):
    print(f"🕵️ Refining Citations for Loan {loan_id} using Claude...")
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 1. Collect Citations (Evidence Files + Calculation Steps)
    citations_by_doc = {}
    
    # Evidence Files
    cur.execute("""
        SELECT ef.id, ef.file_name, ef.page_number, ed.extracted_value, fa.attribute_label
        FROM evidence_files ef
        JOIN extracted_1008_data ed ON ed.loan_id = ef.loan_id AND ed.attribute_id = ef.attribute_id
        JOIN form_1008_attributes fa ON fa.id = ef.attribute_id
        WHERE ef.loan_id = %s AND ef.verification_status = 'verified' 
        AND ef.file_name != 'Calculated' AND ef.file_name IS NOT NULL
    """, (loan_id,))
    
    for row in cur.fetchall():
        doc = row['file_name']
        if doc not in citations_by_doc: citations_by_doc[doc] = []
        citations_by_doc[doc].append({
            'type': 'evidence',
            'id': row['id'],
            'label': row['attribute_label'],
            'value': row['extracted_value'],
            'current_page': row['page_number']
        })

    # Calculation Steps
    cur.execute("""
        SELECT cs.id, cs.document_name, cs.page_number, cs.value, cs.description
        FROM calculation_steps cs
        WHERE cs.loan_id = %s AND cs.document_name IS NOT NULL AND cs.page_number IS NOT NULL
    """, (loan_id,))
    
    for row in cur.fetchall():
        doc = row['document_name']
        if doc == 'Calculated': continue
        if doc not in citations_by_doc: citations_by_doc[doc] = []
        citations_by_doc[doc].append({
            'type': 'step',
            'id': row['id'],
            'label': row['description'],
            'value': row['value'],
            'current_page': row['page_number']
        })

    print(f"Found {len(citations_by_doc)} documents to audit.")

    # 2. Process Each Document
    total_corrections = 0
    
    for doc_name, items in citations_by_doc.items():
        print(f"\n📄 Auditing {doc_name} ({len(items)} items)...")
        
        # Load Deep JSON
        cur.execute("""
            SELECT individual_analysis FROM document_analysis 
            WHERE loan_id = %s AND filename ILIKE %s
        """, (loan_id, doc_name))
        res = cur.fetchone()
        
        if not res or not res['individual_analysis']:
            print("   ⚠️ No Deep JSON found. Skipping.")
            continue
            
        deep_json = res['individual_analysis']
        
        prompt = f"""
You are a Quality Assurance Auditor for mortgage data.
Your goal is to VERIFY and CORRECT the page numbers for specific data points found in a document.

DOCUMENT: {doc_name}
CONTENT: See the JSON below (paginated).

ITEMS TO VERIFY:
{json.dumps(items, indent=2)}

INSTRUCTIONS:
1. For each item, search the Document JSON to find where the specified 'value' appears.
2. Use the structural context (labels, tables) to ensure it's the CORRECT value (e.g. for '$46', ensure it's a payment/fee, not a random number).
3. Return the `confirmed_page` number (integer) where the value is found.
4. If the item is NOT found, set status to "not_found".
5. If found on a different page than 'current_page', set status to "corrected".
6. If found on the same page, set status to "confirmed".

OUTPUT REQUIREMENTS:
Return a valid JSON object with a key "results" containing a list of objects.
Do not include markdown code blocks.

Example Output:
{{
  "results": [
    {{ "id": 123, "type": "evidence", "confirmed_page": 3, "status": "corrected", "reason": "Found in Open Accounts table on page 3" }}
  ]
}}

DOCUMENT JSON:
{json.dumps(deep_json)}
"""
        
        try:
            # Using Opus 4.5 for high precision on JSON analysis
            response = call_bedrock(prompt, model='claude-opus-4-5', max_tokens=4000)
            result = extract_json_from_text(response)
            
            if not result or 'results' not in result:
                print("   ❌ Failed to parse Claude response.")
                continue
                
            updates = result['results']
            print(f"   🤖 Audited {len(updates)} items.")
            
            for up in updates:
                if up['status'] == 'corrected':
                    new_page = up['confirmed_page']
                    item_id = up['id']
                    
                    if up['type'] == 'evidence':
                        cur.execute("UPDATE evidence_files SET page_number = %s WHERE id = %s", (new_page, item_id))
                    elif up['type'] == 'step':
                        cur.execute("UPDATE calculation_steps SET page_number = %s WHERE id = %s", (new_page, item_id))
                        
                    print(f"      ✨ Corrected {item_id}: Page {new_page} (Reason: {up.get('reason')})")
                    total_corrections += 1
                    
            conn.commit()
            
        except Exception as e:
            print(f"   ❌ Error calling Claude: {e}")

    cur.close()
    conn.close()
    print(f"\n🏁 Refining Complete. Total corrections: {total_corrections}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        refine_citations(int(sys.argv[1]))
