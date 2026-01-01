"""
MT360 1004 Appraisal Extractor
Extracts only 1004 (Appraisal Report) data for all loans using Playwright DOM extraction
"""

import asyncio
from playwright.async_api import async_playwright
import json
from pathlib import Path
from datetime import datetime

OUTPUT_DIR = Path("/Users/sunny/Applications/bts/jpmorgan/mortgage/modda/outputs/mt360_complete_extraction/data")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# All loan file IDs
LOANS = [
    "1642451", "1642452", "1642450", "1642448", "1642449",
    "1475076", "1528996", "1448202", "1573326", "1584069",
    "1597233", "1598638", "1439728", "1642453", "1579510"
]

async def wait_for_login(page):
    """Wait for user to login"""
    print("\n" + "="*60)
    print("BROWSER OPENED - PLEASE LOGIN TO MT360")
    print("="*60)
    print("\nNavigating to MT360...")
    
    await page.goto("https://www.mt360.com/")
    
    print("\n⏳ Waiting for you to login (up to 5 minutes)...")
    print("   After login, you should be on the Dashboard page.\n")
    
    try:
        await page.wait_for_url("**/Dashboard**", timeout=300000)
        print("\n✓ Login detected!")
    except:
        print("\n⚠ Continuing anyway...")
    
    await page.wait_for_timeout(2000)

async def extract_1004_data(page, loan_file_id):
    """Extract 1004 Appraisal data from DOM"""
    url = f"https://www.mt360.com/Document/Detail/{loan_file_id}?type=1004"
    
    try:
        print(f"  Navigating to {url}")
        await page.goto(url, wait_until='networkidle', timeout=30000)
        await page.wait_for_timeout(2000)
        
        # Extract data from DOM tables
        data = await page.evaluate("""() => {
            const fields = {};
            let totalRows = 0;
            
            const tables = document.querySelectorAll('table');
            
            tables.forEach((table, tableIdx) => {
                // Skip first table (loan header)
                if (tableIdx === 0) return;
                
                table.querySelectorAll('tr').forEach(row => {
                    totalRows++;
                    const th = row.querySelector('th');
                    const td = row.querySelector('td');
                    
                    if (th && td) {
                        const key = (th.innerText || th.textContent || '').trim();
                        const value = (td.innerText || td.textContent || '').trim();
                        
                        // Skip invalid keys
                        if (!key || key.length === 0 || key.length > 100 || /^[\\d$%.,\\s]+$/.test(key)) {
                            return;
                        }
                        
                        // Keep first value for each key
                        if (!fields.hasOwnProperty(key)) {
                            fields[key] = value;
                        }
                    }
                });
            });
            
            return {
                fields: fields,
                tableCount: tables.length,
                rowCount: totalRows
            };
        }""")
        
        field_count = len(data.get('fields', {}))
        
        # Check if page has real data or just header
        is_header_only = field_count <= 6 and all(
            k in ['Loan Number', 'Closing Date', 'Borrower(s)', 'Originator', 'Loan Amount', 'Property', 'Workflow Step']
            for k in data.get('fields', {}).keys()
        )
        
        return {
            "loan_file_id": loan_file_id,
            "document_type": "1004",
            "extraction_timestamp": datetime.now().isoformat(),
            "source": "mt360.com - 1004 Appraisal Extractor",
            "url": url,
            "has_data": field_count > 0 and not is_header_only,
            "field_count": field_count,
            "fields": data.get('fields', {}),
            "debug": {
                "tables_scanned": data.get('tableCount', 0),
                "rows_scanned": data.get('rowCount', 0)
            }
        }
        
    except Exception as e:
        return {
            "loan_file_id": loan_file_id,
            "document_type": "1004",
            "extraction_timestamp": datetime.now().isoformat(),
            "url": url,
            "has_data": False,
            "error": str(e)[:200]
        }

async def extract_all_1004():
    """Extract 1004 for all loans"""
    print("\n" + "="*60)
    print("MT360 1004 APPRAISAL EXTRACTOR")
    print("="*60)
    print(f"\nTotal loans to process: {len(LOANS)}")
    print(f"Output directory: {OUTPUT_DIR}")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=50)
        context = await browser.new_context()
        page = await context.new_page()
        
        await wait_for_login(page)
        
        total_docs = 0
        docs_with_data = 0
        start_time = datetime.now()
        
        print("\n" + "="*60)
        print("STARTING 1004 EXTRACTION")
        print("="*60)
        
        for i, loan_id in enumerate(LOANS, 1):
            print(f"\n[{i}/{len(LOANS)}] Loan {loan_id}")
            
            data = await extract_1004_data(page, loan_id)
            
            output_file = OUTPUT_DIR / f"loan_{loan_id}_1004.json"
            with open(output_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            field_count = data.get('field_count', 0)
            has_data = data.get('has_data', False)
            
            if has_data:
                print(f"  ✓ {field_count} fields extracted")
                docs_with_data += 1
            else:
                error = data.get('error', '')
                if error:
                    print(f"  ✗ Error: {error[:50]}...")
                else:
                    print(f"  ○ No data available")
            
            total_docs += 1
        
        await browser.close()
        
        elapsed = (datetime.now() - start_time).total_seconds()
        
        print("\n" + "="*60)
        print("✅ 1004 EXTRACTION COMPLETE!")
        print("="*60)
        print(f"Total loans processed: {total_docs}")
        print(f"Loans with 1004 data: {docs_with_data} ({docs_with_data/total_docs*100:.1f}%)")
        print(f"Time: {elapsed/60:.1f} minutes")
        print(f"\n✓ Output: {OUTPUT_DIR}")
        print("\nFiles created:")
        for loan_id in LOANS:
            file_path = OUTPUT_DIR / f"loan_{loan_id}_1004.json"
            if file_path.exists():
                size = file_path.stat().st_size
                print(f"  - loan_{loan_id}_1004.json ({size} bytes)")

if __name__ == "__main__":
    asyncio.run(extract_all_1004())
