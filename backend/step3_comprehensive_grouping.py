#!/usr/bin/env python3
"""
Step 3: Comprehensive Document Grouping
Analyzes all remaining ungrouped documents (< 10 pages) using Claude VLM.
Extracts detailed metadata, then performs intelligent batch grouping.
"""

import sys
import json
import logging
import base64
import io
from pathlib import Path
from pdf2image import convert_from_path
from db import execute_query
sys.path.append('/Users/sunny/Applications/bts/jpmorgan/mortgage/mt360-viewer/analytics_dashboard')
from vlm_utils import VLMClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

client = VLMClient()

def get_ungrouped_documents(loan_id):
    """Get all documents without version_group_id and < 10 pages"""
    query = """
        SELECT id, loan_id, filename, file_path, page_count, 
               individual_analysis
        FROM document_analysis
        WHERE loan_id = %s 
          AND version_group_id IS NULL
          AND (page_count IS NULL OR page_count < 10)
        ORDER BY filename
    """
    return execute_query(query, (loan_id,))

def extract_document_metadata(doc):
    """Extract comprehensive metadata from a single document using Claude"""
    doc_id = doc['id']
    filename = doc['filename']
    file_path = doc['file_path']
    
    # Check if already analyzed
    if doc.get('individual_analysis'):
        logger.info(f"Skipping {filename} - already analyzed")
        # JSONB column returns dict directly, not string
        analysis = doc['individual_analysis']
        return analysis if isinstance(analysis, dict) else json.loads(analysis)
    
    logger.info(f"Analyzing document {doc_id}: {filename}")
    
    try:
        # Convert PDF to images (first 3 + last 2 pages)
        images = convert_from_path(file_path, dpi=150, fmt='jpeg')
        
        pages_to_send = []
        if len(images) <= 5:
            pages_to_send = images
        else:
            pages_to_send = images[:3] + images[-2:]
        
        # Encode images
        image_data = []
        for img in pages_to_send:
            buffered = io.BytesIO()
            img.save(buffered, format="JPEG", quality=85)
            img_b64 = base64.b64encode(buffered.getvalue()).decode()
            image_data.append(img_b64)
        
        # Prompt for detailed extraction
        prompt = f"""Analyze this document (filename: {filename}) and extract ALL relevant information as JSON.

EXTRACT:
1. Document Type (e.g., "W-2", "Pay Stub", "Bank Statement", "Tax Return", etc.)
2. Borrower/Applicant Name(s) - extract ALL names mentioned
3. Co-Borrower Name (if different from primary)
4. SSN or Tax ID (if visible)
5. Employer/Company Name
6. Document Date (any date: full date, month/year, or just year)
7. Period Covered (for statements: "01/01/2024 to 12/31/2024")
8. Account Numbers (for bank statements)
9. Signature Status: "Signed" or "Unsigned" (check ALL pages)
10. Version Indicators: "Draft", "Final", "Preliminary", "Revised", etc.
11. Page Numbers Visible: Does document show "Page X of Y"?
12. Content Consistency: Do all pages appear to belong to this document type?
13. Filename Match: Does the filename accurately describe the content?
14. Anomalies: Any mixed content, wrong pages, or mismatches?

Return ONLY valid JSON:
{{
  "document_type": "...",
  "borrower_name": "...",
  "co_borrower_name": "..." or null,
  "ssn": "..." or null,
  "employer": "..." or null,
  "document_date": "...",
  "period_covered": "..." or null,
  "account_numbers": [...] or null,
  "has_signature": true/false,
  "version_indicator": "..." or null,
  "page_numbers_visible": true/false,
  "content_consistent": true/false,
  "filename_matches_content": true/false,
  "anomalies": "..." or null,
  "ocr_text_summary": "Brief summary of key text visible in document"
}}"""
        
        response = client.process_images(image_data, prompt)
        
        # Parse JSON from response
        try:
            # Try to extract JSON from markdown blocks
            if '```json' in response:
                json_str = response.split('```json')[1].split('```')[0].strip()
            elif '```' in response:
                json_str = response.split('```')[1].split('```')[0].strip()
            else:
                json_str = response.strip()
            
            metadata = json.loads(json_str)
            
            # Store in database
            execute_query(
                "UPDATE document_analysis SET individual_analysis = %s WHERE id = %s",
                (json.dumps(metadata), doc_id),
                fetch=False
            )
            
            logger.info(f"✓ Extracted metadata for {filename}")
            return metadata
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON for {filename}: {e}")
            logger.error(f"Response: {response[:500]}")
            return None
            
    except Exception as e:
        logger.error(f"Error analyzing {filename}: {e}")
        return None

def get_all_documents_metadata(loan_id):
    """Get metadata for ALL documents (both grouped and ungrouped)"""
    query = """
        SELECT id, filename, individual_analysis, vlm_analysis, 
               version_group_id, is_latest_version, version_metadata
        FROM document_analysis
        WHERE loan_id = %s
        ORDER BY filename
    """
    docs = execute_query(query, (loan_id,))
    
    all_metadata = {}
    for doc in docs:
        doc_id = doc['id']
        
        # Use individual_analysis if available, otherwise vlm_analysis
        # JSONB columns return dicts directly, not strings
        if doc.get('individual_analysis'):
            analysis = doc['individual_analysis']
            metadata = analysis if isinstance(analysis, dict) else json.loads(analysis)
        elif doc.get('vlm_analysis'):
            vlm = doc['vlm_analysis']
            vlm_data = vlm if isinstance(vlm, dict) else json.loads(vlm)
            # Extract relevant fields from vlm_analysis
            metadata = {
                "document_type": vlm_data.get('category', 'Unknown'),
                "borrower_name": vlm_data.get('extracted_attributes', {}).get('borrower_name'),
                "document_date": vlm_data.get('extracted_attributes', {}).get('document_date'),
                "has_signature": vlm_data.get('extracted_attributes', {}).get('has_signature'),
                "existing_group_id": doc.get('version_group_id'),
                "is_currently_latest": doc.get('is_latest_version'),
                "filename": doc['filename']
            }
        else:
            # No metadata yet - skip
            continue
        
        all_metadata[doc_id] = metadata
    
    return all_metadata

def extract_json_from_response(response_text):
    """
    Extracts a JSON object from a string, handling markdown code blocks.
    """
    try:
        # Try to extract JSON from markdown blocks
        if '```json' in response_text:
            json_str = response_text.split('```json')[1].split('```')[0].strip()
        elif '```' in response_text:
            json_str = response_text.split('```')[1].split('```')[0].strip()
        else:
            json_str = response_text.strip()
        
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON from response: {e}")
        logger.error(f"Response snippet: {response_text[:500]}")
        return None
    except Exception as e:
        logger.error(f"Error extracting JSON: {e}")
        return None

def batch_group_documents(loan_id, documents_metadata):
    """
    Process ALL documents in a single batch with robust JSON parsing.
    """
    logger.info(f"Performing batch grouping for {len(documents_metadata)} documents")
    
    # Prepare summary for Claude
    docs_summary = []
    for doc_id, metadata in documents_metadata.items():
        if metadata:
            docs_summary.append({
                "id": doc_id,
                "metadata": metadata
            })
    
    # Chunk size 50 with minified schema should be safe
    chunk_size = 50
    chunks = [docs_summary[i:i + chunk_size] for i in range(0, len(docs_summary), chunk_size)]
    
    initial_groups = []
    all_anomalies = []
    
    logger.info(f"--- PASS 1: Processing {len(chunks)} chunks ---")
    
    for i, chunk in enumerate(chunks):
        logger.info(f"Processing Chunk {i+1}/{len(chunks)} ({len(chunk)} docs)")
        
        # Minified prompt
        prompt = f"""Analyze {len(chunk)} docs.
Group into: VERSIONS, DUPLICATES, DISTINCT.
Select LATEST version.

DOCS:
{json.dumps(chunk, indent=2)}

OUTPUT ONLY STARTING WITH {{
{{
  "g": [  
    {{
      "t": "v|d|u",        // v=version, d=duplicate, u=distinct
      "ids": [123, 456],   
      "l": 123,            // latest_id
      "n": "Name",         // group_name
      "b": "Name"          // borrower
    }}
  ],
  "a": [  
    {{
      "id": 789,
      "err": "Issue"
    }}
  ]
}}"""
        
        try:
            text_content = json.dumps(chunk, indent=2)
            response = client.process_text(text_content, prompt, return_json=False)
            result = extract_json_from_response(response)
            
            if result:
                # Expand minified keys
                for g in result.get('g', []):
                    initial_groups.append({
                        "group_type": "version" if g['t'] == 'v' else "duplicate" if g['t'] == 'd' else "distinct",
                        "document_ids": g['ids'],
                        "latest_document_id": g['l'],
                        "group_name": g.get('n', 'Unknown'),
                        "borrower": g.get('b', 'Unknown'),
                        "reasoning": "Batch grouping"
                    })
                
                for a in result.get('a', []):
                    all_anomalies.append({
                        "document_id": a['id'],
                        "issue": a['err'],
                        "severity": "medium"
                    })
            else:
                logger.error(f"Chunk {i+1} failed to parse.")
                # Fallback: All distinct
                for doc in chunk:
                    initial_groups.append({
                        "group_type": "distinct",
                        "document_ids": [doc['id']],
                        "latest_document_id": doc['id'],
                        "group_name": doc['metadata'].get('filename'),
                        "borrower": doc['metadata'].get('borrower_name'),
                        "reasoning": "Fallback"
                    })

        except Exception as e:
            logger.error(f"Error in Chunk {i+1}: {e}")
            continue

    # --- PASS 2: Merge Groups ---
    logger.info(f"--- PASS 2: Merging {len(initial_groups)} Initial Groups ---")
    
    # Simple merge logic: Send group summaries to Claude
    groups_summary = []
    for idx, g in enumerate(initial_groups):
        groups_summary.append({
            "idx": idx,
            "n": g['group_name'],
            "b": g['borrower']
        })
        
    prompt_merge = f"""Identify merges for these {len(groups_summary)} groups.
Return ONLY indices to merge.

GROUPS:
{json.dumps(groups_summary, indent=2)}

RETURN:
{{
  "m": [ // Merges
    {{
      "stay": 0,       // Index of master group (keeps name)
      "join": [5, 12]  // Indices to merge into it
    }}
  ]
}}"""

    try:
        if groups_summary:
            response_merge = client.process_text(json.dumps(groups_summary, indent=2), prompt_merge, return_json=False)
            merge_result = extract_json_from_response(response_merge)
            
            final_groups = []
            skip_indices = set()
            
            if merge_result:
                for m in merge_result.get('m', []):
                    master_idx = m['stay']
                    if master_idx >= len(initial_groups): continue
                    
                    master_group = initial_groups[master_idx]
                    skip_indices.add(master_idx)
                    
                    for child_idx in m['join']:
                        if child_idx >= len(initial_groups) or child_idx in skip_indices: continue
                        child_group = initial_groups[child_idx]
                        master_group['document_ids'].extend(child_group['document_ids'])
                        skip_indices.add(child_idx)
                    
                    final_groups.append(master_group)
                
                # Add unmerged
                for idx, g in enumerate(initial_groups):
                    if idx not in skip_indices:
                        final_groups.append(g)
                
                return {"groups": final_groups, "anomalies": all_anomalies}
            
    except Exception as e:
        logger.error(f"Error in Pass 2: {e}")

    return {"groups": initial_groups, "anomalies": all_anomalies}

def apply_grouping(loan_id, grouping_result):
    """Apply Claude's grouping decisions to the database"""
    import uuid
    
    groups = grouping_result.get('groups', [])
    anomalies = grouping_result.get('anomalies', [])
    
    # Store anomalies
    for anomaly in anomalies:
        doc_id = anomaly['document_id']
        execute_query(
            """UPDATE document_analysis 
               SET anomaly_detected = %s, anomaly_severity = %s 
               WHERE id = %s""",
            (anomaly['issue'], anomaly['severity'], doc_id),
            fetch=False
        )
    
    # Apply groups
    for group in groups:
        group_id = str(uuid.uuid4())
        doc_ids = group['document_ids']
        latest_id = group.get('latest_document_id')
        group_type = group['group_type']
        
        for doc_id in doc_ids:
            is_latest = (doc_id == latest_id)
            
            # Determine status
            if group_type == 'duplicate':
                status = 'duplicate' if not is_latest else 'unique'
            else:
                status = 'unique'
            
            # Store group metadata
            group_metadata = {
                "group_name": group['group_name'],
                "group_type": group_type,
                "borrower": group['borrower'],
                "reasoning": group['reasoning']
            }
            
            execute_query(
                """UPDATE document_analysis 
                   SET version_group_id = %s, 
                       is_latest_version = %s,
                       status = %s,
                       version_metadata = %s
                   WHERE id = %s""",
                (group_id, is_latest, status, json.dumps(group_metadata), doc_id),
                fetch=False
            )
        
        # Update duplicate counts
        if group_type == 'duplicate':
            dup_count = len([d for d in doc_ids if d != latest_id])
            execute_query(
                "UPDATE document_analysis SET duplicate_count = %s WHERE id = %s",
                (dup_count, latest_id),
                fetch=False
            )
        
        logger.info(f"✓ Created {group_type} group: {group['group_name']} ({len(doc_ids)} docs)")

def main(loan_id):
    logger.info(f"Starting comprehensive grouping for Loan {loan_id}")
    
    # Step 1: Get ungrouped documents for individual analysis
    ungrouped = get_ungrouped_documents(loan_id)
    logger.info(f"Found {len(ungrouped)} ungrouped documents")
    
    # Step 2: Extract metadata from ungrouped documents
    if len(ungrouped) > 0:
        logger.info("Extracting metadata from ungrouped documents...")
        for doc in ungrouped:
            extract_document_metadata(doc)
    
    # Step 3: Get ALL documents metadata (both grouped and ungrouped)
    logger.info("Loading metadata for ALL documents...")
    all_documents_metadata = get_all_documents_metadata(loan_id)
    logger.info(f"Loaded metadata for {len(all_documents_metadata)} documents")
    
    if len(all_documents_metadata) == 0:
        logger.info("No documents with metadata to process")
        return
    
    # Step 4: Batch grouping with ALL documents
    grouping_result = batch_group_documents(loan_id, all_documents_metadata)
    
    if not grouping_result:
        logger.error("Batch grouping failed")
        return
    
    # Step 5: Apply grouping to database
    apply_grouping(loan_id, grouping_result)
    
    logger.info("✅ Comprehensive grouping complete!")
    
    # Print summary
    print("\n" + "="*60)
    print("COMPREHENSIVE GROUPING SUMMARY")
    print("="*60)
    print(f"Ungrouped documents analyzed: {len(ungrouped)}")
    print(f"Total documents in batch grouping: {len(all_documents_metadata)}")
    print(f"Groups created/updated: {len(grouping_result.get('groups', []))}")
    print(f"Anomalies detected: {len(grouping_result.get('anomalies', []))}")
    print("="*60)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        loan_id = int(sys.argv[1])
    else:
        loan_id = 1
    
    main(loan_id)
