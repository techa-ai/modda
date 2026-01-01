"""
MT360 Bulk Loan Scraper
Scrapes OCR data from all loans in the MT360.com portfolio
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any
import re

# List of all loan numbers visible in MT360 Loan Index (15 total)
ALL_LOANS = [
    {"loan_number": "105742610", "loan_file_id": "1642451", "status": "Data Validation"},
    {"loan_number": "1225501664", "loan_file_id": "1584069", "status": "Data Validation"},
    {"loan_number": "2046007999", "loan_file_id": "1598638", "status": "Data Validation"},
    {"loan_number": "2052700869", "loan_file_id": "1579510", "status": "Data Validation"},
    {"loan_number": "9230018836", "loan_file_id": "1642452", "status": "Data Validation"},  # Note: displayed as 92300188365
    {"loan_number": "1551504333", "loan_file_id": "1597233", "status": "Data Validation"},
    {"loan_number": "1225421582", "loan_file_id": "1642450", "status": "Data Validation"},
    {"loan_number": "1457382910", "loan_file_id": "1642448", "status": "Data Validation"},
    {"loan_number": "1525185423", "loan_file_id": "1528996", "status": "Data Validation"},
    {"loan_number": "924087025", "loan_file_id": "1642449", "status": "Data Validation"},
    # Additional 5 loans (shown when display = 25)
    {"loan_number": "980121258806", "loan_file_id": "1475076", "status": "Data Validation"},
    {"loan_number": "4250489570", "loan_file_id": "1448202", "status": "Data Validation"},
    {"loan_number": "819912", "loan_file_id": "1573326", "status": "Data Validation"},
    {"loan_number": "1525070964", "loan_file_id": "1439728", "status": "Data Validation"},
    {"loan_number": "2501144775", "loan_file_id": "1642453", "status": "Data Validation"},
]

# Document types to scrape per loan
DOCUMENT_TYPES = {
    '1008': 'URLA/1008 Form',
    'URLA': 'Uniform Residential Loan Application',
    'Note': 'Promissory Note',
    'LoanEstimate': 'Loan Estimate',
    'ClosingDisclosure': 'Closing Disclosure',
    'CreditReport': 'Credit Report',
    '1004': 'Appraisal Report'
}


class MT360BulkScraper:
    """Scrapes all loans from MT360.com"""
    
    def __init__(self, output_dir: str = None):
        """Initialize bulk scraper"""
        self.output_dir = output_dir or "/Users/sunny/Applications/bts/jpmorgan/mortgage/modda/outputs/mt360_bulk_scrape"
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Create subdirectories
        self.data_dir = Path(self.output_dir) / "data"
        self.reports_dir = Path(self.output_dir) / "reports"
        self.logs_dir = Path(self.output_dir) / "logs"
        
        for dir_path in [self.data_dir, self.reports_dir, self.logs_dir]:
            dir_path.mkdir(exist_ok=True)
    
    def scrape_all_loans_from_screenshots(self) -> List[Dict]:
        """
        Extract loan data from browser screenshots and manual extraction
        This is a simplified version that uses the data we can see
        """
        print(f"\n{'='*80}")
        print("MT360 BULK LOAN SCRAPER")
        print(f"{'='*80}")
        print(f"Total loans to process: {len(ALL_LOANS)}")
        print(f"Document types per loan: {len(DOCUMENT_TYPES)}")
        print(f"Output directory: {self.output_dir}")
        
        all_scraped_data = []
        successful = 0
        failed = 0
        
        for idx, loan_info in enumerate(ALL_LOANS, 1):
            loan_number = loan_info['loan_number']
            loan_file_id = loan_info['loan_file_id']
            
            print(f"\n{'='*80}")
            print(f"Processing Loan {idx}/{len(ALL_LOANS)}")
            print(f"{'='*80}")
            print(f"Loan Number: {loan_number}")
            print(f"Loan File ID: {loan_file_id}")
            print(f"Status: {loan_info['status']}")
            
            try:
                loan_data = {
                    'loan_number': loan_number,
                    'loan_file_id': loan_file_id,
                    'scrape_timestamp': datetime.now().isoformat(),
                    'scrape_status': 'pending',
                    'documents': {},
                    'urls': {}
                }
                
                # Generate URLs for each document type
                for doc_type, doc_name in DOCUMENT_TYPES.items():
                    url = f"https://www.mt360.com/Document/Detail/{loan_file_id}?type={doc_type}"
                    loan_data['urls'][doc_type] = url
                    
                    # Placeholder for actual scraping
                    # In production, this would make actual browser requests
                    loan_data['documents'][doc_type] = {
                        'url': url,
                        'status': 'url_generated',
                        'document_type': doc_type,
                        'document_name': doc_name
                    }
                    
                    print(f"  ✓ Generated URL for {doc_type}: {url}")
                
                loan_data['scrape_status'] = 'urls_generated'
                all_scraped_data.append(loan_data)
                successful += 1
                
                # Save individual loan data
                loan_file = self.data_dir / f"loan_{loan_file_id}_urls.json"
                with open(loan_file, 'w') as f:
                    json.dump(loan_data, f, indent=2)
                
                print(f"  ✓ Saved to: {loan_file.name}")
                
            except Exception as e:
                print(f"  ✗ Error processing loan {loan_number}: {str(e)}")
                failed += 1
                loan_data['scrape_status'] = 'failed'
                loan_data['error'] = str(e)
                all_scraped_data.append(loan_data)
        
        # Generate summary
        summary = {
            'scrape_timestamp': datetime.now().isoformat(),
            'total_loans': len(ALL_LOANS),
            'successful': successful,
            'failed': failed,
            'document_types': list(DOCUMENT_TYPES.keys()),
            'loans': all_scraped_data
        }
        
        # Save bulk summary
        summary_file = self.data_dir / f"bulk_scrape_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)
        
        print(f"\n{'='*80}")
        print("BULK SCRAPE SUMMARY")
        print(f"{'='*80}")
        print(f"Total Loans: {summary['total_loans']}")
        print(f"✓ Successful: {summary['successful']}")
        print(f"✗ Failed: {summary['failed']}")
        print(f"\n✓ Summary saved to: {summary_file}")
        
        return all_scraped_data
    
    def generate_scrape_manifest(self, scraped_data: List[Dict]) -> str:
        """Generate a manifest of all URLs to scrape"""
        manifest = {
            'generated_at': datetime.now().isoformat(),
            'total_loans': len(scraped_data),
            'total_urls': len(scraped_data) * len(DOCUMENT_TYPES),
            'scrape_list': []
        }
        
        for loan in scraped_data:
            loan_entry = {
                'loan_number': loan['loan_number'],
                'loan_file_id': loan['loan_file_id'],
                'documents': []
            }
            
            for doc_type, url in loan['urls'].items():
                loan_entry['documents'].append({
                    'type': doc_type,
                    'url': url,
                    'status': 'pending'
                })
            
            manifest['scrape_list'].append(loan_entry)
        
        # Save manifest
        manifest_file = self.data_dir / "scrape_manifest.json"
        with open(manifest_file, 'w') as f:
            json.dump(manifest, f, indent=2)
        
        print(f"\n✓ Scrape manifest saved to: {manifest_file}")
        print(f"  Total URLs to scrape: {manifest['total_urls']}")
        
        return str(manifest_file)
    
    def generate_markdown_report(self, scraped_data: List[Dict]) -> str:
        """Generate markdown report of all loans"""
        report = f"""# MT360 Bulk Scrape Report

**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  
**Total Loans:** {len(scraped_data)}  
**Document Types:** {len(DOCUMENT_TYPES)}  
**Total URLs:** {len(scraped_data) * len(DOCUMENT_TYPES)}

---

## Summary

| Metric | Count |
|--------|-------|
| Total Loans | {len(scraped_data)} |
| Document Types per Loan | {len(DOCUMENT_TYPES)} |
| Total URLs Generated | {len(scraped_data) * len(DOCUMENT_TYPES)} |
| Successful | {sum(1 for l in scraped_data if l.get('scrape_status') != 'failed')} |
| Failed | {sum(1 for l in scraped_data if l.get('scrape_status') == 'failed')} |

---

## Loan List

"""
        
        for idx, loan in enumerate(scraped_data, 1):
            report += f"""
### {idx}. Loan {loan['loan_number']} (File ID: {loan['loan_file_id']})

**Status:** {loan['scrape_status']}

**Document URLs:**

"""
            
            for doc_type, doc_name in DOCUMENT_TYPES.items():
                url = loan['urls'].get(doc_type, 'N/A')
                report += f"- **{doc_name}:** [{url}]({url})\n"
            
            report += "\n---\n"
        
        # Add document types section
        report += f"""
## Document Types

The following document types are available for each loan:

"""
        
        for doc_type, doc_name in DOCUMENT_TYPES.items():
            report += f"1. **{doc_name}** (`{doc_type}`)\n"
        
        report += f"""

---

## Next Steps

### To Scrape Using Selenium:

```bash
cd /Users/sunny/Applications/bts/jpmorgan/mortgage/modda/backend

# For each loan in the manifest:
python3 mt360_scraper.py \\
  --username sbhatnagar \\
  --password '@Aa640192S' \\
  --loan-id LOAN_FILE_ID
```

### Or Use the Bulk Scraper:

```python
from mt360_scraper import MT360Scraper

scraper = MT360Scraper("sbhatnagar", "@Aa640192S")
scraper.setup_driver()
scraper.login()

for loan in ALL_LOANS:
    data = scraper.scrape_all_documents(loan['loan_file_id'])
    scraper.save_scraped_data(data)

scraper.cleanup()
```

---

**Report Generated:** {datetime.now().isoformat()}
"""
        
        # Save report
        report_file = self.reports_dir / f"bulk_scrape_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        with open(report_file, 'w') as f:
            f.write(report)
        
        print(f"\n✓ Markdown report saved to: {report_file}")
        
        return str(report_file)
    
    def generate_csv_summary(self, scraped_data: List[Dict]) -> str:
        """Generate CSV summary of all loans"""
        import csv
        
        csv_file = self.reports_dir / f"loan_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        with open(csv_file, 'w', newline='') as f:
            writer = csv.writer(f)
            
            # Header
            header = ['Loan Number', 'Loan File ID', 'Status']
            for doc_type in DOCUMENT_TYPES.keys():
                header.append(f'{doc_type} URL')
            writer.writerow(header)
            
            # Data rows
            for loan in scraped_data:
                row = [
                    loan['loan_number'],
                    loan['loan_file_id'],
                    loan['scrape_status']
                ]
                
                for doc_type in DOCUMENT_TYPES.keys():
                    row.append(loan['urls'].get(doc_type, ''))
                
                writer.writerow(row)
        
        print(f"✓ CSV summary saved to: {csv_file}")
        
        return str(csv_file)


def main():
    """Main execution"""
    print("""
╔════════════════════════════════════════════════════════════════════════════╗
║                     MT360 BULK LOAN SCRAPER                                 ║
║                                                                              ║
║  This script generates URLs and manifests for all loans in MT360.com        ║
║  Use the selenium-based scraper to fetch actual OCR data.                   ║
╚════════════════════════════════════════════════════════════════════════════╝
""")
    
    scraper = MT360BulkScraper()
    
    # Generate loan data with URLs
    print("\n📋 Generating loan URLs...")
    scraped_data = scraper.scrape_all_loans_from_screenshots()
    
    # Generate manifest
    print("\n📋 Generating scrape manifest...")
    manifest_file = scraper.generate_scrape_manifest(scraped_data)
    
    # Generate markdown report
    print("\n📝 Generating markdown report...")
    report_file = scraper.generate_markdown_report(scraped_data)
    
    # Generate CSV summary
    print("\n📊 Generating CSV summary...")
    csv_file = scraper.generate_csv_summary(scraped_data)
    
    print(f"\n{'='*80}")
    print("✅ BULK SCRAPE PREPARATION COMPLETE")
    print(f"{'='*80}")
    print(f"\n📁 All files saved to: {scraper.output_dir}")
    print(f"\n📄 Files generated:")
    print(f"  - Scrape manifest: {manifest_file}")
    print(f"  - Markdown report: {report_file}")
    print(f"  - CSV summary: {csv_file}")
    print(f"  - Individual loan JSONs: {scraper.data_dir}")
    
    print(f"\n{'='*80}")
    print("NEXT STEPS:")
    print(f"{'='*80}")
    print("""
1. Review the scrape manifest to see all URLs
2. Use mt360_scraper.py to scrape actual OCR data for each loan
3. Or integrate with your existing automation

Example command:
    python3 mt360_scraper.py --username sbhatnagar --password '@Aa640192S' --loan-id 1642452
    
For bulk automation, modify mt360_scraper.py to loop through all loans in the manifest.
""")


if __name__ == '__main__':
    main()

