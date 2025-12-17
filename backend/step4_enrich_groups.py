import os
import json
import logging
import argparse
from db import execute_query, get_db_connection
from vlm_utils import VLMClient

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize VLM Client
client = VLMClient()

def get_groups_to_enrich(loan_id):
    """Fetch all version/duplicate groups for a loan"""
    query = """
        SELECT version_group_id, array_agg(id) as doc_ids
        FROM document_analysis
        WHERE loan_id = %s 
          AND version_group_id IS NOT NULL
        GROUP BY version_group_id
        HAVING count(*) > 0
    """
    return execute_query(query, (loan_id,))

def get_group_docs_metadata(doc_ids):
    """Get metadata for documents in a specific group"""
    if not doc_ids:
        return []
    
    placeholders = ','.join(['%s'] * len(doc_ids))
    query = f"""
        SELECT id, filename, page_count, individual_analysis, vlm_analysis
        FROM document_analysis
        WHERE id IN ({placeholders})
    """
    rows = execute_query(query, tuple(doc_ids))
    
    docs_data = []
    for row in rows:
        # Merge analyses
        analysis = {}
        if row['individual_analysis']:
            analysis.update(row['individual_analysis'])
        if row['vlm_analysis']:
            # vlm_analysis might be a string or dict
            vlm = row['vlm_analysis']
            if isinstance(vlm, str):
                try:
                    vlm = json.loads(vlm)
                except:
                    vlm = {}
            if isinstance(vlm, dict):
                analysis.update(vlm)
                
        docs_data.append({
            "id": row['id'],
            "filename": row['filename'],
            "page_count": row['page_count'],
            "metadata": analysis
        })
    return docs_data

def enrich_group(group_id, docs):
    """Ask Claude to double-check and enrich group metadata"""
    
    prompt = f"""You are validating a specific group of {len(docs)} documents.
They have been tentatively grouped together.

Task:
1. CONFIRM if they truly belong together (same doc type, same borrower entity).
2. Identify BORROWER vs CO-BORROWER distinctions.
3. Extract DATES SIGNED for each document.
4. Select the LATEST/BEST version definitively.
5. Provide detailed REASONING.

DOCUMENTS:
{json.dumps(docs, indent=2)}

Return JSON:
{{
  "group_name": "Standardized Group Name",
  "group_type": "version|duplicate|distinct",
  "borrower": "Name of Borrower(s)",
  "latest_document_id": 123,
  "reasoning": "Detailed explanation...",
  "doc_details": [
    {{
      "document_id": 123,
      "date_signed": "YYYY-MM-DD",
      "borrower_type": "borrower|co-borrower|both",
      "notes": "..."
    }}
  ]
}}"""

    try:
        # Use robust parsing from before (re-implemented here simply)
        response = client.process_text(json.dumps(docs, indent=2), prompt, return_json=False)
        
        json_str = response.strip()
        if '```json' in json_str:
            json_str = json_str.split('```json')[1].split('```')[0].strip()
        elif '```' in json_str:
            json_str = json_str.split('```')[1].split('```')[0].strip()
            
        result = json.loads(json_str)
        return result
        
    except Exception as e:
        logger.error(f"Error enriching group {group_id}: {e}")
        return None

def update_group_in_db(group_id, enrichment_result):
    """Update database with enriched metadata"""
    if not enrichment_result:
        return

    latest_id = enrichment_result.get('latest_document_id')
    
    # Common group metadata
    group_meta = {
        "group_name": enrichment_result.get('group_name'),
        "group_type": enrichment_result.get('group_type'),
        "borrower": enrichment_result.get('borrower'),
        "reasoning": enrichment_result.get('reasoning')
    }
    
    # Update latest flag and group metadata for all docs in group
    # First, reset latest flags for this group
    execute_query(
        "UPDATE document_analysis SET is_latest_version = FALSE, version_metadata = %s WHERE version_group_id = %s",
        (json.dumps(group_meta), group_id),
        fetch=False
    )
    
    # Set latest
    if latest_id:
        execute_query(
            "UPDATE document_analysis SET is_latest_version = TRUE WHERE id = %s",
            (latest_id,),
            fetch=False
        )
        
    # We could also store per-doc details (date signed) in 'individual_analysis' or similar?
    # For now, we mainly want the group metadata enriched.
    logger.info(f"Updated group {group_id} ({enrichment_result.get('group_name')})")

def main(loan_id):
    logger.info(f"Starting enrichment for Loan {loan_id}")
    
    groups = get_groups_to_enrich(loan_id)
    logger.info(f"Found {len(groups)} groups to enrich")
    
    for i, g in enumerate(groups):
        group_id = g['version_group_id']
        doc_ids = g['doc_ids']
        
        # Only enrich groups with > 1 doc? or all? 
        # User said "send all groups", so we do all, including distinct ones, to enable reasoning.
        
        logger.info(f"Enriching Group {i+1}/{len(groups)} (ID: {group_id}, Docs: {len(doc_ids)})")
        
        docs_data = get_group_docs_metadata(doc_ids)
        result = enrich_group(group_id, docs_data)
        
        if result:
            update_group_in_db(group_id, result)
            
    logger.info("✅ Enrichment complete!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('loan_id', type=int)
    args = parser.parse_args()
    main(args.loan_id)
