#!/usr/bin/env python3
"""
Batch Property Value & CLTV Verification
Runs property verification for all loans in the system.
"""

import sys
from db import execute_query
from summary_s4v_verify_property_value import main as verify_property_main


def batch_verify_property():
    """Run property verification for all loans."""
    print("=" * 80)
    print("🏠 BATCH PROPERTY VALUE & CLTV VERIFICATION")
    print("=" * 80)
    
    # Get all loan IDs
    loans = execute_query('SELECT DISTINCT loan_id FROM loan_profiles ORDER BY loan_id')
    
    if not loans:
        print("❌ No loans found in the system")
        return
    
    print(f"\n📊 Found {len(loans)} loans to process\n")
    
    results = {
        'success': [],
        'failed': [],
        'skipped': []
    }
    
    for idx, loan in enumerate(loans, 1):
        loan_id = loan['loan_id']
        
        print(f"\n{'='*80}")
        print(f"Processing Loan {loan_id} ({idx}/{len(loans)})")
        print(f"{'='*80}")
        
        try:
            # Run verification
            success = verify_property_main(loan_id)
            
            if success:
                results['success'].append(loan_id)
                print(f"✅ Loan {loan_id}: Property verification completed successfully")
            else:
                results['skipped'].append(loan_id)
                print(f"⚠️  Loan {loan_id}: Skipped (no property documents)")
                
        except Exception as e:
            results['failed'].append(loan_id)
            print(f"❌ Loan {loan_id}: Failed with error: {e}")
            import traceback
            traceback.print_exc()
    
    # Print summary
    print("\n" + "=" * 80)
    print("📊 BATCH VERIFICATION SUMMARY")
    print("=" * 80)
    print(f"✅ Successful: {len(results['success'])} loans")
    if results['success']:
        print(f"   {', '.join(map(str, results['success']))}")
    
    print(f"\n⚠️  Skipped: {len(results['skipped'])} loans")
    if results['skipped']:
        print(f"   {', '.join(map(str, results['skipped']))}")
    
    print(f"\n❌ Failed: {len(results['failed'])} loans")
    if results['failed']:
        print(f"   {', '.join(map(str, results['failed']))}")
    
    print("\n" + "=" * 80)
    print("✨ Batch verification complete!")
    print("=" * 80)


if __name__ == "__main__":
    batch_verify_property()




