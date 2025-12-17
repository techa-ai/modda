"""
Summary Step S2: DSCR Calculation for Investment Properties

DSCR = Net Operating Income / Annual Debt Service
     = (Monthly Rental Income × 0.75) / Monthly P&I Payment

Standard thresholds:
- DSCR ≥ 1.25: Strong (Green)
- DSCR 1.0-1.25: Acceptable (Amber)
- DSCR < 1.0: Negative cash flow (Red)

This step runs after S1 (Profile Extraction) to calculate DSCR for investment properties.
"""

import json
import re
from db import execute_query, execute_one, get_db_connection


def is_investment_property(loan_id):
    """Check if a loan is for an investment property."""
    # Check loan profile first
    profile = execute_one("""
        SELECT profile_data->'property_info'->>'occupancy' as occupancy
        FROM loan_profiles
        WHERE loan_id = %s
    """, (loan_id,))
    
    if profile and profile.get('occupancy'):
        occupancy = profile['occupancy'].lower()
        return 'investment' in occupancy
    
    # Fallback: check URLA
    urla = execute_one("""
        SELECT individual_analysis
        FROM document_analysis
        WHERE loan_id = %s AND filename ILIKE '%%urla%%final%%'
        LIMIT 1
    """, (loan_id,))
    
    if urla and urla.get('individual_analysis'):
        analysis = urla['individual_analysis']
        doc_summary = analysis.get('document_summary', {})
        fin_summary = doc_summary.get('financial_summary', {})
        prop_details = fin_summary.get('property_details', {})
        occupancy = prop_details.get('occupancy_type', '')
        return 'investment' in occupancy.lower()
    
    return False


def extract_rental_income(loan_id):
    """Extract monthly rental income from various document sources."""
    rental_income = None
    source_doc = None
    source_page = None
    
    # 1. Try URLA first
    urla = execute_one("""
        SELECT filename, individual_analysis
        FROM document_analysis
        WHERE loan_id = %s AND filename ILIKE '%%urla%%final%%'
        LIMIT 1
    """, (loan_id,))
    
    if urla and urla.get('individual_analysis'):
        analysis = urla['individual_analysis']
        doc_summary = analysis.get('document_summary', {})
        fin_summary = doc_summary.get('financial_summary', {})
        rental_info = fin_summary.get('rental_income', {})
        
        # Get expected monthly rental income
        expected_rent = rental_info.get('expected_monthly_rental_income', {})
        if isinstance(expected_rent, dict):
            rental_income = expected_rent.get('value')
        elif isinstance(expected_rent, (int, float)):
            rental_income = expected_rent
            
        if rental_income:
            source_doc = urla['filename']
            source_page = 1  # Usually on first pages
            return rental_income, source_doc, source_page
    
    # 2. Try underwriting docs (common for DSCR loans)
    uw_docs = execute_one("""
        SELECT filename, individual_analysis
        FROM document_analysis
        WHERE loan_id = %s AND filename ILIKE '%%underwriting%%'
        LIMIT 1
    """, (loan_id,))
    
    if uw_docs and uw_docs.get('individual_analysis'):
        analysis = uw_docs['individual_analysis']
        pages = analysis.get('pages', [])
        for i, page in enumerate(pages):
            # Check financial_data for rental income
            fin_data = page.get('financial_data', {})
            rental_data = fin_data.get('rental_income', {})
            if rental_data:
                rental_income = rental_data.get('monthly_rental_income') or rental_data.get('dscr_income') or rental_data.get('market_rent')
                if rental_income:
                    source_doc = uw_docs['filename']
                    source_page = i + 1
                    return rental_income, source_doc, source_page
            
            # Also check text_content for lease review
            text_content = page.get('text_content', {})
            lease_review = text_content.get('lease_review', [])
            for item in lease_review:
                if 'monthly rental income' in item.lower():
                    # Extract number from text like "Monthly rental income of $1,200"
                    match = re.search(r'\$?([\d,]+)', item)
                    if match:
                        rental_income = float(match.group(1).replace(',', ''))
                        source_doc = uw_docs['filename']
                        source_page = i + 1
                        return rental_income, source_doc, source_page
    
    # 3. Try conditional approval notice
    cond_approval = execute_one("""
        SELECT filename, individual_analysis
        FROM document_analysis
        WHERE loan_id = %s AND filename ILIKE '%%conditional_approval%%'
        LIMIT 1
    """, (loan_id,))
    
    if cond_approval and cond_approval.get('individual_analysis'):
        analysis = cond_approval['individual_analysis']
        doc_summary = analysis.get('document_summary', {})
        extracted = doc_summary.get('extracted_data', {})
        
        # Check loan_metrics or loan_terms for DSCR-related data
        loan_metrics = extracted.get('loan_metrics', {})
        loan_terms = extracted.get('loan_terms', {})
        
        # If we find a pre-calculated DSCR, we can back-calculate rent
        pre_dscr = loan_metrics.get('dscr') or loan_terms.get('dscr')
        pitia = loan_metrics.get('total_pitia')
        
        if pre_dscr and pitia:
            # DSCR = (Rent * 0.75) / PITIA, so Rent = DSCR * PITIA / 0.75
            rental_income = round(pre_dscr * pitia / 0.75, 2)
            source_doc = cond_approval['filename']
            source_page = 1
            return rental_income, source_doc, source_page
    
    # 4. Try appraisal (check rental comparables section)
    # Prefer main appraisal file over related docs
    appraisal = execute_one("""
        SELECT filename, individual_analysis
        FROM document_analysis
        WHERE loan_id = %s 
        AND filename ILIKE '%%appraisal%%'
        AND filename NOT ILIKE '%%acknowledgement%%'
        AND filename NOT ILIKE '%%disclosure%%'
        AND filename NOT ILIKE '%%review%%'
        AND filename NOT ILIKE '%%other%%'
        AND filename NOT ILIKE '%%related%%'
        ORDER BY 
            CASE WHEN filename ILIKE 'appraisal[_]%%' THEN 0 ELSE 1 END,
            filename
        LIMIT 1
    """, (loan_id,))
    
    if appraisal and appraisal.get('individual_analysis'):
        analysis = appraisal['individual_analysis']
        pages = analysis.get('pages', [])
        
        for i, page in enumerate(pages):
            key_data = page.get('key_data', {})
            
            # Check for subject_property in rental comparables section
            subject_prop = key_data.get('subject_property', {})
            if subject_prop:
                # Try to get indicated market rent first, then monthly rental
                market_rent = subject_prop.get('indicated_monthly_market_rent', {})
                if isinstance(market_rent, dict):
                    rental_income = market_rent.get('amount')
                    if rental_income:
                        source_doc = appraisal['filename']
                        source_page = i + 1
                        return rental_income, source_doc, source_page
                
                # Try monthly_rental
                monthly_rental = subject_prop.get('monthly_rental', {})
                if isinstance(monthly_rental, dict):
                    rental_income = monthly_rental.get('if_currently_rented')
                elif isinstance(monthly_rental, (int, float)):
                    rental_income = monthly_rental
                
                if not rental_income:
                    rental_income = subject_prop.get('adjusted_monthly_rent')
                
                if rental_income:
                    source_doc = appraisal['filename']
                    source_page = i + 1
                    return rental_income, source_doc, source_page
            
            # Also check for generic rent/market rent fields
            for key, val in key_data.items():
                key_lower = key.lower()
                if 'rent' in key_lower and 'market' in key_lower:
                    if isinstance(val, dict):
                        rental_income = val.get('value') or val.get('monthly') or val.get('amount')
                    elif isinstance(val, (int, float)):
                        rental_income = val
                    if rental_income:
                        source_doc = appraisal['filename']
                        source_page = i + 1
                        return rental_income, source_doc, source_page
    
    # 5. Try 1008 (sometimes has rental income)
    doc_1008 = execute_one("""
        SELECT filename, individual_analysis
        FROM document_analysis
        WHERE loan_id = %s AND filename ILIKE '%%1008%%final%%'
        LIMIT 1
    """, (loan_id,))
    
    if doc_1008 and doc_1008.get('individual_analysis'):
        analysis = doc_1008['individual_analysis']
        pages = analysis.get('pages', [])
        if pages:
            key_data = pages[0].get('key_data', {})
            section3 = key_data.get('section_3_underwriting_information', {})
            income = section3.get('stable_monthly_income', {})
            total_income = income.get('total', {})
            # Check for positive cash flow (rental income)
            pcf = total_income.get('positive_cash_flow_subject_property')
            if pcf and isinstance(pcf, (int, float)) and pcf > 0:
                # This is net income, estimate gross
                rental_income = pcf / 0.75  # Reverse the 75% factor
                source_doc = doc_1008['filename']
                source_page = 1
                return rental_income, source_doc, source_page
    
    return None, None, None


def extract_monthly_pi(loan_id):
    """Extract monthly P&I payment from various document sources."""
    monthly_pi = None
    source_doc = None
    source_page = None
    
    # 1. Try loan profile first (most reliable if populated)
    profile = execute_one("""
        SELECT profile_data->'loan_info'->>'monthly_pi_payment' as pi
        FROM loan_profiles
        WHERE loan_id = %s
    """, (loan_id,))
    
    if profile and profile.get('pi'):
        monthly_pi = float(profile['pi'])
        if monthly_pi:
            source_doc = 'loan_profile'
            source_page = None
            return monthly_pi, source_doc, source_page
    
    # 2. Try 1008
    doc_1008 = execute_one("""
        SELECT filename, individual_analysis
        FROM document_analysis
        WHERE loan_id = %s AND filename ILIKE '%%1008%%final%%'
        LIMIT 1
    """, (loan_id,))
    
    if doc_1008 and doc_1008.get('individual_analysis'):
        analysis = doc_1008['individual_analysis']
        pages = analysis.get('pages', [])
        if pages:
            key_data = pages[0].get('key_data', {})
            section2 = key_data.get('section_2_mortgage_information', {})
            note_info = section2.get('note_information', {})
            monthly_pi = note_info.get('initial_p_and_i_payment')
            if monthly_pi:
                source_doc = doc_1008['filename']
                source_page = 1
                return monthly_pi, source_doc, source_page
    
    # 3. Try conditional approval notice
    cond_approval = execute_one("""
        SELECT filename, individual_analysis
        FROM document_analysis
        WHERE loan_id = %s AND filename ILIKE '%%conditional_approval%%'
        LIMIT 1
    """, (loan_id,))
    
    if cond_approval and cond_approval.get('individual_analysis'):
        analysis = cond_approval['individual_analysis']
        doc_summary = analysis.get('document_summary', {})
        extracted = doc_summary.get('extracted_data', {})
        loan_metrics = extracted.get('loan_metrics', {})
        
        # Get total PITIA (includes taxes, insurance, etc.)
        pitia = loan_metrics.get('total_pitia')
        if pitia:
            monthly_pi = pitia  # For DSCR, we often use PITIA not just P&I
            source_doc = cond_approval['filename']
            source_page = 1
            return monthly_pi, source_doc, source_page
    
    # 4. Try promissory note
    note = execute_one("""
        SELECT filename, individual_analysis
        FROM document_analysis
        WHERE loan_id = %s 
        AND (filename ILIKE '%%note_0%%' OR filename ILIKE '%%note__%%final%%')
        AND filename NOT ILIKE '%%additional%%'
        LIMIT 1
    """, (loan_id,))
    
    if note and note.get('individual_analysis'):
        analysis = note['individual_analysis']
        pages = analysis.get('pages', [])
        if pages:
            key_data = pages[0].get('key_data', {})
            monthly_pi = key_data.get('monthly_payment_amount')
            if monthly_pi:
                # Clean up if string
                if isinstance(monthly_pi, str):
                    monthly_pi = float(re.sub(r'[^\d.]', '', monthly_pi))
                source_doc = note['filename']
                source_page = 1
                return monthly_pi, source_doc, source_page
    
    # 5. Calculate P&I from 1008 loan terms if available
    doc_1008 = execute_one("""
        SELECT filename, individual_analysis
        FROM document_analysis
        WHERE loan_id = %s AND filename ILIKE '%%1008%%final%%'
        LIMIT 1
    """, (loan_id,))
    
    if doc_1008 and doc_1008.get('individual_analysis'):
        analysis = doc_1008['individual_analysis']
        pages = analysis.get('pages', [])
        if pages:
            page = pages[0]
            key_data = page.get('key_data', {})
            
            # Check multiple locations for section_2
            sections = page.get('sections', {}) or key_data.get('sections', {})
            section2 = (sections.get('section_2_mortgage_information', {}) or 
                       key_data.get('section_2_mortgage_information', {}))
            
            if section2:
                note_info = section2.get('note_information', {})
                rate = note_info.get('note_rate')
                amount = note_info.get('loan_amount')
                term = note_info.get('loan_terms_in_months') or note_info.get('loan_term_in_months', 360)
                
                if rate and amount and term:
                    # Calculate P&I
                    monthly_rate = rate / 100 / 12
                    monthly_pi = amount * (monthly_rate * (1 + monthly_rate)**term) / ((1 + monthly_rate)**term - 1)
                    source_doc = f"{doc_1008['filename']} (calculated)"
                    source_page = 1
                    return round(monthly_pi, 2), source_doc, source_page
    
    return None, None, None


def calculate_dscr(rental_income, monthly_pi, vacancy_factor=0.75):
    """
    Calculate DSCR.
    
    DSCR = Net Operating Income / Debt Service
         = (Monthly Rental Income × vacancy_factor) / Monthly P&I
    
    Standard vacancy_factor is 0.75 (25% for vacancy/maintenance)
    """
    if not rental_income or not monthly_pi or monthly_pi == 0:
        return None
    
    net_rental = rental_income * vacancy_factor
    dscr = net_rental / monthly_pi
    return round(dscr, 3)


def get_dscr_rating(dscr):
    """Get RAG rating for DSCR."""
    if dscr is None:
        return None
    if dscr >= 1.25:
        return 'G'  # Green - Strong
    elif dscr >= 1.0:
        return 'A'  # Amber - Acceptable
    else:
        return 'R'  # Red - Negative cash flow


def save_dscr_result(loan_id, result):
    """Save DSCR calculation result to loan_profiles."""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Update loan_profiles with DSCR data
        cur.execute("""
            UPDATE loan_profiles
            SET profile_data = jsonb_set(
                COALESCE(profile_data, '{}'::jsonb),
                '{dscr_analysis}',
                %s::jsonb
            )
            WHERE loan_id = %s
        """, (json.dumps(result), loan_id))
        
        conn.commit()
        print(f"✅ Saved DSCR analysis for loan {loan_id}")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error saving DSCR: {e}")
    finally:
        cur.close()
        conn.close()


def calculate_dscr_for_loan(loan_id):
    """Main function to calculate DSCR for a single loan."""
    print(f"\n{'='*80}")
    print(f"📊 DSCR CALCULATION FOR LOAN ID {loan_id}")
    print(f"{'='*80}")
    
    # Check if investment property
    if not is_investment_property(loan_id):
        print(f"⏭️  Loan {loan_id} is NOT an investment property - skipping DSCR")
        return None
    
    print(f"✅ Confirmed: Investment Property")
    
    # Extract rental income
    rental_income, rent_doc, rent_page = extract_rental_income(loan_id)
    if rental_income:
        print(f"📄 Rental Income: ${rental_income:,.2f}/month")
        print(f"   Source: {rent_doc} (Page {rent_page})")
    else:
        print(f"⚠️  Could not find rental income data")
    
    # Extract monthly P&I
    monthly_pi, pi_doc, pi_page = extract_monthly_pi(loan_id)
    if monthly_pi:
        print(f"📄 Monthly P&I: ${monthly_pi:,.2f}")
        print(f"   Source: {pi_doc} (Page {pi_page})")
    else:
        print(f"⚠️  Could not find monthly P&I payment")
    
    # Calculate DSCR
    if rental_income and monthly_pi:
        dscr = calculate_dscr(rental_income, monthly_pi)
        rating = get_dscr_rating(dscr)
        net_rental = rental_income * 0.75
        
        print(f"\n📈 DSCR CALCULATION:")
        print(f"   Gross Monthly Rent: ${rental_income:,.2f}")
        print(f"   Net Rent (75%):     ${net_rental:,.2f}")
        print(f"   Monthly P&I:        ${monthly_pi:,.2f}")
        print(f"   ─────────────────────────────")
        print(f"   DSCR = ${net_rental:,.2f} / ${monthly_pi:,.2f} = {dscr:.3f}")
        
        rating_desc = {
            'G': '🟢 STRONG (≥1.25)',
            'A': '🟡 ACCEPTABLE (1.0-1.25)',
            'R': '🔴 NEGATIVE CASH FLOW (<1.0)'
        }
        print(f"   Rating: {rating_desc.get(rating, 'Unknown')}")
        
        # Build result
        result = {
            'dscr': dscr,
            'dscr_rating': rating,
            'gross_monthly_rent': rental_income,
            'net_monthly_rent': net_rental,
            'monthly_pi': monthly_pi,
            'vacancy_factor': 0.75,
            'rent_source': {
                'document': rent_doc,
                'page': rent_page
            },
            'pi_source': {
                'document': pi_doc,
                'page': pi_page
            },
            'calculation_formula': 'DSCR = (Gross Rent × 0.75) / Monthly P&I'
        }
        
        # Save result
        save_dscr_result(loan_id, result)
        
        return result
    else:
        print(f"\n❌ Cannot calculate DSCR - missing data")
        result = {
            'dscr': None,
            'dscr_rating': None,
            'error': 'Missing rental income or P&I data',
            'gross_monthly_rent': rental_income,
            'monthly_pi': monthly_pi
        }
        save_dscr_result(loan_id, result)
        return result


def run_dscr_for_all_investment_properties():
    """Run DSCR calculation for all investment property loans."""
    # Get all loans with profiles
    loans = execute_query("""
        SELECT lp.loan_id, l.loan_number,
               lp.profile_data->'property_info'->>'occupancy' as occupancy
        FROM loan_profiles lp
        JOIN loans l ON l.id = lp.loan_id
        WHERE lp.profile_data IS NOT NULL
        ORDER BY lp.loan_id
    """)
    
    print(f"\n🏠 DSCR CALCULATION FOR INVESTMENT PROPERTIES")
    print(f"{'='*80}")
    print(f"Found {len(loans)} loans with profiles")
    
    investment_count = 0
    calculated_count = 0
    
    for loan in loans:
        occupancy = loan.get('occupancy', '').lower()
        if 'investment' in occupancy:
            investment_count += 1
            result = calculate_dscr_for_loan(loan['loan_id'])
            if result and result.get('dscr'):
                calculated_count += 1
    
    print(f"\n{'='*80}")
    print(f"📊 SUMMARY:")
    print(f"   Total loans: {len(loans)}")
    print(f"   Investment properties: {investment_count}")
    print(f"   DSCR calculated: {calculated_count}")


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1:
        loan_id = int(sys.argv[1])
        calculate_dscr_for_loan(loan_id)
    else:
        # Run for all investment properties
        run_dscr_for_all_investment_properties()

