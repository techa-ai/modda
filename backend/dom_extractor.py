"""
MT360 Complete DOM Data Extractor
Extracts all structured data from MT360 document pages by reading the actual HTML table data
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import json
from datetime import datetime
from pathlib import Path
import time

def extract_1008_full_data(driver, loan_file_id):
    """
    Extract complete 1008 data including all property, borrower, and underwriting fields
    """
    url = f"https://www.mt360.com/Document/Detail/{loan_file_id}?type=1008"
    driver.get(url)
    time.sleep(2)
    
    data = {
        "loan_file_id": loan_file_id,
        "document_type": "1008",
        "extraction_timestamp": datetime.now().isoformat(),
        "source": "mt360.com",
        "url": url,
        "has_data": True,
        "fields": {}
    }
    
    try:
        # Find all tables on the page
        tables = driver.find_elements(By.TAG_NAME, "table")
        
        for table in tables:
            try:
                rows = table.find_elements(By.TAG_NAME, "tr")
                for row in rows:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if len(cells) == 2:
                        # Key-value pair
                        key = cells[0].text.strip()
                        value = cells[1].text.strip()
                        if key and value:
                            data["fields"][key] = value
            except:
                continue
        
        # Organize by sections
        property_fields = {}
        borrower_fields = {}
        underwriting_fields = {}
        
        for key, value in data["fields"].items():
            key_lower = key.lower()
            if any(x in key_lower for x in ['property', 'occupancy', 'unit', 'apprais']):
                property_fields[key] = value
            elif any(x in key_lower for x in ['borrower', 'income', 'asset', 'coborrower']):
                borrower_fields[key] = value
            elif any(x in key_lower for x in ['loan', 'rate', 'term', 'ltv', 'dti', 'fico', 'heloc']):
                underwriting_fields[key] = value
        
        data["property_info"] = property_fields
        data["borrower_info"] = borrower_fields
        data["underwriting_info"] = underwriting_fields
        
    except Exception as e:
        data["extraction_error"] = str(e)
    
    return data

def extract_all_doc_types(driver, loan_file_id):
    """
    Extract all 6 document types for a given loan
    """
    doc_types = ["1008", "URLA", "Note", "LoanEstimate", "ClosingDisclosure", "CreditReport"]
    all_data = {}
    
    for doc_type in doc_types:
        try:
            url = f"https://www.mt360.com/Document/Detail/{loan_file_id}?type={doc_type}"
            driver.get(url)
            time.sleep(2)
            
            data = {
                "loan_file_id": loan_file_id,
                "document_type": doc_type,
                "extraction_timestamp": datetime.now().isoformat(),
                "source": "mt360.com",
                "url": url,
                "has_data": True,
                "fields": {}
            }
            
            # Find all tables and extract key-value pairs
            tables = driver.find_elements(By.TAG_NAME, "table")
            for table in tables:
                try:
                    rows = table.find_elements(By.TAG_NAME, "tr")
                    for row in rows:
                        cells = row.find_elements(By.TAG_NAME, "td")
                        if len(cells) == 2:
                            key = cells[0].text.strip()
                            value = cells[1].text.strip()
                            if key and value:
                                data["fields"][key] = value
                except:
                    continue
            
            all_data[doc_type] = data
            print(f"  ✓ {doc_type}: {len(data['fields'])} fields")
            
        except Exception as e:
            print(f"  ✗ {doc_type}: ERROR - {str(e)}")
            all_data[doc_type] = {
                "loan_file_id": loan_file_id,
                "document_type": doc_type,
                "has_data": False,
                "error": str(e)
            }
    
    return all_data

if __name__ == "__main__":
    print("="*80)
    print("MT360 COMPLETE DOM DATA EXTRACTOR")
    print("="*80)
    print("\nThis script requires Selenium with a browser driver.")
    print("For best results, use this as a template for browser automation.")
    print("\nExample usage:")
    print("  from selenium import webdriver")
    print("  driver = webdriver.Chrome()")
    print("  # Login to MT360")
    print("  data = extract_all_doc_types(driver, '1642451')")
    print("  # Save data")


