"""
Debug script to understand the exact HTML table structure on MT360
"""

import asyncio
from playwright.async_api import async_playwright

async def debug_table_structure():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        # Navigate and wait for login
        await page.goto("https://www.mt360.com/")
        print("\n" + "="*60)
        print("PLEASE LOGIN - Script will continue once logged in")
        print("="*60)
        
        try:
            await page.wait_for_url("**/Dashboard**", timeout=300000)
            print("✓ Login detected!")
        except:
            pass
        
        # Navigate to specific document
        url = "https://www.mt360.com/Document/Detail/1642451?type=1008"
        print(f"\nNavigating to: {url}")
        await page.goto(url, wait_until='networkidle')
        await page.wait_for_timeout(3000)
        
        # Get detailed table structure
        structure = await page.evaluate("""() => {
            const result = {
                tables: []
            };
            
            document.querySelectorAll('table').forEach((table, tableIdx) => {
                const tableInfo = {
                    index: tableIdx,
                    className: table.className,
                    rows: []
                };
                
                table.querySelectorAll('tr').forEach((row, rowIdx) => {
                    const rowInfo = {
                        index: rowIdx,
                        cells: []
                    };
                    
                    // Get ALL cells in the row
                    row.querySelectorAll('th, td').forEach((cell, cellIdx) => {
                        rowInfo.cells.push({
                            index: cellIdx,
                            tagName: cell.tagName.toLowerCase(),
                            text: cell.innerText?.trim() || cell.textContent?.trim() || '',
                            colspan: cell.colSpan || 1,
                            className: cell.className
                        });
                    });
                    
                    if (rowInfo.cells.length > 0) {
                        tableInfo.rows.push(rowInfo);
                    }
                });
                
                if (tableInfo.rows.length > 0) {
                    result.tables.push(tableInfo);
                }
            });
            
            return result;
        }""")
        
        print("\n" + "="*60)
        print("TABLE STRUCTURE ANALYSIS")
        print("="*60)
        
        for table in structure['tables']:
            print(f"\n--- TABLE {table['index']} (class: {table['className']}) ---")
            for row in table['rows'][:10]:  # First 10 rows
                cells_str = []
                for cell in row['cells']:
                    tag = cell['tagName']
                    text = cell['text'][:30] if cell['text'] else '(empty)'
                    cells_str.append(f"[{tag}:{text}]")
                print(f"  Row {row['index']}: {' | '.join(cells_str)}")
            
            if len(table['rows']) > 10:
                print(f"  ... and {len(table['rows']) - 10} more rows")
        
        # Keep browser open to see
        print("\n✓ Browser will close in 30 seconds. Check the output above.")
        await page.wait_for_timeout(30000)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(debug_table_structure())


