# Refined Document Processing Pipeline V2

## 🎯 **Final Optimized Sequence**

```
1. Ingest
   ├─ Extract 1008 data
   └─ Store all PDFs in document_analysis

2. Dedup (hash-based)
   ├─ Text hash (SHA-256) for exact duplicates
   └─ Visual hash (phash/dhash/ahash) for similar docs

3. Deep Extract (Opus page-wise)
   ├─ Page-by-page JSON extraction
   ├─ Document summary (metadata-rich)
   └─ Stores in individual_analysis->document_summary

3.1. Deep Extract (Small pages failed)
    └─ Retry extraction for docs < 20 pages that failed

4. Metadata Extraction
   ├─ Extract from document_summary:
   │  ├─ document_type
   │  ├─ borrower_name, co_borrower_name
   │  ├─ document_date, period_covered
   │  ├─ has_signature
   │  ├─ issuer, account_numbers
   │  ├─ financial details (income, debt, loan amounts)
   │  └─ completeness status
   └─ Store in version_metadata

5. Global Classification
   ├─ Analyze ALL documents together with Claude
   ├─ Classification: FINANCIAL vs NON-FINANCIAL
   ├─ Document Type: Standard industry names
   ├─ Dates: YYYY-MM-DD format
   ├─ Signers: Borrower/Co-Borrower/Both/Unsigned
   ├─ Signed Status: Signed or Unsigned
   ├─ Grouping: Related docs (siblings, versions, duplicates)
   └─ Primary Selection: Best/latest version in each group

6. AI Grouping
   ├─ Semantic document understanding (Claude VLM)
   ├─ Groups related documents by meaning
   ├─ Groups versions (Initial → Preliminary → Final)
   ├─ Creates ai_group_id
   └─ Handles complex relationships visual hashing misses

7. AI Versioning
   ├─ Uses ai_group_id from Step 6
   ├─ Determines latest version intelligently
   ├─ Handles version progressions
   ├─ Updates is_latest_version flag
   └─ Sets status: master/unique/superseded

8. Knowledge Graph Creation
   ├─ Filter: ONLY latest version docs (is_latest_version = TRUE)
   ├─ Build revised full JSON from deduplicated latest versions
   ├─ Batch process in 100K token chunks (~400K chars)
   ├─ Extract entities and relationships
   ├─ Build compressed knowledge graph
   └─ Incremental saving after each batch
```

---

## 📊 **Key Changes from V1**

### **Removed Steps (Redundant):**
- ❌ `step4a_filename_audit.py` - Covered by Global Classification (Step 5)
- ❌ `step4b_generate_summaries.py` - Covered by Global Classification (Step 5)
- ❌ `step7_reversioning.py` (old) - Replaced by AI Versioning (Step 7)
- ❌ `step5_financial_classification.py` - Replaced by Global Classification (Step 5)

### **New Steps (AI-Powered):**
- ✅ `step6_global_classification.py` - Comprehensive classification + grouping
- ✅ `step3_comprehensive_grouping.py` - AI semantic document grouping
- ✅ `step7_apply_ai_versioning.py` - AI-driven version identification

---

## 🔍 **What Each Step Provides**

| Step | Script | Output Fields | Purpose |
|------|--------|---------------|---------|
| 1 | `processing.py` | - | Ingest PDFs, extract 1008 |
| 2 | `dedup_task.py` | `text_hash`, `visual_phash/dhash/ahash`, `status: duplicate/unique` | Remove exact duplicates |
| 3 | `step5_deep_extraction.py` | `individual_analysis->document_summary` | Rich page-wise JSON + summary |
| 4 | `step4_extract_metadata.py` | `version_metadata->{document_type, borrower_name, document_date, has_signature, etc}` | Structured metadata from summary |
| 5 | `step6_global_classification.py` | `version_metadata->{classification, doc_type, doc_date, signers, signed_status, group_id, is_primary}` | Full classification + grouping |
| 6 | `step3_comprehensive_grouping.py` | `version_metadata->ai_group_id` | Semantic document groups |
| 7 | `step7_apply_ai_versioning.py` | `is_latest_version`, `status: master/unique/superseded` | Latest version identification |
| 8 | `step6_generate_knowledge_graph.py` | `loans->knowledge_graph` (JSONB) | Compressed entity-relationship graph (latest versions only) |

---

## 💡 **Why This Solves the URLA Problem**

### Before (Visual Hashing Only):
```
initial_urla_42.pdf        → Group 077f6d90 → status: unique → is_latest: TRUE
urla___preliminary_71.pdf  → Group 077f6d90 → status: unique → is_latest: TRUE
urla___final_70.pdf        → No Group      → status: unique → is_latest: TRUE
```
**Problem**: All 3 marked as "latest" → Knowledge graph has duplicate/conflicting info

### After (AI Grouping + Versioning + Clean KG):
```
Step 6 (AI Grouping):
  → Claude recognizes all 3 are URLA 1003 forms
  → Creates ai_group_id: "urla_1003_group"
  → Groups them together by semantic meaning

Step 7 (AI Versioning):
  → Within "urla_1003_group":
    - initial_urla_42.pdf    → is_latest: FALSE, status: superseded
    - urla___preliminary_71.pdf → is_latest: FALSE, status: superseded
    - urla___final_70.pdf    → is_latest: TRUE, status: master

Step 8 (Knowledge Graph):
  → Query filters: WHERE is_latest_version = TRUE
  → ONLY urla___final_70.pdf is included in KG
  → Superseded versions are excluded
```
**Result**: Clean knowledge graph with no duplicate/conflicting URLA information

---

## 🚀 **Next Steps**

1. ✅ **Pipeline Updated** - `batch_process_loans.py` now uses refined sequence
2. ⏳ **Test on Loan 27** - Run refined pipeline to verify URLA versioning
3. ⏳ **Knowledge Graph** - Regenerate KG with clean document versions
4. ⏳ **Batch Process** - Apply to all 12 loans

---

## 📝 **Implementation Details**

### Script Locations:
- **Batch Orchestrator**: `batch_process_loans.py`
- **Global Classification**: `step6_global_classification.py`
- **AI Grouping**: `step3_comprehensive_grouping.py`
- **AI Versioning**: `step7_apply_ai_versioning.py`
- **Knowledge Graph**: `step6_generate_knowledge_graph.py`

### Execution:
```bash
# Single loan
python3 batch_process_loans.py --loans loan_1642451 --skip-copy --concurrency 10

# All loans
python3 batch_process_loans.py --concurrency 10
```

### Expected Time:
- **Deep Extraction**: 2-4 hours (largest time sink)
- **Metadata Extraction**: 5-10 minutes
- **Global Classification**: 30-60 minutes (Claude analyzes all docs)
- **AI Grouping**: 1-2 hours (VLM for semantic understanding)
- **AI Versioning**: 15-30 minutes
- **Total**: ~4-8 hours per loan

---

## ✨ **Benefits**

1. **Accurate Versioning**: AI understands document relationships
2. **Clean Knowledge Graph**: No duplicate/conflicting information
3. **Reduced Redundancy**: Removed 4 redundant scripts
4. **Comprehensive Metadata**: All classification in one place
5. **Scalable**: Same process works for all document types
6. **Maintainable**: Clear, documented pipeline

