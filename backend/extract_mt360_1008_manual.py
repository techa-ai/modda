"""
Simple script to extract 1008 data directly from mt360.com browser session
"""

import json
from datetime import datetime

# Manually captured 1008 data from mt360.com for loan 1642451
# Based on the screenshot, here's what we can see:

mt360_1008_data = {
    "loan_id": "1642451",
    "loan_number": "105742610",
    "document_type": "1008",
    "extraction_timestamp": datetime.now().isoformat(),
    "source": "mt360.com",
    "url": "https://www.mt360.com/Document/Detail/1642451?type=1008",
    
    "fields": {
        # From the screenshot of 1008 Details page
        "Loan Number": "105742610",
        "Closing Date": "8/21/2025",
        "Borrower(s)": "Robert M. Dugan",
        "Originator": "RENA BONILLA",
        "Loan Amount": "$115,000.00",
        "Property Type": "1 unit",
        "Occupancy Status": "Primary Residence",
        "Number Of Units": "1",
        "Appraised Value": "$1,619,967.00",
        "Property Rights Type": "Fee Simple",
        "Loan Type": "Conventional",
        "Mort Amortization Type": "Fixed-Rate Monthly Payments",
        "Loan Purpose Type": "Cash-Out Refinance",
        "Mort Original Loan Amount": "$115,000.00",
        "Mort Initial Pand I Payment Amount": "$979.88",
        "Mort Interest Rate": "8.25000%",
        "Mort Loan Term Months": "240",
        "Mort Originator Type": "Seller",
        "Buydown": "False",
        "Mort This Lien Position First": "False",
        "Second Mort Present Indicator": "True",
        "HELOC Balance": "$194,882.00",
        "HELOC Credit": "$194,882.00",
        
        # Borrower Info section
        "Borrower Type": "Borrower",
        "Borrower Base Income Amount": "$30,721.67",
        "CoBorrower Type": "CoBorrower",  # Multiple co-borrowers listed
        
        # Underwriting Info section
        "Combined Total Income Amount": "$30,721.67",
        "Proposed Monthly Hazard Insurance Amount": "$806.25",
        "Proposed Monthly Taxes Amount": "$612.70",
        "Proposed Monthly Total Primary Housing Expense Amount": "$6,624.00",
        "Proposed Monthly All Other Monthly Payments Amount": "$877.00",
        "Borrower Funds To Close Number Of Months Reserves": "0",
        "Borrower Funds To Close Number Of Years Reserves": "0",
        "Borrower Funds To Close Interest Paid Party Contributions Percentage": "0.00000%",
        "Qualifying Ratios Primary House Expense To Income": "21.50340%",
        "Qualifying Ratios Total Obligations To Income": "24.00000%",
        "Qualifying Ratios Debt To Housing Gap Ratio": "0.00000%",
        "LTV Ratios LTV": "7.09900%",
        "LTV Ratios CLTV Wo TLTV": "7.09900%",
        "LTV Ratios HCLTV Wo HTLTV": "19.12900%",
        "Qualifying Note Rate Type": "Note Rate",
        "Qualifying Note Rate Amount": "825.00000%",
        "Level Of Property Review Type": "Exterior Only",
        "Escrow Tand I Indicator": "True",
        "Representative Credit Indicator Score": "820",
        "Supplemental Property Insurance": "$69.42"
    },
    
    "extraction_notes": "Data manually extracted from MT360 1008 Details page screenshot"
}

# Save to JSON file
output_file = "/Users/sunny/Applications/bts/jpmorgan/mortgage/modda/outputs/mt360_validation/mt360_1008_loan_1642451_manual.json"

import os
os.makedirs(os.path.dirname(output_file), exist_ok=True)

with open(output_file, 'w') as f:
    json.dump(mt360_1008_data, f, indent=2)

print(f"✓ MT360 1008 data saved to: {output_file}")
print(f"Total fields extracted: {len(mt360_1008_data['fields'])}")


