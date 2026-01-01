#!/usr/bin/env python3
"""
Step 7: Reclassify Documents with Improved Categories

Updates document classification with:
1. document_purpose: EVIDENTIARY, COMPLIANCE, ADMINISTRATIVE
   - EVIDENTIARY: Documents that prove/justify income, debt, expenses, credit, value
   - COMPLIANCE: Forms ensuring regulatory compliance (disclosures, authorizations)
   - ADMINISTRATIVE: Other operational documents

2. process_stage: ORIGINATION, UNDERWRITING, CLOSING, POST_CLOSING
   - ORIGINATION: Loan application, initial docs
   - UNDERWRITING: Verification, analysis docs
   - CLOSING: Final loan docs, signatures
   - POST_CLOSING: Recording, servicing docs
"""

import json
import sys
from db import execute_query, get_db_connection
from vlm_utils import VLMClient

SCHEMA = "modda_v2"
BATCH_SIZE = 10  # Reduced for full JSON payload


def get_documents_for_reclassification(loan_id):
    """Get documents needing reclassification with FULL individual_analysis"""
    query = """
    SELECT id, filename, 
           individual_analysis as full_analysis,
           page_count,
           version_metadata
    FROM """ + SCHEMA + """.document_analysis
    WHERE loan_id = %s
      AND (page_count <= 20 OR page_count IS NULL)
    ORDER BY filename
    """
    return execute_query(query, (loan_id,))


def classify_batch(docs, batch_num, total_batches):
    """Reclassify a batch of documents using Claude with FULL individual_analysis"""
    
    print(f"  📤 Sending batch {batch_num}/{total_batches} ({len(docs)} docs) to Claude...")
    
    # Prepare payload with FULL analysis
    payload = []
    for doc in docs:
        full_analysis = doc.get('full_analysis') or {}
        if isinstance(full_analysis, str):
            try:
                full_analysis = json.loads(full_analysis)
            except:
                full_analysis = {}
        
        # Get existing metadata
        meta = doc.get('version_metadata') or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except:
                meta = {}
        
        payload.append({
            "id": doc['id'],
            "name": doc['filename'],
            "page_count": doc.get('page_count', 0),
            "current_doc_type": meta.get('doc_type', 'Unknown'),
            "full_analysis": full_analysis  # Send complete page-by-page analysis
        })
    
    prompt = """You are a senior mortgage underwriter analyzing loan documents.

CRITICAL RULES (MUST FOLLOW):
1. Promissory Notes (including Second Lien Notes, Mortgage Notes) = ALWAYS EVIDENTIARY_FINANCIAL (they prove debt obligation)
2. Deed of Trust / Mortgage Deed = ALWAYS EVIDENTIARY_FINANCIAL (they secure the debt)
3. Compliance Reports (Mavent, regulatory compliance) = ALWAYS COMPLIANCE  
4. Insurance PREMIUM/COST documents (showing actual $ premium expense) = EVIDENTIARY_FINANCIAL
5. Insurance COVERAGE documents (policy declarations, coverage limits, reconstruction cost estimates) = EVIDENTIARY_NON_FINANCIAL (property status)
6. Flood Notices, Flood Zone Determinations, Flood Certificates = EVIDENTIARY_NON_FINANCIAL (property status)
7. Corporate Registration, Business Entity docs = OPERATIONAL (not financial evidence)
8. Verbal VOE alone = EVIDENTIARY_FINANCIAL, but misc docs with corp registration = OPERATIONAL

TASK: For EACH document, classify it into the following categories:

## 1. document_purpose (Choose ONE):

**EVIDENTIARY_FINANCIAL** - Documents that PROVE FINANCIAL facts (money, income, debts, credit):
- Income: Tax Returns (1040, 1120S, W-2, 1099, K-1), Paystubs, Employment Verification Letters
- Assets: Bank Statements, Investment Account Statements, Retirement Statements
- Debt/Liabilities: Credit Reports (with scores), Mortgage Statements, Loan Payoff Letters
- Credit: Credit Reports with FICO scores
- **LEGAL DEBT INSTRUMENTS**: Promissory Notes, Second Lien Notes, Mortgage Notes - ALWAYS classify as EVIDENTIARY_FINANCIAL
- Expenses/Costs: Insurance documents showing Premium Amounts (Hazard Insurance with costs)

**EVIDENTIARY_NON_FINANCIAL** - Documents that PROVE NON-FINANCIAL property/status facts:
- Property Value: Appraisal Reports (Form 1004), AVM Reports
- Property Condition: Property Condition Reports, Property Inspections, Property Detail Reports
- Property Status: Title Reports, Flood Zone Determinations, Survey Reports  
- Insurance Coverage (without financial amounts): Policy declarations showing coverage only

**COMPLIANCE** - Forms for REGULATORY compliance (disclosures, authorizations, notices, reports):
- **COMPLIANCE REPORTS**: Mavent Compliance Reports, Regulatory Compliance Reports - ALWAYS COMPLIANCE
- Authorization/Consent forms (4506-C IVES Request, Borrower Authorizations, Taxpayer Consent)
- Disclosure forms (TILA, RESPA, Loan Estimates, Closing Disclosures, Right to Cancel)
- Notice forms (Flood zone notices, Rate lock notices, Appraisal notices)
- Anti-coercion statements, Privacy notices, Acknowledgements

**APPLICATION_FORMS** - Loan application and transmittal documents:
- Uniform Residential Loan Application (URLA/Form 1003)
- Lender Loan Information forms
- Form 1008 Transmittal Summary
- Form 1103 Supplementary Consumer Information Form

**OPERATIONAL** - Internal processing and calculation documents:
- Fee worksheets, Itemization of Fees
- Payment schedules, Payoff schedules
- Tax workup sheets, Income calculations
- Tracking reports, Checklists

## 2. process_stage (Choose ONE):
- ORIGINATION: Loan application, initial disclosures, rate locks
- UNDERWRITING: Verification docs, credit reports, appraisals, 4506 requests
- CLOSING: Closing Disclosure, Note, Deed of Trust, final disclosures
- POST_CLOSING: Recording, servicing transfers

## 3. evidentiary_type (Only if EVIDENTIARY_FINANCIAL or EVIDENTIARY_NON_FINANCIAL):
For Financial: income, assets, debt, credit_score
For Non-Financial: property_value, property_condition, property_status, insurance

## 4. doc_type_specific - PROVIDE A SPECIFIC DOCUMENT NAME:
Be VERY specific. Examples:
- "IRS Form 4506-C IVES Request for Transcript"
- "Federal Tax Return Form 1040"
- "Property Condition Report (PCR)"
- "FEMA Standard Flood Hazard Determination Form"
- "Hazard Insurance Policy Declaration Page"

OUTPUT FORMAT (strict JSON):
{
  "results": [
    {
      "id": <doc_id>,
      "document_purpose": "EVIDENTIARY_FINANCIAL" | "EVIDENTIARY_NON_FINANCIAL" | "COMPLIANCE" | "APPLICATION_FORMS" | "OPERATIONAL",
      "process_stage": "ORIGINATION" | "UNDERWRITING" | "CLOSING" | "POST_CLOSING",
      "evidentiary_type": "income" | "assets" | "debt" | "credit_score" | "property_value" | "property_condition" | "property_status" | "insurance" | null,
      "doc_type_specific": "Specific document name",
      "purpose_reason": "Brief explanation"
    }
  ]
}

EXAMPLES:
- Tax Return → EVIDENTIARY_FINANCIAL, evidentiary_type: income
- Bank Statement → EVIDENTIARY_FINANCIAL, evidentiary_type: assets
- Credit Report → EVIDENTIARY_FINANCIAL, evidentiary_type: credit_score
- Promissory Note → EVIDENTIARY_FINANCIAL, evidentiary_type: debt
- Mortgage/Deed of Trust → EVIDENTIARY_FINANCIAL, evidentiary_type: debt
- Appraisal Report → EVIDENTIARY_NON_FINANCIAL, evidentiary_type: property_value
- Property Condition Report → EVIDENTIARY_NON_FINANCIAL, evidentiary_type: property_condition
- Flood Zone Determination → EVIDENTIARY_NON_FINANCIAL, evidentiary_type: property_status
- Hazard Insurance Policy → EVIDENTIARY_NON_FINANCIAL, evidentiary_type: insurance
- 4506-C Request → COMPLIANCE
- Closing Disclosure → COMPLIANCE
- Form 1008 Transmittal → APPLICATION_FORMS
- URLA/Form 1003 → APPLICATION_FORMS
- Fee Worksheet → OPERATIONAL
- Payment Schedule → OPERATIONAL
- Tax Workup Sheet → OPERATIONAL

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
    """Save reclassification results to database"""
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    for res in results:
        doc_id = res.get('id')
        if not doc_id:
            continue
        
        # Build metadata update
        meta_update = {
            "document_purpose": res.get("document_purpose"),
            "process_stage": res.get("process_stage"),
            "evidentiary_type": res.get("evidentiary_type"),
            "purpose_reason": res.get("purpose_reason"),
            "doc_type": res.get("doc_type_specific")  # Update doc_type with more specific name
        }
        
        # Update version_metadata (merge with existing)
        cur.execute(f"""
            UPDATE {SCHEMA}.document_analysis
            SET version_metadata = COALESCE(version_metadata, '{{}}'::jsonb) || %s::jsonb
            WHERE id = %s
        """, (json.dumps(meta_update), doc_id))
    
    conn.commit()
    cur.close()
    conn.close()
    
    return len(results)


def reclassify_loan(loan_id):
    """Run reclassification for a loan"""
    
    print(f"\n{'='*60}")
    print(f"🏷️  DOCUMENT RECLASSIFICATION - Loan {loan_id}")
    print(f"    Schema: {SCHEMA}")
    print(f"{'='*60}")
    
    # Get documents
    docs = get_documents_for_reclassification(loan_id)
    print(f"📄 Documents for reclassification: {len(docs)}")
    
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
    print(f"\n📊 Reclassification Complete!")
    print(f"   Total reclassified: {saved}")
    
    # Get purpose breakdown
    breakdown = execute_query(f"""
        SELECT 
            version_metadata->>'document_purpose' as purpose,
            COUNT(*) as cnt
        FROM {SCHEMA}.document_analysis
        WHERE loan_id = %s
          AND version_metadata->>'document_purpose' IS NOT NULL
        GROUP BY version_metadata->>'document_purpose'
        ORDER BY cnt DESC
    """, (loan_id,))
    
    if breakdown:
        print(f"\n   📂 Document Purpose:")
        for row in breakdown:
            emoji = "📋" if row['purpose'] == 'EVIDENTIARY' else "📑" if row['purpose'] == 'COMPLIANCE' else "📁"
            print(f"      {emoji} {row['purpose']}: {row['cnt']}")
    
    # Get stage breakdown
    stage_breakdown = execute_query(f"""
        SELECT 
            version_metadata->>'process_stage' as stage,
            COUNT(*) as cnt
        FROM {SCHEMA}.document_analysis
        WHERE loan_id = %s
          AND version_metadata->>'process_stage' IS NOT NULL
        GROUP BY version_metadata->>'process_stage'
        ORDER BY cnt DESC
    """, (loan_id,))
    
    if stage_breakdown:
        print(f"\n   🔄 Process Stage:")
        for row in stage_breakdown:
            print(f"      {row['stage']}: {row['cnt']}")
    
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
            reclassify_loan(loan['id'])
    else:
        reclassify_loan(args.loan_id)


if __name__ == "__main__":
    main()
