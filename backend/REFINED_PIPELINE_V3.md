# Refined Document Processing Pipeline V3 (Data Tape Architecture)

## 🎯 **Final Optimized Sequence**

```
1. Ingest
   └─ Store all PDFs in document_analysis

2. Dedup (hash-based)
   ├─ Text hash (SHA-256) for exact duplicates
   └─ Visual hash (phash/dhash/ahash) for similar docs

3. Deep Extract (Opus page-wise)
   ├─ Page-by-page JSON extraction
   └─ Stores in individual_analysis->document_summary

4. Metadata Extraction
   └─ Extract structured fields from document_summary

5. Global Classification
   ├─ Analyze ALL documents together
   ├─ Classification: FINANCIAL vs NON-FINANCIAL
   ├─ Document Type: 1008, 1003, Paystubs, W2s, etc.
   └─ Grouping: Related docs

6. AI Grouping
   └─ Semantic grouping of related documents

7. AI Versioning
   ├─ Identify LATEST/MASTER version for each group
   └─ Sets status: master/unique/superseded

-----------------------------------------------------------
   CORE DOCUMENT PROCESSING COMPLETE
-----------------------------------------------------------

8. Data Tape Construction (formerly 1008 Extraction)
   ├─ Locate TARGET form:
   │   1. Check for Master 1008 (Transmittal Summary)
   │   2. Fallback to Master 1003 (URLA)
   ├─ Extract target attributes (Income, Ratios, Loan Details)
   └─ Populate `extracted_1008_data` (Data Tape)

9. Systematic Verification (Golden Standard)
   ├─ Input: Data Tape Attributes (from Step 8)
   ├─ Input: All Master Source Documents (from Step 7)
   ├─ Execute `run_full_verification.py`
   └─ Generate calculation steps and verification status
```

## 🔄 **Key Changes**
1. **Moved Extraction**: 1008/1003 extraction is now **Step 8**, occurring AFTER we know which document version is the "Master".
2. **Fallback Logic**: Explicitly handles 1008 → 1003 fallback.
3. **Renaming**: "1008 Evidencing" → "Data Tape Validation".
4. **Clean Separation**: Processing (Steps 1-7) vs. Analysis (Steps 8-9).

## 💡 **Why This is Better**
- We only extract data from the **FINAL/MASTER** 1008 or 1003 (avoiding preliminary versions).
- We handle cases where 1008 is missing (common).
- Verification runs on clean, versioned data.

