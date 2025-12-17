-- =====================================================
-- MORTGAGE COMPLIANCE DATABASE SCHEMA
-- Version: 1.0
-- Purpose: Support comprehensive compliance checking
-- =====================================================

-- Drop existing tables if they exist (in correct order)
DROP TABLE IF EXISTS compliance_audit_log CASCADE;
DROP TABLE IF EXISTS compliance_evidence CASCADE;
DROP TABLE IF EXISTS compliance_results CASCADE;
DROP TABLE IF EXISTS compliance_rules CASCADE;
DROP TABLE IF EXISTS compliance_calculations CASCADE;
DROP TABLE IF EXISTS disclosures CASCADE;
DROP TABLE IF EXISTS loan_fees CASCADE;
DROP TABLE IF EXISTS borrowers CASCADE;
DROP TABLE IF EXISTS nmls_licenses CASCADE;
DROP TABLE IF EXISTS state_compliance_rules CASCADE;
DROP TABLE IF EXISTS conforming_limits CASCADE;
DROP TABLE IF EXISTS apor_rates CASCADE;

-- =====================================================
-- SECTION 1: REFERENCE DATA TABLES
-- =====================================================

-- APOR (Average Prime Offer Rate) historical data
CREATE TABLE apor_rates (
    apor_id SERIAL PRIMARY KEY,
    effective_date DATE NOT NULL,
    rate_type VARCHAR(20) NOT NULL CHECK (rate_type IN ('Fixed', 'ARM')),
    loan_term_years INTEGER NOT NULL,
    arm_index_term INTEGER, -- For ARM: 1, 3, 5, 7, 10 year
    apor_rate DECIMAL(8,5) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(effective_date, rate_type, loan_term_years, arm_index_term)
);

CREATE INDEX idx_apor_lookup ON apor_rates(effective_date, rate_type, loan_term_years);

-- Conforming loan limits by county
CREATE TABLE conforming_limits (
    limit_id SERIAL PRIMARY KEY,
    effective_year INTEGER NOT NULL,
    state_code VARCHAR(2) NOT NULL,
    county_name VARCHAR(100) NOT NULL,
    fips_code VARCHAR(10),
    one_unit_limit DECIMAL(15,2) NOT NULL,
    two_unit_limit DECIMAL(15,2) NOT NULL,
    three_unit_limit DECIMAL(15,2) NOT NULL,
    four_unit_limit DECIMAL(15,2) NOT NULL,
    is_high_cost_area BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(effective_year, state_code, county_name)
);

CREATE INDEX idx_conforming_limits_lookup ON conforming_limits(effective_year, state_code, county_name);

-- State-specific rules and thresholds
CREATE TABLE state_compliance_rules (
    state_rule_id SERIAL PRIMARY KEY,
    state_code VARCHAR(2) NOT NULL,
    rule_category VARCHAR(50) NOT NULL,
    rule_name VARCHAR(200) NOT NULL,
    rule_description TEXT,
    statute_reference VARCHAR(200),
    threshold_type VARCHAR(50),
    threshold_value DECIMAL(15,4),
    effective_date DATE NOT NULL,
    expiration_date DATE,
    rule_logic JSONB,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_state_rules_state ON state_compliance_rules(state_code);
CREATE INDEX idx_state_rules_category ON state_compliance_rules(rule_category);

-- NMLS License data
CREATE TABLE nmls_licenses (
    license_id SERIAL PRIMARY KEY,
    nmls_id VARCHAR(20) NOT NULL,
    entity_type VARCHAR(20) CHECK (entity_type IN ('Individual', 'Company')),
    entity_name VARCHAR(200) NOT NULL,
    license_type VARCHAR(50) NOT NULL,
    license_state VARCHAR(2) NOT NULL,
    license_number VARCHAR(50),
    license_status VARCHAR(30) NOT NULL,
    status_date DATE,
    original_issue_date DATE,
    expiration_date DATE,
    last_verified_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(nmls_id, license_state, license_type)
);

CREATE INDEX idx_nmls_lookup ON nmls_licenses(nmls_id);
CREATE INDEX idx_nmls_state ON nmls_licenses(license_state);

-- =====================================================
-- SECTION 2: ENHANCED LOAN DATA TABLES
-- =====================================================

-- Enhanced borrowers table
CREATE TABLE IF NOT EXISTS borrowers (
    borrower_id SERIAL PRIMARY KEY,
    loan_id INTEGER NOT NULL REFERENCES loans(id),
    borrower_type VARCHAR(20) NOT NULL CHECK (borrower_type IN ('Primary', 'CoBorrower', 'Guarantor')),
    borrower_sequence INTEGER NOT NULL,
    
    -- Personal Information
    first_name VARCHAR(100),
    middle_name VARCHAR(100),
    last_name VARCHAR(100),
    ssn_last_four VARCHAR(4),
    date_of_birth DATE,
    
    -- Credit
    credit_score INTEGER,
    credit_score_model VARCHAR(50),
    credit_report_date DATE,
    
    -- Employment
    employment_status VARCHAR(30),
    employer_name VARCHAR(200),
    years_employed DECIMAL(4,2),
    
    -- Income (Monthly)
    base_income DECIMAL(15,2) DEFAULT 0,
    overtime_income DECIMAL(15,2) DEFAULT 0,
    bonus_income DECIMAL(15,2) DEFAULT 0,
    commission_income DECIMAL(15,2) DEFAULT 0,
    self_employment_income DECIMAL(15,2) DEFAULT 0,
    rental_income DECIMAL(15,2) DEFAULT 0,
    other_income DECIMAL(15,2) DEFAULT 0,
    total_monthly_income DECIMAL(15,2),
    
    -- Debts
    monthly_debt_payments DECIMAL(15,2) DEFAULT 0,
    proposed_housing_payment DECIMAL(15,2) DEFAULT 0,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(loan_id, borrower_sequence)
);

-- Loan fees table
CREATE TABLE loan_fees (
    fee_id SERIAL PRIMARY KEY,
    loan_id INTEGER NOT NULL REFERENCES loans(id),
    
    -- Fee Classification
    fee_category VARCHAR(50) NOT NULL,
    fee_type VARCHAR(100) NOT NULL,
    fee_description VARCHAR(500),
    
    -- Amounts
    amount DECIMAL(15,2) NOT NULL,
    paid_by VARCHAR(20) CHECK (paid_by IN ('Borrower', 'Seller', 'Lender', 'ThirdParty', 'Other')),
    paid_to VARCHAR(200),
    
    -- Regulatory Classification
    is_finance_charge BOOLEAN DEFAULT FALSE,
    is_qm_points_and_fees BOOLEAN DEFAULT FALSE,
    is_hoepa_points_and_fees BOOLEAN DEFAULT FALSE,
    
    -- TRID Section
    trid_section VARCHAR(50),
    tolerance_category VARCHAR(20) CHECK (tolerance_category IN ('ZeroTolerance', 'TenPercent', 'Unlimited')),
    
    -- LE vs CD tracking
    le_amount DECIMAL(15,2),
    cd_amount DECIMAL(15,2),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_loan_fees_loan_id ON loan_fees(loan_id);
CREATE INDEX idx_loan_fees_qm ON loan_fees(is_qm_points_and_fees) WHERE is_qm_points_and_fees = TRUE;

-- =====================================================
-- SECTION 3: COMPLIANCE TABLES
-- =====================================================

-- Compliance calculations storage
CREATE TABLE compliance_calculations (
    calculation_id SERIAL PRIMARY KEY,
    loan_id INTEGER NOT NULL REFERENCES loans(id),
    
    -- Calculation Identity
    calculation_type VARCHAR(100) NOT NULL,
    calculation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- APR Calculations
    calculated_apr DECIMAL(8,5),
    apr_tolerance DECIMAL(8,5),
    
    -- APOR Comparison
    apor_rate DECIMAL(8,5),
    apor_date DATE,
    apor_spread DECIMAL(8,5),
    
    -- QM Points and Fees
    qm_points_fees_amount DECIMAL(15,2),
    qm_points_fees_limit DECIMAL(15,2),
    qm_points_fees_percentage DECIMAL(8,5),
    qm_points_fees_compliant BOOLEAN,
    
    -- HOEPA Points and Fees
    hoepa_points_fees_amount DECIMAL(15,2),
    hoepa_points_fees_limit DECIMAL(15,2),
    hoepa_triggered BOOLEAN,
    
    -- DTI Calculations
    total_monthly_income DECIMAL(15,2),
    housing_expense DECIMAL(15,2),
    total_debt_payments DECIMAL(15,2),
    front_end_dti DECIMAL(8,5),
    back_end_dti DECIMAL(8,5),
    
    -- ATR/QM Determination
    atr_type VARCHAR(50),
    qm_type VARCHAR(50),
    qm_eligible BOOLEAN,
    qm_safe_harbor BOOLEAN,
    
    -- HPML Determination
    is_hpml BOOLEAN,
    hpml_threshold DECIMAL(8,5),
    hpml_spread DECIMAL(8,5),
    
    -- Calculation Details (JSON)
    calculation_inputs JSONB,
    calculation_breakdown JSONB,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_compliance_calc_loan ON compliance_calculations(loan_id);
CREATE INDEX idx_compliance_calc_type ON compliance_calculations(calculation_type);

-- Master rule definitions
CREATE TABLE compliance_rules (
    rule_id SERIAL PRIMARY KEY,
    rule_code VARCHAR(50) UNIQUE NOT NULL,
    rule_name VARCHAR(200) NOT NULL,
    rule_description TEXT,
    
    -- Classification
    rule_category VARCHAR(50) NOT NULL,
    regulation_reference VARCHAR(100),
    
    -- Applicability
    applies_to_loan_types TEXT[], -- array of loan types
    applies_to_states TEXT[], -- NULL means all states
    
    -- Effective Dates
    effective_date DATE NOT NULL,
    expiration_date DATE,
    
    -- Rule Logic
    rule_logic JSONB NOT NULL,
    
    -- Severity
    severity VARCHAR(20) NOT NULL CHECK (severity IN ('Critical', 'High', 'Medium', 'Low', 'Info')),
    
    -- Automation
    is_automated BOOLEAN DEFAULT TRUE,
    requires_manual_review BOOLEAN DEFAULT FALSE,
    
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_compliance_rules_category ON compliance_rules(rule_category);
CREATE INDEX idx_compliance_rules_active ON compliance_rules(is_active) WHERE is_active = TRUE;

-- Rule execution results
CREATE TABLE compliance_results (
    result_id SERIAL PRIMARY KEY,
    loan_id INTEGER NOT NULL REFERENCES loans(id),
    rule_id INTEGER NOT NULL REFERENCES compliance_rules(rule_id),
    
    -- Execution Context
    execution_id VARCHAR(100) NOT NULL,
    execution_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Result
    status VARCHAR(20) NOT NULL CHECK (status IN ('PASS', 'FAIL', 'WARNING', 'NA', 'ERROR', 'PENDING_REVIEW')),
    
    -- Details
    expected_value TEXT,
    actual_value TEXT,
    variance TEXT,
    
    -- Evidence
    evidence_summary TEXT,
    evidence_documents JSONB,
    source_data JSONB,
    
    -- Messages
    result_message TEXT,
    remediation_guidance TEXT,
    
    -- Manual Review
    requires_manual_review BOOLEAN DEFAULT FALSE,
    manual_review_status VARCHAR(20),
    manual_review_notes TEXT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_compliance_results_loan ON compliance_results(loan_id);
CREATE INDEX idx_compliance_results_execution ON compliance_results(execution_id);
CREATE INDEX idx_compliance_results_status ON compliance_results(status);

-- Disclosure tracking
CREATE TABLE disclosures (
    disclosure_id SERIAL PRIMARY KEY,
    loan_id INTEGER NOT NULL REFERENCES loans(id),
    
    -- Disclosure Type
    disclosure_type VARCHAR(50) NOT NULL,
    disclosure_version INTEGER DEFAULT 1,
    
    -- Key Dates
    prepared_date DATE NOT NULL,
    delivered_date DATE,
    received_date DATE,
    delivery_method VARCHAR(30),
    
    -- Timing Compliance
    required_by_date DATE,
    days_before_consummation INTEGER,
    timing_compliant BOOLEAN,
    
    -- Key Values
    disclosed_apr DECIMAL(8,5),
    disclosed_finance_charge DECIMAL(15,2),
    disclosed_cash_to_close DECIMAL(15,2),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_disclosures_loan ON disclosures(loan_id);

-- =====================================================
-- VIEWS FOR DASHBOARD
-- =====================================================

-- Loan compliance summary view
CREATE OR REPLACE VIEW vw_loan_compliance_summary AS
SELECT 
    l.id as loan_id,
    l.borrower_name,
    
    -- Compliance Counts
    COUNT(cr.result_id) as total_rules_checked,
    COUNT(CASE WHEN cr.status = 'PASS' THEN 1 END) as passed_count,
    COUNT(CASE WHEN cr.status = 'FAIL' THEN 1 END) as failed_count,
    COUNT(CASE WHEN cr.status = 'WARNING' THEN 1 END) as warning_count,
    
    -- Overall Status
    CASE 
        WHEN COUNT(CASE WHEN cr.status = 'FAIL' THEN 1 END) > 0 THEN 'FAIL'
        WHEN COUNT(CASE WHEN cr.status = 'WARNING' THEN 1 END) > 0 THEN 'WARNING'
        ELSE 'PASS'
    END as overall_compliance_status,
    
    -- Latest Check
    MAX(cr.execution_timestamp) as last_compliance_check,
    
    -- Key Metrics from latest calculation
    cc.qm_type,
    cc.qm_eligible,
    cc.is_hpml,
    cc.back_end_dti,
    cc.qm_points_fees_percentage
    
FROM loans l
LEFT JOIN compliance_results cr ON l.id = cr.loan_id
LEFT JOIN LATERAL (
    SELECT * FROM compliance_calculations 
    WHERE loan_id = l.id 
    ORDER BY calculation_date DESC 
    LIMIT 1
) cc ON true
GROUP BY l.id, l.borrower_name, cc.qm_type, cc.qm_eligible, cc.is_hpml, cc.back_end_dti, cc.qm_points_fees_percentage;

-- Category-level compliance view
CREATE OR REPLACE VIEW vw_compliance_by_category AS
SELECT 
    l.id as loan_id,
    r.rule_category,
    COUNT(cr.result_id) as rules_in_category,
    COUNT(CASE WHEN cr.status = 'PASS' THEN 1 END) as passed,
    COUNT(CASE WHEN cr.status = 'FAIL' THEN 1 END) as failed,
    COUNT(CASE WHEN cr.status = 'WARNING' THEN 1 END) as warnings,
    CASE 
        WHEN COUNT(CASE WHEN cr.status = 'FAIL' THEN 1 END) > 0 THEN 'FAIL'
        WHEN COUNT(CASE WHEN cr.status = 'WARNING' THEN 1 END) > 0 THEN 'WARNING'
        ELSE 'PASS'
    END as category_status
FROM loans l
CROSS JOIN (SELECT DISTINCT rule_category FROM compliance_rules WHERE is_active = TRUE) r
LEFT JOIN compliance_rules cr_def ON r.rule_category = cr_def.rule_category
LEFT JOIN compliance_results cr ON l.id = cr.loan_id AND cr_def.rule_id = cr.rule_id
GROUP BY l.id, r.rule_category;

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO postgres;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO postgres;


-- =====================================================
-- COMPLIANCE EXTRACTED DATA TABLE
-- Stores all extracted compliance data from documents
-- =====================================================

CREATE TABLE IF NOT EXISTS compliance_extracted_data (
    loan_id INTEGER PRIMARY KEY,
    extracted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    data_json JSONB NOT NULL,
    FOREIGN KEY (loan_id) REFERENCES loans(loan_id) ON DELETE CASCADE
);

CREATE INDEX idx_compliance_extracted_loan ON compliance_extracted_data(loan_id);
CREATE INDEX idx_compliance_extracted_data_json ON compliance_extracted_data USING GIN (data_json);

COMMENT ON TABLE compliance_extracted_data IS 'Stores all compliance-relevant data extracted from loan documents';
COMMENT ON COLUMN compliance_extracted_data.data_json IS 'JSON object containing all extracted compliance fields from LE, CD, Note, Underwriting, etc.';



