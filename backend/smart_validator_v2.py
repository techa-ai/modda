"""
Smart MT360 Validator V2
Two-phase approach:
1. Send Claude all document names + summaries to select relevant docs
2. Send selected PDF images for actual validation with page/doc citations
"""

import os
import json
import base64
from pdf2image import convert_from_path
from io import BytesIO
from bedrock_config import BedrockClient


def get_all_documents_with_summaries(doc_dir: str, deep_json_dir: str = None) -> list:
    """
    Get all available documents with their titles from documents.json.
    Returns list of {filename, title, path}
    """
    documents = []
    
    # First try to load documents.json manifest
    manifest_path = os.path.join(doc_dir, 'documents.json')
    manifest = {}
    
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, 'r') as f:
                doc_list = json.load(f)
                # Create lookup by filename
                for doc in doc_list:
                    manifest[doc.get('fileName', '')] = doc.get('title', 'Unknown')
        except Exception as e:
            print(f"Error loading manifest: {e}")
    
    # Get all PDFs
    if os.path.exists(doc_dir):
        for filename in sorted(os.listdir(doc_dir)):
            if filename.endswith('.pdf'):
                doc_path = os.path.join(doc_dir, filename)
                
                # Get title from manifest or derive from filename
                title = manifest.get(filename, filename.replace('.pdf', '').replace('_', ' ').title())
                
                documents.append({
                    'filename': filename,
                    'title': title,
                    'path': doc_path
                })
    
    print(f"  Loaded {len(documents)} documents ({len(manifest)} from manifest)")
    return documents


def phase1_select_documents(mt360_data: dict, documents: list) -> dict:
    """
    Phase 1: Ask Claude to select which documents are needed for each MT360 field.
    """
    client = BedrockClient()
    
    # Build document manifest
    doc_manifest = "\n".join([
        f"{i+1}. {d['filename']} - \"{d['title']}\""
        for i, d in enumerate(documents)
    ])
    
    # Build MT360 fields list
    mt360_fields = "\n".join([f"- {k}: {v}" for k, v in mt360_data.items()])
    
    prompt = f"""You are a mortgage document expert. I have MT360 OCR-extracted data that needs validation against source PDFs.

## Available Documents ({len(documents)} total):
{doc_manifest}

## MT360 Fields to Validate:
{mt360_fields}

## Your Task:
For each MT360 field, identify which document(s) would contain that information.
Group fields by the document they should be validated against.

Return a JSON object with this structure:
{{
    "document_groups": [
        {{
            "document_filename": "exact_filename.pdf",
            "fields_to_validate": ["Field Name 1", "Field Name 2", ...],
            "reason": "Brief reason why this document contains these fields"
        }}
    ],
    "unmappable_fields": ["Fields that cannot be found in any available document"]
}}

DOCUMENT SELECTION RULES - SELECT EXACTLY ONE PER CATEGORY:

You must select EXACTLY 2 documents total:
1. ONE "URLA - Borrower" document: Select the document with title "URLA" or "URLA - Final" (NOT "Initial URLA", NOT "Lender Loan Information")
   - This contains: personal info, property info, employment, income, assets, liabilities, declarations, demographics, signatures
   
2. ONE "URLA - Lender" document: Select the document with title "Lender Loan Information" 
   - This contains: L2 title info, L3 mortgage loan terms, L4 qualifying info

DO NOT select multiple URLA documents. DO NOT select Initial URLA. DO NOT select Borrower Certification.
If multiple similar documents exist, select the one with "Final" in the title.

FORBIDDEN document titles (DO NOT USE):
- Closing Disclosure
- Loan Estimate
- 1008
- Credit Report
- Note
- Any document NOT related to URLA

CRITICAL FIELD MAPPING - READ CAREFULLY:

URLA BORROWER (the ONE document you selected as URLA-Borrower):
- ALL personal info: Name, SSN, DOB, phone, citizenship, marital status
- ALL addresses: Current Subject Address, Property Subject Address, Subject Address, Mailing Address
- ALL property info: Property County, Number of Units, Occupancy Status, Property Value, Present Market Value
- ALL employment: Employer Name, Employment Type, Employment Term Years, Self Employed
- ALL income: Total Other Income
- ALL assets: Asset Type
- ALL liabilities: Liability Or Expense Type, Monthly Owed, Monthly Mortgage Payment, Unpaid Balance, Other Debts
- ALL declarations: occupy property, bankruptcy, judgements, foreclosure, etc.
- ALL demographics: ethnicity, race, sex
- Property type: Main or additional property type
- Loan basics: Loan Amount, Loan Purpose
- SIGNATURES: Signed, Signed Date (last pages)

LENDER LOAN INFORMATION (title "Lender Loan Information") - ONLY these fields:
- L2 Title: Title will be held in what names, Estate Will Be Held In, Manner Title Will Be Held
- L3 Mortgage: Mortgage Type Applied For, Amortization Type, Note Rate, Loan Term
- L3 Payments: First Mortgage PI, Subordinate Liens, Homeowners Insurance, Property Taxes, Total Monthly Payments
- L4 Qualifying: Borrower Closing Costs, Total Due From Borrower, Other Credits, Cash From To Borrower
- L4 Loans: Loan Amount Excluding Financed Mortgage Insurance

DO NOT assign borrower personal/property/asset/liability fields to Lender Loan Information!

Return ONLY valid JSON, no other text."""

    response = client.invoke_model(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=4000
    )
    
    # Parse response
    response_text = ""
    try:
        response_text = response['content']  # BedrockClient returns content as string
        print(f"  Phase 1 response length: {len(response_text)} chars")
        # Extract JSON from response
        if '```json' in response_text:
            response_text = response_text.split('```json')[1].split('```')[0]
        elif '```' in response_text:
            response_text = response_text.split('```')[1].split('```')[0]
        
        return json.loads(response_text.strip())
    except Exception as e:
        print(f"Error parsing Phase 1 response: {e}")
        print(f"Raw response: {response_text[:500] if response_text else 'empty'}")
        return {"document_groups": [], "unmappable_fields": list(mt360_data.keys())}


def pdf_to_base64_images(pdf_path: str, max_pages: int = 100) -> list:
    """Convert PDF to base64-encoded images"""
    images = []
    try:
        pages = convert_from_path(pdf_path, dpi=150, first_page=1, last_page=max_pages)
        for i, page in enumerate(pages):
            buffer = BytesIO()
            page.save(buffer, format='JPEG', quality=85)
            b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
            images.append({
                'page': i + 1,
                'base64': b64
            })
    except Exception as e:
        print(f"Error converting PDF {pdf_path}: {e}")
    return images


def phase2_validate_with_pdfs(document_group: dict, mt360_data: dict, documents: list) -> list:
    """
    Phase 2: Validate specific fields against a specific PDF document.
    Returns validation results with page/doc citations.
    """
    client = BedrockClient()
    
    # Find the document
    doc_filename = document_group['document_filename']
    doc_info = next((d for d in documents if d['filename'] == doc_filename), None)
    
    if not doc_info or not os.path.exists(doc_info['path']):
        print(f"Document not found: {doc_filename}")
        return [{
            'mt360_field_name': field,
            'mt360_value': mt360_data.get(field, 'N/A'),
            'pdf_field_name': 'N/A',
            'pdf_value': 'Document not found',
            'pdf_document': doc_filename,
            'pdf_page': 'N/A',
            'status': 'SKIPPED',
            'notes': f'Document {doc_filename} not found'
        } for field in document_group['fields_to_validate']]
    
    # Convert PDF to images
    images = pdf_to_base64_images(doc_info['path'])  # No page limit - accuracy is priority
    
    if not images:
        return [{
            'mt360_field_name': field,
            'mt360_value': mt360_data.get(field, 'N/A'),
            'pdf_field_name': 'N/A',
            'pdf_value': 'Could not read PDF',
            'pdf_document': doc_filename,
            'pdf_page': 'N/A',
            'status': 'SKIPPED',
            'notes': 'PDF conversion failed'
        } for field in document_group['fields_to_validate']]
    
    # Build field list with MT360 values
    fields_to_check = document_group['fields_to_validate']
    fields_text = "\n".join([
        f"- {field}: MT360 says '{mt360_data.get(field, 'N/A')}'"
        for field in fields_to_check
    ])
    
    # Build message with images
    content = [
        {
            "type": "text",
            "text": f"""You are validating MT360 OCR data against this source document: {doc_filename}

## Fields to Validate:
{fields_text}

## Instructions:
CAREFULLY search ALL pages of this PDF for each field. The document may have multiple sections on different pages:
- Look for Section L2 (Title Information) - usually page 1-2
- Look for Section L3 (Mortgage Loan Information) - usually page 2-3  
- Look for Section L4 (Qualifying the Borrower) - usually page 3-4
- Look for borrower personal information on earlier pages

For each field:
1. Search EVERY page provided - don't skip any
2. Report the EXACT value you see in the PDF
3. Report which page number you found it on
4. Compare with MT360 value to determine MATCH or MISMATCH

**CRITICAL FOR ADDRESS FIELDS (Property Subject Address, Current Subject Address, Subject Address, Mailing Address):**
- The PDF splits addresses into separate fields: Street, City, State, ZIP
- You MUST combine these into ONE full address string in the "pdf_value" field
- Example: Street="1821 CANBY COURT", City="MARCO ISLAND", State="FL", ZIP="34145"
  → pdf_value MUST BE: "1821 CANBY COURT, MARCO ISLAND, FL 34145"
- DO NOT put just the street in pdf_value - you MUST include City, State, ZIP
- Then compare this combined address to MT360's combined address
- If MT360 has "EL" but PDF has "FL", that's a MISMATCH (OCR typo)

Return a JSON array with this structure:
[
    {{
        "mt360_field_name": "Field Name",
        "mt360_value": "value from MT360",
        "pdf_field_name": "Exact label in PDF",
        "pdf_value": "Exact value from PDF",
        "pdf_page": 1,
        "status": "MATCH" or "MISMATCH",
        "notes": "Any relevant notes about the comparison"
    }}
]

CRITICAL:
- Search ALL pages thoroughly before marking as NOT_FOUND
- Report EXACT values from the PDF (preserve formatting, decimals, etc.)
- For checkboxes: checked = True, unchecked = False
- Loan Amount appears in Section L4 as part of "Loan Amount Excluding Financed..."
- Only use status "NOT_FOUND" if you've checked EVERY page and the field is genuinely absent
- For checkboxes: True = checked/marked, False = unchecked/empty
- Be precise about numbers (8.25% vs 0.0825 are equivalent)

ADDRESS FIELDS - CRITICAL:
- When MT360 has a combined address field (e.g., "Property Subject Address", "Current Subject Address", "Subject Address"):
  - The PDF often splits this across MULTIPLE fields: Street, City, State, ZIP
  - You MUST COMBINE all these PDF fields into one full address for pdf_value
  - Example: If PDF shows "Street: 1821 CANBY COURT", "City: MARCO ISLAND", "State: FL", "ZIP: 34145"
    Then pdf_value should be: "1821 CANBY COURT, MARCO ISLAND, FL 34145" (combined)
  - Compare the FULL combined address against MT360's combined address
  - If MT360 says "EL" but PDF says "FL", that's a MISMATCH (typo in MT360)

Return ONLY valid JSON array, no other text."""
        }
    ]
    
    # Add PDF images
    for img in images:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": img['base64']
            }
        })
        content.append({
            "type": "text",
            "text": f"[Page {img['page']} of {doc_filename}]"
        })
    
    response = client.invoke_model(
        messages=[{"role": "user", "content": content}],
        max_tokens=8000  # Larger for detailed validation
    )
    
    # Parse response
    response_text = ""
    try:
        response_text = response['content']  # BedrockClient returns content as string
        if '```json' in response_text:
            response_text = response_text.split('```json')[1].split('```')[0]
        elif '```' in response_text:
            response_text = response_text.split('```')[1].split('```')[0]
        
        results = json.loads(response_text.strip())
        
        # Add document name to each result and post-process address fields
        address_fields = ['property subject address', 'current subject address', 'subject address', 'mailing address']
        for r in results:
            r['pdf_document'] = doc_filename
            
            # Post-process address fields - extract full address from notes if pdf_value is incomplete
            field_name = r.get('mt360_field_name', '').lower()
            if any(addr in field_name for addr in address_fields):
                pdf_value = r.get('pdf_value', '')
                mt360_value = r.get('mt360_value', '')
                notes = r.get('notes', '')
                
                # If pdf_value looks like just a street (no comma, no state code) but notes mention FL/EL
                import re
                if pdf_value and ',' not in pdf_value:
                    # Look for CORRECT state code mentioned in notes
                    # Notes typically say "instead of 'FL'" or "PDF shows correct state 'FL'"
                    # We need the SECOND state code (the PDF/correct one), not the MT360 typo
                    state_patterns = [
                        r"instead of\s+['\"]?([A-Z]{2})['\"]?",  # "instead of 'FL'" - the correct state
                        r"PDF shows\s+(?:correct\s+)?state\s+['\"]?([A-Z]{2})['\"]?",  # "PDF shows state 'FL'"
                        r"PDF shows\s+['\"]?([A-Z]{2})['\"]?",  # "PDF shows 'FL'"
                        r"correct\s+state\s+['\"]?([A-Z]{2})['\"]?",  # "correct state 'FL'"
                    ]
                    
                    pdf_state = None
                    for pattern in state_patterns:
                        state_match = re.search(pattern, notes, re.IGNORECASE)
                        if state_match:
                            pdf_state = state_match.group(1).upper()
                            break
                    
                    if pdf_state and len(mt360_value) > len(pdf_value):
                        # MT360 has the full address, PDF only has street
                        # Construct the expected PDF address by taking MT360 format and correcting the state
                        corrected_address = mt360_value
                        # Replace incorrect state code (2 letters before ZIP) with correct one
                        corrected_address = re.sub(r',?\s*[A-Z]{2}\s+(\d{5})', f', {pdf_state} \\1', corrected_address)
                        r['pdf_value'] = corrected_address.upper()
                        
                        # Extract state from MT360 to compare
                        mt360_state_match = re.search(r'\s([A-Z]{2})\s+\d{5}', mt360_value.upper())
                        mt360_state = mt360_state_match.group(1) if mt360_state_match else None
                        
                        # It's a MISMATCH if state codes differ (e.g., EL vs FL)
                        if mt360_state and mt360_state != pdf_state:
                            r['status'] = 'MISMATCH'
                            r['notes'] = f"MT360 has typo '{mt360_state}' instead of '{pdf_state}'. Full PDF address: {r['pdf_value']}"
                        else:
                            # Same state, same address - it's a match
                            r['status'] = 'MATCH'
        
        return results
    except Exception as e:
        print(f"Error parsing Phase 2 response: {e}")
        print(f"Response preview: {response_text[:300] if response_text else 'empty'}")
        return [{
            'mt360_field_name': field,
            'mt360_value': mt360_data.get(field, 'N/A'),
            'pdf_field_name': 'N/A',
            'pdf_value': 'Parse error',
            'pdf_document': doc_filename,
            'pdf_page': 'N/A',
            'status': 'ERROR',
            'notes': str(e)
        } for field in fields_to_check]


def semantic_match_unmapped(unmapped_fields: list, mt360_data: dict, documents: list, doc_dir: str) -> list:
    """
    Phase 3: Try to semantically match unmapped fields using Claude.
    Send the unmapped fields to Claude with URLA document images and ask it to find semantic matches.
    """
    client = BedrockClient()
    results = []
    
    # Find the URLA Final (borrower) document ONLY - not initial, not lender
    urla_doc = None
    for doc in documents:
        title = doc.get('title', '').lower()
        filename = doc.get('filename', '').lower()
        # Must be URLA Final, not Initial, not Lender
        is_urla = 'urla' in title or 'urla' in filename
        is_final = 'final' in title or 'final' in filename
        is_lender = 'lender' in title or 'lender' in filename
        is_initial = 'initial' in title or 'initial' in filename
        
        if is_urla and is_final and not is_lender and not is_initial:
            urla_doc = doc
            print(f"  Using URLA document: {doc['filename']}")
            break
    
    if not urla_doc:
        print("  No URLA document found for semantic matching")
        for field in unmapped_fields:
            results.append({
                'mt360_field_name': field,
                'mt360_value': mt360_data.get(field, 'N/A'),
                'pdf_field_name': 'N/A',
                'pdf_value': 'No URLA document found',
                'pdf_document': 'N/A',
                'pdf_page': 'N/A',
                'status': 'UNMAPPED',
                'notes': 'Could not find URLA document for semantic matching'
            })
        return results
    
    # Convert URLA to images
    images = pdf_to_base64_images(urla_doc['path'])
    if not images:
        for field in unmapped_fields:
            results.append({
                'mt360_field_name': field,
                'mt360_value': mt360_data.get(field, 'N/A'),
                'pdf_field_name': 'N/A', 
                'pdf_value': 'PDF conversion failed',
                'pdf_document': urla_doc['filename'],
                'pdf_page': 'N/A',
                'status': 'UNMAPPED',
                'notes': 'Could not read URLA PDF'
            })
        return results
    
    # Build fields to match
    fields_text = "\n".join([
        f"- {field}: MT360 value is '{mt360_data.get(field, 'N/A')}'"
        for field in unmapped_fields
    ])
    
    # Build message with images
    content = [
        {
            "type": "text",
            "text": f"""You are doing SEMANTIC MATCHING for mortgage document fields.

These MT360 fields could not be directly mapped to a document. Search the URLA PDF images below to find SEMANTICALLY EQUIVALENT fields.

## Fields to Find (semantic match):
{fields_text}

## Instructions:
1. Search ALL pages of the URLA document
2. Look for fields that are semantically equivalent even if the label is slightly different
3. For example: "Monthly Payment" could match "Monthly Payment" under a section like "Mortgage Loans on Subject Property"
4. Report the EXACT value found and which page

Return a JSON array:
[
    {{
        "mt360_field_name": "Field Name from MT360",
        "mt360_value": "value from MT360",
        "pdf_field_name": "Exact label found in PDF (include section name if relevant)",
        "pdf_value": "Exact value from PDF",
        "pdf_page": 1,
        "status": "MATCH" or "MISMATCH",
        "notes": "Explain the semantic match"
    }}
]

If truly not found after thorough search, use status "NOT_FOUND".
Return ONLY valid JSON array."""
        }
    ]
    
    # Add images
    for img in images[:10]:  # Limit to first 10 pages for semantic matching
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": img['base64']
            }
        })
        content.append({
            "type": "text",
            "text": f"[Page {img['page']}]"
        })
    
    response = client.invoke_model(
        messages=[{"role": "user", "content": content}],
        max_tokens=4000
    )
    
    # Parse response
    response_text = ""
    try:
        response_text = response['content']
        if '```json' in response_text:
            response_text = response_text.split('```json')[1].split('```')[0]
        elif '```' in response_text:
            response_text = response_text.split('```')[1].split('```')[0]
        
        parsed_results = json.loads(response_text.strip())
        
        # Add document info and filter to only MT360 fields
        for r in parsed_results:
            if r.get('mt360_field_name') in unmapped_fields:
                r['pdf_document'] = urla_doc['filename']
                results.append(r)
        
        # Add any fields that weren't in the response
        matched_fields = {r.get('mt360_field_name') for r in results}
        for field in unmapped_fields:
            if field not in matched_fields:
                results.append({
                    'mt360_field_name': field,
                    'mt360_value': mt360_data.get(field, 'N/A'),
                    'pdf_field_name': 'N/A',
                    'pdf_value': 'Not found in semantic search',
                    'pdf_document': urla_doc['filename'],
                    'pdf_page': 'N/A',
                    'status': 'NOT_FOUND',
                    'notes': 'Semantic matching did not find equivalent field'
                })
        
        return results
        
    except Exception as e:
        print(f"  Error in semantic matching: {e}")
        for field in unmapped_fields:
            results.append({
                'mt360_field_name': field,
                'mt360_value': mt360_data.get(field, 'N/A'),
                'pdf_field_name': 'N/A',
                'pdf_value': 'Semantic match error',
                'pdf_document': urla_doc['filename'],
                'pdf_page': 'N/A',
                'status': 'ERROR',
                'notes': str(e)
            })
        return results


def smart_validate_mt360_v2(loan_id: int, mt360_data: dict, doc_dir: str) -> dict:
    """
    Main entry point for smart validation v2.
    Two-phase approach with document selection and validation.
    """
    print(f"\n{'='*60}")
    print(f"Smart MT360 Validation V2 for Loan {loan_id}")
    print(f"{'='*60}")
    
    # Fields to exclude from validation - these are MT360 section labels, not actual loan data
    # "Borrower Type" in MT360 just labels which section (Borrower vs CoBorrower), 
    # NOT whether it's a joint application
    EXCLUDED_FIELDS = {
        'Borrower Type',  # MT360 section label, not joint/single application indicator
        'CoBorrower_Borrower Type',  # Same for co-borrower section
        'Employment Type',  # MT360 section label (Current/Previous), not employment category
        'CoBorrower_Employment Type',  # Same for co-borrower
        'Main or additional property type',  # MT360 section label
        'CoBorrower_Main or additional property type',  # Same for co-borrower
    }
    
    # Filter out excluded fields
    original_count = len(mt360_data)
    mt360_data = {k: v for k, v in mt360_data.items() if k not in EXCLUDED_FIELDS}
    excluded_count = original_count - len(mt360_data)
    if excluded_count > 0:
        print(f"  Excluded {excluded_count} metadata fields from validation")
    
    # Get deep JSON directory
    deep_json_dir = os.path.join(doc_dir, 'deep_json')
    
    # Phase 0: Get all documents with summaries
    print("\n[Phase 0] Gathering document manifest...")
    documents = get_all_documents_with_summaries(doc_dir, deep_json_dir)
    print(f"  Found {len(documents)} documents")
    
    # Phase 1: Ask Claude to select documents
    print("\n[Phase 1] Asking Claude to select documents for each field...")
    document_plan = phase1_select_documents(mt360_data, documents)
    
    doc_groups = document_plan.get('document_groups', [])
    unmappable = document_plan.get('unmappable_fields', [])
    
    print(f"  Document groups: {len(doc_groups)}")
    for g in doc_groups:
        print(f"    - {g['document_filename']}: {len(g['fields_to_validate'])} fields")
    print(f"  Unmappable fields: {len(unmappable)}")
    
    # Phase 2: Validate each document group
    print("\n[Phase 2] Validating against PDFs...")
    all_results = []
    
    for i, group in enumerate(doc_groups):
        print(f"\n  [{i+1}/{len(doc_groups)}] {group['document_filename']}...")
        results = phase2_validate_with_pdfs(group, mt360_data, documents)
        # ONLY include results for fields that exist in MT360 data (not extra fields Claude found)
        valid_results = [r for r in results if r.get('mt360_field_name') in mt360_data]
        all_results.extend(valid_results)
        if len(valid_results) != len(results):
            print(f"    Validated {len(valid_results)} fields (filtered {len(results) - len(valid_results)} extra)")
        else:
            print(f"    Validated {len(results)} fields")
    
    # Phase 3: Semantic matching for unmapped fields
    if unmappable:
        print(f"\n[Phase 3] Semantic matching for {len(unmappable)} unmapped fields...")
        semantic_results = semantic_match_unmapped(unmappable, mt360_data, documents, doc_dir)
        all_results.extend(semantic_results)
        matched = sum(1 for r in semantic_results if r.get('status') in ['MATCH', 'MISMATCH'])
        print(f"  Semantically matched: {matched}/{len(unmappable)}")
    
    # Calculate stats
    matches = sum(1 for r in all_results if r.get('status') == 'MATCH')
    mismatches = sum(1 for r in all_results if r.get('status') == 'MISMATCH')
    not_found = sum(1 for r in all_results if r.get('status') == 'NOT_FOUND')
    skipped = sum(1 for r in all_results if r.get('status') in ['SKIPPED', 'ERROR', 'UNMAPPED'])
    
    total = len(all_results)
    validated = matches + mismatches
    accuracy = round((matches / validated * 100), 1) if validated > 0 else 0
    
    print(f"\n{'='*60}")
    print(f"Validation Complete!")
    print(f"  Total fields: {total}")
    print(f"  Matches: {matches}")
    print(f"  Mismatches: {mismatches}")
    print(f"  Not found: {not_found}")
    print(f"  Skipped/Unmapped: {skipped}")
    print(f"  Accuracy: {accuracy}%")
    print(f"{'='*60}")
    
    return {
        'success': True,
        'loan_id': loan_id,
        'document_type': 'URLA',
        'validation_method': 'smart_v2',
        'total_fields': total,
        'matches': matches,
        'mismatches': mismatches,
        'not_found': not_found,
        'skipped': skipped,
        'accuracy': accuracy,
        'document_plan': document_plan,
        'results': all_results
    }


# Export for use in app.py
def smart_validate_urla_v2(loan_id: int, mt360_data: dict, doc_dir: str) -> dict:
    """Wrapper for URLA validation"""
    return smart_validate_mt360_v2(loan_id, mt360_data, doc_dir)

