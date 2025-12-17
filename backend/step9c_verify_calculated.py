import sys
import json
import traceback
from db import get_db_connection

def parse_currency(val):
    if not val: return 0.0
    s = str(val).replace('$', '').replace(',', '').replace('%', '').strip()
    if not s or s.lower() in ['none', 'null']: return 0.0
    try:
        return float(s)
    except:
        return 0.0

def verify_calculated_attributes(loan_id):
    print(f"🧮 Verifying Calculated Attributes for Loan {loan_id}...")
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # 1. Fetch Extracted Data
        cur.execute("""
            SELECT fa.attribute_label, ed.extracted_value, fa.id as attr_id
            FROM extracted_1008_data ed
            JOIN form_1008_attributes fa ON fa.id = ed.attribute_id
            WHERE ed.loan_id = %s
        """, (loan_id,))
        
        data = {row['attribute_label']: {'value': row['extracted_value'], 'id': row['attr_id']} for row in cur.fetchall()}
        
        # 2. Fetch Evidence Status
        cur.execute("""
            SELECT fa.attribute_label, ef.verification_status, ef.file_name, ef.page_number
            FROM evidence_files ef
            JOIN form_1008_attributes fa ON fa.id = ef.attribute_id
            WHERE ef.loan_id = %s
        """, (loan_id,))
        
        evidence_map = {
            row['attribute_label']: {
                'status': row['verification_status'],
                'file_name': row['file_name'],
                'page_number': row['page_number']
            } 
            for row in cur.fetchall()
        }
        
        def get_val(label):
            return parse_currency(data.get(label, {}).get('value'))
        
        def get_evidence(label):
            return evidence_map.get(label, {}) # Default empty if missing
            
        def get_id_doc(label):
            aid = data.get(label, {}).get('id')
            if aid:
                return f"See ID - {aid}"
            return evidence_map.get(label, {}).get('file_name')
            
        def save_verification(target_label, is_math_match, all_components_verified, calc_val, extracted_val, steps):
            if target_label not in data:
                print(f"⚠️ {target_label} not found in extracted data. Skipping.")
                return
                
            attr_id = data[target_label]['id']
            
            # Logic:
            # Verified = Match AND All Components Verified
            # Review = Match BUT Components Not Verified
            # Not Verified = Mismatch
            
            if is_math_match:
                if all_components_verified:
                    status = 'verified'
                    mismatch_reason = None
                    notes_txt = "Verified: Math matches and all components verified."
                else:
                    status = 'not_verified' # Use 'not_verified' to show red/yellow, but we distinguish via notes?
                    mismatch_reason = "Math matches but some components are not verified."
                    notes_txt = mismatch_reason
            else:
                status = 'not_verified'
                mismatch_reason = f"Math Mismatch: Calculated {calc_val:,.2f} != Extracted {extracted_val:,.2f}"
                notes_txt = mismatch_reason
            
            # Delete existing evidence for this attribute
            cur.execute("DELETE FROM evidence_files WHERE loan_id = %s AND attribute_id = %s", (loan_id, attr_id))
            
            # Insert Evidence File
            notes_json = json.dumps({
                'verified': status == 'verified',
                'mismatch_reason': mismatch_reason,
                'is_calculated': True
            })
            
            cur.execute("""
                INSERT INTO evidence_files (loan_id, attribute_id, file_name, file_path, verification_status, notes, uploaded_at)
                VALUES (%s, %s, 'Calculated', 'calculated', %s, %s, NOW())
            """, (loan_id, attr_id, status, notes_json))
            
            # Update Calculation Steps
            cur.execute("DELETE FROM calculation_steps WHERE loan_id = %s AND attribute_id = %s", (loan_id, attr_id))
            for idx, step in enumerate(steps):
                cur.execute("""
                    INSERT INTO calculation_steps (loan_id, attribute_id, step_order, description, value, document_name, page_number)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (loan_id, attr_id, idx+1, step['desc'], step['val'], step.get('doc'), step.get('page')))
            
            print(f"✅ Processed {target_label}: {status} ({notes_txt})")

        # --- 1. Total Primary Housing Expense ---
        housing_comps = [
            'First Mortgage P&I', 'Second Mortgage P&I', 'Hazard Insurance', 'Taxes', 
            'Mortgage Insurance', 'HOA Fees', 'Lease/Ground Rent'
        ]
        
        calc_total = 0.0
        steps = []
        all_verified = True
        
        for lbl in housing_comps:
            if lbl in data:
                val = get_val(lbl)
                ev = get_evidence(lbl)
                stat = ev.get('status', 'not_verified')
                
                calc_total += val
                steps.append({
                    'desc': f"{lbl}", 
                    'val': f"${val:,.2f}",
                    'doc': get_id_doc(lbl),
                    'page': ev.get('page_number')
                })
                
                if stat != 'verified' and val > 0:
                    all_verified = False
            else:
                pass
                
        # Handle "Other"
        other_lbl = 'Other'
        if other_lbl in data:
            val = get_val(other_lbl)
            if val > 0:
                ev = get_evidence(other_lbl)
                calc_total += val
                steps.append({
                    'desc': other_lbl, 
                    'val': f"${val:,.2f}",
                    'doc': get_id_doc(other_lbl),
                    'page': ev.get('page_number')
                })
                if ev.get('status') != 'verified':
                    all_verified = False

        steps.append({'desc': 'Total Calculated', 'val': f"${calc_total:,.2f}"})
        
        target = 'Total Primary Housing Expense'
        if target in data:
            extracted_val = get_val(target)
            match = abs(calc_total - extracted_val) < 0.10
            save_verification(target, match, all_verified, calc_total, extracted_val, steps)

        # --- 1b. Present Housing Payment ---
        # Logic: Typically First Mortgage P&I + Hazard + Taxes + MI + HOA + Lease (Exclude Second Mtg if new)
        # We try to match what fits the extracted value.
        present_target = 'Present Housing Payment'
        if present_target in data:
            # Try components excluding Second Mortgage P&I
            present_comps = [
                'First Mortgage P&I', 'Hazard Insurance', 'Taxes', 
                'Mortgage Insurance', 'HOA Fees', 'Lease/Ground Rent'
            ]
            
            calc_present = 0.0
            steps_present = []
            all_verified_present = True
            
            for lbl in present_comps:
                if lbl in data:
                    val = get_val(lbl)
                    ev = get_evidence(lbl)
                    stat = ev.get('status', 'not_verified')
                    
                    calc_present += val
                    steps_present.append({
                        'desc': f"{lbl}", 
                        'val': f"${val:,.2f}",
                        'doc': get_id_doc(lbl),
                        'page': ev.get('page_number')
                    })
                    
                    if stat != 'verified' and val > 0:
                        all_verified_present = False
            
            steps_present.append({'desc': 'Total Calculated', 'val': f"${calc_present:,.2f}"})
            
            extracted_present = get_val(present_target)
            match_present = abs(calc_present - extracted_present) < 0.10
            
            if match_present:
                 save_verification(present_target, match_present, all_verified_present, calc_present, extracted_present, steps_present)
            else:
                # If mismatch, maybe it INCLUDES Second Mortgage?
                # Check 118 logic (which is basically this + Second Mortgage)
                pass

        # --- 2. Total All Monthly Payments ---
        all_comps = [
            'Total Primary Housing Expense', 
            'Negative Cash Flow (subject property)', 
            'All Other Monthly Payments',
            'Other Obligations'
        ]
        
        calc_total_all = 0.0
        steps_all = []
        all_verified_all = True
        
        # Re-fetch status for Total Primary since we just updated it
        cur.execute("SELECT verification_status FROM evidence_files WHERE loan_id=%s AND attribute_id=%s", 
                   (loan_id, data.get('Total Primary Housing Expense', {}).get('id')))
        res = cur.fetchone()
        tp_status = res['verification_status'] if res else 'not_verified'
        
        # Update evidence_map for Total Primary
        # Note: We won't have file/page for Total Primary itself (it's Calculated), unless we want to link to "Calculated"?
        # Or maybe link to 1008? The UI steps for Total All will reference Total Primary.
        
        tp_id = data.get('Total Primary Housing Expense', {}).get('id')
        evidence_map['Total Primary Housing Expense'] = {
            'status': tp_status, 
            'file_name': f"See ID - {tp_id}" if tp_id else 'Calculated', 
            'page_number': None
        }
        
        for lbl in all_comps:
            if lbl in data:
                val = get_val(lbl)
                ev = get_evidence(lbl)
                stat = ev.get('status', 'not_verified')
                
                calc_total_all += val
                steps_all.append({
                    'desc': lbl, 
                    'val': f"${val:,.2f}",
                    'doc': get_id_doc(lbl),
                    'page': ev.get('page_number')
                })
                
                if stat != 'verified' and val > 0:
                    all_verified_all = False
        
        steps_all.append({'desc': 'Total Calculated', 'val': f"${calc_total_all:,.2f}"})
        
        target_all = 'Total All Monthly Payments'
        if target_all in data:
            extracted_val = get_val(target_all)
            match = abs(calc_total_all - extracted_val) < 0.10
            save_verification(target_all, match, all_verified_all, calc_total_all, extracted_val, steps_all)

        # --- 3. Ratios ---
        # Need Income Denominator
        income = 0.0
        income_lbl = 'Total'
        if income_lbl not in data:
            income_lbl = 'Borrower Total Income Amount'
        
        if income_lbl in data:
            income = get_val(income_lbl)
            ev_inc = get_evidence(income_lbl)
            income_verified = (ev_inc.get('status') == 'verified')
            income_doc = ev_inc.get('file_name')
            income_page = ev_inc.get('page_number')
        else:
            print("⚠️ Income attribute not found. Skipping ratios.")
            income_verified = False
            income_doc = None
            income_page = None

        if income > 0:
            # Front End Ratio
            target_fe = 'Primary Housing Expense/Income'
            if target_fe in data:
                housing_val = get_val('Total Primary Housing Expense')
                # housing doc is "Calculated"
                
                ratio = (housing_val / income) * 100
                extracted_ratio = get_val(target_fe)
                match = abs(ratio - extracted_ratio) < 0.10 
                
                steps_ratio = [
                    {'desc': 'Total Primary Housing', 'val': f"${housing_val:,.2f}", 'doc': f"See ID - {data.get('Total Primary Housing Expense', {}).get('id')}", 'page': None},
                    {'desc': 'Total Income', 'val': f"${income:,.2f}", 'doc': income_doc, 'page': income_page},
                    {'desc': 'Calculated Ratio', 'val': f"{ratio:.3f}%"}
                ]
                
                housing_verified = (tp_status == 'verified')
                all_ver_ratio = housing_verified and income_verified
                
                save_verification(target_fe, match, all_ver_ratio, ratio, extracted_ratio, steps_ratio)
                
            # Back End Ratio
            target_be = 'Total Obligations/Income'
            if target_be in data:
                total_val = get_val('Total All Monthly Payments')
                ratio = (total_val / income) * 100
                extracted_ratio = get_val(target_be)
                match = abs(ratio - extracted_ratio) < 0.10
                
                # Check Total All status
                cur.execute("SELECT verification_status FROM evidence_files WHERE loan_id=%s AND attribute_id=%s", 
                           (loan_id, data.get('Total All Monthly Payments', {}).get('id')))
                res = cur.fetchone()
                ta_status = res['verification_status'] if res else 'not_verified'
                
                steps_ratio = [
                    {'desc': 'Total All Monthly', 'val': f"${total_val:,.2f}", 'doc': f"See ID - {data.get('Total All Monthly Payments', {}).get('id')}", 'page': None},
                    {'desc': 'Total Income', 'val': f"${income:,.2f}", 'doc': income_doc, 'page': income_page},
                    {'desc': 'Calculated Ratio', 'val': f"{ratio:.3f}%"}
                ]
                
                all_ver_ratio = (ta_status == 'verified') and income_verified
                
                save_verification(target_be, match, all_ver_ratio, ratio, extracted_ratio, steps_ratio)

        conn.commit()
        print("✅ Verification Complete.")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        traceback.print_exc()
    finally:
        conn.close()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        verify_calculated_attributes(int(sys.argv[1]))
