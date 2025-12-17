#!/usr/bin/env python3
"""
Step 5c: Large Document Deep Extraction with Prompt Caching

This step handles documents that were skipped by step5 due to size (>50 pages).
Uses prompt caching for 90% cost savings on the system prompt.

Pipeline Order:
1. step5_deep_extraction.py - Regular deep extraction (skips large docs)
2. step5b_retry_failed_extraction.py - Retry failed small documents
3. step5c_large_doc_extraction.py - THIS SCRIPT: Large docs with caching

Features:
- Prompt caching for 90% savings on system prompt tokens
- Optimized compact output format for reduced output costs
- Actual cost tracking and reporting
- Resume capability (skips already-extracted pages)

Pricing (Claude Opus 4.5 on Bedrock):
- Input: $0.005 / 1K tokens
- Output: $0.025 / 1K tokens (5x more expensive!)
- Cache write: $0.00625 / 1K tokens (first request)
- Cache read: $0.0005 / 1K tokens (90% savings!)

Usage:
    # Process specific document
    python step5c_large_doc_extraction.py --loan-id 27 --filename tax_returns_65.pdf
    
    # Process all large documents for a loan
    python step5c_large_doc_extraction.py --loan-id 27 --all-large
    
    # Dry run to see costs
    python step5c_large_doc_extraction.py --loan-id 27 --filename tax_returns_65.pdf --dry-run
"""

import os
import sys
import json
import time
import base64
import requests
import logging
import argparse
from io import BytesIO
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from pdf2image import convert_from_path
from PyPDF2 import PdfReader
from db import execute_query, execute_one, get_db_connection

# Import from existing bedrock_config
from bedrock_config import BEDROCK_API_KEY, BEDROCK_ENDPOINT, BEDROCK_MODELS

# Model configuration
MODEL_ID = BEDROCK_MODELS.get('claude-opus-4-5', 'global.anthropic.claude-opus-4-5-20251101-v1:0')

# Pricing (per 1K tokens)
PRICING = {
    'input': 0.005,
    'output': 0.025,
    'cache_write': 0.00625,
    'cache_read': 0.0005
}

# Default prompt path
DEFAULT_PROMPT_PATH = os.path.join(os.path.dirname(__file__), 'tax_returns_optimized_prompt.txt')

# Logging
LOG_DIR = "/tmp/modda_pipeline"
os.makedirs(LOG_DIR, exist_ok=True)

# Thread-safe stats
stats_lock = Lock()
stats = {
    'pages_processed': 0,
    'pages_successful': 0,
    'cache_read_tokens': 0,
    'cache_write_tokens': 0,
    'input_tokens': 0,
    'output_tokens': 0,
    'errors': 0
}


def setup_logging(loan_id, filename):
    """Setup logging for this run"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_filename = filename.replace('/', '_').replace('.', '_')
    log_file = os.path.join(LOG_DIR, f"step5c_large_doc_{loan_id}_{safe_filename}_{timestamp}.log")
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)s | %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__), log_file


def convert_page_to_base64(image):
    """Convert PIL Image to base64 string"""
    buffered = BytesIO()
    image.save(buffered, format="JPEG", quality=85)
    return base64.b64encode(buffered.getvalue()).decode('utf-8')


def invoke_bedrock_with_cache(system_prompt: str, user_content: list, max_tokens: int = 1500, use_cache: bool = True, max_retries: int = 5):
    """
    Invoke Bedrock with prompt caching enabled.
    Cache persists for 5 minutes, saving 90% on repeated calls.
    """
    
    if use_cache:
        system = [{
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral"}
        }]
    else:
        system = system_prompt
    
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "temperature": 0,
        "system": system,
        "messages": [{"role": "user", "content": user_content}]
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {BEDROCK_API_KEY}",
        "Accept": "application/json"
    }
    
    url = f"{BEDROCK_ENDPOINT}/model/{MODEL_ID}/invoke"
    
    for attempt in range(max_retries):
        try:
            response = requests.post(url, headers=headers, json=body, timeout=600)
            
            if response.status_code == 429:
                wait_time = min(2 ** attempt * 2, 60)
                time.sleep(wait_time)
                continue
            
            response.raise_for_status()
            result = response.json()
            
            if 'content' in result and len(result['content']) > 0:
                text = result['content'][0]['text']
                usage = result.get('usage', {})
                
                with stats_lock:
                    stats['cache_read_tokens'] += usage.get('cache_read_input_tokens', 0)
                    stats['cache_write_tokens'] += usage.get('cache_creation_input_tokens', 0)
                    stats['input_tokens'] += usage.get('input_tokens', 0)
                    stats['output_tokens'] += usage.get('output_tokens', 0)
                
                return text, usage
            else:
                raise ValueError(f"Unexpected response format: {result}")
                
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                if e.response.status_code == 429 and attempt < max_retries - 1:
                    wait_time = min(2 ** attempt * 2, 60)
                    time.sleep(wait_time)
                    continue
            raise Exception(f"Bedrock API error: {e}")
    
    raise Exception(f"Max retries ({max_retries}) exceeded")


def extract_single_page(args):
    """Extract data from a single page using cached prompt"""
    page_num, image_base64, total_pages, custom_prompt, filename = args
    
    user_content = [
        {"type": "text", "text": f"Extract data from page {page_num} of {total_pages} of '{filename}'. Return compact JSON only."},
        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_base64}}
    ]
    
    try:
        response_text, usage = invoke_bedrock_with_cache(
            system_prompt=custom_prompt,
            user_content=user_content,
            max_tokens=1500,  # Compact output
            use_cache=True
        )
        
        # Parse JSON response
        try:
            if '```json' in response_text:
                response_text = response_text.split('```json')[1].split('```')[0].strip()
            elif '```' in response_text:
                response_text = response_text.split('```')[1].split('```')[0].strip()
            
            data = json.loads(response_text)
            data['page_number'] = page_num
        except json.JSONDecodeError:
            data = {'raw_text': response_text, 'page_number': page_num}
        
        with stats_lock:
            stats['pages_processed'] += 1
            stats['pages_successful'] += 1
        
        return {'success': True, 'page': page_num, 'data': data, 'usage': usage}
        
    except Exception as e:
        with stats_lock:
            stats['pages_processed'] += 1
            stats['errors'] += 1
        return {'success': False, 'page': page_num, 'error': str(e)}


def calculate_actual_cost():
    """Calculate actual cost from tracked tokens"""
    cost = (
        stats['cache_write_tokens'] * PRICING['cache_write'] / 1000 +
        stats['cache_read_tokens'] * PRICING['cache_read'] / 1000 +
        stats['input_tokens'] * PRICING['input'] / 1000 +
        stats['output_tokens'] * PRICING['output'] / 1000
    )
    return cost


def process_document(pdf_path: str, filename: str, custom_prompt: str, 
                    start_page: int = 1, end_page: int = None,
                    batch_size: int = 50, max_workers: int = 5, logger=None,
                    output_dir: str = None):
    """Process all pages of a document with caching"""
    
    reader = PdfReader(pdf_path)
    total_pages = len(reader.pages)
    
    if end_page is None or end_page > total_pages:
        end_page = total_pages
    
    pages_to_process = end_page - start_page + 1
    
    logger.info(f"Processing pages {start_page} to {end_page} ({pages_to_process} pages)")
    
    # Setup output directory for incremental saves
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        logger.info(f"Saving incremental results to: {output_dir}")
    
    # Estimate costs
    prompt_tokens = len(custom_prompt) // 4
    cost_no_cache = (
        prompt_tokens * pages_to_process * PRICING['input'] / 1000 +
        1500 * pages_to_process * PRICING['input'] / 1000 +  # Image
        500 * pages_to_process * PRICING['output'] / 1000
    )
    cost_with_cache = (
        prompt_tokens * PRICING['cache_write'] / 1000 +  # First request
        prompt_tokens * (pages_to_process - 1) * PRICING['cache_read'] / 1000 +  # Cached
        1500 * pages_to_process * PRICING['input'] / 1000 +
        500 * pages_to_process * PRICING['output'] / 1000
    )
    
    logger.info(f"Estimated cost WITHOUT caching: ${cost_no_cache:.2f}")
    logger.info(f"Estimated cost WITH caching: ${cost_with_cache:.2f}")
    logger.info(f"Estimated savings: ${cost_no_cache - cost_with_cache:.2f}")
    
    all_results = []
    start_time = time.time()
    
    num_batches = (pages_to_process + batch_size - 1) // batch_size
    
    for batch_idx in range(num_batches):
        batch_start = start_page + batch_idx * batch_size
        batch_end = min(batch_start + batch_size - 1, end_page)
        
        logger.info(f"Batch {batch_idx + 1}/{num_batches}: Pages {batch_start}-{batch_end}")
        
        # Convert batch pages to images
        batch_images = convert_from_path(
            pdf_path, dpi=150,
            first_page=batch_start, last_page=batch_end
        )
        
        # Prepare arguments for parallel processing
        batch_args = []
        for idx, image in enumerate(batch_images):
            page_num = batch_start + idx
            image_base64 = convert_page_to_base64(image)
            batch_args.append((page_num, image_base64, total_pages, custom_prompt, filename))
        
        # Process batch in parallel
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
                            status = f"CACHE HIT ({cache_read:,} tokens)"
                        elif cache_write > 0:
                            status = f"CACHE WRITE ({cache_write:,} tokens)"
                        else:
                            status = "NO CACHE"
                        logger.info(f"  Page {page_num}: {status}")
                    else:
                        logger.error(f"  Page {page_num}: {result.get('error', 'Unknown')[:50]}")
                        
                except Exception as e:
                    logger.error(f"  Page {page_num}: Exception - {str(e)[:50]}")
                    batch_results.append({'success': False, 'page': page_num, 'error': str(e)})
        
        all_results.extend(batch_results)
        
        # Progress update
        elapsed = time.time() - start_time
        pages_done = len(all_results)
        rate = pages_done / elapsed * 60 if elapsed > 0 else 0
        eta = (pages_to_process - pages_done) / (rate / 60) if rate > 0 else 0
        
        logger.info(f"  Progress: {pages_done}/{pages_to_process} | Rate: {rate:.1f}/min | ETA: {eta:.1f} min")
        logger.info(f"  Cache: reads={stats['cache_read_tokens']:,}, writes={stats['cache_write_tokens']:,}")
        logger.info(f"  Running cost: ${calculate_actual_cost():.2f}")
        
        # Incremental save to file after each batch
        if output_dir:
            batch_file = os.path.join(output_dir, f"batch_{batch_idx + 1:03d}_pages_{batch_start}_{batch_end}.json")
            with open(batch_file, 'w') as f:
                json.dump({
                    'batch': batch_idx + 1,
                    'pages_range': [batch_start, batch_end],
                    'results': batch_results,
                    'stats': dict(stats),
                    'cost': calculate_actual_cost()
                }, f, indent=2, default=str)
            
            # Also save cumulative progress
            progress_file = os.path.join(output_dir, "progress.json")
            with open(progress_file, 'w') as f:
                json.dump({
                    'filename': filename,
                    'total_pages': total_pages,
                    'pages_processed': pages_done,
                    'batches_completed': batch_idx + 1,
                    'total_batches': num_batches,
                    'stats': dict(stats),
                    'cost': calculate_actual_cost(),
                    'elapsed_seconds': elapsed,
                    'rate_per_min': rate,
                    'last_updated': datetime.now().isoformat()
                }, f, indent=2)
            logger.info(f"  Saved batch to: {batch_file}")
    
    # Save final all_results
    if output_dir:
        final_file = os.path.join(output_dir, "all_pages.json")
        with open(final_file, 'w') as f:
            json.dump(all_results, f, indent=2, default=str)
        logger.info(f"Saved all results to: {final_file}")
    
    return all_results


def create_document_summary(pages_data: list, filename: str, custom_prompt: str, logger):
    """Create document-level summary from extracted pages"""
    
    pages_summary = []
    for result in pages_data:
        if result.get('success') and result.get('data'):
            data = result['data']
            summary_data = {k: v for k, v in data.items() if not k.startswith('_')}
            pages_summary.append(summary_data)
    
    summary_system = "You are a tax document analysis expert. Create comprehensive document summaries."
    
    summary_prompt = f"""Create a document summary for "{filename}" ({len(pages_summary)} pages extracted).

Sample data (first 50 pages):
{json.dumps(pages_summary[:50], indent=2, default=str)}

Return JSON with:
1. document_overview: Description and tax years
2. document_types_found: List with counts
3. key_entities: People, orgs, employers with roles
4. financial_summary: Total wages, taxes withheld, etc.
5. tax_years_covered: List of years
6. page_index: Map of page ranges to doc types

Return valid JSON only."""

    user_content = [{"type": "text", "text": summary_prompt}]
    
    logger.info("Creating document summary...")
    start_time = time.time()
    
    response_text, usage = invoke_bedrock_with_cache(
        system_prompt=summary_system,
        user_content=user_content,
        max_tokens=8000,
        use_cache=False
    )
    
    elapsed = time.time() - start_time
    logger.info(f"Document summary created in {elapsed:.1f}s")
    
    try:
        if '```json' in response_text:
            response_text = response_text.split('```json')[1].split('```')[0].strip()
        elif '```' in response_text:
            response_text = response_text.split('```')[1].split('```')[0].strip()
        
        summary = json.loads(response_text)
    except json.JSONDecodeError:
        summary = {"raw_summary": response_text}
    
    return summary


def get_large_documents_needing_extraction(loan_id: int, min_pages: int = 51):
    """Get documents that are large and need extraction"""
    query = """
        SELECT id, filename, file_path, page_count
        FROM document_analysis
        WHERE loan_id = %s
        AND status IN ('unique', 'master', 'active')
        AND page_count >= %s
        AND (individual_analysis IS NULL 
             OR individual_analysis->'document_summary' IS NULL)
        ORDER BY page_count ASC
    """
    return execute_query(query, (loan_id, min_pages))


def save_to_database(doc_id: int, loan_id: int, pages_data: list, summary: dict, logger):
    """Save extraction results to database"""
    
    # Build individual_analysis structure
    individual_analysis = {
        'document_summary': summary,
        'pages': [r.get('data', {}) for r in pages_data if r.get('success')],
        'extraction_metadata': {
            'method': 'step5c_large_doc_cached',
            'model': MODEL_ID,
            'timestamp': datetime.now().isoformat(),
            'pages_extracted': stats['pages_successful'],
            'pages_failed': stats['errors'],
            'token_usage': {
                'cache_read_tokens': stats['cache_read_tokens'],
                'cache_write_tokens': stats['cache_write_tokens'],
                'input_tokens': stats['input_tokens'],
                'output_tokens': stats['output_tokens']
            },
            'actual_cost': calculate_actual_cost()
        }
    }
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE document_analysis 
                SET individual_analysis = %s
                WHERE id = %s
            """, (json.dumps(individual_analysis), doc_id))
        conn.commit()
        logger.info(f"Saved to database (doc_id: {doc_id})")
    finally:
        conn.close()


def process_single_document(loan_id: int, filename: str, prompt_path: str,
                           batch_size: int, workers: int, start_page: int, 
                           output_dir: str, dry_run: bool, logger):
    """Process a single large document"""
    
    # Get document info
    doc = execute_one(
        "SELECT id, file_path, page_count FROM document_analysis WHERE loan_id = %s AND filename = %s",
        (loan_id, filename)
    )
    
    if not doc:
        logger.error(f"Document not found: {filename}")
        return False
    
    pdf_path = doc['file_path']
    doc_id = doc['id']
    page_count = doc['page_count'] or 0
    
    if not os.path.exists(pdf_path):
        logger.error(f"File not found: {pdf_path}")
        return False
    
    logger.info(f"Document: {filename}")
    logger.info(f"Path: {pdf_path}")
    logger.info(f"Pages: {page_count}")
    
    # Load prompt
    if not os.path.exists(prompt_path):
        logger.error(f"Prompt file not found: {prompt_path}")
        return False
    
    with open(prompt_path, 'r') as f:
        custom_prompt = f.read()
    
    prompt_tokens = len(custom_prompt) // 4
    logger.info(f"Prompt: ~{prompt_tokens:,} tokens ({len(custom_prompt):,} chars)")
    
    if dry_run:
        # Calculate estimated costs
        cost_no_cache = (
            prompt_tokens * page_count * PRICING['input'] / 1000 +
            1500 * page_count * PRICING['input'] / 1000 +
            500 * page_count * PRICING['output'] / 1000
        )
        cost_with_cache = (
            prompt_tokens * PRICING['cache_write'] / 1000 +
            prompt_tokens * (page_count - 1) * PRICING['cache_read'] / 1000 +
            1500 * page_count * PRICING['input'] / 1000 +
            500 * page_count * PRICING['output'] / 1000
        )
        logger.info(f"\n=== DRY RUN COST ESTIMATE ===")
        logger.info(f"Pages: {page_count}")
        logger.info(f"Cost without caching: ${cost_no_cache:.2f}")
        logger.info(f"Cost with caching: ${cost_with_cache:.2f}")
        logger.info(f"Savings: ${cost_no_cache - cost_with_cache:.2f} ({(1 - cost_with_cache/cost_no_cache)*100:.0f}%)")
        return True
    
    # Process all pages
    start_time = time.time()
    
    pages_data = process_document(
        pdf_path=pdf_path,
        filename=filename,
        custom_prompt=custom_prompt,
        start_page=start_page,
        batch_size=batch_size,
        max_workers=workers,
        logger=logger,
        output_dir=output_dir
    )
    
    # Create summary
    summary = create_document_summary(pages_data, filename, custom_prompt, logger)
    
    # Save to database
    save_to_database(doc_id, loan_id, pages_data, summary, logger)
    
    # Final stats
    elapsed = time.time() - start_time
    actual_cost = calculate_actual_cost()
    
    logger.info(f"\n{'='*60}")
    logger.info(f"EXTRACTION COMPLETE")
    logger.info(f"{'='*60}")
    logger.info(f"Pages: {stats['pages_successful']}/{stats['pages_processed']} successful")
    logger.info(f"Errors: {stats['errors']}")
    logger.info(f"Time: {elapsed/60:.1f} minutes")
    logger.info(f"Rate: {stats['pages_processed']/elapsed*60:.1f} pages/min")
    logger.info(f"\nToken Usage:")
    logger.info(f"  Cache writes: {stats['cache_write_tokens']:,}")
    logger.info(f"  Cache reads: {stats['cache_read_tokens']:,}")
    logger.info(f"  Input tokens: {stats['input_tokens']:,}")
    logger.info(f"  Output tokens: {stats['output_tokens']:,}")
    logger.info(f"\n💰 ACTUAL COST: ${actual_cost:.2f}")
    
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Step 5c: Large Document Deep Extraction with Prompt Caching"
    )
    parser.add_argument("--loan-id", type=int, required=True, help="Loan ID")
    parser.add_argument("--filename", type=str, help="Specific document filename")
    parser.add_argument("--all-large", action="store_true", help="Process all large docs for loan")
    parser.add_argument("--min-pages", type=int, default=51, help="Min pages for 'large' (default: 51)")
    parser.add_argument("--prompt", type=str, default=DEFAULT_PROMPT_PATH, help="Path to prompt file")
    parser.add_argument("--batch-size", type=int, default=50, help="Batch size (default: 50)")
    parser.add_argument("--workers", type=int, default=5, help="Parallel workers (default: 5)")
    parser.add_argument("--start-page", type=int, default=1, help="Start page (for resume)")
    parser.add_argument("--output-dir", type=str, help="Directory to save incremental results")
    parser.add_argument("--dry-run", action="store_true", help="Show costs without processing")
    
    args = parser.parse_args()
    
    if not args.filename and not args.all_large:
        print("Error: Must specify --filename or --all-large")
        sys.exit(1)
    
    filename_for_log = args.filename or "all_large"
    logger, log_file = setup_logging(args.loan_id, filename_for_log)
    
    logger.info(f"{'='*60}")
    logger.info(f"STEP 5c: LARGE DOCUMENT EXTRACTION WITH CACHING")
    logger.info(f"{'='*60}")
    logger.info(f"Loan ID: {args.loan_id}")
    logger.info(f"Mode: {'Specific file' if args.filename else 'All large documents'}")
    logger.info(f"Prompt: {args.prompt}")
    logger.info(f"Started: {datetime.now()}")
    logger.info(f"Log file: {log_file}")
    
    if args.filename:
        # Auto-generate output dir if not specified
        if not args.output_dir:
            safe_filename = args.filename.replace('.', '_').replace('/', '_')
            args.output_dir = os.path.join(
                os.path.dirname(__file__), 
                'extractions', 
                f'loan_{args.loan_id}_{safe_filename}'
            )
        
        # Process single document
        success = process_single_document(
            loan_id=args.loan_id,
            filename=args.filename,
            prompt_path=args.prompt,
            batch_size=args.batch_size,
            workers=args.workers,
            start_page=args.start_page,
            output_dir=args.output_dir,
            dry_run=args.dry_run,
            logger=logger
        )
        sys.exit(0 if success else 1)
    
    elif args.all_large:
        # Process all large documents
        docs = get_large_documents_needing_extraction(args.loan_id, args.min_pages)
        
        if not docs:
            logger.info("No large documents need extraction")
            sys.exit(0)
        
        logger.info(f"Found {len(docs)} large documents to process:")
        for doc in docs:
            logger.info(f"  - {doc['filename']} ({doc['page_count']} pages)")
        
        if args.dry_run:
            total_pages = sum(d['page_count'] or 0 for d in docs)
            prompt_tokens = len(open(args.prompt).read()) // 4
            
            # Estimate total cost (cache shared across all docs if processed sequentially)
            cost_no_cache = (
                prompt_tokens * total_pages * PRICING['input'] / 1000 +
                1500 * total_pages * PRICING['input'] / 1000 +
                500 * total_pages * PRICING['output'] / 1000
            )
            cost_with_cache = (
                prompt_tokens * PRICING['cache_write'] / 1000 +
                prompt_tokens * (total_pages - 1) * PRICING['cache_read'] / 1000 +
                1500 * total_pages * PRICING['input'] / 1000 +
                500 * total_pages * PRICING['output'] / 1000
            )
            
            logger.info(f"\n=== DRY RUN COST ESTIMATE ===")
            logger.info(f"Total pages: {total_pages}")
            logger.info(f"Cost without caching: ${cost_no_cache:.2f}")
            logger.info(f"Cost with caching: ${cost_with_cache:.2f}")
            logger.info(f"Savings: ${cost_no_cache - cost_with_cache:.2f}")
            sys.exit(0)
        
        # Process each document
        for idx, doc in enumerate(docs):
            logger.info(f"\n{'='*60}")
            logger.info(f"Document {idx + 1}/{len(docs)}: {doc['filename']}")
            logger.info(f"{'='*60}")
            
            # Reset stats for each document
            global stats
            stats = {
                'pages_processed': 0, 'pages_successful': 0,
                'cache_read_tokens': 0, 'cache_write_tokens': 0,
                'input_tokens': 0, 'output_tokens': 0, 'errors': 0
            }
            
            safe_filename = doc['filename'].replace('.', '_').replace('/', '_')
            doc_output_dir = os.path.join(
                os.path.dirname(__file__), 
                'extractions', 
                f'loan_{args.loan_id}_{safe_filename}'
            )
            
            process_single_document(
                loan_id=args.loan_id,
                filename=doc['filename'],
                prompt_path=args.prompt,
                batch_size=args.batch_size,
                workers=args.workers,
                start_page=1,  # Always start from 1 for all-large mode
                output_dir=doc_output_dir,
                dry_run=False,
                logger=logger
            )


if __name__ == "__main__":
    main()



