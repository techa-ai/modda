import json
import sys
import os
from db import execute_query
from vlm_utils import VLMClient

def classify_global(loan_id):
    print(f"Fetching all documents for Loan {loan_id}...")
    
    # Fetch Data - use document_summary instead of full individual_analysis
    query = """
    SELECT id, filename, 
           COALESCE(individual_analysis->>'document_summary', '{}'::text)::jsonb as document_summary,
           detected_date, file_size
    FROM document_analysis
    WHERE loan_id = %s
    ORDER BY filename
    """
    rows = execute_query(query, (loan_id,))
    
    print(f"Found {len(rows)} documents.")
    
    # Prepare payload - use only document_summary to reduce tokens
    docs = []
    for r in rows:
        summary = r.get('document_summary') or {}
        docs.append({
            "id": r['id'],
            "name": r['filename'],
            "date": str(r['detected_date']) if r['detected_date'] else "Unknown",
            "extracted_data": summary  # Use summary instead of full analysis
        })
    
    # Prompt
    prompt = """
    You are a senior mortgage underwriter and compliance officer.
    I am providing you with the extraction data for ALL documents in a loan file.
    
    TASK 1: CLASSIFICATION & DETAILS
    For EACH document, determine:
    - classification: "FINANCIAL" (Income, Assets, Credit, Loan Terms) or "NON-FINANCIAL" (Admin, Disclosures).
    - doc_type: Standard Industry Name (e.g., "URLA 1003", "Form 1008", "Closing Disclosure", "W-2", "Paystub", "Bank Statement").
    - doc_date: The document date (YYYY-MM-DD) or "Unknown".
    - signers: "Borrower", "Co-Borrower", "Both", or "Unsigned".
    - signed_status: "Signed" or "Unsigned".
    
    TASK 2: GROUPING
    Assign a 'group_id' (string) to group related documents.
    - Group siblings (Borrower W-2 + Co-Borrower W-2) together.
    - Group versions (Signed URLA + Unsigned URLA) together.
    - Group duplicates together.
    - Group Description: A human-readable name for the group (e.g., "W-2 Forms (2024)", "Loan Estimates").
    - Group Rationale: Why these documents belong together.
    
    TASK 3: PRIMARY DOCUMENT SELECTION
    For each group, identify the "Primary" document(s).
    - A group implies a single logical requirement (e.g. "Proof of Income").
    - SELECT the Best/Latest version as Primary.
    - CRITICAL: If a group contains distinct documents for distinct entities (e.g. Borrower's W-2 AND Co-Borrower's W-2), BOTH are Primary.
    - CRITICAL: If a group contains Signed and Unsigned versions, the SIGNED, LATEST dated version is Primary.
    - Primary Rationale: Why this document was selected (e.g., "Latest signed version", "Co-borrower's distinct document").
    
    OUTPUT FORMAT:
    Return a strictly valid JSON object with a "results" key containing a list.
    {
      "results": [
        {
          "id": <doc_id>,
          "classification": "FINANCIAL" | "NON-FINANCIAL",
          "doc_type": "...",
          "doc_date": "YYYY-MM-DD",
          "signers": "...",
          "signed_status": "...",
          "reason": "<specific doc reasoning>",
          "group_id": "<id>",
          "group_description": "...",
          "group_reason": "<grouping rationale>",
          "is_primary": true | false,
          "primary_reason": "<why primary?>"
        },
        ...
      ]
    }
    
    ENSURE YOU RETURN RESULTS FOR EVERY SINGLE DOCUMENT provided in the input list.
    """
    
    print("Sending to Claude (max_tokens=60000)...")
    
    client = VLMClient(max_tokens=60000)
    
    try:
        response = client.process_text(
            text=json.dumps(docs),
            prompt=prompt,
            return_json=True
        )
    except Exception as e:
        print(f"Error calling VLM: {e}")
        return

    # Handle String Response (Markdown cleanup)
    if isinstance(response, str):
        print("Received raw string (likely valid JSON wrapped in Markdown). Cleaning...")
        cleaned = response.replace("```json", "").replace("```", "").strip()
        try:
            response = json.loads(cleaned)
        except Exception as e:
            print(f"FAILED to parse cleaned JSON: {e}")
            # Fallback: try to find first { and last }
            try:
                start = cleaned.find('{')
                end = cleaned.rfind('}') + 1
                if start >= 0 and end > start:
                    response = json.loads(cleaned[start:end])
                else:
                    return
            except:
                return

    if not response or not isinstance(response, dict) or 'results' not in response:
        print("Invalid response from VLM (missing 'results' key).")
        return
        
    results = response['results']
    print(f"Received {len(results)} results.")
    
    # Save
    print("Saving to database...")
    count = 0
    for res in results:
        doc_id = res.get('id')
        if not doc_id: continue
        
        # Merge into version_metadata
        meta_update = {
            "financial_category": res.get("classification"),
            "financial_reason": res.get("reason"),
            "ai_group_id": res.get("group_id"),
            "ai_group_reason": res.get("group_reason"),
            "doc_type": res.get("doc_type"),
            "doc_date_ai": res.get("doc_date"),
            "signers": res.get("signers"),
            "signed_status": res.get("signed_status"),
            "ai_group_description": res.get("group_description"),
            "is_primary": res.get("is_primary"),
            "primary_reason": res.get("primary_reason")
        }
        
        update_sql = """
            UPDATE document_analysis
            SET version_metadata = COALESCE(version_metadata, '{}'::jsonb) || %s::jsonb
            WHERE id = %s
        """
        execute_query(update_sql, (json.dumps(meta_update), doc_id), fetch=False)
        count += 1
        
    print(f"Done. {count} classifications persisted.")

if __name__ == "__main__":
    import sys
    loan_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    classify_global(loan_id)
