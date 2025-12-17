#!/usr/bin/env python3
"""
Batch deep JSON extraction for all evidence documents
Skips documents that already have vlm_analysis or are too large (>100 pages)
"""

import os
import sys
from deep_json_extraction import process_evidence_document
from db import execute_query
from pdf2image import convert_from_path

def get_documents_needing_extraction(loan_id):
    """Get evidence documents that need deep JSON extraction"""
    
    query = """
        SELECT DISTINCT
            ef.file_name,
            da.id,
            da.file_path,
            da.vlm_analysis
        FROM evidence_files ef
        JOIN document_analysis da ON da.filename = ef.file_name AND da.loan_id = ef.loan_id
        WHERE ef.loan_id = %s
        AND ef.file_name LIKE '%%.pdf'
        ORDER BY ef.file_name
    """
    
    docs = execute_query(query, (loan_id,))
    
    docs_to_process = []
    
    for doc in docs:
        # Skip if already has vlm_analysis with pages structure
        if doc['vlm_analysis']:
            try:
                import json
                vlm = json.loads(doc['vlm_analysis']) if isinstance(doc['vlm_analysis'], str) else doc['vlm_analysis']
                if 'pages' in vlm and 'document_summary' in vlm:
                    print(f"✓ Skipping {doc['file_name']} - already has page-wise JSON")
                    continue
            except:
                pass
        
        # Check page count
        try:
            if os.path.exists(doc['file_path']):
                images = convert_from_path(doc['file_path'], dpi=72, first_page=1, last_page=1)
                # Get total page count
                from PyPDF2 import PdfReader
                reader = PdfReader(doc['file_path'])
                page_count = len(reader.pages)
                
                if page_count > 100:
                    print(f"✗ Skipping {doc['file_name']} - too large ({page_count} pages)")
                    continue
                
                print(f"+ Adding {doc['file_name']} - {page_count} pages")
                docs_to_process.append({
                    'file_name': doc['file_name'],
                    'page_count': page_count
                })
        except Exception as e:
            print(f"! Error checking {doc['file_name']}: {e}")
            continue
    
    return docs_to_process

def main():
    loan_id = 1
    
    print(f"\n{'='*80}")
    print(f"BATCH DEEP JSON EXTRACTION - Loan {loan_id}")
    print(f"Using Claude Opus 4.5 for page-wise extraction + document summary")
    print(f"{'='*80}\n")
    
    docs = get_documents_needing_extraction(loan_id)
    
    if not docs:
        print("No documents need extraction!")
        return
    
    print(f"\n📊 Found {len(docs)} documents to process")
    total_pages = sum(d['page_count'] for d in docs)
    print(f"📄 Total pages: {total_pages}")
    print(f"⏱️  Estimated time: {total_pages * 0.5:.1f} minutes (30 sec/page avg)\n")
    
    # Process each document
    for idx, doc in enumerate(docs, 1):
        print(f"\n{'='*80}")
        print(f"Processing {idx}/{len(docs)}: {doc['file_name']}")
        print(f"Pages: {doc['page_count']}")
        print(f"{'='*80}\n")
        
        try:
            result = process_evidence_document(doc['file_name'], loan_id)
            
            if result:
                print(f"\n✅ SUCCESS: {doc['file_name']}")
                print(f"   - {len(result['pages'])} pages extracted")
                print(f"   - Document summary created")
                print(f"   - Stored in database\n")
            else:
                print(f"\n❌ FAILED: {doc['file_name']}\n")
                
        except Exception as e:
            print(f"\n❌ ERROR processing {doc['file_name']}: {e}\n")
            continue
    
    print(f"\n{'='*80}")
    print(f"BATCH PROCESSING COMPLETE")
    print(f"{'='*80}\n")
    print(f"Processed {len(docs)} documents")
    print(f"Total pages: {total_pages}")
    print(f"\nYou can now view the page-wise JSON in the frontend!")
    print(f"Open any document and click the 'Extracted JSON' tab.\n")

if __name__ == "__main__":
    main()

