"""
MT360 Snapshot Parser - Extract data from browser accessibility snapshot YAML files
Parses the YAML accessibility tree to extract all field names and values
"""

import re
import json
from pathlib import Path
from datetime import datetime

def parse_snapshot_file(snapshot_path):
    """
    Parse a browser snapshot YAML file and extract all data fields
    The snapshots contain accessibility tree with 'name:' attributes containing the actual text
    """
    with open(snapshot_path, 'r') as f:
        content = f.read()
    
    # Extract all lines with 'name:' that contain actual data
    # Pattern: name: followed by text (not just navigation/UI elements)
    data_fields = {}
    
    # Look for patterns like "name: Field Name" followed by "name: Value"
    lines = content.split('\n')
    
    for i, line in enumerate(lines):
        if 'name:' in line:
            # Extract the value after 'name:'
            match = re.search(r'name:\s*(.+)', line)
            if match:
                text = match.group(1).strip().strip('"\'')
                # Filter out navigation and UI elements
                if text and not any(x in text.lower() for x in [
                    'home', 'loan index', 'dashboard', 'logout', 'profile', 'search',
                    'back', 'actions', 'export', 'help', 'welcome', 'concierge',
                    'download', 'mtrade', 'mortgage', 'software', 'session', 'logged'
                ]):
                    # Check if next few lines contain a value
                    for j in range(i+1, min(i+10, len(lines))):
                        if 'name:' in lines[j]:
                            value_match = re.search(r'name:\s*(.+)', lines[j])
                            if value_match:
                                value = value_match.group(1).strip().strip('"\'')
                                # Check if this looks like a value (has numbers, $, %, etc.)
                                if value and any(c in value for c in ['$', '%', '0', '1', '2', '3', '4', '5', '6', '7', '8', '9']):
                                    data_fields[text] = value
                                    break
    
    return data_fields

def extract_loan_from_snapshot(snapshot_path, loan_file_id, doc_type):
    """
    Extract complete loan data from a snapshot file
    """
    fields = parse_snapshot_file(snapshot_path)
    
    data = {
        "loan_file_id": loan_file_id,
        "document_type": doc_type,
        "extraction_timestamp": datetime.now().isoformat(),
        "source": "mt360.com - DOM snapshot",
        "url": f"https://www.mt360.com/Document/Detail/{loan_file_id}?type={doc_type}",
        "has_data": len(fields) > 0,
        "fields": fields,
        "field_count": len(fields)
    }
    
    return data

if __name__ == "__main__":
    # Test with the current snapshot
    snapshot_file = "/Users/sunny/.cursor/browser-logs/snapshot-2025-12-18T12-14-24-218Z.log"
    
    print("MT360 Snapshot Parser")
    print("=" * 80)
    print(f"Parsing: {snapshot_file}")
    
    data = extract_loan_from_snapshot(snapshot_file, "1642452", "1008")
    
    print(f"\nExtracted {data['field_count']} fields:")
    for key, value in list(data['fields'].items())[:10]:
        print(f"  {key}: {value}")
    
    # Save to JSON
    output_file = Path("/Users/sunny/Applications/bts/jpmorgan/mortgage/modda/outputs/mt360_complete_extraction/data/loan_1642452_1008.json")
    with open(output_file, 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"\n✓ Saved to: {output_file}")


