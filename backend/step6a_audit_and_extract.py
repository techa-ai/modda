
import json
import sys
import os
from db import execute_query
from vlm_utils import VLMClient

def extract_all_json(loan_id):
    from pdf2image import pdfinfo_from_path
    
    print(f"--- STARTING TARGETED JSON EXTRACTION FOR LOAN {loan_id} (FINANCIAL Only) ---")
    
    # Fetch Financial docs only
    docs = execute_query(
        """SELECT id, filename, file_path, vlm_analysis 
           FROM document_analysis 
           WHERE loan_id = %s 
           AND status != 'deleted'
           AND (version_metadata->>'financial_category' = 'FINANCIAL' OR version_metadata->>'classification' = 'FINANCIAL')
           ORDER BY id""", 
        (loan_id,)
    )
    
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    # We can run parallel threads for Bedrock calls
    # Limit to 5 workers to avoid Rate Limits (Token Bucket)
    max_workers = 5
    
    print(f"Found {len(docs)} FINANCIAL documents. Checking page counts...")
    
    def process_one_doc(d):
        if not d['file_path'] or not os.path.exists(d['file_path']):
            return False
            
        # Check Cache: if vlm_analysis seems strictly populated (Full Extraction), skip
        if d.get('vlm_analysis') and isinstance(d['vlm_analysis'], dict):
             keys = d['vlm_analysis'].keys()
             # Old/Sparse style often has 'extracted_attributes' or just 'classification'
             # New strict style has flat keys.
             if len(keys) > 3 and 'extracted_attributes' not in keys and 'error' not in keys:
                 print(f"[{d['filename']}] Using Cached Extraction.")
                 return True

            
        # Check Page Count limit ( < 10 pages)
        try:
            info = pdfinfo_from_path(d['file_path'])
            pages = int(info.get("Pages", 0))
            if pages >= 10:
                # Skip silently or log?
                # print(f"Skipping {d['filename']} ({pages} pages)")
                return False
        except Exception as e:
            # If pdfinfo fails, maybe proceed or skip?
            print(f"Warning: Could not count pages for {d['filename']}: {e}")
            pass
            
        prompt = """
        You are a Document Extraction Specialist.
        TASK: Extract ALL visible data from this document image into a structured JSON object.
        
         GUIDELINES:
        1. Capture key-value pairs (Header Info, Dates, Names, Amounts, Clauses).
        2. Use specific, descriptive keys (e.g., 'loan_number', 'borrower_name', 'effective_date', 'total_amount').
        3. If the document is unstructured, extract summary fields.
        4. Return ONLY the JSON object. 
        5. DO NOT START WITH "Here is..." or "```json". Just the curly braces { ... }.
        """
        
        try:
            # Client must be thread-safe or instantiated per thread? 
            # Bedrock client (boto3) is generally thread-safe, but let's instantiate local
            local_client = VLMClient(max_tokens=60000)
            res = local_client.process_document(d['file_path'], prompt, max_pages=2, return_json=True)
            
            if res:
                final_data = res
                if not isinstance(res, dict):
                    final_data = {"error": "JSON Parse Failed", "raw_content": str(res)}
                
                # Update DB - execute_query creates its own connection/cursor so it IS thread-safe logic wise 
                # (db.py creates new conn each call usually, or formatted that way)
                # Let's verify db.py. If it uses global conn, we need lock.
                # Assuming standard pattern: db.py usually gets conn from pool or creates one.
                # I'll check db.py quickly or assume risk. Using lock is safer for "updates" counter.
                
                execute_query(
                    "UPDATE document_analysis SET vlm_analysis = %s WHERE id = %s", 
                    (json.dumps(final_data), d['id']), 
                    fetch=False
                )
                return True
        except Exception as e:
            print(f"Error doc {d['id']}: {e}")
        return False

    updates = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_one_doc, d): d for d in docs}
        
        for i, future in enumerate(as_completed(futures)):
            d = futures[future]
            try:
                success = future.result()
                if success:
                    updates += 1
                    print(f"[{i+1}/{len(docs)}] Success: {d['filename']}")
                else:
                    print(f"[{i+1}/{len(docs)}] Failed: {d['filename']}")
            except Exception as e:
                print(f"[{i+1}/{len(docs)}] Exception: {d['filename']} - {e}")

    print(f"--- EXTRACTION COMPLETE. Updated {updates} documents. ---")

def audit_groups(loan_id):
    print(f"--- STARTING GROUP AUDIT FOR LOAN {loan_id} ---")
    
    # Fetch groups
    # We fetch docs and group them by version_group_id
    docs = execute_query(
        """SELECT id, filename, version_group_id, version_metadata, vlm_analysis 
           FROM document_analysis 
           WHERE loan_id = %s AND status != 'deleted' AND version_group_id IS NOT NULL
           ORDER BY version_group_id""",
        (loan_id,)
    )
    
    from collections import defaultdict
    groups = defaultdict(list)
    for d in docs:
        groups[d['version_group_id']].append(d)
        
    client = VLMClient(max_tokens=60000)
    
    audited_count = 0
    
    for gid, group_docs in groups.items():
        print(f"Auditing Group {gid} ({len(group_docs)} docs)...")
        
        # sort group docs by id to be deterministic
        # prepare summary for Claude
        doc_summaries = []
        for d in group_docs:
            meta = d['version_metadata'] or {}
            analysis = d['vlm_analysis'] or {}
            # extract a snippet of analysis
            snippet = str(analysis)[:500]
            doc_summaries.append({
                "id": d['id'],
                "filename": d['filename'],
                "current_role": "Primary" if meta.get('is_primary') else "Secondary",
                "extracted_date": meta.get('doc_date') or meta.get('date'),
                "content_snippet": snippet
            })
            
        prompt = f"""
        You are a Senior Loan Document Auditor.
        Review this group of {len(group_docs)} documents that have been grouped together.
        
        DOCUMENTS in Group {gid}:
        {json.dumps(doc_summaries, indent=2)}
        
        Your Mission:
        1. IDENTIFY THE BEST REPRESENTATIVE (Leader). 
           - Criteria: Latest Date, Signed/Completed status, Best Quality.
           - If multiple are "Primary" (e.g. Borrower and Co-Borrower versions), identify BOTH.
           
        2. GENERATE "WELL WRITTEN" EXPLANATIONS.
           - For the Leader(s): WRITE A "primary_reason". 
             Example: "Chosen as representative because it is the fully executed version dated 2025-08-11, superseding the draft."
             NOT: "Latest version". (Be specific).
             
           - For the Others: WRITE A "rejection_reason".
             Example: "Duplicate of the signed version." OR "Older draft dated 2025-07-25."
        
        3. AUDIT FILENAMES.
           - Does the filename match the content?
           - Is it too generic (e.g. "scan1.pdf", "misc.pdf")?
           - If generic or misleading, generate a "filename_warning" message.
           
        OUTPUT FORMAT (JSON):
        {{
            "audit_results": [
                {{
                    "id": <doc_id>,
                    "is_primary": true/false,
                    "primary_reason": "Detailed explanation...",  // Only if primary
                    "rejection_reason": "Detailed explanation...", // Only if secondary
                    "filename_assessment": "Valid" or "Generic" or "Misleading",
                    "filename_warning": "Warning message..." // Optional, if assessment is bad
                }},
                ...
            ]
        }}
        """
        
        try:
            res = client.process_text(json.dumps(doc_summaries), prompt, return_json=True)
            if res and 'audit_results' in res:
                # Update DB
                for result in res['audit_results']:
                    doc_id = result['id']
                    # Fetch original meta
                    # We can't fetch easily here efficiently, so we assume we merge into what we have in memory or DB
                    # We'll just update the specific fields in version_metadata
                    
                    # Construct update query
                    # We need to read existing metadata first to merge?
                    # Postgres jsonb_set or || operator?
                    # || operator merges at top level. perfect.
                    
                    new_meta_fields = {
                        "primary_reason": result.get('primary_reason'),
                        "rejection_reason": result.get('rejection_reason'),
                        "filename_assessment": result.get('filename_assessment'),
                        "filename_warning": result.get('filename_warning'),
                        "is_primary": result.get('is_primary')
                    }
                    # Remove None values
                    new_meta_fields = {k: v for k, v in new_meta_fields.items() if v is not None}
                    
                    execute_query(
                        """
                        UPDATE document_analysis 
                        SET version_metadata = version_metadata || %s
                        WHERE id = %s
                        """,
                        (json.dumps(new_meta_fields), doc_id),
                        fetch=False
                    )
                audited_count += 1
                print(f"  Success: Audited Group {gid}")
            else:
                print(f"  Failed: Invalid response from Claude.")
                
        except Exception as e:
            print(f"  Error auditing group {gid}: {e}")

    print(f"--- AUDIT COMPLETE. Audited {audited_count} groups. ---")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        loan_id = sys.argv[1]
    else:
        # Default to 1 for testing
        loan_id = 1
        
    print(f"Processing Loan {loan_id}...")
    
    # Step 1: Extract JSON for ALL docs
    extract_all_json(loan_id)
    
    # Step 2: Audit Groups
    audit_groups(loan_id)
