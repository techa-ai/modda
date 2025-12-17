"""
Summary Step S4: Verify Key Loan Attributes

Verifies the four key loan attributes for summary badges (I, D, C, V):
1. Income (I) - Verify borrower income from pay stubs, W-2s, tax returns
2. Debt/Expense (D) - Verify debts from credit report, mortgage statements  
3. Credit Score (C) - Verify credit score from credit report
4. Property Value (V) - Verify property value from appraisal

This step runs after S1-S3 to determine verification badge status.
Checks existing evidence_files first, then looks for new document sources.
"""

import json
import re
from db import execute_query, execute_one, get_db_connection


def parse_number(value):
    """Parse number from string, handling currency and percentages."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        # Remove currency symbols, commas, percentages
        cleaned = re.sub(r'[$,%]', '', value.replace(',', ''))
        match = re.search(r'([\d.]+)', cleaned)
        if match:
            return float(match.group(1))
    return None


def verify_income(loan_id, profile):
    """
    Verify income from multiple sources:
    - Existing verified evidence in evidence_files
    - Pay stubs
    - W-2 forms
    - Tax returns
    - Employment verification
    - URLA/1003
    """
    result = {
        'verified': False,
        'profile_value': None,
        'document_value': None,
        'variance_percent': None,
        'sources': [],
        'notes': []
    }
    
    income_profile = profile.get('income_profile', {})
    profile_income = income_profile.get('total_monthly_income')
    
    if not profile_income:
        result['notes'].append('No income in profile to verify')
        return result
    
    result['profile_value'] = profile_income
    
    # First, check if we already have verified income evidence
    existing_income_evidence = execute_query("""
        SELECT ef.file_name, ef.verification_status, fa.attribute_label
        FROM evidence_files ef
        JOIN form_1008_attributes fa ON fa.id = ef.attribute_id
        WHERE ef.loan_id = %s 
        AND ef.verification_status = 'verified'
        AND (fa.attribute_label ILIKE '%%income%%' 
             OR fa.attribute_label ILIKE '%%borrower total income%%')
        LIMIT 5
    """, (loan_id,))
    
    if existing_income_evidence:
        for ev in existing_income_evidence:
            result['sources'].append({
                'document': ev['file_name'],
                'value': profile_income,  # Use profile value as it was already verified
                'type': f"existing_verified ({ev['attribute_label']})"
            })
        result['verified'] = True
        result['document_value'] = profile_income
        result['variance_percent'] = 0
        result['notes'].append(f"Previously verified: {existing_income_evidence[0]['file_name']}")
        return result
    
    # 1. Check pay stubs
    pay_stubs = execute_query("""
        SELECT filename, individual_analysis
        FROM document_analysis
        WHERE loan_id = %s 
        AND filename ILIKE '%%pay%%stub%%'
        ORDER BY filename DESC
        LIMIT 3
    """, (loan_id,))
    
    for stub in pay_stubs:
        if stub.get('individual_analysis'):
            analysis = stub['individual_analysis']
            doc_summary = analysis.get('document_summary', {})
            fin_summary = doc_summary.get('financial_summary', {})
            
            # Check current_period for gross earnings
            current_period = fin_summary.get('current_period', {})
            if current_period:
                gross = current_period.get('gross_earnings') or current_period.get('gross_pay')
                if gross:
                    result['sources'].append({
                        'document': stub['filename'],
                        'value': parse_number(gross),
                        'type': 'current_period_gross'
                    })
            
            # Look for direct income values
            gross = fin_summary.get('gross_pay') or fin_summary.get('gross_income') or fin_summary.get('gross_earnings')
            if gross:
                result['sources'].append({
                    'document': stub['filename'],
                    'value': parse_number(gross),
                    'type': 'gross_pay'
                })
            
            # Check pages for key_data
            pages = analysis.get('pages', [])
            for page in pages:
                key_data = page.get('key_data', {})
                for key in ['gross_pay', 'gross_earnings', 'current_gross', 'total_gross', 'gross_this_period']:
                    if key in key_data:
                        val = parse_number(key_data[key])
                        if val and val > 0:
                            result['sources'].append({
                                'document': stub['filename'],
                                'value': val,
                                'type': key
                            })
    
    # 2. Check W-2 forms
    w2s = execute_query("""
        SELECT filename, individual_analysis
        FROM document_analysis
        WHERE loan_id = %s 
        AND filename ILIKE '%%w2%%'
        ORDER BY filename DESC
        LIMIT 3
    """, (loan_id,))
    
    for w2 in w2s:
        if w2.get('individual_analysis'):
            analysis = w2['individual_analysis']
            pages = analysis.get('pages', [])
            for page in pages:
                key_data = page.get('key_data', {})
                # Box 1 = wages, tips, other compensation
                wages = key_data.get('box_1_wages') or key_data.get('wages_tips_other')
                if wages:
                    result['sources'].append({
                        'document': w2['filename'],
                        'value': parse_number(wages),
                        'type': 'w2_annual_wages'
                    })
    
    # 3. Check URLA/1003
    urla = execute_one("""
        SELECT filename, individual_analysis
        FROM document_analysis
        WHERE loan_id = %s 
        AND (filename ILIKE '%%urla%%final%%' OR filename ILIKE '%%1003%%')
        ORDER BY filename
        LIMIT 1
    """, (loan_id,))
    
    if urla and urla.get('individual_analysis'):
        analysis = urla['individual_analysis']
        doc_summary = analysis.get('document_summary', {})
        fin_summary = doc_summary.get('financial_summary', {})
        
        income = fin_summary.get('income', {})
        monthly = income.get('monthly_income', {})
        
        if monthly:
            total = sum(v for v in monthly.values() if isinstance(v, (int, float)))
            if total > 0:
                result['sources'].append({
                    'document': urla['filename'],
                    'value': total,
                    'type': 'urla_monthly_income'
                })
    
    # 4. Check employment verification
    voe = execute_one("""
        SELECT filename, individual_analysis
        FROM document_analysis
        WHERE loan_id = %s 
        AND (filename ILIKE '%%verification%%employment%%' OR filename ILIKE '%%voe%%')
        LIMIT 1
    """, (loan_id,))
    
    if voe and voe.get('individual_analysis'):
        analysis = voe['individual_analysis']
        doc_summary = analysis.get('document_summary', {})
        
        # Look for income in various locations
        income_val = doc_summary.get('monthly_income') or doc_summary.get('annual_salary')
        if income_val:
            result['sources'].append({
                'document': voe['filename'],
                'value': parse_number(income_val),
                'type': 'voe_income'
            })
    
    # Evaluate verification
    if result['sources']:
        # Find best match (closest to profile value)
        best_match = None
        best_variance = float('inf')
        
        for src in result['sources']:
            doc_val = src['value']
            if doc_val and doc_val > 0:
                # Normalize to monthly if annual
                if 'annual' in src['type'] or 'w2' in src['type']:
                    doc_val = doc_val / 12
                
                variance = abs(doc_val - profile_income) / profile_income * 100
                if variance < best_variance:
                    best_variance = variance
                    best_match = src
                    result['document_value'] = doc_val
        
        if best_match:
            result['variance_percent'] = round(best_variance, 2)
            # Verified if within 10% tolerance
            result['verified'] = best_variance <= 10
            result['notes'].append(f"Best match from {best_match['document']}: ${result['document_value']:,.2f}/mo")
    
    if not result['sources']:
        result['notes'].append('No income documents found for verification')
    
    return result


def verify_debt(loan_id, profile):
    """
    Verify debt/expenses from:
    - Existing verified evidence in evidence_files
    - Credit report
    - Mortgage statements
    - URLA liabilities section
    - Check for DOCUMENTATION GAPS
    """
    result = {
        'verified': False,
        'profile_value': None,
        'document_value': None,
        'variance_percent': None,
        'sources': [],
        'notes': []
    }
    
    credit_profile = profile.get('credit_profile', {})
    profile_debt = credit_profile.get('total_monthly_debts')
    
    # Also check ratios for DTI-derived debt
    ratios = profile.get('ratios', {})
    income_profile = profile.get('income_profile', {})
    
    if not profile_debt:
        # Try to derive from DTI and income
        dti = ratios.get('dti_back_end_percent')
        income = income_profile.get('total_monthly_income')
        if dti and income:
            profile_debt = (dti / 100) * income
    
    if not profile_debt:
        result['notes'].append('No debt amount in profile to verify')
        return result
    
    result['profile_value'] = profile_debt
    
    # Check for DOCUMENTATION GAPS first
    gaps = execute_query("""
        SELECT ef.file_name, ef.notes, fa.attribute_label
        FROM evidence_files ef
        JOIN form_1008_attributes fa ON fa.id = ef.attribute_id
        WHERE ef.loan_id = %s 
        AND ef.notes ILIKE '%%documentation gap%%'
    """, (loan_id,))
    
    if gaps:
        result['verified'] = False
        result['notes'].append(f"DOCUMENTATION GAP: {len(gaps)} debt items missing documentation")
        for gap in gaps[:3]:
            result['notes'].append(f"  - {gap['attribute_label']}")
        return result
    
    # First, check if we already have verified debt/expense evidence
    existing_debt_evidence = execute_query("""
        SELECT ef.file_name, ef.verification_status, fa.attribute_label
        FROM evidence_files ef
        JOIN form_1008_attributes fa ON fa.id = ef.attribute_id
        WHERE ef.loan_id = %s 
        AND ef.verification_status = 'verified'
        AND (fa.attribute_label ILIKE '%%expense%%' 
             OR fa.attribute_label ILIKE '%%payment%%'
             OR fa.attribute_label ILIKE '%%total all monthly%%'
             OR fa.attribute_label ILIKE '%%total primary housing%%')
        LIMIT 5
    """, (loan_id,))
    
    if existing_debt_evidence:
        for ev in existing_debt_evidence:
            result['sources'].append({
                'document': ev['file_name'],
                'value': profile_debt,
                'type': f"existing_verified ({ev['attribute_label']})"
            })
        result['verified'] = True
        result['document_value'] = profile_debt
        result['variance_percent'] = 0
        result['notes'].append(f"Previously verified: {existing_debt_evidence[0]['file_name']}")
        return result
    
    # 1. Check credit report
    credit_report = execute_one("""
        SELECT filename, individual_analysis
        FROM document_analysis
        WHERE loan_id = %s 
        AND filename ILIKE '%%credit_report%%final%%'
        LIMIT 1
    """, (loan_id,))
    
    if credit_report and credit_report.get('individual_analysis'):
        analysis = credit_report['individual_analysis']
        doc_summary = analysis.get('document_summary', {})
        fin_summary = doc_summary.get('financial_summary', {})
        
        # Check important_values.monthly_payments
        important = doc_summary.get('important_values', {})
        monthly_payments = important.get('monthly_payments', [])
        if monthly_payments:
            total = sum(parse_number(p.get('value', 0)) or 0 for p in monthly_payments if isinstance(p, dict))
            if total > 0:
                result['sources'].append({
                    'document': credit_report['filename'],
                    'value': total,
                    'type': 'important_values_monthly_payments'
                })
        
        # Look for total monthly payments in financial_summary
        total_payments = fin_summary.get('total_monthly_payments') or fin_summary.get('total_debt_payments')
        if total_payments:
            result['sources'].append({
                'document': credit_report['filename'],
                'value': parse_number(total_payments),
                'type': 'credit_report_total'
            })
        
        # Sum up individual tradelines
        tradelines = fin_summary.get('tradelines', [])
        if tradelines:
            total = sum(parse_number(t.get('monthly_payment', 0)) or 0 for t in tradelines)
            if total > 0:
                result['sources'].append({
                    'document': credit_report['filename'],
                    'value': total,
                    'type': 'credit_report_tradelines'
                })
    
    # 2. Check URLA liabilities
    urla = execute_one("""
        SELECT filename, individual_analysis
        FROM document_analysis
        WHERE loan_id = %s 
        AND filename ILIKE '%%urla%%final%%'
        LIMIT 1
    """, (loan_id,))
    
    if urla and urla.get('individual_analysis'):
        analysis = urla['individual_analysis']
        doc_summary = analysis.get('document_summary', {})
        fin_summary = doc_summary.get('financial_summary', {})
        
        liabilities = fin_summary.get('liabilities', {})
        total_payment = 0
        
        for category, data in liabilities.items():
            if isinstance(data, dict):
                payment = parse_number(data.get('total_monthly_payment'))
                if payment:
                    total_payment += payment
        
        if total_payment > 0:
            result['sources'].append({
                'document': urla['filename'],
                'value': total_payment,
                'type': 'urla_liabilities'
            })
    
    # 3. Check mortgage statement
    mortgage_stmt = execute_one("""
        SELECT filename, individual_analysis
        FROM document_analysis
        WHERE loan_id = %s 
        AND filename ILIKE '%%mortgage%%statement%%'
        LIMIT 1
    """, (loan_id,))
    
    if mortgage_stmt and mortgage_stmt.get('individual_analysis'):
        analysis = mortgage_stmt['individual_analysis']
        pages = analysis.get('pages', [])
        for page in pages:
            key_data = page.get('key_data', {})
            payment = key_data.get('monthly_payment') or key_data.get('payment_amount')
            if payment:
                result['sources'].append({
                    'document': mortgage_stmt['filename'],
                    'value': parse_number(payment),
                    'type': 'mortgage_payment'
                })
    
    # Evaluate
    if result['sources']:
        best_match = None
        best_variance = float('inf')
        
        for src in result['sources']:
            doc_val = src['value']
            if doc_val and doc_val > 0 and profile_debt > 0:
                variance = abs(doc_val - profile_debt) / profile_debt * 100
                if variance < best_variance:
                    best_variance = variance
                    best_match = src
                    result['document_value'] = doc_val
        
        if best_match:
            result['variance_percent'] = round(best_variance, 2)
            result['verified'] = best_variance <= 15  # 15% tolerance for debts
            result['notes'].append(f"Best match from {best_match['document']}: ${result['document_value']:,.2f}/mo")
    
    if not result['sources']:
        result['notes'].append('No debt verification documents found')
    
    return result


def verify_credit_score(loan_id, profile):
    """
    Verify credit score from credit report.
    """
    result = {
        'verified': False,
        'profile_value': None,
        'document_value': None,
        'variance_percent': None,
        'sources': [],
        'notes': []
    }
    
    credit_profile = profile.get('credit_profile', {})
    profile_score = credit_profile.get('credit_score')
    
    if not profile_score:
        result['notes'].append('No credit score in profile to verify')
        return result
    
    result['profile_value'] = profile_score
    
    # Check credit report
    credit_report = execute_one("""
        SELECT filename, individual_analysis
        FROM document_analysis
        WHERE loan_id = %s 
        AND filename ILIKE '%%credit_report%%final%%'
        LIMIT 1
    """, (loan_id,))
    
    if credit_report and credit_report.get('individual_analysis'):
        analysis = credit_report['individual_analysis']
        doc_summary = analysis.get('document_summary', {})
        
        # Check important_values.credit_scores first (most reliable)
        important = doc_summary.get('important_values', {})
        credit_scores_list = important.get('credit_scores', [])
        
        for score_entry in credit_scores_list:
            if isinstance(score_entry, dict):
                val = score_entry.get('value')
                label = score_entry.get('label', '')
                if val and 300 <= val <= 850:
                    result['sources'].append({
                        'document': credit_report['filename'],
                        'value': int(val),
                        'location': f'important_values.credit_scores ({label})'
                    })
        
        # Also check other locations
        score_locations = [
            ('document_summary.credit_score', doc_summary.get('credit_score')),
            ('document_summary.fico_score', doc_summary.get('fico_score')),
        ]
        
        # Check extracted_data
        extracted = doc_summary.get('extracted_data', {})
        if extracted:
            score_locations.append(('extracted_data.credit_score', extracted.get('credit_score')))
            score_locations.append(('extracted_data.fico_score', extracted.get('fico_score')))
        
        # Check key_entities
        entities = doc_summary.get('key_entities', {})
        if entities:
            scores = entities.get('credit_scores', [])
            if scores and len(scores) > 0:
                score_locations.append(('key_entities.credit_scores', scores[0]))
        
        # Check pages
        pages = analysis.get('pages', [])
        for i, page in enumerate(pages[:3]):
            key_data = page.get('key_data', {})
            for key in ['credit_score', 'fico_score', 'vantage_score', 'representative_score']:
                if key in key_data:
                    score_locations.append((f'page_{i+1}.{key}', key_data[key]))
        
        for location, val in score_locations:
            if val:
                parsed = parse_number(val)
                if parsed and 300 <= parsed <= 850:
                    result['sources'].append({
                        'document': credit_report['filename'],
                        'value': int(parsed),
                        'location': location
                    })
    
    # Evaluate - find best match to profile score
    if result['sources']:
        best_match = None
        best_variance = float('inf')
        
        for src in result['sources']:
            doc_score = src['value']
            variance = abs(doc_score - profile_score)
            if variance < best_variance:
                best_variance = variance
                best_match = src
        
        if best_match:
            result['document_value'] = best_match['value']
            result['variance_percent'] = round(best_variance / profile_score * 100, 2)
            
            # Credit scores should match exactly or be within 10 points
            result['verified'] = best_variance <= 10
            result['notes'].append(f"Credit score from {best_match['document']}: {best_match['value']}")
    
    if not result['sources']:
        result['notes'].append('Credit score not found in credit report')
    
    return result


def verify_property_value(loan_id, profile):
    """
    Verify property value from:
    - Appraisal
    - AVM (Automated Valuation Model)
    - Purchase contract (for purchases)
    """
    result = {
        'verified': False,
        'profile_value': None,
        'document_value': None,
        'variance_percent': None,
        'sources': [],
        'notes': []
    }
    
    property_info = profile.get('property_info', {})
    profile_value = property_info.get('appraised_value') or property_info.get('purchase_price')
    
    if not profile_value:
        result['notes'].append('No property value in profile to verify')
        return result
    
    result['profile_value'] = profile_value
    
    # 1. Check appraisal (primary source)
    appraisal = execute_one("""
        SELECT filename, individual_analysis
        FROM document_analysis
        WHERE loan_id = %s 
        AND filename ILIKE '%%appraisal%%'
        AND filename NOT ILIKE '%%disclosure%%'
        AND filename NOT ILIKE '%%acknowledgement%%'
        AND filename NOT ILIKE '%%review%%'
        AND filename NOT ILIKE '%%other%%'
        ORDER BY 
            CASE WHEN filename ILIKE 'appraisal[_]%%' THEN 0 ELSE 1 END
        LIMIT 1
    """, (loan_id,))
    
    if appraisal and appraisal.get('individual_analysis'):
        analysis = appraisal['individual_analysis']
        doc_summary = analysis.get('document_summary', {})
        
        # Check important_values
        important = doc_summary.get('important_values', {})
        if important:
            valuations = important.get('property_valuation', [])
            for val in valuations:
                if 'appraised' in val.get('label', '').lower() or 'final' in val.get('label', '').lower():
                    result['sources'].append({
                        'document': appraisal['filename'],
                        'value': parse_number(val.get('value')),
                        'type': 'appraisal_value'
                    })
        
        # Check pages for appraised value
        pages = analysis.get('pages', [])
        for page in pages:
            key_data = page.get('key_data', {})
            for key in ['appraised_value', 'final_value', 'as_is_value', 'market_value', 'opinion_of_value']:
                if key in key_data:
                    val = parse_number(key_data[key])
                    if val and val > 10000:  # Reasonable property value
                        result['sources'].append({
                            'document': appraisal['filename'],
                            'value': val,
                            'type': key
                        })
    
    # 2. Check AVM/BPO
    avm = execute_one("""
        SELECT filename, individual_analysis
        FROM document_analysis
        WHERE loan_id = %s 
        AND (filename ILIKE '%%avm%%' OR filename ILIKE '%%bpo%%' OR filename ILIKE '%%valuation%%')
        AND filename NOT ILIKE '%%disclosure%%'
        LIMIT 1
    """, (loan_id,))
    
    if avm and avm.get('individual_analysis'):
        analysis = avm['individual_analysis']
        pages = analysis.get('pages', [])
        for page in pages:
            key_data = page.get('key_data', {})
            for key in ['estimated_value', 'avm_value', 'property_value']:
                if key in key_data:
                    val = parse_number(key_data[key])
                    if val and val > 10000:
                        result['sources'].append({
                            'document': avm['filename'],
                            'value': val,
                            'type': key
                        })
    
    # 3. Check purchase contract (for purchases)
    loan_info = profile.get('loan_info', {})
    if loan_info.get('loan_purpose', '').lower() == 'purchase':
        contract = execute_one("""
            SELECT filename, individual_analysis
            FROM document_analysis
            WHERE loan_id = %s 
            AND (filename ILIKE '%%purchase%%contract%%' OR filename ILIKE '%%sales%%contract%%')
            LIMIT 1
        """, (loan_id,))
        
        if contract and contract.get('individual_analysis'):
            analysis = contract['individual_analysis']
            pages = analysis.get('pages', [])
            for page in pages:
                key_data = page.get('key_data', {})
                for key in ['purchase_price', 'sale_price', 'contract_price']:
                    if key in key_data:
                        val = parse_number(key_data[key])
                        if val and val > 10000:
                            result['sources'].append({
                                'document': contract['filename'],
                                'value': val,
                                'type': key
                            })
    
    # Evaluate
    if result['sources']:
        best_match = None
        best_variance = float('inf')
        
        for src in result['sources']:
            doc_val = src['value']
            if doc_val and doc_val > 0:
                variance = abs(doc_val - profile_value) / profile_value * 100
                if variance < best_variance:
                    best_variance = variance
                    best_match = src
                    result['document_value'] = doc_val
        
        if best_match:
            result['variance_percent'] = round(best_variance, 2)
            # Property values should match within 5%
            result['verified'] = best_variance <= 5
            result['notes'].append(f"Best match from {best_match['document']}: ${result['document_value']:,.0f}")
    
    if not result['sources']:
        result['notes'].append('No property valuation documents found')
    
    return result


def save_verification_status(loan_id, verification_data):
    """Save verification status to loan_profiles."""
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
        
        # Filter out "not run" statuses (no documents found)
        # Only save verification status if:
        # 1. Verified successfully (verified=True), OR
        # 2. Has calculation steps or evidence files (proper verification was done), OR  
        # 3. Found a specific gap (like DOCUMENTATION GAP)
        filtered_verification = {}
        for key, status in verification_data.items():
            notes = status.get('notes', [])
            
            # Check if verification was properly done (has calculation steps or evidence)
            attr_mapping = {
                'debt': ['%debt%', '%payment%', '%expense%', '%total all monthly%'],
                'income': ['%income%', '%borrower total income%'],
                'credit_score': ['%credit%', '%fico%'],
                'property_value': ['%property value%', '%appraised%', '%purchase price%']
            }
            
            has_steps_or_evidence = False
            if key in attr_mapping:
                try:
                    patterns = attr_mapping[key]
                    
                    # Check calculation steps - use %% to escape % in SQL
                    steps_query = f"""
                        SELECT COUNT(*) as count 
                        FROM calculation_steps cs
                        JOIN form_1008_attributes fa ON fa.id = cs.attribute_id
                        WHERE cs.loan_id = %s 
                        AND ({' OR '.join([f"fa.attribute_label ILIKE '{pattern.replace('%', '%%')}'" for pattern in patterns])})
                    """
                    steps_result = execute_query(steps_query, (loan_id,))
                    has_steps = False
                    if steps_result and len(steps_result) > 0:
                        has_steps = steps_result[0].get('count', 0) > 0
                    
                    # Check evidence files
                    evidence_query = f"""
                        SELECT COUNT(*) as count
                        FROM evidence_files ef
                        JOIN form_1008_attributes fa ON fa.id = ef.attribute_id
                        WHERE ef.loan_id = %s
                        AND ({' OR '.join([f"fa.attribute_label ILIKE '{pattern.replace('%', '%%')}'" for pattern in patterns])})
                    """
                    evidence_result = execute_query(evidence_query, (loan_id,))
                    has_evidence = False
                    if evidence_result and len(evidence_result) > 0:
                        has_evidence = evidence_result[0].get('count', 0) > 0
                    
                    has_steps_or_evidence = has_steps or has_evidence
                except Exception as e:
                    import traceback
                    print(f"  ⚠️ Error checking {key} steps/evidence: {e}")
                    traceback.print_exc()
                    has_steps_or_evidence = False
            
            # Check if this is just "not found" without any actual document comparison
            is_documentation_gap = any('documentation gap' in str(note).lower() for note in notes)
            
            # Only save if:
            # - Verified successfully, OR
            # - Has calculation steps/evidence (formal verification was done), OR
            # - Has a specific documentation gap (not just "no docs found")
            # 
            # IMPORTANT: Even if we found a value in deep JSON, if there are no 
            # formal calculation steps or evidence files, treat it as "not run" (GRAY)
            if status.get('verified'):
                # Always save successful verifications
                filtered_verification[key] = status
            elif has_steps_or_evidence or is_documentation_gap:
                # Save if there's formal verification (even if failed)
                filtered_verification[key] = status
            # Otherwise: skip - leave as "not run" (GRAY)
        
        profile = result['profile_data'] or {}
        profile['verification_status'] = filtered_verification
        
        cur.execute("""
            UPDATE loan_profiles 
            SET profile_data = %s
            WHERE loan_id = %s
        """, (json.dumps(profile), loan_id))
        
        conn.commit()
        
    except Exception as e:
        conn.rollback()
        print(f"  ❌ Error saving verification: {e}")
    finally:
        cur.close()
        conn.close()


def verify_loan(loan_id, loan_number, profile):
    """Run all verifications for a loan."""
    print(f"\n{'='*70}")
    print(f"🔍 VERIFYING LOAN {loan_id} (#{loan_number})")
    print(f"{'='*70}")
    
    verification = {
        'income': verify_income(loan_id, profile),
        'debt': verify_debt(loan_id, profile),
        'credit_score': verify_credit_score(loan_id, profile),
        'property_value': verify_property_value(loan_id, profile)
    }
    
    # Print summary
    for key, result in verification.items():
        status = '✅' if result['verified'] else '❌'
        profile_val = result.get('profile_value', 'N/A')
        doc_val = result.get('document_value', 'N/A')
        variance = result.get('variance_percent', 'N/A')
        
        # Format values
        if key == 'credit_score':
            pv = f"{profile_val}" if profile_val else 'N/A'
            dv = f"{doc_val}" if doc_val else 'N/A'
        elif key in ['income', 'debt']:
            pv = f"${profile_val:,.2f}" if profile_val else 'N/A'
            dv = f"${doc_val:,.2f}" if doc_val else 'N/A'
        else:
            pv = f"${profile_val:,.0f}" if profile_val else 'N/A'
            dv = f"${doc_val:,.0f}" if doc_val else 'N/A'
        
        var_str = f"{variance}%" if variance and variance != 'N/A' else 'N/A'
        
        print(f"  {status} {key.upper():15} Profile: {pv:>15} | Doc: {dv:>15} | Var: {var_str:>8}")
        
        if result.get('notes'):
            for note in result['notes'][:2]:
                print(f"     └─ {note}")
    
    # Save to database
    save_verification_status(loan_id, verification)
    
    return verification


def run_verification(loan_id=None):
    """Run verification for all loans or a specific loan."""
    print("🔍 VERIFYING KEY LOAN ATTRIBUTES")
    print("=" * 70)
    
    if loan_id:
        loans = execute_query("""
            SELECT lp.loan_id, l.loan_number, lp.profile_data
            FROM loan_profiles lp
            JOIN loans l ON l.id = lp.loan_id
            WHERE lp.loan_id = %s
        """, (loan_id,))
    else:
        loans = execute_query("""
            SELECT lp.loan_id, l.loan_number, lp.profile_data
            FROM loan_profiles lp
            JOIN loans l ON l.id = lp.loan_id
            ORDER BY lp.loan_id
        """)
    
    print(f"Processing {len(loans)} loans\n")
    
    summary = {
        'income': {'verified': 0, 'total': 0},
        'debt': {'verified': 0, 'total': 0},
        'credit_score': {'verified': 0, 'total': 0},
        'property_value': {'verified': 0, 'total': 0}
    }
    
    for loan in loans:
        result = verify_loan(loan['loan_id'], loan['loan_number'], loan['profile_data'] or {})
        
        for key in summary.keys():
            summary[key]['total'] += 1
            if result[key]['verified']:
                summary[key]['verified'] += 1
    
    # Print summary
    print(f"\n{'='*70}")
    print("📊 VERIFICATION SUMMARY")
    print(f"{'='*70}")
    
    for key, counts in summary.items():
        pct = (counts['verified'] / counts['total'] * 100) if counts['total'] > 0 else 0
        print(f"  {key.upper():15} {counts['verified']}/{counts['total']} verified ({pct:.1f}%)")


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1:
        loan_id = int(sys.argv[1])
        run_verification(loan_id)
    else:
        run_verification()

