#!/usr/bin/env python3
"""
Intelligent Document Examiner Agent
Learns from past loans to identify important documents for evidencing
"""

import json
from db import get_db_connection
from bedrock_config import call_bedrock

# Known important document types from experience (Loans 1, 30, 31)
KNOWN_IMPORTANT_DOCS = {
    "1008": "Transmittal Summary - contains all key loan attributes to verify",
    "urla": "Uniform Residential Loan Application (1003) - borrower info, income, assets",
    "appraisal": "Property valuation - required for LTV verification",
    "avm_report": "Automated Valuation Model - property value backup",
    "mortgage_loan_statement": "Existing mortgage details - critical for refinance/2nd liens",
    "promissory_note": "Loan terms, rate, payment amount - golden source",
    "note_2nd_lien": "Second lien note - payment terms for subordinate financing",
    "heloc_agreement": "HELOC terms - serves as promissory note for HELOCs",
    "hazard_insurance": "Property insurance - required escrow component",
    "flood_policy": "Flood insurance if applicable",
    "credit_report": "Credit history, existing debts, payment obligations",
    "pay_stub": "Current income verification",
    "w_2": "Annual wage verification",
    "tax_return": "Self-employment/complex income verification",
    "tax_workup": "Property tax details for escrow",
    "title_policy": "Property ownership verification",
    "purchase_agreement": "Purchase price, terms for purchase transactions",
    "closing_disclosure": "Final loan terms (use as backup, not primary)",
    "income_summary": "Underwriter's income calculation breakdown - KEY for income verification!",
    "voe": "Verification of Employment",
}


def get_loan_profile(loan_id: int) -> dict:
    """Extract loan profile from 1008 and URLA deep JSON"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    profile = {
        "loan_type": None,  # Purchase, Refinance, Cash-out Refinance
        "lien_position": None,  # First, Second
        "property_type": None,  # SFR, Condo, Multi-unit
        "occupancy": None,  # Primary, Investment, Second Home
        "income_types": [],  # W2, Self-Employed, Rental, etc.
        "loan_amount": None,
        "property_value": None,
        "ltv": None,
        "cltv": None,
        "dti": None,
        "credit_score": None,
        "borrower_name": None,
        "has_coborrower": False,
        "is_heloc": False,
        "is_second_lien": False,
        "has_rental_income": False,
        "has_self_employment": False,
    }
    
    try:
        # Get 1008 deep JSON
        cur.execute("""
            SELECT individual_analysis FROM document_analysis
            WHERE loan_id = %s AND filename LIKE '%%1008%%final%%'
            AND is_latest_version = TRUE
        """, (loan_id,))
        row = cur.fetchone()
        
        if row and row["individual_analysis"]:
            dj = row["individual_analysis"]
            # Extract from document_summary or pages
            summary = dj.get("document_summary", {})
            
            # Try to get key values
            important = summary.get("important_values", {})
            extracted = summary.get("extracted_data", {})
            
            # Look in pages for key_data
            for page in dj.get("pages", []):
                kd = page.get("key_data", {})
                
                # Loan type
                if "loan_purpose" in str(kd).lower():
                    purpose = kd.get("section_ii_mortgage_information", {}).get("loan_purpose", {})
                    if purpose.get("purchase"):
                        profile["loan_type"] = "Purchase"
                    elif purpose.get("cash_out_refinance"):
                        profile["loan_type"] = "Cash-Out Refinance"
                    elif purpose.get("no_cash_out_refinance_freddie") or purpose.get("limited_cash_out_refinance_fannie"):
                        profile["loan_type"] = "Rate/Term Refinance"
                
                # Lien position
                lien = kd.get("section_ii_mortgage_information", {}).get("lien_position", {})
                if lien.get("second_mortgage"):
                    profile["lien_position"] = "Second"
                    profile["is_second_lien"] = True
                elif lien.get("first_mortgage"):
                    profile["lien_position"] = "First"
                
                # Income info
                income = kd.get("section_iii_underwriting_information", {}).get("stable_monthly_income", {})
                if income:
                    if income.get("base_income", {}).get("borrower"):
                        profile["income_types"].append("W2/Salary")
                    if income.get("other_income", {}).get("borrower"):
                        profile["income_types"].append("Other/Bonus")
                
                # Ratios
                ratios = kd.get("section_iii_underwriting_information", {}).get("qualifying_ratios", {})
                if ratios:
                    profile["dti"] = ratios.get("total_obligations_income_percent")
                
                ltv_ratios = kd.get("section_iii_underwriting_information", {}).get("loan_to_value_ratios", {})
                if ltv_ratios:
                    profile["ltv"] = ltv_ratios.get("ltv_percent")
                    profile["cltv"] = ltv_ratios.get("cltv_tltv_percent")
        
        # Get URLA deep JSON for additional info
        cur.execute("""
            SELECT individual_analysis FROM document_analysis
            WHERE loan_id = %s AND filename LIKE '%%urla%%final%%'
            AND is_latest_version = TRUE
        """, (loan_id,))
        row = cur.fetchone()
        
        if row and row["individual_analysis"]:
            dj = row["individual_analysis"]
            summary = dj.get("document_summary", {})
            extracted = summary.get("extracted_data", {})
            
            # Borrower info
            if extracted.get("borrower_information"):
                profile["borrower_name"] = extracted["borrower_information"].get("name")
            
            # Employment info
            emp = extracted.get("employment_information", {})
            if emp.get("self_employed"):
                profile["has_self_employment"] = True
                profile["income_types"].append("Self-Employed")
            
            # Check for rental income in pages
            for page in dj.get("pages", []):
                text = json.dumps(page).lower()
                if "rental income" in text or "investment property" in text:
                    profile["has_rental_income"] = True
                    if "Rental" not in profile["income_types"]:
                        profile["income_types"].append("Rental")
                if "heloc" in text:
                    profile["is_heloc"] = True
        
        # Dedupe income types
        profile["income_types"] = list(set(profile["income_types"]))
        
        return profile
        
    finally:
        cur.close()
        conn.close()


def get_required_docs_for_profile(profile: dict) -> dict:
    """Determine required documents based on loan profile"""
    required = {
        "always_required": [
            "1008 (Transmittal Summary)",
            "URLA/1003 (Loan Application)",
            "Credit Report",
            "Title Policy/Commitment",
            "Closing Disclosure",
            "Hazard Insurance",
        ],
        "income_docs": [],
        "asset_docs": ["Bank Statements"],
        "property_docs": [],
        "loan_specific": [],
    }
    
    # Income documentation based on income types
    if "W2/Salary" in profile.get("income_types", []):
        required["income_docs"].extend(["Pay Stubs (30 days)", "W-2s (2 years)", "VOE"])
    
    if "Self-Employed" in profile.get("income_types", []) or profile.get("has_self_employment"):
        required["income_docs"].extend([
            "Tax Returns (2 years personal)",
            "Tax Returns (2 years business)",
            "Business License",
            "CPA Letter/Profit & Loss"
        ])
    
    if "Rental" in profile.get("income_types", []) or profile.get("has_rental_income"):
        required["income_docs"].extend(["Lease Agreements", "Schedule E", "Rental Income Verification"])
    
    if "Other/Bonus" in profile.get("income_types", []):
        required["income_docs"].append("Income Summary Report/Worksheet")
    
    # Property documentation
    required["property_docs"].append("Appraisal or AVM Report")
    
    if profile.get("loan_type") == "Purchase":
        required["loan_specific"].extend([
            "Purchase Agreement/Contract",
            "Earnest Money Verification",
            "Gift Letter (if applicable)"
        ])
    
    if "Refinance" in str(profile.get("loan_type", "")):
        required["loan_specific"].extend([
            "Existing Mortgage Statement",
            "Payoff Statement",
            "Net Tangible Benefit Worksheet"
        ])
    
    # Lien position specific
    if profile.get("is_second_lien") or profile.get("lien_position") == "Second":
        required["loan_specific"].extend([
            "First Lien Mortgage Statement",
            "Promissory Note (2nd Lien)",
            "Subordination Agreement (if applicable)"
        ])
    
    if profile.get("is_heloc"):
        required["loan_specific"].extend([
            "HELOC Agreement",
            "HELOC Disclosure"
        ])
    
    # Always need promissory note
    required["always_required"].append("Promissory Note")
    
    return required


def get_all_documents(loan_id: int) -> list[dict]:
    """Get all unique documents with their summaries for a loan"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            SELECT 
                filename,
                file_path,
                version_metadata->>'financial_category' as financial_category,
                individual_analysis
            FROM document_analysis
            WHERE loan_id = %s AND is_latest_version = TRUE
            ORDER BY filename
        """, (loan_id,))
        
        docs = []
        for row in cur.fetchall():
            doc = {
                "filename": row["filename"],
                "file_path": row["file_path"],
                "financial_category": row["financial_category"] or "UNKNOWN",
                "document_summary": None,
                "document_type": None,
                "key_entities": None,
                "important_values": None
            }
            
            # Extract summary from deep JSON if available
            if row["individual_analysis"]:
                dj = row["individual_analysis"]
                if isinstance(dj, dict):
                    summary = dj.get("document_summary", {})
                    if summary:
                        doc["document_summary"] = summary.get("document_overview", {})
                        doc["document_type"] = summary.get("document_overview", {}).get("document_type")
                        doc["key_entities"] = summary.get("key_entities", {})
                        doc["important_values"] = summary.get("important_values", {})
            
            docs.append(doc)
        
        return docs
    finally:
        cur.close()
        conn.close()


def classify_documents(loan_id: int, docs: list[dict], profile: dict = None, required: dict = None) -> dict:
    """Use Claude to intelligently classify documents based on loan profile"""
    
    # Prepare document list for Claude
    doc_list = []
    for d in docs:
        doc_info = {
            "filename": d["filename"],
            "financial_category": d["financial_category"],
            "document_type": d["document_type"],
        }
        # Add summary excerpt if available
        if d["document_summary"]:
            doc_info["summary"] = str(d["document_summary"])[:500]
        if d["important_values"]:
            doc_info["values_preview"] = str(d["important_values"])[:300]
        doc_list.append(doc_info)
    
    # Build loan profile context
    profile_context = ""
    if profile:
        profile_context = f"""
## LOAN PROFILE (extracted from 1008/URLA):
- Loan Type: {profile.get('loan_type', 'Unknown')}
- Lien Position: {profile.get('lien_position', 'Unknown')}
- Is HELOC: {profile.get('is_heloc', False)}
- Is 2nd Lien: {profile.get('is_second_lien', False)}
- Income Types: {profile.get('income_types', [])}
- Self-Employed Borrower: {profile.get('has_self_employment', False)}
- Has Rental Income: {profile.get('has_rental_income', False)}
- LTV: {profile.get('ltv')}%
- CLTV: {profile.get('cltv')}%
- DTI: {profile.get('dti')}%
"""
    
    required_context = ""
    if required:
        required_context = f"""
## REQUIRED DOCUMENTS FOR THIS LOAN PROFILE:
{json.dumps(required, indent=2)}
"""
    
    prompt = f"""You are an expert mortgage document analyst. Analyze these {len(doc_list)} documents from Loan ID {loan_id} and classify them by importance for loan verification/evidencing.
{profile_context}
{required_context}
## KNOWN IMPORTANT DOCUMENT TYPES (from experience):
{json.dumps(KNOWN_IMPORTANT_DOCS, indent=2)}

## DOCUMENTS TO CLASSIFY:
{json.dumps(doc_list, indent=2)}

## YOUR TASK:
Classify each document into one of these categories:
1. **CRITICAL** - Must have for verification (1008, URLA, promissory notes, mortgage statements, credit report)
2. **IMPORTANT** - Key evidence sources (pay stubs, W-2s, tax docs, insurance, appraisal, income reports)
3. **SUPPORTING** - Useful but not primary (disclosures, acknowledgments, checklists)
4. **NON-ESSENTIAL** - Administrative/legal only (e-signatures, consent forms, notices)

**IMPORTANT RULES:**
- PREFER FINAL versions over preliminary/initial versions (e.g., use "urla___final" not "urla___preliminary")
- If both final and preliminary exist, ONLY include the FINAL in critical/important lists
- Preliminary/initial docs go to SUPPORTING category as backup references

Also identify:
- Any documents that should be reclassified (wrong financial_category)
- Any key documents that appear to be MISSING based on typical loan packages
- Any "miscellaneous_docs" that are actually important (like Income Summary Reports)

## OUTPUT FORMAT (keep descriptions SHORT - max 50 chars):
```json
{{
    "critical_docs": ["filename1", "filename2"],
    "important_docs": ["filename1", "filename2"],
    "supporting_docs": ["filename1", "filename2"],
    "non_essential_docs": ["filename1", "filename2"],
    "hidden_gems": [
        {{"filename": "...", "actual_content": "short desc", "importance": "HIGH/MEDIUM"}}
    ],
    "missing_docs": ["doc_type1", "doc_type2"],
    "reclassification": [
        {{"filename": "...", "from": "FINANCIAL", "to": "NON-FINANCIAL"}}
    ]
}}
```
IMPORTANT: Keep the JSON compact. Just list filenames for the main categories.
"""
    
    print("🤖 Asking Claude Opus to classify documents...")
    response = call_bedrock(prompt, model="claude-opus-4-5", max_tokens=8000)
    
    # Extract JSON from response
    try:
        import re
        # Try to find JSON block
        json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
            return json.loads(json_str)
        
        # Try to find any JSON object
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(0))
        
        # Try to parse the whole response as JSON
        return json.loads(response)
    except json.JSONDecodeError as e:
        print(f"⚠️ JSON parse error: {e}")
        # Try to salvage partial JSON
        try:
            # Find the start of JSON and try to parse what we have
            start = response.find('{')
            if start >= 0:
                partial = response[start:]
                # Try to fix common truncation issues
                import re
                # Count open braces vs close braces
                open_count = partial.count('{')
                close_count = partial.count('}')
                # Add missing close braces
                partial += '}' * (open_count - close_count)
                return json.loads(partial)
        except:
            pass
        print("⚠️ Could not parse JSON response, returning raw text")
        return {"raw_response": response[:2000] + "...[truncated]"}


def run_examiner(loan_id: int):
    """Run the intelligent document examiner for a loan"""
    print(f"\n{'='*70}")
    print(f"🔍 INTELLIGENT DOCUMENT EXAMINER - Loan ID {loan_id}")
    print('='*70)
    
    # Step 1: Extract loan profile from 1008/URLA
    print("\n📊 Extracting Loan Profile from 1008/URLA...")
    profile = get_loan_profile(loan_id)
    
    print(f"   Loan Type: {profile.get('loan_type', 'Unknown')}")
    print(f"   Lien Position: {profile.get('lien_position', 'Unknown')}")
    print(f"   Is HELOC: {profile.get('is_heloc', False)}")
    print(f"   Is 2nd Lien: {profile.get('is_second_lien', False)}")
    print(f"   Income Types: {profile.get('income_types', [])}")
    print(f"   Self-Employed: {profile.get('has_self_employment', False)}")
    print(f"   Rental Income: {profile.get('has_rental_income', False)}")
    print(f"   LTV: {profile.get('ltv')}%") if profile.get('ltv') else None
    print(f"   CLTV: {profile.get('cltv')}%") if profile.get('cltv') else None
    print(f"   DTI: {profile.get('dti')}%") if profile.get('dti') else None
    
    # Step 2: Determine required docs based on profile
    print("\n📋 Required Documents for this Loan Profile:")
    required = get_required_docs_for_profile(profile)
    for category, docs_list in required.items():
        if docs_list:
            print(f"   {category}: {', '.join(docs_list[:5])}{'...' if len(docs_list) > 5 else ''}")
    
    # Step 3: Get all documents
    print("\n📄 Fetching all documents...")
    docs = get_all_documents(loan_id)
    print(f"   Found {len(docs)} unique documents")
    
    # Count by category
    by_cat = {}
    for d in docs:
        cat = d["financial_category"]
        by_cat[cat] = by_cat.get(cat, 0) + 1
    print(f"   Categories: {by_cat}")
    
    # Show documents with summaries
    print("\n📋 Documents with Deep JSON Summaries:")
    with_summary = [d for d in docs if d["document_type"]]
    print(f"   {len(with_summary)} of {len(docs)} have document_type extracted")
    
    # Step 4: Classify using Claude with loan profile context
    print("\n🧠 Intelligent Classification (with loan profile context)...")
    classification = classify_documents(loan_id, docs, profile, required)
    
    # Display results
    print("\n" + "="*70)
    print("📊 CLASSIFICATION RESULTS")
    print("="*70)
    
    if "critical_docs" in classification:
        critical = classification.get('critical_docs', [])
        print(f"\n🔴 CRITICAL DOCUMENTS ({len(critical)}):")
        for doc in critical:
            if isinstance(doc, dict):
                print(f"   ✓ {doc.get('filename', doc)}")
            else:
                print(f"   ✓ {doc}")
    
    if "important_docs" in classification:
        important = classification.get('important_docs', [])
        print(f"\n🟠 IMPORTANT DOCUMENTS ({len(important)}):")
        for doc in important:
            if isinstance(doc, dict):
                print(f"   • {doc.get('filename', doc)}")
            else:
                print(f"   • {doc}")
    
    if "hidden_gems" in classification:
        gems = classification.get("hidden_gems", [])
        if gems:
            print(f"\n💎 HIDDEN GEMS (Important docs with misleading names) ({len(gems)}):")
            for doc in gems:
                if isinstance(doc, dict):
                    print(f"   ★ {doc.get('filename', 'unknown')}")
                    print(f"     → {doc.get('actual_content', doc.get('importance', 'N/A'))}")
                else:
                    print(f"   ★ {doc}")
    
    if "missing_docs" in classification:
        missing = classification.get("missing_docs", [])
        if missing:
            print(f"\n⚠️ POTENTIALLY MISSING DOCUMENTS ({len(missing)}):")
            for doc in missing:
                if isinstance(doc, dict):
                    print(f"   ❌ {doc.get('doc_type', doc)}")
                else:
                    print(f"   ❌ {doc}")
    
    if "reclassification" in classification or "reclassification_needed" in classification:
        reclass = classification.get("reclassification", classification.get("reclassification_needed", []))
        if reclass:
            print(f"\n🔄 RECLASSIFICATION NEEDED ({len(reclass)}):")
            for doc in reclass:
                if isinstance(doc, dict):
                    print(f"   📝 {doc.get('filename', 'unknown')}: {doc.get('from', '?')} → {doc.get('to', '?')}")
                else:
                    print(f"   📝 {doc}")
    
    # Summary stats
    print("\n" + "="*70)
    print("📈 SUMMARY")
    print("="*70)
    total_important = len(classification.get("critical_docs", [])) + len(classification.get("important_docs", []))
    print(f"   Total Documents: {len(docs)}")
    print(f"   Critical + Important: {total_important}")
    print(f"   Hidden Gems Found: {len(classification.get('hidden_gems', []))}")
    print(f"   Missing Docs: {len(classification.get('missing_docs', []))}")
    
    return classification


if __name__ == "__main__":
    import sys
    loan_id = int(sys.argv[1]) if len(sys.argv) > 1 else 31
    result = run_examiner(loan_id)
    
    # Save results
    output_file = f"/Users/sunny/Applications/bts/jpmorgan/mortgage/modda/outputs/doc_classification_loan_{loan_id}.json"
    import os
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\n💾 Results saved to: {output_file}")

