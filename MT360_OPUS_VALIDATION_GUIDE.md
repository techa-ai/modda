# MT360 OCR Validation with Claude Opus

## Overview
Implemented a comprehensive MT360 OCR validation system that uses Claude Opus to compare MT360's extracted data against actual PDF documents and deep JSON data from our database.

## How It Works

### 1. **Data Sources**
For each document (1008, URLA, Note, etc.), the system compares:
- **MT360 Extracted Data**: OCR data from mt360.com (JSON files)
- **Actual PDF**: Original document images
- **Deep JSON**: Our database's extracted data

### 2. **Claude Opus Analysis**
Claude Opus 4 receives:
- MT360 JSON extract
- Deep JSON from database  
- PDF images (first 3 pages, 150 DPI)
- Structured prompt asking for field-by-field comparison

### 3. **Validation Output**
For each field, Opus returns:
```json
{
  "mt360_field_name": "Property Type",
  "mt360_value": "1 unit",
  "actual_field_name": "Property Type",
  "actual_value": "1 unit",
  "status": "MATCH",
  "confidence": "HIGH",
  "notes": "Perfect match"
}
```

## User Interface

### **Document View with Validation Button**
- Each document tab (1008, URLA, Note, etc.) has a "Validate with Opus" button
- Click to trigger Claude Opus analysis
- Shows loading state during validation

### **Validation Results Display**
Once validation completes:
1. **Summary Card** showing:
   - Total Fields
   - Matches (green)
   - Mismatches (red)
   - Accuracy % (purple)

2. **Detailed Results Table**:
   - Status column with ✓ (green) or ✗ (red) icons
   - Field Name
   - MT360 Value
   - Actual Value (from PDF/Deep JSON)
   - Notes (explanation of mismatch)
   - Mismatched rows highlighted in red

### **Table Design**
- Compact layout (10px headers, 11px content)
- Color-coded status indicators
- Red background for mismatch rows
- Sortable and scannable

## API Endpoints

### `GET /api/admin/loans/<loan_id>/mt360-ocr`
Returns all MT360 extracted data for a loan (6 document types)

### `POST /api/admin/loans/<loan_id>/validate-mt360/<doc_type>`
Validates a specific document type using Claude Opus
- **Parameters**: `loan_id`, `doc_type` (1008, URLA, Note, etc.)
- **Returns**: Validation results with matches/mismatches

## Backend Implementation

### **File**: `backend/mt360_validator.py`
Main validation logic:
1. Loads MT360 JSON
2. Queries deep JSON from database
3. Converts PDF to images (first 3 pages)
4. Sends to Claude Opus with structured prompt
5. Parses JSON response
6. Returns validation results

### **Key Features**:
- Handles multiple page PDFs
- Graceful error handling
- Structured JSON output parsing
- Confidence scoring
- Match/mismatch categorization

## Usage Instructions

### **For Loan ID 27 (1008 form)**:
1. Navigate to: http://localhost:3006
2. Go to Admin → Loans → Loan #27
3. Click "MT360 OCR Validation" tab
4. Click "1008 Form" in the left sidebar
5. Click "Validate with Opus" button
6. Wait ~30-60 seconds for Opus analysis
7. Review validation results

### **Expected Results**:
- Match/mismatch for each field
- Actual values from PDF when mismatched
- Overall accuracy percentage
- Explanatory notes for discrepancies

## Data Flow

```
┌─────────────┐
│  User Clicks│
│  "Validate" │
└──────┬──────┘
       │
       v
┌─────────────────────────────────────────┐
│  Frontend (MT360OCRValidation.jsx)     │
│  - Shows loading spinner                │
│  - Calls API endpoint                   │
└──────┬──────────────────────────────────┘
       │
       v
┌─────────────────────────────────────────┐
│  Backend API (app.py)                   │
│  - Get loan details from DB             │
│  - Load MT360 JSON file                 │
│  - Query deep JSON from DB              │
│  - Find PDF file path                   │
└──────┬──────────────────────────────────┘
       │
       v
┌─────────────────────────────────────────┐
│  MT360 Validator (mt360_validator.py)  │
│  - Convert PDF to images                │
│  - Build structured prompt              │
│  - Call Claude Opus API                 │
│  - Parse JSON response                  │
└──────┬──────────────────────────────────┘
       │
       v
┌─────────────────────────────────────────┐
│  Claude Opus 4                          │
│  - Analyzes PDF images                  │
│  - Compares MT360 vs Actual             │
│  - Returns structured JSON              │
└──────┬──────────────────────────────────┘
       │
       v
┌─────────────────────────────────────────┐
│  Frontend Display                       │
│  - Shows validation results             │
│  - Highlights mismatches                │
│  - Displays accuracy stats              │
└─────────────────────────────────────────┘
```

## Technical Stack

- **AI Model**: Claude Opus 4 (claude-opus-4-20250514)
- **PDF Processing**: pdf2image (150 DPI, first 3 pages)
- **Image Format**: PNG, base64 encoded
- **Backend**: Flask, Python
- **Frontend**: React, Axios, Tailwind CSS
- **Database**: PostgreSQL (deep JSON queries)

## Configuration Required

### **Environment Variables**:
```bash
ANTHROPIC_API_KEY=your_anthropic_api_key_here
```

Add to `.env` file in backend directory.

## Document Types Supported

1. ✅ **1008** - Fannie Mae 1008 Form
2. ✅ **URLA** - Uniform Residential Loan Application
3. ✅ **Note** - Promissory Note
4. ✅ **LoanEstimate** - Loan Estimate Disclosure
5. ✅ **ClosingDisclosure** - Closing Disclosure
6. ✅ **CreditReport** - Credit Report

## Example Validation Flow

### **Starting State** (No Validation):
Shows MT360 extracted data in 2-column table

### **User Clicks "Validate with Opus"**:
Button shows: "Validating with Opus..." with spinner

### **After Validation** (30-60 seconds):
```
┌─────────────────────────────────────────────────┐
│  Validation Results                             │
├─────────────────────────────────────────────────┤
│  Total: 40  |  Matches: 38  |  Mismatches: 2   │
│              |  Accuracy: 95%                    │
└─────────────────────────────────────────────────┘

┌──────────┬───────────────┬──────────────┬──────────────┬─────────┐
│ Status   │ Field Name    │ MT360 Value  │ Actual Value │ Notes   │
├──────────┼───────────────┼──────────────┼──────────────┼─────────┤
│ ✓ MATCH  │ Property Type │ 1 unit       │ 1 unit       │ Perfect │
│ ✓ MATCH  │ Loan Type     │ Conventional │ Conventional │ Match   │
│ ✗ MISMATCH│ Note Rate    │ 825.00000%   │ 8.25000%     │ Decimal │
└──────────┴───────────────┴──────────────┴──────────────┴─────────┘
```

## Error Handling

- **PDF Not Found**: Returns 404 with clear error message
- **MT360 Data Missing**: Returns 404 with document type
- **Opus API Error**: Returns 500 with error details
- **JSON Parse Error**: Gracefully handles malformed responses
- **Image Conversion Error**: Falls back to deep JSON only

## Performance Notes

- **Validation Time**: ~30-60 seconds per document
- **Image Processing**: ~2-5 seconds for PDF conversion
- **Opus Analysis**: ~25-55 seconds
- **Max PDF Pages**: First 3 pages only (performance optimization)
- **Image DPI**: 150 (balance between quality and size)

## Next Steps

To validate all documents for Loan #27:
1. Start with 1008 (as requested)
2. Then URLA
3. Then Note
4. Then Loan Estimate
5. Then Closing Disclosure
6. Then Credit Report

Each validation is independent and can be run separately.

## Files Modified/Created

### **Created**:
- `backend/mt360_validator.py` - Core validation logic

### **Modified**:
- `backend/app.py` - Added validation endpoint
- `frontend/src/components/MT360OCRValidation.jsx` - Added validation UI

## Status

✅ **Ready to Use!**

Services running:
- Frontend: http://localhost:3006
- Backend: http://127.0.0.1:8006

Navigate to Loan #27 → MT360 OCR Validation → 1008 Form → Click "Validate with Opus"

