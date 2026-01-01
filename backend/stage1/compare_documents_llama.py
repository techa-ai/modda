#!/usr/bin/env python3
"""
Use Llama 4 Maverick to semantically compare two documents
"""

import os
import sys
import json
from pathlib import Path
from pdf2image import convert_from_path
import base64
from io import BytesIO
import boto3

# Import existing client
sys.path.insert(0, str(Path(__file__).parent))
from llama_pagewise_extractor import LlamaClient


def pdf_to_images(pdf_path: str, dpi: int = 150):
    """Convert PDF to images"""
    print(f"  📄 Converting {Path(pdf_path).name} to images (DPI: {dpi})...")
    images = convert_from_path(pdf_path, dpi=dpi)
    print(f"  ✓ Converted {len(images)} pages")
    return images


def images_to_base64(images):
    """Convert PIL images to base64"""
    base64_images = []
    for img in images:
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        base64_images.append(img_str)
    return base64_images


def compare_documents(pdf1_path: str, pdf2_path: str, client: LlamaClient):
    """Use Llama to compare two documents semantically"""
    
    print("\n" + "="*80)
    print(f"🔍 SEMANTIC DOCUMENT COMPARISON")
    print("="*80)
    print(f"Document 1: {Path(pdf1_path).name}")
    print(f"Document 2: {Path(pdf2_path).name}")
    print()
    
    # Convert both PDFs to images
    images1 = pdf_to_images(pdf1_path, dpi=150)
    images2 = pdf_to_images(pdf2_path, dpi=150)
    
    # Convert to base64
    print("\n  🔄 Encoding images...")
    base64_images1 = images_to_base64(images1)
    base64_images2 = images_to_base64(images2)
    
    # Prepare comparison prompt
    comparison_prompt = """You are comparing two documents to determine if they are similar versions of the same document or completely different documents.

Please analyze both documents and provide:

1. **Similarity Assessment**: Are these the same document or different documents? (IDENTICAL / VERY_SIMILAR / SOMEWHAT_SIMILAR / DIFFERENT)

2. **Document Type**: What type of document is this?

3. **Core Content Comparison**: Compare the main content (loan amounts, dates, parties, terms, etc.)
   - List all IDENTICAL fields/values
   - List all DIFFERENT fields/values

4. **Key Differences**: What are the main differences between the two documents?
   - Substantive differences (amounts, terms, parties, conditions)
   - Minor differences (formatting, timestamps, signatures, metadata)

5. **Recommendation**: Based on your analysis, are these:
   - Exact duplicates (keep only one)
   - Same document with signature/timestamp differences (unsigned vs signed version)
   - Different versions with substantive changes (preliminary vs final with changes)
   - Completely different documents

Return your analysis as a structured JSON object with the following format:
{
  "similarity_level": "IDENTICAL|VERY_SIMILAR|SOMEWHAT_SIMILAR|DIFFERENT",
  "confidence": "HIGH|MEDIUM|LOW",
  "document_type": "description of document type",
  "identical_fields": ["list of fields with identical values"],
  "different_fields": [
    {
      "field": "field name",
      "doc1_value": "value in document 1",
      "doc2_value": "value in document 2",
      "difference_type": "SUBSTANTIVE|MINOR"
    }
  ],
  "key_differences_summary": "brief summary of main differences",
  "recommendation": "KEEP_ONE|KEEP_SIGNED_VERSION|KEEP_BOTH|FURTHER_REVIEW",
  "reasoning": "explanation of your recommendation"
}

Provide ONLY valid JSON, no other text."""

    # For Llama 4 Maverick, limit to 3 images total
    # Send 1 page from each document (focusing on first page which has most info)
    print("\n  🤖 Sending to Llama 4 Maverick for semantic comparison...")
    print(f"  📊 Comparing first page + 1 additional page per document (3 images total)")
    
    # Build message content
    content_parts = []
    content_parts.append({"type": "text", "text": comparison_prompt})
    content_parts.append({"type": "text", "text": "\n--- DOCUMENT 1 ---"})
    
    # Add first page from doc 1
    if len(base64_images1) > 0:
        content_parts.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": base64_images1[0]
            }
        })
    
    content_parts.append({"type": "text", "text": "\n--- DOCUMENT 2 ---"})
    
    # Add first 2 pages from doc 2 (totaling 3 images)
    for i in range(min(2, len(base64_images2))):
        content_parts.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": base64_images2[i]
            }
        })
    
    try:
        # Use LlamaClient's invoke_model method
        response = client.invoke_model(
            messages=[{
                "role": "user",
                "content": content_parts
            }],
            max_tokens=4000,
            temperature=0.0
        )
        
        # Response is a dict with 'content' key containing the text
        if isinstance(response, dict) and 'content' in response:
            result_text = response['content']
        elif isinstance(response, dict):
            result_text = response.get('response', response.get('text', str(response)))
        else:
            result_text = str(response)
        
        # Parse JSON from response
        try:
            # Extract JSON from markdown code blocks if present
            if '```json' in result_text:
                json_start = result_text.find('```json') + 7
                json_end = result_text.find('```', json_start)
                json_text = result_text[json_start:json_end].strip()
            elif '```' in result_text:
                json_start = result_text.find('```') + 3
                json_end = result_text.rfind('```')
                json_text = result_text[json_start:json_end].strip()
            else:
                # Try to extract JSON object
                json_start = result_text.find('{')
                json_end = result_text.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    json_text = result_text[json_start:json_end]
                else:
                    json_text = result_text
            
            result_json = json.loads(json_text)
        except json.JSONDecodeError as e:
            print(f"\n⚠️  Warning: Could not parse JSON: {e}")
            print("Raw response:")
            print(result_text[:500])
            result_json = {"raw_response": result_text, "error": f"JSON parse failed: {e}"}
        
        # Print results
        print("\n" + "="*80)
        print("📊 COMPARISON RESULTS")
        print("="*80)
        
        if "similarity_level" in result_json:
            print(f"\n🎯 Similarity Level: {result_json['similarity_level']}")
            print(f"   Confidence: {result_json['confidence']}")
            print(f"   Document Type: {result_json['document_type']}")
            
            print(f"\n✅ Identical Fields ({len(result_json.get('identical_fields', []))}):")
            for field in result_json.get('identical_fields', [])[:10]:
                print(f"   - {field}")
            if len(result_json.get('identical_fields', [])) > 10:
                print(f"   ... and {len(result_json['identical_fields']) - 10} more")
            
            print(f"\n⚠️  Different Fields ({len(result_json.get('different_fields', []))}):")
            for diff in result_json.get('different_fields', []):
                print(f"   - {diff.get('field', 'unknown')} ({diff.get('difference_type', 'unknown')})")
                print(f"     Doc 1: {diff.get('doc1_value', 'N/A')}")
                print(f"     Doc 2: {diff.get('doc2_value', 'N/A')}")
            
            print(f"\n📝 Key Differences Summary:")
            print(f"   {result_json.get('key_differences_summary', 'N/A')}")
            
            print(f"\n💡 Recommendation: {result_json.get('recommendation', 'N/A')}")
            print(f"   Reasoning: {result_json.get('reasoning', 'N/A')}")
        else:
            print("\n⚠️  Unexpected response format")
            print(json.dumps(result_json, indent=2))
        
        print("\n" + "="*80)
        
        return result_json
        
    except Exception as e:
        print(f"\n❌ Error during comparison: {e}")
        return {"error": str(e)}


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python compare_documents_llama.py <pdf1_path> <pdf2_path>")
        print("\nExample:")
        print("  python compare_documents_llama.py \\")
        print("    ../../documents/loan_1642451/borrower_rate_lock_agreement_18.pdf \\")
        print("    ../../documents/loan_1642451/borrower_rate_lock_agreement_19.pdf")
        sys.exit(1)
    
    pdf1 = sys.argv[1]
    pdf2 = sys.argv[2]
    
    if not os.path.exists(pdf1):
        print(f"❌ Error: File not found: {pdf1}")
        sys.exit(1)
    
    if not os.path.exists(pdf2):
        print(f"❌ Error: File not found: {pdf2}")
        sys.exit(1)
    
    # Initialize client
    client = LlamaClient()
    
    # Compare documents
    result = compare_documents(pdf1, pdf2, client)
    
    # Save result
    output_file = Path("comparison_result.json")
    with open(output_file, 'w') as f:
        json.dump({
            'document1': str(pdf1),
            'document2': str(pdf2),
            'comparison_result': result
        }, f, indent=2)
    
    print(f"\n💾 Full result saved to: {output_file}")

