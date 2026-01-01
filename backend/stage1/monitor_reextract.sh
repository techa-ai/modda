#!/bin/bash
# Monitor concurrent re-extraction progress

LOG_FILE="logs_concurrent_reextract.txt"

echo "📊 Concurrent Re-Extraction Monitor"
echo "===================================="
echo ""

# Check if process is running
if ps aux | grep -q "[c]oncurrent_reextract.py"; then
    echo "✅ Process is running"
else
    echo "⚠️  Process not found"
fi

echo ""
echo "📈 Progress:"
echo "------------"

# Count completions by category
echo "1_2_1 (Scanned):        $(grep -c '\[1_2_1_scanned\].*✅' $LOG_FILE) completed"
echo "1_2_3 (Text+Tables):    $(grep -c '\[1_2_3_text_tables\].*✅' $LOG_FILE) completed"
echo "1_2_4 (Text no tables): $(grep -c '\[1_2_4_text_no_tables\].*✅' $LOG_FILE) completed"
echo ""
echo "Total completed: $(grep -c '✅ \[' $LOG_FILE)"
echo "Total failed:    $(grep -c '❌ \[' $LOG_FILE)"

echo ""
echo "📂 Output files created:"
echo "------------------------"
echo "1_2_1: $(ls output/loan_1642451/1_2_1_llama_extractions/*.json 2>/dev/null | wc -l | xargs) files"
echo "1_2_3: $(ls output/loan_1642451/1_2_3_llama_extractions/*.json 2>/dev/null | wc -l | xargs) files"
echo "1_2_4: $(ls output/loan_1642451/1_2_4_llama_extractions/*.json 2>/dev/null | wc -l | xargs) files"

echo ""
echo "🔍 Recent activity (last 10 lines):"
echo "------------------------------------"
tail -10 $LOG_FILE

echo ""
echo "To see live updates: tail -f $LOG_FILE"



