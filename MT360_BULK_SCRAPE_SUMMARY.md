# MT360 Bulk Scrape Summary

**Generated:** December 18, 2025  
**Status:** ✅ **URL Manifest Complete**

---

## 📊 Quick Stats

| Metric | Count |
|--------|-------|
| **Total Loans** | 10 |
| **Document Types per Loan** | 6 |
| **Total URLs Generated** | 60 |
| **Status** | Ready for bulk scraping |

---

## 📋 Loan Portfolio

### All 10 Loans Identified:

| # | Loan Number | Loan File ID | Status |
|---|-------------|--------------|--------|
| 1 | 105742610 | 1642451 | ✅ URLs Generated |
| 2 | 1225501664 | 1584069 | ✅ URLs Generated |
| 3 | 2046007999 | 1598638 | ✅ URLs Generated |
| 4 | 2052700869 | 1579510 | ✅ URLs Generated |
| 5 | 9230018836 | 1642452 | ✅ URLs Generated |
| 6 | 1551504333 | 1597233 | ✅ URLs Generated |
| 7 | 1225421582 | 1642450 | ✅ URLs Generated |
| 8 | 1457382910 | 1642448 | ✅ URLs Generated |
| 9 | 1525185423 | 1528996 | ✅ URLs Generated |
| 10 | 924087025 | 1642449 | ✅ URLs Generated |

---

## 📑 Document Types (6 per loan)

1. **1008** - URLA/1008 Form
2. **URLA** - Uniform Residential Loan Application  
3. **Note** - Promissory Note
4. **LoanEstimate** - Loan Estimate
5. **ClosingDisclosure** - Closing Disclosure
6. **CreditReport** - Credit Report

**Total URLs:** 10 loans × 6 documents = **60 URLs**

---

## 📁 Files Generated

### Data Files:
- **`scrape_manifest.json`** - Complete manifest with all 60 URLs
- **`bulk_scrape_summary_*.json`** - Summary with metadata
- **10 individual loan JSON files** - One per loan with URLs

### Reports:
- **`bulk_scrape_report_*.md`** - Detailed markdown report
- **`loan_summary_*.csv`** - CSV export for spreadsheet analysis

**Location:** `/Users/sunny/Applications/bts/jpmorgan/mortgage/modda/outputs/mt360_bulk_scrape/`

---

## 🚀 Next Steps: Actual Scraping

### Option 1: Manual Scraping (One at a time)

```bash
cd /Users/sunny/Applications/bts/jpmorgan/mortgage/modda/backend

# For each loan:
python3 mt360_scraper.py \
  --username sbhatnagar \
  --password '@Aa640192S' \
  --loan-id 1642451
```

### Option 2: Automated Bulk Scraping

Create a script that loops through the manifest:

```python
import json
from mt360_scraper import MT360Scraper

# Load manifest
with open('outputs/mt360_bulk_scrape/data/scrape_manifest.json', 'r') as f:
    manifest = json.load(f)

# Initialize scraper
scraper = MT360Scraper("sbhatnagar", "@Aa640192S")
scraper.setup_driver()
scraper.login()

# Loop through all loans
for loan in manifest['scrape_list']:
    loan_file_id = loan['loan_file_id']
    print(f"Scraping loan {loan_file_id}...")
    
    data = scraper.scrape_all_documents(loan_file_id)
    scraper.save_scraped_data(data)
    
    time.sleep(2)  # Be nice to the server

scraper.cleanup()
```

### Option 3: Browser-Based Manual Review

You're currently logged into MT360.com. You can manually navigate to each URL and review the data:

**Example URLs:**
- Loan 1642451 (105742610): https://www.mt360.com/Document/Detail/1642451?type=1008
- Loan 1642452 (9230018836): https://www.mt360.com/Document/Detail/1642452?type=1008
- Loan 1597233 (1551504333): https://www.mt360.com/Document/Detail/1597233?type=1008
- ...and so on

---

## 📈 Scraping Priority

### High Priority (Already Validated):
- ✅ **Loan 1642451** - Full validation complete

### Medium Priority (Similar loans):
- Loan 1642452, 1642448, 1642449, 1642450 (same file ID series)

### All Loans:
- All 10 loans should be scraped for complete portfolio coverage

---

## 💾 Expected Data Volume

**Per Loan:**
- 6 document types
- ~50-100 fields per document
- Estimated ~300-600 data points per loan

**Total Portfolio:**
- 10 loans × 6 documents = 60 documents
- Estimated 3,000-6,000 total data points
- JSON size: ~500KB - 2MB total

---

## ⏱️ Estimated Scraping Time

**With Selenium Automation:**
- ~2-3 minutes per loan (including page loads, data extraction)
- Total: **20-30 minutes for all 10 loans**

**Manual Review:**
- ~5-10 minutes per loan
- Total: **50-100 minutes for all 10 loans**

---

## 🔍 Validation Strategy

After scraping all loans, you can:

1. **Compare across loans** - Identify common patterns and anomalies
2. **Statistical analysis** - Calculate average LTV, DTI, loan amounts, etc.
3. **OCR quality trends** - Track accuracy across different document types
4. **Field completeness** - Identify missing fields across the portfolio

---

## 📊 Sample URL Structure

All URLs follow this pattern:
```
https://www.mt360.com/Document/Detail/{LOAN_FILE_ID}?type={DOCUMENT_TYPE}
```

**Examples:**
- `https://www.mt360.com/Document/Detail/1642451?type=1008`
- `https://www.mt360.com/Document/Detail/1642451?type=URLA`
- `https://www.mt360.com/Document/Detail/1642451?type=Note`
- `https://www.mt360.com/Document/Detail/1642451?type=LoanEstimate`
- `https://www.mt360.com/Document/Detail/1642451?type=ClosingDisclosure`
- `https://www.mt360.com/Document/Detail/1642451?type=CreditReport`

---

## ✅ Current Status

- [x] Identified all 10 loans in MT360 portfolio
- [x] Generated URLs for all 60 documents (10 loans × 6 doc types)
- [x] Created scrape manifest with complete URL list
- [x] Generated reports (Markdown + CSV)
- [x] Validated first loan (1642451) - OCR quality confirmed
- [ ] Scrape remaining 9 loans (ready to execute)
- [ ] Generate bulk validation report
- [ ] Statistical analysis across portfolio

---

## 📞 Support

**MT360 Platform:**
- URL: https://www.mt360.com
- Support: mthelp@mtrade.com
- Phone: 844-MTHELP1

**Current Session:**
- Logged in as: sbhatnagar
- Status: Active
- Access: All 10 loans visible

---

## 🎯 Recommendation

**For complete portfolio validation:**

1. Use the existing `mt360_scraper.py` with a loop to scrape all 10 loans
2. Save each loan's data to individual JSON files
3. Run `validate_mt360_ocr.py` on each loan
4. Generate aggregate statistics and quality metrics

**Estimated Total Time:** 1-2 hours for complete automation and validation

---

**Report Generated:** December 18, 2025  
**Script:** `mt360_bulk_scraper.py`  
**Output Location:** `/outputs/mt360_bulk_scrape/`


