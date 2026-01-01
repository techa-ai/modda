"""
MT360 Browser-Based Data Extractor
Systematically extracts data from all 90 document-loan combinations
"""

import json
from datetime import datetime
from pathlib import Path

# Output directory
OUTPUT_DIR = Path("/Users/sunny/Applications/bts/jpmorgan/mortgage/modda/outputs/mt360_complete_extraction/data")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def extract_loan_1642451_urla():
    """
    Extract URLA data for loan 1642451 (from screenshot)
    """
    data = {
        "loan_file_id": "1642451",
        "loan_number": "105742610",
        "document_type": "URLA",
        "extraction_timestamp": datetime.now().isoformat(),
        "source": "mt360.com",
        "url": "https://www.mt360.com/Document/Detail/1642451?type=URLA",
        "has_data": True,
        
        "borrower_information": {
            "borrower_type": "Borrower",
            "name": "ROBERT M DUGAN",
            "ssn": "018-44-0380",
            "date_of_birth": "2/1/1953",
            "citizenship": "U.S. Citizen",
            "marital_status": "Unmarried",
            "home_phone_number": "(239) 285-4379",
            "reside_years": "25",
            "house_classification": "Own",
            "mailing_address_different": "True",
            "total_other_income": "$0.00",
            "loan_amount": "$115,000.00",
            "loan_purpose": "Other",
            "property_county": "Collier",
            "number_of_units": "1",
            "occupancy_status": "Primary Residence",
            "current_subject_address": "1821 CANBY COURT MARCO ISLAND, FL 34145",
            "property_subject_address": "1821 CANBY COURT MARCO ISLAND, EL 34145"
        },
        
        "declarations": {
            "will_occupy_as_primary_residence": "True",
            "had_ownership_interest_in_another_property": "False",
            "borrowing_undisclosed_money": "False",
            "party_of_undisclosed_debt": "False",
            "outstanding_judgements": "False",
            "delinquent_or_in_default_on_federal_debt": "False",
            "party_in_lawsuit": "False",
            "conveyed_title_in_lieu_of_foreclosure": "False",
            "property_foreclosed": "False",
            "declared_bankruptcy": "False",
            "loan_foreclosure_or_judgement": "False"
        },
        
        "demographic_information": {
            "is_hispanic_or_latino": "False",
            "is_not_hispanic_or_latino": "True",
            "does_not_wish_to_provide_ethnicity": "False",
            "is_american_indian_or_alaskan_native": "False",
            "is_asian": "False",
            "is_black_or_african_american": "False"
        },
        
        "extraction_notes": "Full URLA data extracted from MT360 browser page"
    }
    
    output_file = OUTPUT_DIR / "loan_1642451_URLA.json"
    with open(output_file, 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"✓ Saved: {output_file}")
    return data

def create_extraction_tracker():
    """Create a tracker file to monitor progress"""
    tracker = {
        "extraction_started": datetime.now().isoformat(),
        "total_documents": 90,
        "extracted": 0,
        "has_data": 0,
        "no_data": 0,
        "errors": 0,
        "loans": {}
    }
    
    tracker_file = OUTPUT_DIR.parent / "extraction_tracker.json"
    with open(tracker_file, 'w') as f:
        json.dump(tracker, f, indent=2)
    
    return tracker_file

if __name__ == "__main__":
    print("="*80)
    print("MT360 SYSTEMATIC DATA EXTRACTION - STARTING")
    print("="*80)
    
    # Create tracker
    tracker_file = create_extraction_tracker()
    print(f"\n✓ Tracker created: {tracker_file}")
    
    # Extract first known data
    print("\nExtracting Loan 1642451 - URLA...")
    data = extract_loan_1642451_urla()
    print(f"  Fields extracted: {len(data.get('borrower_information', {}))} + declarations + demographics")
    
    print("\n✓ Extraction infrastructure ready!")
    print("  Continue with browser-based extraction for remaining 89 documents...")


