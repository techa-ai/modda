import json
import logging
import argparse
from db import execute_query
from vlm_utils import VLMClient

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

client = VLMClient()

def classify_financial_docs(loan_id):
    logger.info(f"Classifying documents for Loan {loan_id}...")
    
    # Get all "latest version" documents (visible items)
    # We use group_name if available, else filename
    query = """
        SELECT id, filename, version_metadata
        FROM document_analysis
        WHERE loan_id = %s AND (is_latest_version = TRUE OR version_group_id IS NULL)
    """
    rows = execute_query(query, (loan_id,))
    
    items_to_classify = []
    for r in rows:
        name = r['filename']
        if r['version_metadata']:
            try:
                vm = r['version_metadata'] if isinstance(r['version_metadata'], dict) else json.loads(r['version_metadata'])
                if vm.get('group_name'):
                    name = vm.get('group_name')
            except:
                pass
        items_to_classify.append({"id": r['id'], "name": name})
    
    logger.info(f"Found {len(items_to_classify)} items to classify.")
    
    chunk_size = 50
    chunks = [items_to_classify[i:i + chunk_size] for i in range(0, len(items_to_classify), chunk_size)]
    
    total_f = 0
    total_n = 0
    all_results = [] # Store all for DB update
    
    id_map = {item['id']: item['name'] for item in items_to_classify}
    
    for i, chunk in enumerate(chunks):
        logger.info(f"Processing chunk {i+1}/{len(chunks)} ({len(chunk)} items)...")
        prompt = f"""Classify {len(chunk)} items.
1. FINANCIAL (F): Assess Credit, Capacity, Capital, Collateral (Paystubs, Bank Stmts, Taxes, Appraisal, Note, 1003, 1008, Credit Report).
2. NON-FINANCIAL (N): Compliance, Disclosures, Affidavits, Privacy, Instructions.

ITEMS:
{json.dumps(chunk, indent=2)}

RETURN JSON ONLY:
{{
  "s": {{ "f": 0, "n": 0 }}, 
  "c": [ 
    {{ "id": 123, "t": "F|N", "r": "Reason short" }}
  ]
}}"""
        try:
            response = client.process_text(json.dumps(chunk, indent=2), prompt, return_json=False)
            json_str = response.strip()
            if '```json' in json_str:
                json_str = json_str.split('```json')[1].split('```')[0].strip()
            elif '```' in json_str:
                json_str = json_str.split('```')[1].split('```')[0].strip()
                
            result = json.loads(json_str)
            
            s = result.get('s', {})
            total_f += s.get('f', 0)
            total_n += s.get('n', 0)
            
            # Collect all for update
            for c in result.get('c', []):
                all_results.append(c)
            
        except Exception as e:
            logger.error(f"Error chunk {i+1}: {e}")
            continue

    # Update Database
    print(f"\nSaving {len(all_results)} classifications to database...")
    for res in all_results:
        cat = "FINANCIAL" if res['t'] == 'F' else "NON-FINANCIAL"
        reason = res.get('r')
        doc_id = res['id']
        
        # We also want to update the 'version_metadata' JSON column
        # Using jsonb_set to add/update 'financial_category' key
        update_query = """
            UPDATE document_analysis 
            SET version_metadata = jsonb_set(
                COALESCE(version_metadata, '{}'::jsonb), 
                '{financial_category}', 
                to_jsonb(%s::text)
            ) 
            WHERE id = %s
        """
        execute_query(update_query, (cat, doc_id), fetch=False)
        
    # Final Report
    print("\n" + "="*50)
    print("DOCUMENT CLASSIFICATION REPORT")
    print("="*50)
    print(f"Total Processed: {len(all_results)}")
    print(f"Financial: {total_f}")
    print(f"Non-Financial: {total_n}")
    print("="*50)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Classify financial vs non-financial documents")
    parser.add_argument("loan_id", type=int, help="Loan ID to classify")
    args = parser.parse_args()
    
    classify_financial_docs(args.loan_id)
