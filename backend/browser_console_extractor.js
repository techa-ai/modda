"""
Extract data from MT360 1008 page using browser console JavaScript
Run this in the browser console to extract all table data as JSON
"""

js_extractor = """
// MT360 DOM Data Extractor - Run this in browser console
(function() {
    const data = {
        loan_file_id: document.querySelector('input[name]')?.value || '',
        document_type: document.title.replace(' Details', '').replace('Detail', '').trim(),
        extraction_timestamp: new Date().toISOString(),
        fields: {}
    };
    
    // Extract all tables with 2-column key-value pairs
    document.querySelectorAll('table').forEach(table => {
        table.querySelectorAll('tr').forEach(row => {
            const cells = row.querySelectorAll('td');
            if (cells.length === 2) {
                const key = cells[0].textContent.trim();
                const value = cells[1].textContent.trim();
                if (key && value) {
                    data.fields[key] = value;
                }
            }
        });
    });
    
    // Output as JSON
    console.log(JSON.stringify(data, null, 2));
    return data;
})();
"""

print("Copy and paste this JavaScript into the browser console:")
print("="*80)
print(js_extractor)
print("="*80)
print("\nThis will extract ALL field data from the current page as JSON")


