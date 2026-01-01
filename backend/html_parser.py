"""
MT360 DOM Parser - Extract data from HTML without screenshots
Uses BeautifulSoup to parse the actual HTML DOM structure
"""

from bs4 import BeautifulSoup
import json
from datetime import datetime
from pathlib import Path

def parse_mt360_html(html_content, loan_file_id, doc_type):
    """
    Parse MT360 HTML and extract all table data
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    
    data = {
        "loan_file_id": loan_file_id,
        "document_type": doc_type,
        "extraction_timestamp": datetime.now().isoformat(),
        "source": "mt360.com",
        "url": f"https://www.mt360.com/Document/Detail/{loan_file_id}?type={doc_type}",
        "has_data": True,
        "fields": {}
    }
    
    # Find all tables
    tables = soup.find_all('table')
    
    for table in tables:
        rows = table.find_all('tr')
        for row in rows:
            cells = row.find_all('td')
            if len(cells) == 2:
                key = cells[0].get_text(strip=True)
                value = cells[1].get_text(strip=True)
                if key and value:
                    data["fields"][key] = value
    
    return data

def extract_from_browser_log(snapshot_file, loan_file_id, doc_type):
    """
    Extract data from browser snapshot log file
    This reads the actual HTML content, not visual screenshots
    """
    # Read the snapshot file
    with open(snapshot_file, 'r') as f:
        content = f.read()
    
    # The snapshot is YAML format, but we need to get the actual HTML
    # For now, return structure info
    return {
        "loan_file_id": loan_file_id,
        "document_type": doc_type,
        "note": "Snapshot file is YAML accessibility tree, not HTML"
    }

if __name__ == "__main__":
    print("MT360 DOM Parser")
    print("=" * 80)
    print("\nTo use this parser:")
    print("1. Save the HTML source from the browser (right-click -> Save Page As)")
    print("2. Or use Selenium to get page_source")
    print("3. Pass the HTML content to parse_mt360_html()")
    print("\nExample:")
    print("  html = driver.page_source")
    print("  data = parse_mt360_html(html, '1642451', '1008')")
    print("  print(json.dumps(data, indent=2))")


