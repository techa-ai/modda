import json
import re
import sys
from db import execute_query
from collections import defaultdict

def apply_versioning(loan_id):
    print(f"Applying AI Versioning for Loan {loan_id}...")
    
    # Fetch docs with AI grouping
    query = """
    SELECT id, filename, detected_date, upload_date, version_metadata, text_hash, visual_dhash
    FROM document_analysis
    WHERE loan_id = %s 
      AND version_metadata->>'ai_group_id' IS NOT NULL
      AND status != 'deleted'
    """
    rows = execute_query(query, (loan_id,))
    
    # --- GLOBAL DEDUPLICATION START ---
    print(f"Starting Global Deduplication on {len(rows)} documents...")
    
    # 1. Global Hash Deduplication (Visual > Text > ID)
    hash_map = defaultdict(list)
    for d in rows:
        dhash = d.get('visual_dhash')
        thash = d.get('text_hash')
        
        if dhash and str(dhash).strip():
            h = f"vis_{dhash}"
        elif thash and str(thash).strip():
            h = f"txt_{thash}"
        else:
            h = f"id_{d['id']}"
        hash_map[h].append(d)
        
    unique_map_by_id = {}
    
    for h, duplicates in hash_map.items():
        # Sort by ID to be deterministic
        duplicates.sort(key=lambda x: x['id'])
        master = duplicates[0]
        count = len(duplicates) - 1
        
        master['calc_dup_count'] = count
        unique_map_by_id[master['id']] = master
        
        # Mark duplicates globally immediately
        for dup in duplicates[1:]:
             execute_query(
                 """
                 UPDATE document_analysis 
                 SET status = 'duplicate', 
                     master_document_id = %s, 
                     version_group_id = NULL,
                     duplicate_count = 0,
                     is_latest_version = false
                 WHERE id = %s
                 """,
                 (master['id'], dup['id']), 
                 fetch=False
             )

    # Survivors from Hash Dedupe
    pass_1_survivors = list(unique_map_by_id.values())
    doc_map = {d['id']: d for d in pass_1_survivors}
    
    final_survivors = []
    
    # 2. Global Regex Deduplication (Explicit "Duplicate of doc X")
    for d in pass_1_survivors:
        meta = d['version_metadata'] or {}
        reason = meta.get('primary_reason') or ""
        match = re.search(r'Duplicate of doc (\d+)', reason, re.IGNORECASE)
        
        is_explicit_dup = False
        if match:
            target_id = int(match.group(1))
            # Check if target is a known survivor
            if target_id in doc_map and target_id != d['id']:
                 master_id = target_id
                 is_explicit_dup = True
                 
                 # Master inherits duplicates from this doc
                 master_doc = doc_map[master_id]
                 inherited_count = d.get('calc_dup_count', 0)
                 master_doc['calc_dup_count'] = master_doc.get('calc_dup_count', 0) + 1 + inherited_count
                 
                 # Mark valid duplicate in DB
                 execute_query(
                     """
                     UPDATE document_analysis 
                     SET status = 'duplicate', 
                     master_document_id = %s, 
                     version_group_id = NULL,
                     duplicate_count = 0,
                     is_latest_version = false
                     WHERE id = %s
                     """,
                     (master_id, d['id']), 
                     fetch=False
                 )
        
        if not is_explicit_dup:
            final_survivors.append(d)

    print(f"Global Deduplication complete. Survivors: {len(final_survivors)}")

    # 3. Grouping Survivors
    groups = defaultdict(list)
    for r in final_survivors:
        meta = r['version_metadata']
        gid = meta.get('ai_group_id')
        if gid:
            groups[gid].append(r)
            
    print(f"Formed {len(groups)} AI groups from survivors.")
    
    updates = 0
    for gid, docs in groups.items():
        # 4. Apply Versioning Logic to Survivors within Groups
        
        # Ensure dates are populated for sorting and storage
        for d in docs:
             if not d.get('detected_date'):
                 meta = d['version_metadata'] or {}
                 # Try common date fields from AI
                 raw_date = meta.get('doc_date') or meta.get('effective_date') or meta.get('date') or meta.get('doc_date_ai')
                 
                 # Validate date format (YYYY-MM-DD) to avoid DB errors
                 if raw_date and re.match(r'^\d{4}-\d{2}-\d{2}$', str(raw_date)):
                     d['detected_date'] = raw_date

        # Determine Primaries based on AI 'is_primary' flag
        primaries = []
        for d in docs:
            meta = d['version_metadata'] or {}
            # Check boolean or string "true"
            primary_flag = meta.get('is_primary')
            if primary_flag is True or (isinstance(primary_flag, str) and primary_flag.lower() == 'true'):
                primaries.append(d)
        
        # fallback if no primary specified: Sort by Date, then Final > Preliminary
        if not primaries:
            def get_version_priority(filename):
                """Final > Unknown > Preliminary > Draft"""
                fn_lower = filename.lower()
                if 'final' in fn_lower:
                    return 3
                elif 'preliminary' in fn_lower or 'prelim' in fn_lower:
                    return 1
                elif 'draft' in fn_lower:
                    return 0
                return 2
            
            def sort_key(d):
                dd = d.get('detected_date')
                ud = d.get('upload_date')
                version_priority = get_version_priority(d['filename'])
                return (str(dd) if dd else '0000-00-00', version_priority, str(ud) if ud else '0000-00-00')
            docs.sort(key=sort_key, reverse=True)
            primaries = [docs[0]]
            
        primary_ids = set(p['id'] for p in primaries)
        
        # Update Survivors
        for d in docs:
            is_primary = d['id'] in primary_ids
            
            dup_count = d.get('calc_dup_count', 0)
            status = 'master' if dup_count > 0 else 'unique'
            
            execute_query(
                """
                UPDATE document_analysis
                SET version_group_id = %s,
                    is_latest_version = %s,
                    status = %s,
                    duplicate_count = %s,
                    detected_date = %s
                WHERE id = %s
                """,
                (gid, is_primary, status, dup_count, d.get('detected_date'), d['id']),
                fetch=False
            )
            
        updates += 1
        
    print(f"Detailed versioning applied to {updates} groups (with intra-group deduplication).")

if __name__ == "__main__":
    import sys
    loan_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    apply_versioning(loan_id)
