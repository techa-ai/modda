#!/usr/bin/env python3
"""
Compare two documents using their FULL deep JSON extractions
"""

import os
import sys
import json
from pathlib import Path

# Import Llama client
sys.path.insert(0, str(Path(__file__).parent))
from llama_pagewise_extractor import LlamaClient


def compare_documents_json(json1_path: str, json2_path: str, client: LlamaClient):
    """Compare two documents using their full deep JSON"""
    
    print("\n" + "="*80)
    print(f"🔍 SEMANTIC DOCUMENT COMPARISON (Full Deep JSON)")
    print("="*80)
    print(f"Document 1: {Path(json1_path).name}")
    print(f"Document 2: {Path(json2_path).name}")
    print()
    
    # Load both JSONs
    with open(json1_path, 'r') as f:
        json1 = json.load(f)
    
    with open(json2_path, 'r') as f:
        json2 = json.load(f)
    
    json1_str = json.dumps(json1, indent=2)
    json2_str = json.dumps(json2, indent=2)
    
    print(f"  📊 Document 1: {len(json1_str)} chars, {len(json1_str)//4} tokens (estimated)")
    print(f"  📊 Document 2: {len(json2_str)} chars, {len(json2_str)//4} tokens (estimated)")
    
    # Create comparison prompt
    prompt = f"""You are comparing two documents using their FULL deep JSON extractions. These JSONs contain ALL information extracted from the documents, including dates, signatures, timestamps, and all content.

DOCUMENT 1 JSON ({Path(json1_path).stem}):
{json1_str}

DOCUMENT 2 JSON ({Path(json2_path).stem}):
{json2_str}

TASK: Analyze these two documents and determine their relationship.

**Critical: Look for signature/acknowledgment differences:**
- Check for fields like: signature, signed, acknowledgment_date, acknowledgment_time, signature_date, etc.
- Check if one has signature fields and the other doesn't
- Check timestamps and date fields on ALL pages, not just page 1

Return a JSON analysis with this structure:
{{
  "similarity_level": "IDENTICAL|VERY_SIMILAR|SOMEWHAT_SIMILAR|DIFFERENT",
  "relationship": "exact_duplicate|signed_unsigned|chronological|preliminary_final|different_documents",
  "confidence": "HIGH|MEDIUM|LOW",
  "document_type": "the document type",
  "identical_fields": ["list of fields with identical values"],
  "different_fields": [
    {{
      "field": "field name",
      "location": "page X",
      "doc1_value": "value in document 1",
      "doc2_value": "value in document 2",
      "difference_type": "SUBSTANTIVE|MINOR"
    }}
  ],
  "signature_analysis": {{
    "doc1_has_signature": true/false,
    "doc2_has_signature": true/false,
    "signature_fields_doc1": ["list of signature-related fields in doc1"],
    "signature_fields_doc2": ["list of signature-related fields in doc2"]
  }},
  "date_analysis": {{
    "same_date": true/false,
    "doc1_dates": ["dates found in doc1"],
    "doc2_dates": ["dates found in doc2"]
  }},
  "key_differences_summary": "summary of main differences",
  "recommendation": "KEEP_ONE|KEEP_SIGNED_VERSION|KEEP_BOTH|KEEP_LATEST",
  "reasoning": "explanation"
}}

Provide ONLY valid JSON, no other text."""
    
    print(f"\n  🤖 Sending FULL JSONs to Llama 4 Maverick...")
    print(f"  📊 Total prompt size: ~{len(prompt)//4:,} tokens")
    
    try:
        response = client.invoke_model(
            messages=[{
                "role": "user",
                "content": prompt
            }],
            max_tokens=4000,
            temperature=0.0
        )
        
        # Extract response
        result_text = response.get('content', str(response))
        
        # Parse JSON
        try:
            if '```json' in result_text:
                json_start = result_text.find('```json') + 7
                json_end = result_text.find('```', json_start)
                json_text = result_text[json_start:json_end].strip()
            elif '```' in result_text:
                json_start = result_text.find('```') + 3
                json_end = result_text.rfind('```')
                json_text = result_text[json_start:json_end].strip()
            else:
                json_start = result_text.find('{')
                json_end = result_text.rfind('}') + 1
                json_text = result_text[json_start:json_end]
            
            result_json = json.loads(json_text)
        except json.JSONDecodeError as e:
            print(f"\n⚠️  Warning: Could not parse JSON: {e}")
            print("Raw response:")
            print(result_text[:1000])
            result_json = {"raw_response": result_text, "error": f"JSON parse failed: {e}"}
        
        # Print results
        print("\n" + "="*80)
        print("📊 COMPARISON RESULTS")
        print("="*80)
        
        if "similarity_level" in result_json:
            print(f"\n🎯 Similarity Level: {result_json['similarity_level']}")
            print(f"   Relationship: {result_json.get('relationship', 'N/A')}")
            print(f"   Confidence: {result_json['confidence']}")
            print(f"   Document Type: {result_json['document_type']}")
            
            # Signature analysis
            sig_analysis = result_json.get('signature_analysis', {})
            print(f"\n✍️  SIGNATURE ANALYSIS:")
            print(f"   Doc 1 has signature: {sig_analysis.get('doc1_has_signature', 'Unknown')}")
            if sig_analysis.get('signature_fields_doc1'):
                print(f"   Doc 1 signature fields: {sig_analysis['signature_fields_doc1']}")
            print(f"   Doc 2 has signature: {sig_analysis.get('doc2_has_signature', 'Unknown')}")
            if sig_analysis.get('signature_fields_doc2'):
                print(f"   Doc 2 signature fields: {sig_analysis['signature_fields_doc2']}")
            
            # Date analysis
            date_analysis = result_json.get('date_analysis', {})
            print(f"\n📅 DATE ANALYSIS:")
            print(f"   Same date: {date_analysis.get('same_date', 'Unknown')}")
            print(f"   Doc 1 dates: {date_analysis.get('doc1_dates', [])}")
            print(f"   Doc 2 dates: {date_analysis.get('doc2_dates', [])}")
            
            print(f"\n✅ Identical Fields ({len(result_json.get('identical_fields', []))}):")
            for field in result_json.get('identical_fields', [])[:10]:
                print(f"   - {field}")
            if len(result_json.get('identical_fields', [])) > 10:
                print(f"   ... and {len(result_json['identical_fields']) - 10} more")
            
            print(f"\n⚠️  Different Fields ({len(result_json.get('different_fields', []))}):")
            for diff in result_json.get('different_fields', []):
                print(f"   - {diff.get('field', 'unknown')} @ {diff.get('location', 'unknown')} ({diff.get('difference_type', 'unknown')})")
                print(f"     Doc 1: {diff.get('doc1_value', 'N/A')}")
                print(f"     Doc 2: {diff.get('doc2_value', 'N/A')}")
            
            print(f"\n📝 Key Differences Summary:")
            print(f"   {result_json.get('key_differences_summary', 'N/A')}")
            
            print(f"\n💡 Recommendation: {result_json.get('recommendation', 'N/A')}")
            print(f"   Reasoning: {result_json.get('reasoning', 'N/A')}")
        else:
            print("\n⚠️  Unexpected response format")
            print(json.dumps(result_json, indent=2)[:1000])
        
        print("\n" + "="*80)
        
        return result_json
        
    except Exception as e:
        print(f"\n❌ Error during comparison: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python compare_documents_json.py <json1_path> <json2_path>")
        print("\nExample:")
        print("  python compare_documents_json.py \\")
        print("    output/loan_1642451/1_2_4_llama_extractions/flood_notice_to_borrower_36.json \\")
        print("    output/loan_1642451/1_2_4_llama_extractions/flood_notice_to_borrower_37.json")
        sys.exit(1)
    
    json1 = sys.argv[1]
    json2 = sys.argv[2]
    
    if not os.path.exists(json1):
        print(f"❌ Error: File not found: {json1}")
        sys.exit(1)
    
    if not os.path.exists(json2):
        print(f"❌ Error: File not found: {json2}")
        sys.exit(1)
    
    # Initialize client
    client = LlamaClient()
    
    # Compare documents
    result = compare_documents_json(json1, json2, client)
    
    # Save result
    output_file = Path("comparison_json_result.json")
    with open(output_file, 'w') as f:
        json.dump({
            'document1': str(json1),
            'document2': str(json2),
            'comparison_result': result
        }, f, indent=2)
    
    print(f"\n💾 Full result saved to: {output_file}")



