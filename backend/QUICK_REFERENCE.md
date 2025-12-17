# Quick Reference Guide

## One-Page Cheat Sheet for Model Comparison

### 🎯 Goal
Compare Claude Opus 4.5 vs Llama models for extracting 1008 forms with table alignment issues.

---

## 🚀 Quick Start (3 Commands)

```bash
cd /Users/sunny/Applications/bts/jpmorgan/mortgage/modda/backend

# 1. Check setup
python3 test_model_setup.py

# 2. Enable Llama in AWS Console (if needed)
open "https://console.aws.amazon.com/bedrock/home#/modelaccess"

# 3. Run comparison
./run_loan30_comparison.sh
```

---

## 📁 Files You'll Use

### Run Comparisons
```bash
./run_loan30_comparison.sh              # Single loan (Loan 30)
python3 compare_opus_vs_llama.py <pdf>  # Custom PDF
python3 batch_compare_1008.py           # All loans
```

### Check Status
```bash
python3 test_model_setup.py          # Validate API access
python3 list_available_models.py     # List Llama models
```

### Read Documentation
```bash
cat COMPARISON_SUMMARY.md            # Overview (start here)
cat SETUP_INSTRUCTIONS.md            # Detailed setup
cat MODEL_COMPARISON_README.md       # Full usage guide
```

---

## ⚙️ Configuration

### Change Llama Model

Edit `compare_opus_vs_llama.py` line 28:

```python
# Current (Llama 3.2 90B Vision)
LLAMA_MODEL_ID = "us.meta.llama3-2-90b-instruct-v1:0"

# Alternatives:
# LLAMA_MODEL_ID = "us.meta.llama3-2-11b-instruct-v1:0"  # Faster
# LLAMA_MODEL_ID = "meta.llama3-3-70b-instruct-v1:0"     # No vision
```

---

## 📊 Output Location

```
outputs/model_comparison/
├── loan_1579510/                    # Loan 30 results
│   ├── report_*.md                  # Human-readable
│   ├── comparison_*.json            # Full comparison
│   ├── claude_opus_4.5_*.json       # Claude output
│   └── llama_*_*.json               # Llama output
└── batch_summary_*.md               # Aggregate stats
```

---

## 🔍 What to Check in Reports

### 1. Performance (Speed)
```markdown
| Metric | Claude | Llama | Winner |
| Duration | 45s | 38s | LLAMA |
```

### 2. Accuracy (Critical Fields)
```markdown
✅ total_income: Match ($21,759.79)
❌ all_other_monthly_payments: Claude=$0, Llama=$1,046
```

### 3. Key Differences
- Focus on "Other Obligations" section
- Check table alignments
- Verify math (totals = sum of parts)

---

## 🐛 Troubleshooting

### Problem: "Invalid model identifier"
**Solution:** Enable Llama access in AWS Bedrock Console
```
https://console.aws.amazon.com/bedrock/home#/modelaccess
```

### Problem: "No such file"
**Solution:** Check PDF path
```bash
ls ../public/loans/loan_1579510/1008*.pdf
```

### Problem: "Failed to parse JSON"
**Solution:** Check raw response in output file, model may have returned invalid JSON

### Problem: "Timeout"
**Solution:** Increase timeout or try smaller document

---

## 💰 Cost Estimate

| Action | Claude Cost | Llama Cost | Time |
|--------|------------|-----------|------|
| Single 1008 | $0.15 | $0.01 | 1 min |
| 10 loans | $1.50 | $0.10 | 5 min |
| 100 loans | $15.00 | $1.00 | 50 min |

**Potential savings with Llama: 90-95%**

---

## 📈 Decision Matrix

### Use Claude If:
- ✅ Llama accuracy < 90%
- ✅ Table alignment errors
- ✅ Cost is not a concern
- ✅ Need highest quality

### Use Llama If:
- ✅ Accuracy ≥ 90%
- ✅ Table alignment good
- ✅ Processing large volumes
- ✅ Cost is important

### Use Hybrid If:
- ✅ Mixed results
- ✅ Different error patterns
- ✅ Want best of both

---

## 🔄 Workflow

```
1. Enable Llama → 2. Test Setup → 3. Run Loan 30 → 4. Review Report
                                        ↓
                              Good results? 
                                   / \
                                YES   NO
                                 ↓     ↓
                        5a. Batch test  5b. Debug/adjust
                                 ↓
                        6. Make decision
                                 ↓
                        7. Update production
```

---

## 🎓 Key Files to Edit

### Change model:
`compare_opus_vs_llama.py` (line 28)

### Change prompt:
`compare_opus_vs_llama.py` (function `create_1008_extraction_prompt`)

### Change output:
`compare_opus_vs_llama.py` (function `generate_comparison_report`)

---

## 📞 Help

1. **Setup issues?** → `SETUP_INSTRUCTIONS.md`
2. **Usage questions?** → `MODEL_COMPARISON_README.md`
3. **Model options?** → `LLAMA_MODEL_SETUP.md`
4. **Overview?** → `COMPARISON_SUMMARY.md`
5. **This cheat sheet!** → `QUICK_REFERENCE.md`

---

## ✅ Success Checklist

- [ ] Llama model enabled in AWS
- [ ] `test_model_setup.py` passes all tests
- [ ] Ran comparison on Loan 30
- [ ] Reviewed report
- [ ] Understood differences
- [ ] Made model selection decision

**All checked?** → You're ready for production! 🚀

