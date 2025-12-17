# MODDA Document Processing Pipeline

## Overview
This pipeline processes raw mortgage loan documents through multiple stages to create
evidence-backed 1008 form verification with multi-step calculations.

## Pipeline Stages

### Stage 1: Document Ingestion
**Script**: `processing.py` (triggered via API)
**Input**: Raw PDF documents from loan folder (279 documents typical)
**Output**: Documents loaded into `document_analysis` table
**Actions**:
- Load PDFs from loan folder
- Extract basic metadata (filename, path, page count, hash)
- Store in `document_analysis` table

### Stage 2: Deduplication
**Scripts**: `dedup_task.py`, `dedup_utils.py`
**Input**: All documents in `document_analysis`
**Output**: Duplicate documents flagged (status='duplicate')
**Actions**:
- Calculate content hashes for each document
- Identify exact duplicates by hash
- Flag duplicates, keep one representative

### Stage 3: LLM Analysis & Classification
**Script**: `step2_llm_analysis.py`
**Input**: Unique documents
**Output**: `version_metadata` populated with doc_type, financial_category
**Actions**:
- Use Claude to analyze each document
- Determine document type (1008, URLA, Credit Report, etc.)
- Classify as FINANCIAL or NON-FINANCIAL

### Stage 4: Document Grouping
**Script**: `step3_comprehensive_grouping.py`
**Input**: Classified documents
**Output**: `version_group_id` populated
**Actions**:
- Group similar documents together (e.g., all W-2s)
- Create version groups for related documents

### Stage 5: Version Detection
**Scripts**: `step4_enrich_groups.py`, `step7_apply_ai_versioning.py`
**Input**: Grouped documents
**Output**: `is_latest_version` flag set
**Actions**:
- Within each group, identify versions (preliminary, final)
- Mark latest/best version for each document type

### Stage 6: Important Document Identification
**Script**: `step6_global_classification.py`, `step6a_audit_and_extract.py`
**Input**: Versioned documents
**Output**: Documents classified by importance for 1008 verification
**Important Documents for 1008**:
- 1008 Transmittal Form (source of truth)
- Credit Report (debts, mortgage payment)
- Purchase Agreement (sales price)
- Loan Estimate (P&I, loan terms)
- Tax Returns (income)
- URLA (borrower info, expenses)
- Appraisal (property value)
- Hazard Insurance Policy (insurance premium)
- HOA Documents (HOA fees)
- Bank Statements (assets)

### Stage 5b: Deep JSON Extraction
**Script**: `step5_deep_extraction.py`
**Input**: All unique documents (skip >50 pages, skip large bank statements)
**Output**: `individual_analysis` with:
  - `pages[]` - Page-by-page extracted data
  - `document_summary{}` - Comprehensive summary with financial_summary, important_values
**Actions**:
- Use Claude Opus 4.5 to extract structured data page-by-page
- Create document_summary aggregating all page data
- Store page references for each extracted value
- Documents are "deep extracted" ONLY if they have `document_summary` key
**Critical Check**:
```sql
-- Documents needing deep extraction:
SELECT COUNT(*) FROM document_analysis 
WHERE individual_analysis->'document_summary' IS NULL;
```

### Stage 6: Important Document Identification (LEGACY)
**Scripts**: `step6_global_classification.py`, `step6a_audit_and_extract.py`
(Merged into Stage 5b - all unique docs get deep extraction now)

### Stage 8: Evidence Identification
**Script**: `step8_identify_evidence.py`
**Input**: 1008 form attributes, Important documents with VLM analysis
**Output**: `evidence_files` table populated
**Actions**:
- For each 1008 attribute, find supporting evidence documents
- Use Claude to match values across documents
- Store evidence mappings with confidence scores

### Stage 9: Multi-Step Calculation Generation (NEW)
**Script**: `step9_generate_calculations.py` (TO BE CREATED)
**Input**: Evidence files, VLM analysis data
**Output**: `calculation_steps` table populated
**Actions**:
- For each 1008 attribute that requires calculation:
  - Ask Claude to create step-by-step calculation breakdown
  - Include document references (document_id, page_number) for each value
  - Store each step with rationale
- Single-value attributes get 1 step pointing to source document/page

### Stage 10: Frontend Display
**Frontend**: `LoanDetailPage.jsx`, `VerificationModal.jsx`, `EvidenceDocumentModal.jsx`
**Input**: `calculation_steps`, `evidence_files`, `vlm_analysis`
**Output**: 1008 Evidencing tab with:
- Multi-step calculations showing document links
- Clickable documents that open to correct page
- Green checkmarks for final steps matching 1008 values

---

## Database Tables

### Core Tables
- `loans` - Loan metadata
- `document_analysis` - All documents with metadata and VLM analysis
- `form_1008_attributes` - 1008 form field definitions
- `extracted_1008_data` - Values extracted from 1008 form

### Evidence Tables
- `evidence_files` - Evidence document mappings to 1008 attributes
- `calculation_steps` - Multi-step calculation breakdowns with doc references

---

## Running the Pipeline

```bash
# Full pipeline for a new loan
python run_pipeline.py --loan-id 1 --stages all

# Individual stages
python run_pipeline.py --loan-id 1 --stages ingest,dedup,classify
python run_pipeline.py --loan-id 1 --stages deep-extract
python run_pipeline.py --loan-id 1 --stages evidence,calculations
```

---

## Key Principles

1. **No Hardcoding** - All values come from source documents via Claude extraction
2. **Document References** - Every value must have document_id and page_number
3. **Systematic Processing** - Use Claude to analyze documents, not manual entry
4. **Audit Trail** - Full traceability from 1008 value → calculation steps → source documents

