"""
Document deduplication utilities for MODDA
Adapted from mt360-viewer analytics dashboard
"""

import hashlib
import PyPDF2
from pathlib import Path
from collections import defaultdict


def extract_text_from_pdf(pdf_path):
    """Extract text from PDF using PyPDF2"""
    try:
        text_parts = []
        page_count = 0
        
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            page_count = len(reader.pages)
            
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)
        
        full_text = '\n'.join(text_parts)
        return full_text, page_count
        
    except Exception as e:
        print(f"Error extracting text from {pdf_path}: {e}")
        return None, 0


def compute_text_hash(text):
    """Compute SHA256 hash of text"""
    if not text:
        return None
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def deduplicate_documents(document_location):
    """
    Scan a directory and identify duplicate documents based on text content hash.
    
    Returns:
        dict with keys:
            - raw: list of all documents
            - unique: list of unique documents (masters + singles)
            - duplicates: list of duplicate documents
            - hash_groups: dict mapping hash to list of documents
    """
    if not document_location or not Path(document_location).exists():
        return {
            'raw': [],
            'unique': [],
            'duplicates': [],
            'hash_groups': {}
        }
    
    doc_path = Path(document_location)
    pdf_files = list(doc_path.glob('*.pdf'))
    
    # Track documents by hash
    hash_to_docs = defaultdict(list)
    all_docs = []
    
    # Process each PDF
    for pdf_path in pdf_files:
        try:
            # Extract text
            text, page_count = extract_text_from_pdf(pdf_path)
            
            # Check if text is sufficient for deduplication
            if text and len(text.strip()) > 50:
                text_hash = compute_text_hash(text)
                is_scanned = False
            else:
                # Text is missing or too short (scanned document or image)
                # Treat as unique, do not group by hash
                text_hash = None
                is_scanned = True
            
            file_stats = pdf_path.stat()
            
            doc_info = {
                'name': pdf_path.name,
                'path': str(pdf_path),
                'type': 'PDF',
                'size': file_stats.st_size,
                'pages': page_count,
                'upload_date': file_stats.st_mtime,
                'hash': text_hash,
                'status': 'processed'
            }
            
            all_docs.append(doc_info)
            
            if is_scanned:
                # Scanned docs are always unique as we can't compare text
                # We could compare file content hash (MD5) later if needed
                doc_info['status'] = 'unique_scanned'
                # Do not add to hash_to_docs
            else:
                hash_to_docs[text_hash].append(doc_info)
            
        except Exception as e:
            print(f"Error processing {pdf_path.name}: {e}")
            # Still include the file but mark as error
            try:
                file_stats = pdf_path.stat()
                doc_info = {
                    'name': pdf_path.name,
                    'path': str(pdf_path),
                    'type': 'PDF',
                    'size': file_stats.st_size,
                    'pages': 0,
                    'upload_date': file_stats.st_mtime,
                    'hash': None,
                    'status': 'error'
                }
                all_docs.append(doc_info)
            except:
                pass

    # Categorize documents
    unique_docs = []
    duplicate_docs = []
    
    # First, add all scanned docs as unique
    for doc in all_docs:
        if doc.get('status') == 'unique_scanned':
             doc['status'] = 'unique' # Normalized status for DB
             doc['duplicate_count'] = 0
             unique_docs.append(doc)
    
    for text_hash, docs in hash_to_docs.items():
        if len(docs) == 1:
            # Unique document
            doc = docs[0]
            doc['status'] = 'unique'
            doc['duplicate_count'] = 0
            unique_docs.append(doc)
        else:
            # Duplicates found - first is master, rest are duplicates
            master = docs[0].copy()
            master['status'] = 'master'
            master['duplicate_count'] = len(docs) - 1
            master['duplicates'] = [d['name'] for d in docs[1:]]
            unique_docs.append(master)
            
            for dup in docs[1:]:
                dup_copy = dup.copy()
                dup_copy['status'] = 'duplicate'
                dup_copy['master'] = master['name']
                duplicate_docs.append(dup_copy)
    
    return {
        'raw': all_docs,
        'unique': unique_docs,
        'duplicates': duplicate_docs,
        'hash_groups': dict(hash_to_docs),
        'stats': {
            'total': len(all_docs),
            'unique': len(unique_docs),
            'duplicates': len(duplicate_docs)
        }
    }
