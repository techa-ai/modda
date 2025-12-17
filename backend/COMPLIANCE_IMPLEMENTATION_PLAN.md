# Comprehensive Compliance Implementation Plan

## Overview
Implement ALL compliance rules from the Mavent report by extracting required attributes from 279 loan documents.

## Phase 1: Data Extraction Strategy (Document Intelligence)

### 1.1 Document Classification & Mapping
Map each of the 279 documents to compliance categories:

| Document Type | Compliance Use | Key Fields to Extract |
|--------------|----------------|----------------------|
| **Loan Estimate (LE)** | TILA, RESPA | Prepared date, Delivered date, APR, Finance Charge, Amount Financed, Total of Payments, Projected Payments Table, Loan Terms, Closing Costs |
| **Closing Disclosure (CD)** | TILA, RESPA | Similar to LE + Actual closing costs, Cash to Close, Seller credits |
| **URLA (1003/1008)** | ATR/QM, HPML | Borrower info, Income, Assets, Debts, Employment, Credit score, DTI, Property details |
| **Credit Report** | ATR | Credit scores, Trade lines, Inquiries, Public records |
| **Appraisal** | HPML, ATR | Appraised value, Property type, As-is value, Subject to completion value |
| **Bank Statements** | ATR | Account balances, Transaction history, Reserves |
| **Pay Stubs** | ATR | Income verification, YTD earnings, Employer |
| **Tax Returns** | ATR | AGI, Self-employment income, Rental income |
| **W-2s** | ATR | Annual income, Employer verification |
| **VOE (Verification of Employment)** | ATR | Current employment status, Income stability |
| **Gift Letters** | ATR | Source of funds, Gift amount, Relationship |
| **Underwriting Approval** | ATR/QM | Underwriter name, Approval date, Conditions, AUS decision |
| **Note** | ATR/QM, TILA | Loan amount, Interest rate, Payment schedule, ARM terms, Prepayment penalty |
| **Deed of Trust/Mortgage** | RESPA | Property description, Lien position |
| **Title Report** | RESPA | Liens, Encumbrances, Title exceptions |
| **Insurance Binder** | HPML, RESPA | Policy amount, Coverage type, Premium |
| **HUD-1/Settlement Statement** | RESPA | Line-by-line settlement charges |
| **Fee Worksheets** | ATR/QM Points & Fees | All lender fees, Third-party fees, Who pays |
| **NMLS Documents** | Licenses | Originator NMLS, Company NMLS, Branch NMLS |
| **Disclosures (various)** | TILA, RESPA | Delivery dates, Receipt dates, Content accuracy |

### 1.2 Compliance Data Model (What to Extract)

```python
# Core compliance data structure needed from documents
{
    # LOAN TERMS
    "loan_amount": Decimal,
    "purchase_price": Decimal,
    "appraised_value": Decimal,
    "interest_rate": Decimal,
    "note_rate": Decimal,
    "apr": Decimal,
    "loan_term_months": int,
    "first_payment_date": date,
    "lien_position": str,  # "First", "Second"
    
    # PROPERTY
    "property_address": str,
    "property_city": str,
    "property_state": str,
    "property_county": str,
    "property_zip": str,
    "property_type": str,  # "1 Unit", "2-4 Units", "Condo", "PUD"
    "occupancy_type": str,  # "Primary", "Second Home", "Investment"
    
    # LOAN TYPE & PURPOSE
    "loan_type": str,  # "Conventional", "FHA", "VA", "USDA"
    "loan_purpose": str,  # "Purchase", "Refinance", "Cash-Out Refinance"
    "documentation_type": str,  # "Full Doc", "Alternative Doc"
    
    # LOAN FEATURES
    "is_arm": bool,
    "arm_initial_period": int,
    "arm_adjustment_period": int,
    "arm_first_change_date": date,
    "arm_index": str,
    "arm_margin": Decimal,
    "arm_caps": {
        "initial": Decimal,
        "periodic": Decimal,
        "lifetime": Decimal,
        "floor": Decimal
    },
    "has_prepayment_penalty": bool,
    "prepayment_penalty_terms": str,
    "has_balloon": bool,
    "balloon_date": date,
    "has_interest_only": bool,
    "interest_only_period": int,
    "has_negative_amortization": bool,
    
    # BORROWER DATA (for each borrower)
    "borrowers": [{
        "name": str,
        "ssn_last4": str,
        "credit_score": int,
        "total_monthly_income": Decimal,
        "gross_monthly_income": Decimal,
        "employment_status": str,
        "employment_history": [
            {
                "employer": str,
                "start_date": date,
                "end_date": date,
                "monthly_income": Decimal
            }
        ],
        "monthly_debt_obligations": Decimal,
        "housing_expense": Decimal,
        "assets": [
            {
                "type": str,  # "Checking", "Savings", "401k", etc.
                "institution": str,
                "account_number_last4": str,
                "balance": Decimal,
                "verified": bool
            }
        ],
        "liabilities": [
            {
                "type": str,
                "creditor": str,
                "monthly_payment": Decimal,
                "balance": Decimal,
                "paid_off_at_closing": bool
            }
        ]
    }],
    
    # DTI CALCULATIONS
    "front_end_dti": Decimal,
    "back_end_dti": Decimal,
    "housing_payment_proposed": Decimal,
    
    # FEES & CHARGES
    "fees": [
        {
            "section": str,  # "A. Origination Charges", "B. Services...", etc.
            "fee_name": str,
            "amount": Decimal,
            "paid_by": str,  # "Borrower", "Seller", "Lender"
            "poc": bool,  # Paid Outside Closing
            "is_qm_points_fees": bool,
            "is_bona_fide_discount_point": bool,
            "hud_line": str  # "801", "802", etc.
        }
    ],
    "total_loan_costs": Decimal,
    "total_other_costs": Decimal,
    "total_closing_costs": Decimal,
    "lender_credits": Decimal,
    "seller_credits": Decimal,
    
    # DISCLOSURES
    "disclosures": [
        {
            "type": str,  # "Loan Estimate", "Closing Disclosure", etc.
            "version": int,  # 1, 2, 3 for revised
            "prepared_date": date,
            "delivered_date": date,
            "delivery_method": str,  # "Electronic", "Mail", "In-Person"
            "received_date": date,
            "disclosed_values": {
                "apr": Decimal,
                "finance_charge": Decimal,
                "amount_financed": Decimal,
                "total_of_payments": Decimal,
                "principal_interest": Decimal,
                "mortgage_insurance": Decimal,
                "estimated_escrow": Decimal,
                "estimated_total_payment": Decimal,
                "cash_to_close": Decimal
            }
        }
    ],
    
    # DATES
    "application_date": date,
    "intent_to_proceed_date": date,
    "lock_date": date,
    "lock_expiration_date": date,
    "initial_le_date": date,
    "revised_le_dates": [date],
    "initial_cd_date": date,
    "revised_cd_dates": [date],
    "closing_date": date,
    "note_date": date,
    "first_payment_date": date,
    "aus_submission_date": date,
    "aus_recommendation_date": date,
    "underwriting_approval_date": date,
    "clear_to_close_date": date,
    
    # UNDERWRITING
    "underwriter_name": str,
    "underwriter_nmls": str,
    "aus_system": str,  # "Desktop Underwriter", "Loan Prospector", etc.
    "aus_recommendation": str,  # "Approve/Eligible", "Refer", etc.
    "aus_findings": str,
    "manual_underwriting": bool,
    "underwriting_conditions": [str],
    
    # LICENSES & ORIGINATORS
    "loan_originator": {
        "name": str,
        "nmls_id": str,
        "license_state": str,
        "license_number": str,
        "company_nmls": str,
        "company_name": str,
        "branch_nmls": str
    },
    "loan_processor": {
        "name": str,
        "nmls_id": str
    },
    
    # THIRD-PARTY PROVIDERS
    "title_company": str,
    "escrow_company": str,
    "appraisal_company": str,
    "appraiser_name": str,
    "appraiser_license": str,
    
    # SPECIAL PROGRAMS
    "is_rural_or_underserved": bool,
    "is_manufactured_housing": bool,
    "is_reverse_mortgage": bool,
    "is_hpml": bool,
    "is_hoepa": bool,
    "qm_classification": str,  # "General QM", "Seasoned QM", etc.
    
    # ESCROW
    "escrow_waived": bool,
    "escrow_waiver_reason": str,
    "initial_escrow_deposit": Decimal,
    "monthly_escrow_payment": Decimal
}
```

## Phase 2: Document Processing Pipeline

### 2.1 Automated Document Intelligence Extraction

```python
# Pseudocode for extraction pipeline
def extract_compliance_data_from_loan_file(loan_id):
    """
    Process all 279 documents to extract compliance data
    """
    
    # Step 1: Get all documents for loan
    documents = get_loan_documents(loan_id)
    
    # Step 2: Classify each document (already done via document_analysis)
    classified_docs = {
        'loan_estimate': [],
        'closing_disclosure': [],
        'urla': [],
        'credit_report': [],
        'appraisal': [],
        'note': [],
        'underwriting': [],
        # ... etc
    }
    
    for doc in documents:
        doc_type = doc['doc_type']
        classified_docs[doc_type].append(doc)
    
    # Step 3: Extract structured data from each doc type
    compliance_data = {}
    
    # Extract from LE
    if classified_docs['loan_estimate']:
        le_data = extract_loan_estimate_data(
            classified_docs['loan_estimate'][0],  # Use most recent
            use_deep_json=True  # We have deep JSON for all docs
        )
        compliance_data.update(le_data)
    
    # Extract from CD
    if classified_docs['closing_disclosure']:
        cd_data = extract_closing_disclosure_data(
            classified_docs['closing_disclosure'][0]
        )
        compliance_data.update(cd_data)
    
    # Extract from URLA (we already have this from 1008!)
    urla_data = get_1008_extracted_data(loan_id)
    compliance_data.update(urla_data)
    
    # Extract from Credit Report
    if classified_docs['credit_report']:
        credit_data = extract_credit_report_data(
            classified_docs['credit_report'][0]
        )
        compliance_data.update(credit_data)
    
    # ... continue for all doc types
    
    # Step 4: Store in compliance_data table
    store_compliance_data(loan_id, compliance_data)
    
    return compliance_data
```

### 2.2 Extraction Functions (Use Claude Opus + Deep JSON)

For each document type, create targeted extraction:

```python
def extract_loan_estimate_data(document, use_deep_json=True):
    """
    Extract LE-specific compliance data
    """
    if use_deep_json and document.get('individual_analysis'):
        # Parse from existing deep JSON
        json_data = document['individual_analysis']
        
        # Map JSON to compliance fields
        return {
            'le_prepared_date': parse_date(json_data.get('prepared_date')),
            'le_disclosed_apr': parse_decimal(json_data.get('apr')),
            'le_finance_charge': parse_decimal(json_data.get('finance_charge')),
            # ... map all LE fields
        }
    else:
        # Use Claude to extract from OCR/images
        prompt = f"""
        From this Loan Estimate document, extract the following compliance data:
        
        1. Prepared Date
        2. Loan Terms (loan amount, interest rate, monthly P&I)
        3. Projected Payments Table (Year 1-7, 8-30, etc.)
        4. Estimated Closing Costs (Sections A-H)
        5. Disclosed APR, Finance Charge, Amount Financed, Total of Payments
        6. Cash to Close calculation
        7. Comparisons section
        
        Return as structured JSON with exact values from the document.
        
        OCR Text:
        {document['ocr_text_summary']}
        """
        
        response = ask_claude_opus(prompt, document['images'])
        return parse_json_response(response)
```

## Phase 3: Compliance Rules Implementation (50+ Rules)

Based on Mavent report, implement rules in these categories:

### 3.1 ATR/QM Rules (15-20 rules)
- [ ] QM Price-Based Limit (APR threshold by loan amount)
- [ ] QM Points & Fees Limit (3%, 5%, 8% tiers)
- [ ] QM Points & Fees Calculation (what's included/excluded)
- [ ] General QM Product Feature Restrictions (no balloon, IO, neg am)
- [ ] Loan Term Limit (≤ 30 years)
- [ ] DTI Limit (≤ 43% for General QM)
- [ ] Underwriter ATR Factor Verification
- [ ] Income Verification Standards
- [ ] Asset Verification Standards
- [ ] Employment Verification Standards
- [ ] Credit History Consideration
- [ ] Monthly Payment Calculation
- [ ] Mortgage-Related Obligations Calculation
- [ ] Simultaneous Loan Consideration
- [ ] Safe Harbor vs Rebuttable Presumption determination

### 3.2 TILA Rules (10-15 rules)
- [ ] Loan Estimate Timing (≤ 3 business days after application)
- [ ] Loan Estimate Delivery Method Compliance
- [ ] Closing Disclosure Timing (≥ 3 business days before closing)
- [ ] Closing Disclosure Re-disclosure Triggers
- [ ] APR Accuracy (within tolerance)
- [ ] Finance Charge Accuracy
- [ ] Amount Financed Accuracy
- [ ] Total of Payments Accuracy
- [ ] Payment Schedule Disclosure
- [ ] Projected Payments Table Accuracy (LE vs CD)
- [ ] Escrow Disclosure Requirements
- [ ] ARM Disclosure Requirements
- [ ] Variable Rate Disclosures
- [ ] Right to Rescind (if applicable)

### 3.3 RESPA Rules (8-10 rules)
- [ ] Affiliated Business Arrangement Disclosures
- [ ] Good Faith Estimate Timing (pre-2015 loans)
- [ ] Settlement Service Provider Selection
- [ ] Fee Tolerance Compliance (0%, 10% categories)
- [ ] Cash to Close Variance
- [ ] Escrow Account Requirements
- [ ] Escrow Account Disclosure
- [ ] Kickbacks and Unearned Fees Prohibition
- [ ] Title Insurance Requirements

### 3.4 HPML Rules (8-10 rules)
- [ ] HPML Determination (APR spread vs APOR)
- [ ] HPML Escrow Requirement (first 5 years minimum)
- [ ] HPML Appraisal Requirements
- [ ] HPML Second Appraisal (flipped properties)
- [ ] HPML Appraiser Independence
- [ ] HPML Prohibited Prepayment Penalties
- [ ] HPML Homeownership Counseling
- [ ] HPML Late Fee Restrictions
- [ ] HPML Rural/Underserved Exemptions

### 3.5 HOEPA (High-Cost) Rules (5-7 rules)
- [ ] HOEPA APR Threshold Check
- [ ] HOEPA Points & Fees Threshold Check
- [ ] HOEPA Prepayment Penalty Threshold
- [ ] HOEPA Prohibited Features (balloon, neg am, default rate)
- [ ] HOEPA Counseling Requirement
- [ ] HOEPA Advertising Restrictions
- [ ] HOEPA Refinance Restrictions

### 3.6 State-Specific Rules (varies by state)
California example:
- [ ] CA High-Cost Mortgage Definition (differs from federal)
- [ ] CA Negative Amortization Prohibition (HPML)
- [ ] CA Prepayment Penalty Restrictions
- [ ] CA Counseling Requirements
- [ ] CA Appraisal Requirements
- [ ] CA Servicing Requirements
- [ ] CA Foreclosure Restrictions

### 3.7 NMLS/License Rules (5-7 rules)
- [ ] Loan Originator Licensed in Property State
- [ ] Loan Originator NMLS Valid and Active
- [ ] Company NMLS Valid and Active
- [ ] Branch NMLS Valid and Active (if applicable)
- [ ] License Not Expired
- [ ] License Not Suspended
- [ ] Required State-Specific Licenses

### 3.8 Enterprise (GSE) Rules (5-8 rules)
- [ ] Fannie Mae Loan Limits
- [ ] Freddie Mac Loan Limits
- [ ] DTI Limits for Fannie/Freddie
- [ ] LTV/CLTV Limits
- [ ] Cash-Out Refinance Restrictions
- [ ] Appraisal Requirements
- [ ] Underwriting Standards
- [ ] Representations & Warranties Compliance

### 3.9 HMDA Reporting Rules (3-5 rules)
- [ ] Rate Spread Calculation
- [ ] HPML Reportability
- [ ] Reportable Loan Type
- [ ] Property Type Reporting
- [ ] Purpose Reporting

## Phase 4: Implementation Approach

### Step 1: Create Compliance Data Extraction Service
```python
# backend/compliance_data_extractor.py
class ComplianceDataExtractor:
    """
    Orchestrates extraction of all compliance data from loan documents
    """
    
    def extract_all(self, loan_id):
        """Main entry point"""
        # Get all 279 documents
        # Classify and route to specialized extractors
        # Aggregate results
        # Store in compliance_data table
        # Return complete compliance dataset
        pass
```

### Step 2: Implement 50+ Compliance Rules
```python
# backend/compliance_rules/
#   __init__.py
#   atr_qm_rules.py (20 rules)
#   tila_rules.py (15 rules)
#   respa_rules.py (10 rules)
#   hpml_rules.py (10 rules)
#   hoepa_rules.py (7 rules)
#   state_rules.py (varies)
#   nmls_rules.py (7 rules)
#   enterprise_rules.py (8 rules)
#   hmda_rules.py (5 rules)
```

### Step 3: Enhanced Compliance Engine
```python
# backend/compliance_engine_v3.py
# Load all 50+ rules
# Run against extracted compliance data
# Generate comprehensive Mavent-style report
```

### Step 4: Frontend Enhancement
- Compliance Dashboard with all categories
- Rule detail modals with evidence
- Document viewer integration (click rule → view source doc & page)
- Export compliance report as PDF

## Phase 5: Execution Timeline

### Sprint 1 (Current): Foundation ✅
- [x] Database schema
- [x] Basic compliance engine (10 rules)
- [x] Frontend dashboard
- [x] API endpoint

### Sprint 2: Data Extraction (Next)
- [ ] Build ComplianceDataExtractor class
- [ ] Implement LE extraction
- [ ] Implement CD extraction  
- [ ] Implement Note extraction
- [ ] Implement Underwriting extraction
- [ ] Aggregate and store compliance data

### Sprint 3: Rules Implementation
- [ ] Implement all ATR/QM rules (20)
- [ ] Implement all TILA rules (15)
- [ ] Implement all RESPA rules (10)
- [ ] Test against sample loan

### Sprint 4: Advanced Rules
- [ ] Implement HPML rules (10)
- [ ] Implement HOEPA rules (7)
- [ ] Implement State rules (10)
- [ ] Implement NMLS rules (7)
- [ ] Implement Enterprise rules (8)
- [ ] Implement HMDA rules (5)

### Sprint 5: Integration & Polish
- [ ] Evidence linking (rule → document → page)
- [ ] Compliance report export
- [ ] Performance optimization
- [ ] Testing & validation

## Expected Outcome

A fully automated compliance checking system that:
1. ✅ Analyzes all 279 documents in a loan file
2. ✅ Extracts 100+ compliance-relevant data points
3. ✅ Runs 50+ compliance rules across all categories
4. ✅ Generates Mavent-style comprehensive report
5. ✅ Links every rule result to source documents
6. ✅ Exports professional compliance report

**Total Rules Target: 80-100 rules** (Mavent has ~100-150)

---

## Next Steps

1. **Create ComplianceDataExtractor** - Start building the document intelligence pipeline
2. **Test extraction on key docs** - LE, CD, Note, URLA  
3. **Implement next 20 rules** - Focus on TILA and RESPA
4. **Build evidence linking** - Connect rules to source docs

Should I start with Step 1 (ComplianceDataExtractor)?




