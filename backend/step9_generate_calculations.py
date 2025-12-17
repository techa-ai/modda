#!/usr/bin/env python3
"""
Step 9: Generate Multi-Step Calculations with Document References

This script systematically generates calculation steps for all 1008 attributes
by asking Claude to analyze the evidence documents and create step-by-step
breakdowns with proper document and page references.

NO HARDCODING - All values come from Claude's analysis of source documents.
"""

import json
import sys
from db import execute_query, execute_one, get_db_connection
from vlm_utils import VLMClient


def get_1008_attributes(loan_id):
    """Get all 1008 attributes with their extracted values"""
    return execute_query("""
        SELECT 
            fa.id as attribute_id,
            fa.attribute_label,
            fa.section,
            ed.extracted_value
        FROM form_1008_attributes fa
        LEFT JOIN extracted_1008_data ed ON ed.attribute_id = fa.id AND ed.loan_id = %s
        WHERE ed.extracted_value IS NOT NULL 
        AND ed.extracted_value != ''
        AND ed.extracted_value != '0.00'
        ORDER BY fa.display_order
    """, (loan_id,))


def get_evidence_for_attribute(loan_id, attribute_id):
    """Get all evidence files for an attribute"""
    return execute_query("""
        SELECT 
            ef.id,
            ef.file_name,
            ef.notes,
            ef.verification_status,
            da.id as document_id,
            da.filename,
            da.page_count,
            da.vlm_analysis
        FROM evidence_files ef
        LEFT JOIN document_analysis da ON da.filename = ef.file_name AND da.loan_id = ef.loan_id
        WHERE ef.loan_id = %s AND ef.attribute_id = %s
        ORDER BY ef.id
    """, (loan_id, attribute_id))


def get_important_documents(loan_id):
    """Get all important financial documents with VLM analysis"""
    return execute_query("""
        SELECT 
            id,
            filename,
            page_count,
            vlm_analysis,
            version_metadata
        FROM document_analysis
        WHERE loan_id = %s
        AND status != 'duplicate'
        AND vlm_analysis IS NOT NULL
        AND (
            version_metadata->>'financial_category' = 'FINANCIAL'
            OR version_metadata->>'classification' = 'FINANCIAL'
            OR filename ILIKE '%%1008%%'
            OR filename ILIKE '%%credit%%'
            OR filename ILIKE '%%tax%%'
            OR filename ILIKE '%%purchase%%'
            OR filename ILIKE '%%appraisal%%'
            OR filename ILIKE '%%urla%%'
            OR filename ILIKE '%%insurance%%'
            OR filename ILIKE '%%note%%'
            OR filename ILIKE '%%loan_estimate%%'
        )
        ORDER BY filename
    """, (loan_id,))


def create_document_context(documents):
    """Create a summary of all documents for Claude context"""
    context = []
    for doc in documents:
        vlm = doc.get('vlm_analysis', {})
        
        # Get document summary if available
        summary = vlm.get('document_summary', {})
        if not summary:
            summary = vlm.get('summary', {})
        
        # Get key values from pages
        pages_summary = []
        pages = vlm.get('pages', [])
        for i, page in enumerate(pages, 1):
            if isinstance(page, dict):
                # Extract key-value pairs from page
                page_content = page.get('content', page)
                if isinstance(page_content, dict):
                    pages_summary.append({
                        'page': i,
                        'fields': list(page_content.keys())[:20]  # Limit fields shown
                    })
        
        context.append({
            'document_id': doc['id'],
            'filename': doc['filename'],
            'page_count': doc['page_count'],
            'document_type': doc.get('version_metadata', {}).get('doc_type', 'Unknown'),
            'summary': summary,
            'pages': pages_summary[:5]  # Limit pages shown
        })
    
    return context


def generate_calculation_for_attribute(client, loan_id, attribute, documents_context, evidence):
    """Use Claude to generate calculation steps for a single attribute"""
    
    # Build evidence context
    evidence_notes = []
    for ev in evidence:
        if ev.get('notes'):
            try:
                notes = json.loads(ev['notes']) if isinstance(ev['notes'], str) else ev['notes']
                evidence_notes.append({
                    'filename': ev['filename'],
                    'document_id': ev['document_id'],
                    'notes': notes
                })
            except:
                pass
    
    # Prepare context data
    context_data = f"""ATTRIBUTE: {attribute['attribute_label']}
EXTRACTED VALUE FROM 1008: {attribute['extracted_value']}
SECTION: {attribute['section']}

AVAILABLE DOCUMENTS:
{json.dumps(documents_context, indent=2)}

EXISTING EVIDENCE NOTES:
{json.dumps(evidence_notes, indent=2)}"""

    prompt = """Create a step-by-step calculation showing how the 1008 value was derived.
For EACH step, you MUST provide:
1. description - What this step represents
2. value - The numeric value for this step
3. document_id - The ID of the source document (from AVAILABLE DOCUMENTS above)
4. document_name - The filename of the source document
5. page_number - The page number where this value is found (if known)
6. rationale - Brief explanation of why this value is used
7. is_calculated - true if this is a calculated/derived value, false if from a document

RULES:
- For simple attributes (single value from one document), create 1 step
- For calculated attributes (sum, multiplication, etc.), show each component
- The FINAL step's value must match the 1008 extracted value
- ONLY use documents from AVAILABLE DOCUMENTS - no made-up references
- If a value is calculated (not from a document), set document_id to null
- Be precise with document references - use exact document_id and filename

Respond with ONLY a JSON array of steps, no other text:
[
  {
    "step_order": 1,
    "description": "...",
    "value": "...",
    "document_id": <number or null>,
    "document_name": "..." or null,
    "page_number": <number or null>,
    "rationale": "...",
    "is_calculated": false
  },
  ...
]
"""

    try:
        response = client.process_text(context_data, prompt, return_json=False)
        
        if response is None:
            print(f"    No response from Claude")
            return None
        
        # Parse JSON response
        response_text = response.strip() if isinstance(response, str) else str(response)
        
        # Handle markdown code blocks
        if '```json' in response_text:
            response_text = response_text.split('```json')[1].split('```')[0].strip()
        elif '```' in response_text:
            response_text = response_text.split('```')[1].split('```')[0].strip()
        
        steps = json.loads(response_text)
        return steps
        
    except json.JSONDecodeError as e:
        print(f"    Error parsing Claude response: {e}")
        return None
    except Exception as e:
        print(f"    Error calling Claude: {e}")
        return None


def save_calculation_steps(loan_id, attribute_id, steps):
    """Save calculation steps to database"""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        
        # Delete existing steps
        cur.execute(
            "DELETE FROM calculation_steps WHERE loan_id = %s AND attribute_id = %s",
            (loan_id, attribute_id)
        )
        
        # Insert new steps
        for step in steps:
            cur.execute("""
                INSERT INTO calculation_steps 
                (loan_id, attribute_id, step_order, description, value,
                 document_id, document_name, page_number, rationale, is_calculated)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                loan_id,
                attribute_id,
                step.get('step_order', 1),
                step.get('description', ''),
                step.get('value', ''),
                step.get('document_id'),
                step.get('document_name'),
                step.get('page_number'),
                step.get('rationale', ''),
                step.get('is_calculated', False)
            ))
        
        conn.commit()
        return True
        
    except Exception as e:
        conn.rollback()
        print(f"    Error saving steps: {e}")
        return False
    finally:
        cur.close()
        conn.close()


def generate_all_calculations(loan_id, force=False):
    """Generate calculation steps for all 1008 attributes"""
    print(f"\n{'='*60}")
    print(f"Step 9: Generate Calculations for Loan {loan_id}")
    print(f"{'='*60}\n")
    
    # Initialize Claude client
    client = VLMClient()
    
    # Get all 1008 attributes with values
    attributes = get_1008_attributes(loan_id)
    print(f"Found {len(attributes)} 1008 attributes with extracted values\n")
    
    # Get all important documents
    documents = get_important_documents(loan_id)
    print(f"Found {len(documents)} important documents for reference\n")
    
    # Create document context for Claude
    documents_context = create_document_context(documents)
    
    # Process each attribute
    success_count = 0
    error_count = 0
    skipped_count = 0
    
    for attr in attributes:
        attr_id = attr['attribute_id']
        attr_label = attr['attribute_label']
        
        print(f"Processing: {attr_label}")
        print(f"  1008 Value: {attr['extracted_value']}")
        
        # Check if already has calculation steps (unless force)
        if not force:
            existing = execute_one(
                "SELECT COUNT(*) as cnt FROM calculation_steps WHERE loan_id = %s AND attribute_id = %s",
                (loan_id, attr_id)
            )
            if existing and existing['cnt'] > 1:
                print(f"  ⏭️  Skipped (already has {existing['cnt']} steps)")
                skipped_count += 1
                continue
        
        # Get evidence for this attribute
        evidence = get_evidence_for_attribute(loan_id, attr_id)
        print(f"  Found {len(evidence)} evidence files")
        
        # Generate calculation steps using Claude
        steps = generate_calculation_for_attribute(
            client, loan_id, attr, documents_context, evidence
        )
        
        if steps and len(steps) > 0:
            # Save to database
            if save_calculation_steps(loan_id, attr_id, steps):
                print(f"  ✅ Generated {len(steps)} steps")
                success_count += 1
            else:
                print(f"  ❌ Failed to save steps")
                error_count += 1
        else:
            print(f"  ❌ Failed to generate steps")
            error_count += 1
        
        print()
    
    # Summary
    print(f"\n{'='*60}")
    print("Summary:")
    print(f"  ✅ Success: {success_count}")
    print(f"  ⏭️  Skipped: {skipped_count}")
    print(f"  ❌ Errors: {error_count}")
    print(f"{'='*60}\n")
    
    return error_count == 0


def regenerate_single_attribute(loan_id, attribute_label):
    """Regenerate calculation steps for a single attribute"""
    print(f"\nRegenerating calculations for: {attribute_label}\n")
    
    # Get attribute
    attr = execute_one("""
        SELECT 
            fa.id as attribute_id,
            fa.attribute_label,
            fa.section,
            ed.extracted_value
        FROM form_1008_attributes fa
        LEFT JOIN extracted_1008_data ed ON ed.attribute_id = fa.id AND ed.loan_id = %s
        WHERE fa.attribute_label = %s
    """, (loan_id, attribute_label))
    
    if not attr:
        print(f"Attribute not found: {attribute_label}")
        return False
    
    # Initialize Claude client
    client = VLMClient()
    
    # Get documents and evidence
    documents = get_important_documents(loan_id)
    documents_context = create_document_context(documents)
    evidence = get_evidence_for_attribute(loan_id, attr['attribute_id'])
    
    # Generate steps
    steps = generate_calculation_for_attribute(
        client, loan_id, attr, documents_context, evidence
    )
    
    if steps and len(steps) > 0:
        if save_calculation_steps(loan_id, attr['attribute_id'], steps):
            print(f"✅ Generated {len(steps)} steps for {attribute_label}")
            for i, step in enumerate(steps, 1):
                print(f"  Step {i}: {step.get('description')} = {step.get('value')}")
                if step.get('document_name'):
                    print(f"           Source: {step['document_name']} (Page {step.get('page_number', 'N/A')})")
            return True
    
    print(f"❌ Failed to generate steps for {attribute_label}")
    return False


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python step9_generate_calculations.py <loan_id>")
        print("  python step9_generate_calculations.py <loan_id> --force")
        print("  python step9_generate_calculations.py <loan_id> --attribute 'Attribute Label'")
        sys.exit(1)
    
    loan_id = int(sys.argv[1])
    
    if '--attribute' in sys.argv:
        idx = sys.argv.index('--attribute')
        attr_label = sys.argv[idx + 1]
        regenerate_single_attribute(loan_id, attr_label)
    else:
        force = '--force' in sys.argv
        generate_all_calculations(loan_id, force)

