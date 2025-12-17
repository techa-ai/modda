"""
Systematic Evidence Generation - V5 Standardized
================================================
This version implements the standardized verification process that delivers:
1. Detailed calculation steps with exact page references
2. Comprehensive verification summary with document links
3. Proper income inclusion/exclusion analysis
4. Compliance with underwriting guidelines
5. Full audit trail with clickable document badges

This is the GOLD STANDARD based on the manual verification of attribute 319.
"""

import json
import os
from datetime import datetime

from db import get_db_connection
from bedrock_config import call_bedrock

# Override default - Opus 4.5 required for quality evidence generation
DEFAULT_MODEL = 'claude-opus-4-5'
from datetime import datetime

MAX_DOC_CHARS_DEFAULT = 8_000  # per-document truncation to fit context window
MAX_TOTAL_CONTEXT_CHARS_DEFAULT = 2_000_000  # overall context cap for Opus 4.5

def get_deep_json_for_document(document_name):
    """Load deep JSON extraction for a document if available"""
    base_name = document_name.replace('.pdf', '')
    deep_json_path = f'/Users/sunny/Applications/bts/jpmorgan/mortgage/modda/outputs/deep_json/{base_name}_deep.json'
    
    if os.path.exists(deep_json_path):
        with open(deep_json_path, 'r') as f:
            return json.load(f)
    return None

def get_pagewise_json_for_document(document_name):
    """Load pagewise JSON extraction for a document if available"""
    base_name = document_name.replace('.pdf', '')
    pagewise_path = f'/Users/sunny/Applications/bts/jpmorgan/mortgage/modda/outputs/ocr/{base_name}/pagewise_extraction.json'
    
    if os.path.exists(pagewise_path):
        with open(pagewise_path, 'r') as f:
            return json.load(f)
    return None

def get_borrower_datastore(document_name):
    """Load borrower-specific datastore if available"""
    base_name = document_name.replace('.pdf', '')
    datastore_path = f'/Users/sunny/Applications/bts/jpmorgan/mortgage/modda/outputs/ocr/{base_name}/borrower_datastore.json'
    
    if os.path.exists(datastore_path):
        with open(datastore_path, 'r') as f:
            return json.load(f)
    return None

def _safe_json_dumps(obj) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, indent=2, default=str)
    except Exception:
        return json.dumps(str(obj), ensure_ascii=False)


def _extract_json_from_model_response(response_text: str) -> dict:
    """
    Extract JSON object from a Claude response that may include fenced code blocks.
    """
    text = (response_text or "").strip()
    if not text:
        raise ValueError("Empty model response")

    if "```json" in text:
        candidate = text.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in text:
        candidate = text.split("```", 1)[1].split("```", 1)[0].strip()
    else:
        # fallback: take first {...} block
        start = text.find("{")
        end = text.rfind("}") + 1
        candidate = text[start:end] if start != -1 and end != -1 else text

    return json.loads(candidate)


def load_all_extracted_1008_values(loan_id: int) -> list[dict]:
    """
    Load extracted 1008 values for context (all attributes for the loan).
    """
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT
                ed.attribute_id,
                fa.attribute_label,
                fa.section,
                ed.extracted_value,
                ed.document_path
            FROM extracted_1008_data ed
            JOIN form_1008_attributes fa ON fa.id = ed.attribute_id
            WHERE ed.loan_id = %s
            ORDER BY fa.display_order
            """,
            (loan_id,),
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        cur.close()
        conn.close()


def load_document_analysis_context(loan_id: int, max_docs: int = 100) -> list[dict]:
    """
    Load document_analysis rows (deep/pagewise JSON already stored) for the loan.
    We keep it bounded: include key metadata + truncated analysis JSON.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT
                filename,
                version_metadata,
                individual_analysis
            FROM document_analysis
            WHERE loan_id = %s
            ORDER BY filename
            """,
            (loan_id,),
        )
        rows = cur.fetchall()

        # Use financial_category tag from version_metadata
        selected = []
        
        for r in rows:
            fn = (r.get("filename") or "").lower()
            md = r.get("version_metadata") or {}
            
            # Skip 1008 - it's what we're VERIFYING, NOT evidence!
            if "1008" in fn:
                continue
            
            # Skip tax returns - only needed for income attributes
            if "tax_return" in fn:
                continue
            
            # Skip URLA and lender_loan_information - also what we're verifying
            if "urla" in fn or "lender_loan_information" in fn:
                continue
            
            # ONLY include FINANCIAL docs (tagged in version_metadata)
            if md.get("financial_category") == "FINANCIAL":
                selected.append(r)

        # Limit to max_docs
        selected = selected[:max_docs]
        out = []
        for r in selected:
            md = r.get("version_metadata")
            analysis = r.get("individual_analysis")
            analysis_str = _safe_json_dumps(analysis)
            if len(analysis_str) > MAX_DOC_CHARS_DEFAULT:
                analysis_str = analysis_str[:MAX_DOC_CHARS_DEFAULT] + "\n...[truncated]..."
            out.append(
                {
                    "filename": r.get("filename"),
                    "version_metadata": md,
                    "individual_analysis_truncated": analysis_str,
                }
            )
        return out
    finally:
        cur.close()
        conn.close()


def generate_systematic_evidence(
    loan_id: int,
    attribute_id: int,
    attribute_name: str,
    attribute_value: str,
    model: str = DEFAULT_MODEL,
):
    """
    Generate systematic evidence using Claude Opus 4.5 with standardized prompting.
    
    This is the GOLD STANDARD process that delivers:
    - Step-by-step calculations with exact page numbers
    - Comprehensive verification summary
    - Income inclusion/exclusion analysis
    - Compliance verification
    """
    
    print(f"\n{'='*80}")
    print(f"🔍 Generating Systematic Evidence")
    print(f"{'='*80}")
    print(f"Attribute: {attribute_name}")
    print(f"Expected Value: {attribute_value}")
    print(f"{'='*80}\n")
    
    # ❌ DO NOT SEND ALL 1008 DATA! It's what we're VERIFYING, not evidence!
    # Claude should build calculations ONLY from document JSONs (deep extractions)
    # We only tell Claude the TARGET attribute and expected value
    
    # Load ONLY the target attribute info (for context, NOT as evidence)
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT
                ed.attribute_id,
                fa.attribute_label,
                fa.section,
                ed.extracted_value
            FROM extracted_1008_data ed
            JOIN form_1008_attributes fa ON fa.id = ed.attribute_id
            WHERE ed.loan_id = %s AND fa.attribute_label = %s
            LIMIT 1
            """,
            (loan_id, attribute_name),
        )
        target_attr = cur.fetchone()
    finally:
        cur.close()
        conn.close()
    
    target_context = {
        "attribute_id": attribute_id,
        "attribute_name": attribute_name,
        "expected_value": attribute_value,
        "section": target_attr.get("section") if target_attr else None
    }
    
    # Load related 1008 breakdown fields for composite attributes
    breakdown_fields = []
    if "housing expense" in attribute_name.lower() or "total" in attribute_name.lower():
        conn2 = get_db_connection()
        cur2 = conn2.cursor()
        try:
            # Get housing expense component fields from 1008
            cur2.execute("""
                SELECT fa.attribute_label, ed.extracted_value
                FROM extracted_1008_data ed
                JOIN form_1008_attributes fa ON fa.id = ed.attribute_id
                WHERE ed.loan_id = %s
                AND fa.id IN (111, 112, 113, 114, 115, 116, 117, 329)
                ORDER BY fa.id
            """, (loan_id,))
            for row in cur2.fetchall():
                val = row['extracted_value']
                if val and str(val).strip() and str(val).strip() not in ['None', 'null', '']:
                    breakdown_fields.append({
                        "component": row['attribute_label'],
                        "value": str(val)
                    })
        finally:
            cur2.close()
            conn2.close()
    
    if breakdown_fields:
        target_context["breakdown_to_evidence"] = breakdown_fields
        print(f"  🎯 Target: {attribute_name} = {attribute_value}")
        print(f"  📑 Breakdown components to evidence: {len(breakdown_fields)}")
    else:
        print(f"  🎯 Target: {attribute_name} = {attribute_value}")
    
    doc_analysis = load_document_analysis_context(loan_id)
    print(f"  📄 Loaded {len(doc_analysis)} document JSONs as EVIDENCE sources")
    
    # Build the standardized prompt - GENERIC, NO HARDCODED VALUES
    prompt = f"""You are MODDA, a mortgage document verification system.

# TARGET TO VERIFY
{_safe_json_dumps(target_context)}

# DOCUMENT EVIDENCE (search these JSONs for proof)
{_safe_json_dumps(doc_analysis)}

# CRITICAL RULES

1. If "breakdown_to_evidence" is provided, find evidence for EACH component value EXACTLY
2. ONLY cite documents where you FOUND the exact value in the JSON above
3. If value not found in JSON → document_name: null, page_number: null
4. NEVER cite URLA, 1008, or lender_loan_information as evidence (that's what we're verifying)
5. Calculate P&I by adding Principal + Interest from mortgage statements
6. For each step, match the EXACT dollar amount from the breakdown

# OUTPUT FORMAT

Return JSON with this structure:
{{
  "calculation_steps": [
    {{
      "step_order": 1,
      "value": "<dollar amount found>",
      "description": "<short description under 50 chars>",
      "rationale": "<why included>",
      "formula": "<math formula if calculated>",
      "document_name": "<exact filename from JSON or null>",
      "page_number": <integer page from JSON or null>,
      "source_location": "<form/line reference>"
    }}
  ],
  "verification_summary": "<markdown summary with all values having (Page X, doc.pdf) references>",
  "evidence_files": [
    {{
      "file_name": "<doc name>",
      "classification": "primary|secondary",
      "page_number": null,
      "document_type": "<type>",
      "document_purpose": "<purpose>",
      "confidence_score": 0.95
    }}
  ],
  "verification_confidence": {{
    "overall_score": 0.95,
    "match_status": "EXACT_MATCH|PARTIAL_MATCH|NO_MATCH",
    "variance": 0.0,
    "notes": "<explanation>"
  }}
}}

Begin analysis. Search the document JSONs for values that sum to {attribute_value}."""

    # Token estimation before calling Claude
    prompt_chars = len(prompt)
    estimated_tokens = prompt_chars // 4  # rough estimate: 4 chars per token
    print(f"  📊 Prompt: {prompt_chars:,} chars (~{estimated_tokens:,} tokens)")
    
    if estimated_tokens > 180000:
        print(f"  ⚠️  WARNING: Prompt exceeds 180K tokens! May fail.")
    
    # Call Claude via Bedrock (repo standard)
    print(f"🤖 Calling Claude via Bedrock ({model})...")

    try:
        response_text = call_bedrock(
            prompt=prompt,
            model=model,
            max_tokens=12000,
            temperature=0.0,
        )

        # Save raw response for debugging
        debug_dir = '/Users/sunny/Applications/bts/jpmorgan/mortgage/modda/outputs/systematic_evidence'
        os.makedirs(debug_dir, exist_ok=True)
        debug_file = f'{debug_dir}/raw_response_{attribute_id}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt'
        with open(debug_file, 'w') as f:
            f.write(response_text)
        print(f"  💾 Saved raw response to: {debug_file}")

        result = _extract_json_from_model_response(response_text)
        
        print(f"✅ Generated {len(result.get('calculation_steps', []))} calculation steps")
        print(f"✅ Generated verification summary ({len(result.get('verification_summary', ''))} chars)")
        print(f"✅ Identified {len(result.get('evidence_files', []))} evidence files")
        
        return result
        
    except Exception as e:
        print(f"❌ Error calling Claude/Bedrock: {e}")
        return None


def save_evidence_to_database(loan_id, attribute_id, evidence_data):
    """Save the generated evidence to the database"""
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Clear existing data for this attribute
        cur.execute("DELETE FROM calculation_steps WHERE loan_id = %s AND attribute_id = %s", 
                   (loan_id, attribute_id))
        cur.execute("DELETE FROM evidence_files WHERE loan_id = %s AND attribute_id = %s", 
                   (loan_id, attribute_id))
        
        # Insert calculation steps
        steps = evidence_data.get('calculation_steps', [])
        for step in steps:
            cur.execute("""
                INSERT INTO calculation_steps 
                (loan_id, attribute_id, step_order, value, description, rationale, formula, 
                 document_name, page_number, source_location, is_calculated, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
            """, (
                loan_id, attribute_id,
                step.get('step_order'),
                step.get('value'),
                step.get('description'),
                step.get('rationale'),
                step.get('formula'),
                step.get('document_name'),
                step.get('page_number'),
                step.get('source_location'),
                False
            ))
        
        # Insert evidence files (and mark as verified for 1008 evidencing UI)
        evidence_files = evidence_data.get('evidence_files', [])
        for ev_file in evidence_files:
            # Build notes JSON
            notes = {
                'document_classification': ev_file.get('classification'),
                'document_type': ev_file.get('document_type'),
                'document_purpose': ev_file.get('document_purpose'),
                'verification_summary': evidence_data.get('verification_summary', '')
            }
            
            cur.execute("""
                INSERT INTO evidence_files
                (loan_id, attribute_id, file_name, file_path, page_number, notes, confidence_score, verification_status, uploaded_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
            """, (
                loan_id, attribute_id,
                ev_file.get('file_name'),
                f"documents/loan_{loan_id}/{ev_file.get('file_name')}",
                ev_file.get('page_number'),
                json.dumps(notes),
                ev_file.get('confidence_score', 0.95),
                'verified'
            ))
        
        conn.commit()
        print(f"\n✅ Saved {len(steps)} calculation steps to database")
        print(f"✅ Saved {len(evidence_files)} evidence files to database")
        
        return True
        
    except Exception as e:
        conn.rollback()
        print(f"\n❌ Error saving to database: {e}")
        return False
        
    finally:
        cur.close()
        conn.close()


def main():
    """Main execution function"""
    
    # Configuration
    LOAN_NUMBER = '1642451'
    
    # Get loan ID
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM loans WHERE loan_number = %s", (LOAN_NUMBER,))
    loan_result = cur.fetchone()
    
    if not loan_result:
        print(f"❌ Loan {LOAN_NUMBER} not found")
        return
    
    loan_id = loan_result['id']
    
    # Get a few 1008 attributes that have extracted values but no calculation_steps yet
    cur.execute(
        """
        SELECT
            fa.id as attribute_id,
            fa.attribute_label as label,
            ed.extracted_value as value
        FROM extracted_1008_data ed
        JOIN form_1008_attributes fa ON fa.id = ed.attribute_id
        WHERE ed.loan_id = %s
          AND ed.extracted_value IS NOT NULL
          AND ed.extracted_value != ''
          AND NOT EXISTS (
            SELECT 1 FROM calculation_steps cs
            WHERE cs.loan_id = ed.loan_id AND cs.attribute_id = ed.attribute_id
          )
        ORDER BY fa.display_order
        LIMIT 50
        """,
        (loan_id,),
    )
    
    attributes = cur.fetchall()
    cur.close()
    conn.close()
    
    if not attributes:
        print("✅ All attributes already have evidence generated!")
        print("💡 Tip: Delete calculation_steps for an attribute to regenerate")
        return
    
    print(f"\n📋 Found {len(attributes)} attributes without evidence:\n")
    for attr in attributes:
        print(f"   • {attr['label']}: {attr['value']}")
    
    # Process each attribute
    for attr in attributes:
        attribute_id = attr['attribute_id']
        attribute_name = attr['label']
        attribute_value = attr['value']
        
        # Generate evidence (Bedrock model can be overridden via env: SYSTEMATIC_BEDROCK_MODEL)
        model = os.environ.get("SYSTEMATIC_BEDROCK_MODEL", DEFAULT_MODEL)
        evidence_data = generate_systematic_evidence(
            loan_id=loan_id,
            attribute_id=attribute_id,
            attribute_name=attribute_name,
            attribute_value=attribute_value,
            model=model,
        )
        
        if evidence_data:
            # Save to database
            save_evidence_to_database(loan_id, attribute_id, evidence_data)
            
            # Save output for review
            output_dir = f'/Users/sunny/Applications/bts/jpmorgan/mortgage/modda/outputs/systematic_evidence'
            os.makedirs(output_dir, exist_ok=True)
            
            output_file = f'{output_dir}/attribute_{attribute_id}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
            with open(output_file, 'w') as f:
                json.dump(evidence_data, f, indent=2)
            
            print(f"📝 Saved output to: {output_file}\n")
        else:
            print(f"⚠️  Skipping attribute {attribute_id} due to error\n")


def get_knowledge_graph_context(*_args, **_kwargs):
    """
    Deprecated in V5 standardized:
    For 1008 evidencing we rely on extracted_1008_data + document_analysis context.
    Kept for backward compatibility with earlier experiments.
    """
    return {}


if __name__ == "__main__":
    main()

