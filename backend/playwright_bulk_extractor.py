"""
MT360 Bulk DOM Extractor - FINAL WORKING VERSION
Key fix: Don't overwrite existing values (keeps primary borrower data)
"""

import asyncio
from playwright.async_api import async_playwright
import json
from pathlib import Path
from datetime import datetime

OUTPUT_DIR = Path("/Users/sunny/Applications/bts/jpmorgan/mortgage/modda/outputs/mt360_complete_extraction/data")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

async def wait_for_login(page):
    """Wait for user to login"""
    print("\n" + "="*60)
    print("BROWSER OPENED - PLEASE LOGIN")
    print("="*60)
    
    await page.goto("https://www.mt360.com/")
    
    try:
        await page.wait_for_url("**/Dashboard**", timeout=300000)
        print("\n✓ Login detected!")
    except:
        print("\n⚠ Continuing...")
    
    await page.wait_for_timeout(2000)

async def extract_document_data(page, loan_file_id, doc_type):
    """Extract data - capture both Borrower and CoBorrower (if has Name)"""
    url = f"https://www.mt360.com/Document/Detail/{loan_file_id}?type={doc_type}"
    
    try:
        await page.goto(url, wait_until='networkidle', timeout=30000)
        await page.wait_for_timeout(2000)
        
        # Smart extraction: capture primary borrower + co-borrower if has Name
        data = await page.evaluate("""() => {
            const fields = {};
            let totalRows = 0;
            let duplicatesSkipped = 0;
            let coBorrowerFields = {};  // Temporary storage for co-borrower section
            let inCoBorrowerSection = false;
            let coBorrowerHasName = false;
            
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
                        if (!key || key.length === 0 || key.length > 100 || /^[\d$%.,\s]+$/.test(key)) {
                            return;
                        }
                        
                        // Detect Co-Borrower section
                        if (key === 'Borrower Type' && value === 'CoBorrower') {
                            inCoBorrowerSection = true;
                            coBorrowerFields = {'Borrower Type': 'CoBorrower'};
                            coBorrowerHasName = false;
                            return;
                        }
                        
                        // If we hit a new Borrower section, save co-borrower data if valid
                        if (key === 'Borrower Type' && value === 'Borrower' && inCoBorrowerSection) {
                            // Save co-borrower fields if it had a Name (legitimate data)
                            if (coBorrowerHasName) {
                                for (const [cbKey, cbVal] of Object.entries(coBorrowerFields)) {
                                    fields['CoBorrower_' + cbKey] = cbVal;
                                }
                            }
                            inCoBorrowerSection = false;
                        }
                        
                        if (inCoBorrowerSection) {
                            // Track if co-borrower has a name (legitimate data)
                            if (key === 'Name' && value && value.length > 0) {
                                coBorrowerHasName = true;
                            }
                            coBorrowerFields[key] = value;
                        } else {
                            // Primary borrower - keep first value
                            if (!fields.hasOwnProperty(key)) {
                                fields[key] = value;
                            } else {
                                duplicatesSkipped++;
                            }
                        }
                    }
                });
            });
            
            // Don't forget to save co-borrower at end if valid
            if (inCoBorrowerSection && coBorrowerHasName) {
                for (const [cbKey, cbVal] of Object.entries(coBorrowerFields)) {
                    fields['CoBorrower_' + cbKey] = cbVal;
                }
            }
            
            return {
                fields: fields,
                tableCount: tables.length,
                rowCount: totalRows,
                duplicatesSkipped: duplicatesSkipped,
                hasCoBorrower: coBorrowerHasName
            };
        }""")
        
        field_count = len(data.get('fields', {}))
        
        # Filter out header-only extractions
        is_header_only = field_count <= 6 and all(
            k in ['Loan Number', 'Closing Date', 'Borrower(s)', 'Originator', 'Loan Amount', 'Property', 'Workflow Step']
            for k in data.get('fields', {}).keys()
        )
        
        return {
            "loan_file_id": loan_file_id,
            "document_type": doc_type,
            "extraction_timestamp": datetime.now().isoformat(),
            "source": "mt360.com - Final Extractor v2",
            "url": url,
            "has_data": field_count > 0 and not is_header_only,
            "field_count": field_count,
            "fields": data.get('fields', {}),
            "debug": {
                "tables_scanned": data.get('tableCount', 0),
                "rows_scanned": data.get('rowCount', 0),
                "duplicates_skipped": data.get('duplicatesSkipped', 0)
            }
        }
        
    except Exception as e:
        return {
            "loan_file_id": loan_file_id,
            "document_type": doc_type,
            "extraction_timestamp": datetime.now().isoformat(),
            "url": url,
            "has_data": False,
            "error": str(e)[:200]
        }

async def extract_all_loans():
    """Extract all 14 unique loans"""
    loans = [
        "1642451", "1642452", "1642450", "1642448", "1642449",
        "1475076", "1528996", "1448202", "1573326", "1584069",
        "1597233", "1598638", "1439728", "1642453"
    ]
    
    doc_types = ["1008", "URLA", "Note", "LoanEstimate", "ClosingDisclosure", "CreditReport", "1004"]
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=50)
        context = await browser.new_context()
        page = await context.new_page()
        
        await wait_for_login(page)
        
        total_docs = 0
        docs_with_data = 0
        
        start_time = datetime.now()
        
        print("\n" + "="*60)
        print("STARTING EXTRACTION (keeps first value - primary borrower)")
        print("="*60)
        
        for i, loan_id in enumerate(loans, 1):
            print(f"\n[{i}/{len(loans)}] Loan {loan_id}")
            print("-" * 40)
            
            loan_docs = 0
            for doc_type in doc_types:
                data = await extract_document_data(page, loan_id, doc_type)
                
                output_file = OUTPUT_DIR / f"loan_{loan_id}_{doc_type}.json"
                with open(output_file, 'w') as f:
                    json.dump(data, f, indent=2)
                
                field_count = data.get('field_count', 0)
                has_data = data.get('has_data', False)
                dups = data.get('debug', {}).get('duplicates_skipped', 0)
                
                if has_data:
                    status = f"✓ {field_count} fields"
                    if dups > 0:
                        status += f" (+{dups} dups)"
                    docs_with_data += 1
                    loan_docs += 1
                else:
                    status = f"○ no data"
                
                print(f"  {doc_type:20s} {status}")
                total_docs += 1
            
            elapsed = (datetime.now() - start_time).total_seconds()
            rate = total_docs / elapsed if elapsed > 0 else 0
            remaining = ((len(loans) - i) * len(doc_types))
            eta = (remaining / rate / 60) if rate > 0 else 0
            
            print(f"  → {loan_docs}/6 docs | Total: {docs_with_data}/{total_docs} | ETA: {eta:.1f}min")
        
        await browser.close()
        
        print("\n" + "="*60)
        print("✅ EXTRACTION COMPLETE!")
        print("="*60)
        print(f"Total documents: {total_docs}")
        print(f"With real data: {docs_with_data} ({docs_with_data/total_docs*100:.1f}%)")
        print(f"Time: {(datetime.now()-start_time).total_seconds()/60:.1f} minutes")
        print(f"\n✓ Output: {OUTPUT_DIR}")

if __name__ == "__main__":
    print("\n" + "="*60)
    print("MT360 BULK EXTRACTOR - v2 (First Value Wins)")
    print("Keeps primary borrower data, skips duplicates")
    print("="*60)
    
    asyncio.run(extract_all_loans())
