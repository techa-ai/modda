#!/usr/bin/env python3
"""
Stage 1 - Step 3 Substep 1: Semantic Document Grouping using Llama 4 Maverick
Identify groups of same documents with variations:
- Signed vs Unsigned
- Chronological differences (dates)
- Revised versions
- Incomplete vs Complete
- Preliminary vs Final
- Draft vs Executed

Naming: 1_3_1 = Stage 1, Step 3, Substep 1
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple
from collections import defaultdict

# Import Llama client
sys.path.insert(0, str(Path(__file__).parent))
from llama_pagewise_extractor import LlamaClient


def estimate_tokens(text: str) -> int:
    """Estimate token count (4 chars per token approximation)"""
    return len(text) // 4


def load_extracted_jsons(stage1_output_dir: Path, loan_id: str) -> List[Dict]:
    """Load all extracted JSONs and calculate metadata"""
    
    documents = []
    
    # Load from all extraction folders
    for extraction_folder in ['1_2_1_llama_extractions', '1_2_3_llama_extractions', 
                               '1_2_4_llama_extractions']:
        folder_path = stage1_output_dir / extraction_folder
        if not folder_path.exists():
            continue
        
        for json_file in folder_path.glob('*.json'):
            if json_file.name == 'extraction_summary.json':
                continue
            
            try:
                with open(json_file, 'r') as f:
                    data = json.load(f)
                
                # Get content as string for token estimation
                content_str = json.dumps(data, indent=2)
                tokens = estimate_tokens(content_str)
                
                # Get page count
                page_count = len(data.get('pages', []))
                if page_count == 0:
                    page_count = data.get('total_pages', 1)
                
                # Create document summary
                doc_info = {
                    'filename': data.get('filename', json_file.stem + '.pdf'),
                    'json_file': str(json_file),
                    'content': content_str,
                    'tokens': tokens,
                    'page_count': page_count,
                    'extraction_folder': extraction_folder,
                    'document_summary': data.get('document_summary', {})
                }
                
                documents.append(doc_info)
                
            except Exception as e:
                print(f"  ⚠️  Error loading {json_file.name}: {e}")
                continue
    
    return documents


def filter_and_sort_documents(documents: List[Dict], max_pages: int = 50) -> Tuple[List[Dict], List[Dict]]:
    """Filter out large documents and sort by filename
    
    Exception: Keep large documents if there are 2+ with similar page counts
    """
    
    # Group by page count
    page_count_groups = defaultdict(list)
    for doc in documents:
        page_count_groups[doc['page_count']].append(doc)
    
    included = []
    excluded = []
    
    for doc in documents:
        page_count = doc['page_count']
        
        # Include if under threshold
        if page_count <= max_pages:
            included.append(doc)
        # Include if 2+ documents with same page count (likely versions)
        elif len(page_count_groups[page_count]) >= 2:
            included.append(doc)
            doc['large_but_included'] = True
        else:
            excluded.append(doc)
    
    # Sort by filename
    included.sort(key=lambda x: x['filename'])
    
    return included, excluded


def create_batches(documents: List[Dict], target_tokens: int = 100000) -> List[List[Dict]]:
    """Create batches of documents targeting ~100k tokens each"""
    
    batches = []
    current_batch = []
    current_tokens = 0
    
    for doc in documents:
        doc_tokens = doc['tokens']
        
        # If adding this doc would exceed target, start new batch
        if current_tokens + doc_tokens > target_tokens and current_batch:
            batches.append(current_batch)
            current_batch = []
            current_tokens = 0
        
        current_batch.append(doc)
        current_tokens += doc_tokens
    
    # Add final batch
    if current_batch:
        batches.append(current_batch)
    
    return batches


def create_semantic_grouping_prompt(documents: List[Dict], batch_num: int, total_batches: int) -> str:
    """Create prompt for semantic document grouping"""
    
    # Create document summaries for Llama
    doc_summaries = []
    for idx, doc in enumerate(documents, 1):
        # Extract key information from the document
        content_json = json.loads(doc['content'])
        pages = content_json.get('pages', [])
        first_page = pages[0] if pages else {}
        
        doc_summary_obj = content_json.get('document_summary', {})
        overview = doc_summary_obj.get('document_overview', {})
        
        # Get the ACTUAL document type from the page
        actual_doc_type = first_page.get('document_type_on_page', 'Unknown')
        
        # Get document purpose
        doc_purpose = overview.get('purpose', 'N/A')
        if doc_purpose == 'N/A':
            # Try to get from first section title
            text_content = first_page.get('text_content', {})
            sections = text_content.get('sections', [])
            if sections and len(sections) > 0:
                doc_purpose = sections[0].get('title', 'N/A')
        
        # Check for signature/acknowledgment fields across ALL pages
        has_signature = False
        signature_fields = []
        for page in pages:
            key_data_page = page.get('key_data', {})
            for field in ['signature', 'borrower_signature', 'acknowledgment_date', 'acknowledgment_time', 'lender_signature', 'signed_date', 'notary_signature']:
                if field in key_data_page:
                    has_signature = True
                    signature_fields.append(field)
        
        summary = {
            'index': idx,
            'filename': doc['filename'],
            'pages': doc['page_count'],
            '⚠️_ACTUAL_DOCUMENT_TYPE': actual_doc_type,  # Make this super visible
            'document_purpose': doc_purpose,
            '🖊️_HAS_SIGNATURE': '✅ SIGNED' if has_signature else '❌ UNSIGNED',  # Make signature status super visible
            'signature_fields_found': signature_fields if has_signature else [],
            'dates': [
                overview.get('effective_date'),
                overview.get('ordered_date'),
                overview.get('date'),
                first_page.get('key_data', {}).get('date')
            ]
        }
        summary['dates'] = [d for d in summary['dates'] if d]
        
        # Add key data preview showing what the document is about
        key_data = first_page.get('key_data', {})
        if key_data:
            summary['key_fields'] = {k: v for k, v in list(key_data.items())[:5]}  # First 5 fields
        
        doc_summaries.append(summary)
    
    prompt = f"""You are analyzing a batch of mortgage loan documents (Batch {batch_num}/{total_batches}) to identify which documents are VERSIONS of the SAME DOCUMENT vs which are COMPLETELY DIFFERENT DOCUMENTS.

🚨 CRITICAL RULE: Two documents can ONLY be grouped if they have the EXACT SAME "⚠️_ACTUAL_DOCUMENT_TYPE". 
   - If Document A is "Appraisal Deposit Agreement" and Document B is "Notice Regarding Lender Contributions", they are DIFFERENT documents - DO NOT GROUP.
   - Ignore filename similarities - focus ONLY on the actual document type and content.

DOCUMENT LIST ({len(documents)} documents):
{json.dumps(doc_summaries, indent=2)}

⚠️ IMPORTANT FIELDS IN THE DOCUMENT LIST ABOVE:
- "⚠️_ACTUAL_DOCUMENT_TYPE": The actual document type (must be identical for grouping)
- "🖊️_HAS_SIGNATURE": Whether the document is SIGNED (✅) or UNSIGNED (❌)
- "dates": Key dates found in the document

FULL DOCUMENT CONTENT (COMPLETE - NO TRUNCATION):
"""
    
    for idx, doc in enumerate(documents, 1):
        prompt += f"\n\n{'='*80}\n"
        prompt += f"DOCUMENT {idx}: {doc['filename']}\n"
        prompt += f"{'='*80}\n"
        # Send FULL content - NO TRUNCATION
        prompt += doc['content']
    
    prompt += f"""

{'='*80}
GROUPING TASK
{'='*80}

For EACH PAIR of documents, first determine: Are these the SAME DOCUMENT or DIFFERENT DOCUMENTS?

TWO DOCUMENTS ARE THE SAME ONLY IF:
1. **Same Document Type**: e.g., both are "Closing Disclosure" (not just both from loanDepot)
2. **Same Purpose**: Both serve the exact same purpose in the loan process
3. **Same Core Content**: The substantive content is the same (amounts, terms, conditions)
4. **Different Only In**: Status (preliminary/final), signatures (signed/unsigned), dates (versions), completeness

TWO DOCUMENTS ARE DIFFERENT IF:
1. **Different Purpose**: One is about appraisal fees, another about lender contributions
2. **Different Content Type**: One is a disclosure, another is an agreement
3. **Different Legal Function**: Even if from same lender/borrower

EXAMPLES OF SAME DOCUMENT (should be grouped):
- "Closing Disclosure dated Aug 4" vs "Closing Disclosure dated Aug 21" (chronological versions)
- "Unsigned Rate Lock Agreement" vs "Signed Rate Lock Agreement" (signed/unsigned versions)
- "Preliminary Loan Estimate" vs "Final Loan Estimate" (preliminary/final versions)

EXAMPLES OF DIFFERENT DOCUMENTS (should NOT be grouped):
- "Notice about Lender Contributions" vs "Appraisal Deposit Agreement" (different purposes)
- "Closing Disclosure" vs "Loan Estimate" (different document types)
- "Borrower Certification" vs "Property Inspection Waiver" (different purposes)

⚠️ IGNORE FILENAME PATTERNS: Documents like "additional_other_disclosures_10.pdf" and "additional_other_disclosures_11.pdf" may have similar filenames but could be COMPLETELY DIFFERENT documents. Always compare the CONTENT and PURPOSE.

Return a JSON object with this structure:
{{
  "batch_number": {batch_num},
  "total_documents_analyzed": {len(documents)},
  "groups": [
    {{
      "group_id": 1,
      "group_type": "signed_unsigned|chronological|preliminary_final|revised|incomplete_complete",
      "document_type": "EXACT document type (must be identical for all docs in group)",
      "document_purpose": "What this document type does",
      "documents": [
        {{
          "index": 1,
          "filename": "document_name.pdf",
          "version_type": "unsigned|signed|preliminary|final|draft|revised|incomplete|complete",
          "confidence": "HIGH|MEDIUM|LOW",
          "key_identifiers": ["specific differences like dates, signatures, revision marks"]
        }}
      ],
      "reasoning": "Why these are versions of the SAME document (not just similar filenames)"
    }}
  ],
  "ungrouped_documents": [
    {{
      "index": 2,
      "filename": "unique_document.pdf",
      "reason": "no versions found" or "different document type/purpose from others"
    }}
  ]
}}

IMPORTANT RULES:
- Groups must have at least 2 documents
- All documents in a group must have the EXACT SAME document_type
- All documents in a group must serve the SAME PURPOSE
- Only group if differences are MINOR (status, date, signature) not SUBSTANTIVE (content, purpose)
- When in doubt, keep documents separate (ungrouped)
- Be CONSERVATIVE - false negatives (missing a group) are better than false positives (wrong grouping)

⚠️ CRITICAL CLASSIFICATION PRIORITY:
When determining group_type, use this hierarchy (check in this order):
1. **signed_unsigned**: If documents have DIFFERENT signature status (one has signature/acknowledgment, other doesn't) → signed_unsigned
2. **preliminary_final**: If documents are marked as preliminary vs final versions → preliminary_final
3. **chronological**: If documents have DIFFERENT dates but SAME signature status → chronological
4. **revised**: If documents show evidence of revisions, amendments, or corrections → revised
5. **incomplete_complete**: If one document has missing sections/data that the other has → incomplete_complete

⚠️ KEY DISTINCTION: "signed_unsigned" vs "chronological"
- If TWO documents have the SAME DATE but one is SIGNED and one is UNSIGNED → Group type is "signed_unsigned"
- If TWO documents have DIFFERENT DATES and SAME signature status → Group type is "chronological"
- Signature difference ALWAYS takes precedence over date difference

CONCRETE EXAMPLE:
Document A: "Flood Notice dated AUGUST 4, 2025" - UNSIGNED (no signature/acknowledgment fields)
Document B: "Flood Notice dated AUGUST 4, 2025" - SIGNED (has acknowledgment_date field)
→ Group type MUST be "signed_unsigned" (NOT chronological, because the dates are the SAME)

NOTE: "acknowledgment_date" indicates a signature was added, making it a SIGNED document.

Provide ONLY valid JSON, no other text."""
    
    return prompt


def semantic_group_batch(documents: List[Dict], batch_num: int, total_batches: int, client: LlamaClient) -> Dict:
    """Send a batch to Llama for semantic grouping"""
    
    print(f"\n🤖 Processing Batch {batch_num}/{total_batches}")
    print(f"   Documents: {len(documents)}")
    total_tokens = sum(doc['tokens'] for doc in documents)
    print(f"   Total tokens: ~{total_tokens:,}")
    
    prompt = create_semantic_grouping_prompt(documents, batch_num, total_batches)
    
    try:
        response = client.invoke_model(
            messages=[{
                "role": "user",
                "content": prompt
            }],
            max_tokens=8000,
            temperature=0.0
        )
        
        # Extract response
        result_text = response.get('content', str(response))
        
        # Parse JSON
        try:
            if '```json' in result_text:
                json_start = result_text.find('```json') + 7
                json_end = result_text.find('```', json_start)
                json_text = result_text[json_start:json_end].strip()
            elif '```' in result_text:
                json_start = result_text.find('```') + 3
                json_end = result_text.rfind('```')
                json_text = result_text[json_start:json_end].strip()
            else:
                json_start = result_text.find('{')
                json_end = result_text.rfind('}') + 1
                json_text = result_text[json_start:json_end]
            
            result_json = json.loads(json_text)
            print(f"   ✅ Found {len(result_json.get('groups', []))} groups, {len(result_json.get('ungrouped_documents', []))} ungrouped")
            return result_json
            
        except json.JSONDecodeError as e:
            print(f"   ⚠️  JSON parse error: {e}")
            print(f"   Raw response (first 500 chars): {result_text[:500]}")
            return {
                "batch_number": batch_num,
                "error": f"JSON parse failed: {e}",
                "raw_response": result_text[:1000]
            }
    
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return {
            "batch_number": batch_num,
            "error": str(e)
        }


def extract_document_metadata(doc: Dict) -> Dict:
    """Extract key metadata from document for validation"""
    content_json = json.loads(doc['content'])
    pages = content_json.get('pages', [])
    
    doc_summary = content_json.get('document_summary', {})
    overview = doc_summary.get('document_overview', {})
    
    # Extract all possible dates from ALL pages
    dates = []
    
    # Common date field names
    date_fields = ['date', 'effective_date', 'ordered_date', 'creation_date', 
                   'date_issued', 'closing_date', 'date_signed', 'agreement_date',
                   'signature_date', 'lock_in_date', 'expiration_date', 'acknowledgment_date']
    
    # Check overview first
    for field in date_fields:
        date_val = overview.get(field)
        if date_val:
            dates.append({field: date_val})
    
    # Check ALL pages for dates
    for page in pages:
        key_data = page.get('key_data', {})
        for field in date_fields:
            date_val = key_data.get(field)
            if date_val and {field: date_val} not in dates:
                dates.append({field: date_val})
    
    # Extract form IDs from ALL pages
    form_ids = []
    form_id_fields = ['form_number', 'form_id', 'form_type', 'document_id', 
                      'reference_number', 'loan_number']
    
    for field in form_id_fields:
        form_val = overview.get(field)
        if form_val:
            form_ids.append({field: form_val})
    
    for page in pages:
        key_data = page.get('key_data', {})
        for field in form_id_fields:
            form_val = key_data.get(field)
            if form_val and {field: form_val} not in form_ids:
                form_ids.append({field: form_val})
    
    # Check for standard form references in document type
    if pages:
        doc_type = pages[0].get('document_type_on_page', '')
        if 'Form' in doc_type or 'form' in doc_type:
            form_ids.append({'document_type_has_form': doc_type})
    
    # Extract signature status - CHECK ALL PAGES
    has_signature = False
    signature_fields = ['signature', 'signed', 'borrower_signature', 'lender_signature',
                       'acknowledgment', 'acknowledgment_date', 'acknowledgment_time',
                       'signature_date', 'signature_time', 'electronic_signature']
    
    for page in pages:
        key_data = page.get('key_data', {})
        for field in signature_fields:
            if key_data.get(field):
                has_signature = True
                break
        if has_signature:
            break
    
    return {
        'dates': dates,
        'form_ids': form_ids,
        'has_signature': has_signature,
        'document_type': pages[0].get('document_type_on_page', 'Unknown') if pages else 'Unknown',
        'page_count': len(pages)
    }


def validate_and_enrich_groups(batch_results: List[Dict], all_documents: List[Dict]) -> Dict:
    """Validate groups and enrich with metadata"""
    
    # Create document lookup
    doc_lookup = {doc['filename']: doc for doc in all_documents}
    
    enriched_groups = []
    
    for batch_result in batch_results:
        for group in batch_result.get('groups', []):
            enriched_group = group.copy()
            enriched_docs = []
            
            for doc_ref in group.get('documents', []):
                filename = doc_ref['filename']
                if filename in doc_lookup:
                    # Extract metadata
                    metadata = extract_document_metadata(doc_lookup[filename])
                    
                    enriched_doc = doc_ref.copy()
                    enriched_doc['dates'] = metadata['dates']
                    enriched_doc['form_ids'] = metadata['form_ids']
                    enriched_doc['has_signature'] = metadata['has_signature']
                    enriched_doc['validated_document_type'] = metadata['document_type']
                    
                    enriched_docs.append(enriched_doc)
            
            enriched_group['documents'] = enriched_docs
            
            # Validate group
            validation = validate_group(enriched_group)
            enriched_group['validation'] = validation
            
            enriched_groups.append(enriched_group)
    
    return enriched_groups


def validate_group(group: Dict) -> Dict:
    """Validate that a group meets the criteria"""
    docs = group.get('documents', [])
    group_type = group.get('group_type', '')
    
    validation = {
        'valid': True,
        'warnings': [],
        'confidence': 'HIGH'
    }
    
    # Check 1: All documents must have same document_type
    doc_types = set(doc.get('validated_document_type', 'Unknown') for doc in docs)
    if len(doc_types) > 1:
        validation['valid'] = False
        validation['warnings'].append(f"Mixed document types: {doc_types}")
        validation['confidence'] = 'LOW'
    
    # Check 2: Chronological groups must have dates
    if group_type == 'chronological':
        docs_with_dates = [doc for doc in docs if doc.get('dates')]
        if len(docs_with_dates) < len(docs):
            validation['warnings'].append(f"Only {len(docs_with_dates)}/{len(docs)} documents have dates")
            validation['confidence'] = 'MEDIUM'
    
    # Check 3: signed_unsigned groups should have different signature status
    if group_type == 'signed_unsigned':
        signature_statuses = [doc.get('has_signature', False) for doc in docs]
        if len(set(signature_statuses)) < 2:
            validation['warnings'].append("All documents have same signature status")
            validation['confidence'] = 'MEDIUM'
    
    # Check 4: At least some documents should have dates
    docs_with_any_date = [doc for doc in docs if doc.get('dates')]
    if len(docs_with_any_date) == 0:
        validation['warnings'].append("No documents have dates - cannot verify chronological order")
        validation['confidence'] = 'LOW'
    
    return validation


def deduplicate_groups(groups: List[Dict]) -> List[Dict]:
    """Remove duplicate groups where the same documents appear in multiple groups.
    Priority: signed_unsigned > preliminary_final > revised > incomplete_complete > chronological
    """
    
    # Create a map of document sets to groups
    doc_set_to_groups = defaultdict(list)
    
    for group in groups:
        doc_filenames = tuple(sorted([doc['filename'] for doc in group.get('documents', [])]))
        doc_set_to_groups[doc_filenames].append(group)
    
    # Priority mapping for group types
    group_type_priority = {
        'signed_unsigned': 1,
        'preliminary_final': 2,
        'revised': 3,
        'incomplete_complete': 4,
        'chronological': 5,
        'other': 6
    }
    
    # For each set of duplicate groups, keep only the highest priority one
    deduplicated = []
    
    for doc_set, group_list in doc_set_to_groups.items():
        if len(group_list) == 1:
            deduplicated.append(group_list[0])
        else:
            # Multiple groups with same documents - keep the highest priority
            sorted_groups = sorted(group_list, key=lambda g: (
                group_type_priority.get(g.get('group_type', 'other'), 99),
                -len(g.get('documents', []))  # If same priority, prefer larger group
            ))
            best_group = sorted_groups[0]
            deduplicated.append(best_group)
            
            # Log the deduplication
            print(f"   ℹ️  Deduplicated: Kept '{best_group.get('group_type')}' over {[g.get('group_type') for g in sorted_groups[1:]]} for {len(doc_set)} documents")
    
    return deduplicated


def consolidate_groups(batch_results: List[Dict], all_documents: List[Dict]) -> Dict:
    """Consolidate and validate groups across all batches"""
    
    # Validate and enrich groups with metadata
    print("\n🔍 Validating and enriching groups with dates/form IDs...")
    enriched_groups = validate_and_enrich_groups(batch_results, all_documents)
    
    # Deduplicate groups
    print("\n🔧 Deduplicating groups...")
    enriched_groups = deduplicate_groups(enriched_groups)
    
    # Collect ungrouped documents
    all_ungrouped = []
    for batch_result in batch_results:
        if 'ungrouped_documents' in batch_result:
            all_ungrouped.extend(batch_result['ungrouped_documents'])
    
    # Create final consolidated result
    consolidated = {
        'timestamp': datetime.now().isoformat(),
        'total_documents': len(all_documents),
        'total_groups': len(enriched_groups),
        'total_ungrouped': len(all_ungrouped),
        'groups': enriched_groups,
        'ungrouped_documents': all_ungrouped,
        'batch_results': batch_results
    }
    
    return consolidated


def semantic_group_documents(loan_id: str, stage1_output_dir: Path):
    """Main function for semantic document grouping"""
    
    print("\n" + "="*80)
    print(f"🔍 STAGE 1 STEP 3.1: Semantic Document Grouping - {loan_id}")
    print("="*80)
    
    # Load all extracted JSONs
    print("\n📂 Loading extracted JSON files...")
    documents = load_extracted_jsons(stage1_output_dir, loan_id)
    print(f"   Loaded {len(documents)} documents")
    
    total_tokens = sum(doc['tokens'] for doc in documents)
    print(f"   Total tokens: ~{total_tokens:,}")
    
    # Filter and sort
    print("\n🔧 Filtering and sorting documents...")
    included_docs, excluded_docs = filter_and_sort_documents(documents, max_pages=50)
    print(f"   Included: {len(included_docs)} documents")
    print(f"   Excluded (>50 pages, single instance): {len(excluded_docs)} documents")
    
    if excluded_docs:
        print("\n   Excluded files:")
        for doc in excluded_docs:
            print(f"      - {doc['filename']} ({doc['page_count']} pages)")
    
    # Create batches
    print("\n📦 Creating batches (~100k tokens each)...")
    batches = create_batches(included_docs, target_tokens=100000)
    print(f"   Created {len(batches)} batches")
    
    for idx, batch in enumerate(batches, 1):
        batch_tokens = sum(doc['tokens'] for doc in batch)
        print(f"   Batch {idx}: {len(batch)} docs, ~{batch_tokens:,} tokens")
    
    # Process each batch with Llama
    print("\n" + "="*80)
    print("🤖 SEMANTIC GROUPING WITH LLAMA 4 MAVERICK")
    print("="*80)
    
    client = LlamaClient()
    batch_results = []
    
    for idx, batch in enumerate(batches, 1):
        result = semantic_group_batch(batch, idx, len(batches), client)
        batch_results.append(result)
        
        # Small delay between batches
        if idx < len(batches):
            import time
            time.sleep(2)
    
    # Consolidate results
    print("\n" + "="*80)
    print("📊 CONSOLIDATING RESULTS")
    print("="*80)
    
    consolidated = consolidate_groups(batch_results, included_docs)
    
    # Save results
    output_file = stage1_output_dir / "1_3_1_semantic_groups.json"
    with open(output_file, 'w') as f:
        json.dump(consolidated, f, indent=2)
    
    # Print summary
    print(f"\n✅ Semantic grouping complete!")
    print(f"   Total documents analyzed: {len(included_docs)}")
    print(f"   Total groups found: {consolidated['total_groups']}")
    print(f"   Ungrouped documents: {consolidated['total_ungrouped']}")
    print(f"\n💾 Results saved: {output_file.name}")
    
    # Print group details
    if consolidated['groups']:
        print("\n📋 GROUPS FOUND:")
        for group in consolidated['groups']:
            validation = group.get('validation', {})
            valid_icon = "✅" if validation.get('valid', True) else "⚠️"
            confidence = validation.get('confidence', 'UNKNOWN')
            
            print(f"\n   {valid_icon} Group {group.get('group_id', '?')}: {group.get('document_type', 'Unknown')}")
            print(f"   Type: {group.get('group_type', 'unknown')} | Confidence: {confidence}")
            print(f"   Documents: {len(group.get('documents', []))}")
            
            for doc in group.get('documents', []):
                # Show dates if available
                dates_str = ""
                if doc.get('dates'):
                    dates_str = " | Dates: " + ", ".join([f"{list(d.keys())[0]}={list(d.values())[0]}" for d in doc['dates'][:2]])
                
                # Show form IDs if available
                form_str = ""
                if doc.get('form_ids'):
                    form_str = " | Form: " + ", ".join([f"{list(f.values())[0]}" for f in doc['form_ids'][:1]])
                
                # Show signature status
                sig_str = " | ✍️ Signed" if doc.get('has_signature') else " | ⭕ Unsigned"
                
                print(f"      - {doc.get('filename', 'unknown')} ({doc.get('version_type', 'unknown')}){dates_str}{form_str}{sig_str}")
            
            # Show validation warnings
            if validation.get('warnings'):
                print(f"      ⚠️  Warnings: {'; '.join(validation['warnings'])}")
    
    print("\n" + "="*80)
    
    return consolidated


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python 1_3_1_semantic_grouping.py <loan_id>")
        print("\nExample:")
        print("  python 1_3_1_semantic_grouping.py loan_1642451")
        sys.exit(1)
    
    loan_id = sys.argv[1]
    
    # Setup paths
    script_dir = Path(__file__).parent
    stage1_output_dir = script_dir / "output" / loan_id
    
    if not stage1_output_dir.exists():
        print(f"❌ Error: Stage 1 output not found for {loan_id}")
        sys.exit(1)
    
    # Run semantic grouping
    result = semantic_group_documents(loan_id, stage1_output_dir)
    
    print("\n✅ Semantic grouping complete!")

