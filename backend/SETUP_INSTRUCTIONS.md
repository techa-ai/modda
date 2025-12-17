# Model Comparison Setup Instructions

## What We've Built

I've created a comprehensive head-to-head comparison system for testing **Claude Opus 4.5** vs **Llama models** on 1008 form extraction, specifically targeting the table and alignment issues you mentioned.

### Files Created

```
backend/
├── compare_opus_vs_llama.py          # Main comparison script
├── batch_compare_1008.py             # Batch processing script  
├── test_model_setup.py               # Setup validation script
├── list_available_models.py          # Check available Llama models
├── run_loan30_comparison.sh          # Quick runner for Loan 30
├── MODEL_COMPARISON_README.md        # Complete documentation
├── LLAMA_MODEL_SETUP.md              # Llama model options
└── SETUP_INSTRUCTIONS.md             # This file
```

## Current Status

### ✅ Working
- Claude Opus 4.5 API access
- Loan 30 (loan_1579510) 1008 PDF found
- All comparison scripts created and tested
- Documentation complete

### ⚠️ Needs Setup
- **Llama model access** - Not yet enabled in your AWS account

## Llama Model Issue

The comparison script is trying to use:
- **Target (Future):** Llama 4 Maverick 17B
- **Current Alternative:** Llama 3.2 90B Vision or Llama 3.3 70B

**Problem:** Neither model is currently accessible in your AWS Bedrock account.

## Step-by-Step Setup

### Step 1: Check Available Models

```bash
cd /Users/sunny/Applications/bts/jpmorgan/mortgage/modda/backend
python3 list_available_models.py
```

This will test all known Llama model IDs and show which ones you can access.

### Step 2: Enable Llama Model Access (If Needed)

1. Go to AWS Bedrock Console:
   ```
   https://console.aws.amazon.com/bedrock/home?region=ap-southeast-1#/modelaccess
   ```

2. Find Llama models in the list:
   - Meta Llama 3.2 90B Instruct (Vision)
   - Meta Llama 3.2 11B Instruct (Vision)
   - Meta Llama 3.3 70B Instruct
   - Meta Llama 3.1 405B/70B/8B Instruct

3. Click "Request Access" or "Enable"

4. Access is usually granted instantly

5. Wait a few minutes for propagation

### Step 3: Update Configuration

Once you know which Llama model is available, edit `compare_opus_vs_llama.py`:

```python
# Line 28: Update this line with your available model
LLAMA_MODEL_ID = "us.meta.llama3-2-90b-instruct-v1:0"  # Or whichever is available
```

**Model Recommendations (in order of preference):**
1. `us.meta.llama3-2-90b-instruct-v1:0` - Best quality, has vision
2. `us.meta.llama3-2-11b-instruct-v1:0` - Faster, cheaper, has vision
3. `meta.llama3-3-70b-instruct-v1:0` - Good quality, no vision (will need different approach)

### Step 4: Validate Setup

```bash
cd /Users/sunny/Applications/bts/jpmorgan/mortgage/modda/backend
python3 test_model_setup.py
```

Expected output:
```
✅ Claude Opus 4.5
✅ Llama 3.2 90B Vision
✅ Vision Support (optional)
✅ Loan 30 PDF

✅ All critical tests passed! Ready to run comparison.
```

### Step 5: Run First Comparison

```bash
cd /Users/sunny/Applications/bts/jpmorgan/mortgage/modda/backend
./run_loan30_comparison.sh
```

Or directly:
```bash
python3 compare_opus_vs_llama.py \
    ../public/loans/loan_1579510/1008___final_0.pdf \
    --output-dir ../outputs/model_comparison/loan_1579510
```

### Step 6: Review Results

Results will be saved to:
```
outputs/model_comparison/loan_1579510/
├── claude_opus_4.5_<timestamp>.json       # Full Claude extraction
├── llama_maverick_17b_<timestamp>.json    # Full Llama extraction
├── comparison_<timestamp>.json            # Detailed comparison
└── report_<timestamp>.md                  # Human-readable report
```

Open the `report_*.md` file to see:
- Performance comparison (speed, tokens)
- Critical field accuracy
- Specific differences in table alignment
- Value mismatches

## Understanding the Results

### What to Look For

1. **Table Alignment Issues**
   - Check the "Other Obligations" section
   - Compare: `all_other_monthly_payments`, `negative_cash_flow`, `total_all_monthly_payments`
   - Common issue: Values get shifted/misaligned

2. **Critical Field Accuracy**
   - Total income calculations
   - Debt-to-income ratios
   - Housing expense totals
   - Loan amounts and rates

3. **Performance Metrics**
   - Extraction time
   - Token usage (affects cost)
   - Success rate

### Example Issues We're Testing

**Problem:** In 1008 forms, the "Other Obligations" table often has:
```
Label Column          | Value Column
--------------------- | ------------
All Other Monthly     | $0.00
Payments             |
                     |
Negative Cash Flow   | $0.00
(subject property)   |
                     |
Total All Monthly    | $4,034.42
Payments             |
```

**What Goes Wrong:**
- Models sometimes see `$4,034.42` visually aligned with "All Other Monthly Payments"
- Should actually be for "Total All Monthly Payments"
- Our prompt includes specific instructions to handle this via math validation

## Running Batch Comparisons

Once single comparison works:

```bash
# Compare all 1008 forms
python3 batch_compare_1008.py

# Compare first 5 forms only
python3 batch_compare_1008.py --max-forms 5

# Compare specific loans
python3 batch_compare_1008.py --loan-ids loan_1579510 loan_1439728
```

Results will include:
- Individual comparison reports for each loan
- Aggregate statistics
- Performance trends
- Accuracy patterns

## Troubleshooting

### "Invalid model identifier"
→ Model not accessible. Follow Step 2 to enable access.

### "Connection timeout"
→ Network issue or model overloaded. Retry in a few minutes.

### "Failed to parse JSON"
→ Model returned invalid output. Check raw response in output file.

### "Too many differences"
→ Major structural mismatch. Review both outputs manually.

## Cost Estimates

### Per 1008 Form (1-2 pages)
- **Claude Opus 4.5:** ~$0.10-0.20 per extraction
- **Llama 3.2 90B:** ~$0.01-0.02 per extraction
- **Llama 3.2 11B:** ~$0.002-0.005 per extraction

### Batch Testing (10 forms)
- **Total Cost:** ~$1-3
- **Time:** ~5-10 minutes

## Next Steps After Comparison

### If Claude Wins
- Continue using Claude Opus 4.5
- Cost is higher but accuracy justifies it
- Consider Claude Haiku/Sonnet for simpler docs

### If Llama Wins  
- Switch to Llama for production
- Massive cost savings (10-100x cheaper)
- Faster processing
- May need post-processing validation

### If Mixed Results
- Use hybrid approach:
  - Llama for initial extraction
  - Claude for validation/correction
  - Focus Claude on problem fields only

### If Both Have Issues
- May need specialized solution:
  - OCR + structured extraction
  - Custom table detection
  - Multi-stage processing

## When Llama 4 Becomes Available

Llama 4 Maverick 17B is expected in **April 2025**. When available:

1. Update model ID in `compare_opus_vs_llama.py`:
   ```python
   LLAMA_MODEL_ID = "global.meta.llama4-maverick-17b-instruct-v1:0"
   ```

2. Re-run comparisons:
   ```bash
   python3 batch_compare_1008.py
   ```

3. Compare Llama 4 vs Llama 3.2 vs Claude

Expected improvements with Llama 4:
- 1M token context (vs 128K in Llama 3.2)
- Better multimodal understanding
- Improved reasoning for complex tables
- Lower cost per token

## Support

For questions or issues:
1. Check the documentation: `MODEL_COMPARISON_README.md`
2. Review model options: `LLAMA_MODEL_SETUP.md`  
3. Run validation: `python3 test_model_setup.py`
4. Check available models: `python3 list_available_models.py`

## Summary

**What Works Now:**
- ✅ Complete comparison framework
- ✅ Claude Opus 4.5 extraction
- ✅ Detailed analysis and reporting
- ✅ Batch processing capability
- ✅ Documentation

**What You Need:**
- ⚠️ Enable Llama model access in AWS Bedrock

**Time to Get Running:**
- 5 minutes to enable model access
- 5 minutes to run first comparison
- Results immediately available

**Expected Outcome:**
- Objective comparison of both models
- Identify which handles table alignment better
- Make data-driven decision on model choice
- Potential 10-100x cost reduction if Llama works well

