#!/usr/bin/env python3
"""
Create a comprehensive document map/audit of the entire tax return package.
Maps every page to its document, form type, entity/person, year, and relationships.
"""
import json
from typing import List, Dict, Any
from bedrock_config import call_bedrock

def load_pagewise_data(input_file: str) -> List[Dict[str, Any]]:
    """Load the pagewise extraction JSON."""
    with open(input_file, 'r') as f:
        data = json.load(f)
    return data.get('pages', [])

def group_consecutive_pages(pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Group consecutive pages with the same form/entity/year into document ranges.
    """
    if not pages:
        return []
    
    documents = []
    current_doc = {
        'start_page': pages[0].get('page'),
        'end_page': pages[0].get('page'),
        'form_name': pages[0].get('form_name'),
        'form_type': pages[0].get('form_type'),
        'person_name': pages[0].get('person_name'),
        'entity_name': pages[0].get('entity_name'),
        'year': pages[0].get('year'),
        'pages': [pages[0]]
    }
    
    for page in pages[1:]:
        # Check if this page belongs to the same document
        same_form = page.get('form_name') == current_doc['form_name']
        same_entity = (page.get('entity_name') == current_doc['entity_name'] or 
                      (not page.get('entity_name') and not current_doc['entity_name']))
        same_person = (page.get('person_name') == current_doc['person_name'] or 
                      (not page.get('person_name') and not current_doc['person_name']))
        same_year = page.get('year') == current_doc['year']
        consecutive = page.get('page') == current_doc['end_page'] + 1
        
        # If similar enough and consecutive, extend current document
        if consecutive and same_form and same_year and (same_entity or same_person):
            current_doc['end_page'] = page.get('page')
            current_doc['pages'].append(page)
        else:
            # Start new document
            documents.append(current_doc)
            current_doc = {
                'start_page': page.get('page'),
                'end_page': page.get('page'),
                'form_name': page.get('form_name'),
                'form_type': page.get('form_type'),
                'person_name': page.get('person_name'),
                'entity_name': page.get('entity_name'),
                'year': page.get('year'),
                'pages': [page]
            }
    
    # Add final document
    documents.append(current_doc)
    return documents

def create_document_audit(pages: List[Dict[str, Any]], batch_size: int = 200) -> str:
    """
    Send pages to Claude Haiku 4.5 to create a comprehensive document map.
    Process in smaller batches to avoid token limits.
    """
    # Group consecutive pages first
    documents = group_consecutive_pages(pages)
    
    print(f"📊 Identified {len(documents)} potential document ranges from {len(pages)} pages")
    print()
    
    # Create batches of documents
    audit_sections = []
    
    for i in range(0, len(documents), batch_size):
        batch = documents[i:i+batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(documents) + batch_size - 1) // batch_size
        
        print(f"📤 Processing batch {batch_num}/{total_batches} ({len(batch)} document ranges)...")
        
        # Create compact representation for Claude
        docs_summary = []
        for doc in batch:
            page_range = f"{doc['start_page']}-{doc['end_page']}" if doc['start_page'] != doc['end_page'] else str(doc['start_page'])
            docs_summary.append({
                'pages': page_range,
                'form_name': doc['form_name'],
                'form_type': doc['form_type'],
                'person': doc['person_name'],
                'entity': doc['entity_name'],
                'year': doc['year'],
                'num_pages': doc['end_page'] - doc['start_page'] + 1
            })
        
        prompt = f"""You are creating a COMPREHENSIVE DOCUMENT MAP/AUDIT for a 2271-page tax return package.

This is BATCH {batch_num} of {total_batches}.

DOCUMENT RANGES TO ANALYZE:
{json.dumps(docs_summary, indent=2)}

YOUR TASK:
Create a structured document map in this format:

```
DOCUMENT MAP - BATCH {batch_num}

[Page Range] | [Form Type] | [Description] | [Year]
-----------------------------------------------------------------------------
10-14        | Form 1120-S | Thor Guard, Inc. S-Corporation Return | 2023
15           | Form 1125-A | Cost of Goods Sold (Attachment to 1120-S Thor Guard) | 2023
16           | Form 4562   | Depreciation and Amortization (Attachment to 1120-S Thor Guard) | 2023
...
41-45        | Schedule K-1 (1120-S) | Robert M. Dugan - Shareholder K-1 | 2023
46-50        | Schedule K-1 (1120-S) | Tyler M. Townsend - Shareholder K-1 | 2023
...
```

RULES:
1. Merge consecutive pages with the same form/entity/person into single range
2. Identify attachments and note "Attachment to [parent form]"
3. Include full names for people (e.g., "Robert M. Dugan" not just "Robert Dugan")
4. Include entity names (e.g., "Thor Guard, Inc.")
5. Be specific about document type (e.g., "Schedule K-1 (Form 1120-S)" not just "K-1")
6. Group related documents logically
7. Use consistent formatting: "Pages X-Y | Form Type | Description | Year"

Return ONLY the formatted document map."""
        
        response = call_bedrock(
            prompt=prompt,
            model="claude-haiku-4-5",
            max_tokens=8000
        )
        
        audit_sections.append(response)
        print(f"✅ Batch {batch_num} complete")
        print()
    
    return "\n\n".join(audit_sections)

def main():
    input_file = "/Users/sunny/Applications/bts/jpmorgan/mortgage/modda/outputs/ocr/tax_returns_65/pagewise_extract_vision.json"
    output_file = "/Users/sunny/Applications/bts/jpmorgan/mortgage/modda/outputs/ocr/tax_returns_65/document_audit_map.txt"
    
    print("🚀 Creating Comprehensive Document Map/Audit")
    print("="*80)
    print()
    
    # Load pages
    pages = load_pagewise_data(input_file)
    print(f"📄 Loaded {len(pages)} pages")
    print()
    
    # Create audit
    audit_text = create_document_audit(pages, batch_size=200)
    
    # Save
    header = f"""TAX RETURN PACKAGE - COMPREHENSIVE DOCUMENT MAP
Borrower: ROBERT M DUGAN
Total Pages: {len(pages)}
Generated: {json.dumps({'date': 'now'})}

================================================================================

"""
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(header)
        f.write(audit_text)
    
    print()
    print(f"✅ Document map saved to: {output_file}")
    
    # Print summary
    documents = group_consecutive_pages(pages)
    print()
    print("📊 SUMMARY:")
    print(f"   Total pages: {len(pages)}")
    print(f"   Document ranges identified: {len(documents)}")
    print(f"   Output file: {output_file}")

if __name__ == "__main__":
    main()

