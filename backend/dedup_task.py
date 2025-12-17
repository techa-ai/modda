"""
Background task for document deduplication analysis
"""

import json
import threading
from datetime import datetime
from dedup_utils import deduplicate_documents
from db import execute_query, execute_one


def run_deduplication_analysis(loan_id, doc_location):
    """
    Run deduplication analysis in background and store results in database
    """
    def background_task():
        try:
            print(f"Starting deduplication analysis for loan {loan_id}...")
            
            # Update status to running
            execute_query(
                "UPDATE loans SET dedup_status = %s WHERE id = %s",
                ('running', loan_id),
                fetch=False
            )
            
            # Run deduplication
            result = deduplicate_documents(doc_location)
            
            # PRESERVE existing deep extraction data before delete
            existing_analysis = execute_query(
                """SELECT filename, individual_analysis, version_metadata 
                   FROM document_analysis 
                   WHERE loan_id = %s AND individual_analysis IS NOT NULL""",
                (loan_id,)
            )
            preserved_data = {row['filename']: {
                'individual_analysis': row['individual_analysis'],
                'version_metadata': row['version_metadata']
            } for row in (existing_analysis or [])}
            
            if preserved_data:
                print(f"Preserving deep extraction data for {len(preserved_data)} documents...", flush=True)
            
            # Clear existing analysis for this loan
            execute_query(
                "DELETE FROM document_analysis WHERE loan_id = %s",
                (loan_id,),
                fetch=False
            )
            
            # Store unique and master documents first
            doc_id_map = {}  # Map filename to database ID
            unique_inserted = 0
            duplicates_inserted = 0
            
            print(f"Inserting {len(result['unique'])} unique documents...", flush=True)
            for doc in result['unique']:
                try:
                    cursor_result = execute_one(
                        """INSERT INTO document_analysis 
                           (loan_id, filename, file_path, file_size, page_count, 
                            text_hash, status, upload_date, duplicate_count)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                           RETURNING id""",
                        (
                            loan_id,
                            doc['name'],
                            doc['path'],
                            doc['size'],
                            doc.get('pages', 0),
                            doc.get('hash'),
                            doc.get('status', 'unknown'),
                            datetime.fromtimestamp(doc['upload_date']) if 'upload_date' in doc else None,
                            doc.get('duplicate_count', 0)
                        )
                    )
                    if cursor_result:
                        doc_id_map[doc['name']] = cursor_result['id']
                        unique_inserted += 1
                except Exception as ex:
                    print(f"Error inserting unique doc {doc['name']}: {ex}", flush=True)
            
            print(f"Inserted {unique_inserted} unique documents. Inserting duplicates...", flush=True)
            
            # Store duplicate documents with master references
            for doc in result.get('duplicates', []):
                try:
                    master_name = doc.get('master')
                    master_id = doc_id_map.get(master_name) if master_name else None
                    
                    execute_query(
                        """INSERT INTO document_analysis 
                           (loan_id, filename, file_path, file_size, page_count, 
                            text_hash, status, upload_date, master_document_id)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                        (
                            loan_id,
                            doc['name'],
                            doc['path'],
                            doc['size'],
                            doc.get('pages', 0),
                            doc.get('hash'),
                            'duplicate',
                            datetime.fromtimestamp(doc['upload_date']) if 'upload_date' in doc else None,
                            master_id
                        ),
                        fetch=False
                    )
                    duplicates_inserted += 1
                except Exception as ex:
                    print(f"Error inserting duplicate doc {doc['name']}: {ex}", flush=True)
            
            print(f"Inserted {duplicates_inserted} duplicate documents.", flush=True)
            
            # RESTORE preserved deep extraction and metadata
            if preserved_data:
                restored = 0
                for filename, data in preserved_data.items():
                    try:
                        execute_query(
                            """UPDATE document_analysis 
                               SET individual_analysis = %s, version_metadata = %s
                               WHERE loan_id = %s AND filename = %s""",
                            (
                                json.dumps(data['individual_analysis']) if data['individual_analysis'] else None,
                                json.dumps(data['version_metadata']) if data['version_metadata'] else None,
                                loan_id,
                                filename
                            ),
                            fetch=False
                        )
                        restored += 1
                    except Exception as ex:
                        print(f"Error restoring data for {filename}: {ex}", flush=True)
                print(f"Restored deep extraction data for {restored}/{len(preserved_data)} documents.", flush=True)
            
            # Update loan status
            execute_query(
                "UPDATE loans SET dedup_status = %s, dedup_last_run = %s WHERE id = %s",
                ('completed', datetime.now(), loan_id),
                fetch=False
            )
            
            print(f"Deduplication analysis completed for loan {loan_id}")
            print(f"  Total: {result['stats']['total']}, Unique: {result['stats']['unique']}, Duplicates: {result['stats']['duplicates']}")
            
            # Trigger Version Analysis (Step 2)
            try:
                print("Starting Version Analysis (Step 2)...")
                from version_task import run_version_analysis
                run_version_analysis(loan_id, doc_location)
            except Exception as ve:
                print(f"Error in version analysis: {ve}")
                # Don't fail the whole task if versioning fails
            
        except Exception as e:
            print(f"Error in deduplication analysis for loan {loan_id}: {e}")
            import traceback
            traceback.print_exc()
            
            # Update status to failed
            execute_query(
                "UPDATE loans SET dedup_status = %s WHERE id = %s",
                ('failed', loan_id),
                fetch=False
            )
    
    # Start background thread
    thread = threading.Thread(target=background_task, daemon=True)
    thread.start()
    
    return {'message': 'Deduplication analysis started in background', 'loan_id': loan_id}
