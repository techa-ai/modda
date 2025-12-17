#!/usr/bin/env python3
"""
Extract Rich Loan Profile from 1008 and URLA Deep JSON using Claude Opus
"""

import json
import sys
from db import get_db_connection
from bedrock_config import call_bedrock


def get_1008_and_urla_json(loan_id: int) -> dict:
    """Get deep JSON for 1008, URLA, and alternative rate sources"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    result = {"loan_id": loan_id, "1008": None, "urla": None, "rate_sources": []}
    
    try:
        # Get 1008 (prefer final)
        cur.execute("""
            SELECT filename, individual_analysis FROM document_analysis
            WHERE loan_id = %s 
            AND (filename ILIKE '%%1008%%final%%' OR filename ILIKE '%%1008%%')
            AND is_latest_version = TRUE
            ORDER BY filename DESC
            LIMIT 1
        """, (loan_id,))
        row = cur.fetchone()
        if row and row["individual_analysis"]:
            result["1008"] = {
                "filename": row["filename"],
                "content": row["individual_analysis"]
            }
        
        # Get URLA (prefer final)
        cur.execute("""
            SELECT filename, individual_analysis FROM document_analysis
            WHERE loan_id = %s 
            AND (filename ILIKE '%%urla%%final%%' OR filename ILIKE '%%urla%%')
            AND is_latest_version = TRUE
            ORDER BY 
                CASE WHEN filename ILIKE '%%final%%' THEN 0 ELSE 1 END,
                filename DESC
            LIMIT 1
        """, (loan_id,))
        row = cur.fetchone()
        if row and row["individual_analysis"]:
            result["urla"] = {
                "filename": row["filename"],
                "content": row["individual_analysis"]
            }
        
        # Get Non-Standard Loan Application (if no 1008 or URLA)
        if not result["1008"] and not result["urla"]:
            cur.execute("""
                SELECT filename, individual_analysis FROM document_analysis
                WHERE loan_id = %s 
                AND (filename ILIKE '%%non%%standard%%loan%%' OR filename ILIKE '%%loan%%application%%')
                AND is_latest_version = TRUE
                ORDER BY 
                    CASE WHEN filename ILIKE '%%final%%' THEN 0 ELSE 1 END,
                    filename DESC
                LIMIT 1
            """, (loan_id,))
            row = cur.fetchone()
            if row and row["individual_analysis"]:
                result["urla"] = {
                    "filename": row["filename"],
                    "content": row["individual_analysis"],
                    "is_non_standard": True
                }
        
        # If no 1008, get alternative rate sources (HELOC Agreement, Rate Lock)
        if not result["1008"]:
            # HELOC Agreement
            cur.execute("""
                SELECT filename, individual_analysis FROM document_analysis
                WHERE loan_id = %s 
                AND (filename ILIKE '%%heloc%%agreement%%' OR filename ILIKE '%%heloc%%')
                AND is_latest_version = TRUE
                ORDER BY 
                    CASE WHEN filename ILIKE '%%final%%' THEN 0 ELSE 1 END,
                    filename DESC
                LIMIT 1
            """, (loan_id,))
            row = cur.fetchone()
            if row and row["individual_analysis"]:
                result["rate_sources"].append({
                    "type": "HELOC Agreement",
                    "filename": row["filename"],
                    "content": row["individual_analysis"]
                })
            
            # Rate Lock Agreement
            cur.execute("""
                SELECT filename, individual_analysis FROM document_analysis
                WHERE loan_id = %s 
                AND (filename ILIKE '%%rate%%lock%%' OR filename ILIKE '%%lock%%confirmation%%')
                AND is_latest_version = TRUE
                ORDER BY 
                    CASE WHEN filename ILIKE '%%final%%' THEN 0 ELSE 1 END,
                    filename DESC
                LIMIT 1
            """, (loan_id,))
            row = cur.fetchone()
            if row and row["individual_analysis"]:
                result["rate_sources"].append({
                    "type": "Rate Lock",
                    "filename": row["filename"],
                    "content": row["individual_analysis"]
                })
            
            # Promissory Note / HELOC Note
            cur.execute("""
                SELECT filename, individual_analysis FROM document_analysis
                WHERE loan_id = %s 
                AND (filename ILIKE '%%promissory%%note%%' OR filename ILIKE '%%note%%')
                AND NOT filename ILIKE '%%miscellaneous%%'
                AND is_latest_version = TRUE
                ORDER BY 
                    CASE WHEN filename ILIKE '%%final%%' THEN 0 ELSE 1 END,
                    filename DESC
                LIMIT 1
            """, (loan_id,))
            row = cur.fetchone()
            if row and row["individual_analysis"]:
                result["rate_sources"].append({
                    "type": "Promissory Note",
                    "filename": row["filename"],
                    "content": row["individual_analysis"]
                })
        
        return result
        
    finally:
        cur.close()
        conn.close()


def extract_loan_profile_with_opus(loan_id: int, docs: dict) -> dict:
    """Use Claude Opus to extract comprehensive loan profile"""
    
    doc_context = ""
    rate_source_note = ""
    
    if docs["1008"]:
        doc_context += f"\n## 1008 TRANSMITTAL SUMMARY ({docs['1008']['filename']}):\n"
        doc_context += json.dumps(docs["1008"]["content"], indent=2)[:30000]
    
    if docs["urla"]:
        is_non_std = docs["urla"].get("is_non_standard", False)
        label = "NON-STANDARD LOAN APPLICATION" if is_non_std else "URLA/1003 APPLICATION"
        doc_context += f"\n\n## {label} ({docs['urla']['filename']}):\n"
        doc_context += json.dumps(docs["urla"]["content"], indent=2)[:30000]
    
    # Add alternative rate sources if 1008 not available
    if not docs["1008"] and docs.get("rate_sources"):
        rate_source_note = "\n\n⚠️ IMPORTANT: 1008 is NOT available. Extract interest_rate from the alternative sources below:\n"
        for rs in docs["rate_sources"]:
            doc_context += f"\n\n## {rs['type'].upper()} ({rs['filename']}) - USE FOR INTEREST RATE:\n"
            doc_context += json.dumps(rs["content"], indent=2)[:15000]
        rate_source_note += "Look for APR, Interest Rate, Note Rate in HELOC Agreement, Rate Lock, or Promissory Note.\n"
    
    if not doc_context:
        return {"error": "No 1008 or URLA found for this loan"}
    
    prompt = f"""You are an expert mortgage underwriter. Extract a COMPREHENSIVE loan profile from these documents for Loan ID {loan_id}.
{rate_source_note}
{doc_context}

## EXTRACT THE FOLLOWING LOAN PROFILE:

```json
{{
    "loan_id": {loan_id},
    
    "borrower_info": {{
        "primary_borrower_name": "...",
        "co_borrower_name": "... or null",
        "has_co_borrower": true/false,
        "ssn_last4": "...",
        "dob": "...",
        "citizenship": "...",
        "marital_status": "..."
    }},
    
    "property_info": {{
        "address": "...",
        "city": "...",
        "state": "...",
        "zip": "...",
        "property_type": "SFR/Condo/2-4 Unit/PUD/etc",
        "occupancy": "Primary/Investment/Second Home",
        "number_of_units": 1,
        "year_built": "...",
        "appraised_value": 0.00,
        "purchase_price": 0.00
    }},
    
    "loan_info": {{
        "loan_purpose": "Purchase/Rate-Term Refi/Cash-Out Refi",
        "loan_type": "Conventional/FHA/VA/USDA",
        "lien_position": "First/Second",
        "is_heloc": true/false,
        "loan_amount": 0.00,
        "loan_term_months": 360,
        "interest_rate": 0.00,
        "amortization_type": "Fixed/ARM/Interest-Only",
        "monthly_pi_payment": 0.00
    }},
    
    "ratios": {{
        "ltv_percent": 0.00,
        "cltv_percent": 0.00,
        "dti_front_end_percent": 0.00,
        "dti_back_end_percent": 0.00
    }},
    
    "income_profile": {{
        "total_monthly_income": 0.00,
        "base_income": 0.00,
        "bonus_income": 0.00,
        "overtime_income": 0.00,
        "commission_income": 0.00,
        "rental_income": 0.00,
        "other_income": 0.00,
        "income_types": ["W2/Salary", "Self-Employed", "Rental", "Retirement", etc],
        "is_self_employed": true/false,
        "has_rental_income": true/false,
        "has_variable_income": true/false
    }},
    
    "employment_info": {{
        "employer_name": "...",
        "position": "...",
        "years_employed": 0,
        "months_employed": 0,
        "employment_type": "Full-Time/Part-Time/Self-Employed"
    }},
    
    "credit_profile": {{
        "credit_score": 0,
        "credit_score_source": "Equifax/TransUnion/Experian",
        "existing_first_mortgage_balance": 0.00,
        "existing_first_mortgage_payment": 0.00,
        "total_monthly_debts": 0.00
    }},
    
    "transaction_details": {{
        "is_refinance": true/false,
        "is_purchase": true/false,
        "is_cash_out": true/false,
        "cash_out_amount": 0.00,
        "subordinate_financing": 0.00,
        "seller_credits": 0.00,
        "closing_costs": 0.00
    }},
    
    "escrow_items": {{
        "property_taxes_annual": 0.00,
        "hazard_insurance_annual": 0.00,
        "flood_insurance_annual": 0.00,
        "hoa_monthly": 0.00,
        "mortgage_insurance_monthly": 0.00
    }},
    
    "underwriting_notes": {{
        "aus_system": "DU/LP/Manual",
        "aus_recommendation": "Approve/Refer/etc",
        "underwriter_name": "...",
        "special_conditions": ["..."]
    }},
    
    "required_documents_for_this_profile": [
        "List of docs needed based on this specific loan profile"
    ]
}}
```

Extract ALL available values. Use null for missing data. Be precise with numbers.
"""
    
    print(f"🤖 Asking Claude Opus to extract loan profile for Loan {loan_id}...")
    response = call_bedrock(prompt, model="claude-opus-4-5", max_tokens=4000)
    
    # Parse JSON from response
    try:
        import re
        json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(1))
        
        # Try to find any JSON object
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            return json.loads(json_match.group(0))
            
        return {"raw_response": response[:2000]}
    except json.JSONDecodeError as e:
        print(f"⚠️ JSON parse error: {e}")
        return {"raw_response": response[:2000]}


def compare_loan_profiles(profiles: list[dict]):
    """Compare loan profiles side by side"""
    print("\n" + "="*100)
    print("📊 LOAN PROFILE COMPARISON")
    print("="*100)
    
    # Key comparison fields
    fields = [
        ("Loan ID", lambda p: p.get("loan_id")),
        ("Borrower", lambda p: p.get("borrower_info", {}).get("primary_borrower_name")),
        ("Property State", lambda p: p.get("property_info", {}).get("state")),
        ("Property Type", lambda p: p.get("property_info", {}).get("property_type")),
        ("Occupancy", lambda p: p.get("property_info", {}).get("occupancy")),
        ("Loan Purpose", lambda p: p.get("loan_info", {}).get("loan_purpose")),
        ("Lien Position", lambda p: p.get("loan_info", {}).get("lien_position")),
        ("Is HELOC", lambda p: p.get("loan_info", {}).get("is_heloc")),
        ("Loan Amount", lambda p: f"${p.get('loan_info', {}).get('loan_amount', 0):,.2f}" if p.get('loan_info', {}).get('loan_amount') else "N/A"),
        ("Interest Rate", lambda p: f"{p.get('loan_info', {}).get('interest_rate', 0)}%" if p.get('loan_info', {}).get('interest_rate') else "N/A"),
        ("LTV", lambda p: f"{p.get('ratios', {}).get('ltv_percent', 0)}%" if p.get('ratios', {}).get('ltv_percent') else "N/A"),
        ("CLTV", lambda p: f"{p.get('ratios', {}).get('cltv_percent', 0)}%" if p.get('ratios', {}).get('cltv_percent') else "N/A"),
        ("DTI", lambda p: f"{p.get('ratios', {}).get('dti_back_end_percent', 0)}%" if p.get('ratios', {}).get('dti_back_end_percent') else "N/A"),
        ("Monthly Income", lambda p: f"${p.get('income_profile', {}).get('total_monthly_income', 0):,.2f}" if p.get('income_profile', {}).get('total_monthly_income') else "N/A"),
        ("Income Types", lambda p: ", ".join(p.get("income_profile", {}).get("income_types", [])) or "N/A"),
        ("Self-Employed", lambda p: p.get("income_profile", {}).get("is_self_employed")),
        ("Rental Income", lambda p: p.get("income_profile", {}).get("has_rental_income")),
        ("Credit Score", lambda p: p.get("credit_profile", {}).get("credit_score")),
    ]
    
    # Print header
    header = f"{'Field':<25}"
    for p in profiles:
        header += f" | Loan {p.get('loan_id', '?'):<12}"
    print(header)
    print("-" * len(header))
    
    # Print each field
    for field_name, getter in fields:
        row = f"{field_name:<25}"
        for p in profiles:
            val = getter(p)
            val_str = str(val) if val is not None else "N/A"
            if len(val_str) > 14:
                val_str = val_str[:12] + ".."
            row += f" | {val_str:<14}"
        print(row)
    
    # Print required docs comparison
    print("\n" + "="*100)
    print("📋 REQUIRED DOCUMENTS BY LOAN PROFILE")
    print("="*100)
    
    for p in profiles:
        loan_id = p.get("loan_id", "?")
        docs = p.get("required_documents_for_this_profile", [])
        print(f"\n🔹 Loan {loan_id}:")
        for doc in docs[:10]:
            print(f"   • {doc}")
        if len(docs) > 10:
            print(f"   ... and {len(docs) - 10} more")


def run_profile_extraction(loan_ids: list[int]):
    """Run profile extraction for multiple loans"""
    profiles = []
    
    for loan_id in loan_ids:
        print(f"\n{'='*70}")
        print(f"🔍 LOAN PROFILE EXTRACTION - Loan ID {loan_id}")
        print("="*70)
        
        # Get 1008 and URLA
        docs = get_1008_and_urla_json(loan_id)
        print(f"   1008: {'✓ ' + docs['1008']['filename'] if docs['1008'] else '✗ Not found'}")
        if docs["urla"]:
            is_non_std = docs["urla"].get("is_non_standard", False)
            label = "Non-Std App" if is_non_std else "URLA"
            print(f"   {label}: ✓ {docs['urla']['filename']}")
        else:
            print(f"   URLA: ✗ Not found")
        
        # Show alternative rate sources if no 1008
        if not docs["1008"] and docs.get("rate_sources"):
            print(f"   📊 Alternative Rate Sources:")
            for rs in docs["rate_sources"]:
                print(f"      • {rs['type']}: {rs['filename']}")
        
        if not docs["1008"] and not docs["urla"]:
            print(f"   ⚠️ No 1008 or URLA found for Loan {loan_id}")
            profiles.append({"loan_id": loan_id, "error": "No documents found"})
            continue
        
        # Extract profile with Opus
        profile = extract_loan_profile_with_opus(loan_id, docs)
        profiles.append(profile)
        
        # Print key info
        if "error" not in profile and "raw_response" not in profile:
            print(f"\n   📊 Profile Extracted:")
            print(f"   • Borrower: {profile.get('borrower_info', {}).get('primary_borrower_name', 'N/A')}")
            print(f"   • Loan Purpose: {profile.get('loan_info', {}).get('loan_purpose', 'N/A')}")
            print(f"   • Lien Position: {profile.get('loan_info', {}).get('lien_position', 'N/A')}")
            print(f"   • Loan Amount: ${profile.get('loan_info', {}).get('loan_amount', 0):,.2f}")
            print(f"   • Income Types: {profile.get('income_profile', {}).get('income_types', [])}")
    
    # Compare all profiles
    if len(profiles) > 1:
        compare_loan_profiles(profiles)
    
    # Save results
    output_file = "/Users/sunny/Applications/bts/jpmorgan/mortgage/modda/outputs/loan_profiles_comparison.json"
    import os
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(profiles, f, indent=2)
    print(f"\n💾 Profiles saved to: {output_file}")
    
    return profiles


if __name__ == "__main__":
    # Default to loans 1, 30, 31, 32
    if len(sys.argv) > 1:
        loan_ids = [int(x) for x in sys.argv[1:]]
    else:
        loan_ids = [1, 30, 31, 32]
    
    run_profile_extraction(loan_ids)

