"""
Batch Deep JSON Extraction for ALL Unique Documents

Processes all documents that are missing individual_analysis.
Uses Claude for page-wise extraction with intelligent batching.
"""

import os
import sys
import json
import time
import logging
from pdf2image import convert_from_path
import base64
from io import BytesIO
from db import execute_query, get_db_connection
from bedrock_config import call_bedrock

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def convert_page_to_base64(image, quality=85):
    """Convert PIL Image to base64 string"""
    buffered = BytesIO()
    image.save(buffered, format="JPEG", quality=quality)
    return base64.b64encode(buffered.getvalue()).decode('utf-8')

def extract_page_json(image_base64, page_num, total_pages, filename):
    """Extract structured JSON from a single page"""
    
    prompt = f"""Analyze page {page_num} of {total_pages} from "{filename}".

Extract ALL data into structured JSON:
{{
    "page_number": {page_num},
    "page_type": "form|statement|report|table|text|cover|signature_page",
    "document_type": "What type of document/section this is",
    "key_data": {{
        // All important fields and values found
    }},
    "financial_data": {{
        // Any amounts, dates, account numbers
    }},
    "parties": {{
        "names": [],
        "companies": [],
        "addresses": []
    }},
    "has_signature": true/false,
    "text_summary": "Brief summary of page content"
}}

Return ONLY valid JSON."""

    try:
        response = call_bedrock(
            prompt=prompt,
            image_base64=image_base64,
            model="us.anthropic.claude-sonnet-4-20250514-v1:0",  # Use Sonnet for speed
            max_tokens=4000
        )
        
        text = response
        if '```json' in text:
            text = text.split('```json')[1].split('```')[0].strip()
        elif '```' in text:
            text = text.split('```')[1].split('```')[0].strip()
        
        return json.loads(text)
    except Exception as e:
        logger.error(f"Error extracting page {page_num}: {e}")
        return {"page_number": page_num, "error": str(e)}

def create_document_summary(pages_data, filename):
    """Create a summary from extracted page data"""
    
    # Compile key information
    all_parties = set()
    all_dates = []
    all_amounts = []
    doc_types = set()
    has_any_signature = False
    
    for page in pages_data:
        if page.get('parties'):
            all_parties.update(page['parties'].get('names', []))
        if page.get('financial_data'):
            fd = page['financial_data']
            if fd.get('date'): all_dates.append(fd['date'])
            if fd.get('amount'): all_amounts.append(fd['amount'])
        if page.get('document_type'):
            doc_types.add(page['document_type'])
        if page.get('has_signature'):
            has_any_signature = True
    
    return {
        "filename": filename,
        "total_pages": len(pages_data),
        "document_types": list(doc_types),
        "parties_found": list(all_parties)[:10],
        "has_signature": has_any_signature,
        "key_dates": all_dates[:5],
        "key_amounts": all_amounts[:10]
    }

def process_document(doc_id, filename, file_path, max_pages=50):
    """Process a single document with page-wise extraction"""
    
    logger.info(f"\n{'='*60}")
    logger.info(f"Processing: {filename}")
    logger.info(f"{'='*60}")
    
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        return None
    
    try:
        # Convert PDF to images
        logger.info("Converting PDF to images...")
        images = convert_from_path(file_path, dpi=100)  # Lower DPI for speed
        total_pages = len(images)
        logger.info(f"Total pages: {total_pages}")
        
        # Limit pages for very large documents
        if total_pages > max_pages:
            logger.warning(f"Document has {total_pages} pages, processing first {max_pages}")
            images = images[:max_pages]
        
        # Process each page
        pages_data = []
        for idx, image in enumerate(images, 1):
            logger.info(f"  Page {idx}/{len(images)}...")
            
            # Convert to base64
            image_base64 = convert_page_to_base64(image)
            
            # Extract JSON
            page_json = extract_page_json(image_base64, idx, total_pages, filename)
            pages_data.append(page_json)
            
            # Small delay to avoid rate limits
            time.sleep(0.5)
        
        # Create summary
        logger.info("Creating document summary...")
        doc_summary = create_document_summary(pages_data, filename)
        
        # Combine everything
        result = {
            "filename": filename,
            "total_pages": total_pages,
            "pages_processed": len(pages_data),
            "document_summary": doc_summary,
            "pages": pages_data
        }
        
        # Store in database
        logger.info("Saving to database...")
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE document_analysis
            SET individual_analysis = %s
            WHERE id = %s
        """, (json.dumps(result), doc_id))
        conn.commit()
        cur.close()
        conn.close()
        
        logger.info(f"✅ Successfully processed {filename}")
        return result
        
    except Exception as e:
        logger.error(f"Error processing {filename}: {e}")
        import traceback
        traceback.print_exc()
        return None

def should_skip_document(filename, page_count, skip_large=100):
    """
    Determine if a document should be skipped from deep extraction.
    
    Skip rules:
    - Bank statements over 20 pages (never yield useful info)
    - Any document over skip_large pages
    """
    fn_lower = filename.lower()
    
    # Bank statements over 20 pages - skip (too many transaction pages, no useful data)
    if 'bank_statement' in fn_lower and page_count > 20:
        return True, "Bank statement too large (>20 pages) - no useful extraction benefit"
    
    # Generic large document threshold
    if page_count > skip_large:
        return True, f"Document too large (>{skip_large} pages)"
    
    return False, None

def batch_extract_all(loan_id, max_pages_per_doc=50, skip_large=100):
    """Extract deep JSON for all documents missing analysis"""
    
    logger.info(f"\n{'='*60}")
    logger.info(f"BATCH DEEP JSON EXTRACTION - Loan {loan_id}")
    logger.info(f"{'='*60}\n")
    
    # Get documents needing extraction
    docs = execute_query("""
        SELECT id, filename, file_path, page_count
        FROM document_analysis
        WHERE loan_id = %s
        AND status IN ('unique', 'active', 'master')
        AND individual_analysis IS NULL
        ORDER BY page_count ASC
    """, (loan_id,))
    
    if not docs:
        logger.info("All documents already have analysis!")
        return
    
    logger.info(f"Found {len(docs)} documents needing extraction")
    
    # Filter documents using smart skip logic
    to_process = []
    skipped = []
    
    for d in docs:
        skip, reason = should_skip_document(d['filename'], d['page_count'], skip_large)
        if skip:
            skipped.append((d, reason))
        else:
            to_process.append(d)
    
    if skipped:
        logger.warning(f"Skipping {len(skipped)} documents:")
        conn = get_db_connection()
        cur = conn.cursor()
        for doc, reason in skipped:
            logger.warning(f"  ⏭️ {doc['filename']} ({doc['page_count']} pages) - {reason}")
            # Mark as skipped in database with reason
            cur.execute("""
                UPDATE document_analysis
                SET individual_analysis = %s
                WHERE id = %s AND individual_analysis IS NULL
            """, (json.dumps({
                "skipped": True,
                "skip_reason": reason,
                "filename": doc['filename'],
                "page_count": doc['page_count']
            }), doc['id']))
        conn.commit()
        cur.close()
        conn.close()
    
    logger.info(f"\nProcessing {len(to_process)} documents...\n")
    
    success = 0
    failed = 0
    
    for i, doc in enumerate(to_process, 1):
        logger.info(f"\n[{i}/{len(to_process)}] {doc['filename']} ({doc['page_count']} pages)")
        
        result = process_document(
            doc['id'], 
            doc['filename'], 
            doc['file_path'],
            max_pages=max_pages_per_doc
        )
        
        if result:
            success += 1
        else:
            failed += 1
        
        # Delay between documents
        time.sleep(1)
    
    logger.info(f"\n{'='*60}")
    logger.info(f"BATCH EXTRACTION COMPLETE")
    logger.info(f"  Success: {success}")
    logger.info(f"  Failed: {failed}")
    logger.info(f"  Skipped (large): {len(skipped)}")
    logger.info(f"{'='*60}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Batch extract deep JSON for all documents")
    parser.add_argument("loan_id", type=int, help="Loan ID to process")
    parser.add_argument("--max-pages", type=int, default=50, help="Max pages per document")
    parser.add_argument("--skip-large", type=int, default=100, help="Skip documents with more pages")
    args = parser.parse_args()
    
    batch_extract_all(args.loan_id, args.max_pages, args.skip_large)

