#!/usr/bin/env python3
"""
Enhanced Global Classification for V2 Schema

Takes the existing step6_global_classification approach and:
1. Works on modda_v2 schema
2. Adds document_category (income, debt, credit_score, loan_valuation, disclosure, admin)
3. Preserves all existing metadata fields
4. Skip large documents (>40 pages) to avoid token limits
"""

import json
import sys
import os
from db import execute_query, get_db_connection
from vlm_utils import VLMClient

SCHEMA = "modda_v2"
MAX_PAGES = 40
BATCH_SIZE = 75  # Process in batches to avoid token limits


def get_documents_for_classification(loan_id):
    """Get documents needing classification"""
    query = """
    SELECT id, filename, 
           individual_analysis->'document_summary' as document_summary,
           detected_date, file_size, page_count
    FROM """ + SCHEMA + """.document_analysis
    WHERE loan_id = %s
      AND (page_count <= %s OR page_count IS NULL)
    ORDER BY filename
    """
    return execute_query(query, (loan_id, MAX_PAGES))


def classify_batch(docs, batch_num, total_batches):
    """Classify a batch of documents using Claude"""
    
    print(f"  📤 Sending batch {batch_num}/{total_batches} ({len(docs)} docs) to Claude...")
    
    # Prepare payload
    payload = []
    for doc in docs:
        summary = doc.get('document_summary') or {}
        payload.append({
            "id": doc['id'],
            "name": doc['filename'],
            "date": str(doc['detected_date']) if doc['detected_date'] else "Unknown",
            "page_count": doc.get('page_count') or 1,
            "extracted_data": summary
        })
    
    prompt = """You are a senior mortgage underwriter analyzing loan documents.

TASK: For EACH document, determine ALL of the following:

1. **classification**: "FINANCIAL" (Income, Assets, Credit, Loan Terms) or "NON-FINANCIAL" (Admin, Disclosures, Legal)

2. **document_category**: Choose ONE:
   - "income" (W-2, Paystubs, Tax Returns, Employment Letters, 1099s)
   - "assets" (Bank Statements, Investment Accounts, Retirement Accounts)
   - "debt" (Credit Report, Liability Statements, Existing Mortgages)
   - "credit_score" (Credit Reports with FICO scores)
   - "loan_valuation" (Appraisals, 1004, AVM Reports, Property Inspections)
   - "loan_terms" (1008 Transmittal, Loan Estimate, Closing Disclosure, Note, Deed)
   - "identity" (Driver's License, SSN Verification, IDs)
   - "insurance" (HOI, Title Insurance, PMI, Flood Insurance)
   - "disclosure" (Disclosures, Notices, Acknowledgements, Authorizations)
   - "compliance" (TILA, RESPA, Flood Zone, Anti-Coercion)
   - "other" (Miscellaneous documents)

3. **doc_type**: Standard Industry Name. Examples:
   - "URLA 1003", "Form 1008 Transmittal", "Closing Disclosure", "Loan Estimate"
   - "W-2 (2024)", "W-2 (2023)", "Paystub", "Employment Verification Letter"
   - "Bank Statement", "Tax Return (1040)", "Credit Report"
   - "Appraisal (Form 1004)", "AVM Report", "Property Inspection"
   - "Right to Cancel Notice", "TILA Disclosure", "Borrower Authorization"

4. **signed_status**: "SIGNED" or "UNSIGNED" (look for signatures, dates, or explicit "signed" in filename/content)

5. **version_type**: "FINAL", "PRELIMINARY", or "UNKNOWN" (check filename for "final", "preliminary", "draft")

6. **group_id**: Assign related documents the SAME group_id (e.g., all W-2 forms together, all versions of same doc together). Use format like "G001", "G002", etc.

7. **is_primary**: true if this is the BEST/LATEST/SIGNED version in its group, false otherwise

8. **primary_reason**: If is_primary=true, explain why (e.g., "Latest signed version", "Final version")

OUTPUT FORMAT (strict JSON):
{
  "results": [
    {
      "id": <doc_id>,
      "classification": "FINANCIAL" | "NON-FINANCIAL",
      "document_category": "income" | "assets" | "debt" | "credit_score" | "loan_valuation" | "loan_terms" | "identity" | "insurance" | "disclosure" | "compliance" | "other",
      "doc_type": "Standard Name",
      "signed_status": "SIGNED" | "UNSIGNED",
      "version_type": "FINAL" | "PRELIMINARY" | "UNKNOWN",
      "group_id": "G001",
      "group_description": "Human readable group name",
      "is_primary": true | false,
      "primary_reason": "Reason if primary"
    }
  ]
}

RULES:
- Every document MUST appear in results
- Be specific with doc_type (include year for tax docs)
- Group ALL versions/variants of the same document together
- Credit Reports belong to BOTH "debt" and "credit_score" - pick "credit_score" if FICO visible

DOCUMENTS TO ANALYZE:
"""
    
    client = VLMClient(max_tokens=30000)
    
    try:
        response = client.process_text(
            text=json.dumps(payload, default=str),
            prompt=prompt,
            return_json=True
        )
    except Exception as e:
        print(f"  ❌ Error calling VLM: {e}")
        return []
    
    # Parse response
    if isinstance(response, str):
        cleaned = response.replace("```json", "").replace("```", "").strip()
        try:
            response = json.loads(cleaned)
        except:
            try:
                start = cleaned.find('{')
                end = cleaned.rfind('}') + 1
                if start >= 0 and end > start:
                    response = json.loads(cleaned[start:end])
                else:
                    return []
            except:
                return []
    
    if not response or not isinstance(response, dict) or 'results' not in response:
        print(f"  ⚠️ Invalid response from VLM")
        return []
    
    return response['results']


def save_classification_results(loan_id, results):
    """Save classification results to database"""
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    for res in results:
        doc_id = res.get('id')
        if not doc_id:
            continue
        
        # Build metadata update
        meta_update = {
            "financial_category": res.get("classification"),
            "document_category": res.get("document_category"),
            "doc_type": res.get("doc_type"),
            "signed_status": res.get("signed_status"),
            "version_type": res.get("version_type"),
            "ai_group_id": res.get("group_id"),
            "ai_group_description": res.get("group_description"),
            "is_primary": res.get("is_primary"),
            "primary_reason": res.get("primary_reason")
        }
        
        # Update version_metadata (merge with existing)
        cur.execute(f"""
            UPDATE {SCHEMA}.document_analysis
            SET version_metadata = COALESCE(version_metadata, '{{}}'::jsonb) || %s::jsonb
            WHERE id = %s
        """, (json.dumps(meta_update), doc_id))
        
        # Also update status based on is_primary and grouping
        is_primary = res.get("is_primary", False)
        group_id = res.get("group_id")
        
        # Determine status
        if is_primary:
            status = 'unique'  # Will update to master if has duplicates
        else:
            status = 'superseded'  # Non-primary in a group
        
        cur.execute(f"""
            UPDATE {SCHEMA}.document_analysis
            SET version_group_id = %s,
                is_latest_version = %s,
                status = CASE 
                    WHEN status = 'duplicate' THEN status  -- Keep duplicate status
                    ELSE %s
                END
            WHERE id = %s
        """, (group_id, is_primary, status, doc_id))
    
    conn.commit()
    cur.close()
    conn.close()
    
    return len(results)


def classify_loan(loan_id):
    """Run full classification for a loan"""
    
    print(f"\n{'='*60}")
    print(f"🏷️  ENHANCED CLASSIFICATION - Loan {loan_id}")
    print(f"    Schema: {SCHEMA}")
    print(f"{'='*60}")
    
    # Get documents
    docs = get_documents_for_classification(loan_id)
    print(f"📄 Documents for classification: {len(docs)}")
    
    if not docs:
        print("❌ No documents found")
        return
    
    # Process in batches
    all_results = []
    total_batches = (len(docs) + BATCH_SIZE - 1) // BATCH_SIZE
    
    for i in range(0, len(docs), BATCH_SIZE):
        batch = docs[i:i+BATCH_SIZE]
        batch_num = (i // BATCH_SIZE) + 1
        
        results = classify_batch(batch, batch_num, total_batches)
        all_results.extend(results)
        
        print(f"  ✅ Received {len(results)} classifications")
    
    # Save results
    saved = save_classification_results(loan_id, all_results)
    
    # Show summary
    print(f"\n📊 Classification Complete!")
    print(f"   Total classified: {saved}")
    
    # Get category breakdown
    breakdown = execute_query(f"""
        SELECT 
            version_metadata->>'document_category' as category,
            COUNT(*) as cnt
        FROM {SCHEMA}.document_analysis
        WHERE loan_id = %s
          AND version_metadata->>'document_category' IS NOT NULL
        GROUP BY version_metadata->>'document_category'
        ORDER BY cnt DESC
    """, (loan_id,))
    
    if breakdown:
        print(f"\n   📂 Categories:")
        for row in breakdown:
            print(f"      {row['category']}: {row['cnt']}")
    
    print(f"{'='*60}\n")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("loan_id", type=int, nargs='?')
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    
    if args.all or args.loan_id is None:
        loans = execute_query("SELECT id FROM loans ORDER BY id")
        for loan in loans:
            classify_loan(loan['id'])
    else:
        classify_loan(args.loan_id)


if __name__ == "__main__":
    main()
