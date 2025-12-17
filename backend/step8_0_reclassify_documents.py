import sys
import json
import os
import traceback
from PyPDF2 import PdfReader
from db import get_db_connection, execute_query
from bedrock_config import call_bedrock
from processing import extract_json_from_text, pdf_to_base64

def run_reclassification(loan_id):
    print(f"🔄 Starting Document Reclassification (Step 8.0) for Loan {loan_id}...")
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # 1. Fetch all latest documents
        cur.execute("""
            SELECT id, filename, file_path, version_metadata
            FROM document_analysis
            WHERE loan_id = %s AND is_latest_version = TRUE
            ORDER BY filename
        """, (loan_id,))
        
        docs = cur.fetchall()
        print(f"Found {len(docs)} documents to classify.")
        
        for doc in docs:
            doc_id = doc['id']
            filename = doc['filename']
            file_path = doc['file_path']
            meta = doc['version_metadata'] or {}
            
            print(f"\n📄 Analyzing: {filename}")
            
            # Extract text from PDF
            context = ""
            if os.path.exists(file_path):
                try:
                    reader = PdfReader(file_path)
                    text = ""
                    # Read first 3 pages max
                    for i in range(min(3, len(reader.pages))):
                        text += reader.pages[i].extract_text() + "\n"
                    
                    if len(text.strip()) > 50:
                        context = text[:5000]
                    else:
                        context = f"Filename: {filename}. (Scanned PDF or Empty)"
                except Exception as e:
                    context = f"Filename: {filename}. Error reading PDF: {e}"
            else:
                print(f"   ⚠️ File missing: {file_path}")
                continue

            current_cat = meta.get('financial_category', 'UNKNOWN')
            print(f"   Current Category: {current_cat}")
            
            prompt = f"""
You are a Mortgage Document Classifier.
Determine if the following document is "FINANCIAL" or "NON-FINANCIAL" for underwriting purposes.

DOCUMENT INFO:
Filename: {filename}
Preview Content:
{context}

DEFINITIONS:
- FINANCIAL: Contains numbers/data used for verifying Income, Assets, Liabilities, Credit, Property Value, Loan Terms, or Tax Calculations.
  Examples: Paystubs, W-2s, Tax Returns (1040/1120/1065/K-1), Bank Statements, Investment Statements, Retirement Acct, 1003/URLA, 1008/Transmittal, Credit Report, Appraisal, Note, Mortgage, HELOC Agreement, Lease Agreement, Insurance Policy, Closing Disclosure, Loan Estimate, VVOE (Verification of Employment) with income.
  
- NON-FINANCIAL: Informational, procedural, or blank forms that do not contain hard underwriting numbers.
  Examples: E-Consent, Tax Transcripts Request (4506-T) (blank/signed only), Fraud Alerts, Privacy Notice, SSA Authorization, Flood Certificate (unless used for insurance calc, usually non-financial), Title Commitment (unless used for tax/lien amount, usually legal), Instructions, Blank Forms, ID Cards (Drivers License).

TASK:
Classify the document.

OUTPUT JSON:
{{
  "category": "FINANCIAL" or "NON-FINANCIAL",
  "reason": "Brief explanation"
}}
"""
            try:
                # Use Haiku for speed/cost as this is simple classification
                response = call_bedrock(prompt, model='claude-haiku-3-5-20241022-v1:0', max_tokens=300)
                result = extract_json_from_text(response)
                
                if result:
                    new_cat = result.get('category')
                    reason = result.get('reason')
                    
                    if new_cat:
                        # Update DB
                        meta['financial_category'] = new_cat
                        meta['classification_reason'] = reason
                        
                        execute_query(
                            "UPDATE document_analysis SET version_metadata = %s WHERE id = %s",
                            (json.dumps(meta), doc_id),
                            fetch=False
                        )
                        
                        # Visual indicator of change
                        arrow = "=>" if new_cat != current_cat else "=="
                        print(f"   {arrow} {new_cat} ({reason})")
                    else:
                        print("   ⚠️ Failed to classify (no category returned)")
                else:
                    print("   ⚠️ Failed to parse Claude response")
                    
            except Exception as e:
                print(f"   ❌ Error calling Claude: {e}")

    except Exception as e:
        traceback.print_exc()
    finally:
        conn.close()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_reclassification(int(sys.argv[1]))
    else:
        print("Usage: python3 step8_0_reclassify_documents.py <loan_id>")

