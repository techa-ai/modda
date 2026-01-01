# Enable Llama 4 Maverick Access - Quick Guide

## Status

- ✅ **Claude Opus 4.5** - Working
- ❌ **Llama 4 Maverick 17B** - Not accessible (needs access request)
- ✅ **Comparison scripts** - Ready to run once Llama is enabled

## The Issue

The error `"The provided model identifier is invalid"` means you haven't requested access to Llama 4 Maverick in AWS Bedrock yet.

## How to Fix (5 minutes)

### Step 1: Go to AWS Bedrock Console

**Direct link:**
```
https://console.aws.amazon.com/bedrock/home?region=ap-southeast-1#/modelaccess
```

Or navigate:
1. AWS Console → Bedrock
2. Left sidebar → "Model access"

### Step 2: Find Llama 4 Maverick

In the Model access page, look for:
- **Model name:** Llama 4 Maverick 17B Instruct
- **Provider:** Meta
- **Model ID:** `meta.llama4-maverick-17b-instruct-v1:0`

### Step 3: Request Access

Click the button next to Llama 4 Maverick:
- If it says **"Request access"** → Click it
- If it says **"Manage access"** → It's already enabled!
- If it says **"Access granted"** → You're done!

### Step 4: Wait (Usually Instant)

- Access is typically granted immediately
- Sometimes takes 1-2 minutes
- You'll see status change to "Access granted"

### Step 5: Test Again

```bash
cd /Users/sunny/Applications/bts/jpmorgan/mortgage/modda/backend
python3 test_model_setup.py
```

Expected output:
```
✅ Claude Opus 4.5
✅ Llama 4 Maverick 17B  ← Should be green now!
✅ Loan 30 PDF
```

## Important Notes

### Cross-Region Inference

Llama 4 Maverick uses **cross-region inference profile**:
- Physical model runs in **us-east-1**
- You can call it from **any region** (like your ap-southeast-1)
- Use model ID: `us.meta.llama4-maverick-17b-instruct-v1:0`
- No need to change your AWS region!

### Why It's Different from Claude

- **Claude:** Uses global inference profile (`global.` prefix)
- **Llama:** Uses cross-region inference profile (`us.` prefix)
- Both work from ap-southeast-1!

## Once Enabled, Run Comparison

```bash
# Single loan comparison
./run_loan30_comparison.sh

# Or directly
python3 compare_opus_vs_llama.py \\
    ../public/loans/loan_1579510/1008___final_0.pdf \\
    --output-dir ../outputs/model_comparison/loan_1579510

# Batch comparison (all loans)
python3 batch_compare_1008.py
```

## Troubleshooting

### "Model access request pending"
→ Wait 1-2 minutes and refresh the page

### "Model not available in your account"
→ May need admin approval for your AWS account
→ Contact your AWS administrator

### Still getting "invalid model identifier"
→ Try waiting 5 minutes after access granted
→ Model access needs to propagate

### "Throughput quota exceeded"
→ Too many requests too fast
→ Wait a minute and try again

## Alternative: Use Llama 3.2 While Waiting

If you want to start testing immediately while waiting for Llama 4 approval, edit `compare_opus_vs_llama.py`:

```python
# Change line ~31 from:
LLAMA_MODEL_ID = "us.meta.llama4-maverick-17b-instruct-v1:0"

# To:
LLAMA_MODEL_ID = "us.meta.llama3-2-90b-instruct-v1:0"  # Llama 3.2 90B Vision
```

Then request access to Llama 3.2 models instead.

## Summary

**Current state:**
- Scripts are ready ✅
- Claude works ✅
- Llama 4 Maverick exists ✅
- You don't have access yet ❌

**Action needed:**
1. Go to: https://console.aws.amazon.com/bedrock/home?region=ap-southeast-1#/modelaccess
2. Find "Llama 4 Maverick 17B"
3. Click "Request access"
4. Wait ~1 minute
5. Run `python3 test_model_setup.py`
6. See both models working! ✅

**Time:** 5 minutes total




