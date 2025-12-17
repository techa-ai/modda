
import os
import json
import logging
import sys
from db import execute_query, execute_one
from dedup_utils import extract_text_from_pdf

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_vlm_client():
    try:
        from vlm_utils import VLMClient
        return VLMClient()
    except ImportError as e:
        logger.error(f"vlm_utils not found or dependencies missing: {e}")
        return None
    except Exception as e:
        logger.error(f"Error initializing VLMClient: {e}")
        return None

def get_1008_context(loan_id):
    """Fetch 1008 text content."""
    # Try finding 1008 file path
    query = """
        SELECT file_path FROM document_analysis 
        WHERE loan_id = %s 
        AND (filename ILIKE '%%1008%%')
        ORDER BY detected_date DESC, id DESC LIMIT 1
    """
    res = execute_one(query, (loan_id,))
    if res and res.get('file_path'):
        text, _ = extract_text_from_pdf(res['file_path'])
        return text or "Form 1008 content unreadable."
    return "No Form 1008 found."

def run_llm_version_analysis(loan_id):
    logger.info(f"Starting LLM Version Analysis for Loan {loan_id}")
    
    client = get_vlm_client()
    if not client:
        logger.error("VLM Client unavailable. Aborting LLM analysis.")
        return
        
    context_1008 = get_1008_context(loan_id)
    if len(context_1008) > 5000:
        context_1008 = context_1008[:5000] + "...(truncated)"
    
    # Fetch groups
    rows = execute_query(
        """SELECT id, filename, file_path, version_group_id, detected_date, vlm_analysis
           FROM document_analysis 
           WHERE loan_id = %s AND version_group_id IS NOT NULL 
           ORDER BY version_group_id""",
        (loan_id,)
    )
    
    if not rows:
        logger.info("No grouped documents found to analyze.")
        return

    # Organize by group
    groups = {}
    for r in rows:
        gid = r['version_group_id']
        if gid not in groups: groups[gid] = []
        groups[gid].append(r)
        
    for gid, docs in groups.items():
        if len(docs) < 2:
            logger.info(f"Skipping Group {gid} (only 1 document)")
            continue
            
        # Check if all docs in this group already have VLM analysis
        already_analyzed = all(doc.get('vlm_analysis') is not None for doc in docs)
        if already_analyzed:
            logger.info(f"Skipping Group {gid} - already analyzed")
            continue
            
        logger.info(f"Processing Group {gid} ({len(docs)} documents)")
        
        # Construct Prompt with structured extraction
        prompt = f"""
You are an expert Senior Mortgage Underwriter analyzing mortgage documents.

CONTEXT (Form 1008):
{context_1008}

TASK: Analyze the provided document images and:
1. Extract key attributes from EACH document
2. Determine version relationships
3. Identify the latest/best representative

NOTE: You will see ALL pages of each document for comprehensive analysis.

For EACH document, extract these attributes (look carefully at the actual document content):
- Borrower Name(s)
- SSN (if visible)
- Employer/Company (if applicable)
- Document Date (extract ANY date info you can find: full date like "08/15/2025", month/year like "August 2025", or just year like "2025". Look for dates in headers, footers, or document body. Do NOT leave as null if any date is visible)
- Signature Status (Signed/Unsigned) - CHECK ALL PAGES FOR SIGNATURES
- Any version indicators (Draft, Final, Preliminary, etc.)

DOCUMENTS TO ANALYZE:
"""
        
        doc_map = {}
        doc_images = []
        
        for doc in docs:
            doc_id = doc['id']
            doc_map[doc_id] = doc
            date_str = str(doc.get('detected_date') or "Unknown")
            
            prompt += f"\n--- Document ID: {doc_id} ---"
            prompt += f"\nFilename: {doc['filename']}"
            prompt += f"\nDetected Date: {date_str}\n"
            
            # Store image info for VLM
            doc_images.append({
                'id': doc_id,
                'filename': doc['filename'],
                'path': doc['file_path']
            })
            
        prompt += """
-------------------------------------------------------------
INSTRUCTIONS:
1. Look at the ACTUAL CONTENT of each document image
2. Extract the key attributes listed above for each document
3. Compare documents to determine:
   - Are they DUPLICATES (exact same content)?
   - Are they VERSIONS (same document type, different dates/signatures)?
   - Are they DISTINCT (different borrowers, different document types)?
4. Determine the LATEST / BEST version:
   - Prefer SIGNED over Unsigned
   - Prefer LATER DATE
   - Prefer COMPLETE over incomplete
5. If documents are for DIFFERENT borrowers, mark them as "Distinct Document"
   
OUTPUT FORMAT (JSON ONLY):
{
    "group_summary": "Brief explanation of what you found",
    "documents": [
        {
            "id": <Document ID>,
            "extracted_attributes": {
                "borrower_name": "Name from document",
                "ssn": "XXX-XX-XXXX or null",
                "employer": "Company name or null",
                "document_date": "Date or null",
                "has_signature": true/false
            },
            "is_latest": true/false,
            "category": "Duplicate" | "Version" | "Distinct Document",
            "borrower": "Borrower" | "Co-Borrower" | "Both" | "Unknown",
            "status": "Signed" | "Unsigned" | "Draft" | "Complete" | "Incomplete",
            "reasoning": "Short explanation based on what you see in the image"
        }
    ]
}
"""
        
        try:
            # Use VLM with document images instead of text
            # Process each document and combine into single analysis
            from pdf2image import convert_from_path
            import base64
            import io
            
            all_images = []
            for doc_info in doc_images:
                try:
                    # Convert PDF to images - limit pages to avoid token limits
                    images = convert_from_path(
                        doc_info['path'],
                        dpi=150,
                        fmt='jpeg'
                    )
                    
                    # Send first 3 pages + last 2 pages (captures most content + signatures)
                    # This avoids "Input too long" errors while maintaining accuracy
                    pages_to_send = []
                    if len(images) <= 5:
                        pages_to_send = images
                    else:
                        pages_to_send = images[:3] + images[-2:]
                    
                    for img in pages_to_send:
                        buffered = io.BytesIO()
                        img.save(buffered, format="JPEG", quality=85)
                        img_b64 = base64.b64encode(buffered.getvalue()).decode()
                        all_images.append(img_b64)
                        
                except Exception as e:
                    logger.warning(f"Failed to convert {doc_info['filename']} to image: {e}")
            
            if not all_images:
                logger.warning(f"No images extracted for Group {gid}, skipping")
                continue
            
            # Call VLM with images
            response = client.process_images(all_images, prompt, return_json=True)
            
            # Handle case where Claude wraps JSON in markdown or text
            if isinstance(response, str):
                # Try to extract JSON from markdown code blocks
                import re
                json_match = re.search(r'```json\s*(\{.*?\})\s*```', response, re.DOTALL)
                if json_match:
                    try:
                        response = json.loads(json_match.group(1))
                    except:
                        pass
                else:
                    # Try to find JSON object in the string
                    json_match = re.search(r'\{.*"documents".*\}', response, re.DOTALL)
                    if json_match:
                        try:
                            response = json.loads(json_match.group(0))
                        except:
                            pass
            
            if isinstance(response, dict) and 'documents' in response:
                
                logging.info(f"LLM Response for Group {gid}: {json.dumps(response, indent=2)}")
                
                for doc_result in response['documents']:
                    doc_id = doc_result.get('id')
                    is_latest = doc_result.get('is_latest', False)
                    
                    if doc_id in doc_map:
                        # Extract date from Claude's analysis if available
                        extracted_attrs = doc_result.get('extracted_attributes', {})
                        extracted_date_raw = extracted_attrs.get('document_date')
                        
                        # Normalize date for PostgreSQL (handle formats like "2024", "August 2025", "07/01/2025 thru 07/31/2025")
                        normalized_date = None
                        if extracted_date_raw:
                            import re
                            # Try to extract first valid date pattern
                            date_match = re.search(r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{4}|\d{4}[/-]\d{1,2}[/-]\d{1,2}|\d{4})\b', extracted_date_raw)
                            if date_match:
                                normalized_date = date_match.group(1)
                                # Convert to YYYY-MM-DD if needed
                                if len(normalized_date) == 4:  # Just year
                                    normalized_date = f"{normalized_date}-01-01"
                        
                        # Update with normalized date if available
                        if normalized_date:
                            execute_query(
                               "UPDATE document_analysis SET is_latest_version = %s, version_metadata = %s, vlm_analysis = %s, detected_date = %s WHERE id = %s",
                               (is_latest, json.dumps(doc_result), json.dumps(doc_result), normalized_date, doc_id),
                               fetch=False
                            )
                        else:
                            # No valid date, just update other fields
                            execute_query(
                               "UPDATE document_analysis SET is_latest_version = %s, version_metadata = %s, vlm_analysis = %s WHERE id = %s",
                               (is_latest, json.dumps(doc_result), json.dumps(doc_result), doc_id),
                               fetch=False
                            )
                
                
                # Update duplicate counts based on Claude's categorization
                duplicates_in_group = [d for d in response['documents'] if d.get('category') == 'Duplicate']
                if duplicates_in_group:
                    # Mark duplicates with status='duplicate'
                    for dup in duplicates_in_group:
                        dup_id = dup.get('id')
                        if dup_id in doc_map:
                            execute_query(
                                "UPDATE document_analysis SET status = 'duplicate' WHERE id = %s",
                                (dup_id,),
                                fetch=False
                            )
                    
                    # Update duplicate_count on the master (latest) document
                    latest_doc = next((d for d in response['documents'] if d.get('is_latest')), None)
                    if latest_doc:
                        latest_id = latest_doc.get('id')
                        dup_count = len(duplicates_in_group)
                        execute_query(
                            "UPDATE document_analysis SET duplicate_count = %s WHERE id = %s",
                            (dup_count, latest_id),
                            fetch=False
                        )
                
                logger.info(f"Updated Group {gid} successfully.")
                
            else:
                logger.warning(f"Invalid JSON response for Group {gid}: {response}")
                
        except Exception as e:
            logger.error(f"Error processing Group {gid}: {e}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        run_llm_version_analysis(int(sys.argv[1]))
    else:
        print("Usage: python step2_llm_analysis.py <loan_id>")
