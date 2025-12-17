#!/bin/bash
# Quick runner for Loan 30 (loan_1579510) comparison

echo "========================================"
echo "Running Comparison for Loan 30"
echo "Claude Opus 4.5 vs Llama Maverick 17B"
echo "========================================"
echo ""

cd "$(dirname "$0")"

LOAN_ID="loan_1579510"
PDF_PATH="../public/loans/${LOAN_ID}/1008___final_0.pdf"
OUTPUT_DIR="../outputs/model_comparison/${LOAN_ID}"

# Check if PDF exists
if [ ! -f "$PDF_PATH" ]; then
    echo "❌ Error: 1008 form not found at $PDF_PATH"
    exit 1
fi

echo "📄 Document: $PDF_PATH"
echo "📁 Output: $OUTPUT_DIR"
echo ""

# Run comparison
python3 compare_opus_vs_llama.py "$PDF_PATH" --output-dir "$OUTPUT_DIR"

echo ""
echo "========================================"
echo "✅ Comparison Complete!"
echo "========================================"
echo ""
echo "📊 View results in: $OUTPUT_DIR"
echo ""

