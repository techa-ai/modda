#!/usr/bin/env python3
"""
Shared utility module for page-wise Llama 4 Maverick extraction
Used by 1_2_1, 1_2_2, and 1_2_3 scripts
"""

import json
import time
import boto3
import base64
import hashlib
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
from pdf2image import convert_from_path
from PIL import Image
import io
import imagehash

# Llama Model Configuration
LLAMA_MODEL_ID = "us.meta.llama4-maverick-17b-instruct-v1:0"
LLAMA_REGION = "us-east-1"


class LlamaClient:
    """Client for Llama 4 Maverick 17B via AWS Bedrock"""
    
    def __init__(self):
        self.model = LLAMA_MODEL_ID
        self.client = boto3.client('bedrock-runtime', region_name=LLAMA_REGION)
    
    def invoke_model(
        self,
        messages: List[Dict],
        max_tokens: int = 8000,
        temperature: float = 0.0
    ) -> Dict:
        """Invoke Llama 4 Maverick with multimodal messages"""
        prompt_parts = []
        images = []
        
        # Extract text and images from messages
        for msg in messages:
            if isinstance(msg["content"], str):
                prompt_parts.append(msg["content"])
            elif isinstance(msg["content"], list):
                for item in msg["content"]:
                    if item["type"] == "text":
                        prompt_parts.append(item["text"])
                    elif item["type"] == "image":
                        images.append(item["source"]["data"])
        
        # Format prompt with Llama's special tokens
        user_prompt = "\n\n".join(prompt_parts)
        
        if images:
            image_tokens = " ".join(["<|image|>" for _ in images])
            formatted_prompt = f"{image_tokens}\n\n{user_prompt}"
        else:
            formatted_prompt = user_prompt
        
        prompt = f"""<|begin_of_text|><|start_header_id|>user<|end_header_id|>
{formatted_prompt}
<|eot_id|>
<|start_header_id|>assistant<|end_header_id|>"""
        
        body = {
            "prompt": prompt,
            "max_gen_len": max_tokens,
            "temperature": temperature
        }
        
        if images:
            body["images"] = images
        
        try:
            response = self.client.invoke_model(
                modelId=self.model,
                body=json.dumps(body)
            )
            
            result = json.loads(response['body'].read())
            
            if 'generation' in result:
                return {
                    'content': result['generation'],
                    'usage': {
                        'input_tokens': result.get('prompt_token_count', 0),
                        'output_tokens': result.get('generation_token_count', 0)
                    },
                    'model': self.model
                }
            else:
                raise ValueError(f"Unexpected Llama response format: {result}")
                
        except Exception as e:
            raise Exception(f"Bedrock API error for Llama: {e}")


def compute_image_hashes(image: Image.Image) -> Dict[str, str]:
    """Compute perceptual hashes for an image"""
    return {
        'phash': str(imagehash.phash(image)),
        'dhash': str(imagehash.dhash(image)),
        'average_hash': str(imagehash.average_hash(image)),
        'whash': str(imagehash.whash(image))  # Wavelet hash
    }


def convert_pdf_to_base64_images(pdf_path: str, dpi: int = 150) -> tuple[List[str], List[Dict[str, str]]]:
    """Convert PDF pages to base64-encoded images and compute perceptual hashes
    
    Returns:
        tuple: (base64_images, page_hashes)
    """
    
    print(f"  📄 Converting PDF to images (DPI: {dpi})...")
    images = convert_from_path(pdf_path, dpi=dpi)
    
    base64_images = []
    page_hashes = []
    
    for i, img in enumerate(images):
        # Compute perceptual hashes
        hashes = compute_image_hashes(img)
        page_hashes.append(hashes)
        
        # Convert to base64
        img_buffer = io.BytesIO()
        img.save(img_buffer, format="JPEG", quality=85)
        img_b64 = base64.b64encode(img_buffer.getvalue()).decode('utf-8')
        base64_images.append(img_b64)
    
    print(f"  ✓ Converted {len(base64_images)} pages with perceptual hashes")
    return base64_images, page_hashes


def create_pagewise_extraction_prompt(filename: str, page_num: int, total_pages: int) -> str:
    """Create prompt for page-wise extraction matching Claude Opus format"""
    
    return f"""You are analyzing PAGE {page_num} of {total_pages} from mortgage document: {filename}

TASK: Extract ALL information from THIS PAGE ONLY into structured JSON.

CRITICAL: Your response must be VALID JSON for this specific page, matching this exact structure:

{{
  "page_number": {page_num},
  "page_type": "<cover_page|report|form|glossary|text|table_page>",
  "document_type_on_page": "<specific document type shown on this page>",
  "metadata": {{
    "header": "<header text if present>",
    "footer": "<footer text if present>",
    "page_indicator": "<page number shown on page>",
    "logos": ["<logo descriptions>"],
    "company_name": "<company if shown>"
  }},
  "key_data": {{
    // Extract all key labeled data points on this page
    // Include: addresses, names, dates, reference numbers, etc.
  }},
  "financial_data": {{
    // All dollar amounts, percentages, numeric values on this page
    // Group by category (valuations, prices, rates, etc.)
  }},
  "tables": [
    {{
      "table_name": "<descriptive name>",
      "headers": ["col1", "col2", ...],
      "rows": [
        // Extract table data maintaining structure
      ]
    }}
  ],
  "text_content": {{
    // Main text sections, paragraphs, lists on this page
    "sections": [
      {{
        "title": "<section title>",
        "content": "<section text>"
      }}
    ]
  }},
  "charts": [
    {{
      "chart_name": "<chart title>",
      "chart_type": "<bar|line|pie|area>",
      "description": "<what the chart shows>",
      "x_axis": "<x-axis label>",
      "y_axis": "<y-axis label>"
    }}
  ],
  "signatures": {{
    // Any signatures, signature lines, or signature blocks on this page
  }}
}}

EXTRACTION RULES:
1. Extract ONLY data visible on THIS PAGE ({page_num})
2. Be PRECISE with numbers - no rounding or approximation
3. Preserve table structure exactly as shown
4. Include ALL text, even small print
5. Note header/footer information
6. Identify any forms, charts, or special elements
7. Use null for missing fields, not empty strings
8. Financial values should be numeric (no $ or commas in numbers)

Return ONLY valid JSON - no explanatory text before or after."""


def parse_json_from_text(text: str) -> Optional[Dict]:
    """Extract and parse JSON from text response"""
    
    json_start = text.find('{')
    json_end = text.rfind('}')
    
    if json_start != -1 and json_end != -1:
        json_str = text[json_start:json_end+1]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            try:
                cleaned = json_str.strip()
                return json.loads(cleaned)
            except:
                return None
    
    return None


def extract_single_page(image_base64: str, filename: str, page_num: int, total_pages: int, client: LlamaClient) -> Optional[Dict]:
    """Extract JSON from a single page"""
    
    prompt = create_pagewise_extraction_prompt(filename, page_num, total_pages)
    
    content_parts = [
        {"type": "text", "text": prompt},
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": image_base64
            }
        }
    ]
    
    messages = [{"role": "user", "content": content_parts}]
    
    try:
        result = client.invoke_model(
            messages=messages,
            max_tokens=8000,
            temperature=0.0
        )
        
        print(f"     Page {page_num}: Tokens: Input={result['usage']['input_tokens']}, Output={result['usage']['output_tokens']}")
        
        page_data = parse_json_from_text(result['content'])
        
        if page_data:
            page_data['page_number'] = page_num
            
        return page_data
        
    except Exception as e:
        print(f"     ❌ Page {page_num} extraction error: {e}")
        return None


def generate_document_summary(pages: List[Dict], filename: str, client: LlamaClient) -> Optional[Dict]:
    """Generate document-level summary by analyzing all page data together"""
    
    print(f"  📊 Generating document-level summary...")
    
    # Create a consolidated view of all page data
    page_summaries = []
    for page in pages:
        if 'extraction_error' not in page:
            summary = {
                "page": page.get('page_number'),
                "type": page.get('page_type'),
                "key_data": page.get('key_data', {}),
                "financial_data": page.get('financial_data', {}),
                "tables": page.get('tables', [])
            }
            page_summaries.append(summary)
    
    prompt = f"""You are analyzing a complete mortgage document: {filename}

I have extracted {len(pages)} pages individually. Now I need you to create a DOCUMENT-LEVEL SUMMARY that consolidates all the data across pages.

Here is the data from all pages:
{json.dumps(page_summaries, indent=2)[:15000]}  

TASK: Create a comprehensive document_summary that includes:

{{
  "document_summary": {{
    "document_metadata": {{
      "document_type": "<EXACT document type/name as shown on the document>",
      "document_status": "signed|unsigned|partially_signed",
      "document_version": "preliminary|final|draft|revised|unknown",
      "total_pages": {len(pages)},
      "visual_fingerprint": {{
        "page_count": {len(pages)},
        "has_logos": true|false,
        "has_headers": true|false,
        "has_footers": true|false,
        "predominant_content_type": "text|tables|forms|mixed",
        "layout_pattern": "<describe overall layout: form-based|report-style|letter-format|multi-column|etc>",
        "branding": "<company/organization name from headers/logos>",
        "color_scheme": "<if visible: monochrome|color|specific colors>",
        "form_structure": "<if form: grid-based|line-based|section-based|etc>",
        "signature_blocks_count": <number of signature blocks found>,
        "table_count": <number of tables across all pages>,
        "estimated_filled_percentage": <0-100, how much of the document appears filled vs blank>
      }},
      "all_dates": [
        {{
          "date_type": "effective_date|signature_date|issue_date|expiration_date|etc",
          "date_value": "<YYYY-MM-DD or as shown>",
          "page_number": <page where found>
        }}
      ],
      "document_persons": [
        {{
          "person_type": "borrower|co_borrower|lender|notary|witness|etc",
          "name": "<full name>",
          "role": "<specific role>",
          "signature_present": true|false,
          "page_number": <page where found>
        }}
      ],
      "form_identifiers": {{
        "form_number": "<if standard form>",
        "form_name": "<official form name>",
        "loan_number": "<if present>",
        "file_number": "<if present>",
        "case_number": "<if present>",
        "reference_id": "<any other reference ID>"
      }},
      "signature_analysis": {{
        "has_any_signature": true|false,
        "signature_pages": [<list of page numbers with signatures>],
        "signature_fields": [
          {{
            "field_name": "borrower_signature|lender_signature|acknowledgment|etc",
            "is_signed": true|false,
            "date_if_present": "<date>",
            "page_number": <page>
          }}
        ]
      }},
      "key_identifiers": {{
        "property_address": "<full property address if mentioned>",
        "loan_amount": "<loan amount if mentioned>",
        "borrower_names": ["<list of all borrower names>"],
        "lender_name": "<lending institution name>",
        "property_type": "<SFR|Condo|Multi-family|etc if mentioned>"
      }},
      "document_completeness": {{
        "is_complete": true|false,
        "completion_percentage": <0-100>,
        "missing_required_fields": ["<list of required fields that are blank/missing>"],
        "blank_signature_fields": ["<list of signature fields that are unsigned>"],
        "incomplete_sections": ["<list of sections that appear incomplete>"]
      }},
      "document_scope": {{
        "jurisdiction": "<state/county if mentioned for legal docs>",
        "geographic_location": "<city, state>",
        "applies_to": "<what this document governs - e.g., 'primary residence', 'refinance loan', etc>",
        "regulatory_framework": ["<TILA|RESPA|ECOA|etc if mentioned>"]
      }},
      "document_relationships": {{
        "references_other_documents": ["<list of other documents referenced by name>"],
        "has_attachments": true|false,
        "attachment_list": ["<list of mentioned attachments/exhibits>"],
        "supersedes": "<document this replaces, if mentioned>",
        "part_of_series": "<if this is part 1 of N or similar>"
      }},
      "content_flags": {{
        "has_financial_data": true|false,
        "has_property_details": true|false,
        "has_legal_language": true|false,
        "has_tables": true|false,
        "has_calculations": true|false,
        "is_disclosure": true|false,
        "is_agreement": true|false,
        "is_report": true|false,
        "is_government_form": true|false,
        "requires_notarization": true|false
      }},
      "revision_indicators": {{
        "shows_revision_marks": true|false,
        "revision_number": "<if present>",
        "revision_date": "<if present>",
        "amended_sections": ["<list of sections marked as amended>"]
      }},
      "content_fingerprint": {{
        "key_data_hash": "<conceptual hash: combine critical fields like loan_number + borrower_names + property_address + amounts>",
        "structural_pattern": "<describe document structure: e.g., '2-page form, signatures on page 2, table on page 1'>",
        "unique_identifiers": ["<list of unique IDs that distinguish this document from others>"],
        "template_type": "<if recognizable: URLA_1003|Closing_Disclosure|etc>",
        "distinguishing_features": ["<list features that make this document unique vs similar documents>"]
      }},
      "perceptual_hashes": {{
        "note": "These hashes are computed programmatically from images, not by LLM",
        "page_hashes": [
          {{
            "page": 1,
            "phash": "<will be populated by system>",
            "dhash": "<will be populated by system>",
            "average_hash": "<will be populated by system>",
            "whash": "<will be populated by system>"
          }}
        ],
        "document_phash_signature": "<combined hash of all pages for quick comparison>"
      }}
    }},
    "document_overview": {{
      "document_type": "<specific type from all pages>",
      "effective_date": "<primary document date>",
      "purpose": "<1-2 sentence description>",
      "total_pages": {len(pages)}
    }},
    "document_structure": {{
      "page_breakdown": [
        {{"page": 1, "content": "<brief description of page 1 content>"}},
        {{"page": 2, "content": "<brief description of page 2 content>"}}
      ],
      "sections": ["<list of main sections in document>"]
    }},
    "extracted_data": {{
      // Consolidate ALL key data from all pages
      // Group by category (property info, financial data, parties, etc.)
    }},
    "financial_summary": {{
      // All financial data consolidated and organized
    }},
    "important_values": {{
      // Key values with page references
    }},
    "key_entities": {{
      "addresses": {{...}},
      "organizations": [...],
      "people": [...],
      "reference_numbers": {{...}}
    }},
    "summary_statistics": {{
      // Any calculated statistics or aggregations
    }}
  }}
}}

CRITICAL RULES:
1. **document_metadata is MANDATORY** - Extract ALL subsections completely
2. **document_status**: Check ALL pages for signatures/acknowledgments. If ANY signature field is present → "signed", else → "unsigned"
3. **visual_fingerprint**: Describe the visual/structural characteristics - helps identify same template/form with different data
4. **all_dates**: Extract EVERY date found in the document with its type and page number
5. **document_persons**: Extract EVERY person mentioned (borrowers, lenders, notaries, witnesses) with their role and signature status
6. **signature_analysis**: List ALL signature fields found, even if unsigned/blank
7. **key_identifiers**: Extract property address, loan amount, borrower names - critical for document matching
8. **document_completeness**: Assess if document is fully filled out. Check for blank required fields, unsigned signature blocks
9. **document_scope**: Extract jurisdiction, regulatory references (TILA, RESPA, etc.)
10. **document_relationships**: Note any references to other documents, attachments, exhibits
11. **content_flags**: Mark what type of content this document contains
12. **revision_indicators**: Look for any revision marks, version numbers, amendment indicators
13. **content_fingerprint**: Identify what makes this document unique vs similar documents (critical for duplicate detection)
14. Consolidate data from ALL pages
15. Remove duplicates
16. Include page references for key values
17. Calculate aggregates where applicable
18. Organize hierarchically
19. Use null for missing data, false for boolean flags when not present

⚠️ IMPORTANT: The document_metadata section is critical for downstream processing (semantic grouping, duplicate detection, document matching). Be thorough and accurate.

Return ONLY valid JSON."""

    messages = [{"role": "user", "content": prompt}]
    
    try:
        result = client.invoke_model(
            messages=messages,
            max_tokens=8000,
            temperature=0.0
        )
        
        print(f"     Summary: Tokens: Input={result['usage']['input_tokens']}, Output={result['usage']['output_tokens']}")
        
        summary_data = parse_json_from_text(result['content'])
        return summary_data
        
    except Exception as e:
        print(f"     ⚠️ Could not generate document summary: {e}")
        return None


def extract_document_pagewise(pdf_path: str, filename: str, client: LlamaClient, pdf_type: str = "scanned", dpi: int = 150) -> Dict:
    """Extract deep JSON from PDF in page-wise format matching Claude Opus"""
    
    print(f"\n{'='*80}")
    print(f"🦙 Processing: {filename}")
    print(f"{'='*80}")
    
    start_time = time.time()
    
    try:
        images_base64, page_hashes = convert_pdf_to_base64_images(pdf_path, dpi=dpi)
        page_count = len(images_base64)
        
        print(f"  📄 Processing {page_count} pages individually...")
        
        pages = []
        for page_idx, img_b64 in enumerate(images_base64, 1):
            print(f"  🔄 Extracting page {page_idx}/{page_count}")
            
            page_data = extract_single_page(img_b64, filename, page_idx, page_count, client)
            
            if page_data:
                pages.append(page_data)
            else:
                pages.append({
                    "page_number": page_idx,
                    "page_type": "unknown",
                    "extraction_error": "Failed to extract page data"
                })
            
            if page_idx < page_count:
                time.sleep(1)
        
        # Generate document-level summary
        document_summary = generate_document_summary(pages, filename, client)
        
        # Compute document-level perceptual hash signature (combine all page hashes)
        combined_phash = "-".join([h['phash'] for h in page_hashes])
        document_phash_signature = hashlib.md5(combined_phash.encode()).hexdigest()
        
        duration = time.time() - start_time
        
        document_json = {
            "filename": filename,
            "model": "Llama 4 Maverick 17B",
            "total_pages": page_count,
            "processing_date": datetime.now().strftime("%Y-%m-%d"),
            "pages": pages,
            "_extraction_metadata": {
                "model": "llama-4-maverick-17b",
                "extracted_at": datetime.now().isoformat(),
                "duration_seconds": round(duration, 2),
                "page_count": page_count,
                "extraction_method": "page_wise_with_summary",
                "pdf_type": pdf_type,
                "pages_extracted": len(pages),
                "pages_failed": page_count - len([p for p in pages if 'extraction_error' not in p]),
                "has_document_summary": document_summary is not None
            }
        }
        
        # Add document_summary if generated successfully
        if document_summary:
            # Inject perceptual hashes into document_metadata
            if 'document_summary' in document_summary:
                if 'document_metadata' not in document_summary['document_summary']:
                    document_summary['document_summary']['document_metadata'] = {}
                
                # Add perceptual hashes
                document_summary['document_summary']['document_metadata']['perceptual_hashes'] = {
                    'page_hashes': [
                        {
                            'page': idx + 1,
                            'phash': h['phash'],
                            'dhash': h['dhash'],
                            'average_hash': h['average_hash'],
                            'whash': h['whash']
                        }
                        for idx, h in enumerate(page_hashes)
                    ],
                    'document_phash_signature': document_phash_signature
                }
            
            document_json.update(document_summary)
        
        print(f"  ✓ Extraction complete in {duration:.2f}s")
        print(f"  ✓ Extracted {len(pages)} pages")
        if document_summary:
            print(f"  ✓ Generated document-level summary")
        
        return {
            'success': True,
            'filename': filename,
            'data': document_json,
            'duration': duration
        }
            
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return {
            'success': False,
            'filename': filename,
            'error': str(e)
        }

