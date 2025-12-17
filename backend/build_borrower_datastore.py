#!/usr/bin/env python3
"""
Build borrower-specific datastore by processing pagewise extraction in batches.
Each batch enriches the existing datastore with new borrower-relevant information.
"""
import json
import os
from typing import Dict, Any, List
from bedrock_config import call_bedrock

BORROWER_NAME = "ROBERT M DUGAN"
BORROWER_ALIASES = ["ROBERT M DUGAN", "ROBERT DUGAN", "ROBERT M. DUGAN"]

def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token"""
    return len(text) // 4

def create_batches(pages: List[Dict], max_tokens_per_batch: int = 70000) -> List[List[Dict]]:
    """Split pages into batches that fit within token limit (conservative estimate)."""
    batches = []
    current_batch = []
    current_tokens = 0
    
    for page in pages:
        page_json = json.dumps(page)
        page_tokens = estimate_tokens(page_json)
        
        if current_tokens + page_tokens > max_tokens_per_batch and current_batch:
            batches.append(current_batch)
            current_batch = [page]
            current_tokens = page_tokens
        else:
            current_batch.append(page)
            current_tokens += page_tokens
    
    if current_batch:
        batches.append(current_batch)
    
    return batches

def extract_borrower_info(pages_batch: List[Dict], existing_datastore: Dict[str, Any], batch_num: int, total_batches: int) -> Dict[str, Any]:
    """
    Send batch to Claude Opus 4.5 to extract/enrich borrower information.
    """
    prompt = f"""You are analyzing tax documents for borrower: {BORROWER_NAME}

This is BATCH {batch_num} of {total_batches}.

BORROWER ALIASES: {', '.join(BORROWER_ALIASES)}

YOUR TASK:
Extract and organize ALL information relevant to the borrower from these pages. Focus on:

1. **Income Sources** (W-2 wages, K-1 distributions, self-employment income, etc.)
2. **Employment** (Employers, positions, entities where borrower is shareholder/partner)
3. **Business Ownership** (S-Corps, partnerships, ownership percentages, basis calculations)
4. **Assets** (Real estate, investments, basis, depreciation)
5. **Tax Returns** (Forms 1040, state returns, years, AGI, taxable income)
6. **Key Financial Figures** (Total income, deductions, taxes paid, distributions received)
7. **Dependents/Family** (If mentioned)
8. **Addresses** (Residential, business)

**CRITICAL: Every data point MUST include page number(s) for audit trail.**

EXISTING DATASTORE (enrich this with new information):
{json.dumps(existing_datastore, indent=2) if existing_datastore else "{}"}

PAGES TO ANALYZE:
{json.dumps(pages_batch, indent=2)}

OUTPUT REQUIREMENTS:
- JSON format only
- **EVERY data item MUST have "pages" array with page numbers**
- Merge/enrich existing datastore with new findings
- For values appearing on multiple pages, list ALL page numbers
- Group by category (income, employment, businesses, tax_returns, etc.)
- Keep it concise - only borrower-relevant data
- Preserve all page references for audit compliance

OUTPUT JSON STRUCTURE (with page numbers for EVERY item):
{{
  "borrower_name": "{BORROWER_NAME}",
  "income": [
    {{
      "source": "W-2 wages",
      "employer": "THOR GUARD, INC.",
      "year": 2023,
      "amount": 158000,
      "pages": [1],
      "details": {{"box_1_wages": 158000, "box_2_federal_tax": 20400}}
    }},
    {{
      "source": "K-1 ordinary income",
      "entity": "THOR GUARD, INC.",
      "year": 2023,
      "amount": 16277.42,
      "pages": [3, 7],
      "details": {{"shareholder_pct": 6.67, "distributions": 400}}
    }}
  ],
  "employment": [
    {{
      "employer": "THOR GUARD, INC.",
      "position": "Officer/Shareholder",
      "years": [2023, 2024],
      "pages": [1, 2, 3]
    }}
  ],
  "business_ownership": [
    {{
      "entity": "THOR GUARD, INC.",
      "type": "S-Corporation",
      "ein": "65-0057716",
      "ownership_pct": 6.67,
      "shares": 100000,
      "total_shares": 1500000,
      "pages": [3, 10, 122],
      "stock_basis": {{"beginning": 10581, "ending": 12796, "year": 2023, "pages": [122]}}
    }}
  ],
  "tax_returns": [
    {{
      "form": "Form 1040",
      "year": 2023,
      "agi": 150000,
      "total_income": 175000,
      "total_tax": 20000,
      "pages": [...]
    }}
  ],
  "assets": [...],
  "addresses": [
    {{"type": "residential", "address": "1821 CANBY CT, MARCO ISLAND, FL 34145", "pages": [1]}}
  ],
  "notes": "Any other relevant observations"
}}

**REMEMBER: Include page numbers for EVERY data point!**

Return ONLY the JSON."""
    
    print(f"   📤 Sending batch {batch_num}/{total_batches} to Claude Opus 4.5...")
    response = call_bedrock(
        prompt=prompt,
        model="claude-opus-4-5",
        max_tokens=8000
    )
    
    # Parse response
    try:
        # Try direct parse
        datastore = json.loads(response.strip())
        return datastore
    except:
        # Try to salvage
        text = response.strip()
        if '```json' in text:
            text = text.split('```json')[1].split('```')[0]
        elif '```' in text:
            text = text.split('```')[1].split('```')[0]
        try:
            datastore = json.loads(text.strip())
            return datastore
        except Exception as e:
            print(f"   ⚠️  JSON parse error: {e}")
            # Save raw response for debugging
            with open(f'/tmp/batch_{batch_num}_error.txt', 'w') as f:
                f.write(response)
            return existing_datastore  # Return unchanged

def main():
    input_file = "/Users/sunny/Applications/bts/jpmorgan/mortgage/modda/outputs/ocr/tax_returns_65/pagewise_extract_vision.json"
    output_file = "/Users/sunny/Applications/bts/jpmorgan/mortgage/modda/outputs/ocr/tax_returns_65/borrower_datastore.json"
    
    print(f"🚀 Building borrower datastore from pagewise extraction")
    print(f"   Borrower: {BORROWER_NAME}")
    print(f"   Input: {input_file}")
    print()
    
    # Load all pages
    with open(input_file, 'r') as f:
        data = json.load(f)
    
    pages = data.get('pages', [])
    print(f"📄 Loaded {len(pages)} pages")
    
    # Create batches (reduced to 70K to account for prompt overhead and growing datastore)
    batches = create_batches(pages, max_tokens_per_batch=70000)
    total_batches = len(batches)
    print(f"📦 Split into {total_batches} batches (~70K tokens each for safety)")
    print()
    
    # Process batches iteratively
    borrower_datastore = {}
    
    for i, batch in enumerate(batches, 1):
        print(f"🔄 Processing batch {i}/{total_batches} ({len(batch)} pages)...")
        
        try:
            borrower_datastore = extract_borrower_info(
                pages_batch=batch,
                existing_datastore=borrower_datastore,
                batch_num=i,
                total_batches=total_batches
            )
            
            # Save incrementally
            output = {
                'borrower_name': BORROWER_NAME,
                'borrower_aliases': BORROWER_ALIASES,
                'processed_batches': i,
                'total_batches': total_batches,
                'datastore': borrower_datastore
            }
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(output, f, indent=2, ensure_ascii=False)
            
            print(f"   ✅ Batch {i} complete - datastore saved")
            print()
            
        except Exception as e:
            print(f"   ❌ Error processing batch {i}: {e}")
            print(f"   Continuing with existing datastore...")
            print()
    
    print(f"✅ COMPLETE: Borrower datastore created")
    print(f"   Output: {output_file}")
    print(f"   Processed: {total_batches} batches")
    
    # Print summary
    if borrower_datastore:
        print()
        print("📊 Datastore Summary:")
        for key, value in borrower_datastore.items():
            if isinstance(value, list):
                print(f"   {key}: {len(value)} items")
            elif isinstance(value, dict):
                print(f"   {key}: {len(value)} entries")
            else:
                print(f"   {key}: {value}")

if __name__ == "__main__":
    main()

