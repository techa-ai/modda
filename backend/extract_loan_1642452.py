"""
MT360 Bulk OCR Data Extraction - Loan 1642452
Extracted from browser on 2025-12-18
"""

import json
from datetime import datetime

# Loan 1642452 - 1008 Data (from screenshot)
loan_1642452_1008 = {
    "loan_number": "9230018836365",
    "loan_file_id": "1642452",
    "document_type": "1008",
    "extraction_timestamp": datetime.now().isoformat(),
    "source": "mt360.com",
    "url": "https://www.mt360.com/Document/Detail/1642452?type=1008",
    
    "fields": {
        # Loan Information
        "Loan Number": "9230018836365",
        "Closing Date": None,  # Not visible in screenshot
        "Borrower(s)": "Afshin Ashtiani",
        "Originator": "James Baron",
        
        # Property Information
        "Property Type": "PUD",
        "Project Classification Fannie Mae Type": "E PUD",
        "Project Name": "MUSTANG LAKES PHASE 3B",
        "Occupancy Status": "Primary Residence",
        "Appraised Value": "$1,165,000.00",
        
        # Loan Details
        "Loan Type": "Conventional",
        "Mort Amortization Type": "Fixed-Rate Monthly Payments",
        "Loan Purpose Type": "No Cash-Out Refinance (Freddie)",
        "Mort Original Loan Amount": "$904,140.00",
        "Mort Initial Pand I Payment Amount": "$6,872.12",
        "Mort Interest Rate": "8.37500%",
        "Mort Loan Term Months": "360",
        "Buydown": "False",
        "Mort This Lien Position First": "True",
        "Second Mort Present Indicator": "False",
        
        # Borrower Info
        "Borrower Type": "Borrower",
        "Borrower Base Income Amount": "$27,768.27",
        "Borrower Total Income Amount": "$27,768.27",
        "CoBorrower Type": "CoBorrower",
        "CoBorrower Total Income Amount": "$0.00",
        
        # Underwriting Info
        "Combined Total Income Amount": "$27,768.27",
        "Proposed Monthly Hazard Insurance Amount": "$400.42",
        "Proposed Monthly Taxes Amount": "$1,878.49",
        "Proposed Monthly HOA Fees Amount": "$169.00",
        "Proposed Monthly Total Primary Housing Expense Amount": "$9,326.45",
        "Proposed Monthly All Other Monthly Payments Amount": "$1,521.00",
        "Proposed Monthly Total Monthly Payments Amount": "$10,847.45",
        "Borrower Funds To Close Verified Assets Amount": "$40,284.53",
        "Borrower Funds To Close Number Of Months Reserves": "4"
    },
    
    "extraction_notes": "Data extracted from MT360 1008 Details page screenshot"
}

# Save to file
output_file = "/Users/sunny/Applications/bts/jpmorgan/mortgage/modda/outputs/mt360_bulk_scrape/scraped_data/loan_1642452_1008.json"

import os
os.makedirs(os.path.dirname(output_file), exist_ok=True)

with open(output_file, 'w') as f:
    json.dump(loan_1642452_1008, f, indent=2)

print(f"✓ Loan 1642452 1008 data saved to: {output_file}")
print(f"Total fields extracted: {len(loan_1642452_1008['fields'])}")


