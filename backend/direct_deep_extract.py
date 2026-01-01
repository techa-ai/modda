#!/usr/bin/env python3
"""
Direct Deep Extraction Pipeline (No Dedup)

Simplified pipeline that:
1. Scans folder for all PDFs
2. Creates document_analysis records (all as 'unique')
3. Runs Opus page-wise deep extraction
4. Duplicates/versions are identified AFTER from the JSON data

Usage:
    python direct_deep_extract.py <loan_id> [--concurrency 10] [--limit 10] [--small-first]
"""

import os
import sys
import json
import argparse
import time
import re
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

# Add backend to path
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND_DIR)

from db import execute_query, execute_one, get_db_connection
from vlm_utils import VLMClient

# Thread-safe stats
stats_lock = Lock()


def get_loan_info(loan_id):
    """Get loan info from database"""
    return execute_one(
        "SELECT id, loan_number, document_location FROM loans WHERE id = %s",
        (loan_id,)
    )


def scan_and_insert_documents(loan_id, doc_location):
    """Scan folder and insert all PDFs into document_analysis (no dedup)"""
    print(f"\n📂 Scanning: {doc_location}")
    
    doc_path = Path(doc_location)
    if not doc_path.exists():
        print(f"❌ Folder not found: {doc_location}")
        return []
    
    pdf_files = sorted(doc_path.glob('*.pdf'))
    print(f"   Found {len(pdf_files)} PDF files")
    
    # Get existing documents
    existing = execute_query(
        "SELECT filename, individual_analysis FROM document_analysis WHERE loan_id = %s",
        (loan_id,)
    )
    existing_docs = {row['filename']: row for row in (existing or [])}
    
    inserted = 0
    skipped = 0
    documents = []
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    for pdf_path in pdf_files:
        filename = pdf_path.name
        
        if filename in existing_docs:
            skipped += 1
            # Still add to documents list for processing
            doc = existing_docs[filename]
            documents.append({
                'id': None,  # We'll get it if needed
                'filename': filename,
                'file_path': str(pdf_path),
                'page_count': None,
                'individual_analysis': doc.get('individual_analysis')
            })
            continue
        
        # Get file info
        try:
            file_stats = pdf_path.stat()
            
            # Get page count
            from PyPDF2 import PdfReader
            reader = PdfReader(str(pdf_path))
            page_count = len(reader.pages)
            
            # Insert into document_analysis
            cur.execute("""
                INSERT INTO document_analysis 
                    (loan_id, filename, file_path, file_size, page_count, status, created_at)
                VALUES (%s, %s, %s, %s, %s, 'unique', NOW())
                RETURNING id
            """, (
                loan_id,
                filename,
                str(pdf_path),
                file_stats.st_size,
                page_count
            ))
            result = cur.fetchone()
            doc_id = result['id'] if isinstance(result, dict) else result[0]
            conn.commit()
            
            documents.append({
                'id': doc_id,
                'filename': filename,
                'file_path': str(pdf_path),
                'page_count': page_count,
                'individual_analysis': None
            })
            inserted += 1
            
        except Exception as e:
            import traceback
            print(f"   ⚠️ Error with {filename}: {str(e)[:100]}")
            traceback.print_exc()
            continue
    
    cur.close()
    conn.close()
    
    print(f"   ✅ Inserted: {inserted}, Skipped (existing): {skipped}")
    print(f"   📄 Total documents to process: {len(documents)}")
    
    return documents


def needs_extraction(doc):
    """Check if document needs deep extraction"""
    if not doc.get('individual_analysis'):
        return True
    
    analysis = doc['individual_analysis']
    if isinstance(analysis, str):
        try:
            analysis = json.loads(analysis)
        except:
            return True
    
    # Check for valid page-wise structure
    if 'pages' not in analysis or 'document_summary' not in analysis:
        return True
    
    if not analysis['pages'] or len(analysis['pages']) == 0:
        return True
    
    return False


def create_extraction_prompt(filename, page_num, total_pages):
    """Create the page-wise extraction prompt"""
    return f"""Analyze this page ({page_num}/{total_pages}) of the document '{filename}'.

Extract ALL relevant information into structured JSON. This includes:
- Document type and purpose
- Key dates (document date, signature dates, effective dates)
- Names (borrowers, lenders, parties)
- Financial amounts (loan amounts, payments, fees, values)
- Account/reference numbers
- Addresses
- Important terms and conditions
- Any other significant data

Format your response as valid JSON with these keys:
{{
  "page_number": {page_num},
  "document_type": "<type of document/section>",
  "key_data": {{
    // Field-value pairs of important data extracted
  }},
  "dates": [
    {{"type": "<date type>", "value": "<YYYY-MM-DD or as shown>"}}
  ],
  "amounts": [
    {{"type": "<amount type>", "value": <numeric value>, "formatted": "<as shown>"}}
  ],
  "names": [
    {{"role": "<role>", "name": "<full name>"}}
  ],
  "addresses": [
    {{"type": "<address type>", "value": "<full address>"}}
  ],
  "reference_numbers": [
    {{"type": "<type>", "value": "<number>"}}
  ],
  "summary": "<2-3 sentence summary of what this page contains>"
}}

IMPORTANT: 
- Extract EXACT values as they appear (don't interpret or calculate)
- Use null for missing/unclear values
- Include page_number in response
- Return ONLY valid JSON, no other text"""


def create_summary_prompt(filename, pages_data):
    """Create the document-level summary prompt"""
    return f"""You have analyzed {len(pages_data)} pages of '{filename}'.
    
Based on the page-by-page extractions below, create a comprehensive document summary.

PAGE DATA:
{json.dumps(pages_data, indent=2)[:20000]}

Create a document-level summary with this structure:
{{
  "document_type": "<primary document type>",
  "document_subtype": "<more specific type if applicable>",
  "document_date": "<YYYY-MM-DD if found>",
  "purpose": "<what this document is for>",
  "key_entities": {{
    "people": [
      {{"name": "<name>", "role": "<role>"}}
    ],
    "organizations": [
      {{"name": "<name>", "type": "<type>"}}
    ],
    "addresses": [
      {{"type": "<address type>", "street": "<street>", "city": "<city>", "state": "<state>", "zip": "<zip>"}}
    ],
    "account_numbers": [
      {{"type": "<type>", "value": "<number>"}}
    ]
  }},
  "critical_values": {{
    // Most important financial and data values from this document
  }},
  "summary": "<2-3 paragraph executive summary of document contents and significance>"
}}

IMPORTANT: Consolidate and deduplicate data across pages.
Return ONLY valid JSON."""


def extract_json_from_response(text):
    """Extract JSON from VLM response, handling markdown code blocks"""
    text = text.strip()
    
    # Remove markdown code blocks
    if text.startswith('```'):
        text = re.sub(r'^```(?:json)?\s*\n', '', text)
        text = re.sub(r'\n```\s*$', '', text)
    
    # Find JSON object
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            return json.loads(match.group())
        except:
            pass
    
    # Try direct parse
    try:
        return json.loads(text)
    except:
        return None


def process_single_document(doc, loan_id, stats):
    """Process a single document with page-wise deep extraction using Opus"""
    filename = doc['filename']
    file_path = doc['file_path']
    
    try:
        # Get page count
        from PyPDF2 import PdfReader
        from pdf2image import convert_from_path
        import base64
        import io
        
        reader = PdfReader(file_path)
        page_count = len(reader.pages)
        
        # Skip very large documents
        if page_count > 80:
            with stats_lock:
                stats['skipped'] += 1
            return {'success': False, 'filename': filename, 'error': f'Too large ({page_count} pages)'}
        
        # Initialize VLM client
        client = VLMClient(model='claude-opus-4-5', max_tokens=8000)
        
        # Convert PDF to images
        try:
            images = convert_from_path(file_path, dpi=150)
        except Exception as e:
            with stats_lock:
                stats['failed'] += 1
            return {'success': False, 'filename': filename, 'error': f'PDF conversion failed: {e}'}
        
        # Process each page
        pages_data = []
        for page_idx, image in enumerate(images, 1):
            # Convert to base64
            buffer = io.BytesIO()
            image.save(buffer, format='JPEG', quality=85)
            img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
            
            # Create prompt and call VLM
            prompt = create_extraction_prompt(filename, page_idx, page_count)
            
            try:
                result = client.process_images([img_base64], prompt, return_json=True)
                if isinstance(result, dict):
                    pages_data.append(result)
                elif isinstance(result, str):
                    parsed = extract_json_from_response(result)
                    if parsed:
                        pages_data.append(parsed)
                    else:
                        pages_data.append({"page_number": page_idx, "raw_text": result[:500], "parse_error": True})
            except Exception as e:
                pages_data.append({"page_number": page_idx, "error": str(e)[:200]})
        
        # Generate document summary
        summary_prompt = create_summary_prompt(filename, pages_data)
        try:
            summary_result = client.process_text(
                json.dumps(pages_data)[:30000], 
                summary_prompt, 
                return_json=True
            )
            if isinstance(summary_result, str):
                summary_result = extract_json_from_response(summary_result)
        except Exception as e:
            summary_result = {"error": str(e), "summary": "Failed to generate summary"}
        
        # Build final analysis
        analysis = {
            "filename": filename,
            "total_pages": page_count,
            "processing_date": datetime.now().isoformat(),
            "model": "claude-opus-4-5",
            "pages": pages_data,
            "document_summary": summary_result
        }
        
        # Save to database
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE document_analysis 
            SET individual_analysis = %s 
            WHERE loan_id = %s AND filename = %s
        """, (json.dumps(analysis), loan_id, filename))
        conn.commit()
        cur.close()
        conn.close()
        
        with stats_lock:
            stats['success'] += 1
        
        return {'success': True, 'filename': filename, 'pages': page_count}
        
    except Exception as e:
        with stats_lock:
            stats['failed'] += 1
        return {'success': False, 'filename': filename, 'error': str(e)[:200]}


def run_deep_extraction(loan_id, documents, concurrency=10, limit=None, small_first=False):
    """Run deep extraction on all documents"""
    
    # Filter to documents needing extraction
    docs_to_process = [d for d in documents if needs_extraction(d)]
    
    if not docs_to_process:
        print("\n✅ All documents already have valid deep JSON!")
        return
    
    # Get page counts for documents that don't have it yet
    for doc in docs_to_process:
        if doc.get('page_count') is None:
            try:
                from PyPDF2 import PdfReader
                reader = PdfReader(doc['file_path'])
                doc['page_count'] = len(reader.pages)
            except:
                doc['page_count'] = 0
    
    # Sort by page count if small_first
    if small_first:
        docs_to_process.sort(key=lambda x: x.get('page_count', 0))
        print("\n📊 Processing smallest documents first")
    
    # Apply limit
    if limit:
        docs_to_process = docs_to_process[:limit]
    
    total_pages = sum(d.get('page_count', 0) for d in docs_to_process)
    
    print(f"\n{'='*70}")
    print(f"🚀 DEEP EXTRACTION - Loan {loan_id}")
    print(f"{'='*70}")
    print(f"   Documents to process: {len(docs_to_process)}")
    print(f"   Total pages: {total_pages}")
    print(f"   Concurrency: {concurrency}")
    print(f"   Estimated time: {total_pages * 0.5:.0f} - {total_pages * 1:.0f} minutes")
    print(f"{'='*70}\n")
    
    stats = {'success': 0, 'failed': 0, 'skipped': 0}
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {
            executor.submit(process_single_document, doc, loan_id, stats): doc 
            for doc in docs_to_process
        }
        
        for i, future in enumerate(as_completed(futures), 1):
            doc = futures[future]
            try:
                result = future.result()
                status = "✅" if result.get('success') else "❌"
                pages = result.get('pages', '?')
                error = result.get('error', '')[:50] if not result.get('success') else ''
                print(f"[{i}/{len(docs_to_process)}] {status} {doc['filename']} ({pages} pages) {error}")
                
            except Exception as e:
                print(f"[{i}/{len(docs_to_process)}] ❌ {doc['filename']}: {e}")
    
    elapsed = time.time() - start_time
    
    print(f"\n{'='*70}")
    print(f"📊 EXTRACTION COMPLETE")
    print(f"{'='*70}")
    print(f"   ✅ Success: {stats['success']}")
    print(f"   ❌ Failed: {stats['failed']}")
    print(f"   ⏭️ Skipped: {stats['skipped']}")
    print(f"   ⏱️ Time: {elapsed/60:.1f} minutes")
    print(f"{'='*70}\n")


def main():
    parser = argparse.ArgumentParser(description="Direct Deep Extraction Pipeline")
    parser.add_argument("loan_id", type=int, help="Loan ID to process")
    parser.add_argument("--concurrency", type=int, default=5, help="Number of concurrent extractions")
    parser.add_argument("--limit", type=int, help="Limit number of documents to process")
    parser.add_argument("--small-first", action="store_true", help="Process smallest documents first")
    
    args = parser.parse_args()
    
    print(f"\n{'='*70}")
    print(f"📦 DIRECT DEEP EXTRACTION PIPELINE")
    print(f"   Loan ID: {args.loan_id}")
    print(f"   Concurrency: {args.concurrency}")
    print(f"   Limit: {args.limit or 'None'}")
    print(f"   Small First: {args.small_first}")
    print(f"{'='*70}")
    
    # Get loan info
    loan = get_loan_info(args.loan_id)
    if not loan:
        print(f"❌ Loan {args.loan_id} not found!")
        return 1
    
    print(f"\n📋 Loan: {loan['loan_number']}")
    print(f"   Location: {loan['document_location']}")
    
    # Step 1: Scan and insert documents
    documents = scan_and_insert_documents(args.loan_id, loan['document_location'])
    
    if not documents:
        print("❌ No documents found!")
        return 1
    
    # Step 2: Run deep extraction
    run_deep_extraction(
        args.loan_id, 
        documents, 
        concurrency=args.concurrency,
        limit=args.limit,
        small_first=args.small_first
    )
    
    # Final stats
    final_stats = execute_one("""
        SELECT 
            COUNT(*) as total,
            COUNT(CASE WHEN individual_analysis->'pages' IS NOT NULL 
                       AND jsonb_array_length(individual_analysis->'pages') > 0 
                       AND individual_analysis->'document_summary' IS NOT NULL 
                  THEN 1 END) as valid_deep_json
        FROM document_analysis 
        WHERE loan_id = %s
    """, (args.loan_id,))
    
    print(f"\n📊 FINAL STATUS:")
    print(f"   Total documents: {final_stats['total']}")
    print(f"   Valid deep JSON: {final_stats['valid_deep_json']}")
    if final_stats['total'] > 0:
        print(f"   Coverage: {100 * final_stats['valid_deep_json'] / final_stats['total']:.1f}%")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
