"""
Step 4a: Filename Audit and Content-Based Naming

This step:
1. Analyzes document content vs filename
2. Identifies mismatches (e.g., "preliminary" file is actually "final")
3. Generates descriptive names for generic files (miscellaneous, other_disclosures)
4. Stores secondary_name for display in UI
"""

import json
import logging
from db import execute_query, get_db_connection
from vlm_utils import VLMClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

client = VLMClient()

# Generic filenames that need content-based names
GENERIC_PATTERNS = [
    'miscellaneous',
    'other_',
    'additional_',
    'misc_',
    'document_',
    'docs_',
    'file_',
    'unknown',
    'untitled'
]

def is_generic_filename(filename):
    """Check if filename is generic and needs content analysis"""
    lower = filename.lower()
    return any(pattern in lower for pattern in GENERIC_PATTERNS)

def has_version_mismatch_potential(filename):
    """Check if filename has preliminary/final that might be wrong"""
    lower = filename.lower()
    return 'prelim' in lower or 'final' in lower or 'draft' in lower

def audit_document_names(loan_id, batch_size=20):
    """Audit document names and generate secondary names where needed"""
    
    logger.info(f"=== Step 4a: Filename Audit for Loan {loan_id} ===\n")
    
    # Get documents that need auditing
    # Priority: generic names, version indicators, no secondary_name yet
    docs = execute_query("""
        SELECT id, filename, file_path, page_count, individual_analysis, version_metadata
        FROM document_analysis
        WHERE loan_id = %s
        AND status IN ('unique', 'active', 'master')
        AND (version_metadata->>'secondary_name' IS NULL OR version_metadata->>'filename_verified' IS NULL)
        ORDER BY 
            CASE 
                WHEN filename ILIKE '%%miscellaneous%%' THEN 1
                WHEN filename ILIKE '%%other_%%' THEN 1
                WHEN filename ILIKE '%%additional_%%' THEN 1
                WHEN filename ILIKE '%%prelim%%' THEN 2
                WHEN filename ILIKE '%%final%%' THEN 2
                ELSE 3
            END,
            page_count DESC
        LIMIT %s
    """, (loan_id, batch_size))
    
    if not docs:
        logger.info("No documents need filename auditing.")
        return
    
    logger.info(f"Found {len(docs)} documents to audit\n")
    
    # Prepare batch for Claude
    docs_to_analyze = []
    for doc in docs:
        # Get existing metadata about the document
        individual = doc.get('individual_analysis') or {}
        if isinstance(individual, str):
            try:
                individual = json.loads(individual)
            except:
                individual = {}
        
        # Extract document type hints from existing analysis
        doc_type_hint = individual.get('document_type', '')
        content_hint = individual.get('document_description', '')
        
        docs_to_analyze.append({
            "id": doc['id'],
            "filename": doc['filename'],
            "page_count": doc['page_count'],
            "doc_type_hint": doc_type_hint,
            "content_hint": content_hint[:200] if content_hint else ""
        })
    
    # Batch analyze with Claude
    prompt = f"""Analyze these {len(docs_to_analyze)} mortgage document filenames and determine:

1. **secondary_name**: A more descriptive name based on content (especially for generic names like "miscellaneous_docs")
2. **filename_match**: Does the filename accurately describe the content? (MATCH, MISMATCH, GENERIC)
3. **version_status**: If filename says "preliminary" or "final", is that accurate? (CORRECT, WRONG, N/A)
4. **mismatch_reason**: If there's a mismatch, explain why

Documents to analyze:
{json.dumps(docs_to_analyze, indent=2)}

For each document, provide a JSON object with:
- id: document ID
- secondary_name: descriptive name (e.g., "IRS Form 4506-T Tax Transcript Request" instead of "miscellaneous_docs_123.pdf")
- filename_match: MATCH | MISMATCH | GENERIC
- version_status: CORRECT | WRONG | N/A
- mismatch_reason: explanation if mismatch (null otherwise)

Return a JSON array of objects. Be specific with secondary_name - use actual form numbers, document types, etc.

Common mortgage document types to look for:
- IRS Forms (4506-T, 4506-C, W-2, W-9, 1099, etc.)
- Disclosures (ECOA, TILA, RESPA, Right to Cancel, etc.)
- Certifications (Borrower Certification, Occupancy, etc.)
- Legal (Deed, Trust, Power of Attorney, etc.)
- Insurance (Hazard, Flood, HOA, etc.)
- Title (Commitment, Policy, Search, etc.)
- Closing (HUD-1, CD, Settlement Statement, etc.)
"""

    try:
        response = client.process_text(
            text="Filename audit request",
            prompt=prompt,
            return_json=True
        )
        
        if not response or not isinstance(response, list):
            logger.error(f"Invalid response from Claude: {response}")
            return
        
        # Process results
        conn = get_db_connection()
        cur = conn.cursor()
        
        matches = 0
        mismatches = 0
        generics = 0
        
        for result in response:
            doc_id = result.get('id')
            secondary_name = result.get('secondary_name', '')
            filename_match = result.get('filename_match', 'UNKNOWN')
            version_status = result.get('version_status', 'N/A')
            mismatch_reason = result.get('mismatch_reason')
            
            if filename_match == 'MATCH':
                matches += 1
            elif filename_match == 'MISMATCH':
                mismatches += 1
            elif filename_match == 'GENERIC':
                generics += 1
            
            # Update version_metadata with audit results
            update_data = {
                'secondary_name': secondary_name,
                'filename_verified': True,
                'filename_match': filename_match,
                'version_status': version_status,
                'mismatch_reason': mismatch_reason
            }
            
            cur.execute("""
                UPDATE document_analysis
                SET version_metadata = COALESCE(version_metadata, '{}'::jsonb) || %s::jsonb
                WHERE id = %s
            """, (json.dumps(update_data), doc_id))
            
            # Log mismatches
            if filename_match in ['MISMATCH', 'GENERIC']:
                original = next((d['filename'] for d in docs_to_analyze if d['id'] == doc_id), 'unknown')
                logger.info(f"  📝 {original}")
                logger.info(f"     → {secondary_name}")
                if mismatch_reason:
                    logger.info(f"     ⚠️ {mismatch_reason}")
        
        conn.commit()
        cur.close()
        conn.close()
        
        logger.info(f"\n=== Audit Summary ===")
        logger.info(f"  ✅ Matches: {matches}")
        logger.info(f"  ⚠️ Mismatches: {mismatches}")
        logger.info(f"  📝 Generic (renamed): {generics}")
        
    except Exception as e:
        logger.error(f"Error during filename audit: {e}")
        import traceback
        traceback.print_exc()

def get_documents_needing_audit(loan_id):
    """Get count of documents that need filename auditing"""
    result = execute_query("""
        SELECT COUNT(*) as cnt
        FROM document_analysis
        WHERE loan_id = %s
        AND status IN ('unique', 'active', 'master')
        AND (version_metadata->>'secondary_name' IS NULL OR version_metadata->>'filename_verified' IS NULL)
    """, (loan_id,))
    return result[0]['cnt'] if result else 0

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Audit document filenames and generate content-based names")
    parser.add_argument("loan_id", type=int, help="Loan ID to process")
    parser.add_argument("--batch-size", type=int, default=30, help="Number of documents per batch")
    args = parser.parse_args()
    
    remaining = get_documents_needing_audit(args.loan_id)
    logger.info(f"Documents needing audit: {remaining}")
    
    while remaining > 0:
        audit_document_names(args.loan_id, args.batch_size)
        remaining = get_documents_needing_audit(args.loan_id)
        if remaining > 0:
            logger.info(f"\n{remaining} documents remaining...\n")
    
    logger.info("\n✅ Filename audit complete!")

