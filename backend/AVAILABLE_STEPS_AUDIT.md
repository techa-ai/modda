# Document Processing Pipeline - Available Scripts Audit

## ✅ **Currently in Batch Pipeline** (`batch_process_loans.py`)

| Step | Script | Purpose | Status |
|------|--------|---------|--------|
| 1 | `processing.py` | Initial document ingestion & 1008 extraction | ✅ Active |
| 2 | `dedup_task.py` | Text/visual hash deduplication | ✅ Active |
| 3 | `step5_deep_extraction.py` | Page-wise deep JSON + doc summary (Opus) | ✅ Active |
| 4 | `step4_extract_metadata.py` | Extract metadata from `document_summary` | ✅ Active |
| 5 | `step4a_filename_audit.py` | Audit filenames, generate content-based names | ✅ Active |
| 6 | `step4b_generate_summaries.py` | Generate rich UI display summaries | ✅ Active |
| 7 | `step7_reversioning.py` | Re-version with rich metadata (signature, date, version indicator) | ✅ Active |
| 8 | `step5_financial_classification.py` | Classify FINANCIAL vs NON-FINANCIAL | ✅ Active |

---

## ❌ **MISSING from Batch Pipeline** (Available but NOT called)

### 🔴 **CRITICAL - Document Tagging & Clustering**

#### 1. **`step2_llm_analysis.py`** - Initial LLM Document Analysis
**Purpose**: First-pass document analysis using Claude VLM
- Extracts: `document_type`, `borrower_name`, `co_borrower_name`, `ssn`, `employer`, `document_date`, `period_covered`, `account_numbers`, `has_signature`, `version_indicator`, `page_numbers_visible`, `content_consistent`, `filename_matches_content`, `anomalies`
- Stores results in `version_metadata`
- **Why Missing**: Replaced by `step5_deep_extraction.py` (which does deeper analysis)
- **Recommendation**: ⚠️ **May not be needed** - deep extraction covers this

---

#### 2. **`step3_comprehensive_grouping.py`** - AI Document Grouping
**Purpose**: Groups documents using Claude VLM for semantic understanding
- Groups related documents (e.g., Borrower W-2 + Co-Borrower W-2)
- Groups versions (Preliminary → Final)
- Uses Claude to understand document relationships beyond visual similarity
- Creates `ai_group_id` in `version_metadata`
- **Why Missing**: Currently using only `version_task.py` (visual hashing)
- **Recommendation**: 🔥 **SHOULD BE ADDED** - Much smarter than visual hashing alone

---

#### 3. **`step7_apply_ai_versioning.py`** - AI-Driven Versioning
**Purpose**: Uses AI grouping results to determine latest versions
- Requires `version_metadata->>'ai_group_id'` from Step 3
- Uses Claude's understanding of document relationships
- Handles complex cases like:
  - Initial URLA → Preliminary URLA → Final URLA
  - Documents that look different but are versions
  - Borrower/Co-Borrower distinction
- **Why Missing**: No AI grouping step before it
- **Recommendation**: 🔥 **SHOULD BE ADDED** - After Step 3

---

#### 4. **`step4_enrich_groups.py`** - Group Enrichment
**Purpose**: Enriches version groups with comparative analysis
- Compares documents within groups
- Identifies what changed between versions
- Adds enrichment metadata
- **Why Missing**: Unclear - might be replaced by step7_reversioning
- **Recommendation**: ⚠️ **Evaluate** - May be redundant with current pipeline

---

#### 5. **`step6_global_classification.py`** - Global Classification with Grouping
**Purpose**: Global classification + grouping in one pass
- Classifies ALL documents (FINANCIAL vs NON-FINANCIAL)
- Groups related documents (siblings, versions, duplicates)
- Returns structured JSON with group descriptions
- **Why Missing**: Currently using `step5_financial_classification.py` (no grouping)
- **Recommendation**: 🔥 **SHOULD REPLACE** `step5_financial_classification.py` - More comprehensive

---

#### 6. **`step6a_audit_and_extract.py`** - Financial JSON Extraction
**Purpose**: Targeted JSON extraction for financial documents only
- Extracts detailed JSON from financial docs (<10 pages)
- Uses cache to avoid re-extraction
- Parallel processing (5 workers)
- **Why Missing**: `step5_deep_extraction.py` extracts ALL docs, not just financial
- **Recommendation**: ⚠️ **Evaluate** - May be optimization for financial-only extraction

---

#### 7. **`version_task.py`** - Visual Version Analysis (OLD)
**Purpose**: Visual hash-based version detection
- Uses phash/dhash/ahash for similarity
- Date extraction and version priority (final > preliminary)
- Simple pairwise clustering
- **Current Status**: Used in OLD deduplication, but NOT in batch pipeline
- **Recommendation**: ⚠️ **Being replaced** by AI versioning

---

## 📊 **Recommended Pipeline Update**

### Current Order:
```
1. Ingest → 2. Dedup → 3. Deep Extract → 4. Metadata → 5. Filename Audit 
→ 6. Summaries → 7. Reversioning → 8. Classification
```

### Recommended Order:
```
1. Ingest
2. Dedup (text/visual hash)
3. Deep Extract (Opus page-wise)
4. Metadata Extraction
5. Filename Audit
6. Summaries
7. 🆕 AI Grouping (step3_comprehensive_grouping.py)
8. 🆕 AI Versioning (step7_apply_ai_versioning.py)
9. 🔄 Global Classification (step6_global_classification.py) [replaces step5]
10. [Optional] Enrich Groups (step4_enrich_groups.py)
```

---

## 🎯 **Key Issue Identified**

### Problem: URLA Versioning Failure
- **Current**: Only visual hashing (`version_task.py`) → Initial/Preliminary/Final URLA don't match
- **Solution**: Use AI Grouping (`step3`) + AI Versioning (`step7_apply_ai_versioning.py`)
- **Impact**: Knowledge graph includes duplicate URLA versions marked as "latest"

---

## 📝 **Action Items**

### High Priority:
1. ✅ Add `step3_comprehensive_grouping.py` after deep extraction
2. ✅ Add `step7_apply_ai_versioning.py` after AI grouping
3. ✅ Replace `step5_financial_classification.py` with `step6_global_classification.py`

### Medium Priority:
4. ⚠️ Evaluate `step4_enrich_groups.py` - keep or discard?
5. ⚠️ Evaluate `step6a_audit_and_extract.py` - optimization worth it?

### Low Priority:
6. 🗑️ Remove `step2_llm_analysis.py` - redundant with deep extraction

---

## 💡 **Why This Matters**

### Without AI Grouping/Versioning:
- ❌ Initial URLA + Preliminary URLA + Final URLA → 3 separate "latest" documents
- ❌ Knowledge graph has duplicate/conflicting information
- ❌ Evidence gathering uses wrong versions

### With AI Grouping/Versioning:
- ✅ Claude understands they're the same document type
- ✅ Groups them by semantic meaning (not just visual similarity)
- ✅ Correctly marks only Final URLA as latest
- ✅ Knowledge graph is clean and accurate






