"""
MT360 Extractor for specific loans
Extracts all document types (1008, URLA, Note, LoanEstimate, ClosingDisclosure, CreditReport, 1004)
"""

import asyncio
from playwright.async_api import async_playwright
import json
from pathlib import Path
from datetime import datetime

OUTPUT_DIR = Path("/Users/sunny/Applications/bts/jpmorgan/mortgage/modda/outputs/mt360_complete_extraction/data")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Loans to extract
LOANS = ["1579510", "1503797"]

# All document types
DOC_TYPES = ["1008", "URLA", "Note", "LoanEstimate", "ClosingDisclosure", "CreditReport", "1004"]

async def wait_for_login(page):
    """Wait for user to login"""
    print("\n" + "="*60)
    print("BROWSER OPENED - PLEASE LOGIN TO MT360")
    print("="*60)
    
    await page.goto("https://www.mt360.com/")
    
    print("\n⏳ Waiting for you to login (up to 5 minutes)...")
    try:
        await page.wait_for_url("**/Dashboard**", timeout=300000)
        print("\n✓ Login detected!")
    except:
        print("\n⚠ Continuing anyway...")
    
    await page.wait_for_timeout(2000)

async def extract_document_data(page, loan_file_id, doc_type):
    """Extract data from DOM tables"""
    url = f"https://www.mt360.com/Document/Detail/{loan_file_id}?type={doc_type}"
    
    try:
        await page.goto(url, wait_until='networkidle', timeout=30000)
        await page.wait_for_timeout(2000)
        
        # Smart extraction
        data = await page.evaluate("""() => {
            const fields = {};
            let totalRows = 0;
            let coBorrowerFields = {};
            let inCoBorrowerSection = false;
            let coBorrowerHasName = false;
            
            const tables = document.querySelectorAll('table');
            
            tables.forEach((table, tableIdx) => {
                if (tableIdx === 0) return;
                
                table.querySelectorAll('tr').forEach(row => {
                    totalRows++;
                    const th = row.querySelector('th');
                    const td = row.querySelector('td');
                    
                    if (th && td) {
                        const key = (th.innerText || th.textContent || '').trim();
                        const value = (td.innerText || td.textContent || '').trim();
                        
                        if (!key || key.length === 0 || key.length > 100 || /^[\\d$%.,\\s]+$/.test(key)) {
                            return;
                        }
                        
                        if (key === 'Borrower Type' && value === 'CoBorrower') {
                            inCoBorrowerSection = true;
                            coBorrowerFields = {'Borrower Type': 'CoBorrower'};
                            coBorrowerHasName = false;
                            return;
                        }
                        
                        if (key === 'Borrower Type' && value === 'Borrower' && inCoBorrowerSection) {
                            if (coBorrowerHasName) {
                                for (const [cbKey, cbVal] of Object.entries(coBorrowerFields)) {
                                    fields['CoBorrower_' + cbKey] = cbVal;
                                }
                            }
                            inCoBorrowerSection = false;
                        }
                        
                        if (inCoBorrowerSection) {
                            if (key === 'Name' && value && value.length > 0) {
                                coBorrowerHasName = true;
                            }
                            coBorrowerFields[key] = value;
                        } else {
                            if (!fields.hasOwnProperty(key)) {
                                fields[key] = value;
                            }
                        }
                    }
                });
            });
            
            if (inCoBorrowerSection && coBorrowerHasName) {
                for (const [cbKey, cbVal] of Object.entries(coBorrowerFields)) {
                    fields['CoBorrower_' + cbKey] = cbVal;
                }
            }
            
            return {
                fields: fields,
                tableCount: tables.length,
                rowCount: totalRows
            };
        }""")
        
        field_count = len(data.get('fields', {}))
        
        is_header_only = field_count <= 6 and all(
            k in ['Loan Number', 'Closing Date', 'Borrower(s)', 'Originator', 'Loan Amount', 'Property', 'Workflow Step']
            for k in data.get('fields', {}).keys()
        )
        
        return {
            "loan_file_id": loan_file_id,
            "document_type": doc_type,
            "extraction_timestamp": datetime.now().isoformat(),
            "source": "mt360.com - Specific Loan Extractor",
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
            "document_type": doc_type,
            "extraction_timestamp": datetime.now().isoformat(),
            "url": url,
            "has_data": False,
            "error": str(e)[:200]
        }

async def extract_specific_loans():
    """Extract all doc types for specific loans"""
    print("\n" + "="*60)
    print("MT360 EXTRACTOR - SPECIFIC LOANS")
    print(f"Loans: {LOANS}")
    print(f"Document Types: {DOC_TYPES}")
    print("="*60)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=50)
        context = await browser.new_context()
        page = await context.new_page()
        
        await wait_for_login(page)
        
        total_docs = 0
        docs_with_data = 0
        start_time = datetime.now()
        
        print("\n" + "="*60)
        print("STARTING EXTRACTION")
        print("="*60)
        
        for i, loan_id in enumerate(LOANS, 1):
            print(f"\n[{i}/{len(LOANS)}] Loan {loan_id}")
            print("-" * 40)
            
            loan_docs = 0
            for doc_type in DOC_TYPES:
                data = await extract_document_data(page, loan_id, doc_type)
                
                output_file = OUTPUT_DIR / f"loan_{loan_id}_{doc_type}.json"
                with open(output_file, 'w') as f:
                    json.dump(data, f, indent=2)
                
                field_count = data.get('field_count', 0)
                has_data = data.get('has_data', False)
                
                if has_data:
                    status = f"✓ {field_count} fields"
                    docs_with_data += 1
                    loan_docs += 1
                else:
                    status = f"○ no data"
                
                print(f"  {doc_type:20s} {status}")
                total_docs += 1
            
            print(f"  → {loan_docs}/{len(DOC_TYPES)} docs with data")
        
        await browser.close()
        
        elapsed = (datetime.now() - start_time).total_seconds()
        
        print("\n" + "="*60)
        print("✅ EXTRACTION COMPLETE!")
        print("="*60)
        print(f"Total documents: {total_docs}")
        print(f"With data: {docs_with_data} ({docs_with_data/total_docs*100:.1f}%)")
        print(f"Time: {elapsed/60:.1f} minutes")
        print(f"\n✓ Output: {OUTPUT_DIR}")

if __name__ == "__main__":
    asyncio.run(extract_specific_loans())
