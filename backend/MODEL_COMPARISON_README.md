# Model Comparison: Claude Opus 4.5 vs Llama 4 Maverick 17B

## Overview

This toolkit provides head-to-head comparison between:
- **Claude Opus 4.5** (global.anthropic.claude-opus-4-5-20251101-v1:0)
- **Llama 4 Maverick 17B** (global.meta.llama4-maverick-17b-instruct-v1:0)

For deep JSON extraction of Form 1008 (Uniform Underwriting and Transmittal Summary).

## Problem Statement

Form 1008 presents significant challenges:
- **Table Alignment Issues**: Multiple columns (Borrower, Co-Borrower, Combined)
- **Visual Misalignment**: Values may appear shifted from their labels
- **Complex Calculations**: Multiple sections with sums that must validate
- **Critical Fields**: DTI ratios, income calculations, payment obligations

## Tools

### 1. Single Form Comparison

**File:** `compare_opus_vs_llama.py`

Compare extraction on a single 1008 form.

**Usage:**
```bash
python3 compare_opus_vs_llama.py <pdf_path> [--output-dir <dir>]
```

**Example:**
```bash
# Compare loan 30's 1008 form
python3 compare_opus_vs_llama.py \
    ../public/loans/loan_1579510/1008___final_0.pdf \
    --output-dir ../outputs/model_comparison/loan_1579510
```

**Quick Run (Loan 30):**
```bash
./run_loan30_comparison.sh
```

**Output:**
- `claude_opus_4.5_<timestamp>.json` - Full Claude extraction
- `llama_maverick_17b_<timestamp>.json` - Full Llama extraction
- `comparison_<timestamp>.json` - Detailed comparison data
- `report_<timestamp>.md` - Human-readable comparison report

### 2. Batch Comparison

**File:** `batch_compare_1008.py`

Run comparisons across multiple 1008 forms.

**Usage:**
```bash
python3 batch_compare_1008.py [options]
```

**Options:**
- `--base-dir <dir>` - Base directory with loan folders (default: `public/loans`)
- `--output-dir <dir>` - Output directory (default: `outputs/model_comparison`)
- `--max-forms <n>` - Limit number of forms to process
- `--loan-ids <id1> <id2> ...` - Process specific loan IDs only

**Examples:**
```bash
# Compare all 1008 forms found
python3 batch_compare_1008.py

# Compare only first 5 forms
python3 batch_compare_1008.py --max-forms 5

# Compare specific loans
python3 batch_compare_1008.py --loan-ids loan_1579510 loan_1439728

# Compare all in custom directory
python3 batch_compare_1008.py \
    --base-dir /path/to/loans \
    --output-dir /path/to/output
```

**Output:**
- Individual comparison results in `<output-dir>/<loan_id>/`
- `batch_summary_<timestamp>.json` - Aggregate statistics
- `batch_summary_<timestamp>.md` - Summary report

## Comparison Metrics

### Performance
- **Duration**: Time to complete extraction (seconds)
- **Tokens**: Input/output token counts
- **Speed Winner**: Faster model

### Accuracy
- **Critical Field Match Rate**: % of key fields that match
- **Critical Fields Evaluated**:
  - Combined Total Income
  - Total Primary Housing Expense
  - Total All Monthly Payments
  - Total Debt Ratio
  - Original Loan Amount
  - And more...

### Differences
- **Type Mismatches**: Different data types extracted
- **Value Mismatches**: Different values for same field
- **Missing Fields**: Fields extracted by one model but not the other
- **Structural Differences**: Nested structure variations

## Evaluation Focus

### Table Alignment Issues (HIGH PRIORITY)
1. **Stable Monthly Income Table**
   - Borrower vs Co-Borrower column alignment
   - Base Income, Other Income, Positive Cash Flow, Total
   - Combined Total calculation

2. **Proposed Monthly Payments**
   - P&I, Insurance, Taxes, MI, HOA, etc.
   - Total Primary Housing Expense calculation

3. **Other Obligations** (CRITICAL PROBLEM AREA)
   - "All Other Monthly Payments" (small number)
   - "Negative Cash Flow" (subject property)
   - "Total All Monthly Payments" (large number)
   - **Common Issue**: Visual misalignment causes incorrect assignment
   - **Math Validation**: Total = Primary + Other + Negative Cash Flow

### Numerical Precision
- Decimal places preserved (e.g., 6.875%)
- Large numbers (e.g., $1,276,000.00)
- Small numbers (e.g., $267.93)

### Structural Completeness
- All sections extracted
- Nested structures maintained
- Null/empty fields handled correctly

## Expected Output Structure

```json
{
  "document_metadata": {
    "form_name": "Uniform Underwriting and Transmittal Summary",
    "fannie_mae_form_number": "1008",
    "page_count": 1
  },
  "section_1_borrower_and_property": {
    "borrower": {"name": "...", "ssn": "..."},
    "co_borrower": {"name": "...", "ssn": "..."},
    "property": {...}
  },
  "section_2_mortgage_information": {...},
  "section_3_underwriting_information": {
    "stable_monthly_income": {
      "borrower": {...},
      "co_borrower": {...},
      "combined_total": {...}
    },
    "proposed_monthly_payments": {...},
    "other_obligations": {
      "all_other_monthly_payments": 0.0,
      "negative_cash_flow": 0.0,
      "total_all_monthly_payments": 0.0
    },
    "ratios": {...}
  },
  "section_4_aus_recommendation": {...},
  "section_5_underwriter_certification": {...}
}
```

## Interpretation Guide

### Reading the Comparison Report

#### Performance Section
```markdown
| Metric | Claude Opus 4.5 | Llama Maverick 17B | Winner |
|--------|-----------------|-------------------|--------|
| Duration | 45.2s | 38.7s | LLAMA |
```
- Lower duration = faster
- Token counts indicate efficiency

#### Accuracy Section
```markdown
#### section_3_underwriting_information.ratios.total_debt_ratio
✅ **Match:** True

- **Claude:** 46.65
- **Llama:** 46.65
```
- ✅ = Both models agree (good!)
- ❌ = Models disagree (investigate!)

#### Differences Section
```json
{
  "path": "section_3.other_obligations.all_other_monthly_payments",
  "type": "value_mismatch",
  "claude": 1046.00,
  "llama": 0.00
}
```
- Review the original PDF to determine which is correct
- Table alignment issues often cause these mismatches

### Common Patterns to Watch

1. **Swapped Values**: 
   - Claude: $4,034 for "All Other"
   - Llama: $0 for "All Other"
   - Reality: $0 is likely correct (alignment issue)

2. **Missing Decimals**:
   - Claude: 6.875
   - Llama: 6.88
   - Precision loss in Llama

3. **Type Mismatches**:
   - Claude: "123456.78" (string)
   - Llama: 123456.78 (number)
   - Formatting difference

## Troubleshooting

### API Errors

**Error:** `Bedrock API error: ...`
- Check AWS credentials: `BEDROCK_API_KEY` in `bedrock_config.py`
- Verify model access in AWS Bedrock console
- Check region configuration (us-east-1 for Llama)

**Error:** `Model not found`
- Verify model ID: `global.meta.llama4-maverick-17b-instruct-v1:0`
- Check if model is available in your AWS account
- May need to request model access in Bedrock console

### Extraction Failures

**Error:** `Failed to parse JSON`
- Model returned invalid JSON
- Check raw response in output file
- May need to adjust prompt

**Error:** `Timeout`
- Increase timeout in request (currently 600s)
- Large documents may take longer
- Consider processing fewer pages

### Comparison Issues

**High difference count (>100)**
- Likely structural mismatch
- Review both outputs manually
- May need to standardize output format

**All critical fields mismatch**
- Major extraction failure by one model
- Review individual outputs
- Check prompt clarity

## Next Steps

1. **Run Initial Test** (Loan 30):
   ```bash
   ./run_loan30_comparison.sh
   ```

2. **Review Results**:
   - Check `outputs/model_comparison/loan_1579510/report_*.md`
   - Focus on critical field matches
   - Identify common error patterns

3. **Expand Testing**:
   ```bash
   python3 batch_compare_1008.py --max-forms 10
   ```

4. **Analyze Patterns**:
   - Which model handles table alignment better?
   - Which model is more accurate on critical fields?
   - Performance vs accuracy tradeoffs?

5. **Make Decision**:
   - Based on accuracy, speed, and cost
   - Consider hybrid approach (use both for validation)
   - Document findings and recommendation

## Cost Considerations

### Token Usage
- Claude Opus 4.5: Higher cost per token, more accurate
- Llama Maverick 17B: Lower cost per token, may need validation

### Processing Speed
- Factor in time savings vs cost savings
- Batch processing efficiency
- Re-processing failed extractions

### Accuracy Impact
- Cost of errors in production
- Manual review/correction time
- Downstream processing failures

## Support

For issues or questions:
1. Check this README
2. Review output logs and error messages
3. Examine individual extraction JSONs
4. Compare against original PDF manually

## Files

```
backend/
├── compare_opus_vs_llama.py      # Single comparison script
├── batch_compare_1008.py         # Batch comparison script
├── run_loan30_comparison.sh      # Quick runner for Loan 30
├── MODEL_COMPARISON_README.md    # This file
├── bedrock_config.py             # AWS Bedrock configuration
└── vlm_utils.py                  # VLM utilities

outputs/model_comparison/
├── loan_1579510/
│   ├── claude_opus_4.5_*.json
│   ├── llama_maverick_17b_*.json
│   ├── comparison_*.json
│   └── report_*.md
├── batch_summary_*.json
└── batch_summary_*.md
```

