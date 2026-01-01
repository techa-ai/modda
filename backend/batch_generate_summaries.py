#!/usr/bin/env python3
"""
Batch Generate Loan Summaries

Generates comprehensive loan summaries for multiple loans using Claude Opus.
"""

import sys
import argparse
from datetime import datetime
from generate_loan_summary import generate_loan_summary
from db import execute_query

def batch_generate_summaries(loan_ids=None, skip_existing=True):
    """Generate summaries for multiple loans"""
    
    # Get loans to process
    if loan_ids:
        loans = execute_query(
            f"SELECT id, loan_number FROM loans WHERE id = ANY(%s) ORDER BY id",
            (loan_ids,)
        )
    else:
        # Get all enriched loans without summaries
        if skip_existing:
            loans = execute_query("""
                SELECT id, loan_number 
                FROM loans 
                WHERE status = 'enriched' 
                AND loan_summary IS NULL
                ORDER BY id
            """)
        else:
            loans = execute_query("""
                SELECT id, loan_number 
                FROM loans 
                WHERE status = 'enriched'
                ORDER BY id
            """)
    
    if not loans:
        print("No loans to process")
        return
    
    print("=" * 100)
    print(f"BATCH LOAN SUMMARY GENERATION")
    print("=" * 100)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Loans to process: {len(loans)}")
    print()
    
    results = {
        'success': [],
        'failed': []
    }
    
    for i, loan in enumerate(loans, 1):
        loan_id = loan['id']
        loan_number = loan['loan_number']
        
        print(f"\n{'='*100}")
        print(f"[{i}/{len(loans)}] Processing Loan {loan_id} ({loan_number})")
        print(f"{'='*100}")
        
        try:
            summary = generate_loan_summary(loan_id, dry_run=False)
            
            if summary:
                print(f"✅ SUCCESS - Summary generated ({len(summary):,} characters)")
                results['success'].append({
                    'id': loan_id,
                    'number': loan_number,
                    'length': len(summary)
                })
            else:
                print(f"❌ FAILED - No summary returned")
                results['failed'].append({
                    'id': loan_id,
                    'number': loan_number,
                    'error': 'No summary returned'
                })
                
        except Exception as e:
            print(f"❌ FAILED - Error: {e}")
            results['failed'].append({
                'id': loan_id,
                'number': loan_number,
                'error': str(e)
            })
    
    # Final summary
    print("\n" + "=" * 100)
    print("BATCH SUMMARY GENERATION COMPLETE")
    print("=" * 100)
    print(f"Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print(f"✅ Successful: {len(results['success'])}/{len(loans)}")
    if results['success']:
        total_chars = sum(r['length'] for r in results['success'])
        avg_chars = total_chars / len(results['success'])
        print(f"   Total output: {total_chars:,} characters")
        print(f"   Average: {avg_chars:,.0f} characters per loan")
    
    if results['failed']:
        print(f"\n❌ Failed: {len(results['failed'])}/{len(loans)}")
        for fail in results['failed']:
            print(f"   Loan {fail['id']} ({fail['number']}): {fail['error']}")
    
    print("=" * 100)
    
    return results

def main():
    parser = argparse.ArgumentParser(description='Batch generate loan summaries')
    parser.add_argument('--loan-ids', type=int, nargs='+', help='Specific loan IDs to process')
    parser.add_argument('--all', action='store_true', help='Process all enriched loans')
    parser.add_argument('--regenerate', action='store_true', help='Regenerate existing summaries')
    
    args = parser.parse_args()
    
    skip_existing = not args.regenerate
    
    batch_generate_summaries(
        loan_ids=args.loan_ids,
        skip_existing=skip_existing
    )

if __name__ == "__main__":
    main()






