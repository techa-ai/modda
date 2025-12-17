"""
Step 7: Re-Versioning with Rich Metadata

After metadata extraction, re-evaluate which document is the latest/master
version within each cluster using richer criteria:
- has_signature (signed > unsigned)
- document_date (later > earlier)  
- version indicators (final > preliminary)
- borrower vs co-borrower (split if different)
- completeness
"""

import json
import logging
import argparse
from db import execute_query, get_db_connection
from datetime import datetime
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_version_priority(metadata):
    """Get numeric priority for version indicator"""
    if not metadata:
        return 2
    
    filename_or_indicator = str(metadata.get('version_indicator', '')).lower()
    if 'final' in filename_or_indicator:
        return 3
    if 'prelim' in filename_or_indicator:
        return 1
    if 'draft' in filename_or_indicator:
        return 0
    return 2  # default

def parse_date(date_str):
    """Parse date string to datetime for comparison"""
    if not date_str:
        return datetime.min
    
    try:
        # Try various formats
        for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%Y', '%m/%d/%y']:
            try:
                return datetime.strptime(str(date_str)[:10], fmt)
            except:
                continue
        return datetime.min
    except:
        return datetime.min

def reversion_cluster(cluster_docs):
    """Re-version documents within a cluster using rich metadata"""
    
    if len(cluster_docs) <= 1:
        # Single doc, mark as unique
        return [{'id': cluster_docs[0]['id'], 'status': 'unique', 'is_latest': True, 'reason': 'Only document in cluster'}]
    
    # Group by borrower (if borrower info available)
    borrower_groups = defaultdict(list)
    for doc in cluster_docs:
        meta = doc.get('version_metadata') or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except:
                meta = {}
        
        borrower = meta.get('borrower_name', 'unknown')
        borrower_groups[borrower].append({**doc, 'parsed_metadata': meta})
    
    results = []
    
    # Process each borrower group separately
    for borrower, docs in borrower_groups.items():
        if len(docs) == 1:
            # Single doc for this borrower, mark as unique
            results.append({
                'id': docs[0]['id'],
                'status': 'unique',
                'is_latest': True,
                'reason': f'Only document for {borrower}'
            })
            continue
        
        # Sort by priority
        def sort_key(d):
            meta = d['parsed_metadata']
            
            # Priority 1: Signature (signed > unsigned)
            has_sig = 1 if meta.get('has_signature') else 0
            
            # Priority 2: Version indicator (final > default > preliminary)
            version_pri = get_version_priority(meta)
            
            # Priority 3: Document date (later > earlier)
            doc_date = parse_date(meta.get('document_date'))
            
            # Priority 4: Completeness
            completeness_score = {'complete': 3, 'partial': 2, 'incomplete': 1}.get(
                meta.get('completeness', 'unknown'), 0
            )
            
            # Priority 5: Page count (more > less)
            pages = d.get('page_count', 0)
            
            return (has_sig, version_pri, doc_date, completeness_score, pages)
        
        # Sort in descending order (best first)
        sorted_docs = sorted(docs, key=sort_key, reverse=True)
        
        # Mark first as master, rest as superseded
        for i, doc in enumerate(sorted_docs):
            if i == 0:
                # Latest version
                meta = doc['parsed_metadata']
                reason_parts = []
                if meta.get('has_signature'):
                    reason_parts.append('signed')
                version_pri = get_version_priority(meta)
                if version_pri == 3:
                    reason_parts.append('final')
                elif version_pri == 1:
                    reason_parts.append('preliminary')
                if meta.get('document_date'):
                    reason_parts.append(f"date: {meta['document_date']}")
                
                results.append({
                    'id': doc['id'],
                    'status': 'master',
                    'is_latest': True,
                    'reason': f"Latest: {', '.join(reason_parts) if reason_parts else 'best match'}"
                })
            else:
                # Superseded version
                results.append({
                    'id': doc['id'],
                    'status': 'superseded',
                    'is_latest': False,
                    'reason': f"Superseded by doc {sorted_docs[0]['id']}"
                })
    
    return results

def reversion_loan_documents(loan_id):
    """Re-version all documents for a loan"""
    
    logger.info(f"=" * 80)
    logger.info(f"Step 7: Re-Versioning with Rich Metadata - Loan {loan_id}")
    logger.info(f"=" * 80)
    
    # Get all documents grouped by cluster
    docs = execute_query("""
        SELECT id, filename, version_group_id, page_count, status, version_metadata
        FROM document_analysis
        WHERE loan_id = %s
        ORDER BY version_group_id, id
    """, (loan_id,))
    
    if not docs:
        logger.info("No documents found")
        return {"updated": 0, "errors": 0}
    
    # Group by cluster
    clusters = defaultdict(list)
    no_cluster_docs = []
    
    for doc in docs:
        cluster_id = doc.get('version_group_id')
        if cluster_id:
            clusters[cluster_id].append(doc)
        else:
            no_cluster_docs.append(doc)
    
    logger.info(f"Found {len(clusters)} clusters and {len(no_cluster_docs)} unclustered documents\n")
    
    conn = get_db_connection()
    updated = 0
    errors = 0
    
    # Process each cluster
    for cluster_id, cluster_docs in clusters.items():
        logger.info(f"Cluster {cluster_id}: {len(cluster_docs)} documents")
        
        try:
            # Re-version this cluster
            versioning_results = reversion_cluster(cluster_docs)
            
            # Update database
            cur = conn.cursor()
            for result in versioning_results:
                # Update version_metadata with reversioning info
                cur.execute("""
                    SELECT version_metadata FROM document_analysis WHERE id = %s
                """, (result['id'],))
                row = cur.fetchone()
                
                existing_meta = row[0] if row and row[0] else {}
                if isinstance(existing_meta, str):
                    try:
                        existing_meta = json.loads(existing_meta)
                    except:
                        existing_meta = {}
                
                # Add reversioning info
                existing_meta['reversioned_at'] = datetime.now().isoformat()
                existing_meta['reversioning_reason'] = result['reason']
                
                # Update document
                cur.execute("""
                    UPDATE document_analysis
                    SET status = %s,
                        is_latest_version = %s,
                        version_metadata = %s::jsonb
                    WHERE id = %s
                """, (result['status'], result['is_latest'], json.dumps(existing_meta), result['id']))
                
                updated += 1
                logger.info(f"  {result['status']:12} Doc {result['id']:4} - {result['reason']}")
            
            conn.commit()
            cur.close()
            
        except Exception as e:
            logger.error(f"  ❌ Error processing cluster: {e}")
            conn.rollback()
            errors += 1
            continue
    
    # Handle unclustered documents (mark as unique)
    if no_cluster_docs:
        logger.info(f"\nProcessing {len(no_cluster_docs)} unclustered documents...")
        cur = conn.cursor()
        for doc in no_cluster_docs:
            try:
                cur.execute("""
                    UPDATE document_analysis
                    SET status = 'unique',
                        is_latest_version = true
                    WHERE id = %s
                """, (doc['id'],))
                updated += 1
            except Exception as e:
                logger.error(f"  ❌ Error updating doc {doc['id']}: {e}")
                errors += 1
        conn.commit()
        cur.close()
    
    conn.close()
    
    logger.info(f"\n{'=' * 80}")
    logger.info(f"Re-Versioning Summary:")
    logger.info(f"  ✅ Updated: {updated}")
    logger.info(f"  ❌ Errors: {errors}")
    logger.info(f"{'=' * 80}\n")
    
    return {"updated": updated, "errors": errors}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Re-version documents with rich metadata")
    parser.add_argument("loan_id", type=int, help="Loan ID to process")
    
    args = parser.parse_args()
    
    result = reversion_loan_documents(args.loan_id)
    
    if result['errors'] > 0:
        exit(1)

