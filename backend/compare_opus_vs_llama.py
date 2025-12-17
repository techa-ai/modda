#!/usr/bin/env python3
"""
Head-to-Head Comparison: Claude Opus 4.5 vs Llama 4 Maverick 17B
For 1008 Form Deep JSON Extraction

Focus on:
- Table extraction accuracy
- Field alignment issues
- Numerical accuracy
- Structural completeness
"""

import os
import sys
import json
import time
import base64
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import difflib
from pdf2image import convert_from_path
import io

# Import existing utilities
from bedrock_config import BedrockClient, BEDROCK_API_KEY, AWS_REGION, BEDROCK_ENDPOINT, BEDROCK_ENDPOINT_US_EAST_1

# Llama Model Configuration
# Llama 4 Maverick 17B Instruct - Released April 2025
# 17B active parameters, 400B total (MoE), 1M token context, Vision support
# NOTE: Must use inference profile (us. prefix) with boto3
LLAMA_MODEL_ID = "us.meta.llama4-maverick-17b-instruct-v1:0"
LLAMA_REGION = "us-east-1"

# Alternative models (if needed):
# LLAMA_MODEL_ID = "us.meta.llama3-2-90b-instruct-v1:0"  # Llama 3.2 90B Vision
# LLAMA_MODEL_ID = "us.meta.llama3-2-11b-instruct-v1:0"  # Llama 3.2 11B Vision
# LLAMA_MODEL_ID = "meta.llama3-3-70b-instruct-v1:0"     # Llama 3.3 70B (no vision)


class LlamaClient:
    """Client for Llama 4 Maverick 17B via AWS Bedrock using boto3"""
    
    def __init__(self, api_key: Optional[str] = None):
        import boto3
        self.model = LLAMA_MODEL_ID
        # Use boto3 client (not REST API) for Llama 4
        self.client = boto3.client('bedrock-runtime', region_name=LLAMA_REGION)
    
    def invoke_model(
        self,
        messages: List[Dict],
        max_tokens: int = 16000,
        temperature: float = 0.0,
        system_prompt: Optional[str] = None
    ) -> Dict:
        """
        Invoke Llama 4 Maverick model with messages.
        
        Llama 4 uses a different API format than Claude - requires 'prompt' instead of 'messages'
        """
        import requests
        
        # Convert messages to Llama format with special tokens
        # Reference: https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-meta.html
        
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
                        # Extract base64 image data (just the data, not the full structure)
                        images.append(item["source"]["data"])
        
        # Format prompt with Llama's special tokens
        # For multimodal, add <image> tokens for each image
        user_prompt = "\n\n".join(prompt_parts)
        
        # Add image tokens at the beginning if images present
        # Llama 4 uses <|image|> format (with pipes)
        if images:
            image_tokens = "".join(["<|image|>" for _ in images])
            formatted_prompt = f"""<|begin_of_text|><|start_header_id|>user<|end_header_id|>
{image_tokens}
{user_prompt}
<|eot_id|>
<|start_header_id|>assistant<|end_header_id|>"""
        else:
            formatted_prompt = f"""<|begin_of_text|><|start_header_id|>user<|end_header_id|>
{user_prompt}
<|eot_id|>
<|start_header_id|>assistant<|end_header_id|>"""
        
        # Llama 4 Maverick API format
        body = {
            "prompt": formatted_prompt,
            "max_gen_len": max_tokens,
            "temperature": temperature,
        }
        
        # Add images if present (Llama 3.2+ supports multimodal)
        # images should be a list of base64 strings
        if images:
            body["images"] = images
        
        # Make request using boto3 SDK
        try:
            response = self.client.invoke_model(
                modelId=self.model,
                body=json.dumps(body)
            )
            
            # Parse response
            result = json.loads(response['body'].read())
            
            # Extract content from Llama 4 Maverick response
            # Llama 4 returns: {"generation": "...", "prompt_token_count": ..., "generation_token_count": ...}
            if 'generation' in result:
                return {
                    'content': result['generation'],
                    'usage': {
                        'input_tokens': result.get('prompt_token_count', 0),
                        'output_tokens': result.get('generation_token_count', 0)
                    },
                    'model': self.model
                }
            # Fallback for other response formats
            elif 'content' in result and len(result['content']) > 0:
                return {
                    'content': result['content'][0]['text'],
                    'usage': result.get('usage', {}),
                    'model': self.model
                }
            else:
                raise ValueError(f"Unexpected Llama response format: {result}")
                
        except Exception as e:
            raise Exception(f"Bedrock API error for Llama: {e}")


def convert_pdf_to_base64_images(pdf_path: str, dpi: int = 150) -> List[str]:
    """Convert PDF to list of base64-encoded images"""
    print(f"  📄 Converting PDF to images (DPI={dpi})...")
    images = convert_from_path(pdf_path, dpi=dpi, fmt='jpeg')
    
    base64_images = []
    for i, img in enumerate(images):
        buffered = io.BytesIO()
        img.save(buffered, format="JPEG", quality=85)
        img_b64 = base64.b64encode(buffered.getvalue()).decode()
        base64_images.append(img_b64)
        print(f"    Page {i+1}: {len(img_b64)} chars")
    
    return base64_images


def create_1008_extraction_prompt() -> str:
    """Create comprehensive prompt for 1008 form extraction"""
    
    return """Analyze this Form 1008 - Uniform Underwriting and Transmittal Summary.

TASK: Extract ALL data from this form into a comprehensive JSON structure.

CRITICAL REQUIREMENTS:

1. **Table Alignment & Structure**:
   - Pay close attention to column alignment in tables
   - Borrower vs Co-Borrower columns must be correctly identified
   - Income sections: Base Income, Other Income, Positive Cash Flow, Total
   - Proposed Monthly Payments: Match each label to its correct value
   - Handle multi-line labels correctly (e.g., "Negative Cash Flow (subject property)")

2. **Numerical Accuracy**:
   - Extract ALL dollar amounts, percentages, and dates precisely
   - Preserve decimal precision (e.g., 6.875%, $8,382.41)
   - Verify math: Total = Sum of components
   - Common calculations to verify:
     * Combined Total = Borrower + Co-Borrower
     * Total Housing Expense = sum of all housing costs
     * Total Monthly Payments = Housing + Other Obligations + Negative Cash Flow

3. **Field Completeness**:
   - Extract EVERY filled field on the form
   - Include checkboxes (checked/unchecked)
   - Capture signatures, dates, stamps
   - Don't skip empty fields - mark them as null

4. **Specific Problem Areas (VERY IMPORTANT)**:
   - "Other Obligations" section: Distinguish between:
     * "All Other Monthly Payments" (usually small: credit cards, car loans)
     * "Negative Cash Flow" (subject property rental shortfall)
     * "Total All Monthly Payments" (final sum)
   - Visual misalignment: Values may appear shifted
   - Use MATH to validate correct assignment
   - Example: If Total Primary = $4,034 and you see $4,034 next to "All Other", 
     that's WRONG - it's likely "Total All" due to alignment issues

OUTPUT STRUCTURE:
{
  "document_metadata": {
    "form_name": "...",
    "fannie_mae_form_number": "1008",
    "page_count": 1
  },
  "section_1_borrower_and_property": {
    "borrower": {"name": "...", "ssn": "..."},
    "co_borrower": {"name": "...", "ssn": "..."},
    "property": {
      "address": "...",
      "type": "...",
      "sales_price": 0.0,
      "appraised_value": 0.0,
      "property_rights": "..."
    },
    "occupancy_status": "..."
  },
  "section_2_mortgage_information": {
    "loan_type": "...",
    "loan_purpose": "...",
    "note_information": {
      "original_loan_amount": 0.0,
      "initial_note_rate": 0.0,
      "loan_term_months": 0
    }
  },
  "section_3_underwriting_information": {
    "underwriter_name": "...",
    "stable_monthly_income": {
      "borrower": {
        "base_income": 0.0,
        "other_income": 0.0,
        "positive_cash_flow": 0.0,
        "total_income": 0.0
      },
      "co_borrower": {
        "base_income": 0.0,
        "other_income": 0.0,
        "positive_cash_flow": 0.0,
        "total_income": 0.0
      },
      "combined_total": {
        "base_income": 0.0,
        "other_income": 0.0,
        "positive_cash_flow": 0.0,
        "total_income": 0.0
      }
    },
    "present_housing_payment": 0.0,
    "proposed_monthly_payments": {
      "first_mortgage_pi": 0.0,
      "second_mortgage_pi": 0.0,
      "hazard_insurance": 0.0,
      "taxes": 0.0,
      "mortgage_insurance": 0.0,
      "hoa_fees": 0.0,
      "lease_ground_rent": 0.0,
      "other": 0.0,
      "total_primary_housing_expense": 0.0
    },
    "other_obligations": {
      "all_other_monthly_payments": 0.0,
      "negative_cash_flow": 0.0,
      "total_all_monthly_payments": 0.0
    },
    "ratios": {
      "total_debt_ratio": 0.0,
      "housing_expense_ratio": 0.0
    }
  },
  "section_4_aus_recommendation": {
    "system_used": "...",
    "recommendation": "...",
    "case_file_id": "..."
  },
  "section_5_underwriter_certification": {
    "certification_text": "...",
    "underwriter_signature": "...",
    "date": "..."
  }
}

Return ONLY valid JSON. Be extremely precise with numbers and alignment."""


def extract_with_claude(pdf_path: str, images_base64: List[str]) -> Dict:
    """Extract 1008 form data using Claude Opus 4.5"""
    
    print("\n" + "="*80)
    print("🤖 CLAUDE OPUS 4.5 EXTRACTION")
    print("="*80)
    
    client = BedrockClient(model='claude-opus-4-5')
    prompt = create_1008_extraction_prompt()
    
    # Prepare multimodal content
    content_parts = [{"type": "text", "text": prompt}]
    for img_b64 in images_base64:
        content_parts.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": img_b64
            }
        })
    
    messages = [{"role": "user", "content": content_parts}]
    
    print("  🔄 Calling Claude Opus 4.5...")
    start_time = time.time()
    
    try:
        result = client.invoke_model(
            messages=messages,
            max_tokens=16000,
            temperature=0.0
        )
        
        duration = time.time() - start_time
        print(f"  ✓ Response received in {duration:.2f}s")
        print(f"  📊 Tokens: {result['usage']}")
        
        # Parse JSON from response
        content = result['content']
        extracted_json = parse_json_from_text(content)
        
        return {
            'success': True,
            'data': extracted_json,
            'raw_response': content,
            'duration': duration,
            'usage': result['usage'],
            'model': 'claude-opus-4-5'
        }
        
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return {
            'success': False,
            'error': str(e),
            'model': 'claude-opus-4-5'
        }


def extract_with_llama(pdf_path: str, images_base64: List[str]) -> Dict:
    """Extract 1008 form data using Llama model"""
    
    print("\n" + "="*80)
    print(f"🦙 LLAMA EXTRACTION ({LLAMA_MODEL_ID})")
    print("="*80)
    
    client = LlamaClient()
    prompt = create_1008_extraction_prompt()
    
    # Prepare multimodal content (same format for consistency)
    content_parts = [{"type": "text", "text": prompt}]
    for img_b64 in images_base64:
        content_parts.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": img_b64
            }
        })
    
    messages = [{"role": "user", "content": content_parts}]
    
    print(f"  🔄 Calling Llama ({LLAMA_MODEL_ID})...")
    start_time = time.time()
    
    try:
        result = client.invoke_model(
            messages=messages,
            max_tokens=8000,  # Llama 4 max is 8192
            temperature=0.0
        )
        
        duration = time.time() - start_time
        print(f"  ✓ Response received in {duration:.2f}s")
        print(f"  📊 Tokens: {result['usage']}")
        
        # Parse JSON from response
        content = result['content']
        extracted_json = parse_json_from_text(content)
        
        return {
            'success': True,
            'data': extracted_json,
            'raw_response': content,
            'duration': duration,
            'usage': result['usage'],
            'model': 'llama-4-maverick-17b'
        }
        
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return {
            'success': False,
            'error': str(e),
            'model': 'llama-4-maverick-17b'
        }


def parse_json_from_text(text: str) -> Optional[Dict]:
    """Extract and parse JSON from text response"""
    
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # Try removing markdown code blocks
    if '```json' in text:
        try:
            json_text = text.split('```json')[1].split('```')[0].strip()
            return json.loads(json_text)
        except:
            pass
    
    if '```' in text:
        try:
            json_text = text.split('```')[1].split('```')[0].strip()
            return json.loads(json_text)
        except:
            pass
    
    # Try finding first { to last }
    try:
        start = text.find('{')
        end = text.rfind('}') + 1
        if start != -1 and end > start:
            json_text = text[start:end]
            return json.loads(json_text)
    except:
        pass
    
    return None


def compare_extractions(claude_result: Dict, llama_result: Dict) -> Dict:
    """Compare the two extractions and identify differences"""
    
    print("\n" + "="*80)
    print("📊 COMPARISON ANALYSIS")
    print("="*80)
    
    comparison = {
        'timestamp': datetime.now().isoformat(),
        'models': {
            'claude': 'claude-opus-4-5',
            'llama': LLAMA_MODEL_ID
        },
        'performance': {},
        'accuracy': {},
        'differences': {}
    }
    
    # Performance comparison
    if claude_result.get('success') and llama_result.get('success'):
        comparison['performance'] = {
            'claude_duration_sec': claude_result.get('duration', 0),
            'llama_duration_sec': llama_result.get('duration', 0),
            'claude_tokens': claude_result.get('usage', {}),
            'llama_tokens': llama_result.get('usage', {}),
            'speed_winner': 'claude' if claude_result.get('duration', 999) < llama_result.get('duration', 999) else 'llama'
        }
        
        print(f"\n⚡ Performance:")
        print(f"  Claude: {claude_result.get('duration', 0):.2f}s")
        print(f"  Llama:  {llama_result.get('duration', 0):.2f}s")
        print(f"  Winner: {comparison['performance']['speed_winner'].upper()}")
    
    # Accuracy comparison (if both succeeded)
    if claude_result.get('success') and llama_result.get('success'):
        claude_data = claude_result.get('data', {})
        llama_data = llama_result.get('data', {})
        
        # Compare key fields
        comparison['differences'] = compare_json_structures(
            claude_data,
            llama_data,
            path='root'
        )
        
        # Critical field comparison
        critical_fields = [
            'section_3_underwriting_information.stable_monthly_income.combined_total.total_income',
            'section_3_underwriting_information.proposed_monthly_payments.total_primary_housing_expense',
            'section_3_underwriting_information.other_obligations.total_all_monthly_payments',
            'section_3_underwriting_information.ratios.total_debt_ratio',
            'section_2_mortgage_information.note_information.original_loan_amount',
        ]
        
        print(f"\n🎯 Critical Field Comparison:")
        field_accuracy = {}
        
        for field_path in critical_fields:
            claude_val = get_nested_value(claude_data, field_path)
            llama_val = get_nested_value(llama_data, field_path)
            
            match = claude_val == llama_val
            field_accuracy[field_path] = {
                'claude': claude_val,
                'llama': llama_val,
                'match': match
            }
            
            status = "✓" if match else "✗"
            print(f"  {status} {field_path}")
            print(f"      Claude: {claude_val}")
            print(f"      Llama:  {llama_val}")
        
        comparison['accuracy']['critical_fields'] = field_accuracy
        
        # Calculate accuracy score
        matches = sum(1 for f in field_accuracy.values() if f['match'])
        total = len(field_accuracy)
        accuracy_pct = (matches / total * 100) if total > 0 else 0
        comparison['accuracy']['critical_field_match_rate'] = accuracy_pct
        
        print(f"\n📈 Accuracy Score: {accuracy_pct:.1f}% ({matches}/{total} critical fields match)")
    
    return comparison


def compare_json_structures(obj1, obj2, path='root', max_depth=10) -> List[Dict]:
    """Recursively compare two JSON structures and identify differences"""
    
    differences = []
    
    if max_depth <= 0:
        return differences
    
    # Type mismatch
    if type(obj1) != type(obj2):
        differences.append({
            'path': path,
            'type': 'type_mismatch',
            'claude': type(obj1).__name__,
            'llama': type(obj2).__name__
        })
        return differences
    
    # Dict comparison
    if isinstance(obj1, dict) and isinstance(obj2, dict):
        all_keys = set(obj1.keys()) | set(obj2.keys())
        
        for key in all_keys:
            new_path = f"{path}.{key}"
            
            if key not in obj1:
                differences.append({
                    'path': new_path,
                    'type': 'missing_in_claude',
                    'llama': obj2[key]
                })
            elif key not in obj2:
                differences.append({
                    'path': new_path,
                    'type': 'missing_in_llama',
                    'claude': obj1[key]
                })
            else:
                differences.extend(
                    compare_json_structures(obj1[key], obj2[key], new_path, max_depth - 1)
                )
    
    # List comparison
    elif isinstance(obj1, list) and isinstance(obj2, list):
        if len(obj1) != len(obj2):
            differences.append({
                'path': path,
                'type': 'length_mismatch',
                'claude_length': len(obj1),
                'llama_length': len(obj2)
            })
        
        for i in range(min(len(obj1), len(obj2))):
            differences.extend(
                compare_json_structures(obj1[i], obj2[i], f"{path}[{i}]", max_depth - 1)
            )
    
    # Value comparison
    else:
        if obj1 != obj2:
            differences.append({
                'path': path,
                'type': 'value_mismatch',
                'claude': obj1,
                'llama': obj2
            })
    
    return differences


def get_nested_value(obj: Dict, path: str):
    """Get nested value from dict using dot notation path"""
    
    keys = path.split('.')
    current = obj
    
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return None
    
    return current


def generate_comparison_report(
    pdf_path: str,
    claude_result: Dict,
    llama_result: Dict,
    comparison: Dict,
    output_dir: str
):
    """Generate comprehensive comparison report"""
    
    print("\n" + "="*80)
    print("📝 GENERATING REPORT")
    print("="*80)
    
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Save individual results
    claude_file = output_dir / f"claude_opus_4.5_{timestamp}.json"
    llama_file = output_dir / f"llama_maverick_17b_{timestamp}.json"
    comparison_file = output_dir / f"comparison_{timestamp}.json"
    report_file = output_dir / f"report_{timestamp}.md"
    
    # Save JSONs
    with open(claude_file, 'w') as f:
        json.dump(claude_result, f, indent=2)
    print(f"  ✓ Saved Claude result: {claude_file}")
    
    with open(llama_file, 'w') as f:
        json.dump(llama_result, f, indent=2)
    print(f"  ✓ Saved Llama result: {llama_file}")
    
    with open(comparison_file, 'w') as f:
        json.dump(comparison, f, indent=2)
    print(f"  ✓ Saved comparison: {comparison_file}")
    
    # Generate markdown report
    report_md = generate_markdown_report(pdf_path, claude_result, llama_result, comparison)
    with open(report_file, 'w') as f:
        f.write(report_md)
    print(f"  ✓ Saved report: {report_file}")
    
    return {
        'claude_file': str(claude_file),
        'llama_file': str(llama_file),
        'comparison_file': str(comparison_file),
        'report_file': str(report_file)
    }


def generate_markdown_report(
    pdf_path: str,
    claude_result: Dict,
    llama_result: Dict,
    comparison: Dict
) -> str:
    """Generate markdown comparison report"""
    
    report = f"""# 1008 Form Extraction Comparison Report

**Document:** `{pdf_path}`  
**Timestamp:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

## Executive Summary

### Models Tested
- **Claude Opus 4.5** (global.anthropic.claude-opus-4-5-20251101-v1:0)
- **Llama Model** ({comparison['models']['llama']})

### Results Overview
"""
    
    if claude_result.get('success') and llama_result.get('success'):
        perf = comparison.get('performance', {})
        acc = comparison.get('accuracy', {})
        
        report += f"""
| Metric | Claude Opus 4.5 | Llama Maverick 17B | Winner |
|--------|-----------------|-------------------|--------|
| Duration | {perf.get('claude_duration_sec', 0):.2f}s | {perf.get('llama_duration_sec', 0):.2f}s | {perf.get('speed_winner', 'N/A').upper()} |
| Accuracy | {acc.get('critical_field_match_rate', 0):.1f}% | {acc.get('critical_field_match_rate', 0):.1f}% | TBD |

---

## Performance Analysis

### Claude Opus 4.5
- **Duration:** {perf.get('claude_duration_sec', 0):.2f} seconds
- **Tokens:** {perf.get('claude_tokens', {})}

### Llama Maverick 17B
- **Duration:** {perf.get('llama_duration_sec', 0):.2f} seconds
- **Tokens:** {perf.get('llama_tokens', {})}

---

## Accuracy Analysis

### Critical Field Comparison

"""
        
        critical_fields = acc.get('critical_fields', {})
        for field_path, field_data in critical_fields.items():
            match_icon = "✅" if field_data['match'] else "❌"
            report += f"""
#### {field_path}
{match_icon} **Match:** {field_data['match']}

- **Claude:** `{field_data['claude']}`
- **Llama:** `{field_data['llama']}`

"""
        
        # Differences summary
        differences = comparison.get('differences', [])
        if differences:
            report += f"""
---

## Detailed Differences

Found {len(differences)} difference(s):

"""
            for i, diff in enumerate(differences[:50], 1):  # Limit to first 50
                report += f"""
### Difference {i}
- **Path:** `{diff.get('path', 'N/A')}`
- **Type:** {diff.get('type', 'N/A')}
"""
                if 'claude' in diff:
                    report += f"- **Claude:** `{diff['claude']}`\n"
                if 'llama' in diff:
                    report += f"- **Llama:** `{diff['llama']}`\n"
                report += "\n"
    
    else:
        report += "\n### ⚠️ One or both extractions failed\n\n"
        
        if not claude_result.get('success'):
            report += f"**Claude Error:** {claude_result.get('error', 'Unknown')}\n\n"
        
        if not llama_result.get('success'):
            report += f"**Llama Error:** {llama_result.get('error', 'Unknown')}\n\n"
    
    report += """
---

## Conclusion

### Table & Alignment Issues
[To be analyzed based on differences]

### Recommendations
[To be determined based on results]

"""
    
    return report


def run_comparison(pdf_path: str, output_dir: str = 'outputs/model_comparison'):
    """Run full comparison between Claude and Llama"""
    
    print("\n" + "="*80)
    print("🔬 HEAD-TO-HEAD MODEL COMPARISON")
    print("="*80)
    print(f"Document: {pdf_path}")
    print(f"Output: {output_dir}")
    print("="*80)
    
    # Convert PDF to images
    images_base64 = convert_pdf_to_base64_images(pdf_path)
    print(f"✓ Converted to {len(images_base64)} image(s)")
    
    # Extract with Claude
    claude_result = extract_with_claude(pdf_path, images_base64)
    
    # Extract with Llama
    llama_result = extract_with_llama(pdf_path, images_base64)
    
    # Compare results
    comparison = compare_extractions(claude_result, llama_result)
    
    # Generate report
    files = generate_comparison_report(
        pdf_path,
        claude_result,
        llama_result,
        comparison,
        output_dir
    )
    
    print("\n" + "="*80)
    print("✅ COMPARISON COMPLETE")
    print("="*80)
    print(f"📁 Results saved to: {output_dir}")
    print(f"📊 Report: {files['report_file']}")
    
    return {
        'claude_result': claude_result,
        'llama_result': llama_result,
        'comparison': comparison,
        'files': files
    }


def main():
    """Main entry point"""
    
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Compare Claude Opus 4.5 vs Llama Maverick 17B for 1008 extraction'
    )
    parser.add_argument(
        'pdf_path',
        help='Path to 1008 PDF file'
    )
    parser.add_argument(
        '--output-dir',
        default='outputs/model_comparison',
        help='Output directory for results'
    )
    
    args = parser.parse_args()
    
    if not os.path.exists(args.pdf_path):
        print(f"❌ Error: File not found: {args.pdf_path}")
        sys.exit(1)
    
    run_comparison(args.pdf_path, args.output_dir)


if __name__ == '__main__':
    main()

