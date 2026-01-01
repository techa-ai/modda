#!/usr/bin/env python3
"""
Stage 1 - Run All Step 1 Substeps
Executes all three substeps in sequence for a given loan

Substeps:
1. 1_1_1: Analyze PDF structure and table detection
2. 1_1_2: Generate detailed statistics
3. 1_1_3: Categorize files by extraction strategy

All outputs saved to: backend/stage1/output/<loan_id>/
"""

import sys
import subprocess
from pathlib import Path


def run_all_steps(loan_folder, sample_pages=3):
    """Run all Stage 1 analysis steps"""
    
    # Extract loan_id
    loan_path = Path(loan_folder)
    if not loan_path.exists():
        print(f"❌ Error: Loan folder not found: {loan_folder}")
        return False
    
    loan_id = loan_path.name
    script_dir = Path(__file__).parent
    output_dir = script_dir / "output" / loan_id
    
    print("\n" + "="*80)
    print(f"🚀 STAGE 1: PDF STRUCTURE ANALYSIS - {loan_id}")
    print("="*80 + "\n")
    
    # Step 1 Substep 1: Analyze PDF structure
    print("📊 Step 1.1.1: Analyzing PDF structure and detecting tables...")
    print("-" * 80)
    try:
        result = subprocess.run(
            ["python3", str(script_dir / "1_1_1_analyze_pdf_structure.py"), 
             loan_folder, str(sample_pages)],
            check=True,
            capture_output=False
        )
        print(f"✅ Step 1.1.1 complete: {output_dir}/1_1_1_analysis.json\n")
    except subprocess.CalledProcessError as e:
        print(f"❌ Step 1.1.1 failed: {e}")
        return False
    
    # Step 1 Substep 2: Generate statistics
    print("\n📈 Step 1.1.2: Generating detailed statistics...")
    print("-" * 80)
    try:
        result = subprocess.run(
            ["python3", str(script_dir / "1_1_2_visualize_results.py"), 
             loan_id],
            check=True,
            capture_output=False
        )
        print(f"✅ Step 1.1.2 complete: {output_dir}/1_1_2_statistics.json\n")
    except subprocess.CalledProcessError as e:
        print(f"❌ Step 1.1.2 failed: {e}")
        return False
    
    # Step 1 Substep 3: Categorize files
    print("\n📋 Step 1.1.3: Categorizing files by extraction strategy...")
    print("-" * 80)
    try:
        result = subprocess.run(
            ["python3", str(script_dir / "1_1_3_list_by_category.py"), 
             loan_id],
            check=True,
            capture_output=False
        )
        print(f"✅ Step 1.1.3 complete: {output_dir}/1_1_3_categories.json\n")
    except subprocess.CalledProcessError as e:
        print(f"❌ Step 1.1.3 failed: {e}")
        return False
    
    # Summary
    print("\n" + "="*80)
    print("✅ ALL SUBSTEPS COMPLETED SUCCESSFULLY!")
    print("="*80)
    print(f"\n📁 Output directory: {output_dir}")
    print(f"   - 1_1_1_analysis.json    (Full PDF structure analysis)")
    print(f"   - 1_1_2_statistics.json  (Summary statistics)")
    print(f"   - 1_1_3_categories.json  (File categorization)")
    print("\n" + "="*80 + "\n")
    
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python run_all_steps.py <loan_folder> [sample_pages]")
        print("\nExample:")
        print("  python run_all_steps.py /path/to/loan_1642451")
        print("  python run_all_steps.py /path/to/loan_1642451 5")
        print("\nThis will run all 3 substeps in sequence:")
        print("  1. Analyze PDF structure (1_1_1)")
        print("  2. Generate statistics (1_1_2)")
        print("  3. Categorize files (1_1_3)")
        print("\nOutputs saved to: backend/stage1/output/<loan_id>/")
        sys.exit(1)
    
    loan_folder = sys.argv[1]
    sample_pages = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    
    success = run_all_steps(loan_folder, sample_pages)
    sys.exit(0 if success else 1)

