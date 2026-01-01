# Stage 1: Step Sequence and Output Structure

## Step Naming Convention

All scripts follow the `{stage}_{step}_{substep}` naming pattern:

- **1_1_1**: Stage 1, Step 1, Substep 1 - Primary analysis
- **1_1_2**: Stage 1, Step 1, Substep 2 - Statistics generation (depends on 1_1_1)
- **1_1_3**: Stage 1, Step 1, Substep 3 - File categorization (depends on 1_1_1)
- **1_2_1**: Stage 1, Step 2, Substep 1 - Deep JSON extraction with Llama
- **1_2_2**: Stage 1, Step 2, Substep 2 - Retry failed extractions

## Sequential Workflow

```
┌─────────────────────────────────────────────────────────┐
│  INPUT: Raw PDF files in loan folder                   │
│  /path/to/documents/loan_1642451/*.pdf                 │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  STEP 1.1.1: Analyze PDF Structure                     │
│  - Detect text vs scanned PDFs                         │
│  - Find tables in text PDFs                            │
│  - Determine OCR requirements                          │
│  OUTPUT: 1_1_1_analysis.json (71 KB)                   │
└─────────────────────────────────────────────────────────┘
                         │
                    ┌────┴────┐
                    │         │
                    ▼         ▼
┌─────────────────────┐ ┌──────────────────────┐
│  STEP 1.1.2:        │ │  STEP 1.1.3:         │
│  Generate Stats     │ │  Categorize Files    │
│  - File sizes       │ │  - Scanned PDFs      │
│  - Page counts      │ │  - Text w/ tables    │
│  - Table stats      │ │  - Text no tables    │
│  - Time estimates   │ │  - Extraction plan   │
│  OUTPUT:            │ │  OUTPUT:             │
│  1_1_2_stats.json   │ │  1_1_3_cats.json     │
│  (4.3 KB)           │ │  (3.5 KB)            │
└─────────────────────┘ └──────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  STEP 1.2.1: Deep JSON Extraction (Llama 4 Maverick)   │
│  - Extract from scanned PDFs                           │
│  - Batch processing for multi-page docs                │
│  OUTPUT: 1_2_1_llama_extractions/ (24 JSONs)           │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  STEP 1.2.2: Retry Failed Extractions                  │
│  - Retry with adjusted parameters                      │
│  OUTPUT: 1_2_2_retry_extractions/ (recovered JSONs)    │
└─────────────────────────────────────────────────────────┘
```

## Output Structure

### Directory Layout

```
backend/stage1/
├── 1_1_1_analyze_pdf_structure.py
├── 1_1_2_visualize_results.py
├── 1_1_3_list_by_category.py
├── 1_2_1_deep_extract_llama.py
├── 1_2_2_retry_failed.py
├── run_all_steps.py (master script for Step 1.1)
├── README.md
└── output/
    ├── .gitignore
    └── <loan_id>/
        ├── 1_1_1_analysis.json           (~71 KB)
        ├── 1_1_2_statistics.json         (~4 KB)
        ├── 1_1_3_categories.json         (~3 KB)
        ├── 1_2_1_llama_extractions/      (Llama JSONs)
        └── 1_2_2_retry_extractions/      (Retry JSONs)
```

### Per-Loan Output Folder

Each loan gets its own output folder named by loan_id:

- `loan_1642451/` 
- `loan_1642452/`
- etc.

All JSON outputs are saved in the loan-specific folder for easy organization and reference.

## File Descriptions

### 1_1_1_analysis.json
**Size:** ~71 KB  
**Purpose:** Complete analysis with per-file details

**Contents:**
```json
{
  "loan_folder": "/path/to/loan_1642451",
  "total_pdfs": 74,
  "text_based_count": 49,
  "scanned_count": 25,
  "details": [
    {
      "filename": "1008___final_0.pdf",
      "page_count": 1,
      "is_text_based": true,
      "has_tables": true,
      "table_analysis": {
        "total_tables_found": 8,
        "pages_with_multi_table": 1
      },
      "needs_ocr": true,
      "ocr_reason": "has_tables"
    }
    // ... 73 more files
  ]
}
```

### step1_2_statistics.json
**Size:** ~4 KB  
**Purpose:** Aggregated statistics and metrics

**Contents:**
```json
{
  "summary": {
    "total_pdfs": 74,
    "text_based_count": 49,
    "scanned_count": 25
  },
  "extraction_strategy": {
    "pdfs_need_ocr": 50,
    "pdfs_text_extraction": 24
  },
  "file_size_analysis": {
    "total_size_mb": 27.77,
    "average_size_kb": 384.22
  },
  "table_statistics": {
    "total_tables_found": 158,
    "avg_tables_per_pdf": 6.3
  },
  "processing_estimates": {
    "total_minutes": 25.8
  }
}
```

### step1_3_categories.json
**Size:** ~3 KB  
**Purpose:** Organized file lists by extraction method

**Contents:**
```json
{
  "categories": {
    "scanned_pdfs_ocr": {
      "count": 25,
      "files": ["1103_final_1.pdf", "4506_c_3.pdf", ...]
    },
    "text_pdfs_with_tables_ocr": {
      "count": 25,
      "files": ["1008___final_0.pdf", "credit_report_27.pdf", ...]
    },
    "text_pdfs_no_tables_text_extraction": {
      "count": 24,
      "files": ["additional_disclosures_7.pdf", ...]
    }
  },
  "extraction_summary": {
    "ocr_required": 50,
    "text_extraction": 24
  }
}
```

## Usage Examples

### Run All Steps (Recommended)

```bash
cd backend/stage1
python run_all_steps.py /path/to/documents/loan_1642451
```

**Output:**
```
🚀 STAGE 1: PDF STRUCTURE ANALYSIS - loan_1642451

📊 Step 1.1: Analyzing PDF structure...
✅ Step 1.1 complete: output/loan_1642451/step1_1_analysis.json

📈 Step 1.2: Generating statistics...
✅ Step 1.2 complete: output/loan_1642451/step1_2_statistics.json

📋 Step 1.3: Categorizing files...
✅ Step 1.3 complete: output/loan_1642451/step1_3_categories.json

✅ ALL STEPS COMPLETED SUCCESSFULLY!
```

### Run Individual Steps

```bash
# Step 1.1 only
python step1_1_analyze_pdf_structure.py /path/to/loan_1642451

# Then steps 1.2 and 1.3 (require loan_id)
python step1_2_visualize_results.py loan_1642451
python step1_3_list_by_category.py loan_1642451
```

## Data Flow

1. **step1_1** reads raw PDFs → produces `step1_1_analysis.json`
2. **step1_2** reads `step1_1_analysis.json` → produces `step1_2_statistics.json`
3. **step1_3** reads `step1_1_analysis.json` → produces `step1_3_categories.json`

**Note:** Steps 1.2 and 1.3 are independent and can run in parallel after step 1.1 completes.

## Benefits of This Structure

1. **Clear Sequence:** Numbered steps show execution order
2. **Loan-Specific Outputs:** Each loan has its own folder
3. **Reusable:** Can rerun individual steps without reanalyzing
4. **Traceable:** Timestamped outputs for audit trail
5. **Scalable:** Easy to add more loans or more steps

## Processing Time

For loan_1642451 (74 PDFs, 2504 pages):

- **Step 1.1:** ~60 seconds (PDF analysis + table detection)
- **Step 1.2:** ~1 second (statistics generation)
- **Step 1.3:** ~1 second (file categorization)
- **Total:** ~62 seconds

---

**Created:** December 18, 2025  
**Structure:** Sequential steps with loan-specific JSON outputs  
**Maintenance:** Outputs are gitignored, regenerate as needed

