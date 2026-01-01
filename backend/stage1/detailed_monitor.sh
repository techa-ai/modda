#!/bin/bash
# Detailed monitoring of extraction progress

echo "=========================================="
echo "🔍 DETAILED EXTRACTION MONITOR"
echo "=========================================="
echo ""

# Check if processes are running
echo "🏃 Running Processes:"
if ps aux | grep "1_2_1_deep_extract_llama.py" | grep -v grep > /dev/null; then
    echo "   ✅ 1_2_1 (Scanned PDFs) - RUNNING"
else
    echo "   ⏹️  1_2_1 (Scanned PDFs) - COMPLETED or NOT STARTED"
fi

if ps aux | grep "concurrent_extractor.py" | grep -v grep > /dev/null; then
    echo "   ✅ Concurrent Extractor - RUNNING"
    PID=$(ps aux | grep "concurrent_extractor.py" | grep -v grep | awk '{print $2}')
    echo "      PID: $PID"
else
    echo "   ⏹️  Concurrent Extractor - COMPLETED or NOT STARTED"
fi

echo ""
echo "📈 Live Processing (Last 10 actions):"
echo "---"
grep -E "🔄 Processing:|✓ Extraction complete" logs_concurrent.txt 2>/dev/null | tail -10 | sed 's/^/   /'
echo ""

echo "📊 Tax Returns Progress (2271 pages):"
if grep -q "tax_returns_65.pdf" logs_concurrent.txt 2>/dev/null; then
    CURRENT_PAGE=$(grep "🔄 Extracting page" logs_concurrent.txt | grep -oE "[0-9]+/2271" | tail -1)
    if [ ! -z "$CURRENT_PAGE" ]; then
        echo "   📄 Current: Page $CURRENT_PAGE"
        PAGE_NUM=$(echo $CURRENT_PAGE | cut -d'/' -f1)
        PERCENT=$(echo "scale=1; $PAGE_NUM * 100 / 2271" | bc)
        echo "   📊 Progress: $PERCENT%"
    else
        echo "   ⏳ Starting..."
    fi
else
    echo "   ⏳ Not started yet"
fi

echo ""
echo "📂 Files Completed:"
echo "   1_2_1: $(ls output/loan_1642451/1_2_1_llama_extractions/*.json 2>/dev/null | grep -v summary | wc -l | xargs)/24"
echo "   1_2_3: $(ls output/loan_1642451/1_2_3_llama_extractions/*.json 2>/dev/null | grep -v summary | wc -l | xargs)/25"
echo "   1_2_4: $(ls output/loan_1642451/1_2_4_llama_extractions/*.json 2>/dev/null | grep -v summary | wc -l | xargs)/24"
echo "   1_2_5: $(ls output/loan_1642451/1_2_5_llama_extractions/*.json 2>/dev/null | grep -v summary | wc -l | xargs)/1"

echo ""
echo "📝 Log Sizes:"
echo "   1_2_1: $(wc -l < logs_1_2_1_final.txt 2>/dev/null || echo 0) lines"
echo "   Concurrent: $(wc -l < logs_concurrent.txt 2>/dev/null || echo 0) lines"

echo ""
echo "=========================================="



