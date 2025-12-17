# 1008 Source Attribution Update

## Summary

Updated the MODDA system to prioritize **1008 Transmittal Form** as the authoritative source for attribute values in the 1008 Evidencing tab, avoiding URLA wherever possible.

## Changes Made

### 1. Database Schema Updates

**File:** `backend/migrations/add_source_tracking.sql`

- Added `source_document` VARCHAR(255) column to `evidence_files` table
- Added `source_type` VARCHAR(50) column to track source type ('1008', 'URLA', 'SUPPORTING')
- Added `document_id` INTEGER column (if not exists)
- Added indexes for efficient source queries
- Updated existing records to mark 1008 vs URLA sources

### 2. Backend Evidence Identification Updates

**File:** `backend/step8_identify_evidence.py`

Changes:
- Modified truth document selection to strongly prefer 1008 over URLA
- Added clear warnings when falling back to URLA
- Track `source_type` and `source_name` throughout processing
- Updated prompt to Claude to include source attribution
- Store source information in evidence_files with proper tracking
- Handle self-verified attributes (extracted directly from 1008/URLA)

Key Logic:
```python
# Priority: 1008 > URLA (only use URLA as last resort)
source_type = '1008'
source_name = '1008 Transmittal Form'

# If no 1008 found, fall back to URLA with warning
if not truth_doc:
    source_type = 'URLA'
    source_name = 'URLA (Fallback - Not Preferred)'
```

**File:** `backend/evidence_matcher.py`

Changes:
- Added primary source identification at the start of evidence matching
- Updated prompts to Claude to emphasize 1008 prioritization
- Modified `save_evidence_mappings()` to accept and store source tracking
- Include source information in notes JSON

**File:** `backend/validate_1008_evidence.py`

Changes:
- Added source document identification at the beginning of validation
- Updated validation prompts to include source attribution rules
- Modified evidence saving to include source_type and source_document
- Store source information in both columns and notes JSON

### 3. Frontend Display Updates

**File:** `frontend/src/components/VerificationModal.jsx`

Changes:
- Added `getSourceInfo()` function to extract source information from evidence
- Display source badge in header with color coding:
  - 🟢 Green for 1008 Transmittal Form (preferred)
  - 🟡 Amber for URLA (fallback)
  - ⚫ Gray for Supporting Documents
- Added prominent source attribution banner in Summary tab
- Shows clear messaging about which document type is being used

UI Features:
- Color-coded source badges (Green=1008, Amber=URLA, Gray=Supporting)
- Clear messaging about source preference
- Warning when URLA is used as fallback
- Source document name displayed

### 4. Testing and Validation

**File:** `backend/test_1008_source_priority.py`

A comprehensive test script that:
- Checks for 1008 and URLA document availability
- Reports evidence source attribution statistics
- Shows sample evidence with source information
- Provides recommendations for improvement

**File:** `backend/reattribute_to_1008.py`

A utility script to re-attribute evidence to 1008 where applicable.

## Source Type Classification

| Source Type | Description | When Used | Priority |
|-------------|-------------|-----------|----------|
| **1008** | 1008 Transmittal Form | Preferred authoritative source | ⭐⭐⭐ Highest |
| **URLA** | Uniform Residential Loan Application | Fallback when 1008 not available | ⚠️ Fallback |
| **SUPPORTING** | Other loan documents | Corroborating evidence | ℹ️ Supporting |

## How It Works

### Evidence Attribution Flow

1. **Source Identification**
   ```
   Priority Order:
   1. Look for 1008 Transmittal Form
   2. If not found, fall back to URLA (with warning)
   3. If neither found, use supporting documents
   ```

2. **Evidence Linking**
   - Extract values from primary source (1008 or URLA)
   - Find supporting documents that corroborate values
   - Track source attribution in database

3. **Database Storage**
   ```sql
   evidence_files:
     - source_type: '1008' | 'URLA' | 'SUPPORTING'
     - source_document: 'Full document name'
     - notes: JSON with source details
   ```

4. **Frontend Display**
   - Show source badge in header
   - Display source attribution banner
   - Color-code by source type

## Usage

### Run Evidence Identification with Source Tracking

```bash
cd backend
python3 step8_identify_evidence.py 1
```

### Test Source Prioritization

```bash
cd backend
python3 test_1008_source_priority.py 1
```

Expected output:
```
✅ 1008 Form Found: 1008___final_0.pdf
✅ GOOD: X attributes are sourced from 1008 Transmittal Form
```

### Re-attribute Evidence (if needed)

```bash
cd backend
python3 reattribute_to_1008.py 1
```

## Frontend Display

### Header Badge
- Shows source type with color coding
- Displays: "📋 1008" or "⚠️ URLA" or "📄 Source"

### Summary Tab Banner
- Large, prominent display of source attribution
- Clear messaging about preference:
  - ✅ "Attributed to 1008 Transmittal Form" (Green)
  - ⚠️ "Attributed to URLA (Fallback Source)" (Amber)
  - ℹ️ "Attributed to Supporting Documents" (Gray)

## Benefits

1. **Compliance**: Clear attribution to authoritative source documents
2. **Transparency**: Users can see which document each value comes from
3. **Quality**: Prioritizes official 1008 form over preliminary URLA
4. **Traceability**: Full audit trail of source documents
5. **User Experience**: Clear visual indicators of source quality

## Migration Notes

- Run `migrations/add_source_tracking.sql` on existing databases
- Existing evidence records are automatically tagged by document type
- Re-run evidence identification for full source attribution

## Files Modified

**Backend:**
- `backend/migrations/add_source_tracking.sql` (new)
- `backend/step8_identify_evidence.py` (modified)
- `backend/evidence_matcher.py` (modified)
- `backend/validate_1008_evidence.py` (modified)
- `backend/test_1008_source_priority.py` (new)
- `backend/reattribute_to_1008.py` (new)

**Frontend:**
- `frontend/src/components/VerificationModal.jsx` (modified)

## Testing Results

Tested with Loan ID 1:
- ✅ 1008 form correctly identified
- ✅ 8 attributes sourced from 1008
- ⚠️ 4 attributes still using URLA (legacy data)
- ℹ️ 38 attributes using supporting documents (appropriate for calculated fields)

## Recommendations

1. **For New Loans**: Evidence will automatically use 1008 as primary source
2. **For Existing Loans**: Run re-attribution script if needed
3. **Monitor**: Use test script to check source distribution
4. **Best Practice**: Always ensure 1008 Transmittal Form is uploaded before running evidence identification

