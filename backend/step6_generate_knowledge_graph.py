#!/usr/bin/env python3
"""
Step 6: Generate Knowledge Graph from Deep JSON

Processes ONLY LATEST VERSION documents with deep JSON extractions in batches,
building a comprehensive knowledge graph with entities and relationships.
Uses iterative refinement to handle documents exceeding Opus context limits.

CRITICAL: Only includes documents where is_latest_version = TRUE to avoid
duplicate/conflicting information from preliminary/superseded versions.

Knowledge Graph Structure:
- Nodes: Loan, Document, Version, Value, Rule, Adjustment, Source
- Edges: HAS_DOCUMENT, HAS_VERSION, EXTRACTED_FROM, REFERS_TO, etc.
"""

import os
import sys
import json
import argparse
from datetime import datetime
from db import execute_query, execute_one
from bedrock_config import call_bedrock

BATCH_SIZE = 100000  # 100K tokens = ~400K chars (leaves room for rich prompt template)

def chunk_document_json(docs, batch_size_chars=400000):
    """Split documents into batches that fit in context"""
    batches = []
    current_batch = []
    current_size = 0
    
    for doc in docs:
        doc_json = json.dumps(doc)
        doc_size = len(doc_json)
        
        if current_size + doc_size > batch_size_chars and current_batch:
            batches.append(current_batch)
            current_batch = []
            current_size = 0
        
        current_batch.append(doc)
        current_size += doc_size
    
    if current_batch:
        batches.append(current_batch)
    
    return batches

def extract_knowledge_graph_batch(batch_docs, existing_graph=None, batch_num=1, total_batches=1):
    """Extract knowledge graph from a batch of documents using Claude Opus"""
    
    prompt = f"""You are analyzing loan documents to build a comprehensive knowledge graph.

{'EXISTING KNOWLEDGE GRAPH (built from previous batches):' if existing_graph else 'This is the FIRST batch - create a new knowledge graph.'}
{json.dumps(existing_graph, indent=2) if existing_graph else ''}

NEW DOCUMENTS TO PROCESS (Batch {batch_num}/{total_batches}):
{json.dumps(batch_docs, indent=2)}

---

Your task: {'Update and refine' if existing_graph else 'Create'} a knowledge graph following this exact structure:

```json
{{
  "nodes": [
    {{
      "id": "unique_id",
      "type": "Loan|Document|Version|Value|Rule|Adjustment|Source|Person|Property|Company",
      "properties": {{
        "name": "...",
        "...": "..."
      }}
    }}
  ],
  "edges": [
    {{
      "from": "node_id",
      "to": "node_id",
      "type": "HAS_DOCUMENT|HAS_VERSION|EXTRACTED_FROM|REFERS_TO|APPLIES_TO|AUTHORED_BY|DERIVED_FROM|INGESTED_FROM",
      "properties": {{
        "...": "..."
      }}
    }}
  ]
}}
```

## Core Entity Types:

1. **Loan**: The mortgage loan itself
   - Properties: loan_number, amount, rate, term, purpose, ltv, dti, status

2. **Document**: Physical documents in the loan file
   - Properties: filename, type (1008, URLA, Credit, Appraisal, etc.), page_count, date, version

3. **Version**: Preliminary/final variants with timestamps
   - Properties: version_indicator, timestamp, source_system

4. **Value**: Extracted data points (amounts, dates, names, SSNs)
   - Properties: amount, currency, units, confidence, extraction_method, effective_date

5. **Person**: Borrower, co-borrower, underwriter, seller, etc.
   - Properties: name, ssn, role, employer, income, credit_score

6. **Property**: Subject property details
   - Properties: address, appraisal_value, purchase_price, type, occupancy

7. **Company**: Lenders, employers, insurers, title companies
   - Properties: name, role, contact, account_numbers

8. **Rule**: Domain logic (Prop 13 reassessment, underwriting guidelines)
   - Properties: rule_name, parameters, jurisdiction

9. **Adjustment**: Underwriter overrides, counteroffers, exceptions
   - Properties: reason, comment, reference, approval_status, timestamp

10. **Source**: System of record, ingestion pipeline, manual upload
    - Properties: source_name, timestamp, confidence

## Key Relationships:

- HAS_DOCUMENT (Loan → Document)
- HAS_VERSION (Document → Version)  
- EXTRACTED_FROM (Value → Document/Version)
- REFERS_TO (Document → Value for cross-references)
- APPLIES_TO (Rule → Document/Adjustment)
- AUTHORED_BY (Document/Adjustment → Person)
- DERIVED_FROM (Value → Value for calculations)
- INGESTED_FROM (Document → Source)

## Processing Rules:

1. **Deverbose**: Extract only KEY information, remove redundant text
2. **Deduplicate**: Merge similar nodes (same person mentioned in multiple docs)
3. **Normalize**: Standardize formats (dates, amounts, names)
4. **Link**: Create edges between related entities
5. **Preserve**: Keep critical values, dates, amounts, rationale
6. **Confidence**: Include confidence scores for extracted values

{"## Update Instructions:" if existing_graph else "## Creation Instructions:"}

{"- ADD new nodes/edges found in this batch" if existing_graph else "- Create initial graph structure"}
{"- UPDATE existing nodes with new information" if existing_graph else "- Focus on core entities first"}
{"- MERGE duplicate entities across batches" if existing_graph else "- Establish key relationships"}
{"- REMOVE contradictory/outdated information" if existing_graph else "- Be thorough but concise"}
{"- MAINTAIN consistency with existing graph" if existing_graph else ""}

Return ONLY the updated knowledge graph JSON. No explanations."""

    try:
        response = call_bedrock(
            prompt,
            model="claude-opus-4-5",
            max_tokens=32000,  # Increase to handle large graphs
            temperature=0.1
        )
        
        if response:
            # Remove markdown code fences if present
            response_clean = response.strip()
            if response_clean.startswith('```'):
                # Remove opening fence
                lines = response_clean.split('\n')
                if lines[0].startswith('```'):
                    lines = lines[1:]
                # Remove closing fence
                if lines and lines[-1].strip() == '```':
                    lines = lines[:-1]
                response_clean = '\n'.join(lines)
            
            # Try to parse JSON - if incomplete, attempt to fix
            try:
                graph = json.loads(response_clean)
                return graph
            except json.JSONDecodeError as e:
                # Try to salvage incomplete JSON by finding last valid position
                print(f"⚠️  JSON parse error at position {e.pos}: {e.msg}")
                print(f"   Attempting to salvage partial response...")
                
                # Find the last complete node or edge
                last_bracket = response_clean.rfind('}')
                if last_bracket > 0:
                    # Try adding closing brackets
                    for attempt in [
                        response_clean[:last_bracket+1] + ']}',
                        response_clean[:last_bracket+1] + ']}}',
                        response_clean[:last_bracket+1] + ']}}'
                    ]:
                        try:
                            graph = json.loads(attempt)
                            print(f"   ✅ Salvaged partial response")
                            return graph
                        except:
                            continue
                
                # If salvage failed, return None
                print(f"   ❌ Could not salvage response")
                raise e
        else:
            print("❌ No response from Opus")
            return None
            
    except json.JSONDecodeError as e:
        print(f"❌ Failed to parse JSON response: {e}")
        print(f"Response preview: {response[:500] if response else 'None'}")
        return None
    except Exception as e:
        print(f"❌ Error calling Opus: {e}")
        return None

def generate_knowledge_graph(loan_id, dry_run=False):
    """Generate knowledge graph for a loan from deep JSON"""
    import sys
    from datetime import datetime
    
    def log(message):
        """Log with timestamp and flush immediately"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {message}")
        sys.stdout.flush()
    
    log("=" * 100)
    log(f"STEP 8: GENERATE KNOWLEDGE GRAPH - LOAN {loan_id}")
    log("=" * 100)
    log("")
    
    # Get loan info
    loan = execute_one("SELECT * FROM loans WHERE id = %s", (loan_id,))
    if not loan:
        log(f"❌ Loan {loan_id} not found")
        return None
    
    log(f"Loan Number: {loan['loan_number']}")
    log(f"Status: {loan['status']}")
    log("")
    
    # Check if we have existing knowledge graph (for resume capability)
    existing_kg = loan.get('knowledge_graph')
    if existing_kg:
        log("🔄 EXISTING KNOWLEDGE GRAPH FOUND!")
        log("   This will be used as the starting point (resume mode)")
        existing_nodes = len(existing_kg.get('nodes', [])) if isinstance(existing_kg, dict) else 0
        existing_edges = len(existing_kg.get('edges', [])) if isinstance(existing_kg, dict) else 0
        log(f"   Existing: {existing_nodes} nodes, {existing_edges} edges")
        log("")
    else:
        log("🆕 Starting fresh knowledge graph generation")
        log("")
    
    # First, check how many documents are excluded
    all_docs = execute_one("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN is_latest_version = true THEN 1 ELSE 0 END) as latest,
            SUM(CASE WHEN is_latest_version = false THEN 1 ELSE 0 END) as superseded
        FROM document_analysis
        WHERE loan_id = %s 
        AND status IN ('unique', 'master', 'active', 'superseded', 'duplicate')
        AND individual_analysis IS NOT NULL
    """, (loan_id,))
    
    if all_docs:
        log(f"📊 Document Version Filtering:")
        log(f"   Total with deep JSON: {all_docs['total']}")
        log(f"   Latest versions: {all_docs['latest']} ✅ (will be included)")
        log(f"   Superseded versions: {all_docs['superseded']} ❌ (will be excluded)")
        log("")
    
    # Get ONLY latest/master version documents with full deep JSON
    # This ensures we don't include superseded versions in the knowledge graph
    log("🔍 Loading documents from database...")
    log(f"   Query: status IN ('unique','master','active') AND is_latest_version=true")
    
    docs = execute_query("""
        SELECT 
            id,
            filename,
            page_count,
            status,
            is_latest_version,
            individual_analysis
        FROM document_analysis
        WHERE loan_id = %s 
        AND status IN ('unique', 'master', 'active')
        AND is_latest_version = true
        AND individual_analysis IS NOT NULL
        ORDER BY 
            CASE 
                WHEN filename ILIKE '%%1008%%' THEN 1
                WHEN filename ILIKE '%%urla%%' THEN 2
                WHEN filename ILIKE '%%credit%%' THEN 3
                WHEN filename ILIKE '%%appraisal%%' THEN 4
                WHEN filename ILIKE '%%purchase%%' THEN 5
                ELSE 6
            END,
            filename
    """, (loan_id,))
    
    log(f"✅ Loaded {len(docs)} documents from database")
    
    if not docs:
        log("❌ No latest version documents with deep JSON found")
        return None
    
    # Show breakdown
    latest_count = sum(1 for d in docs if d.get('is_latest_version'))
    log(f"Documents: {len(docs)} (latest versions only)")
    log(f"  - Status breakdown:")
    status_counts = {}
    for d in docs:
        status = d.get('status', 'unknown')
        status_counts[status] = status_counts.get(status, 0) + 1
    for status, count in sorted(status_counts.items()):
        log(f"    - {status}: {count}")
    
    # Calculate total size
    log("")
    log("📏 Calculating data size...")
    total_chars = sum(len(json.dumps(d['individual_analysis'])) for d in docs)
    total_tokens = total_chars / 4 / 1000
    
    log(f"Total JSON size: {total_chars:,} chars ({total_tokens:,.0f}K tokens)")
    
    # Split into batches
    batches = chunk_document_json(docs, batch_size_chars=400000)
    log(f"Batches: {len(batches)} (max ~100K tokens each)")
    log("")
    
    if dry_run:
        log("[DRY RUN] Would process batches to build knowledge graph")
        for i, batch in enumerate(batches, 1):
            batch_chars = sum(len(json.dumps(d['individual_analysis'])) for d in batch)
            log(f"  Batch {i}: {len(batch)} docs, {batch_chars:,} chars (~{batch_chars/4/1000:.0f}K tokens)")
        return None
    
    # Initialize knowledge graph (resume from existing if available)
    knowledge_graph = existing_kg if existing_kg else None
    
    for i, batch in enumerate(batches, 1):
        batch_chars = sum(len(json.dumps(d['individual_analysis'])) for d in batch)
        log("="*100)
        log(f"Processing Batch {i}/{len(batches)}")
        log("="*100)
        log(f"Documents in batch: {len(batch)}")
        log(f"Batch size: {batch_chars:,} chars (~{batch_chars/4/1000:.0f}K tokens)")
        
        # Build document list for this batch
        batch_docs = []
        for doc in batch:
            batch_docs.append({
                'filename': doc['filename'],
                'page_count': doc['page_count'],
                'content': doc['individual_analysis']
            })
        
        log(f"📤 Sending to Opus 4.5...")
        
        # Extract/update knowledge graph
        updated_graph = extract_knowledge_graph_batch(
            batch_docs,
            existing_graph=knowledge_graph,
            batch_num=i,
            total_batches=len(batches)
        )
        
        if updated_graph:
            knowledge_graph = updated_graph
            
            # Calculate graph size
            graph_json = json.dumps(knowledge_graph, indent=2)
            graph_chars = len(graph_json)
            graph_tokens = graph_chars / 4 / 1000
            
            log(f"✅ Batch {i} processed")
            log(f"   Nodes: {len(knowledge_graph.get('nodes', []))}")
            log(f"   Edges: {len(knowledge_graph.get('edges', []))}")
            log(f"   Graph size: {graph_chars:,} chars ({graph_tokens:.0f}K tokens)")
            
            # Show compression ratio
            processed_chars = sum(sum(len(json.dumps(d['individual_analysis'])) for d in b) for b in batches[:i])
            compression_ratio = (1 - graph_chars / processed_chars) * 100 if processed_chars > 0 else 0
            log(f"   Compression: {compression_ratio:.1f}% (vs {processed_chars:,} chars processed)")
            
            # 💾 SAVE PROGRESS AFTER EACH BATCH
            log(f"   💾 Saving progress to database...")
            try:
                execute_query("""
                    UPDATE loans 
                    SET knowledge_graph = %s,
                        kg_generated_at = NOW(),
                        updated_at = NOW()
                    WHERE id = %s
                """, (json.dumps(knowledge_graph), loan_id), fetch=False)
                log(f"   ✅ Progress saved (batch {i}/{len(batches)})")
            except Exception as save_error:
                log(f"   ⚠️  Warning: Failed to save progress: {save_error}")
                # Continue anyway - we have the graph in memory
        else:
            log(f"❌ Failed to process batch {i}")
            return None
        
        log("")
    
    print("=" * 100)
    print("KNOWLEDGE GRAPH GENERATION COMPLETE")
    print("=" * 100)
    print()
    
    graph_json = json.dumps(knowledge_graph, indent=2)
    graph_chars = len(graph_json)
    graph_tokens = graph_chars / 4 / 1000
    
    print(f"📊 Final Statistics:")
    print(f"   Total Nodes: {len(knowledge_graph.get('nodes', []))}")
    print(f"   Total Edges: {len(knowledge_graph.get('edges', []))}")
    print(f"   Graph Size: {graph_chars:,} chars ({graph_tokens:.0f}K tokens)")
    print()
    print(f"💾 Compression Results:")
    print(f"   Original JSON: {total_chars:,} chars ({total_tokens:.0f}K tokens)")
    print(f"   Knowledge Graph: {graph_chars:,} chars ({graph_tokens:.0f}K tokens)")
    print(f"   Reduction: {((1 - graph_chars/total_chars) * 100):.1f}%")
    print(f"   Savings: {(total_tokens - graph_tokens):.0f}K tokens")
    print()
    
    # Final save already done after last batch
    print("✅ Knowledge graph saved to database")
    print("=" * 100)
    
    return knowledge_graph

def generate_summary_from_kg(loan_id):
    """Generate loan summary from knowledge graph using Opus"""
    
    # Get knowledge graph from database
    loan = execute_one("""
        SELECT knowledge_graph, loan_number 
        FROM loans 
        WHERE id = %s
    """, (loan_id,))
    
    if not loan or not loan['knowledge_graph']:
        print(f"❌ No knowledge graph found for loan {loan_id}")
        return None
    
    kg = loan['knowledge_graph']
    kg_json = json.dumps(kg, indent=2)
    kg_tokens = len(kg_json) / 4 / 1000
    
    print(f"\n{'='*80}")
    print(f"GENERATING SUMMARY FROM KNOWLEDGE GRAPH - LOAN {loan_id}")
    print(f"{'='*80}")
    print(f"Loan Number: {loan['loan_number']}")
    print(f"Graph size: {len(kg_json):,} chars ({kg_tokens:.0f}K tokens)")
    print(f"Nodes: {len(kg.get('nodes', []))}")
    print(f"Edges: {len(kg.get('edges', []))}")
    
    # Create prompt
    prompt = f"""You are a senior mortgage underwriter. Generate a comprehensive loan summary from this knowledge graph.

KNOWLEDGE GRAPH:
{kg_json}

Generate a detailed summary following this format:

# LOAN SUMMARY

## 1. BORROWER PROFILE
### Primary Borrower
- Name, SSN, Employment, Income
### Co-Borrower (if applicable)
### Total Qualifying Income

## 2. LOAN CHARACTERISTICS  
- Purpose, Type, Amount, Rate, Term, LTV, DTI

## 3. PROPERTY INFORMATION
- Address, Type, Value, Occupancy

## 4. ASSETS
- List all verified assets with balances

## 5. LIABILITIES & DEBTS
- List all debts with payments
- Credit scores, DTI ratios

## 6. COMPLIANCE & DISCLOSURE STATUS
- Required disclosures and signature status

## 7. CRITICAL FINDINGS & RED FLAGS
- List any issues or concerns

## 8. DOCUMENT INVENTORY
- Key documents present/missing

## 9. UNDERWRITER NOTES
- Summary, strengths, concerns, recommendation

Be specific with numbers, dates, and findings."""

    print(f"\n📤 Sending to Opus 4.5...")
    
    try:
        response = call_bedrock(
            prompt,
            model="claude-opus-4-5",
            max_tokens=8000,
            temperature=0.3
        )
        
        if response:
            print(f"✅ Summary generated ({len(response):,} chars)")
            
            # Store in database
            execute_query("""
                UPDATE loans 
                SET kg_summary = %s,
                    updated_at = NOW()
                WHERE id = %s
            """, (response, loan_id), fetch=False)
            
            print("💾 KG-based summary saved to database")
            return response
        else:
            print("❌ No response from Opus")
            return None
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def query_kg(loan_id, query_text):
    """Query knowledge graph using natural language"""
    
    # Get knowledge graph
    loan = execute_one("""
        SELECT knowledge_graph, loan_number 
        FROM loans 
        WHERE id = %s
    """, (loan_id,))
    
    if not loan or not loan['knowledge_graph']:
        return {
            'answer': 'No knowledge graph available for this loan.',
            'relevant_nodes': [],
            'relevant_edges': []
        }
    
    kg = loan['knowledge_graph']
    
    # Send to Claude to answer the query
    prompt = f"""You are analyzing a loan knowledge graph. Answer the user's question clearly and concisely.

KNOWLEDGE GRAPH:
{json.dumps(kg, indent=2)}

USER QUESTION:
{query_text}

Provide a clear, human-readable answer. Include specific values, names, amounts, and relationships.
Also identify which nodes and edges are most relevant to answering this question.

Return JSON in this format:
{{
  "answer": "Your detailed answer here...",
  "relevant_node_ids": ["node_id1", "node_id2", ...],
  "relevant_edge_indices": [0, 5, 12, ...]
}}"""

    try:
        response = call_bedrock(
            prompt,
            model="claude-opus-4-5",
            max_tokens=2000,
            temperature=0.2
        )
        
        if response:
            # Clean and parse
            response_clean = response.strip()
            if response_clean.startswith('```'):
                lines = response_clean.split('\n')
                if lines[0].startswith('```'):
                    lines = lines[1:]
                if lines and lines[-1].strip() == '```':
                    lines = lines[:-1]
                response_clean = '\n'.join(lines)
            
            result = json.loads(response_clean)
            
            # Get full nodes and edges
            relevant_nodes = [n for n in kg.get('nodes', []) if n['id'] in result.get('relevant_node_ids', [])]
            relevant_edges = [kg['edges'][i] for i in result.get('relevant_edge_indices', []) if i < len(kg.get('edges', []))]
            
            return {
                'answer': result.get('answer', ''),
                'relevant_nodes': relevant_nodes,
                'relevant_edges': relevant_edges
            }
        else:
            return {'answer': 'No response from Claude', 'relevant_nodes': [], 'relevant_edges': []}
            
    except Exception as e:
        return {'answer': f'Error: {str(e)}', 'relevant_nodes': [], 'relevant_edges': []}

def main():
    parser = argparse.ArgumentParser(description='Generate knowledge graph from deep JSON')
    parser.add_argument('loan_id', type=int, help='Loan ID to process')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be processed')
    parser.add_argument('--generate-summary', action='store_true', help='Generate summary from existing KG')
    
    args = parser.parse_args()
    
    if args.generate_summary:
        generate_summary_from_kg(args.loan_id)
    else:
        generate_knowledge_graph(args.loan_id, dry_run=args.dry_run)

if __name__ == "__main__":
    main()

