"""
MT360 OCR Data Scraper and Validator
This script logs into mt360.com, extracts OCR data from various document types,
and compares it with local PDF extractions to validate OCR quality.
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.chrome.options import Options
from difflib import SequenceMatcher
import re


class MT360Scraper:
    """Scrapes OCR data from mt360.com"""
    
    DOCUMENT_TYPES = {
        '1008': 'URLA/1008 Form',
        'URLA': 'Uniform Residential Loan Application',
        'Note': 'Promissory Note',
        'LoanEstimate': 'Loan Estimate',
        'ClosingDisclosure': 'Closing Disclosure',
        'CreditReport': 'Credit Report',
        '1004': 'Appraisal Report'
    }
    
    def __init__(self, username: str, password: str, output_dir: str = None):
        """Initialize scraper with credentials"""
        self.username = username
        self.password = password
        self.base_url = "https://www.mt360.com"
        self.output_dir = output_dir or "/Users/sunny/Applications/bts/jpmorgan/mortgage/modda/outputs/mt360_validation"
        self.driver = None
        self.wait = None
        
        os.makedirs(self.output_dir, exist_ok=True)
        
    def setup_driver(self, headless: bool = False):
        """Setup Chrome WebDriver"""
        chrome_options = Options()
        if headless:
            chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        self.driver = webdriver.Chrome(options=chrome_options)
        self.wait = WebDriverWait(self.driver, 15)
        print("✓ Chrome WebDriver initialized")
        
    def login(self):
        """Login to mt360.com"""
        print(f"\n{'='*80}")
        print("Logging into mt360.com...")
        print(f"{'='*80}")
        
        self.driver.get(f"{self.base_url}/Loan/LoanIndex")
        
        try:
            # Wait for login form
            username_field = self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='text'], input[name*='user'], input[placeholder*='user']"))
            )
            
            # Find password field
            password_field = self.driver.find_element(By.CSS_SELECTOR, "input[type='password']")
            
            # Enter credentials
            username_field.clear()
            username_field.send_keys(self.username)
            password_field.clear()
            password_field.send_keys(self.password)
            
            # Click login button
            login_button = self.driver.find_element(By.XPATH, "//button[contains(text(), 'Login') or contains(text(), 'login') or contains(text(), 'Sign In') or contains(text(), 'sign in')]")
            login_button.click()
            
            # Wait for redirect
            time.sleep(3)
            
            # Close any popups
            try:
                popup_buttons = self.driver.find_elements(By.XPATH, "//button[contains(text(), 'Don') or contains(text(), 'OK') or contains(text(), 'Close')]")
                for button in popup_buttons:
                    try:
                        button.click()
                        time.sleep(1)
                    except:
                        pass
            except:
                pass
            
            print("✓ Login successful")
            return True
            
        except Exception as e:
            print(f"✗ Login failed: {str(e)}")
            return False
    
    def extract_1008_data(self, loan_id: str) -> Dict[str, Any]:
        """Extract 1008/URLA data from mt360.com"""
        url = f"{self.base_url}/Document/Detail/{loan_id}?type=1008"
        print(f"\n📄 Extracting 1008 data from: {url}")
        
        self.driver.get(url)
        time.sleep(3)
        
        # Close any popups
        try:
            popup_buttons = self.driver.find_elements(By.XPATH, "//button[contains(text(), 'Don') or contains(text(), 'OK') or contains(text(), 'Close')]")
            for button in popup_buttons:
                try:
                    button.click()
                    time.sleep(0.5)
                except:
                    pass
        except:
            pass
        
        data = {
            'loan_id': loan_id,
            'document_type': '1008',
            'url': url,
            'extraction_timestamp': datetime.now().isoformat(),
            'fields': {},
            'tables': []
        }
        
        try:
            # Extract all visible text from labeled fields
            labels_and_values = self._extract_labeled_data()
            data['fields'] = labels_and_values
            
            # Extract tables
            tables = self._extract_tables()
            data['tables'] = tables
            
            # Get full page text
            body = self.driver.find_element(By.TAG_NAME, "body")
            data['raw_text'] = body.text
            
            print(f"  ✓ Extracted {len(data['fields'])} fields and {len(data['tables'])} tables")
            
        except Exception as e:
            print(f"  ✗ Error extracting 1008 data: {str(e)}")
        
        return data
    
    def extract_document_data(self, loan_id: str, doc_type: str) -> Dict[str, Any]:
        """Extract data for any document type"""
        url = f"{self.base_url}/Document/Detail/{loan_id}?type={doc_type}"
        print(f"\n📄 Extracting {doc_type} from: {url}")
        
        self.driver.get(url)
        time.sleep(3)
        
        # Close any popups
        try:
            popup_buttons = self.driver.find_elements(By.XPATH, "//button[contains(text(), 'Don') or contains(text(), 'OK') or contains(text(), 'Close')]")
            for button in popup_buttons:
                try:
                    button.click()
                    time.sleep(0.5)
                except:
                    pass
        except:
            pass
        
        data = {
            'loan_id': loan_id,
            'document_type': doc_type,
            'url': url,
            'extraction_timestamp': datetime.now().isoformat(),
            'fields': {},
            'tables': []
        }
        
        try:
            # Extract all visible text from labeled fields
            labels_and_values = self._extract_labeled_data()
            data['fields'] = labels_and_values
            
            # Extract tables
            tables = self._extract_tables()
            data['tables'] = tables
            
            # Get full page text
            body = self.driver.find_element(By.TAG_NAME, "body")
            data['raw_text'] = body.text
            
            print(f"  ✓ Extracted {len(data['fields'])} fields and {len(data['tables'])} tables")
            
        except Exception as e:
            print(f"  ✗ Error extracting {doc_type} data: {str(e)}")
        
        return data
    
    def _extract_labeled_data(self) -> Dict[str, str]:
        """Extract label-value pairs from the page"""
        labeled_data = {}
        
        try:
            # Method 1: Find all dt/dd pairs (definition lists)
            dt_elements = self.driver.find_elements(By.TAG_NAME, "dt")
            for dt in dt_elements:
                try:
                    label = dt.text.strip()
                    # Find corresponding dd
                    dd = dt.find_element(By.XPATH, "following-sibling::dd[1]")
                    value = dd.text.strip()
                    if label and value:
                        labeled_data[label] = value
                except:
                    pass
        except:
            pass
        
        try:
            # Method 2: Find label-input/text combinations
            labels = self.driver.find_elements(By.TAG_NAME, "label")
            for label in labels:
                try:
                    label_text = label.text.strip()
                    if not label_text:
                        continue
                    
                    # Try to find associated input/select/textarea
                    label_for = label.get_attribute("for")
                    if label_for:
                        try:
                            input_elem = self.driver.find_element(By.ID, label_for)
                            value = input_elem.get_attribute("value") or input_elem.text
                            if value:
                                labeled_data[label_text] = value.strip()
                        except:
                            pass
                    else:
                        # Try to find input as sibling or child
                        try:
                            input_elem = label.find_element(By.XPATH, ".//input | .//select | .//textarea | following-sibling::*//input | following-sibling::*//select | following-sibling::*//textarea")
                            value = input_elem.get_attribute("value") or input_elem.text
                            if value:
                                labeled_data[label_text] = value.strip()
                        except:
                            pass
                except:
                    pass
        except:
            pass
        
        try:
            # Method 3: Find divs with specific patterns (common in modern web apps)
            # Look for divs with class containing "field", "row", "item", etc.
            field_containers = self.driver.find_elements(By.CSS_SELECTOR, 
                "div[class*='field'], div[class*='row'], div[class*='item'], div[class*='property']")
            
            for container in field_containers:
                try:
                    text = container.text.strip()
                    if not text or len(text) > 200:
                        continue
                    
                    # Try to split by colon or newline
                    if ':' in text:
                        parts = text.split(':', 1)
                        if len(parts) == 2:
                            key = parts[0].strip()
                            value = parts[1].strip()
                            if key and value and len(key) < 100:
                                labeled_data[key] = value
                    elif '\n' in text and len(text.split('\n')) == 2:
                        parts = text.split('\n')
                        key = parts[0].strip()
                        value = parts[1].strip()
                        if key and value and len(key) < 100:
                            labeled_data[key] = value
                except:
                    pass
        except:
            pass
        
        return labeled_data
    
    def _extract_tables(self) -> List[Dict]:
        """Extract table data from the page"""
        tables_data = []
        
        try:
            tables = self.driver.find_elements(By.TAG_NAME, "table")
            
            for idx, table in enumerate(tables):
                table_info = {
                    'table_index': idx,
                    'headers': [],
                    'rows': []
                }
                
                try:
                    # Extract headers
                    headers = table.find_elements(By.TAG_NAME, "th")
                    table_info['headers'] = [h.text.strip() for h in headers if h.text.strip()]
                    
                    # Extract rows
                    rows = table.find_elements(By.TAG_NAME, "tr")
                    for row in rows:
                        cells = row.find_elements(By.TAG_NAME, "td")
                        if cells:
                            row_data = [cell.text.strip() for cell in cells]
                            if any(row_data):  # Only add non-empty rows
                                table_info['rows'].append(row_data)
                    
                    if table_info['headers'] or table_info['rows']:
                        tables_data.append(table_info)
                        
                except:
                    pass
        except:
            pass
        
        return tables_data
    
    def scrape_all_documents(self, loan_id: str) -> Dict[str, Any]:
        """Scrape all document types for a loan"""
        print(f"\n{'='*80}")
        print(f"Scraping all documents for Loan ID: {loan_id}")
        print(f"{'='*80}")
        
        results = {
            'loan_id': loan_id,
            'scrape_timestamp': datetime.now().isoformat(),
            'documents': {}
        }
        
        for doc_type, doc_name in self.DOCUMENT_TYPES.items():
            try:
                doc_data = self.extract_document_data(loan_id, doc_type)
                results['documents'][doc_type] = doc_data
                time.sleep(2)  # Be nice to the server
            except Exception as e:
                print(f"  ✗ Failed to scrape {doc_type}: {str(e)}")
                results['documents'][doc_type] = {
                    'error': str(e),
                    'status': 'failed'
                }
        
        return results
    
    def save_scraped_data(self, data: Dict, filename: str = None):
        """Save scraped data to JSON file"""
        if filename is None:
            loan_id = data.get('loan_id', 'unknown')
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"mt360_scraped_{loan_id}_{timestamp}.json"
        
        output_file = Path(self.output_dir) / filename
        
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"\n✓ Scraped data saved to: {output_file}")
        return output_file
    
    def cleanup(self):
        """Close browser"""
        if self.driver:
            self.driver.quit()
            print("\n✓ Browser closed")


class OCRValidator:
    """Validates MT360 OCR against local extractions"""
    
    def __init__(self, documents_path: str = None):
        """Initialize validator"""
        self.documents_path = documents_path or "/Users/sunny/Applications/bts/jpmorgan/mortgage/modda/documents"
        self.stage1_output = "/Users/sunny/Applications/bts/jpmorgan/mortgage/modda/backend/stage1/output"
    
    def load_local_extraction(self, loan_id: str, doc_type: str) -> Optional[Dict]:
        """Load local PDF extraction data"""
        print(f"  Loading local extraction for {doc_type}...")
        
        # Map MT360 doc types to local file patterns
        doc_patterns = {
            '1008': ['1008___final', 'urla___final', 'initial_urla'],
            'URLA': ['urla___final', 'initial_urla', '1008___final'],
            'Note': ['note_2nd_lien', 'note'],
            'LoanEstimate': ['loan_estimate'],
            'ClosingDisclosure': ['closing_disclosure'],
            'CreditReport': ['credit_report___final']
        }
        
        patterns = doc_patterns.get(doc_type, [doc_type.lower()])
        
        # Check stage1 output for llama extractions
        extraction_folder = Path(self.stage1_output) / f"loan_{loan_id}" / "1_2_1_llama_extractions"
        
        if extraction_folder.exists():
            for pattern in patterns:
                matching_files = list(extraction_folder.glob(f"{pattern}*.json"))
                if matching_files:
                    # Use the first matching file
                    with open(matching_files[0], 'r') as f:
                        data = json.load(f)
                        print(f"  ✓ Loaded from: {matching_files[0].name}")
                        return data
        
        # Check documents folder
        doc_folder = Path(self.documents_path) / f"loan_{loan_id}"
        if doc_folder.exists():
            for pattern in patterns:
                json_file = doc_folder / f"{pattern}_extraction.json"
                if json_file.exists():
                    with open(json_file, 'r') as f:
                        data = json.load(f)
                        print(f"  ✓ Loaded from: {json_file.name}")
                        return data
        
        print(f"  ⚠ No local extraction found for {doc_type}")
        return None
    
    def compare_data(self, mt360_data: Dict, local_data: Dict) -> Dict[str, Any]:
        """Compare MT360 OCR with local extraction"""
        print(f"  Comparing OCR quality...")
        
        comparison = {
            'document_type': mt360_data.get('document_type'),
            'loan_id': mt360_data.get('loan_id'),
            'comparison_timestamp': datetime.now().isoformat(),
            'field_comparisons': [],
            'metrics': {
                'total_fields_compared': 0,
                'exact_matches': 0,
                'partial_matches': 0,
                'mismatches': 0,
                'missing_in_mt360': 0,
                'missing_in_local': 0
            },
            'quality_score': 0.0,
            'text_similarity': 0.0
        }
        
        # Flatten both datasets for comparison
        mt360_fields = self._flatten_dict(mt360_data.get('fields', {}))
        local_fields = self._flatten_dict(local_data)
        
        # Find common keys for comparison
        all_keys = set(mt360_fields.keys()) | set(local_fields.keys())
        
        for key in all_keys:
            mt360_value = mt360_fields.get(key)
            local_value = local_fields.get(key)
            
            if mt360_value is None:
                comparison['metrics']['missing_in_mt360'] += 1
                comparison['field_comparisons'].append({
                    'field': key,
                    'status': 'missing_in_mt360',
                    'local_value': str(local_value),
                    'mt360_value': None,
                    'similarity': 0.0
                })
                continue
            
            if local_value is None:
                comparison['metrics']['missing_in_local'] += 1
                comparison['field_comparisons'].append({
                    'field': key,
                    'status': 'missing_in_local',
                    'local_value': None,
                    'mt360_value': str(mt360_value),
                    'similarity': 0.0
                })
                continue
            
            # Compare values
            comparison['metrics']['total_fields_compared'] += 1
            
            mt360_str = self._normalize_value(str(mt360_value))
            local_str = self._normalize_value(str(local_value))
            
            similarity = SequenceMatcher(None, mt360_str, local_str).ratio()
            
            if similarity == 1.0:
                status = 'exact_match'
                comparison['metrics']['exact_matches'] += 1
            elif similarity >= 0.8:
                status = 'partial_match'
                comparison['metrics']['partial_matches'] += 1
            else:
                status = 'mismatch'
                comparison['metrics']['mismatches'] += 1
            
            comparison['field_comparisons'].append({
                'field': key,
                'status': status,
                'local_value': str(local_value),
                'mt360_value': str(mt360_value),
                'similarity': similarity
            })
        
        # Calculate overall quality score
        total = comparison['metrics']['total_fields_compared']
        if total > 0:
            matches = comparison['metrics']['exact_matches'] + (comparison['metrics']['partial_matches'] * 0.8)
            comparison['quality_score'] = matches / total
        
        # Compare raw text
        mt360_text = mt360_data.get('raw_text', '')
        local_text = self._extract_all_text(local_data)
        
        if mt360_text and local_text:
            comparison['text_similarity'] = SequenceMatcher(
                None,
                self._normalize_value(mt360_text),
                self._normalize_value(local_text)
            ).ratio()
        
        print(f"  ✓ Quality Score: {comparison['quality_score']:.2%}")
        print(f"  ✓ Exact Matches: {comparison['metrics']['exact_matches']}")
        print(f"  ✓ Partial Matches: {comparison['metrics']['partial_matches']}")
        print(f"  ✗ Mismatches: {comparison['metrics']['mismatches']}")
        
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
    
    def _normalize_value(self, value: str) -> str:
        """Normalize string for comparison"""
        if not value:
            return ""
        # Remove extra whitespace, convert to lowercase
        normalized = re.sub(r'\s+', ' ', value.lower().strip())
        # Remove currency symbols and formatting
        normalized = re.sub(r'[$,]', '', normalized)
        return normalized
    
    def _extract_all_text(self, data: Dict) -> str:
        """Extract all text from nested dictionary"""
        texts = []
        
        def extract(obj):
            if isinstance(obj, dict):
                for v in obj.values():
                    extract(v)
            elif isinstance(obj, list):
                for item in obj:
                    extract(item)
            elif isinstance(obj, str):
                texts.append(obj)
        
        extract(data)
        return ' '.join(texts)
    
    def validate_loan(self, loan_id: str, scraped_data: Dict) -> Dict[str, Any]:
        """Validate all documents for a loan"""
        print(f"\n{'='*80}")
        print(f"Validating OCR Quality for Loan: {loan_id}")
        print(f"{'='*80}")
        
        validation_results = {
            'loan_id': loan_id,
            'validation_timestamp': datetime.now().isoformat(),
            'documents': {},
            'overall_metrics': {
                'documents_validated': 0,
                'average_quality_score': 0.0,
                'total_exact_matches': 0,
                'total_mismatches': 0
            }
        }
        
        quality_scores = []
        
        for doc_type, scraped_doc in scraped_data.get('documents', {}).items():
            if 'error' in scraped_doc:
                print(f"\n⚠ Skipping {doc_type} - scraping failed")
                continue
            
            print(f"\n📊 Validating {doc_type}...")
            
            local_data = self.load_local_extraction(loan_id, doc_type)
            
            if not local_data:
                validation_results['documents'][doc_type] = {
                    'status': 'no_local_data',
                    'mt360_fields_count': len(scraped_doc.get('fields', {}))
                }
                continue
            
            comparison = self.compare_data(scraped_doc, local_data)
            validation_results['documents'][doc_type] = comparison
            
            quality_scores.append(comparison['quality_score'])
            validation_results['overall_metrics']['documents_validated'] += 1
            validation_results['overall_metrics']['total_exact_matches'] += comparison['metrics']['exact_matches']
            validation_results['overall_metrics']['total_mismatches'] += comparison['metrics']['mismatches']
        
        # Calculate overall average quality
        if quality_scores:
            validation_results['overall_metrics']['average_quality_score'] = sum(quality_scores) / len(quality_scores)
        
        print(f"\n{'='*80}")
        print(f"Overall Validation Summary")
        print(f"{'='*80}")
        print(f"Documents Validated: {validation_results['overall_metrics']['documents_validated']}")
        print(f"Average Quality Score: {validation_results['overall_metrics']['average_quality_score']:.2%}")
        print(f"Total Exact Matches: {validation_results['overall_metrics']['total_exact_matches']}")
        print(f"Total Mismatches: {validation_results['overall_metrics']['total_mismatches']}")
        
        return validation_results


def main():
    """Main execution"""
    import argparse
    
    parser = argparse.ArgumentParser(description='MT360 OCR Validation')
    parser.add_argument('--username', required=True, help='MT360 username')
    parser.add_argument('--password', required=True, help='MT360 password')
    parser.add_argument('--loan-id', required=True, help='Loan File ID to validate')
    parser.add_argument('--headless', action='store_true', help='Run in headless mode')
    parser.add_argument('--output-dir', help='Output directory for results')
    
    args = parser.parse_args()
    
    # Initialize scraper
    scraper = MT360Scraper(args.username, args.password, args.output_dir)
    validator = OCRValidator()
    
    try:
        # Setup and login
        scraper.setup_driver(headless=args.headless)
        
        if not scraper.login():
            print("Failed to login. Exiting.")
            return
        
        # Scrape all documents
        scraped_data = scraper.scrape_all_documents(args.loan_id)
        scraped_file = scraper.save_scraped_data(scraped_data)
        
        # Validate against local data
        validation_results = validator.validate_loan(args.loan_id, scraped_data)
        
        # Save validation results
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        validation_file = Path(scraper.output_dir) / f"validation_{args.loan_id}_{timestamp}.json"
        with open(validation_file, 'w') as f:
            json.dump(validation_results, f, indent=2)
        
        print(f"\n✓ Validation results saved to: {validation_file}")
        
    except Exception as e:
        print(f"\n✗ Error: {str(e)}")
        import traceback
        traceback.print_exc()
    
    finally:
        scraper.cleanup()


if __name__ == '__main__':
    main()


