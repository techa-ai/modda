"""
MT360 Systematic Data Extractor
Extracts ALL available document data from MT360 for database loading
"""

import json
from datetime import datetime
from pathlib import Path

# All 15 loans with corrected loan ID (1439728, not 1642453)
LOANS = [
    "1642451", "1642452", "1642450", "1642448", "1642449",
    "1475076", "1584069", "1598638", "1579510", "1597233",
    "1528996", "1448202", "1573326", "1439728", "1642453"
]

DOC_TYPES = ["1008", "URLA", "Note", "LoanEstimate", "ClosingDisclosure", "CreditReport"]

def extract_data_from_screenshot(screenshot_path):
    """
    Extract data from screenshot - to be implemented with OCR
    For now, returns placeholder structure
    """
    return {
        "extraction_method": "manual_screenshot_review",
        "fields": {},
        "notes": "Requires OCR or manual field extraction"
    }

def generate_extraction_urls():
    """Generate all 90 URLs for systematic extraction"""
    urls = []
    for loan_id in LOANS:
        for doc_type in DOC_TYPES:
            urls.append({
                "loan_id": loan_id,
                "doc_type": doc_type,
                "url": f"https://www.mt360.com/Document/Detail/{loan_id}?type={doc_type}",
                "output_file": f"loan_{loan_id}_{doc_type}.json"
            })
    return urls

def main():
    output_dir = Path("/Users/sunny/Applications/bts/jpmorgan/mortgage/modda/outputs/mt360_complete_extraction/data")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    urls = generate_extraction_urls()
    
    print("=" * 80)
    print("MT360 SYSTEMATIC EXTRACTION PLAN")
    print("=" * 80)
    print(f"\nTotal URLs to process: {len(urls)}")
    print(f"Output directory: {output_dir}")
    print("\nExtraction URLs:\n")
    
    for i, url_info in enumerate(urls[:10], 1):  # Show first 10
        print(f"{i}. Loan {url_info['loan_id']} - {url_info['doc_type']}")
        print(f"   {url_info['url']}")
    
    print(f"\n... and {len(urls) - 10} more")
    
    # Save URLs to file for reference
    urls_file = output_dir.parent / "extraction_urls.json"
    with open(urls_file, 'w') as f:
        json.dump(urls, f, indent=2)
    
    print(f"\n✓ URLs saved to: {urls_file}")
    print("\nReady for browser-based systematic extraction!")

if __name__ == "__main__":
    main()


