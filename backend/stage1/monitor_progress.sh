#!/bin/bash
# Monitor extraction progress across all concurrent processes

LOAN_ID="loan_1642451"
OUTPUT_DIR="output/$LOAN_ID"

echo "=========================================="
echo "📊 EXTRACTION PROGRESS MONITOR"
echo "=========================================="
echo ""

echo "1️⃣  1_2_1 (Scanned PDFs - 24 files):"
if [ -d "$OUTPUT_DIR/1_2_1_llama_extractions" ]; then
    COUNT=$(ls -1 "$OUTPUT_DIR/1_2_1_llama_extractions"/*.json 2>/dev/null | grep -v summary | wc -l | xargs)
    echo "   ✅ Completed: $COUNT/24"
else
    echo "   ⏳ Not started yet"
fi

echo ""
echo "2️⃣  1_2_3 (Text with Tables - 25 files):"
if [ -d "$OUTPUT_DIR/1_2_3_llama_extractions" ]; then
    COUNT=$(ls -1 "$OUTPUT_DIR/1_2_3_llama_extractions"/*.json 2>/dev/null | grep -v summary | wc -l | xargs)
    echo "   ✅ Completed: $COUNT/25"
else
    echo "   ⏳ Not started yet"
fi

echo ""
echo "3️⃣  1_2_4 (Text without Tables - 24 files):"
if [ -d "$OUTPUT_DIR/1_2_4_llama_extractions" ]; then
    COUNT=$(ls -1 "$OUTPUT_DIR/1_2_4_llama_extractions"/*.json 2>/dev/null | grep -v summary | wc -l | xargs)
    echo "   ✅ Completed: $COUNT/24"
else
    echo "   ⏳ Not started yet"
fi

echo ""
echo "4️⃣  1_2_5 (Large Files 80+ pages - 1 file):"
if [ -d "$OUTPUT_DIR/1_2_5_llama_extractions" ]; then
    COUNT=$(ls -1 "$OUTPUT_DIR/1_2_5_llama_extractions"/*.json 2>/dev/null | grep -v summary | wc -l | xargs)
    echo "   ✅ Completed: $COUNT/1"
else
    echo "   ⏳ Not started yet"
fi

echo ""
echo "=========================================="
echo "📝 Recent Activity:"
echo "=========================================="
echo ""
echo "1_2_1 Latest:"
tail -5 logs_1_2_1_final.txt 2>/dev/null | grep -E "(Processing|complete)" || echo "  No recent activity"

echo ""
echo "Concurrent Latest:"
tail -5 logs_concurrent.txt 2>/dev/null | grep -E "(Processing|complete|Completed group)" || echo "  No recent activity"

echo ""
echo "=========================================="



