# Smart Deep Extraction Pre-Screening Strategy

## Problem
Current deep extraction extracts ALL pages, including:
- ❌ Terms & conditions
- ❌ Glossaries and code explanations  
- ❌ Forms for OTHER shareholders (e.g., Lynn D. Julian's K-1)
- ❌ Blank pages
- ✅ BUT misses some relevant pages (e.g., Georgia Schedule 1 detailed lines)

## Solution: 3-Step Pre-Screening Process

### Step 1: PDF to Images
- Extract PDF pages as images (DPI: 150 for speed)
- Process in batches to manage memory

### Step 2: Local PaddleOCR
- Run fast local OCR to get text from each page
- ~1-2 seconds per page
- No API costs
- Extract ~3000 chars per page for Claude analysis

### Step 3: Claude Decision
- Send OCR text to Claude Opus
- Ask: "Does this page need deep extraction?"
- Claude evaluates based on:
  - **YES**: Contains financial data for borrower (income, K-1, depreciation, etc.)
  - **NO**: Generic content, other people's forms, glossaries, etc.

## Test Cases (from tax_returns_65.pdf)

### Test 1: Georgia Schedule 1 (Pages 2265-2271)
**Expected**: ✅ ELIGIBLE
**Reason**: Contains state tax return with line items and values for Robert M. Dugan

### Test 2: K-1 for Lynn D. Julian (Page 2140)
**Expected**: ❌ NOT ELIGIBLE  
**Reason**: Form is for different shareholder, not borrower of interest

### Test 3: Code Explanations (Pages 88-89)
**Expected**: ❌ NOT ELIGIBLE
**Reason**: Generic glossary/reference material, no financial values

## Benefits

1. **Cost Reduction**: Don't send irrelevant pages to expensive Opus deep extraction
2. **Accuracy**: Focus deep extraction on truly relevant pages
3. **Speed**: Filter out ~30-50% of pages upfront
4. **Quality**: Catch pages that were missed before (like Georgia Schedule 1 details)

## Next Steps

1. ✅ Test screening on sample pages (in progress)
2. Measure accuracy and adjust criteria
3. Build full pipeline: Screen → Deep Extract → Evidence Generation
4. Run on all tax returns in loan portfolio

## Expected Outcomes

- **Accuracy**: >90% correct decisions on page relevance
- **Cost Savings**: 30-50% reduction in deep extraction tokens
- **Better Coverage**: Catch state-specific forms and detailed schedules
- **Faster Processing**: Skip unnecessary pages upfront



