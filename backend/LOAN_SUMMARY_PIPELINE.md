# Loan Summary Processing Pipeline

## 📊 Overview

After **Core Document Processing** (Steps 1-7 in REFINED_PIPELINE_V3.md), we create a comprehensive loan summary for each loan. This summary is used for:
- Loan Management dashboard display
- Quick loan comparison and filtering
- RAG status calculation
- Verification badge status (I, D, C, V)

---

## 🔄 Summary Processing Steps

```
┌─────────────────────────────────────────────────────────────────────┐
│                    LOAN SUMMARY PIPELINE                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  S1. Extract Loan Profile (summary_s1_extract_profile.py)           │
│      ├─ Primary: 1008 (Transmittal Summary)                         │
│      ├─ Fallback: URLA (1003)                                       │
│      ├─ Fallback: Non-Standard Loan Application                     │
│      └─ Output: loan_profiles table                                 │
│                                                                     │
│  S2. DSCR Calculation (summary_s2_dscr_calculation.py)              │
│      ├─ Filter: Investment properties only                         │
│      ├─ Source: URLA, Appraisal, Underwriting docs                  │
│      └─ Output: profile_data.dscr_analysis                          │
│                                                                     │
│  S3. Non-1008 Metrics (summary_s3_non1008_metrics.py)               │
│      ├─ Filter: Loans without 1008 or missing metrics               │
│      ├─ Source: HELOC Agreement, Rate Lock, Closing Disclosure      │
│      └─ Output: Rate, DTI/DSCR, CLTV in profile_data                │
│                                                                     │
│  S4. Verification Status (summary_s4_verify_attributes.py)          │
│      ├─ Check: Income, Debt, Credit Score, Property Value           │
│      ├─ Source: Existing evidence_files OR document analysis        │
│      └─ Output: profile_data.verification_status                    │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 📋 Step Details

### S1: Extract Loan Profile

**Purpose**: Create base loan profile from primary source document

**Source Priority**:
1. `1008___final_*.pdf` (Uniform Underwriting and Transmittal Summary)
2. `urla___final_*.pdf` (Uniform Residential Loan Application)
3. `non_standardloanapplication___final_*.pdf`

**Extracted Fields**:
- Borrower info (name, SSN last 4, DOB, citizenship)
- Loan info (amount, rate, term, type, purpose, lien position)
- Property info (address, value, occupancy, type)
- Ratios (LTV, CLTV, DTI front-end, DTI back-end)
- Income profile (total monthly, income types)
- Credit profile (score, source)
- Employment info

**Output**: `loan_profiles` table with `profile_data` JSON

---

### S2: DSCR Calculation

**Purpose**: Calculate Debt Service Coverage Ratio for investment properties

**Filter**: `profile_data.property_info.occupancy ILIKE '%investment%'`

**Formula**:
```
DSCR = Net Operating Income / Debt Service
     = (Gross Rent × 0.75) / Monthly P&I
```

**Sources for Rental Income**:
1. URLA real estate portfolio
2. Appraisal rental comparables (indicated market rent)
3. Underwriting documents
4. Conditional approval notice

**Sources for Monthly P&I**:
1. Loan profile (monthly_pi_payment)
2. 1008 section 4 (housing expense)
3. Promissory note
4. Calculate from loan terms (amount, rate, term)

**Output**: `profile_data.dscr_analysis`
```json
{
  "dscr": 1.421,
  "dscr_rating": "G",  // G=Green (≥1.25), A=Amber (1.0-1.25), R=Red (<1.0)
  "gross_monthly_rent": 1450,
  "net_monthly_rent": 1087.50,
  "monthly_pi": 765,
  "rent_source": {"document": "urla___final_60.pdf", "page": 3},
  "pi_source": {"document": "loan_profile", "method": "calculated"}
}
```

---

### S3: Non-1008 Metrics

**Purpose**: Extract Rate, DTI, CLTV for loans without 1008

**Filter**: Loans where:
- `analysis_source NOT ILIKE '%1008%'`, OR
- `profile_data.loan_info.interest_rate IS NULL`, OR
- `profile_data.ratios.dti_back_end_percent IS NULL`

**Sources**:
| Metric | Primary Source | Fallback Sources |
|--------|----------------|------------------|
| Rate | HELOC Agreement | Rate Lock, Closing Disclosure, Note |
| DTI | Rate Lock | Calculate from income/debts |
| CLTV | Rate Lock | Calculate from loan amount / property value |
| FICO | Rate Lock | Credit Report |

**Output**: Updates `profile_data.loan_info` and `profile_data.ratios`

---

### S4: Verification Status

**Purpose**: Determine verification status for summary badges (I, D, C, V)

**Checks**:
| Badge | Attribute | Verification Method |
|-------|-----------|---------------------|
| I | Income | Check evidence_files for income attributes OR find in pay stubs/W2s |
| D | Debt | Check evidence_files for expense attributes OR find in credit report |
| C | Credit | Match credit score in credit report |
| V | Property | Match property value in appraisal/AVM |

**Output**: `profile_data.verification_status`
```json
{
  "income": {"verified": true, "source": "basic_income_worksheet_16.pdf"},
  "debt": {"verified": true, "source": "credit_report___final_27.pdf"},
  "credit_score": {"verified": true, "source": "credit_report___final_27.pdf"},
  "property_value": {"verified": false, "notes": "No appraisal found"}
}
```

---

## 🚀 Running the Pipeline

### Individual Loan
```bash
python summary_s1_extract_profile.py 30
python summary_s2_dscr_calculation.py 30
python summary_s3_non1008_metrics.py 30
python summary_s4_verify_attributes.py 30
```

### All Loans
```bash
python run_summary_pipeline.py
# OR
python run_summary_pipeline.py --loan-id 30
```

---

## 📊 Output: loan_profiles Table

| Column | Type | Description |
|--------|------|-------------|
| loan_id | int | FK to loans |
| profile_data | jsonb | Full profile JSON |
| analysis_source | text | "1008", "URLA only", "Non-Standard Loan App" |
| source_document | text | Filename of source document |
| extracted_at | timestamp | When profile was extracted |

---

## 🔗 Integration with UI

The Loan Management page reads from `loan_profiles`:
- Grid/List view shows summary metrics
- RAG badges calculated from DTI/DSCR and CLTV
- Verification badges (I, D, C, V) from verification_status
- DSCR shown instead of DTI for investment properties

