# Enhanced Document Metadata Extraction

## Overview
As of this update, our deep JSON extraction now includes comprehensive metadata in the `document_metadata` section. This metadata is critical for:
- Semantic document grouping
- Duplicate detection
- Document versioning analysis
- Content-based matching

## Metadata Structure

### 1. **Core Identification**
- `document_type`: Exact document type/name as shown on document
- `document_status`: signed | unsigned | partially_signed
- `document_version`: preliminary | final | draft | revised | unknown
- `total_pages`: Number of pages in document

### 2. **Visual Fingerprint** 🎨
Captures visual/structural characteristics to identify same template with different data:
- `page_count`: Total pages
- `has_logos`, `has_headers`, `has_footers`: Layout indicators
- `predominant_content_type`: text | tables | forms | mixed
- `layout_pattern`: Overall layout description
- `branding`: Company/organization from headers/logos
- `form_structure`: Grid-based | line-based | section-based
- `signature_blocks_count`: Number of signature areas
- `table_count`: Total tables across all pages
- `estimated_filled_percentage`: 0-100, how much is filled vs blank

### 3. **Perceptual Hashes** 🔍
Programmatically computed image hashes for visual similarity detection:
- `page_hashes`: Array of hashes per page
  - `phash`: Perceptual hash (robust to minor changes)
  - `dhash`: Difference hash (detects structural similarity)
  - `average_hash`: Average hash (fast comparison)
  - `whash`: Wavelet hash (frequency-domain comparison)
- `document_phash_signature`: Combined hash of all pages

**Use Cases:**
- Find visually identical documents at different resolutions
- Detect same form filled differently
- Identify rescanned versions
- Match documents with minor visual differences

### 4. **Dates & Timeline** 📅
- `all_dates`: Array of all dates found
  - `date_type`: effective_date | signature_date | issue_date | etc
  - `date_value`: Date as shown
  - `page_number`: Where found

### 5. **People & Parties** 👥
- `document_persons`: All persons mentioned
  - `person_type`: borrower | co_borrower | lender | notary | witness
  - `name`: Full name
  - `role`: Specific role
  - `signature_present`: true/false
  - `page_number`: Where found

### 6. **Form Identifiers** 🆔
- `form_number`, `form_name`: Official form designations
- `loan_number`, `file_number`, `case_number`: Reference IDs

### 7. **Signature Analysis** ✍️
- `has_any_signature`: Boolean
- `signature_pages`: List of pages with signatures
- `signature_fields`: Detailed per-field analysis

### 8. **Key Identifiers** 🔑
Critical for matching documents:
- `property_address`: Full property address
- `loan_amount`: Loan amount
- `borrower_names`: All borrower names
- `lender_name`: Lending institution
- `property_type`: SFR | Condo | Multi-family

### 9. **Document Completeness** ✅
- `is_complete`: Boolean assessment
- `completion_percentage`: 0-100
- `missing_required_fields`: List of blank required fields
- `blank_signature_fields`: Unsigned signature blocks
- `incomplete_sections`: Sections that appear incomplete

### 10. **Document Scope** 🌍
- `jurisdiction`: State/county for legal docs
- `geographic_location`: City, state
- `applies_to`: What this document governs
- `regulatory_framework`: TILA | RESPA | ECOA references

### 11. **Document Relationships** 🔗
- `references_other_documents`: Referenced documents
- `has_attachments`: Boolean
- `attachment_list`: Listed attachments/exhibits
- `supersedes`: Document this replaces
- `part_of_series`: If part X of N

### 12. **Content Flags** 🏷️
Boolean flags for content type:
- `has_financial_data`, `has_property_details`, `has_legal_language`
- `has_tables`, `has_calculations`
- `is_disclosure`, `is_agreement`, `is_report`, `is_government_form`
- `requires_notarization`

### 13. **Revision Indicators** 📝
- `shows_revision_marks`: Boolean
- `revision_number`, `revision_date`: If present
- `amended_sections`: Marked amendments

### 14. **Content Fingerprint** 🔐
For deduplication and content-based matching:
- `key_data_hash`: Conceptual hash of critical fields
- `structural_pattern`: Document structure description
- `unique_identifiers`: IDs that distinguish this document
- `template_type`: Recognizable template (URLA_1003, etc)
- `distinguishing_features`: Unique characteristics

## Benefits

### For Semantic Grouping
- Accurately identify signed vs unsigned versions
- Detect preliminary vs final versions
- Group chronological versions by dates
- Identify incomplete vs complete documents

### For Duplicate Detection
- **Exact duplicates**: Compare `document_phash_signature`
- **Near duplicates**: Compare individual page `phash` values
- **Content duplicates**: Compare `key_data_hash`
- **Template matches**: Compare `visual_fingerprint` + `template_type`

### For Document Versioning
- Track document evolution through dates
- Identify revision history
- Detect superseded documents
- Map preliminary → final progression

## Implementation Notes

1. **Perceptual hashes** are computed programmatically during PDF→image conversion
2. **LLM extracts** all other metadata fields from document content
3. Hashes are **injected** into the final JSON after LLM extraction
4. All metadata is **mandatory** - LLM must attempt to fill all fields

