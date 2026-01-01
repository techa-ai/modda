# Stage 1: Document Structure Analysis

This stage analyzes raw PDF files to understand their structure and determine the best extraction strategy.

## Overview

Stage 1 consists of 2 main steps with multiple substeps:

### Step 1: PDF Structure Analysis
1. **1_1_1**: Analyze PDF structure and detect tables
2. **1_1_2**: Generate detailed statistics
3. **1_1_3**: Categorize files by extraction strategy

### Step 2: Deep JSON Extraction
1. **1_2_1**: Deep JSON extraction with Llama 4 Maverick (scanned PDFs)
2. **1_2_2**: Retry failed extractions with adjusted parameters

All outputs are saved to loan-specific folders: `backend/stage1/output/<loan_id>/`

## Naming Convention

Scripts follow the pattern: `{stage}_{step}_{substep}_description.py`

- **1_1_1**: Stage 1, Step 1, Substep 1
- **1_1_2**: Stage 1, Step 1, Substep 2
- **1_1_3**: Stage 1, Step 1, Substep 3
- **1_2_1**: Stage 1, Step 2, Substep 1
- **1_2_2**: Stage 1, Step 2, Substep 2

## Scripts

### Step 1: PDF Structure Analysis

#### 1_1_1_analyze_pdf_structure.py (Main Analysis)

Comprehensive PDF structure analysis that determines:

1. **PDF Type Classification**
   - Text-based PDFs (digitally generated with extractable text)
   - Scanned PDFs (image-based, require OCR)

2. **Table Layout Detection** (for text-based PDFs)
   - No tables: Simple text extraction works fine
   - With tables: **Requires OCR for best results** - tables need proper structure extraction

3. **OCR Recommendations**
   - Scanned PDFs: Always need OCR
   - Text PDFs with tables: Need OCR for accurate extraction

**Output:** `1_1_1_analysis.json`

#### 1_1_2_visualize_results.py (Statistics Generation)

Generates detailed statistics from the analysis:
- File size analysis
- Page count statistics
- Table statistics
- Processing time estimates

**Output:** `1_1_2_statistics.json`

#### 1_1_3_list_by_category.py (File Categorization)

Categorizes PDFs by extraction strategy and saves organized file lists.

**Output:** `1_1_3_categories.json`

### Step 2: Deep JSON Extraction

#### 1_2_1_deep_extract_llama.py (Llama Extraction)

Extracts deep JSON from scanned PDFs using Llama 4 Maverick 17B Instruct:
- Processes all scanned PDFs (excludes large files like tax_returns)
- Handles multi-page documents with batch processing (3 images per batch)
- Saves individual JSON files per document

**Output:** `1_2_1_llama_extractions/<filename>.json` and `extraction_summary.json`

#### 1_2_2_retry_failed.py (Retry Failed)

Retries failed extractions with adjusted parameters:
- Lower DPI (120 instead of 150)
- Smaller batch size (2 images instead of 3)
- Extended timeouts

**Output:** `1_2_2_retry_extractions/<filename>.json` and `retry_summary.json`

### run_all_steps.py (Master Script for Step 1)

Runs all Step 1 substeps (1_1_1, 1_1_2, 1_1_3) in sequence automatically.

## Usage

### Quick Start - Step 1 (Recommended)

Run all Step 1 substeps at once:

```bash
python run_all_steps.py /path/to/loan_folder [sample_pages]
```

**Example:**
```bash
python run_all_steps.py /Users/sunny/Applications/bts/jpmorgan/mortgage/modda/documents/loan_1642451
```

This will:
1. Analyze PDF structure (1_1_1)
2. Generate statistics (1_1_2)
3. Categorize files (1_1_3)
4. Save all outputs to `backend/stage1/output/loan_1642451/`

### Run Individual Step 1 Substeps

If you need to run substeps separately:

```bash
# Step 1.1.1: Analyze PDF structure
python 1_1_1_analyze_pdf_structure.py /path/to/loan_folder [sample_pages]

# Step 1.1.2: Generate statistics (requires 1_1_1 output)
python 1_1_2_visualize_results.py <loan_id>

# Step 1.1.3: Categorize files (requires 1_1_1 output)
python 1_1_3_list_by_category.py <loan_id>
```

**Example:**
```bash
python 1_1_1_analyze_pdf_structure.py /path/to/loan_1642451 3
python 1_1_2_visualize_results.py loan_1642451
python 1_1_3_list_by_category.py loan_1642451
```

### Run Step 2 (Deep Extraction)

After completing Step 1, run deep extraction:

```bash
# Step 1.2.1: Extract JSON from scanned PDFs
python 1_2_1_deep_extract_llama.py <loan_id>

# Step 1.2.2: Retry failed extractions (if any)
python 1_2_2_retry_failed.py <loan_id>
```

**Example:**
```bash
python 1_2_1_deep_extract_llama.py loan_1642451
python 1_2_2_retry_failed.py loan_1642451
```

## Output Structure

All outputs are saved in loan-specific folders:

```
backend/stage1/output/
└── loan_1642451/
    ├── 1_1_1_analysis.json           (Full PDF structure analysis)
    ├── 1_1_2_statistics.json         (Summary statistics)
    ├── 1_1_3_categories.json         (File categorization)
    ├── 1_2_1_llama_extractions/      (Llama extracted JSONs)
    │   ├── <filename>.json
    │   ├── ...
    │   └── extraction_summary.json
    └── 1_2_2_retry_extractions/      (Retry extracted JSONs)
        ├── <filename>.json
        └── retry_summary.json
```

## Dependencies

- `PyPDF2` - Text extraction from PDFs
- `pdfplumber` - Table detection (install with: `pip install pdfplumber`)
- `pdf2image` - PDF to image conversion for Llama
- `boto3` - AWS Bedrock client for Llama 4 Maverick

## Output Files

### 1_1_1_analysis.json
Complete PDF structure analysis with per-file details:
- PDF type (text/scanned)
- Page counts
- Table detection results
- OCR recommendations

### 1_1_2_statistics.json
Summary statistics:
- File size analysis
- Page count totals
- Table statistics
- Processing time estimates
- Extraction strategy breakdown

### 1_1_3_categories.json
Organized file lists by extraction method:
- Scanned PDFs → OCR
- Text PDFs with tables → OCR
- Text PDFs without tables → Text extraction

### 1_2_1_llama_extractions/
Individual JSON files extracted from scanned PDFs using Llama 4 Maverick:
- One JSON file per document
- `extraction_summary.json` with processing details

### 1_2_2_retry_extractions/
Retry extractions for failed documents:
- One JSON file per successfully retried document
- `retry_summary.json` with retry details

## Key Findings (Loan 1642451)

- **74 PDFs total**
- **49 text-based** (66.2%), **25 scanned** (33.8%)
- **44 PDFs need OCR** (59.5%):
  - 25 scanned PDFs
  - 19 text PDFs with tables

### Why Text PDFs with Tables Need OCR

Text PDFs with tables often have:
- Complex column structures
- Overlapping text regions
- Form fields with precise positioning
- Tables within tables

Text extraction from these PDFs often produces garbled output with mixed-up columns and rows. OCR with proper layout analysis provides much better results.

## Next Steps

Based on this analysis:
1. Use simple text extraction for text PDFs without tables
2. Use OCR/LLM extraction for scanned PDFs
3. Use OCR/LLM extraction for text PDFs with tables
4. Compare Llama 4 Maverick extractions with Claude Opus 4.5 extractions

