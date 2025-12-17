"""
Summary Step S1: Extract Loan Profile

Extracts comprehensive loan profile from the primary source document:
1. 1008 (Transmittal Summary) - preferred
2. URLA (1003) - fallback
3. Non-Standard Loan Application - final fallback

Output: loan_profiles table with profile_data JSON
"""

import json
import sys
from datetime import datetime
from db import execute_query, execute_one, get_db_connection


def get_source_document(loan_id):
    """Find the best source document for profile extraction."""
    
    # Priority 1: 1008 Final
    doc_1008 = execute_one("""
        SELECT id, filename, individual_analysis, file_path
        FROM document_analysis
        WHERE loan_id = %s 
        AND filename ILIKE '%%1008%%final%%'
        LIMIT 1
    """, (loan_id,))
    
    if doc_1008 and doc_1008.get('individual_analysis'):
        return {
            'type': '1008',
            'filename': doc_1008['filename'],
            'analysis': doc_1008['individual_analysis'],
            'file_path': doc_1008['file_path'],
            'source_label': '1008'
        }
    
    # Priority 2: URLA Final
    urla = execute_one("""
        SELECT id, filename, individual_analysis, file_path
        FROM document_analysis
        WHERE loan_id = %s 
        AND filename ILIKE '%%urla%%final%%'
        ORDER BY filename
        LIMIT 1
    """, (loan_id,))
    
    if urla and urla.get('individual_analysis'):
        return {
            'type': 'URLA',
            'filename': urla['filename'],
            'analysis': urla['individual_analysis'],
            'file_path': urla['file_path'],
            'source_label': 'URLA only'
        }
    
    # Priority 3: Non-Standard Loan Application (prefer initial)
    non_std = execute_one("""
        SELECT id, filename, individual_analysis, file_path
        FROM document_analysis
        WHERE loan_id = %s 
        AND filename ILIKE '%%non_standard%%'
        ORDER BY 
            CASE WHEN filename ILIKE '%%initial%%' THEN 0 
                 WHEN filename ILIKE '%%final%%' THEN 1 
                 ELSE 2 END
        LIMIT 1
    """, (loan_id,))
    
    if non_std and non_std.get('individual_analysis'):
        return {
            'type': 'Non-Standard',
            'filename': non_std['filename'],
            'analysis': non_std['individual_analysis'],
            'file_path': non_std['file_path'],
            'source_label': 'Non-Standard Loan App (URLA equivalent)'
        }
    
    return None


def extract_profile_from_1008(analysis):
    """Extract profile from 1008 document analysis."""
    profile = {
        'loan_info': {},
        'borrower_info': {},
        'property_info': {},
        'ratios': {},
        'income_profile': {},
        'credit_profile': {},
        'employment_info': {},
        'escrow_items': {},
        'underwriting_notes': {},
        'transaction_details': {}
    }
    
    pages = analysis.get('pages', [])
    if not pages:
        return profile
    
    page = pages[0]
    key_data = page.get('key_data', {})
    sections = page.get('sections', {}) or key_data.get('sections', {})
    
    # Section 1: Borrower Information
    section1 = sections.get('section_1_borrower_information', {})
    if section1:
        profile['borrower_info'] = {
            'primary_borrower_name': section1.get('borrower_name'),
            'ssn_last4': section1.get('ssn_last_4'),
            'co_borrower_name': section1.get('co_borrower_name'),
            'has_co_borrower': bool(section1.get('co_borrower_name'))
        }
    
    # Section 2: Mortgage Information
    section2 = sections.get('section_2_mortgage_information', {})
    if section2:
        note_info = section2.get('note_information', {})
        loan_type = section2.get('loan_type', {})
        loan_purpose = section2.get('loan_purpose', {})
        lien = section2.get('lien_position', {})
        amort = section2.get('amortization_type', {})
        
        # Determine loan type
        lt = 'Conventional'
        if loan_type.get('fha'): lt = 'FHA'
        elif loan_type.get('va'): lt = 'VA'
        elif loan_type.get('usda_rd'): lt = 'USDA'
        
        # Determine purpose
        purpose = 'Purchase'
        if loan_purpose.get('cash_out_refinance'): purpose = 'Cash-Out Refinance'
        elif loan_purpose.get('no_cash_out_refinance_freddie'): purpose = 'Rate-Term Refinance'
        elif loan_purpose.get('limited_cash_out_refinance_fannie'): purpose = 'Rate-Term Refinance'
        elif loan_purpose.get('home_improvement'): purpose = 'Home Improvement'
        
        # Determine lien position
        lien_pos = 'First'
        if lien.get('second_mortgage'): lien_pos = 'Second'
        
        # Check for HELOC
        is_heloc = section2.get('home_equity_line_of_credit', False)
        if is_heloc:
            purpose = 'HELOC'
        
        # Amortization
        amort_type = 'Fixed'
        if amort.get('arm_type'): amort_type = 'ARM'
        elif amort.get('balloon'): amort_type = 'Balloon'
        
        profile['loan_info'] = {
            'loan_type': lt,
            'loan_purpose': purpose,
            'loan_amount': note_info.get('loan_amount'),
            'interest_rate': note_info.get('note_rate'),
            'loan_term_months': note_info.get('loan_terms_in_months'),
            'lien_position': lien_pos,
            'is_heloc': is_heloc,
            'amortization_type': amort_type,
            'monthly_pi_payment': section2.get('pi_payment')
        }
    
    # Section 3: Underwriting Information
    section3 = sections.get('section_3_underwriting_information', {})
    if section3:
        risk = section3.get('risk_assessment', {})
        qualifying = section3.get('qualifying_rate', {})
        
        profile['underwriting_notes'] = {
            'aus_system': 'DU' if risk.get('du') else ('LP' if risk.get('lp') else None),
            'aus_recommendation': risk.get('recommendation'),
            'is_bank_statement_loan': section3.get('bank_statement_loan') or section3.get('alternative_documentation')
        }
        
        profile['credit_profile'] = {
            'credit_score': section3.get('credit_score') or section3.get('representative_credit_score')
        }
    
    # Section 4: Property and Housing Expense
    section4 = sections.get('section_4_property_and_housing_expense', {})
    if section4:
        prop = section4.get('property_information', {})
        
        # Determine occupancy
        occupancy = 'Primary Residence'
        if prop.get('second_home'): occupancy = 'Second Home'
        elif prop.get('investment_property'): occupancy = 'Investment'
        
        profile['property_info'] = {
            'address': prop.get('address'),
            'city': prop.get('city'),
            'state': prop.get('state'),
            'zip': prop.get('zip'),
            'occupancy': occupancy,
            'property_type': prop.get('property_type'),
            'number_of_units': prop.get('number_of_units'),
            'appraised_value': section4.get('appraised_value') or section4.get('property_value'),
            'purchase_price': section4.get('purchase_price')
        }
        
        # Housing expenses
        housing = section4.get('proposed_monthly_housing_expense', {}) or section4.get('housing_expense', {})
        profile['escrow_items'] = {
            'property_taxes_annual': (housing.get('real_estate_taxes', 0) or 0) * 12,
            'hazard_insurance_annual': (housing.get('hazard_insurance', 0) or 0) * 12,
            'mortgage_insurance_monthly': housing.get('mortgage_insurance'),
            'hoa_monthly': housing.get('hoa_dues')
        }
    
    # Section 5: Qualifying Ratios
    section5 = sections.get('section_5_qualifying_ratios', {})
    if section5:
        income = section5.get('income', {})
        
        profile['income_profile'] = {
            'base_income': income.get('base_employment_income'),
            'overtime_income': income.get('overtime'),
            'bonus_income': income.get('bonuses'),
            'commission_income': income.get('commissions'),
            'rental_income': income.get('rental_income'),
            'other_income': income.get('other_income'),
            'total_monthly_income': income.get('total_monthly_income')
        }
        
        ratios = section5.get('qualifying_ratios', {}) or section5
        profile['ratios'] = {
            'dti_front_end_percent': ratios.get('primary_housing_expense_to_income') or ratios.get('front_end_ratio'),
            'dti_back_end_percent': ratios.get('total_obligations_to_income') or ratios.get('back_end_ratio'),
            'ltv_percent': section5.get('ltv') or section5.get('loan_to_value'),
            'cltv_percent': section5.get('cltv') or section5.get('combined_ltv')
        }
    
    return profile


def extract_profile_from_urla(analysis):
    """Extract profile from URLA document analysis."""
    profile = {
        'loan_info': {},
        'borrower_info': {},
        'property_info': {},
        'ratios': {},
        'income_profile': {},
        'credit_profile': {},
        'employment_info': {},
        'escrow_items': {},
        'underwriting_notes': {},
        'transaction_details': {}
    }
    
    doc_summary = analysis.get('document_summary', {})
    fin_summary = doc_summary.get('financial_summary', {})
    entities = doc_summary.get('key_entities', {})
    
    # Borrower info from entities
    people = entities.get('people', [])
    if people:
        primary = people[0] if people else {}
        profile['borrower_info'] = {
            'primary_borrower_name': primary.get('name'),
            'dob': primary.get('dob'),
            'ssn_last4': primary.get('ssn', '')[-4:] if primary.get('ssn') else None,
            'has_co_borrower': len(people) > 1,
            'co_borrower_name': people[1].get('name') if len(people) > 1 else None
        }
    
    # Property info
    addresses = entities.get('addresses', [])
    for addr in addresses:
        if addr.get('type') in ['property', 'subject', 'Property Address', 'Subject Property']:
            profile['property_info'] = {
                'address': addr.get('street') or addr.get('address'),
                'city': addr.get('city'),
                'state': addr.get('state'),
                'zip': addr.get('zip')
            }
            break
    
    # Loan info from financial_summary
    loan_req = fin_summary.get('loan_request', {})
    if loan_req:
        profile['loan_info'] = {
            'loan_amount': loan_req.get('loan_amount') or loan_req.get('amount_requested'),
            'loan_purpose': loan_req.get('purpose') or loan_req.get('loan_purpose'),
            'loan_type': loan_req.get('loan_type', 'Conventional')
        }
        
        profile['property_info']['appraised_value'] = loan_req.get('property_value')
    
    # Income
    income = fin_summary.get('income', {})
    if income:
        monthly = income.get('monthly_income', {})
        total = sum(v for v in monthly.values() if isinstance(v, (int, float))) if monthly else 0
        
        profile['income_profile'] = {
            'total_monthly_income': total or income.get('gross_monthly_income') or income.get('applicant_gross_monthly_income'),
            'base_income': monthly.get('base') or monthly.get('salary'),
            'rental_income': monthly.get('rental') or monthly.get('rental_income')
        }
    
    # Ratios from loan_to_value_estimate
    ltv_est = fin_summary.get('loan_to_value_estimate', {})
    if ltv_est:
        profile['ratios']['ltv_percent'] = ltv_est.get('ltv_percentage')
    
    # DTI from debt_to_income_indicators
    dti_ind = fin_summary.get('debt_to_income_indicators', {})
    if dti_ind:
        profile['ratios']['dti_front_end_percent'] = dti_ind.get('housing_expense_ratio')
    
    return profile


def extract_profile_from_non_standard(analysis):
    """Extract profile from Non-Standard Loan Application."""
    # Similar structure to URLA
    return extract_profile_from_urla(analysis)


def detect_bank_statement_loan(loan_id):
    """Detect if this is a bank statement loan based on income verification documents."""
    # Strategy 1: Check if bank statements were actually used for income verification
    # by looking at the calculation_steps for income attributes
    
    income_attr = execute_one("""
        SELECT id FROM form_1008_attributes 
        WHERE attribute_label ILIKE '%Total%Income%' 
           OR attribute_label ILIKE '%Monthly%Income%'
           OR attribute_label ILIKE '%Borrower%Income%'
        LIMIT 1
    """)
    
    if income_attr:
        # Check if bank statements were used in income calculation steps
        bank_stmt_evidence = execute_query("""
            SELECT DISTINCT document_name
            FROM calculation_steps
            WHERE loan_id = %s 
            AND attribute_id = %s
            AND (
                document_name ILIKE '%%bank%%statement%%'
                OR document_name ILIKE '%%bank%%stmt%%'
            )
        """, (loan_id, income_attr['id']))
        
        if bank_stmt_evidence and len(bank_stmt_evidence) > 0:
            return True
        
        # Also check evidence_files table
        evidence_files = execute_query("""
            SELECT DISTINCT file_name
            FROM evidence_files
            WHERE loan_id = %s 
            AND attribute_id = %s
            AND (
                file_name ILIKE '%%bank%%statement%%'
                OR file_name ILIKE '%%bank%%stmt%%'
            )
        """, (loan_id, income_attr['id']))
        
        if evidence_files and len(evidence_files) > 0:
            return True
    
    # Strategy 2: Check document package - if has bank statements but no traditional income docs
    # This catches bank statement loans before income verification is run
    bank_stmts = execute_query("""
        SELECT filename
        FROM document_analysis
        WHERE loan_id = %s
        AND (
            filename ILIKE '%%bank%%statement%%'
            OR filename ILIKE '%%bank%%stmt%%'
        )
    """, (loan_id,))
    
    traditional_income_docs = execute_query("""
        SELECT filename
        FROM document_analysis
        WHERE loan_id = %s
        AND (
            filename ILIKE '%%pay%%stub%%'
            OR filename ILIKE '%%paystub%%'
            OR filename ILIKE '%%w2%%'
            OR filename ILIKE '%%w-2%%'
        )
    """, (loan_id,))
    
    # If has bank statements but no traditional income docs, likely a bank statement loan
    if bank_stmts and len(bank_stmts) >= 1 and len(traditional_income_docs) == 0:
        return True
    
    return False


def get_alternative_rate_sources(loan_id, profile):
    """Get interest rate from alternative sources if not in profile."""
    if profile.get('loan_info', {}).get('interest_rate'):
        return profile
    
    # Check HELOC Agreement
    heloc = execute_one("""
        SELECT filename, individual_analysis
        FROM document_analysis
        WHERE loan_id = %s AND filename ILIKE '%%heloc_agreement%%final%%'
        LIMIT 1
    """, (loan_id,))
    
    if heloc and heloc.get('individual_analysis'):
        pages = heloc['individual_analysis'].get('pages', [])
        if pages:
            key_data = pages[0].get('key_data', {})
            rate = key_data.get('initial_interest_rate')
            if not rate:
                loan_details = key_data.get('loan_details', {})
                rate = loan_details.get('annual_percentage_rate')
            
            if rate:
                # Parse rate
                import re
                match = re.search(r'([\d.]+)', str(rate))
                if match:
                    profile['loan_info']['interest_rate'] = float(match.group(1))
                    profile['loan_info']['interest_rate_source'] = heloc['filename']
                    profile['loan_info']['is_heloc'] = True
    
    # Check Rate Lock
    if not profile.get('loan_info', {}).get('interest_rate'):
        rate_lock = execute_one("""
            SELECT filename, individual_analysis
            FROM document_analysis
            WHERE loan_id = %s AND filename ILIKE '%%rate_lock%%'
            ORDER BY filename DESC
            LIMIT 1
        """, (loan_id,))
        
        if rate_lock and rate_lock.get('individual_analysis'):
            doc_summary = rate_lock['individual_analysis'].get('document_summary', {})
            extracted = doc_summary.get('extracted_data', {})
            loan_terms = extracted.get('loan_terms', {})
            
            if loan_terms.get('note_rate'):
                import re
                match = re.search(r'([\d.]+)', str(loan_terms['note_rate']))
                if match:
                    profile['loan_info']['interest_rate'] = float(match.group(1))
                    profile['loan_info']['interest_rate_source'] = rate_lock['filename']
    
    return profile


def save_profile(loan_id, profile, source_doc):
    """Save profile to loan_profiles table."""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Add metadata
        profile['loan_id'] = loan_id
        
        # Check if profile exists
        existing = execute_one("""
            SELECT id FROM loan_profiles WHERE loan_id = %s
        """, (loan_id,))
        
        if existing:
            cur.execute("""
                UPDATE loan_profiles
                SET profile_data = %s,
                    analysis_source = %s,
                    source_document = %s,
                    extracted_at = %s
                WHERE loan_id = %s
            """, (
                json.dumps(profile),
                source_doc['source_label'],
                source_doc['filename'],
                datetime.now(),
                loan_id
            ))
        else:
            cur.execute("""
                INSERT INTO loan_profiles (loan_id, profile_data, analysis_source, source_document, extracted_at)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                loan_id,
                json.dumps(profile),
                source_doc['source_label'],
                source_doc['filename'],
                datetime.now()
            ))
        
        conn.commit()
        print(f"  ✅ Saved profile for loan {loan_id}")
        
    except Exception as e:
        conn.rollback()
        print(f"  ❌ Error saving profile: {e}")
    finally:
        cur.close()
        conn.close()


def extract_profile(loan_id):
    """Extract and save loan profile for a single loan."""
    print(f"\n{'='*60}")
    print(f"📊 S1: EXTRACTING PROFILE FOR LOAN {loan_id}")
    print(f"{'='*60}")
    
    # Find source document
    source = get_source_document(loan_id)
    
    if not source:
        print(f"  ⚠️ No source document found (1008, URLA, or Non-Standard)")
        return None
    
    print(f"  📄 Source: {source['filename']} ({source['type']})")
    
    # Extract profile based on document type
    if source['type'] == '1008':
        profile = extract_profile_from_1008(source['analysis'])
    elif source['type'] == 'URLA':
        profile = extract_profile_from_urla(source['analysis'])
    else:
        profile = extract_profile_from_non_standard(source['analysis'])
    
    # Get alternative rate sources if needed
    profile = get_alternative_rate_sources(loan_id, profile)
    
    # Detect bank statement loan if not already flagged
    if not profile.get('underwriting_notes', {}).get('is_bank_statement_loan'):
        is_bank_stmt = detect_bank_statement_loan(loan_id)
        if is_bank_stmt:
            if 'underwriting_notes' not in profile:
                profile['underwriting_notes'] = {}
            profile['underwriting_notes']['is_bank_statement_loan'] = True
    
    # Print summary
    loan_info = profile.get('loan_info', {})
    ratios = profile.get('ratios', {})
    
    print(f"  💰 Amount: ${loan_info.get('loan_amount', 0):,.0f}")
    print(f"  📈 Rate: {loan_info.get('interest_rate', 'N/A')}%")
    print(f"  📊 DTI: {ratios.get('dti_back_end_percent', 'N/A')}%")
    print(f"  🏠 CLTV: {ratios.get('cltv_percent', 'N/A')}%")
    
    # Save profile
    save_profile(loan_id, profile, source)
    
    return profile


def run_extraction(loan_id=None):
    """Run profile extraction for all loans or a specific loan."""
    print("📊 SUMMARY S1: EXTRACT LOAN PROFILES")
    print("=" * 60)
    
    if loan_id:
        loans = execute_query("""
            SELECT id, loan_number FROM loans WHERE id = %s
        """, (loan_id,))
    else:
        loans = execute_query("""
            SELECT id, loan_number FROM loans ORDER BY id
        """)
    
    print(f"Processing {len(loans)} loans\n")
    
    success = 0
    for loan in loans:
        result = extract_profile(loan['id'])
        if result:
            success += 1
    
    print(f"\n{'='*60}")
    print(f"📊 SUMMARY: Extracted {success}/{len(loans)} profiles")


if __name__ == '__main__':
    if len(sys.argv) > 1:
        loan_id = int(sys.argv[1])
        run_extraction(loan_id)
    else:
        run_extraction()

