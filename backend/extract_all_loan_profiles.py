#!/usr/bin/env python3
"""
Extract Loan Profiles for ALL loans and save to database
"""

import json
import sys
from db import get_db_connection, execute_query
from extract_loan_profile import get_1008_and_urla_json, extract_loan_profile_with_opus


def extract_and_save_all_profiles(force_reextract=False):
    """Extract profiles for all loans and save to database"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Get all loan IDs
        cur.execute("SELECT id, loan_number FROM loans ORDER BY id")
        loans = cur.fetchall()
        print(f"📊 Processing {len(loans)} loans...")
        
        for loan in loans:
            loan_id = loan["id"]
            loan_number = loan["loan_number"]
            
            print(f"\n{'='*60}")
            print(f"🔍 Loan ID {loan_id} (#{loan_number})")
            print("="*60)
            
            # Check if already processed
            cur.execute("SELECT id FROM loan_profiles WHERE loan_id = %s", (loan_id,))
            existing = cur.fetchone()
            if existing and not force_reextract:
                print(f"   ⏭️ Already processed, skipping... (use --force to re-extract)")
                continue
            elif existing:
                print(f"   🔄 Re-extracting...")
            
            # Get 1008 and URLA
            docs = get_1008_and_urla_json(loan_id)
            
            has_1008 = docs["1008"] is not None
            has_urla = docs["urla"] is not None
            is_non_standard = docs.get("urla", {}).get("is_non_standard", False) if has_urla else False
            has_rate_sources = len(docs.get("rate_sources", [])) > 0
            
            if has_1008:
                print(f"   ✓ 1008: {docs['1008']['filename']}")
            else:
                print(f"   ✗ 1008: Not found")
                
            if has_urla:
                label = "Non-Std App" if is_non_standard else "URLA"
                print(f"   ✓ {label}: {docs['urla']['filename']}")
            else:
                print(f"   ✗ URLA: Not found")
            
            # Show alternative rate sources
            if not has_1008 and has_rate_sources:
                print(f"   📊 Alt Rate Sources:")
                for rs in docs.get("rate_sources", []):
                    print(f"      • {rs['type']}: {rs['filename']}")
            
            if not has_1008 and not has_urla:
                print(f"   ⚠️ No 1008 or URLA found, skipping...")
                # Save empty profile
                cur.execute("""
                    INSERT INTO loan_profiles (loan_id, profile_data, analysis_source)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (loan_id) DO UPDATE SET
                        profile_data = EXCLUDED.profile_data,
                        analysis_source = EXCLUDED.analysis_source,
                        extracted_at = NOW()
                """, (loan_id, json.dumps({"error": "No 1008 or URLA found"}), "None"))
                conn.commit()
                continue
            
            # Determine source - simplified: if 1008 exists, just use "1008"
            if has_1008:
                source = "1008"
                source_doc = docs["1008"]["filename"]
            elif is_non_standard:
                source = "Non-Standard Loan App (URLA equivalent)"
                source_doc = docs["urla"]["filename"]
            else:
                source = "URLA only"
                source_doc = docs["urla"]["filename"]
            
            # Extract profile with Opus
            profile = extract_loan_profile_with_opus(loan_id, docs)
            
            if "error" in profile or "raw_response" in profile:
                print(f"   ⚠️ Extraction error")
            else:
                print(f"   ✓ Borrower: {profile.get('borrower_info', {}).get('primary_borrower_name', 'N/A')}")
                print(f"   ✓ Loan Purpose: {profile.get('loan_info', {}).get('loan_purpose', 'N/A')}")
                print(f"   ✓ Loan Amount: ${profile.get('loan_info', {}).get('loan_amount', 0):,.2f}")
            
            # Add rate source info to profile if from alternative source
            if not has_1008 and has_rate_sources:
                profile["_rate_from_alternative_source"] = True
                profile["_rate_sources"] = [rs["type"] for rs in docs.get("rate_sources", [])]
            
            # Save to database
            cur.execute("""
                INSERT INTO loan_profiles (loan_id, profile_data, analysis_source, source_document)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (loan_id) DO UPDATE SET
                    profile_data = EXCLUDED.profile_data,
                    analysis_source = EXCLUDED.analysis_source,
                    source_document = EXCLUDED.source_document,
                    extracted_at = NOW()
            """, (loan_id, json.dumps(profile), source, source_doc))
            conn.commit()
            print(f"   💾 Saved to database (source: {source})")
        
        print(f"\n{'='*60}")
        print("✅ ALL LOANS PROCESSED")
        print("="*60)
        
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    force = "--force" in sys.argv or "-f" in sys.argv
    extract_and_save_all_profiles(force_reextract=force)

