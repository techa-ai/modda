"""
Smart MT360 Validation - Uses multiple source documents
Selects the best document to validate each field category
"""
import os
import json
from pdf2image import convert_from_path
import base64
from io import BytesIO
from bedrock_config import BedrockClient

# Document categories and their relevant source documents
FIELD_CATEGORIES = {
    "borrower_info": {
        "fields": ["Borrower Type", "Name", "SSN/EIN", "Date of Birth", "Citizenship", 
                   "Marital Status", "Home Phone Number", "Reside Years", "House Classification",
                   "Mailing Address Different From Current", "Current Subject Address"],
        "docs": ["urla___final", "initial_urla"]
    },
    "loan_info": {
        "fields": ["Loan Amount", "Loan Purpose", "Number of Units", "Occupancy Status",
                   "Property Subject Address", "Property County", "Note Rate", "Loan Term",
                   "Mortgage Type Applied For", "Amortization Type", "First Mortgage PI",
                   "Subordinate Liens", "Total Monthly Payments"],
        "docs": ["lender_loan_information___final", "urla___final", "loan_estimate", "closing_disclosure", "1008___final"]
    },
    "property_info": {
        "fields": ["Property Value", "Present Market Value Total", "Main or additional property type",
                   "Subject Address", "Monthly Owed", "Monthly Mortgage Payment", "Unpaid Balance"],
        "docs": ["urla___final", "1008___final", "avm_report", "1103_final"]
    },
    "income_employment": {
        "fields": ["Total Other Income", "Employment Type", "Employer Name", "Employed Position",
                   "Employment Term Years", "Self Employed or Business Owner"],
        "docs": ["urla___final", "basic_income_worksheet", "tax_returns"]
    },
    "declarations": {
        "fields": ["Will occupy the property as primary residence", "Had ownership interest in another property",
                   "Borrowing undisclosed money", "Party of undisclosed debt", "Outstanding judgements",
                   "Delinquent or in default on federal debt", "Party in lawsuit", 
                   "Conveyed title in lieu of foreclosure", "Property foreclosed", "Declared bankruptcy",
                   "Loan foreclosure or judgement"],
        "docs": ["urla___final"]
    },
    "demographics": {
        "fields": ["Is Hispanic or Latino", "Is not Hispanic or Latino", "Does not wish to provide ethnicity information",
                   "Is American Indian or Alaskan Native", "Is Asian", "Is Black or African American",
                   "Is Native Hawaiian or Other Pacific Islander", "Is Native Hawaiian", "Is White",
                   "Does not wish to provide race information", "Is Female", "Is Male",
                   "Does not wish to provide sex information", "Demographic information provided by"],
        "docs": ["urla___final"]
    },
    "liabilities": {
        "fields": ["Monthly Payment", "Asset Type", "Liability Or Expense Type", "Other Debts",
                   "Borrower Closing Costs", "Total Due From Borrower", "Other Credits", "Cash From To Borrower"],
        "docs": ["urla___final", "closing_disclosure", "credit_report___final"]
    },
    "insurance_taxes": {
        "fields": ["Home Owners Insurance", "Property Taxes", "Conversion Construction",
                   "Title will be held in what names", "Estate Will Be Held In",
                   "Loan Amount Excluding Financed Mortgage Insurance"],
        "docs": ["urla___final", "closing_disclosure", "hazard_insurance_info__and_or_proof_of_insurance"]
    },
    "signature": {
        "fields": ["Signed", "Signed Date"],
        "docs": ["urla___final"]
    }
}


def get_document_summary(doc_dir):
    """Get a summary of available documents"""
    docs = {}
    if os.path.exists(doc_dir):
        for f in sorted(os.listdir(doc_dir)):
            if f.endswith('.pdf'):
                # Extract doc type from filename
                base = f.replace('.pdf', '')
                parts = base.rsplit('_', 1)
                if len(parts) == 2 and parts[1].isdigit():
                    doc_type = parts[0]
                else:
                    doc_type = base
                
                if doc_type not in docs:
                    docs[doc_type] = []
                docs[doc_type].append(f)
    return docs


def find_best_document(doc_dir, doc_types):
    """Find the best available document from a list of preferred types"""
    available = get_document_summary(doc_dir)
    
    for doc_type in doc_types:
        if doc_type in available:
            # Prefer 'final' versions
            files = available[doc_type]
            for f in files:
                if 'final' in f.lower():
                    return os.path.join(doc_dir, f)
            return os.path.join(doc_dir, files[0])
    return None


def pdf_to_base64_images(pdf_path, max_pages=3, dpi=150):
    """Convert PDF pages to base64 images"""
    images = []
    try:
        pages = convert_from_path(pdf_path, first_page=1, last_page=max_pages, dpi=dpi)
        for page in pages:
            buffered = BytesIO()
            page.save(buffered, format="PNG")
            images.append(base64.b64encode(buffered.getvalue()).decode())
    except Exception as e:
        print(f"    Error converting PDF: {e}")
    return images


def validate_field_category(category_name, category_config, mt360_fields, doc_dir):
    """Validate a category of fields against relevant documents"""
    
    # Get fields for this category that exist in MT360 data
    fields_to_validate = {k: v for k, v in mt360_fields.items() 
                         if k in category_config['fields']}
    
    if not fields_to_validate:
        return []
    
    # Find the best document
    pdf_path = find_best_document(doc_dir, category_config['docs'])
    if not pdf_path:
        print(f"    No document found for {category_name}")
        return [{"mt360_field_name": k, "mt360_value": v, 
                 "pdf_field_name": "N/A", "pdf_value": "N/A",
                 "status": "SKIP", "notes": "No source document available"}
                for k, v in fields_to_validate.items()]
    
    print(f"    Using: {os.path.basename(pdf_path)} for {len(fields_to_validate)} fields")
    
    # Convert PDF to images
    images = pdf_to_base64_images(pdf_path)
    if not images:
        return [{"mt360_field_name": k, "mt360_value": v,
                 "pdf_field_name": "N/A", "pdf_value": "N/A", 
                 "status": "SKIP", "notes": "Could not read PDF"}
                for k, v in fields_to_validate.items()]
    
    # Build prompt
    prompt = f"""Validate these MT360 extracted fields against the PDF document.

**MT360 FIELDS TO VALIDATE ({category_name}):**
```json
{json.dumps(fields_to_validate, indent=2)}
```

For EACH field above, find the corresponding value in the PDF and compare.

**OUTPUT FORMAT - JSON array only:**
```json
[
  {{
    "mt360_field_name": "Field name from MT360",
    "mt360_value": "Value from MT360",
    "pdf_field_name": "Field name as shown in PDF",
    "pdf_value": "Value from PDF",
    "status": "MATCH or MISMATCH",
    "notes": "Brief explanation"
  }}
]
```

**RULES:**
- MATCH if values are equivalent (ignore minor formatting)
- Boolean: True = Yes = Checked, False = No = Unchecked
- For checkboxes: verify if box is checked/unchecked in PDF
- You MUST validate ALL {len(fields_to_validate)} fields listed above

Output the JSON array:"""

    # Build message with images
    content = [{"type": "text", "text": prompt}]
    for img in images:
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": img}
        })
    
    # Call Bedrock
    client = BedrockClient(model='claude-opus-4-5')
    try:
        response = client.invoke_model(
            messages=[{"role": "user", "content": content}],
            max_tokens=8000,
            temperature=0.0
        )
        
        response_text = response['content']
        
        # Parse JSON
        if "```json" in response_text:
            json_start = response_text.find("```json") + 7
            json_end = response_text.find("```", json_start)
            json_str = response_text[json_start:json_end].strip()
        elif "```" in response_text:
            json_start = response_text.find("```") + 3
            json_end = response_text.find("```", json_start)
            json_str = response_text[json_start:json_end].strip()
        else:
            json_str = response_text.strip()
        
        return json.loads(json_str)
        
    except Exception as e:
        print(f"    Error: {e}")
        return [{"mt360_field_name": k, "mt360_value": v,
                 "pdf_field_name": "N/A", "pdf_value": "N/A",
                 "status": "ERROR", "notes": str(e)}
                for k, v in fields_to_validate.items()]


def smart_validate_urla(loan_id, mt360_data, doc_dir):
    """
    Smart validation that uses multiple source documents
    """
    mt360_fields = mt360_data.get('fields', {})
    all_results = []
    
    print(f"  Smart validation for {len(mt360_fields)} MT360 fields")
    print(f"  Processing by category...")
    
    for category_name, category_config in FIELD_CATEGORIES.items():
        print(f"\n  [{category_name}]")
        results = validate_field_category(category_name, category_config, mt360_fields, doc_dir)
        all_results.extend(results)
    
    # Calculate stats
    total = len(all_results)
    matches = sum(1 for r in all_results if r.get('status') == 'MATCH')
    mismatches = sum(1 for r in all_results if r.get('status') == 'MISMATCH')
    skipped = sum(1 for r in all_results if r.get('status') in ['SKIP', 'ERROR'])
    
    accuracy = round(matches / (total - skipped) * 100, 2) if (total - skipped) > 0 else 0
    
    return {
        'success': True,
        'results': all_results,
        'total_fields': total,
        'matches': matches,
        'mismatches': mismatches,
        'skipped': skipped,
        'accuracy': accuracy,
        'model': 'claude-opus-4-5 (Smart Validation)'
    }


if __name__ == "__main__":
    # Test
    doc_dir = "/Users/sunny/Applications/bts/jpmorgan/mortgage/modda/documents/loan_1642451"
    mt360_file = "/Users/sunny/Applications/bts/jpmorgan/mortgage/modda/outputs/mt360_complete_extraction/data/loan_1642451_URLA.json"
    
    with open(mt360_file) as f:
        mt360_data = json.load(f)
    
    result = smart_validate_urla(27, mt360_data, doc_dir)
    print(f"\n\nFinal: {result['accuracy']}% accuracy, {result['matches']} matches, {result['mismatches']} mismatches")

