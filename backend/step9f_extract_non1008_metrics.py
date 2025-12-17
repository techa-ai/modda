"""
Step 9f: Extract Rate, DTI, CLTV for Non-1008 Loans

For loans without 1008 documents, extract key metrics from alternative sources:
- HELOC Agreement: interest rate, credit limit
- Rate Lock Confirmation: rate, DTI, CLTV, FICO
- Closing Disclosure: rate, fees, closing costs
- Promissory Note: rate, payment amount
- URLA/Non-Standard Loan App: income, debts for DTI calculation
"""

import json
import re
from db import execute_query, execute_one, get_db_connection


def get_loans_needing_metrics():
    """Find loans without 1008 or with missing key metrics."""
    return execute_query("""
        SELECT lp.loan_id, l.loan_number, lp.analysis_source,
               lp.profile_data
        FROM loan_profiles lp
        JOIN loans l ON l.id = lp.loan_id
        WHERE (
            lp.analysis_source NOT ILIKE '%%1008%%'
            OR lp.profile_data->'loan_info'->>'interest_rate' IS NULL
            OR lp.profile_data->'ratios'->>'dti_back_end_percent' IS NULL
        )
        ORDER BY lp.loan_id
    """)


def parse_percentage(value):
    """Parse percentage from string like '47.10%' to float 47.10."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = re.search(r'([\d.]+)', value.replace(',', ''))
        if match:
            return float(match.group(1))
    return None


def parse_currency(value):
    """Parse currency from string like '$99,000.00' to float 99000.00."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = re.search(r'([\d,.]+)', value.replace(',', ''))
        if match:
            return float(match.group(1).replace(',', ''))
    return None


def extract_from_heloc_agreement(loan_id):
    """Extract rate and loan details from HELOC agreement."""
    result = {
        'interest_rate': None,
        'credit_limit': None,
        'margin': None,
        'source': None
    }
    
    heloc = execute_one("""
        SELECT filename, individual_analysis
        FROM document_analysis
        WHERE loan_id = %s AND filename ILIKE '%%heloc_agreement%%final%%'
        LIMIT 1
    """, (loan_id,))
    
    if heloc and heloc.get('individual_analysis'):
        analysis = heloc['individual_analysis']
        pages = analysis.get('pages', [])
        
        if pages:
            key_data = pages[0].get('key_data', {})
            
            # Direct fields
            rate = key_data.get('initial_interest_rate')
            if rate:
                result['interest_rate'] = parse_percentage(rate)
                result['source'] = heloc['filename']
            
            # Nested in loan_details
            loan_details = key_data.get('loan_details', {})
            if loan_details:
                if not result['interest_rate']:
                    apr = loan_details.get('annual_percentage_rate')
                    if apr:
                        result['interest_rate'] = parse_percentage(apr)
                        result['source'] = heloc['filename']
                
                result['margin'] = parse_percentage(loan_details.get('margin'))
                result['credit_limit'] = parse_currency(loan_details.get('credit_limit'))
    
    return result


def extract_from_rate_lock(loan_id):
    """Extract rate, DTI, CLTV from rate lock confirmation."""
    result = {
        'interest_rate': None,
        'dti': None,
        'cltv': None,
        'ltv': None,
        'fico': None,
        'source': None
    }
    
    rate_lock = execute_one("""
        SELECT filename, individual_analysis
        FROM document_analysis
        WHERE loan_id = %s AND filename ILIKE '%%rate_lock%%'
        ORDER BY filename DESC
        LIMIT 1
    """, (loan_id,))
    
    if rate_lock and rate_lock.get('individual_analysis'):
        analysis = rate_lock['individual_analysis']
        doc_summary = analysis.get('document_summary', {})
        extracted = doc_summary.get('extracted_data', {})
        
        # Loan terms
        loan_terms = extracted.get('loan_terms', {})
        if loan_terms:
            rate = loan_terms.get('note_rate')
            if rate:
                result['interest_rate'] = parse_percentage(rate)
                result['source'] = rate_lock['filename']
        
        # Equity position
        equity = extracted.get('equity_position', {})
        if equity:
            result['cltv'] = parse_percentage(equity.get('cltv'))
            result['ltv'] = parse_percentage(equity.get('ltv'))
        
        # Borrower information
        borrower_info = extracted.get('borrower_information', {})
        if borrower_info:
            result['dti'] = parse_percentage(borrower_info.get('dti_ratio'))
            result['fico'] = borrower_info.get('fico_score')
    
    return result


def extract_from_closing_disclosure(loan_id):
    """Extract rate from closing disclosure."""
    result = {
        'interest_rate': None,
        'source': None
    }
    
    cd = execute_one("""
        SELECT filename, individual_analysis
        FROM document_analysis
        WHERE loan_id = %s 
        AND filename ILIKE '%%closing_disclosure%%final%%'
        LIMIT 1
    """, (loan_id,))
    
    if cd and cd.get('individual_analysis'):
        analysis = cd['individual_analysis']
        pages = analysis.get('pages', [])
        
        for page in pages:
            key_data = page.get('key_data', {})
            
            # Look for interest rate
            for key in ['interest_rate', 'note_rate', 'rate']:
                if key in key_data:
                    rate = parse_percentage(key_data[key])
                    if rate:
                        result['interest_rate'] = rate
                        result['source'] = cd['filename']
                        return result
            
            # Check loan_terms section
            loan_terms = key_data.get('loan_terms', {})
            if loan_terms:
                rate = loan_terms.get('interest_rate') or loan_terms.get('note_rate')
                if rate:
                    result['interest_rate'] = parse_percentage(rate)
                    result['source'] = cd['filename']
                    return result
    
    return result


def extract_from_urla(loan_id):
    """Extract income and calculate DTI from URLA."""
    result = {
        'total_income': None,
        'total_debts': None,
        'dti': None,
        'source': None
    }
    
    urla = execute_one("""
        SELECT filename, individual_analysis
        FROM document_analysis
        WHERE loan_id = %s 
        AND (filename ILIKE '%%urla%%final%%' OR filename ILIKE '%%non_standard%%final%%')
        ORDER BY 
            CASE WHEN filename ILIKE '%%urla%%' THEN 0 ELSE 1 END
        LIMIT 1
    """, (loan_id,))
    
    if urla and urla.get('individual_analysis'):
        analysis = urla['individual_analysis']
        doc_summary = analysis.get('document_summary', {})
        fin_summary = doc_summary.get('financial_summary', {})
        
        # Get income
        income_section = fin_summary.get('income', {})
        if income_section:
            monthly = income_section.get('monthly_income', {})
            if monthly:
                total = sum(v for v in monthly.values() if isinstance(v, (int, float)))
                if total > 0:
                    result['total_income'] = total
            
            # Try gross monthly income
            gross = income_section.get('applicant_gross_monthly_income')
            if gross:
                result['total_income'] = parse_currency(gross)
        
        # Get liabilities
        liabilities = fin_summary.get('liabilities', {})
        if liabilities:
            total_payment = 0
            for key, val in liabilities.items():
                if isinstance(val, dict):
                    payment = val.get('total_monthly_payment')
                    if payment:
                        total_payment += parse_currency(payment) or 0
            if total_payment > 0:
                result['total_debts'] = total_payment
        
        result['source'] = urla['filename']
    
    return result


def calculate_dti(income, proposed_payment, other_debts=0):
    """Calculate DTI ratio."""
    if not income or income <= 0:
        return None
    
    total_obligations = (proposed_payment or 0) + (other_debts or 0)
    return round(total_obligations / income * 100, 2)


def calculate_cltv_from_profile(profile):
    """Calculate CLTV from profile data if possible."""
    if not profile:
        return None
    
    property_info = profile.get('property_info', {})
    loan_info = profile.get('loan_info', {})
    credit_profile = profile.get('credit_profile', {})
    
    property_value = property_info.get('appraised_value') or property_info.get('purchase_price')
    new_loan_amount = loan_info.get('loan_amount')
    existing_mortgage = credit_profile.get('existing_first_mortgage_balance') or 0
    
    if not property_value or not new_loan_amount:
        return None
    
    total_debt = new_loan_amount + existing_mortgage
    cltv = round(total_debt / property_value * 100, 2)
    
    return cltv


def calculate_dti_from_profile(profile):
    """Calculate DTI from profile data if possible."""
    if not profile:
        return None
    
    income_profile = profile.get('income_profile', {})
    loan_info = profile.get('loan_info', {})
    
    monthly_income = income_profile.get('total_monthly_income')
    if not monthly_income or monthly_income <= 0:
        return None
    
    # Get housing expenses
    housing_payment = loan_info.get('monthly_pi_payment') or 0
    
    # Get other debts
    credit_profile = profile.get('credit_profile', {})
    total_debts = credit_profile.get('total_monthly_debts') or 0
    
    total_obligations = housing_payment + total_debts
    
    if total_obligations <= 0:
        return None
    
    dti = round(total_obligations / monthly_income * 100, 2)
    return dti


def update_loan_profile(loan_id, updates):
    """Update loan profile with extracted metrics."""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Get current profile
        cur.execute("""
            SELECT profile_data FROM loan_profiles WHERE loan_id = %s
        """, (loan_id,))
        result = cur.fetchone()
        
        if not result:
            print(f"  ⚠️ No profile found for loan {loan_id}")
            return
        
        profile = result['profile_data'] or {}
        
        # Update loan_info
        loan_info = profile.get('loan_info', {})
        if updates.get('interest_rate') and not loan_info.get('interest_rate'):
            loan_info['interest_rate'] = updates['interest_rate']
            loan_info['interest_rate_source'] = updates.get('rate_source', 'alternative')
        
        if updates.get('credit_limit') and not loan_info.get('loan_amount'):
            loan_info['loan_amount'] = updates['credit_limit']
        
        profile['loan_info'] = loan_info
        
        # Update ratios
        ratios = profile.get('ratios', {})
        if updates.get('dti') and not ratios.get('dti_back_end_percent'):
            ratios['dti_back_end_percent'] = updates['dti']
        
        if updates.get('cltv') and not ratios.get('cltv_percent'):
            ratios['cltv_percent'] = updates['cltv']
        
        if updates.get('ltv') and not ratios.get('ltv_percent'):
            ratios['ltv_percent'] = updates['ltv']
        
        profile['ratios'] = ratios
        
        # Update credit profile
        if updates.get('fico'):
            credit = profile.get('credit_profile', {})
            if not credit.get('credit_score'):
                credit['credit_score'] = updates['fico']
                profile['credit_profile'] = credit
        
        # Track sources
        if not profile.get('alternative_sources'):
            profile['alternative_sources'] = []
        
        sources = updates.get('sources', [])
        for src in sources:
            if src and src not in profile['alternative_sources']:
                profile['alternative_sources'].append(src)
        
        # Save
        cur.execute("""
            UPDATE loan_profiles 
            SET profile_data = %s
            WHERE loan_id = %s
        """, (json.dumps(profile), loan_id))
        
        conn.commit()
        print(f"  ✅ Updated profile for loan {loan_id}")
        
    except Exception as e:
        conn.rollback()
        print(f"  ❌ Error updating loan {loan_id}: {e}")
    finally:
        cur.close()
        conn.close()


def process_loan(loan_id, loan_number, current_profile):
    """Process a single loan to extract missing metrics."""
    print(f"\n{'='*60}")
    print(f"📊 LOAN {loan_id} (#{loan_number})")
    print(f"{'='*60}")
    
    updates = {
        'sources': []
    }
    
    # Current values
    loan_info = current_profile.get('loan_info', {}) if current_profile else {}
    ratios = current_profile.get('ratios', {}) if current_profile else {}
    
    current_rate = loan_info.get('interest_rate')
    current_dti = ratios.get('dti_back_end_percent')
    current_cltv = ratios.get('cltv_percent')
    
    print(f"  Current: Rate={current_rate}, DTI={current_dti}, CLTV={current_cltv}")
    
    # 1. Try HELOC Agreement
    if not current_rate:
        heloc_data = extract_from_heloc_agreement(loan_id)
        if heloc_data['interest_rate']:
            updates['interest_rate'] = heloc_data['interest_rate']
            updates['rate_source'] = heloc_data['source']
            updates['sources'].append(heloc_data['source'])
            print(f"  📄 HELOC: Rate={heloc_data['interest_rate']}%")
        if heloc_data['credit_limit']:
            updates['credit_limit'] = heloc_data['credit_limit']
    
    # 2. Try Rate Lock
    rate_lock_data = extract_from_rate_lock(loan_id)
    if rate_lock_data['source']:
        updates['sources'].append(rate_lock_data['source'])
        
        if not updates.get('interest_rate') and rate_lock_data['interest_rate']:
            updates['interest_rate'] = rate_lock_data['interest_rate']
            updates['rate_source'] = rate_lock_data['source']
            print(f"  📄 Rate Lock: Rate={rate_lock_data['interest_rate']}%")
        
        if not current_dti and rate_lock_data['dti']:
            updates['dti'] = rate_lock_data['dti']
            print(f"  📄 Rate Lock: DTI={rate_lock_data['dti']}%")
        
        if not current_cltv and rate_lock_data['cltv']:
            updates['cltv'] = rate_lock_data['cltv']
            print(f"  📄 Rate Lock: CLTV={rate_lock_data['cltv']}%")
        
        if rate_lock_data['ltv']:
            updates['ltv'] = rate_lock_data['ltv']
        
        if rate_lock_data['fico']:
            updates['fico'] = rate_lock_data['fico']
            print(f"  📄 Rate Lock: FICO={rate_lock_data['fico']}")
    
    # 3. Try Closing Disclosure for rate
    if not updates.get('interest_rate'):
        cd_data = extract_from_closing_disclosure(loan_id)
        if cd_data['interest_rate']:
            updates['interest_rate'] = cd_data['interest_rate']
            updates['rate_source'] = cd_data['source']
            updates['sources'].append(cd_data['source'])
            print(f"  📄 Closing Disclosure: Rate={cd_data['interest_rate']}%")
    
    # 4. Try URLA for DTI calculation
    if not updates.get('dti'):
        urla_data = extract_from_urla(loan_id)
        if urla_data['total_income']:
            print(f"  📄 URLA: Income=${urla_data['total_income']:,.2f}/mo")
            
            # Get proposed payment from profile
            proposed = loan_info.get('monthly_pi_payment', 0) or 0
            other_debts = urla_data.get('total_debts', 0) or 0
            
            if urla_data['total_income'] > 0:
                dti = calculate_dti(urla_data['total_income'], proposed, other_debts)
                if dti:
                    updates['dti'] = dti
                    updates['sources'].append(urla_data['source'])
                    print(f"  📊 Calculated DTI: {dti}%")
    
    # 5. Calculate CLTV from profile if not already set
    if not current_cltv and not updates.get('cltv'):
        cltv = calculate_cltv_from_profile(current_profile)
        if cltv:
            updates['cltv'] = cltv
            print(f"  📊 Calculated CLTV: {cltv}%")
    
    # 6. For HELOCs - if no first mortgage, CLTV = LTV
    if not updates.get('cltv') and loan_info.get('is_heloc'):
        ltv = ratios.get('ltv_percent')
        if ltv:
            updates['cltv'] = ltv
            print(f"  📊 HELOC CLTV (no first mortgage): {ltv}%")
    
    # Update profile if we have new data
    if any(updates.get(k) for k in ['interest_rate', 'dti', 'cltv', 'ltv', 'fico']):
        update_loan_profile(loan_id, updates)
        return True
    else:
        print(f"  ℹ️ No new metrics found")
        return False


def run_extraction():
    """Main function to extract metrics for all non-1008 loans."""
    print("🔍 EXTRACTING METRICS FOR NON-1008 LOANS")
    print("=" * 60)
    
    loans = get_loans_needing_metrics()
    print(f"Found {len(loans)} loans needing metrics\n")
    
    updated = 0
    for loan in loans:
        if process_loan(loan['loan_id'], loan['loan_number'], loan['profile_data']):
            updated += 1
    
    print(f"\n{'='*60}")
    print(f"📊 SUMMARY: Updated {updated}/{len(loans)} loans")


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1:
        loan_id = int(sys.argv[1])
        loan = execute_one("""
            SELECT lp.loan_id, l.loan_number, lp.profile_data
            FROM loan_profiles lp
            JOIN loans l ON l.id = lp.loan_id
            WHERE lp.loan_id = %s
        """, (loan_id,))
        if loan:
            process_loan(loan['loan_id'], loan['loan_number'], loan['profile_data'])
    else:
        run_extraction()

