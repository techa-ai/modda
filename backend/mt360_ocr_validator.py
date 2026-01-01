"""
MT360 OCR Validation Script
----------------------------
This script validates the OCR quality of documents provided by mt360.com
against the actual PDF documents we have locally processed.

Document types to validate:
- URLA (1008)
- Note
- Loan Estimate
- Closing Disclosure
- Credit Report
"""

import os
import json
import re
import time
from datetime import datetime
from typing import Dict, List, Any, Optional
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.chrome.options import Options
from difflib import SequenceMatcher
import pandas as pd


class MT360OCRValidator:
    """Validates OCR quality from mt360.com against local PDFs"""
    
    # Document type mappings
    DOCUMENT_TYPES = {
        'URLA': '1008',
        'Note': 'Note',
        'LoanEstimate': 'LoanEstimate',
        'ClosingDisclosure': 'ClosingDisclosure',
        'CreditReport': 'CreditReport'
    }
    
    def __init__(self, base_url: str = "https://www.mt360.com", 
                 documents_base_path: str = None,
                 output_path: str = None):
        """
        Initialize the validator
        
        Args:
            base_url: Base URL for mt360.com
            documents_base_path: Path to local documents folder
            output_path: Path to save validation reports
        """
        self.base_url = base_url
        self.documents_base_path = documents_base_path or "/Users/sunny/Applications/bts/jpmorgan/mortgage/modda/documents"
        self.output_path = output_path or "/Users/sunny/Applications/bts/jpmorgan/mortgage/modda/outputs/mt360_validation"
        self.driver = None
        self.wait = None
        
        # Create output directory
        os.makedirs(self.output_path, exist_ok=True)
        
    def setup_driver(self, headless: bool = False):
        """Setup Selenium WebDriver"""
        chrome_options = Options()
        if headless:
            chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--window-size=1920,1080')
        
        self.driver = webdriver.Chrome(options=chrome_options)
        self.wait = WebDriverWait(self.driver, 10)
        
    def login(self, username: str, password: str):
        """
        Login to mt360.com
        
        Args:
            username: MT360 username
            password: MT360 password
        """
        print(f"Logging into {self.base_url}...")
        self.driver.get(f"{self.base_url}/Loan/LoanIndex")
        
        try:
            # Wait for login form
            username_field = self.wait.until(
                EC.presence_of_element_located((By.NAME, "username"))
            )
            password_field = self.driver.find_element(By.NAME, "password")
            
            # Enter credentials
            username_field.clear()
            username_field.send_keys(username)
            password_field.clear()
            password_field.send_keys(password)
            
            # Click login button
            login_button = self.driver.find_element(By.XPATH, "//button[contains(text(), 'Login')]")
            login_button.click()
            
            # Wait for redirect to loan index
            self.wait.until(
                EC.url_contains("/Loan/LoanIndex")
            )
            print("✓ Login successful")
            
        except TimeoutException:
            print("✗ Login failed - timeout waiting for elements")
            raise
        except Exception as e:
            print(f"✗ Login failed: {str(e)}")
            raise
    
    def get_loan_list(self) -> List[Dict[str, str]]:
        """
        Get list of loans from the Loan Index page
        
        Returns:
            List of loan dictionaries with loan_number and loan_file_id
        """
        print("Fetching loan list...")
        self.driver.get(f"{self.base_url}/Loan/LoanIndex")
        
        try:
            # Wait for loan table to load
            self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table"))
            )
            
            loans = []
            # Find all loan rows
            rows = self.driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
            
            for row in rows:
                try:
                    # Extract loan number and file ID
                    loan_number_elem = row.find_element(By.CSS_SELECTOR, "td:first-child a")
                    loan_number = loan_number_elem.text.strip()
                    
                    # Extract loan file ID from the last column
                    loan_file_id_elem = row.find_element(By.CSS_SELECTOR, "td:last-child")
                    loan_file_id = loan_file_id_elem.text.strip()
                    
                    if loan_number and loan_file_id:
                        loans.append({
                            'loan_number': loan_number,
                            'loan_file_id': loan_file_id
                        })
                except Exception as e:
                    print(f"  Warning: Could not parse row: {str(e)}")
                    continue
            
            print(f"✓ Found {len(loans)} loans")
            return loans
            
        except Exception as e:
            print(f"✗ Failed to fetch loan list: {str(e)}")
            return []
    
    def extract_document_data(self, loan_file_id: str, doc_type: str) -> Dict[str, Any]:
        """
        Extract OCR data from mt360.com for a specific document type
        
        Args:
            loan_file_id: Loan file ID
            doc_type: Document type (URLA, Note, LoanEstimate, etc.)
            
        Returns:
            Dictionary containing extracted OCR data
        """
        url = f"{self.base_url}/Document/Detail/{loan_file_id}?type={doc_type}"
        print(f"  Extracting {doc_type} from {url}...")
        
        self.driver.get(url)
        
        try:
            # Wait for page to load
            time.sleep(2)
            
            # Extract all visible text and structured data
            ocr_data = {
                'url': url,
                'loan_file_id': loan_file_id,
                'document_type': doc_type,
                'extraction_timestamp': datetime.now().isoformat(),
                'fields': {},
                'raw_text': '',
                'tables': []
            }
            
            # Extract form fields
            try:
                form_fields = self.driver.find_elements(By.CSS_SELECTOR, "input, select, textarea")
                for field in form_fields:
                    try:
                        field_name = field.get_attribute('name') or field.get_attribute('id')
                        field_value = field.get_attribute('value') or field.text
                        if field_name and field_value:
                            ocr_data['fields'][field_name] = field_value
                    except:
                        pass
            except Exception as e:
                print(f"    Warning: Could not extract form fields: {str(e)}")
            
            # Extract all visible text
            try:
                body = self.driver.find_element(By.TAG_NAME, "body")
                ocr_data['raw_text'] = body.text
            except Exception as e:
                print(f"    Warning: Could not extract raw text: {str(e)}")
            
            # Extract tables
            try:
                tables = self.driver.find_elements(By.TAG_NAME, "table")
                for i, table in enumerate(tables):
                    table_data = {
                        'table_index': i,
                        'rows': []
                    }
                    rows = table.find_elements(By.TAG_NAME, "tr")
                    for row in rows:
                        cells = row.find_elements(By.TAG_NAME, "td") + row.find_elements(By.TAG_NAME, "th")
                        table_data['rows'].append([cell.text for cell in cells])
                    ocr_data['tables'].append(table_data)
            except Exception as e:
                print(f"    Warning: Could not extract tables: {str(e)}")
            
            # Extract key-value pairs from visible text
            ocr_data['extracted_kv_pairs'] = self._extract_key_value_pairs(ocr_data['raw_text'])
            
            print(f"  ✓ Extracted {len(ocr_data['fields'])} fields, {len(ocr_data['tables'])} tables")
            return ocr_data
            
        except Exception as e:
            print(f"  ✗ Failed to extract document data: {str(e)}")
            return None
    
    def _extract_key_value_pairs(self, text: str) -> Dict[str, str]:
        """
        Extract key-value pairs from text using common patterns
        
        Args:
            text: Raw text content
            
        Returns:
            Dictionary of extracted key-value pairs
        """
        kv_pairs = {}
        
        # Common patterns for key-value extraction
        patterns = [
            r'([A-Z][A-Za-z\s]+):\s*([^\n]+)',  # "Key: Value"
            r'([A-Z][A-Za-z\s]+)\s+([0-9,.$]+)',  # "Key 12345"
            r'([A-Z][A-Za-z\s]+)\s*[-–]\s*([^\n]+)',  # "Key - Value"
        ]
        
        for pattern in patterns:
            matches = re.finditer(pattern, text)
            for match in matches:
                key = match.group(1).strip()
                value = match.group(2).strip()
                if len(key) > 2 and len(value) > 0:  # Filter out noise
                    kv_pairs[key] = value
        
        return kv_pairs
    
    def load_local_document_data(self, loan_id: str, doc_type: str) -> Optional[Dict[str, Any]]:
        """
        Load locally extracted data for comparison
        
        Args:
            loan_id: Loan ID
            doc_type: Document type
            
        Returns:
            Dictionary containing local extraction data
        """
        loan_folder = Path(self.documents_base_path) / f"loan_{loan_id}"
        
        if not loan_folder.exists():
            print(f"  Warning: Local loan folder not found: {loan_folder}")
            return None
        
        # Map document type to local file patterns
        doc_type_patterns = {
            '1008': ['1008___final', 'urla___final', 'initial_urla'],
            'Note': ['note_2nd_lien', 'note'],
            'LoanEstimate': ['loan_estimate'],
            'ClosingDisclosure': ['closing_disclosure'],
            'CreditReport': ['credit_report']
        }
        
        patterns = doc_type_patterns.get(doc_type, [doc_type.lower()])
        
        # Look for JSON extraction files
        for pattern in patterns:
            # Check extraction JSON
            json_file = loan_folder / f"{pattern}_extraction.json"
            if json_file.exists():
                with open(json_file, 'r') as f:
                    return json.load(f)
            
            # Check in llama extractions folder
            extraction_folder = Path(f"/Users/sunny/Applications/bts/jpmorgan/mortgage/modda/backend/stage1/output/loan_{loan_id}/1_2_1_llama_extractions")
            if extraction_folder.exists():
                for file in extraction_folder.glob(f"{pattern}*.json"):
                    with open(file, 'r') as f:
                        return json.load(f)
        
        print(f"  Warning: No local extraction found for {doc_type}")
        return None
    
    def compare_extractions(self, mt360_data: Dict, local_data: Dict) -> Dict[str, Any]:
        """
        Compare MT360 OCR data with local extraction
        
        Args:
            mt360_data: Data extracted from MT360
            local_data: Data extracted locally
            
        Returns:
            Comparison results with quality metrics
        """
        comparison = {
            'timestamp': datetime.now().isoformat(),
            'mt360_document': mt360_data.get('document_type'),
            'loan_file_id': mt360_data.get('loan_file_id'),
            'field_comparison': {},
            'text_similarity': 0.0,
            'missing_in_mt360': [],
            'missing_in_local': [],
            'value_mismatches': [],
            'quality_score': 0.0,
            'metrics': {}
        }
        
        # Extract key fields from local data
        local_fields = self._flatten_dict(local_data)
        mt360_fields = mt360_data.get('extracted_kv_pairs', {})
        mt360_fields.update(mt360_data.get('fields', {}))
        
        # Compare fields
        all_keys = set(local_fields.keys()) | set(mt360_fields.keys())
        
        matches = 0
        total_compared = 0
        
        for key in all_keys:
            local_value = local_fields.get(key)
            mt360_value = mt360_fields.get(key)
            
            if local_value is None:
                comparison['missing_in_local'].append(key)
                continue
            
            if mt360_value is None:
                comparison['missing_in_mt360'].append(key)
                continue
            
            # Compare values
            total_compared += 1
            local_str = str(local_value).lower().strip()
            mt360_str = str(mt360_value).lower().strip()
            
            similarity = SequenceMatcher(None, local_str, mt360_str).ratio()
            
            comparison['field_comparison'][key] = {
                'local_value': local_value,
                'mt360_value': mt360_value,
                'similarity': similarity,
                'match': similarity > 0.85
            }
            
            if similarity > 0.85:
                matches += 1
            else:
                comparison['value_mismatches'].append({
                    'field': key,
                    'local': local_value,
                    'mt360': mt360_value,
                    'similarity': similarity
                })
        
        # Calculate overall similarity
        if total_compared > 0:
            comparison['quality_score'] = matches / total_compared
        
        # Calculate text similarity
        local_text = self._extract_text_from_dict(local_data)
        mt360_text = mt360_data.get('raw_text', '')
        
        if local_text and mt360_text:
            comparison['text_similarity'] = SequenceMatcher(
                None, 
                local_text.lower(), 
                mt360_text.lower()
            ).ratio()
        
        # Metrics
        comparison['metrics'] = {
            'total_fields_compared': total_compared,
            'matching_fields': matches,
            'fields_missing_in_mt360': len(comparison['missing_in_mt360']),
            'fields_missing_in_local': len(comparison['missing_in_local']),
            'value_mismatches_count': len(comparison['value_mismatches']),
            'field_match_rate': matches / total_compared if total_compared > 0 else 0,
            'text_similarity': comparison['text_similarity']
        }
        
        return comparison
    
    def _flatten_dict(self, d: Dict, parent_key: str = '', sep: str = '.') -> Dict:
        """Flatten nested dictionary"""
        items = []
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(self._flatten_dict(v, new_key, sep=sep).items())
            elif isinstance(v, list):
                for i, item in enumerate(v):
                    if isinstance(item, dict):
                        items.extend(self._flatten_dict(item, f"{new_key}[{i}]", sep=sep).items())
                    else:
                        items.append((f"{new_key}[{i}]", item))
            else:
                items.append((new_key, v))
        return dict(items)
    
    def _extract_text_from_dict(self, d: Dict) -> str:
        """Extract all text content from dictionary"""
        text_parts = []
        
        def extract(obj):
            if isinstance(obj, dict):
                for v in obj.values():
                    extract(v)
            elif isinstance(obj, list):
                for item in obj:
                    extract(item)
            elif isinstance(obj, str):
                text_parts.append(obj)
        
        extract(d)
        return ' '.join(text_parts)
    
    def validate_loan(self, loan_file_id: str, loan_number: str = None) -> Dict[str, Any]:
        """
        Validate all document types for a single loan
        
        Args:
            loan_file_id: Loan file ID from MT360
            loan_number: Optional loan number
            
        Returns:
            Validation results for all document types
        """
        print(f"\n{'='*80}")
        print(f"Validating Loan: {loan_file_id}")
        print(f"{'='*80}")
        
        results = {
            'loan_file_id': loan_file_id,
            'loan_number': loan_number,
            'validation_timestamp': datetime.now().isoformat(),
            'documents': {},
            'overall_quality': 0.0
        }
        
        quality_scores = []
        
        for doc_name, doc_type in self.DOCUMENT_TYPES.items():
            print(f"\n📄 Validating {doc_name}...")
            
            try:
                # Extract from MT360
                mt360_data = self.extract_document_data(loan_file_id, doc_type)
                if not mt360_data:
                    print(f"  ✗ Could not extract {doc_name} from MT360")
                    continue
                
                # Load local data
                local_data = self.load_local_document_data(loan_file_id, doc_type)
                if not local_data:
                    print(f"  ⚠ No local data available for comparison")
                    results['documents'][doc_name] = {
                        'mt360_data': mt360_data,
                        'status': 'no_local_comparison'
                    }
                    continue
                
                # Compare
                comparison = self.compare_extractions(mt360_data, local_data)
                results['documents'][doc_name] = comparison
                
                quality_scores.append(comparison['quality_score'])
                
                # Print summary
                print(f"  ✓ Quality Score: {comparison['quality_score']:.2%}")
                print(f"  ✓ Text Similarity: {comparison['text_similarity']:.2%}")
                print(f"  ✓ Matching Fields: {comparison['metrics']['matching_fields']}/{comparison['metrics']['total_fields_compared']}")
                print(f"  ✗ Mismatches: {comparison['metrics']['value_mismatches_count']}")
                
            except Exception as e:
                print(f"  ✗ Error validating {doc_name}: {str(e)}")
                results['documents'][doc_name] = {
                    'status': 'error',
                    'error': str(e)
                }
        
        # Calculate overall quality
        if quality_scores:
            results['overall_quality'] = sum(quality_scores) / len(quality_scores)
            print(f"\n{'='*80}")
            print(f"Overall Quality Score: {results['overall_quality']:.2%}")
            print(f"{'='*80}")
        
        return results
    
    def save_results(self, results: Dict, filename: str = None):
        """Save validation results to JSON file"""
        if filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            loan_id = results.get('loan_file_id', 'unknown')
            filename = f"validation_{loan_id}_{timestamp}.json"
        
        output_file = Path(self.output_path) / filename
        
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"\n✓ Results saved to: {output_file}")
        return output_file
    
    def generate_summary_report(self, all_results: List[Dict]) -> pd.DataFrame:
        """
        Generate summary report for all validations
        
        Args:
            all_results: List of validation results
            
        Returns:
            Pandas DataFrame with summary statistics
        """
        summary_data = []
        
        for result in all_results:
            loan_id = result.get('loan_file_id')
            overall_quality = result.get('overall_quality', 0)
            
            row = {
                'Loan File ID': loan_id,
                'Overall Quality': overall_quality
            }
            
            # Add document-specific metrics
            for doc_name, doc_result in result.get('documents', {}).items():
                if isinstance(doc_result, dict) and 'quality_score' in doc_result:
                    row[f'{doc_name} Quality'] = doc_result['quality_score']
                    row[f'{doc_name} Mismatches'] = doc_result['metrics'].get('value_mismatches_count', 0)
            
            summary_data.append(row)
        
        df = pd.DataFrame(summary_data)
        
        # Save to CSV
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        csv_file = Path(self.output_path) / f"validation_summary_{timestamp}.csv"
        df.to_csv(csv_file, index=False)
        
        print(f"\n✓ Summary report saved to: {csv_file}")
        
        return df
    
    def cleanup(self):
        """Close browser and cleanup"""
        if self.driver:
            self.driver.quit()
            print("\n✓ Browser closed")


def main():
    """Main execution function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Validate MT360 OCR Quality')
    parser.add_argument('--username', required=True, help='MT360 username')
    parser.add_argument('--password', required=True, help='MT360 password')
    parser.add_argument('--loan-id', help='Specific loan file ID to validate (optional)')
    parser.add_argument('--headless', action='store_true', help='Run browser in headless mode')
    parser.add_argument('--output', help='Output directory for results')
    
    args = parser.parse_args()
    
    # Initialize validator
    validator = MT360OCRValidator(
        output_path=args.output
    )
    
    try:
        # Setup browser
        validator.setup_driver(headless=args.headless)
        
        # Login
        validator.login(args.username, args.password)
        
        # Get loans to validate
        if args.loan_id:
            loans_to_validate = [{'loan_file_id': args.loan_id}]
        else:
            loans_to_validate = validator.get_loan_list()
        
        if not loans_to_validate:
            print("No loans found to validate")
            return
        
        # Validate each loan
        all_results = []
        for loan in loans_to_validate:
            loan_id = loan.get('loan_file_id')
            loan_number = loan.get('loan_number')
            
            results = validator.validate_loan(loan_id, loan_number)
            validator.save_results(results)
            all_results.append(results)
            
            # Add delay between loans
            time.sleep(2)
        
        # Generate summary report
        if len(all_results) > 1:
            summary_df = validator.generate_summary_report(all_results)
            print("\n" + "="*80)
            print("VALIDATION SUMMARY")
            print("="*80)
            print(summary_df.to_string())
        
    except Exception as e:
        print(f"\n✗ Error: {str(e)}")
        raise
    
    finally:
        validator.cleanup()


if __name__ == '__main__':
    main()



