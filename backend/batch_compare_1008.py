#!/usr/bin/env python3
"""
Batch Comparison Script for Multiple 1008 Forms
Run Claude Opus 4.5 vs Llama 4 Maverick 17B comparison across multiple loans
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime
import glob

from compare_opus_vs_llama import run_comparison


def find_1008_forms(base_dir: str = 'public/loans') -> list:
    """Find all 1008 forms across all loan folders"""
    
    print("\n🔍 Searching for 1008 forms...")
    
    base_path = Path(base_dir)
    forms_found = []
    
    # Search pattern for 1008 forms
    patterns = [
        '**/1008*final*.pdf',
        '**/1008*.pdf'
    ]
    
    for pattern in patterns:
        for pdf_path in base_path.glob(pattern):
            loan_folder = pdf_path.parent.name
            forms_found.append({
                'loan_id': loan_folder,
                'file_path': str(pdf_path),
                'file_name': pdf_path.name
            })
    
    # Deduplicate by file path
    unique_forms = {form['file_path']: form for form in forms_found}
    forms_found = list(unique_forms.values())
    
    print(f"✓ Found {len(forms_found)} 1008 form(s)")
    for form in forms_found:
        print(f"  - {form['loan_id']}: {form['file_name']}")
    
    return forms_found


def run_batch_comparison(
    forms: list = None,
    base_dir: str = 'public/loans',
    output_dir: str = 'outputs/model_comparison',
    max_forms: int = None
):
    """Run comparison on multiple 1008 forms"""
    
    print("\n" + "="*80)
    print("🎯 BATCH COMPARISON: Claude Opus 4.5 vs Llama Maverick 17B")
    print("="*80)
    
    # Find forms if not provided
    if forms is None:
        forms = find_1008_forms(base_dir)
    
    if not forms:
        print("❌ No 1008 forms found!")
        return
    
    # Limit number of forms if specified
    if max_forms:
        forms = forms[:max_forms]
        print(f"\n⚠️  Limited to first {max_forms} form(s)")
    
    print(f"\n📋 Will process {len(forms)} form(s)")
    
    # Results tracking
    results = {
        'timestamp': datetime.now().isoformat(),
        'total_forms': len(forms),
        'comparisons': []
    }
    
    # Run comparison on each form
    for i, form in enumerate(forms, 1):
        print("\n" + "="*80)
        print(f"📄 FORM {i}/{len(forms)}: {form['loan_id']}")
        print("="*80)
        
        try:
            # Create loan-specific output directory
            loan_output_dir = os.path.join(output_dir, form['loan_id'])
            
            # Run comparison
            comparison_result = run_comparison(
                form['file_path'],
                loan_output_dir
            )
            
            # Track results
            results['comparisons'].append({
                'loan_id': form['loan_id'],
                'file_path': form['file_path'],
                'success': True,
                'files': comparison_result['files'],
                'performance': comparison_result['comparison'].get('performance', {}),
                'accuracy': comparison_result['comparison'].get('accuracy', {})
            })
            
        except Exception as e:
            print(f"\n❌ Error processing {form['loan_id']}: {e}")
            results['comparisons'].append({
                'loan_id': form['loan_id'],
                'file_path': form['file_path'],
                'success': False,
                'error': str(e)
            })
    
    # Generate summary report
    generate_summary_report(results, output_dir)
    
    return results


def generate_summary_report(results: dict, output_dir: str):
    """Generate summary report across all comparisons"""
    
    print("\n" + "="*80)
    print("📊 GENERATING SUMMARY REPORT")
    print("="*80)
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    summary_file = output_path / f"batch_summary_{timestamp}.json"
    report_file = output_path / f"batch_summary_{timestamp}.md"
    
    # Save JSON summary
    with open(summary_file, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"  ✓ Saved JSON: {summary_file}")
    
    # Generate markdown summary
    md_report = generate_summary_markdown(results)
    with open(report_file, 'w') as f:
        f.write(md_report)
    print(f"  ✓ Saved report: {report_file}")
    
    # Print summary to console
    print_summary_to_console(results)


def generate_summary_markdown(results: dict) -> str:
    """Generate markdown summary report"""
    
    comparisons = results.get('comparisons', [])
    successful = [c for c in comparisons if c.get('success')]
    failed = [c for c in comparisons if not c.get('success')]
    
    report = f"""# Batch Comparison Summary Report

**Timestamp:** {results.get('timestamp')}  
**Total Forms:** {results.get('total_forms', 0)}  
**Successful:** {len(successful)}  
**Failed:** {len(failed)}

---

## Overall Results

| Loan ID | Claude Duration | Llama Duration | Speed Winner | Accuracy Rate |
|---------|-----------------|----------------|--------------|---------------|
"""
    
    for comp in successful:
        loan_id = comp.get('loan_id', 'N/A')
        perf = comp.get('performance', {})
        acc = comp.get('accuracy', {})
        
        claude_dur = perf.get('claude_duration_sec', 0)
        llama_dur = perf.get('llama_duration_sec', 0)
        winner = perf.get('speed_winner', 'N/A')
        accuracy = acc.get('critical_field_match_rate', 0)
        
        report += f"| {loan_id} | {claude_dur:.2f}s | {llama_dur:.2f}s | {winner.upper()} | {accuracy:.1f}% |\n"
    
    # Statistics
    if successful:
        claude_durations = [c.get('performance', {}).get('claude_duration_sec', 0) for c in successful]
        llama_durations = [c.get('performance', {}).get('llama_duration_sec', 0) for c in successful]
        accuracies = [c.get('accuracy', {}).get('critical_field_match_rate', 0) for c in successful]
        
        avg_claude = sum(claude_durations) / len(claude_durations)
        avg_llama = sum(llama_durations) / len(llama_durations)
        avg_accuracy = sum(accuracies) / len(accuracies) if accuracies else 0
        
        report += f"""
---

## Statistics

### Performance
- **Average Claude Duration:** {avg_claude:.2f}s
- **Average Llama Duration:** {avg_llama:.2f}s
- **Overall Speed Winner:** {'Claude' if avg_claude < avg_llama else 'Llama'}

### Accuracy
- **Average Critical Field Match Rate:** {avg_accuracy:.1f}%

"""
    
    if failed:
        report += f"""
---

## Failed Comparisons

"""
        for comp in failed:
            report += f"- **{comp.get('loan_id')}**: {comp.get('error', 'Unknown error')}\n"
    
    report += """
---

## Detailed Reports

Individual comparison reports are available in the respective loan folders.

"""
    
    return report


def print_summary_to_console(results: dict):
    """Print summary to console"""
    
    comparisons = results.get('comparisons', [])
    successful = [c for c in comparisons if c.get('success')]
    failed = [c for c in comparisons if not c.get('success')]
    
    print("\n" + "="*80)
    print("📊 BATCH SUMMARY")
    print("="*80)
    print(f"Total Forms: {results.get('total_forms', 0)}")
    print(f"Successful: {len(successful)}")
    print(f"Failed: {len(failed)}")
    
    if successful:
        print("\n🏆 Results:")
        
        claude_wins = 0
        llama_wins = 0
        
        for comp in successful:
            loan_id = comp.get('loan_id')
            perf = comp.get('performance', {})
            acc = comp.get('accuracy', {})
            
            winner = perf.get('speed_winner', 'N/A')
            if winner == 'claude':
                claude_wins += 1
            elif winner == 'llama':
                llama_wins += 1
            
            accuracy = acc.get('critical_field_match_rate', 0)
            
            print(f"  {loan_id}:")
            print(f"    Speed: {winner.upper()}")
            print(f"    Accuracy: {accuracy:.1f}%")
        
        print(f"\n⚡ Speed Winner Count:")
        print(f"  Claude: {claude_wins}")
        print(f"  Llama: {llama_wins}")
    
    if failed:
        print(f"\n❌ Failed Comparisons:")
        for comp in failed:
            print(f"  - {comp.get('loan_id')}: {comp.get('error')}")


def main():
    """Main entry point"""
    
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Batch comparison of Claude Opus 4.5 vs Llama Maverick 17B'
    )
    parser.add_argument(
        '--base-dir',
        default='public/loans',
        help='Base directory containing loan folders'
    )
    parser.add_argument(
        '--output-dir',
        default='outputs/model_comparison',
        help='Output directory for results'
    )
    parser.add_argument(
        '--max-forms',
        type=int,
        help='Maximum number of forms to process'
    )
    parser.add_argument(
        '--loan-ids',
        nargs='+',
        help='Specific loan IDs to process (e.g., loan_1579510)'
    )
    
    args = parser.parse_args()
    
    # Find forms
    if args.loan_ids:
        forms = []
        for loan_id in args.loan_ids:
            # Find 1008 form for this loan
            loan_dir = Path(args.base_dir) / loan_id
            if loan_dir.exists():
                pattern = str(loan_dir / '1008*.pdf')
                matches = glob.glob(pattern)
                if matches:
                    forms.append({
                        'loan_id': loan_id,
                        'file_path': matches[0],
                        'file_name': Path(matches[0]).name
                    })
        
        if not forms:
            print(f"❌ No 1008 forms found for specified loan IDs")
            sys.exit(1)
    else:
        forms = None  # Will find all forms
    
    # Run batch comparison
    run_batch_comparison(
        forms=forms,
        base_dir=args.base_dir,
        output_dir=args.output_dir,
        max_forms=args.max_forms
    )


if __name__ == '__main__':
    main()




