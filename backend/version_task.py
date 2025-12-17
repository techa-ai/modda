
import os
import uuid
from db import get_db_connection, execute_query, execute_one
from version_utils import compute_visual_hashes, extract_date_from_text, are_visually_similar
from dedup_utils import extract_text_from_pdf

def run_version_analysis(loan_id, document_location):
    """
    Run visual version analysis for a loan.
    1. Compute visual hashes for all eligible documents.
    2. Extract dates.
    3. Group visually similar documents into version groups.
    4. identify latest version in each group.
    """
    print(f"Starting version analysis for loan {loan_id}...")
    
    # 1. Fetch eligible documents (unique and masters)
    # We also include 'unique_scanned' if we have that status, but usually they are 'unique' now.
    documents = execute_query(
        """
        SELECT id, filename, file_path, visual_phash, visual_dhash, visual_ahash, detected_date, status
        FROM document_analysis 
        WHERE loan_id = %s AND status IN ('unique', 'master')
        """,
        (loan_id,)
    )
    
    if not documents:
        print("No documents to analyze for versions.")
        return
        
    print(f"Processing {len(documents)} documents for versioning...")
    
    docs_by_id = {doc['id']: doc for doc in documents}
    updated_docs = []
    
    # 2. Compute hashes and extract dates where missing
    for doc in documents:
        updated = False
        file_path = doc['file_path']
        
        if not os.path.exists(file_path):
            print(f"File not found: {file_path}")
            continue
            
        # Compute Visual Hashes if missing
        if not doc['visual_phash']:
            print(f"Computing visual hashes for {doc['filename']}...")
            hashes = compute_visual_hashes(file_path)
            if hashes:
                doc['visual_phash'] = hashes['phash']
                doc['visual_dhash'] = hashes['dhash']
                doc['visual_ahash'] = hashes['ahash']
                updated = True
                
                # Update DB immediately
                execute_query(
                    """
                    UPDATE document_analysis 
                    SET visual_phash = %s, visual_dhash = %s, visual_ahash = %s
                    WHERE id = %s
                    """,
                    (hashes['phash'], hashes['dhash'], hashes['ahash'], doc['id']),
                    fetch=False
                )
        
        # Extract Date if missing
        if not doc['detected_date']:
            # We need text for date extraction. 
            print(f"Extracting specific date for {doc['filename']}...")
            text, _ = extract_text_from_pdf(file_path)
            if text:
                date_val = extract_date_from_text(text)
                if date_val:
                    doc['detected_date'] = date_val
                    updated = True
                    # Update DB
                    execute_query(
                        "UPDATE document_analysis SET detected_date = %s WHERE id = %s",
                        (date_val, doc['id']),
                        fetch=False
                    )
        
        updated_docs.append(doc)

    # 3. Group by visual similarity
    # Simple pairwise clustering
    processed_ids = set()
    clusters = []
    
    # Pre-structure for faster access
    doc_list = [d for d in updated_docs if d.get('visual_phash')] # Only cluster successfully hashed docs
    
    for i, doc1 in enumerate(doc_list):
        if doc1['id'] in processed_ids:
            continue
            
        current_cluster = [doc1]
        processed_ids.add(doc1['id'])
        
        hashes1 = {
            'phash': doc1['visual_phash'],
            'dhash': doc1['visual_dhash'],
            'ahash': doc1['visual_ahash']
        }
        
        for doc2 in doc_list[i+1:]:
            if doc2['id'] in processed_ids:
                continue
                
            hashes2 = {
                'phash': doc2['visual_phash'],
                'dhash': doc2['visual_dhash'],
                'ahash': doc2['visual_ahash']
            }
            
            if are_visually_similar(hashes1, hashes2, threshold=5):
                current_cluster.append(doc2)
                processed_ids.add(doc2['id'])
                print(f"Found visual duplicate: {doc1['filename']} ~= {doc2['filename']}")
        
        clusters.append(current_cluster)
    
    # 4. Assign Version Groups and Latest Version
    for cluster in clusters:
        # If cluster has > 1 item, it's a version group
        # Even single items might be a "group" of 1, but we usually care about multiples.
        # However, to be consistent, we might leave singletons NULL unless they have versions.
        
        if len(cluster) > 1:
            group_id = str(uuid.uuid4())
            
            from datetime import datetime
            
            def get_version_priority(filename):
                """
                Return priority score for version type in filename.
                Higher score = preferred as latest.
                Final > Preliminary/Draft
                """
                fn_lower = filename.lower()
                if 'final' in fn_lower:
                    return 3
                elif 'preliminary' in fn_lower or 'prelim' in fn_lower:
                    return 1
                elif 'draft' in fn_lower:
                    return 0
                else:
                    return 2  # Unknown - treat as middle priority
            
            def sort_key(d):
                """
                Sort documents to determine latest version.
                Priority order:
                1. Later date (descending)
                2. Final > Preliminary (when same date)
                3. Higher ID (later upload) as tiebreaker
                """
                dt = d.get('detected_date')
                date_val = dt if dt else datetime.min.date()
                version_priority = get_version_priority(d['filename'])
                return (date_val, version_priority, d['id'])
            
            cluster_sorted = sorted(cluster, key=sort_key, reverse=True)
            
            latest_doc = cluster_sorted[0]
            
            for doc in cluster_sorted:
                is_latest = (doc['id'] == latest_doc['id'])
                
                execute_query(
                    """
                    UPDATE document_analysis 
                    SET version_group_id = %s, is_latest_version = %s
                    WHERE id = %s
                    """,
                    (group_id, is_latest, doc['id']),
                    fetch=False
                )
                version_type = "FINAL" if "final" in doc['filename'].lower() else ("PRELIM" if "prelim" in doc['filename'].lower() else "")
                print(f"  -> {doc['filename']}: Group {group_id}, Latest={is_latest}, Date={doc.get('detected_date')} {version_type}")

    print("Version analysis complete.")

if __name__ == "__main__":
    # Test run
    # Usage: python3 version_task.py <loan_id>
    import sys
    if len(sys.argv) > 1:
        run_version_analysis(sys.argv[1], None)
