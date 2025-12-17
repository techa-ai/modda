"""
Step 4b: Generate Document Summaries

Takes existing JSON analysis and generates rich, human-readable summaries
for display in the document viewer.
"""

import json
import logging
from db import execute_query, get_db_connection
from vlm_utils import VLMClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

client = VLMClient()

def generate_document_summary(doc_id, filename, analysis_json):
    """Generate a rich summary from existing analysis JSON"""
    
    # Prepare context for Claude
    json_str = json.dumps(analysis_json, indent=2)[:8000]  # Limit size
    
    prompt = f"""Based on this document analysis JSON, create a concise but comprehensive summary for display.

Document: {filename}
Analysis JSON:
{json_str}

Create a summary object with these fields:
{{
    "title": "Human-readable document title (e.g., 'Uniform Underwriting Summary (Form 1008)')",
    "document_type": "Specific type (e.g., 'Form 1008', 'W-2 Wage Statement', 'Bank Statement')",
    "key_parties": ["List of people/companies mentioned"],
    "key_dates": [
        {{"label": "Document Date", "value": "MM/DD/YYYY"}},
        {{"label": "Period", "value": "Jan 2024 - Dec 2024"}}
    ],
    "key_amounts": [
        {{"label": "Loan Amount", "value": "$XXX,XXX"}},
        {{"label": "Total Income", "value": "$XX,XXX/month"}}
    ],
    "status_indicators": [
        {{"label": "Signature", "value": "Signed/Unsigned", "status": "success/warning/info"}},
        {{"label": "Version", "value": "Final/Preliminary", "status": "success/warning"}}
    ],
    "brief_description": "2-3 sentence description of what this document contains and its purpose",
    "important_notes": ["Any anomalies, warnings, or key observations"]
}}

Return ONLY valid JSON. Extract real values from the analysis, don't make up data.
If a field isn't available, use null or empty array.
"""

    try:
        response = client.process_text(
            text=f"Summarize document: {filename}",
            prompt=prompt,
            return_json=True
        )
        
        if response and isinstance(response, dict):
            return response
        return None
        
    except Exception as e:
        logger.error(f"Error generating summary for {filename}: {e}")
        return None

def generate_summaries_for_loan(loan_id, batch_size=20):
    """Generate summaries for documents that have analysis but no summary"""
    
    logger.info(f"=== Step 4b: Generate Document Summaries for Loan {loan_id} ===\n")
    
    # Get documents with analysis but no summary yet
    docs = execute_query("""
        SELECT id, filename, individual_analysis, vlm_analysis, version_metadata
        FROM document_analysis
        WHERE loan_id = %s
        AND status IN ('unique', 'active', 'master')
        AND (individual_analysis IS NOT NULL OR vlm_analysis IS NOT NULL)
        AND (version_metadata->>'display_summary' IS NULL)
        ORDER BY 
            CASE WHEN filename ILIKE '%%1008%%' THEN 1
                 WHEN filename ILIKE '%%credit%%' THEN 2
                 WHEN filename ILIKE '%%urla%%' THEN 3
                 WHEN filename ILIKE '%%closing%%' THEN 4
                 ELSE 5 END,
            id
        LIMIT %s
    """, (loan_id, batch_size))
    
    if not docs:
        logger.info("No documents need summary generation.")
        return 0
    
    logger.info(f"Generating summaries for {len(docs)} documents...\n")
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    success_count = 0
    
    for doc in docs:
        # Get the best analysis available
        analysis = doc.get('individual_analysis') or doc.get('vlm_analysis') or {}
        if isinstance(analysis, str):
            try:
                analysis = json.loads(analysis)
            except:
                analysis = {}
        
        if not analysis:
            continue
            
        logger.info(f"📝 {doc['filename']}...")
        
        summary = generate_document_summary(doc['id'], doc['filename'], analysis)
        
        if summary:
            # Store summary in version_metadata
            cur.execute("""
                UPDATE document_analysis
                SET version_metadata = COALESCE(version_metadata, '{}'::jsonb) || 
                    jsonb_build_object('display_summary', %s::jsonb)
                WHERE id = %s
            """, (json.dumps(summary), doc['id']))
            
            success_count += 1
            logger.info(f"   ✅ {summary.get('title', 'Summary generated')}")
        else:
            logger.info(f"   ⚠️ Could not generate summary")
    
    conn.commit()
    cur.close()
    conn.close()
    
    logger.info(f"\n=== Generated {success_count} summaries ===")
    return success_count

def get_documents_needing_summary(loan_id):
    """Count documents that need summary generation"""
    result = execute_query("""
        SELECT COUNT(*) as cnt
        FROM document_analysis
        WHERE loan_id = %s
        AND status IN ('unique', 'active', 'master')
        AND (individual_analysis IS NOT NULL OR vlm_analysis IS NOT NULL)
        AND (version_metadata->>'display_summary' IS NULL)
    """, (loan_id,))
    return result[0]['cnt'] if result else 0

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate document summaries from existing analysis")
    parser.add_argument("loan_id", type=int, help="Loan ID to process")
    parser.add_argument("--batch-size", type=int, default=20, help="Documents per batch")
    parser.add_argument("--all", action="store_true", help="Process all documents needing summaries")
    args = parser.parse_args()
    
    if args.all:
        remaining = get_documents_needing_summary(args.loan_id)
        logger.info(f"Documents needing summaries: {remaining}")
        
        while remaining > 0:
            generate_summaries_for_loan(args.loan_id, args.batch_size)
            remaining = get_documents_needing_summary(args.loan_id)
            if remaining > 0:
                logger.info(f"\n{remaining} documents remaining...\n")
    else:
        generate_summaries_for_loan(args.loan_id, args.batch_size)
    
    logger.info("\n✅ Summary generation complete!")

