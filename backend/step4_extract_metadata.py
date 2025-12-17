"""
Step 4: Extract Metadata from Deep JSON

After deep extraction, parse document_summary and extract structured metadata
into version_metadata for better versioning, classification, and UI display.
"""

import json
import logging
import argparse
from db import execute_query, get_db_connection
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def extract_metadata_from_summary(doc_id, filename, individual_analysis):
    """Extract metadata from document_summary"""
    
    if not individual_analysis:
        return None
    
    # Get document_summary
    doc_summary = individual_analysis.get('document_summary', {})
    if not doc_summary:
        return None
    
    metadata = {}
    
    # Extract document overview
    doc_overview = doc_summary.get('document_overview', {})
    if doc_overview:
        metadata['document_type'] = doc_overview.get('document_type')
        metadata['purpose'] = doc_overview.get('purpose')
        metadata['date_range'] = doc_overview.get('date_range')
    
    # Extract key entities
    key_entities = doc_summary.get('key_entities', {})
    if key_entities and isinstance(key_entities, dict):
        people = key_entities.get('people', [])
        if people and isinstance(people, list):
            # First person is usually borrower
            if len(people) > 0:
                metadata['borrower_name'] = people[0].get('name') if isinstance(people[0], dict) else people[0]
            # Second person might be co-borrower
            if len(people) > 1:
                metadata['co_borrower_name'] = people[1].get('name') if isinstance(people[1], dict) else people[1]
        
        orgs = key_entities.get('organizations', [])
        if orgs and isinstance(orgs, list) and len(orgs) > 0:
            metadata['issuer'] = orgs[0] if isinstance(orgs[0], str) else orgs[0].get('name')
        
        addresses = key_entities.get('addresses', [])
        if addresses and isinstance(addresses, list) and len(addresses) > 0:
            metadata['property_address'] = addresses[0]
        
        accounts = key_entities.get('account_numbers', [])
        if accounts and isinstance(accounts, list):
            metadata['account_numbers'] = accounts[:3]  # Store up to 3
    
    # Extract financial summary
    financial = doc_summary.get('financial_summary', {})
    if financial:
        # Loan details
        loan_details = financial.get('loan_details', {})
        if loan_details:
            metadata['loan_amount'] = loan_details.get('loan_amount')
            metadata['interest_rate'] = loan_details.get('interest_rate')
        
        # Borrower financials
        borrower_fin = financial.get('borrower_financials', {})
        if borrower_fin:
            metadata['monthly_income'] = borrower_fin.get('total_monthly_income')
            metadata['monthly_debt'] = borrower_fin.get('total_monthly_debt')
    
    # Extract document structure info
    doc_structure = doc_summary.get('document_structure', {})
    if doc_structure:
        page_breakdown = doc_structure.get('page_breakdown', {})
        # Check for signature mentions
        if isinstance(page_breakdown, dict):
            for page_key, page_desc in page_breakdown.items():
                if isinstance(page_desc, str):
                    if 'sign' in page_desc.lower():
                        metadata['has_signature'] = True
                        break
        
        # Check sections for completeness
        sections = doc_structure.get('sections', [])
        if sections and len(sections) > 0:
            metadata['completeness'] = 'complete'
    
    # Extract important values (dates)
    important_vals = doc_summary.get('important_values', {})
    if important_vals and isinstance(important_vals, dict):
        # Look for dates
        for category, values in important_vals.items():
            if 'date' in category.lower():
                if isinstance(values, list) and values:
                    metadata['document_date'] = values[0].get('value') if isinstance(values[0], dict) else values[0]
                    break
    
    # Try to extract date from overview if not found
    if not metadata.get('document_date'):
        if doc_overview.get('date_range'):
            metadata['document_date'] = doc_overview['date_range']
    
    # Check for anomalies
    anomalies = doc_summary.get('anomalies', [])
    if anomalies and isinstance(anomalies, list):
        metadata['anomalies'] = anomalies[:3]  # Store up to 3
    elif anomalies and not isinstance(anomalies, list):
        # Handle case where anomalies is not a list (e.g., integer 0)
        metadata['anomalies'] = [str(anomalies)]
    
    # Metadata extraction timestamp
    metadata['metadata_extracted_at'] = datetime.now().isoformat()
    
    return metadata if metadata else None

def extract_metadata_for_loan(loan_id, batch_size=50):
    """Extract metadata for all documents with deep JSON"""
    
    logger.info(f"=" * 80)
    logger.info(f"Step 4: Extract Metadata from Deep JSON - Loan {loan_id}")
    logger.info(f"=" * 80)
    
    # Get documents with individual_analysis but no metadata_extracted_at yet
    docs = execute_query("""
        SELECT id, filename, individual_analysis, version_metadata
        FROM document_analysis
        WHERE loan_id = %s
        AND individual_analysis IS NOT NULL
        AND individual_analysis::jsonb ? 'document_summary'
        AND (version_metadata->>'metadata_extracted_at' IS NULL OR version_metadata IS NULL)
        ORDER BY id
        LIMIT %s
    """, (loan_id, batch_size))
    
    if not docs:
        logger.info("No documents need metadata extraction (all already done or no deep JSON)")
        return {"extracted": 0, "skipped": 0, "errors": 0}
    
    logger.info(f"Found {len(docs)} documents to extract metadata from\n")
    
    conn = get_db_connection()
    extracted = 0
    skipped = 0
    errors = 0
    
    for i, doc in enumerate(docs, 1):
        try:
            logger.info(f"[{i}/{len(docs)}] {doc['filename'][:60]}")
            
            # Extract metadata
            metadata = extract_metadata_from_summary(
                doc['id'],
                doc['filename'],
                doc['individual_analysis']
            )
            
            if not metadata:
                logger.info(f"  ⏭️  No extractable metadata")
                skipped += 1
                continue
            
            # Merge with existing version_metadata
            existing_meta = doc.get('version_metadata') or {}
            if isinstance(existing_meta, str):
                try:
                    existing_meta = json.loads(existing_meta)
                except:
                    existing_meta = {}
            
            # Merge (new metadata takes precedence)
            merged_meta = {**existing_meta, **metadata}
            
            # Update database
            cur = conn.cursor()
            cur.execute("""
                UPDATE document_analysis
                SET version_metadata = %s::jsonb
                WHERE id = %s
            """, (json.dumps(merged_meta), doc['id']))
            conn.commit()
            cur.close()
            
            # Log what was extracted
            extracted_items = []
            if metadata.get('document_type'):
                extracted_items.append(f"type: {metadata['document_type']}")
            if metadata.get('borrower_name'):
                extracted_items.append(f"borrower: {metadata['borrower_name']}")
            if metadata.get('document_date'):
                extracted_items.append(f"date: {metadata['document_date']}")
            if metadata.get('has_signature'):
                extracted_items.append("✍️ signed")
            
            logger.info(f"  ✅ {', '.join(extracted_items) if extracted_items else 'metadata extracted'}")
            extracted += 1
            
        except Exception as e:
            logger.error(f"  ❌ Error: {e}")
            errors += 1
            continue
    
    conn.close()
    
    logger.info(f"\n{'=' * 80}")
    logger.info(f"Metadata Extraction Summary:")
    logger.info(f"  ✅ Extracted: {extracted}")
    logger.info(f"  ⏭️  Skipped: {skipped}")
    logger.info(f"  ❌ Errors: {errors}")
    logger.info(f"{'=' * 80}\n")
    
    return {"extracted": extracted, "skipped": skipped, "errors": errors}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract metadata from deep JSON")
    parser.add_argument("loan_id", type=int, help="Loan ID to process")
    parser.add_argument("--batch-size", type=int, default=100, help="Batch size")
    
    args = parser.parse_args()
    
    result = extract_metadata_for_loan(args.loan_id, args.batch_size)
    
    if result['errors'] > 0:
        exit(1)

