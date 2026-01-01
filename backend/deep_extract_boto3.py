#!/usr/bin/env python3
"""
Deep Extract Tax Returns with Boto3 and Prompt Caching

Uses boto3 for proper prompt caching support via Bedrock's native API.
Prompt caching saves up to 90% on repeated system prompts!
"""

import os
import sys
import json
import time
import base64
import boto3
from io import BytesIO
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from pdf2image import convert_from_path
from PyPDF2 import PdfReader
from db import execute_query, execute_one, get_db_connection

# AWS Configuration
AWS_REGION = 'us-east-1'  # Use us-east-1 for best model availability
MODEL_ID = 'anthropic.claude-opus-4-5-20251101-v1:0'

# Initialize Bedrock client
bedrock_runtime = boto3.client(
    service_name='bedrock-runtime',
    region_name=AWS_REGION
)

# Thread-safe stats
stats_lock = Lock()
stats = {
    'pages_processed': 0,
    'cache_read_tokens': 0,
    'cache_write_tokens': 0,
    'input_tokens': 0,
    'output_tokens': 0,
    'errors': 0
}


def convert_page_to_base64(image):
    """Convert PIL Image to base64 string"""
    buffered = BytesIO()
    image.save(buffered, format="JPEG", quality=85)
    return base64.b64encode(buffered.getvalue()).decode('utf-8')


def invoke_with_caching(system_prompt: str, user_content: list, max_tokens: int = 2000, 
                        use_cache: bool = True, max_retries: int = 5):
    """
    Invoke Bedrock with proper prompt caching via boto3.
    
    The system prompt with cache_control is cached for 5 minutes.
    Cache read: $0.0005/1K tokens (90% cheaper than regular input)
    Cache write: $0.00625/1K tokens
    """
    
    # Build request body with cache control
    if use_cache:
        system = [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"}
            }
        ]
    else:
        system = [{"type": "text", "text": system_prompt}]
    
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "temperature": 0,
        "system": system,
        "messages": [
            {
                "role": "user",
                "content": user_content
            }
        ]
    }
    
    # Retry with exponential backoff
    for attempt in range(max_retries):
        try:
            response = bedrock_runtime.invoke_model(
                modelId=MODEL_ID,
                body=json.dumps(body),
                contentType='application/json',
                accept='application/json'
            )
            
            result = json.loads(response['body'].read())
            
            # Extract text and usage
            if 'content' in result and len(result['content']) > 0:
                text = result['content'][0]['text']
                usage = result.get('usage', {})
                
                # Track token usage (thread-safe)
                with stats_lock:
                    stats['cache_read_tokens'] += usage.get('cache_read_input_tokens', 0)
                    stats['cache_write_tokens'] += usage.get('cache_creation_input_tokens', 0)
                    stats['input_tokens'] += usage.get('input_tokens', 0)
                    stats['output_tokens'] += usage.get('output_tokens', 0)
                
                return text, usage
            else:
                raise ValueError(f"Unexpected response: {result}")
                
        except bedrock_runtime.exceptions.ThrottlingException as e:
            wait_time = min(2 ** attempt * 2, 60)
            print(f"    ⏳ Throttled, waiting {wait_time}s (attempt {attempt + 1}/{max_retries})")
            time.sleep(wait_time)
            
        except Exception as e:
            if 'ThrottlingException' in str(e) or 'Too many' in str(e):
                wait_time = min(2 ** attempt * 2, 60)
                print(f"    ⏳ Rate limited, waiting {wait_time}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait_time)
            else:
                raise
    
    raise Exception(f"Max retries ({max_retries}) exceeded")


def extract_single_page(args):
    """Extract data from a single page using cached system prompt."""
    page_num, image_base64, total_pages, system_prompt, filename = args
    
    user_content = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": image_base64
            }
        },
        {
            "type": "text",
            "text": f"Page {page_num}/{total_pages}. Extract data as compact JSON."
        }
    ]
    
    try:
        response_text, usage = invoke_with_caching(
            system_prompt=system_prompt,
            user_content=user_content,
            max_tokens=1500,  # Reduced for compact output
            use_cache=True
        )
        
        # Parse JSON
        try:
            text = response_text.strip()
            if text.startswith('```'):
                text = text.split('```')[1]
                if text.startswith('json'):
                    text = text[4:]
                text = text.strip()
            page_data = json.loads(text)
        except json.JSONDecodeError:
            page_data = {"raw": response_text[:500], "parse_error": True}
        
        page_data['page_number'] = page_num
        
        with stats_lock:
            stats['pages_processed'] += 1
        
        return {'success': True, 'page': page_num, 'data': page_data, 'usage': usage}
        
    except Exception as e:
        with stats_lock:
            stats['errors'] += 1
        return {'success': False, 'page': page_num, 'error': str(e)[:100]}


def process_pages_with_caching(pdf_path: str, system_prompt: str, filename: str,
                                start_page: int = 1, end_page: int = None,
                                batch_size: int = 20, max_workers: int = 3):
    """
    Process pages with prompt caching enabled.
    Uses smaller batches and fewer workers to avoid rate limits.
    """
    print(f"\n{'='*70}")
    print("PROCESSING WITH BOTO3 PROMPT CACHING")
    print(f"{'='*70}\n")
    
    reader = PdfReader(pdf_path)
    total_pages = len(reader.pages)
    
    if end_page is None:
        end_page = total_pages
    
    pages_to_process = end_page - start_page + 1
    prompt_tokens = len(system_prompt) // 4
    
    print(f"📄 Processing pages {start_page} to {end_page} ({pages_to_process} pages)")
    print(f"📝 System prompt: ~{prompt_tokens} tokens (will be cached)")
    print(f"⚙️  Batch: {batch_size}, Workers: {max_workers}")
    
    # Cost estimates
    input_per_page = 1500
    output_per_page = 500
    
    cost_no_cache = (
        (prompt_tokens + input_per_page) * pages_to_process * 0.005 / 1000 +
        output_per_page * pages_to_process * 0.025 / 1000
    )
    
    cost_with_cache = (
        prompt_tokens * 0.00625 / 1000 +  # Cache write once
        prompt_tokens * (pages_to_process - 1) * 0.0005 / 1000 +  # Cache reads
        input_per_page * pages_to_process * 0.005 / 1000 +
        output_per_page * pages_to_process * 0.025 / 1000
    )
    
    savings = cost_no_cache - cost_with_cache
    savings_pct = (savings / cost_no_cache) * 100
    
    print(f"\n💵 Cost WITHOUT caching: ${cost_no_cache:.2f}")
    print(f"💵 Cost WITH caching: ${cost_with_cache:.2f}")
    print(f"💰 Estimated savings: ${savings:.2f} ({savings_pct:.0f}%)\n")
    
    all_results = []
    start_time = time.time()
    num_batches = (pages_to_process + batch_size - 1) // batch_size
    
    for batch_idx in range(num_batches):
        batch_start = start_page + batch_idx * batch_size
        batch_end = min(batch_start + batch_size - 1, end_page)
        
        print(f"\n📦 Batch {batch_idx + 1}/{num_batches}: Pages {batch_start}-{batch_end}")
        
        # Convert pages to images
        images = convert_from_path(pdf_path, dpi=150, first_page=batch_start, last_page=batch_end)
        
        # Prepare batch args
        batch_args = []
        for idx, image in enumerate(images):
            page_num = batch_start + idx
            image_base64 = convert_page_to_base64(image)
            batch_args.append((page_num, image_base64, total_pages, system_prompt, filename))
        
        # Process with limited concurrency
        batch_results = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(extract_single_page, args): args[0] for args in batch_args}
            
            for future in as_completed(futures):
                page_num = futures[future]
                try:
                    result = future.result()
                    batch_results.append(result)
                    
                    if result['success']:
                        usage = result.get('usage', {})
                        cache_read = usage.get('cache_read_input_tokens', 0)
                        cache_write = usage.get('cache_creation_input_tokens', 0)
                        
                        if cache_read > 0:
                            status = f"📖 CACHE HIT ({cache_read:,} tokens saved)"
                        elif cache_write > 0:
                            status = f"✍️ CACHE WRITE ({cache_write:,} tokens)"
                        else:
                            status = "⚠️ NO CACHE"
                        print(f"  ✓ Page {page_num}: {status}")
                    else:
                        print(f"  ✗ Page {page_num}: {result.get('error', 'Error')[:40]}")
                        
                except Exception as e:
                    print(f"  ✗ Page {page_num}: Exception - {str(e)[:40]}")
                    batch_results.append({'success': False, 'page': page_num, 'error': str(e)})
        
        all_results.extend(batch_results)
        
        # Progress
        elapsed = time.time() - start_time
        done = len(all_results)
        rate = done / elapsed * 60 if elapsed > 0 else 0
        eta = (pages_to_process - done) / (rate / 60) if rate > 0 else 0
        
        print(f"\n  📊 Progress: {done}/{pages_to_process} | Rate: {rate:.1f}/min | ETA: {eta:.1f}min")
        print(f"  💾 Cache: {stats['cache_read_tokens']:,} read, {stats['cache_write_tokens']:,} write")
        
        # Small delay between batches to avoid rate limits
        if batch_idx < num_batches - 1:
            time.sleep(2)
    
    return all_results


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Deep extract with boto3 caching")
    parser.add_argument("--loan-id", type=int, default=27)
    parser.add_argument("--filename", type=str, default="tax_returns_65.pdf")
    parser.add_argument("--prompt-file", type=str, required=True, help="Path to system prompt file")
    parser.add_argument("--start-page", type=int, default=1)
    parser.add_argument("--end-page", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--output", type=str, default=None)
    
    args = parser.parse_args()
    
    print(f"\n{'='*70}")
    print("DEEP EXTRACTION WITH BOTO3 PROMPT CACHING")
    print(f"Model: {MODEL_ID}")
    print(f"Region: {AWS_REGION}")
    print(f"Started: {datetime.now()}")
    print(f"{'='*70}\n")
    
    # Get document path
    doc = execute_one(
        "SELECT file_path FROM document_analysis WHERE loan_id = %s AND filename = %s",
        (args.loan_id, args.filename)
    )
    
    if not doc:
        loan = execute_one('SELECT document_location FROM loans WHERE id = %s', (args.loan_id,))
        if loan:
            pdf_path = os.path.join(loan['document_location'], args.filename)
        else:
            print(f"❌ Document not found")
            sys.exit(1)
    else:
        pdf_path = doc['file_path']
    
    if not os.path.exists(pdf_path):
        print(f"❌ File not found: {pdf_path}")
        sys.exit(1)
    
    print(f"📁 Document: {pdf_path}")
    
    # Load prompt
    with open(args.prompt_file, 'r') as f:
        system_prompt = f.read()
    print(f"📝 Prompt loaded: {len(system_prompt)} chars, ~{len(system_prompt)//4} tokens")
    
    # Process pages
    results = process_pages_with_caching(
        pdf_path=pdf_path,
        system_prompt=system_prompt,
        filename=args.filename,
        start_page=args.start_page,
        end_page=args.end_page,
        batch_size=args.batch_size,
        max_workers=args.workers
    )
    
    # Compile results
    successful = [r for r in results if r.get('success')]
    failed = [r for r in results if not r.get('success')]
    
    # Calculate actual cost
    actual_cost = (
        stats['cache_write_tokens'] * 0.00625 / 1000 +
        stats['cache_read_tokens'] * 0.0005 / 1000 +
        (stats['input_tokens'] - stats['cache_read_tokens'] - stats['cache_write_tokens']) * 0.005 / 1000 +
        stats['output_tokens'] * 0.025 / 1000
    )
    
    final_output = {
        "filename": args.filename,
        "loan_id": args.loan_id,
        "pages_processed": len(results),
        "pages_successful": len(successful),
        "pages_failed": len(failed),
        "processing_date": datetime.now().isoformat(),
        "model": MODEL_ID,
        "token_usage": dict(stats),
        "estimated_cost": f"${actual_cost:.2f}",
        "pages": [r.get('data') for r in successful if r.get('data')],
        "failed_pages": [{"page": r['page'], "error": r.get('error')} for r in failed]
    }
    
    # Save output
    output_path = args.output or f"/tmp/tax_returns_boto3_{args.loan_id}.json"
    with open(output_path, 'w') as f:
        json.dump(final_output, f, indent=2)
    
    # Summary
    print(f"\n{'='*70}")
    print("EXTRACTION COMPLETE")
    print(f"{'='*70}")
    print(f"  ✅ Successful: {len(successful)}")
    print(f"  ❌ Failed: {len(failed)}")
    print(f"\n  💾 Token Usage:")
    print(f"     Cache writes: {stats['cache_write_tokens']:,}")
    print(f"     Cache reads: {stats['cache_read_tokens']:,}")
    print(f"     Input tokens: {stats['input_tokens']:,}")
    print(f"     Output tokens: {stats['output_tokens']:,}")
    print(f"\n  💰 Estimated cost: ${actual_cost:.2f}")
    print(f"  📁 Output: {output_path}")
    print(f"{'='*70}\n")
    
    return final_output


if __name__ == "__main__":
    main()






