#!/usr/bin/env python3
"""
Stage 1 - Step 3 Substep 1: Identify Duplicate Documents
Detect duplicate documents using multiple detection methods

Detection Levels:
1. Exact duplicates: Same file hash (MD5)
2. Metadata duplicates: Same page count + file size
3. Content duplicates: Similar extracted JSON content
4. Visual duplicates: Same document type with similar structure

Naming: 1_3_1 = Stage 1, Step 3, Substep 1
"""

import os
import sys
import json
import hashlib
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Tuple


def calculate_file_hash(file_path: Path, algorithm='md5') -> str:
    """Calculate hash of file content"""
    hash_func = hashlib.md5() if algorithm == 'md5' else hashlib.sha256()
    
    with open(file_path, 'rb') as f:
        # Read in chunks for large files
        for chunk in iter(lambda: f.read(8192), b''):
            hash_func.update(chunk)
    
    return hash_func.hexdigest()


def calculate_text_hash(text: str) -> str:
    """Calculate hash of text content (for content comparison)"""
    return hashlib.md5(text.encode('utf-8')).hexdigest()


def get_file_metadata(file_path: Path) -> Dict:
    """Get file metadata"""
    stat = file_path.stat()
    return {
        'size_bytes': stat.st_size,
        'size_kb': round(stat.st_size / 1024, 2),
        'modified_time': datetime.fromtimestamp(stat.st_mtime).isoformat()
    }


def extract_json_signature(json_data: Dict) -> Dict:
    """Extract key signature from JSON for comparison"""
    signature = {
        'page_count': len(json_data.get('pages', [])),
        'has_document_summary': 'document_summary' in json_data,
        'model': json_data.get('model', 'unknown')
    }
    
    # Extract key fields from document summary if present
    if 'document_summary' in json_data:
        doc_summary = json_data['document_summary']
        if 'document_overview' in doc_summary:
            overview = doc_summary['document_overview']
            signature['doc_type'] = overview.get('document_type', 'unknown')
            signature['total_pages'] = overview.get('total_pages')
    
    return signature


def normalize_key(key: str) -> str:
    """Normalize field names for comparison (lowercase, remove special chars)"""
    return key.lower().replace(' ', '_').replace('#', 'number').replace('-', '_')


def calculate_similarity(content1: str, content2: str) -> float:
    """Calculate Jaccard similarity between two content strings
    
    Returns similarity score between 0.0 and 1.0
    """
    if not content1 or not content2:
        return 0.0
    
    # Split into key-value pairs
    pairs1 = set(content1.split('||'))
    pairs2 = set(content2.split('||'))
    
    if not pairs1 or not pairs2:
        return 0.0
    
    # Calculate Jaccard similarity
    intersection = len(pairs1.intersection(pairs2))
    union = len(pairs1.union(pairs2))
    
    return intersection / union if union > 0 else 0.0


def extract_content_fingerprint(json_data: Dict) -> Tuple[str, str]:
    """Extract content fingerprint from JSON for deep comparison
    
    This creates a hash of key extracted data to detect content duplicates
    even when PDFs have different encodings/compression
    
    Normalizes field names to handle variations like 'Date' vs 'date' vs 'Loan #' vs 'loan_number'
    
    Returns: (hash, raw_content_string) tuple
    """
    fingerprint_data = []
    
    # Get key data from each page
    for page in json_data.get('pages', []):
        # Extract key_data if present
        key_data = page.get('key_data', {})
        if key_data:
            # Normalize keys and sort for consistent ordering
            normalized_items = [(normalize_key(k), str(v)) for k, v in key_data.items() if v is not None]
            sorted_items = sorted(normalized_items)
            fingerprint_data.extend([f"{k}:{v}" for k, v in sorted_items])
        
        # Extract financial_data if present
        financial_data = page.get('financial_data', {})
        if financial_data:
            normalized_items = [(normalize_key(k), str(v)) for k, v in financial_data.items() if v is not None]
            sorted_items = sorted(normalized_items)
            fingerprint_data.extend([f"{k}:{v}" for k, v in sorted_items])
    
    # Return both hash and raw content for similarity comparison
    if fingerprint_data:
        content_str = '||'.join(fingerprint_data)
        return calculate_text_hash(content_str), content_str
    
    return None, None


def detect_duplicates(loan_id: str, stage1_output_dir: Path, documents_dir: Path):
    """Detect duplicate documents using multiple methods"""
    
    print("\n" + "="*80)
    print(f"🔍 STAGE 1 STEP 3.1: Identify Duplicates - {loan_id}")
    print("="*80)
    
    # Load analysis data
    analysis_file = stage1_output_dir / "1_1_1_analysis.json"
    if not analysis_file.exists():
        print(f"❌ Error: Analysis file not found: {analysis_file}")
        return None
    
    with open(analysis_file, 'r') as f:
        analysis = json.load(f)
    
    print(f"\n📄 Analyzing {len(analysis['details'])} documents...\n")
    
    # Data structures for duplicate detection
    hash_groups = defaultdict(list)  # file_hash -> [files]
    metadata_groups = defaultdict(list)  # (page_count, size_kb) -> [files]
    content_signatures = {}  # filename -> signature
    content_fingerprints = defaultdict(list)  # content_hash -> [files]
    
    # Process each file
    processed = 0
    for detail in analysis['details']:
        filename = detail['filename']
        pdf_path = documents_dir / filename
        
        if not pdf_path.exists():
            print(f"  ⚠️  Skipping missing file: {filename}")
            continue
        
        processed += 1
        if processed % 10 == 0:
            print(f"  Processed {processed}/{len(analysis['details'])} files...")
        
        # Level 1: Calculate file hash (exact duplicates)
        file_hash = calculate_file_hash(pdf_path)
        
        # Level 2: Get metadata
        metadata = get_file_metadata(pdf_path)
        metadata_key = (detail['page_count'], metadata['size_kb'])
        
        # Level 3: Get JSON signature and content fingerprint if available
        json_signature = None
        content_fingerprint = None
        content_string = None
        for extraction_folder in ['1_2_1_llama_extractions', '1_2_3_llama_extractions', 
                                   '1_2_4_llama_extractions', '1_2_5_llama_extractions']:
            json_file = stage1_output_dir / extraction_folder / f"{Path(filename).stem}.json"
            if json_file.exists():
                with open(json_file, 'r') as f:
                    json_data = json.load(f)
                    json_signature = extract_json_signature(json_data)
                    content_fingerprint, content_string = extract_content_fingerprint(json_data)
                break
        
        # Store information
        file_info = {
            'filename': filename,
            'file_hash': file_hash,
            'page_count': detail['page_count'],
            'pdf_type': detail['pdf_type'],
            'size_bytes': metadata['size_bytes'],
            'size_kb': metadata['size_kb'],
            'json_signature': json_signature,
            'content_fingerprint': content_fingerprint,
            'content_string': content_string,
            'has_extraction': json_signature is not None
        }
        
        hash_groups[file_hash].append(file_info)
        metadata_groups[metadata_key].append(file_info)
        content_signatures[filename] = file_info
        
        # Group by content fingerprint
        if content_fingerprint:
            content_fingerprints[content_fingerprint].append(file_info)
    
    print(f"\n✅ Processed {processed} files\n")
    
    # Analyze duplicates
    print("="*80)
    print("🔍 DUPLICATE ANALYSIS")
    print("="*80)
    
    # Level 1: Exact duplicates (same file hash)
    exact_duplicates = {
        hash_val: files 
        for hash_val, files in hash_groups.items() 
        if len(files) > 1
    }
    
    print(f"\n1️⃣  EXACT DUPLICATES (Same file hash - byte-by-byte identical):")
    if exact_duplicates:
        print(f"   Found {len(exact_duplicates)} groups with exact duplicates")
        for idx, (hash_val, files) in enumerate(exact_duplicates.items(), 1):
            print(f"\n   Group {idx} (Hash: {hash_val[:8]}...):")
            for f in files:
                print(f"      - {f['filename']} ({f['page_count']} pages, {f['size_kb']} KB)")
    else:
        print("   ✅ No exact duplicates found")
    
    # Level 1.5: Content duplicates (same extracted content, different encoding)
    content_duplicates = {
        content_hash: files 
        for content_hash, files in content_fingerprints.items() 
        if len(files) > 1
    }
    
    print(f"\n1.5️⃣ CONTENT DUPLICATES (Same extracted data, different PDF encoding):")
    if content_duplicates:
        print(f"   Found {len(content_duplicates)} groups with content duplicates")
        for idx, (content_hash, files) in enumerate(content_duplicates.items(), 1):
            print(f"\n   Group {idx} (Content Hash: {content_hash[:8]}...):")
            for f in files:
                print(f"      - {f['filename']} ({f['page_count']} pages, {f['size_kb']} KB, File Hash: {f['file_hash'][:8]}...)")
    else:
        print("   ✅ No content duplicates found")
    
    # Level 2: Metadata duplicates (same page count + size, but different content)
    metadata_duplicates = {}
    for metadata_key, files in metadata_groups.items():
        if len(files) > 1:
            # Group by hash to separate exact from metadata duplicates
            hash_subgroups = defaultdict(list)
            for f in files:
                hash_subgroups[f['file_hash']].append(f)
            
            # If all have same hash, it's already counted as exact duplicate
            if len(hash_subgroups) > 1:
                metadata_duplicates[metadata_key] = files
    
    print(f"\n2️⃣  METADATA DUPLICATES (Same page count + size, different content):")
    if metadata_duplicates:
        print(f"   Found {len(metadata_duplicates)} groups with metadata duplicates")
        for idx, (metadata_key, files) in enumerate(metadata_duplicates.items(), 1):
            page_count, size_kb = metadata_key
            print(f"\n   Group {idx} ({page_count} pages, {size_kb} KB):")
            for f in files:
                print(f"      - {f['filename']} (Hash: {f['file_hash'][:8]}...)")
    else:
        print("   ✅ No metadata duplicates found")
    
    # Level 3: Semantic duplicates (similar document types/structure)
    semantic_groups = defaultdict(list)
    for filename, info in content_signatures.items():
        if info['json_signature']:
            sig = info['json_signature']
            # Group by document type and page count
            key = (sig.get('doc_type', 'unknown'), sig.get('total_pages'))
            semantic_groups[key].append(info)
    
    semantic_duplicates = {
        key: files 
        for key, files in semantic_groups.items() 
        if len(files) > 1 and key[0] != 'unknown'
    }
    
    print(f"\n3️⃣  SEMANTIC DUPLICATES (Same document type + page count):")
    if semantic_duplicates:
        print(f"   Found {len(semantic_duplicates)} groups with semantic duplicates")
        for idx, ((doc_type, total_pages), files) in enumerate(semantic_duplicates.items(), 1):
            print(f"\n   Group {idx} (Type: {doc_type}, Pages: {total_pages}):")
            for f in files:
                print(f"      - {f['filename']} (Hash: {f['file_hash'][:8]}...)")
    else:
        print("   ✅ No semantic duplicates found")
    
    # Level 4: Similar documents (high similarity score but not identical)
    print(f"\n4️⃣  SIMILAR DOCUMENTS (40%+ content similarity):")
    similar_groups = []
    similarity_threshold = 0.40  # 40% similarity
    high_similarity_threshold = 0.80  # 80% for "high similarity"
    
    # Compare documents within same semantic groups
    for (doc_type, total_pages), files in semantic_duplicates.items():
        # Only compare files with extracted content
        files_with_content = [f for f in files if f.get('content_string')]
        
        if len(files_with_content) < 2:
            continue
        
        # Compare each pair
        compared_pairs = set()
        for i, file1 in enumerate(files_with_content):
            for file2 in files_with_content[i+1:]:
                pair_key = tuple(sorted([file1['filename'], file2['filename']]))
                if pair_key in compared_pairs:
                    continue
                compared_pairs.add(pair_key)
                
                # Skip if already exact or content duplicates
                if file1['file_hash'] == file2['file_hash']:
                    continue
                if file1['content_fingerprint'] == file2['content_fingerprint']:
                    continue
                
                # Calculate similarity
                similarity = calculate_similarity(file1['content_string'], file2['content_string'])
                
                if similarity >= similarity_threshold:
                    # Categorize by similarity level
                    if similarity >= high_similarity_threshold:
                        similarity_level = 'HIGH'
                    elif similarity >= 0.60:
                        similarity_level = 'MEDIUM'
                    else:
                        similarity_level = 'LOW'
                    
                    similar_groups.append({
                        'file1': file1['filename'],
                        'file2': file2['filename'],
                        'similarity': round(similarity * 100, 1),
                        'similarity_level': similarity_level,
                        'doc_type': doc_type,
                        'file1_hash': file1['file_hash'][:8],
                        'file2_hash': file2['file_hash'][:8]
                    })
    
    if similar_groups:
        print(f"   Found {len(similar_groups)} similar document pairs")
        
        # Group by similarity level
        high_sim = [p for p in similar_groups if p['similarity_level'] == 'HIGH']
        medium_sim = [p for p in similar_groups if p['similarity_level'] == 'MEDIUM']
        low_sim = [p for p in similar_groups if p['similarity_level'] == 'LOW']
        
        if high_sim:
            print(f"\n   🔴 HIGH Similarity (80%+): {len(high_sim)} pairs")
            for pair in high_sim:
                print(f"      {pair['similarity']}% - {pair['file1']} ↔ {pair['file2']}")
        
        if medium_sim:
            print(f"\n   🟡 MEDIUM Similarity (60-80%): {len(medium_sim)} pairs")
            for pair in medium_sim:
                print(f"      {pair['similarity']}% - {pair['file1']} ↔ {pair['file2']}")
        
        if low_sim:
            print(f"\n   🟢 LOW Similarity (40-60%): {len(low_sim)} pairs")
            for pair in low_sim:
                print(f"      {pair['similarity']}% - {pair['file1']} ↔ {pair['file2']}")
    else:
        print("   ✅ No similar documents found (below 40% threshold)")
    
    # Create detailed duplicate report
    duplicate_report = {
        'loan_id': loan_id,
        'analysis_timestamp': datetime.now().isoformat(),
        'total_files_analyzed': processed,
        'similarity_threshold': similarity_threshold,
        'summary': {
            'exact_duplicate_groups': len(exact_duplicates),
            'exact_duplicate_files': sum(len(files) for files in exact_duplicates.values()),
            'content_duplicate_groups': len(content_duplicates),
            'content_duplicate_files': sum(len(files) for files in content_duplicates.values()),
            'metadata_duplicate_groups': len(metadata_duplicates),
            'metadata_duplicate_files': sum(len(files) for files in metadata_duplicates.values()),
            'semantic_duplicate_groups': len(semantic_duplicates),
            'semantic_duplicate_files': sum(len(files) for files in semantic_duplicates.values()),
            'similar_document_pairs': len(similar_groups)
        },
        'exact_duplicates': [
            {
                'group_id': idx,
                'file_hash': hash_val,
                'file_count': len(files),
                'files': files
            }
            for idx, (hash_val, files) in enumerate(exact_duplicates.items(), 1)
        ],
        'content_duplicates': [
            {
                'group_id': idx,
                'content_fingerprint': content_hash,
                'file_count': len(files),
                'files': files
            }
            for idx, (content_hash, files) in enumerate(content_duplicates.items(), 1)
        ],
        'metadata_duplicates': [
            {
                'group_id': idx,
                'page_count': metadata_key[0],
                'size_kb': metadata_key[1],
                'file_count': len(files),
                'files': files
            }
            for idx, (metadata_key, files) in enumerate(metadata_duplicates.items(), 1)
        ],
        'semantic_duplicates': [
            {
                'group_id': idx,
                'document_type': key[0],
                'page_count': key[1],
                'file_count': len(files),
                'files': files
            }
            for idx, (key, files) in enumerate(semantic_duplicates.items(), 1)
        ],
        'similar_documents': similar_groups,
        'recommendations': []
    }
    
    # Add recommendations
    if exact_duplicates:
        duplicate_report['recommendations'].append({
            'level': 'HIGH',
            'type': 'exact_duplicates',
            'message': f"Found {len(exact_duplicates)} exact duplicate groups (byte-by-byte identical). Consider keeping only one copy from each group.",
            'action': 'Review exact_duplicates section and decide which files to keep'
        })
    
    if content_duplicates:
        duplicate_report['recommendations'].append({
            'level': 'HIGH',
            'type': 'content_duplicates',
            'message': f"Found {len(content_duplicates)} content duplicate groups (same data, different PDF encoding). These have identical extracted content despite different file sizes.",
            'action': 'Review content_duplicates section - these are likely re-saved/re-scanned versions of same document'
        })
    
    if metadata_duplicates:
        duplicate_report['recommendations'].append({
            'level': 'MEDIUM',
            'type': 'metadata_duplicates',
            'message': f"Found {len(metadata_duplicates)} metadata duplicate groups. These files have same size/pages but different content. Review for near-duplicates.",
            'action': 'Manual review recommended to check if these are different versions of same document'
        })
    
    if semantic_duplicates:
        duplicate_report['recommendations'].append({
            'level': 'LOW',
            'type': 'semantic_duplicates',
            'message': f"Found {len(semantic_duplicates)} semantic duplicate groups. These are same document types with same page counts but may have different content.",
            'action': 'Review if multiple versions/copies are expected for this document type'
        })
    
    if similar_groups:
        duplicate_report['recommendations'].append({
            'level': 'MEDIUM',
            'type': 'similar_documents',
            'message': f"Found {len(similar_groups)} document pairs with 40%+ similarity. These may be versions with minor or major changes.",
            'action': 'Review similar_documents section by similarity level - HIGH (80%+) are very similar, MEDIUM (60-80%) have moderate differences, LOW (40-60%) have significant differences but same document type'
        })
    
    # Save report
    script_dir = Path(__file__).parent
    output_file = script_dir / "output" / loan_id / "1_3_1_duplicates.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w') as f:
        json.dump(duplicate_report, f, indent=2)
    
    # Print summary
    print("\n" + "="*80)
    print("📊 SUMMARY")
    print("="*80)
    print(f"  Total files analyzed: {processed}")
    print(f"  Exact duplicate groups: {len(exact_duplicates)}")
    print(f"  Content duplicate groups: {len(content_duplicates)}")
    print(f"  Metadata duplicate groups: {len(metadata_duplicates)}")
    print(f"  Semantic duplicate groups: {len(semantic_duplicates)}")
    print(f"  Similar document pairs (40%+): {len(similar_groups)}")
    if similar_groups:
        high_sim = sum(1 for p in similar_groups if p['similarity_level'] == 'HIGH')
        medium_sim = sum(1 for p in similar_groups if p['similarity_level'] == 'MEDIUM')
        low_sim = sum(1 for p in similar_groups if p['similarity_level'] == 'LOW')
        print(f"    - HIGH (80%+): {high_sim}")
        print(f"    - MEDIUM (60-80%): {medium_sim}")
        print(f"    - LOW (40-60%): {low_sim}")
    print(f"\n  💾 Report saved: {output_file.name}")
    print("="*80 + "\n")
    
    return duplicate_report


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python 1_3_1_identify_duplicates.py <loan_id>")
        print("\nExample:")
        print("  python 1_3_1_identify_duplicates.py loan_1642451")
        print("\nPrerequisites:")
        print("  1. Stage 1 Step 1 must be complete (1_1_1_analysis.json must exist)")
        print("  2. Documents must be in /path/to/documents/<loan_id>/")
        print("\nOutput:")
        print("  Report file: backend/stage1/output/<loan_id>/1_3_1_duplicates.json")
        sys.exit(1)
    
    loan_id = sys.argv[1]
    
    # Setup paths
    script_dir = Path(__file__).parent
    stage1_output_dir = script_dir / "output" / loan_id
    documents_dir = script_dir.parent.parent / "documents" / loan_id
    
    # Verify prerequisites
    if not stage1_output_dir.exists():
        print(f"❌ Error: Stage 1 output not found for {loan_id}")
        sys.exit(1)
    
    if not documents_dir.exists():
        print(f"❌ Error: Documents folder not found: {documents_dir}")
        sys.exit(1)
    
    # Run duplicate detection
    report = detect_duplicates(loan_id, stage1_output_dir, documents_dir)
    
    if report:
        total_dup_files = (
            report['summary']['exact_duplicate_files'] +
            report['summary']['content_duplicate_files'] +
            report['summary']['metadata_duplicate_files'] +
            report['summary']['semantic_duplicate_files']
        )
        if total_dup_files > 0:
            print("⚠️  Duplicates found! Review the report for details.")
        else:
            print("✅ No duplicates found!")
        sys.exit(0)
    else:
        print("❌ Duplicate detection failed")
        sys.exit(1)

