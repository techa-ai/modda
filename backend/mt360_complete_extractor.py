"""
MT360 Comprehensive Data Extractor
Checks all 6 document types for all 15 loans and extracts available data to JSON
"""

import json
import time
from datetime import datetime
from pathlib import Path

# Corrected loan list (1439728, NOT 1642453)
ALL_LOANS = [
    {"loan_number": "105742610", "loan_file_id": "1642451"},
    {"loan_number": "9230018836365", "loan_file_id": "1642452"},
    {"loan_number": "1225421582", "loan_file_id": "1642450"},
    {"loan_number": "1457382910", "loan_file_id": "1642448"},
    {"loan_number": "924087025", "loan_file_id": "1642449"},
    {"loan_number": "980121258806", "loan_file_id": "1475076"},
    {"loan_number": "1225501664", "loan_file_id": "1584069"},
    {"loan_number": "2046007999", "loan_file_id": "1598638"},
    {"loan_number": "2052700869", "loan_file_id": "1579510"},
    {"loan_number": "1551504333", "loan_file_id": "1597233"},
    {"loan_number": "1525185423", "loan_file_id": "1528996"},
    {"loan_number": "4250489570", "loan_file_id": "1448202"},
    {"loan_number": "819912", "loan_file_id": "1573326"},
    {"loan_number": "1525070964", "loan_file_id": "1439728"},  # CORRECTED
    {"loan_number": "2501144775", "loan_file_id": "1642453"},
]

DOCUMENT_TYPES = ["1008", "URLA", "Note", "LoanEstimate", "ClosingDisclosure", "CreditReport", "1004"]

# Output directory
OUTPUT_DIR = Path("/Users/sunny/Applications/bts/jpmorgan/mortgage/modda/outputs/mt360_complete_extraction")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def create_extraction_manifest():
    """Create a manifest of all URLs to check"""
    manifest = {
        "extraction_date": datetime.now().isoformat(),
        "total_loans": len(ALL_LOANS),
        "document_types": DOCUMENT_TYPES,
        "total_combinations": len(ALL_LOANS) * len(DOCUMENT_TYPES),
        "loans": []
    }
    
    for loan in ALL_LOANS:
        loan_data = {
            "loan_number": loan["loan_number"],
            "loan_file_id": loan["loan_file_id"],
            "documents": []
        }
        
        for doc_type in DOCUMENT_TYPES:
            url = f"https://www.mt360.com/Document/Detail/{loan['loan_file_id']}?type={doc_type}"
            loan_data["documents"].append({
                "type": doc_type,
                "url": url,
                "checked": False,
                "has_data": None,
                "extracted": False,
                "output_file": f"loan_{loan['loan_file_id']}_{doc_type}.json"
            })
        
        manifest["loans"].append(loan_data)
    
    # Save manifest
    manifest_file = OUTPUT_DIR / "extraction_manifest.json"
    with open(manifest_file, 'w') as f:
        json.dump(manifest, f, indent=2)
    
    print(f"✓ Extraction manifest created: {manifest_file}")
    print(f"  Total URLs to process: {manifest['total_combinations']}")
    return manifest

if __name__ == "__main__":
    print("="*80)
    print("MT360 COMPREHENSIVE DATA EXTRACTOR")
    print("="*80)
    print(f"\nTotal Loans: {len(ALL_LOANS)}")
    print(f"Document Types: {len(DOCUMENT_TYPES)}")
    print(f"Total Combinations: {len(ALL_LOANS) * len(DOCUMENT_TYPES)}")
    print(f"\nOutput Directory: {OUTPUT_DIR}")
    print("\n" + "="*80)
    
    manifest = create_extraction_manifest()
    
    print("\n✓ Manifest ready for browser-based extraction")
    print("\nNext steps:")
    print("1. Use browser automation to navigate each URL")
    print("2. Check if data is available (look for 'No X Information Available' or 'Error')")
    print("3. Extract visible data fields")
    print("4. Save to JSON files")
    print("5. Update manifest with results")


