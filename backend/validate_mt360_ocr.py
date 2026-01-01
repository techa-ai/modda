"""
MT360 OCR Quality Validator
Compares MT360 OCR data with local PDF extractions
"""

import json
import os
from pathlib import Path
from datetime import datetime
from difflib import SequenceMatcher
import re
from typing import Dict, Any, List, Tuple


class OCRQualityValidator:
    """Validates OCR quality by comparing MT360 data with local extractions"""
    
    def __init__(self, documents_path: str = None, stage1_output: str = None):
        """Initialize validator"""
        self.documents_path = documents_path or "/Users/sunny/Applications/bts/jpmorgan/mortgage/modda/documents"
        self.stage1_output = stage1_output or "/Users/sunny/Applications/bts/jpmorgan/mortgage/modda/backend/stage1/output"
        self.output_dir = "/Users/sunny/Applications/bts/jpmorgan/mortgage/modda/outputs/mt360_validation"
        os.makedirs(self.output_dir, exist_ok=True)
    
    def load_local_1008_extraction(self, loan_id: str) -> Dict:
        """Load local 1008 extraction"""
        print(f"\n{'='*80}")
        print(f"Loading local 1008 extraction for loan {loan_id}")
        print(f"{'='*80}")
        
        # Check stage1 output
        extraction_folder = Path(self.stage1_output) / f"loan_{loan_id}" / "1_2_1_llama_extractions"
        
        if extraction_folder.exists():
            # Look for 1008 or URLA files
            patterns = ['1008___final*.json', 'urla___final*.json', 'initial_urla*.json']
            
            for pattern in patterns:
                matching_files = list(extraction_folder.glob(pattern))
                if matching_files:
                    file_path = matching_files[0]
                    with open(file_path, 'r') as f:
                        data = json.load(f)
                        print(f"✓ Loaded local extraction: {file_path.name}")
                        return data
        
        print(f"✗ No local 1008 extraction found for loan {loan_id}")
        return None
    
    def normalize_value(self, value: Any) -> str:
        """Normalize value for comparison"""
        if value is None:
            return ""
        
        s = str(value).lower().strip()
        
        # Remove extra whitespace
        s = re.sub(r'\s+', ' ', s)
        
        # Remove common formatting
        s = s.replace(',', '').replace('$', '').replace('%', '')
        
        # Handle boolean variations
        if s in ['true', 'yes', 'y', '1']:
            return 'true'
        if s in ['false', 'no', 'n', '0']:
            return 'false'
        
        return s
    
    def extract_flat_fields(self, data: Dict, prefix: str = '') -> Dict[str, Any]:
        """Extract flat field mapping from nested dict"""
        flat_fields = {}
        
        def extract_recursive(obj, path=''):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    new_path = f"{path}.{key}" if path else key
                    if isinstance(value, (dict, list)):
                        extract_recursive(value, new_path)
                    else:
                        flat_fields[new_path] = value
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    if isinstance(item, (dict, list)):
                        extract_recursive(item, f"{path}[{i}]")
                    else:
                        flat_fields[f"{path}[{i}]"] = item
        
        extract_recursive(data)
        return flat_fields
    
    def find_matching_fields(self, mt360_fields: Dict, local_fields: Dict) -> List[Tuple]:
        """Find matching field names between MT360 and local extractions"""
        matches = []
        
        # Normalize field names for fuzzy matching
        def normalize_field_name(name):
            return re.sub(r'[^a-z0-9]', '', name.lower())
        
        mt360_normalized = {normalize_field_name(k): k for k in mt360_fields.keys()}
        local_normalized = {normalize_field_name(k): k for k in local_fields.keys()}
        
        # Direct matches
        for norm_name, mt360_name in mt360_normalized.items():
            if norm_name in local_normalized:
                local_name = local_normalized[norm_name]
                matches.append((mt360_name, local_name, 'exact'))
        
        # Fuzzy matches for remaining fields
        matched_mt360 = {m[0] for m in matches}
        matched_local = {m[1] for m in matches}
        
        remaining_mt360 = [(k, v) for k, v in mt360_normalized.items() if v not in matched_mt360]
        remaining_local = [(k, v) for k, v in local_normalized.items() if v not in matched_local]
        
        for norm_mt360, mt360_name in remaining_mt360:
            best_match = None
            best_score = 0.6  # Minimum threshold
            
            for norm_local, local_name in remaining_local:
                score = SequenceMatcher(None, norm_mt360, norm_local).ratio()
                if score > best_score:
                    best_score = score
                    best_match = local_name
            
            if best_match:
                matches.append((mt360_name, best_match, 'fuzzy'))
                remaining_local = [(k, v) for k, v in remaining_local if v != best_match]
        
        return matches
    
    def compare_extractions(self, mt360_data: Dict, local_data: Dict) -> Dict:
        """Compare MT360 and local extractions"""
        print(f"\n{'='*80}")
        print("Comparing MT360 OCR with Local Extraction")
        print(f"{'='*80}")
        
        comparison = {
            'loan_id': mt360_data.get('loan_id'),
            'comparison_timestamp': datetime.now().isoformat(),
            'mt360_source': mt360_data.get('url'),
            'local_source': local_data.get('filename') if local_data else None,
            'field_comparisons': [],
            'metrics': {
                'total_mt360_fields': 0,
                'total_local_fields': 0,
                'matched_fields': 0,
                'exact_matches': 0,
                'partial_matches': 0,
                'mismatches': 0,
                'unmatched_mt360_fields': 0,
                'unmatched_local_fields': 0,
                'accuracy_score': 0.0,
                'precision': 0.0,
                'recall': 0.0
            },
            'quality_assessment': {
                'overall_grade': '',
                'strengths': [],
                'weaknesses': [],
                'recommendations': []
            }
        }
        
        mt360_fields = mt360_data.get('fields', {})
        local_flat = self.extract_flat_fields(local_data) if local_data else {}
        
        comparison['metrics']['total_mt360_fields'] = len(mt360_fields)
        comparison['metrics']['total_local_fields'] = len(local_flat)
        
        # Find matching fields
        field_matches = self.find_matching_fields(mt360_fields, local_flat)
        comparison['metrics']['matched_fields'] = len(field_matches)
        
        print(f"\n📊 Field Matching Statistics:")
        print(f"  MT360 fields: {len(mt360_fields)}")
        print(f"  Local fields: {len(local_flat)}")
        print(f"  Matched fields: {len(field_matches)}")
        
        # Compare matched fields
        for mt360_field, local_field, match_type in field_matches:
            mt360_value = mt360_fields[mt360_field]
            local_value = local_flat[local_field]
            
            mt360_norm = self.normalize_value(mt360_value)
            local_norm = self.normalize_value(local_value)
            
            # Calculate similarity
            if not mt360_norm and not local_norm:
                similarity = 1.0
                status = 'both_empty'
            elif not mt360_norm or not local_norm:
                similarity = 0.0
                status = 'one_empty'
            else:
                similarity = SequenceMatcher(None, mt360_norm, local_norm).ratio()
                
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
                'mt360_field': mt360_field,
                'local_field': local_field,
                'match_type': match_type,
                'mt360_value': str(mt360_value),
                'local_value': str(local_value),
                'mt360_normalized': mt360_norm,
                'local_normalized': local_norm,
                'similarity': similarity,
                'status': status
            })
        
        # Identify unmatched fields
        matched_mt360 = {m[0] for m in field_matches}
        matched_local = {m[1] for m in field_matches}
        
        unmatched_mt360 = [k for k in mt360_fields.keys() if k not in matched_mt360]
        unmatched_local = [k for k in local_flat.keys() if k not in matched_local]
        
        comparison['metrics']['unmatched_mt360_fields'] = len(unmatched_mt360)
        comparison['metrics']['unmatched_local_fields'] = len(unmatched_local)
        
        comparison['unmatched_mt360_fields'] = unmatched_mt360
        comparison['unmatched_local_fields'] = unmatched_local[:20]  # Limit to first 20
        
        # Calculate quality metrics
        if comparison['metrics']['matched_fields'] > 0:
            # Accuracy: (exact + partial * 0.8) / matched
            accuracy_numerator = (
                comparison['metrics']['exact_matches'] + 
                comparison['metrics']['partial_matches'] * 0.8
            )
            comparison['metrics']['accuracy_score'] = accuracy_numerator / comparison['metrics']['matched_fields']
            
            # Precision: correct matches / total MT360 fields
            if comparison['metrics']['total_mt360_fields'] > 0:
                comparison['metrics']['precision'] = accuracy_numerator / comparison['metrics']['total_mt360_fields']
            
            # Recall: correct matches / total local fields
            if comparison['metrics']['total_local_fields'] > 0:
                comparison['metrics']['recall'] = accuracy_numerator / comparison['metrics']['total_local_fields']
        
        # Generate quality assessment
        accuracy = comparison['metrics']['accuracy_score']
        
        if accuracy >= 0.95:
            grade = 'A+ (Excellent)'
            comparison['quality_assessment']['strengths'].append("Very high OCR accuracy")
        elif accuracy >= 0.90:
            grade = 'A (Very Good)'
            comparison['quality_assessment']['strengths'].append("High OCR accuracy")
        elif accuracy >= 0.80:
            grade = 'B (Good)'
            comparison['quality_assessment']['strengths'].append("Good OCR accuracy")
        elif accuracy >= 0.70:
            grade = 'C (Fair)'
            comparison['quality_assessment']['weaknesses'].append("Moderate OCR accuracy issues")
        elif accuracy >= 0.60:
            grade = 'D (Poor)'
            comparison['quality_assessment']['weaknesses'].append("Significant OCR accuracy issues")
        else:
            grade = 'F (Failing)'
            comparison['quality_assessment']['weaknesses'].append("Severe OCR accuracy problems")
        
        comparison['quality_assessment']['overall_grade'] = grade
        
        # Identify specific issues
        high_value_mismatches = []
        for fc in comparison['field_comparisons']:
            if fc['status'] == 'mismatch':
                # Check if this is a critical field (contains money, dates, names, etc.)
                field_lower = fc['mt360_field'].lower()
                if any(term in field_lower for term in ['amount', 'loan', 'rate', 'income', 'value', 'price', 'borrower', 'name']):
                    high_value_mismatches.append(fc['mt360_field'])
        
        if high_value_mismatches:
            comparison['quality_assessment']['weaknesses'].append(
                f"Critical field mismatches: {', '.join(high_value_mismatches[:5])}"
            )
            comparison['quality_assessment']['recommendations'].append(
                "Review and correct high-value fields before using for decision-making"
            )
        
        if comparison['metrics']['unmatched_mt360_fields'] > 10:
            comparison['quality_assessment']['weaknesses'].append(
                f"{comparison['metrics']['unmatched_mt360_fields']} MT360 fields not found in local extraction"
            )
        
        if comparison['metrics']['mismatches'] > comparison['metrics']['exact_matches']:
            comparison['quality_assessment']['recommendations'].append(
                "Consider re-OCRing the document with improved settings"
            )
        
        # Print summary
        print(f"\n{'='*80}")
        print("OCR Quality Assessment")
        print(f"{'='*80}")
        print(f"Overall Grade: {grade}")
        print(f"Accuracy Score: {accuracy:.2%}")
        print(f"Precision: {comparison['metrics']['precision']:.2%}")
        print(f"Recall: {comparison['metrics']['recall']:.2%}")
        print(f"\nDetailed Metrics:")
        print(f"  ✓ Exact Matches: {comparison['metrics']['exact_matches']}")
        print(f"  ≈ Partial Matches: {comparison['metrics']['partial_matches']}")
        print(f"  ✗ Mismatches: {comparison['metrics']['mismatches']}")
        print(f"  ? Unmatched MT360: {comparison['metrics']['unmatched_mt360_fields']}")
        print(f"  ? Unmatched Local: {comparison['metrics']['unmatched_local_fields']}")
        
        if high_value_mismatches:
            print(f"\n⚠ Critical Field Mismatches:")
            for field in high_value_mismatches[:10]:
                print(f"  - {field}")
        
        return comparison
    
    def generate_html_report(self, comparison: Dict, output_file: str = None):
        """Generate HTML report for OCR validation"""
        if output_file is None:
            loan_id = comparison.get('loan_id', 'unknown')
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = f"{self.output_dir}/ocr_validation_report_{loan_id}_{timestamp}.html"
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>MT360 OCR Validation Report - Loan {comparison.get('loan_id')}</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background-color: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #34495e;
            margin-top: 30px;
        }}
        .metric-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}
        .metric-card {{
            background: #ecf0f1;
            padding: 20px;
            border-radius: 6px;
            border-left: 4px solid #3498db;
        }}
        .metric-label {{
            font-weight: bold;
            color: #7f8c8d;
            font-size: 14px;
        }}
        .metric-value {{
            font-size: 28px;
            color: #2c3e50;
            margin-top: 5px;
        }}
        .grade {{
            font-size: 48px;
            font-weight: bold;
            text-align: center;
            padding: 20px;
            margin: 20px 0;
            border-radius: 8px;
        }}
        .grade-a {{ background: #2ecc71; color: white; }}
        .grade-b {{ background: #3498db; color: white; }}
        .grade-c {{ background: #f39c12; color: white; }}
        .grade-d {{ background: #e67e22; color: white; }}
        .grade-f {{ background: #e74c3c; color: white; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background-color: #34495e;
            color: white;
            font-weight: bold;
        }}
        tr:hover {{
            background-color: #f5f5f5;
        }}
        .status-exact {{ color: #27ae60; font-weight: bold; }}
        .status-partial {{ color: #f39c12; font-weight: bold; }}
        .status-mismatch {{ color: #e74c3c; font-weight: bold; }}
        .similarity-bar {{
            height: 20px;
            background-color: #ecf0f1;
            border-radius: 10px;
            overflow: hidden;
        }}
        .similarity-fill {{
            height: 100%;
            background: linear-gradient(90deg, #e74c3c 0%, #f39c12 50%, #27ae60 100%);
        }}
        .section {{
            margin: 30px 0;
            padding: 20px;
            background-color: #f8f9fa;
            border-radius: 6px;
        }}
        .issue-list {{
            list-style: none;
            padding: 0;
        }}
        .issue-list li {{
            padding: 10px;
            margin: 5px 0;
            background: white;
            border-left: 4px solid #e74c3c;
            border-radius: 4px;
        }}
        .strength-list li {{
            border-left-color: #27ae60;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>MT360 OCR Validation Report</h1>
        <p><strong>Loan ID:</strong> {comparison.get('loan_id')}<br>
        <strong>Report Generated:</strong> {comparison.get('comparison_timestamp')}<br>
        <strong>MT360 Source:</strong> <a href="{comparison.get('mt360_source')}">{comparison.get('mt360_source')}</a></p>
        
        <div class="grade grade-{comparison['quality_assessment']['overall_grade'][0].lower()}">
            {comparison['quality_assessment']['overall_grade']}
        </div>
        
        <div class="metric-grid">
            <div class="metric-card">
                <div class="metric-label">Accuracy Score</div>
                <div class="metric-value">{comparison['metrics']['accuracy_score']:.1%}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Exact Matches</div>
                <div class="metric-value">{comparison['metrics']['exact_matches']}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Partial Matches</div>
                <div class="metric-value">{comparison['metrics']['partial_matches']}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Mismatches</div>
                <div class="metric-value">{comparison['metrics']['mismatches']}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Precision</div>
                <div class="metric-value">{comparison['metrics']['precision']:.1%}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Recall</div>
                <div class="metric-value">{comparison['metrics']['recall']:.1%}</div>
            </div>
        </div>
        
        <h2>Quality Assessment</h2>
        
        <div class="section">
            <h3>Strengths</h3>
            <ul class="issue-list strength-list">
                {''.join([f'<li>{s}</li>' for s in comparison['quality_assessment']['strengths']]) or '<li>No specific strengths identified</li>'}
            </ul>
        </div>
        
        <div class="section">
            <h3>Weaknesses</h3>
            <ul class="issue-list">
                {''.join([f'<li>{w}</li>' for w in comparison['quality_assessment']['weaknesses']]) or '<li>No significant weaknesses identified</li>'}
            </ul>
        </div>
        
        <div class="section">
            <h3>Recommendations</h3>
            <ul class="issue-list">
                {''.join([f'<li>{r}</li>' for r in comparison['quality_assessment']['recommendations']]) or '<li>No specific recommendations</li>'}
            </ul>
        </div>
        
        <h2>Field-by-Field Comparison</h2>
        <table>
            <thead>
                <tr>
                    <th>MT360 Field</th>
                    <th>MT360 Value</th>
                    <th>Local Value</th>
                    <th>Status</th>
                    <th>Similarity</th>
                </tr>
            </thead>
            <tbody>
"""
        
        # Add rows for each field comparison
        for fc in sorted(comparison['field_comparisons'], key=lambda x: x['similarity']):
            status_class = fc['status'].replace('_', '-')
            similarity_pct = fc['similarity'] * 100
            
            html += f"""
                <tr>
                    <td><strong>{fc['mt360_field']}</strong></td>
                    <td>{fc['mt360_value'][:100]}</td>
                    <td>{fc['local_value'][:100]}</td>
                    <td class="status-{status_class}">{fc['status'].replace('_', ' ').title()}</td>
                    <td>
                        <div class="similarity-bar">
                            <div class="similarity-fill" style="width: {similarity_pct}%"></div>
                        </div>
                        {similarity_pct:.0f}%
                    </td>
                </tr>
"""
        
        html += """
            </tbody>
        </table>
        
        <div class="section">
            <h3>Unmatched Fields</h3>
            <p><strong>Fields in MT360 but not in local extraction:</strong></p>
            <ul>
"""
        
        for field in comparison.get('unmatched_mt360_fields', [])[:20]:
            html += f"                <li>{field}</li>\n"
        
        html += """
            </ul>
        </div>
    </div>
</body>
</html>
"""
        
        with open(output_file, 'w') as f:
            f.write(html)
        
        print(f"\n✓ HTML report generated: {output_file}")
        return output_file


def main():
    """Main execution"""
    validator = OCRQualityValidator()
    
    # Load MT360 data
    mt360_file = "/Users/sunny/Applications/bts/jpmorgan/mortgage/modda/outputs/mt360_validation/mt360_1008_loan_1642451_manual.json"
    
    print(f"\n{'='*80}")
    print("MT360 OCR Quality Validation")
    print(f"{'='*80}")
    print(f"Loading MT360 data from: {mt360_file}")
    
    with open(mt360_file, 'r') as f:
        mt360_data = json.load(f)
    
    # Load local extraction
    loan_id = mt360_data['loan_id']
    local_data = validator.load_local_1008_extraction(loan_id)
    
    if not local_data:
        print("✗ Cannot proceed without local extraction data")
        return
    
    # Compare
    comparison = validator.compare_extractions(mt360_data, local_data)
    
    # Save comparison results
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    json_file = f"{validator.output_dir}/ocr_comparison_{loan_id}_{timestamp}.json"
    
    with open(json_file, 'w') as f:
        json.dump(comparison, f, indent=2)
    
    print(f"\n✓ Comparison results saved: {json_file}")
    
    # Generate HTML report
    html_file = validator.generate_html_report(comparison)
    
    print(f"\n{'='*80}")
    print("Validation Complete!")
    print(f"{'='*80}")
    print(f"View the HTML report at: file://{html_file}")


if __name__ == '__main__':
    main()


