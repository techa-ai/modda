from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os
import json
from dotenv import load_dotenv
import bcrypt
import jwt
from datetime import datetime, timedelta
from functools import wraps
from db import execute_query, execute_one, get_db_connection, RealDictCursor
from processing import start_loan_processing
import pandas as pd

load_dotenv()

app = Flask(__name__)
CORS(app)

app.config['SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'your-secret-key')
app.config['UPLOAD_FOLDER'] = os.getenv('UPLOAD_FOLDER', './uploads')

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# JWT token required decorator
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        
        if not token:
            return jsonify({'message': 'Token is missing'}), 401
        
        try:
            if token.startswith('Bearer '):
                token = token[7:]
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            current_user = execute_one(
                'SELECT id, username, email, role FROM users WHERE id = %s',
                (data['user_id'],)
            )
            if not current_user:
                return jsonify({'message': 'Invalid token'}), 401
        except Exception as e:
            return jsonify({'message': 'Token is invalid', 'error': str(e)}), 401
        
        return f(current_user, *args, **kwargs)
    
    return decorated

# Admin required decorator
def admin_required(f):
    @wraps(f)
    def decorated(current_user, *args, **kwargs):
        if current_user['role'] != 'admin':
            return jsonify({'message': 'Admin access required'}), 403
        return f(current_user, *args, **kwargs)
    
    return decorated

# ============= AUTH ROUTES =============

@app.route('/api/auth/login', methods=['POST'])
def login():
    """User login"""
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'message': 'Username and password required'}), 400
    
    user = execute_one(
        'SELECT * FROM users WHERE username = %s',
        (username,)
    )
    
    if not user or not bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
        return jsonify({'message': 'Invalid credentials'}), 401
    
    token = jwt.encode({
        'user_id': user['id'],
        'exp': datetime.utcnow() + timedelta(hours=24)
    }, app.config['SECRET_KEY'], algorithm='HS256')
    
    return jsonify({
        'token': token,
        'user': {
            'id': user['id'],
            'username': user['username'],
            'email': user['email'],
            'role': user['role']
        }
    })

@app.route('/api/auth/register', methods=['POST'])
def register():
    """User registration"""
    data = request.get_json()
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    role = data.get('role', 'user')
    
    if not username or not email or not password:
        return jsonify({'message': 'All fields required'}), 400
    
    # Check if user exists
    existing = execute_one(
        'SELECT id FROM users WHERE username = %s OR email = %s',
        (username, email)
    )
    
    if existing:
        return jsonify({'message': 'User already exists'}), 400
    
    # Hash password
    password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    # Create user
    user = execute_one(
        '''INSERT INTO users (username, email, password_hash, role) 
           VALUES (%s, %s, %s, %s) RETURNING id, username, email, role''',
        (username, email, password_hash, role)
    )
    
    return jsonify({'message': 'User created successfully', 'user': dict(user)}), 201

# ============= USER ROUTES =============

@app.route('/api/user/loans', methods=['GET'])
@token_required
def get_user_loans(current_user):
    """Get loans assigned to current user"""
    loans = execute_query(
        '''SELECT l.*, u.username as assigned_to_name
           FROM loans l
           LEFT JOIN users u ON l.assigned_to = u.id
           WHERE l.assigned_to = %s
           ORDER BY l.created_at DESC''',
        (current_user['id'],)
    )
    
    return jsonify({'loans': [dict(loan) for loan in loans]})

@app.route('/api/user/loans/<int:loan_id>', methods=['GET'])
@token_required
def get_loan_details(current_user, loan_id):
    """Get detailed loan information with extracted 1008 data"""
    # Check if loan is assigned to user
    # Check if loan is assigned to user (or if user is admin)
    if current_user['role'] == 'admin':
        loan = execute_one(
            'SELECT * FROM loans WHERE id = %s',
            (loan_id,)
        )
    else:
        loan = execute_one(
            'SELECT * FROM loans WHERE id = %s AND assigned_to = %s',
            (loan_id, current_user['id'])
        )
    
    if not loan:
        return jsonify({'message': 'Loan not found or not assigned to you'}), 404
    
    # Check if we should filter to essential attributes only
    essential_only = request.args.get('essential_only', 'false').lower() == 'true'
    
    # The 32 essential attribute names
    essential_names = [
        'Borrower Total Income Amount', 'Total Monthly Income', 'Borrower Type', 'amount_of_subordinate_financing',
        'borrower_name', 'borrower_representative_credit_indicator_score',
        'borrower_all_other_monthly_payments', 'loan_initial_p_and_i_payment',
        'property_address', 'property_appraised_value', 'loan_cltv_tltv',
        'loan_hcltv_htltv', 'loan_ltv', 'loan_primary_housing_expense_income',
        'loan_total_obligations_income', 'loan_initial_note_rate',
        'loan_original_loan_amount', 'loan_term_in_months', 'Loan Purpose Type',
        'Loan Type', 'Mort Amortization Type', 'Occupancy Status',
        'Property Rights Type', 'Property Type', 'Borrower Funds To Close Required',
        'Level Of Property Review Type', 'Proposed Monthly Hazard Insurance Amount',
        'Proposed Monthly Other Amount', 'Proposed Monthly Taxes Amount',
        'Proposed Monthly Total Monthly Payments Amount',
        'Proposed Monthly Total Primary Housing Expense Amount',
        'underwriters_name', 'second_mortgage_p_and_i'
    ]
    
    # Get extracted 1008 data
    if essential_only:
        placeholders = ','.join(['%s'] * len(essential_names))
        extracted_data = execute_query(
            f'''SELECT ed.*, fa.attribute_name, fa.attribute_label, fa.section, fa.display_order
               FROM extracted_1008_data ed
               JOIN form_1008_attributes fa ON ed.attribute_id = fa.id
               WHERE ed.loan_id = %s AND ed.extracted_value IS NOT NULL
               AND fa.attribute_name IN ({placeholders})
               ORDER BY fa.display_order NULLS LAST, fa.id''',
            (loan_id, *essential_names)
        )
    else:
        extracted_data = execute_query(
            '''SELECT ed.*, fa.attribute_name, fa.attribute_label, fa.section, fa.display_order
               FROM extracted_1008_data ed
               JOIN form_1008_attributes fa ON ed.attribute_id = fa.id
               WHERE ed.loan_id = %s AND ed.extracted_value IS NOT NULL
               ORDER BY fa.display_order NULLS LAST, fa.id''',
            (loan_id,)
        )
    
    # Get evidence files for each attribute
    evidence_files = execute_query(
        '''SELECT ef.*, fa.attribute_name
           FROM evidence_files ef
           JOIN form_1008_attributes fa ON ef.attribute_id = fa.id
           WHERE ef.loan_id = %s''',
        (loan_id,)
    )
    
    # Group evidence by attribute
    evidence_by_attribute = {}
    for evidence in evidence_files:
        attr_id = evidence['attribute_id']
        if attr_id not in evidence_by_attribute:
            evidence_by_attribute[attr_id] = []
        evidence_by_attribute[attr_id].append(dict(evidence))
    
    # Add evidence to extracted data
    data_with_evidence = []
    for data in extracted_data:
        data_dict = dict(data)
        data_dict['evidence'] = evidence_by_attribute.get(data['attribute_id'], [])
        data_with_evidence.append(data_dict)
    
    return jsonify({
        'loan': dict(loan),
        'extracted_data': data_with_evidence
    })

@app.route('/api/user/loans/<int:loan_id>/essential-attributes', methods=['GET'])
@token_required
def get_essential_attributes(current_user, loan_id):
    """Get only the 32 essential 1008 attributes (filtered by Claude)"""
    
    # The 32 essential attribute names
    essential_names = [
        'Borrower Total Income Amount',
        'Total Monthly Income',
        'total_income',
        'total_all_monthly_payments',
        'Total All Monthly Payments',
        'Borrower Type',
        'amount_of_subordinate_financing',
        'borrower_name',
        'borrower_representative_credit_indicator_score',
        'borrower_all_other_monthly_payments',
        'loan_initial_p_and_i_payment',
        'property_address',
        'property_appraised_value',
        'loan_cltv_tltv',
        'loan_hcltv_htltv',
        'loan_ltv',
        'loan_primary_housing_expense_income',
        'loan_total_obligations_income',
        'loan_initial_note_rate',
        'loan_original_loan_amount',
        'loan_term_in_months',
        'Loan Purpose Type',
        'Loan Type',
        'Mort Amortization Type',
        'Occupancy Status',
        'Property Rights Type',
        'Property Type',
        'Borrower Funds To Close Required',
        'Level Of Property Review Type',
        'Proposed Monthly Hazard Insurance Amount',
        'Proposed Monthly Other Amount',
        'Proposed Monthly Taxes Amount',
        'Proposed Monthly Total Monthly Payments Amount',
        'Proposed Monthly Total Primary Housing Expense Amount',
        'underwriters_name',
        'second_mortgage_p_and_i'
    ]
    
    # Category mapping
    category_map = {
        'Borrower Total Income Amount': 'Borrower',
        'Total Monthly Income': 'Borrower',
        'total_income': 'Borrower',
        'total_all_monthly_payments': 'Underwriting',
        'Total All Monthly Payments': 'Underwriting',
        'Borrower Type': 'Borrower',
        'borrower_name': 'Borrower',
        'borrower_representative_credit_indicator_score': 'Borrower',
        'borrower_all_other_monthly_payments': 'Borrower',
        'Borrower Funds To Close Required': 'Borrower',
        
        'property_address': 'Property',
        'property_appraised_value': 'Property',
        'Property Type': 'Property',
        'Property Rights Type': 'Property',
        'Occupancy Status': 'Property',
        
        'amount_of_subordinate_financing': 'Loan',
        'loan_initial_p_and_i_payment': 'Loan',
        'loan_cltv_tltv': 'Loan',
        'loan_hcltv_htltv': 'Loan',
        'loan_ltv': 'Loan',
        'loan_primary_housing_expense_income': 'Loan',
        'loan_total_obligations_income': 'Loan',
        'loan_initial_note_rate': 'Loan',
        'loan_original_loan_amount': 'Loan',
        'loan_term_in_months': 'Loan',
        'Loan Purpose Type': 'Loan',
        'Loan Type': 'Loan',
        'Mort Amortization Type': 'Loan',
        'second_mortgage_p_and_i': 'Loan',
        
        'Level Of Property Review Type': 'Underwriting',
        'Proposed Monthly Hazard Insurance Amount': 'Underwriting',
        'Proposed Monthly Other Amount': 'Underwriting',
        'Proposed Monthly Taxes Amount': 'Underwriting',
        'Proposed Monthly Total Monthly Payments Amount': 'Underwriting',
        'Proposed Monthly Total Primary Housing Expense Amount': 'Underwriting',
        'underwriters_name': 'Underwriting'
    }
    
    placeholders = ','.join(['%s'] * len(essential_names))
    
    # Get these attributes with calculation steps
    # We drive from form_1008_attributes to ensure we get the attribute definition 
    # even if there is no extracted value yet (but there might be calculated evidence)
    extracted_data = execute_query(f'''
        SELECT 
            COALESCE(ed.id, 0) as id,
            COALESCE(ed.loan_id, %s) as loan_id,
            fa.id as attribute_id,
            ed.extracted_value,
            ed.confidence_score,
            ed.document_path,
            ed.page_number,
            ed.ocr_verified,
            ed.bounding_box,
            ed.extraction_date,
            fa.attribute_name,
            fa.attribute_label,
            fa.section,
            CASE 
                WHEN EXISTS (
                    SELECT 1 FROM calculation_steps cs WHERE cs.attribute_id = fa.id AND cs.loan_id = %s
                ) THEN true
                ELSE false
            END as has_evidence
        FROM form_1008_attributes fa
        LEFT JOIN extracted_1008_data ed ON ed.attribute_id = fa.id AND ed.loan_id = %s
        WHERE fa.attribute_name IN ({placeholders})
        ORDER BY fa.attribute_name
    ''', (loan_id, loan_id, loan_id, *essential_names))
    
    # Group by category
    result = {
        'Borrower': [],
        'Property': [],
        'Loan': [],
        'Underwriting': []
    }
    
    for data in extracted_data:
        data_dict = dict(data)
        category = category_map.get(data['attribute_name'], 'Other')
        
        # Get calculation steps for this attribute
        steps = execute_query('''
            SELECT *
            FROM calculation_steps
            WHERE attribute_id = %s AND loan_id = %s
            ORDER BY step_order
        ''', (data['attribute_id'], loan_id))
        
        # Get evidence files for this attribute
        evidence = execute_query('''
            SELECT *
            FROM evidence_files
            WHERE attribute_id = %s AND loan_id = %s
        ''', (data['attribute_id'], loan_id))
        
        data_dict['calculation_steps'] = [dict(s) for s in steps]
        data_dict['evidence'] = [dict(e) for e in evidence]
        
        # Debug logging
        if 'Income' in data['attribute_name']:
            app.logger.info(f"[DEBUG] Loan {loan_id}, Attr {data['attribute_id']} ({data['attribute_name']}): {len(steps)} steps")
            if steps:
                app.logger.info(f"[DEBUG]   First step loan_id: {steps[0]['loan_id']}")
        
        result[category].append(data_dict)
    
    return jsonify(result)

@app.route('/api/user/loans/<int:loan_id>/snippet/<int:data_id>', methods=['GET'])
@token_required
def get_document_snippet(current_user, loan_id, data_id):
    """Get a cropped image snippet for a specific extracted data field"""
    from PIL import Image
    from pdf2image import convert_from_path
    import pytesseract
    import numpy as np
    import cv2
    import pandas as pd
    import io
    import base64
    
    try:
        # Get the extracted data record with attribute label
        data_record = execute_one(
            '''SELECT ed.*, a.attribute_label, a.attribute_name 
               FROM extracted_1008_data ed
               JOIN form_1008_attributes a ON ed.attribute_id = a.id
               WHERE ed.id = %s AND ed.loan_id = %s''',
            (data_id, loan_id)
        )
        
        if not data_record:
            return jsonify({'message': 'Data record not found'}), 404
        
        # Get document path
        doc_path = data_record['document_path']
        if not doc_path or not os.path.exists(doc_path):
            return jsonify({'message': 'Document not found'}), 404
        
        # Convert PDF first page to image
        images = convert_from_path(doc_path, first_page=1, last_page=1, dpi=300)
        if not images:
            return jsonify({'message': 'Failed to convert PDF'}), 500
        
        img = images[0]
        
        # --- SIMPLIFIED STRATEGY: FIND VALUE FIRST, THEN LOOK FOR LABEL NEARBY ---
        target_value = data_record['extracted_value']
        target_label = data_record['attribute_label']
        
        ocr_bbox = None
        ocr_verified = False
        chars = []
        
        try:
            print(f"Debug: Simplified OCR for Value='{target_value}'")
            
            # Get character-level bounding boxes
            box_data = pytesseract.image_to_boxes(img)
            height = img.height
            
            # Parse character data
            for line in box_data.split('\n'):
                if not line: continue
                parts = line.split()
                if len(parts) < 6: continue
                
                char = parts[0]
                left = int(parts[1])
                t_bottom = int(parts[2])
                t_right = int(parts[3])
                t_top = int(parts[4])
                
                # Convert Y from bottom-up to top-down
                y_top = height - t_top
                y_bottom = height - t_bottom
                
                chars.append({
                    'char': char,
                    'x': left,
                    'y': y_top,
                    'w': t_right - left,
                    'h': y_bottom - y_top
                })
        except Exception as e:
            print(f"OCR Error: {e}")
        
        try:
            # Simple strategy: Find the value, show 200px around it
            print(f"Debug: Searching for value='{target_value}'")
            
            # Get character-level bounding boxes
            box_data = pytesseract.image_to_boxes(img)
            height = img.height
            
            # Parse character data
            for line in box_data.split('\n'):
                if not line: continue
                parts = line.split()
                if len(parts) < 6: continue
                
                char = parts[0]
                left = int(parts[1])
                t_bottom = int(parts[2])
                t_right = int(parts[3])
                t_top = int(parts[4])
                
                # Convert Y from bottom-up to top-down
                y_top = height - t_top
                y_bottom = height - t_bottom
                
                chars.append({
                    'char': char,
                    'x': left,
                    'y': y_top,
                    'w': t_right - left,
                    'h': y_bottom - y_top
                })
        except Exception as e:
            print(f"OCR Error: {e}")
        
        
        # Simple fuzzy search for the value
        import re
        ocr_bbox = None
        ocr_verified = False
        
        if chars and target_value:
            # Clean the target for matching
            target_clean = re.sub(r'[^a-zA-Z0-9]', '', str(target_value)).lower()
            
            if len(target_clean) >= 2:
                # Find characters sequentially
                first_char = target_clean[0]
                
                for start_idx, char_obj in enumerate(chars):
                    if char_obj['char'].lower() != first_char:
                        continue
                    
                    # Try to match remaining characters sequentially
                    matched = [char_obj]
                    search_start = start_idx + 1
                    anchor_x = char_obj['x']
                    anchor_y = char_obj['y']
                    
                    for target_char in target_clean[1:]:
                        found = False
                        for idx in range(search_start, len(chars)):
                            c = chars[idx]
                            # Relaxed spatial bounds
                            if c['x'] > anchor_x + 800: break
                            if abs(c['y'] - anchor_y) > 100: continue
                            if c['x'] < anchor_x - 100: continue
                            
                            if c['char'].lower() == target_char:
                                matched.append(c)
                                search_start = idx + 1
                                anchor_x = c['x']  # Update anchor
                                found = True
                                break
                        
                        if not found:
                            break
                    
                    # Check if we matched enough
                    ratio = len(matched) / len(target_clean)
                    if ratio >= 0.7:
                        # Got a good match! Calculate bounding box
                        min_x = min(c['x'] for c in matched)
                        max_x = max(c['x'] + c['w'] for c in matched)
                        min_y = min(c['y'] for c in matched)
                        max_y = max(c['y'] + c['h'] for c in matched)
                        
                        # Center point of matched text
                        center_x = (min_x + max_x) / 2
                        center_y = (min_y + max_y) / 2
                        
                        # Create 200px box around center (400x400 total)
                        box_size = 200
                        ocr_bbox = (
                            int(center_x - box_size),
                            int(center_y - box_size),
                            box_size * 2,
                            box_size * 2
                        )
                        ocr_verified = True
                        print(f"Debug: Found '{target_value}' centered at ({center_x}, {center_y}), bbox={ocr_bbox}")
                        break  # Use first good match
        
        # Update database with OCR verification status
        try:
            execute_query(
                '''UPDATE extracted_1008_data 
                   SET ocr_verified = %s 
                   WHERE id = %s''',
                (ocr_verified, data_id),
                fetch=False
            )
        except Exception as db_err:
            print(f"Warning: Failed to update OCR flag: {db_err}")
                
        except Exception as e:
            print(f"OCR Error: {e}")
            import traceback
            traceback.print_exc()
            ocr_verified = False



        # --- STRATEGY 2: FALLBACK TO LLM BBOX ---
        real_x, real_y, real_w, real_h = 0, 0, 0, 0
        padding_x = 0
        padding_y = 0
        
        # Store the original LLM bbox for the response, even if OCR is used for cropping
        original_llm_bbox = None
        if data_record['bounding_box']:
            original_llm_bbox = json.loads(data_record['bounding_box']) if isinstance(data_record['bounding_box'], str) else data_record['bounding_box']

        if ocr_bbox:
            # OCR bbox already includes proper asymmetric padding
            # (150px left, 100px top, 50px right/bottom)
            real_x, real_y, real_w, real_h = ocr_bbox
            padding_x = 0  # No additional padding needed
            padding_y = 0
        elif original_llm_bbox:
             # Parse bounding box from DB (0-1000 scale)
             bbox_data = original_llm_bbox
             scale_x = img.width / 1000.0
             scale_y = img.height / 1000.0
             
             real_x = int(bbox_data['x'] * scale_x)
             real_y = int(bbox_data['y'] * scale_y)
             real_w = int(bbox_data['width'] * scale_x)
             real_h = int(bbox_data['height'] * scale_y)
             
             # Broader padding for LLM guess
             padding_x = 100
             padding_y = 100
        else:
             # Fallback: Show top of page
             real_x, real_y, real_w, real_h = 0, 0, img.width, 300
             padding_x, padding_y = 0, 0

        # Calculate crop boundaries
        left = max(0, real_x - padding_x)
        top = max(0, real_y - padding_y)
        right = min(img.width, real_x + real_w + padding_x)
        bottom = min(img.height, real_y + real_h + padding_y)
        
        cropped = img.crop((left, top, right, bottom))
        
        # Convert to base64
        buffered = io.BytesIO()
        cropped.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode('utf-8')
        
        # Also return field metadata
        response_data = {
            'image_data': img_str,
            'field_name': data_record['attribute_label'],
            'field_value': data_record['extracted_value'],
            'was_ocr_refined': bool(ocr_bbox),
            'ocr_verified': ocr_verified if 'ocr_verified' in locals() else None
        }
        
        response = jsonify(response_data)
        # Prevent browser caching of snippets
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
        
    except Exception as e:
        import traceback
        print(f"ERROR in get_document_snippet: {e}")
        traceback.print_exc()
        return jsonify({'message': f'Internal Server Error: {str(e)}'}), 500

# ============= ADMIN ROUTES =============

@app.route('/api/admin/loans', methods=['GET'])
@token_required
@admin_required
def get_all_loans(current_user):
    """Get all loans with profile summaries (admin only)"""
    loans = execute_query(
        '''SELECT l.*, u.username as assigned_to_name, c.username as created_by_name,
                  lp.profile_data, lp.analysis_source, lp.source_document, lp.extracted_at as profile_extracted_at
           FROM loans l
           LEFT JOIN users u ON l.assigned_to = u.id
           LEFT JOIN users c ON l.created_by = c.id
           LEFT JOIN loan_profiles lp ON l.id = lp.loan_id
           ORDER BY l.created_at DESC'''
    )
    
    result = []
    for loan in loans:
        loan_dict = dict(loan)
        # Parse profile_data if present
        if loan_dict.get('profile_data'):
            loan_dict['profile'] = loan_dict.pop('profile_data')
        else:
            loan_dict['profile'] = None
            loan_dict.pop('profile_data', None)
        result.append(loan_dict)
    
    return jsonify({'loans': result})


@app.route('/api/admin/loans/<int:loan_id>/profile', methods=['GET'])
@token_required
@admin_required
def get_loan_profile(current_user, loan_id):
    """Get detailed loan profile extracted from 1008/URLA"""
    profile = execute_one(
        '''SELECT lp.*, l.loan_number
           FROM loan_profiles lp
           JOIN loans l ON lp.loan_id = l.id
           WHERE lp.loan_id = %s''',
        (loan_id,)
    )
    
    if not profile:
        return jsonify({'message': 'Loan profile not found', 'profile': None}), 404
    
    return jsonify({
        'loan_id': loan_id,
        'loan_number': profile['loan_number'],
        'profile': profile['profile_data'],
        'analysis_source': profile['analysis_source'],
        'extracted_at': profile['extracted_at'].isoformat() if profile['extracted_at'] else None
    })

@app.route('/api/admin/loans', methods=['POST'])
@token_required
@admin_required
def create_loan(current_user):
    """Create a new loan (admin only)"""
    data = request.get_json()
    loan_number = data.get('loan_number')
    document_location = data.get('document_location')
    assigned_to = data.get('assigned_to')  # Optional
    
    if not loan_number or not document_location:
        return jsonify({'message': 'Loan number and document location required'}), 400
    
    # Check if loan exists
    existing = execute_one(
        'SELECT id FROM loans WHERE loan_number = %s',
        (loan_number,)
    )
    
    if existing:
        return jsonify({'message': 'Loan number already exists'}), 400
    
    # Create loan with optional assignment
    loan = execute_one(
        '''INSERT INTO loans (loan_number, document_location, assigned_to, created_by, status, dedup_status)
           VALUES (%s, %s, %s, %s, %s, %s)
           RETURNING *''',
        (loan_number, document_location, assigned_to if assigned_to else None, current_user['id'], 'processing', 'pending')
    )
    
    # Trigger background processing
    start_loan_processing(loan['id'], document_location)
    
    # Trigger background deduplication analysis
    from dedup_task import run_deduplication_analysis
    run_deduplication_analysis(loan['id'], document_location)
    
    return jsonify({'message': 'Loan created successfully. Processing and deduplication started.', 'loan': dict(loan)}), 201

@app.route('/api/admin/loans/<int:loan_id>/assign', methods=['POST'])
@token_required
@admin_required
def assign_loan(current_user, loan_id):
    """Assign loan to a user (admin only)"""
    data = request.get_json()
    user_id = data.get('user_id')
    
    if not user_id:
        return jsonify({'message': 'User ID required'}), 400
    
    # Check if user exists
    user = execute_one('SELECT id FROM users WHERE id = %s', (user_id,))
    if not user:
        return jsonify({'message': 'User not found'}), 404
    
    # Update loan
    execute_query(
        'UPDATE loans SET assigned_to = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s',
        (user_id, loan_id),
        fetch=False
    )
    
    return jsonify({'message': 'Loan assigned successfully'})

@app.route('/api/admin/loans/<int:loan_id>/process', methods=['POST'])
@token_required
@admin_required
def process_loan(current_user, loan_id):
    """Kick off loan processing (admin only)"""
    loan = execute_one('SELECT * FROM loans WHERE id = %s', (loan_id,))
    
    if not loan:
        return jsonify({'message': 'Loan not found'}), 404
    
    # Update status to processing
    execute_query(
        'UPDATE loans SET status = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s',
        ('processing', loan_id),
        fetch=False
    )
    
    # Log processing start
    execute_query(
        '''INSERT INTO processing_logs (loan_id, step, status, message)
           VALUES (%s, %s, %s, %s)''',
        (loan_id, 'Generic', 'started', 'Processing started manually'),
        fetch=False
    )
    
    # Trigger background processing
    start_loan_processing(loan_id, loan['document_location'])
    
    return jsonify({
        'message': 'Processing started',
        'loan_id': loan_id,
        'status': 'processing'
    })

@app.route('/api/admin/loans/<int:loan_id>/backups', methods=['GET'])
@token_required
@admin_required
def list_loan_backups(current_user, loan_id):
    """List all backups for a loan"""
    from backup_utils import list_backups
    backups = list_backups(loan_id)
    return jsonify({'backups': [dict(b) for b in backups]})

@app.route('/api/admin/loans/<int:loan_id>/restore', methods=['POST'])
@token_required
@admin_required
def restore_loan_from_backup(current_user, loan_id):
    """Restore loan data from backup"""
    from backup_utils import restore_loan_data
    data = request.get_json() or {}
    backup_id = data.get('backup_id')  # Optional - uses latest if not provided
    
    try:
        result = restore_loan_data(loan_id, backup_id)
        return jsonify({
            'message': 'Restore completed successfully',
            'backup_id': result['backup_id'],
            'restored_extracted': result['restored_extracted'],
            'restored_logs': result['restored_logs']
        })
    except Exception as e:
        return jsonify({'message': f'Restore failed: {str(e)}'}), 500

@app.route('/api/admin/loans/<int:loan_id>/logs', methods=['GET'])
@token_required
@admin_required
def get_loan_logs(current_user, loan_id):
    """Get processing logs for a loan"""
    logs = execute_query(
        '''SELECT * FROM processing_logs 
           WHERE loan_id = %s 
           ORDER BY created_at DESC''',
        (loan_id,)
    )
    return jsonify({'logs': [dict(log) for log in logs]})


@app.route('/api/admin/loans/<int:loan_id>/generate-summary', methods=['POST'])
@token_required
@admin_required
def generate_loan_summary(current_user, loan_id):
    """Generate comprehensive loan summary using Claude Opus"""
    from generate_loan_summary import generate_loan_summary as gen_summary
    
    try:
        summary = gen_summary(loan_id)
        
        if summary:
            return jsonify({
                'success': True,
                'summary': summary,
                'message': 'Summary generated successfully'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to generate summary'
            }), 500
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500


@app.route('/api/admin/loans/<int:loan_id>/generate-knowledge-graph', methods=['POST'])
@token_required
@admin_required
def trigger_kg_generation(current_user, loan_id):
    """Trigger knowledge graph generation"""
    import subprocess
    import os
    
    try:
        # Run in background
        script_path = os.path.join(os.path.dirname(__file__), 'step6_generate_knowledge_graph.py')
        log_path = f'/tmp/kg_loan{loan_id}.log'
        
        process = subprocess.Popen(
            ['python3', script_path, str(loan_id)],
            stdout=open(log_path, 'w'),
            stderr=subprocess.STDOUT,
            cwd=os.path.dirname(__file__)
        )
        
        return jsonify({
            'success': True,
            'message': 'Knowledge graph generation started',
            'pid': process.pid,
            'log_file': log_path
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@app.route('/api/admin/loans/<int:loan_id>/knowledge-graph', methods=['GET'])
@token_required
@admin_required
def get_knowledge_graph(current_user, loan_id):
    """Get knowledge graph for a loan"""
    loan = execute_one("""
        SELECT knowledge_graph, kg_summary, kg_generated_at
        FROM loans 
        WHERE id = %s
    """, (loan_id,))
    
    if not loan:
        return jsonify({'message': 'Loan not found'}), 404
    
    return jsonify({
        'knowledge_graph': loan['knowledge_graph'],
        'kg_summary': loan['kg_summary'],
        'generated_at': loan['kg_generated_at'].isoformat() if loan['kg_generated_at'] else None
    })


@app.route('/api/admin/loans/<int:loan_id>/query-knowledge-graph', methods=['POST'])
@token_required
@admin_required
def query_knowledge_graph(current_user, loan_id):
    """Query knowledge graph using natural language"""
    from step6_generate_knowledge_graph import query_kg
    
    data = request.get_json()
    query_text = data.get('query', '')
    
    if not query_text:
        return jsonify({'error': 'Query required'}), 400
    
    try:
        result = query_kg(loan_id, query_text)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/admin/loans/<int:loan_id>/generate-kg-summary', methods=['POST'])
@token_required
@admin_required
def generate_kg_summary(current_user, loan_id):
    """Generate summary from knowledge graph"""
    from step6_generate_knowledge_graph import generate_summary_from_kg
    
    try:
        summary = generate_summary_from_kg(loan_id)
        
        if summary:
            return jsonify({
                'success': True,
                'summary': summary
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to generate summary'
            }), 500
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@app.route('/api/admin/loans/<int:loan_id>/extracted_data', methods=['GET'])
@token_required
@admin_required
def get_loan_extracted_data(current_user, loan_id):
    """Get extracted 1008 data with evidence for a loan"""
    
    # Check if we should filter to essential attributes only
    essential_only = request.args.get('essential_only', 'false').lower() == 'true'
    
    # The 32 essential attribute names
    essential_names = [
        'Borrower Total Income Amount', 'Total Monthly Income', 'Borrower Type', 'amount_of_subordinate_financing',
        'borrower_name', 'borrower_representative_credit_indicator_score',
        'borrower_all_other_monthly_payments', 'loan_initial_p_and_i_payment',
        'property_address', 'property_appraised_value', 'loan_cltv_tltv',
        'loan_hcltv_htltv', 'loan_ltv', 'loan_primary_housing_expense_income',
        'loan_total_obligations_income', 'loan_initial_note_rate',
        'loan_original_loan_amount', 'loan_term_in_months', 'Loan Purpose Type',
        'Loan Type', 'Mort Amortization Type', 'Occupancy Status',
        'Property Rights Type', 'Property Type', 'Borrower Funds To Close Required',
        'Level Of Property Review Type', 'Proposed Monthly Hazard Insurance Amount',
        'Proposed Monthly Other Amount', 'Proposed Monthly Taxes Amount',
        'Proposed Monthly Total Monthly Payments Amount',
        'Proposed Monthly Total Primary Housing Expense Amount',
        'underwriters_name', 'second_mortgage_p_and_i'
    ]
    
    # Get extracted 1008 data
    if essential_only:
        placeholders = ','.join(['%s'] * len(essential_names))
        extracted_data = execute_query(
            f'''SELECT ed.*, fa.attribute_name, fa.attribute_label, fa.section, fa.display_order
               FROM extracted_1008_data ed
               JOIN form_1008_attributes fa ON ed.attribute_id = fa.id
               WHERE ed.loan_id = %s AND ed.extracted_value IS NOT NULL
               AND fa.attribute_name IN ({placeholders})
               ORDER BY fa.display_order NULLS LAST, fa.id''',
            (loan_id, *essential_names)
        )
    else:
        extracted_data = execute_query(
            '''SELECT ed.*, fa.attribute_name, fa.attribute_label, fa.section, fa.display_order
               FROM extracted_1008_data ed
               JOIN form_1008_attributes fa ON ed.attribute_id = fa.id
               WHERE ed.loan_id = %s AND ed.extracted_value IS NOT NULL
               ORDER BY fa.display_order NULLS LAST, fa.id''',
            (loan_id,)
        )
    
    # Get evidence files for each attribute
    evidence_files = execute_query(
        '''SELECT ef.*, fa.attribute_name
           FROM evidence_files ef
           JOIN form_1008_attributes fa ON ef.attribute_id = fa.id
           WHERE ef.loan_id = %s''',
        (loan_id,)
    )
    
    # Group evidence by attribute
    evidence_by_attribute = {}
    for evidence in evidence_files:
        attr_id = evidence['attribute_id']
        if attr_id not in evidence_by_attribute:
            evidence_by_attribute[attr_id] = []
        evidence_by_attribute[attr_id].append(dict(evidence))
    
    # Add evidence to extracted data
    data_with_evidence = []
    for data in extracted_data:
        data_dict = dict(data)
        data_dict['evidence'] = evidence_by_attribute.get(data['attribute_id'], [])
        data_with_evidence.append(data_dict)
        
    return jsonify(data_with_evidence)

@app.route('/api/admin/loans/<int:loan_id>', methods=['GET'])
@token_required
@admin_required
def get_loan_detail(current_user, loan_id):
    """Get detailed information about a specific loan"""
    loan = execute_one(
        '''SELECT l.*, u.username as assigned_to_name
           FROM loans l
           LEFT JOIN users u ON l.assigned_to = u.id
           WHERE l.id = %s''',
        (loan_id,)
    )
    
    if not loan:
        return jsonify({'message': 'Loan not found'}), 404
    
    return jsonify(dict(loan))

@app.route('/api/admin/loans/<int:loan_id>/stats', methods=['GET'])
@token_required
@admin_required
def get_loan_stats(current_user, loan_id):
    """Get statistics for a specific loan"""
    # Get loan to find document location
    loan = execute_one('SELECT * FROM loans WHERE id = %s', (loan_id,))
    
    if not loan:
        return jsonify({'message': 'Loan not found'}), 404
    
    # Check if full deduplication is requested
    run_dedup = request.args.get('deduplicate', 'false').lower() == 'true'
    doc_location = loan['document_location']
    
    if run_dedup:
        # Run deduplication to get accurate stats (slow)
        from dedup_utils import deduplicate_documents
        dedup_result = deduplicate_documents(doc_location)
        
        stats = {
            'total_documents': dedup_result['stats']['total'],
            'unique_documents': dedup_result['stats']['unique'],
            'duplicates_removed': dedup_result['stats']['duplicates'],
            'important_documents': 0
        }
    else:
        # Get actual counts from document_analysis table
        total_documents_result = execute_query('''
            SELECT COUNT(*) as count
            FROM document_analysis
            WHERE loan_id = %s
        ''', (loan_id,))
        total_documents = total_documents_result[0]['count'] if total_documents_result else 0
        
        # Count unique document groups (matches the tab logic)
        # This counts version groups + singles with status='unique' or 'master'
        version_groups_count = execute_query('''
            SELECT COUNT(DISTINCT version_group_id) as count
            FROM document_analysis
            WHERE loan_id = %s
            AND status IN ('unique', 'master')
            AND version_group_id IS NOT NULL
        ''', (loan_id,))
        
        singles_count = execute_query('''
            SELECT COUNT(*) as count
            FROM document_analysis
            WHERE loan_id = %s
            AND status IN ('unique', 'master')
            AND version_group_id IS NULL
        ''', (loan_id,))
        
        version_groups = version_groups_count[0]['count'] if version_groups_count else 0
        singles = singles_count[0]['count'] if singles_count else 0
        unique_documents = version_groups + singles
        
        # Count versions identified (documents with status='unique' in version groups but not the representative)
        total_in_groups = execute_query('''
            SELECT COUNT(*) as count
            FROM document_analysis
            WHERE loan_id = %s
            AND status IN ('unique', 'master')
            AND version_group_id IS NOT NULL
        ''', (loan_id,))
        versions_identified = total_in_groups[0]['count'] - version_groups if total_in_groups else 0
        
        # Count duplicates (documents with status='duplicate')
        duplicates_result = execute_query('''
            SELECT COUNT(*) as count
            FROM document_analysis
            WHERE loan_id = %s
            AND status = 'duplicate'
        ''', (loan_id,))
        duplicates_identified = duplicates_result[0]['count'] if duplicates_result else 0
        
        # Get 1008 evidencing counts
        verified_1008_count = execute_query('''
            SELECT COUNT(DISTINCT fa.id) as count
            FROM form_1008_attributes fa
            JOIN extracted_1008_data ed ON ed.attribute_id = fa.id AND ed.loan_id = %s
            JOIN evidence_files ef ON ef.attribute_id = fa.id AND ef.loan_id = %s
            WHERE ed.extracted_value IS NOT NULL 
            AND ed.extracted_value != ''
            AND ed.extracted_value != '0.00'
            AND ef.verification_status = 'verified'
        ''', (loan_id, loan_id))
        
        total_1008_with_values = execute_query('''
            SELECT COUNT(DISTINCT fa.id) as count
            FROM form_1008_attributes fa
            JOIN extracted_1008_data ed ON ed.attribute_id = fa.id AND ed.loan_id = %s
            WHERE ed.extracted_value IS NOT NULL 
            AND ed.extracted_value != ''
            AND ed.extracted_value != '0.00'
        ''', (loan_id,))
        
        stats = {
            'total_documents': total_documents,
            'unique_documents': unique_documents,
            'versions_identified': versions_identified,
            'duplicates_identified': duplicates_identified,
            'important_documents': 0,
            'verified_1008_count': verified_1008_count[0]['count'] if verified_1008_count else 0,
            'total_1008_with_values': total_1008_with_values[0]['count'] if total_1008_with_values else 0
        }
    
    return jsonify(stats)

@app.route('/api/admin/loans/<int:loan_id>/documents', methods=['GET'])
@token_required
@admin_required
def get_loan_documents(current_user, loan_id):
    """Get categorized documents for a specific loan"""
    from datetime import datetime as dt
    
    # Get loan to find document location
    loan = execute_one('SELECT * FROM loans WHERE id = %s', (loan_id,))
    
    if not loan:
        return jsonify({'message': 'Loan not found'}), 404
    
    # Check if deduplication analysis has been run
    analysis_results = execute_query(
        "SELECT * FROM document_analysis WHERE loan_id = %s ORDER BY upload_date DESC",
        (loan_id,)
    )
    
    if analysis_results:
        # Use stored analysis results (fast!)
        raw_docs = []
        version_groups = {}
        unique_docs_singles = []
        
        for doc in analysis_results:
            doc_info = {
                'id': doc['id'],
                'name': doc['filename'],
                'path': doc['file_path'],
                'type': 'PDF',
                'size': doc['file_size'],
                'pages': doc['page_count'],
                'upload_date': doc['upload_date'].isoformat() if doc['upload_date'] else None,
                'status': doc['status'],
                'hash': doc['text_hash'],
                'duplicate_count': doc['duplicate_count'] or 0,
                'version_group_id': doc.get('version_group_id'),
                'detected_date': doc.get('detected_date').isoformat() if doc.get('detected_date') else None,
                'is_latest_version': doc.get('is_latest_version', False),
                'version_metadata': doc.get('version_metadata'),
                'vlm_analysis': doc.get('vlm_analysis'),
                'individual_analysis': doc.get('individual_analysis')
            }
            
            # If this is a master document, fetch the duplicate filenames
            if doc['status'] == 'master' and doc['duplicate_count'] > 0:
                duplicates = execute_query(
                    "SELECT filename FROM document_analysis WHERE loan_id = %s AND master_document_id = %s",
                    (loan_id, doc['id'])
                )
                doc_info['duplicates'] = [d['filename'] for d in duplicates]
            
            raw_docs.append(doc_info)
            
            # Grouping logic for unique/master list
            if doc['status'] in ['unique', 'master']:
                vg_id = doc.get('version_group_id')
                if vg_id:
                    if vg_id not in version_groups:
                        version_groups[vg_id] = []
                    version_groups[vg_id].append(doc_info)
                else:
                    unique_docs_singles.append(doc_info)
        
        # Process version groups
        final_unique = []
        for vid, group in version_groups.items():
            # Find representative (latest version)
            representative = next((d for d in group if d.get('is_latest_version')), None)
            if not representative:
                # Fallback: Sort by date desc
                group.sort(key=lambda x: x.get('detected_date') or '', reverse=True)
                representative = group[0]
            
            # Other versions
            others = [d for d in group if d['name'] != representative['name']]
            others.sort(key=lambda x: x.get('detected_date') or '', reverse=True)
            
            representative['versions'] = others
            representative['version_count'] = len(group)
            representative['latest_count'] = len([d for d in group if d.get('is_latest_version')])
            
            # Aggregate duplicate count from all versions in the group
            representative['aggregate_duplicate_count'] = sum(d.get('duplicate_count', 0) for d in group)
            # Aggregate actual duplicate filenames
            all_dups = []
            for d in group:
                if d.get('duplicates'):
                    all_dups.extend(d['duplicates'])
            representative['duplicates'] = all_dups
            
            final_unique.append(representative)
            
        # For singles, aggregate is just their own count
        for d in unique_docs_singles:
            d['aggregate_duplicate_count'] = d.get('duplicate_count', 0)
            # d['duplicates'] already set if master
            
        final_unique.extend(unique_docs_singles)
        # Sort final list
        final_unique.sort(key=lambda x: x.get('upload_date') or '', reverse=True)
        
        documents = {
            'raw': raw_docs,
            'unique': final_unique,
            'important': [],
            'dedup_status': loan.get('dedup_status', 'unknown'),
            'dedup_last_run': loan.get('dedup_last_run').isoformat() if loan.get('dedup_last_run') else None
        }
    else:
        # No analysis yet - fall back to file scan
        documents = {
            'raw': [],
            'unique': [],
            'important': [],
            'dedup_status': loan.get('dedup_status', 'pending'),
            'dedup_last_run': None
        }
        
        doc_location = loan['document_location']
        if doc_location and os.path.exists(doc_location):
            try:
                for filename in os.listdir(doc_location):
                    if filename.lower().endswith('.pdf'):
                        file_path = os.path.join(doc_location, filename)
                        file_stats = os.stat(file_path)
                        
                        doc_info = {
                            'name': filename,
                            'path': file_path,
                            'type': 'PDF',
                            'size': file_stats.st_size,
                            'upload_date': dt.fromtimestamp(file_stats.st_mtime).isoformat(),
                            'status': 'not_analyzed'
                        }
                        documents['raw'].append(doc_info)
                
                documents['raw'].sort(key=lambda x: x['upload_date'], reverse=True)
                documents['unique'] = documents['raw'].copy()
                
            except Exception as e:
                print(f"Error scanning documents: {e}")
    
    return jsonify(documents)

@app.route('/api/admin/loans/<int:loan_id>/deduplicate', methods=['POST'])
@token_required
@admin_required
def trigger_deduplication(current_user, loan_id):
    """Trigger deduplication analysis for a loan"""
    loan = execute_one('SELECT * FROM loans WHERE id = %s', (loan_id,))
    
    if not loan:
        return jsonify({'message': 'Loan not found'}), 404
    
    # Check if already running
    if loan.get('dedup_status') == 'running':
        return jsonify({'message': 'Deduplication already in progress'}), 409
    
    # Trigger background analysis
    from dedup_task import run_deduplication_analysis
    result = run_deduplication_analysis(loan_id, loan['document_location'])
    
    return jsonify(result)

@app.route('/api/admin/loans/<int:loan_id>/documents/<int:doc_id>/set_latest', methods=['POST'])
@token_required
@admin_required
def set_latest_version(current_user, loan_id, doc_id):
    """Manually set a document as the latest version in its group"""
    # Verify doc exists and get group
    doc = execute_one(
        "SELECT version_group_id FROM document_analysis WHERE id = %s AND loan_id = %s",
        (doc_id, loan_id)
    )
    
    if not doc:
        return jsonify({'message': 'Document not found'}), 404
        
    group_id = doc.get('version_group_id')
    if not group_id:
        return jsonify({'message': 'Document is not part of a version group'}), 400
        
    try:
        # Reset all in group
        execute_query(
            "UPDATE document_analysis SET is_latest_version = FALSE WHERE version_group_id = %s AND loan_id = %s",
            (group_id, loan_id),
            fetch=False
        )
        # Set target
        execute_query(
            "UPDATE document_analysis SET is_latest_version = TRUE WHERE id = %s",
            (doc_id,),
            fetch=False
        )
        return jsonify({'message': 'Latest version updated successfully'})
    except Exception as e:
        return jsonify({'message': str(e)}), 500

@app.route('/api/admin/loans/<int:loan_id>/documents/<path:filename>/content', methods=['GET'])
# @token_required # Browser iframe can't easily send headers, so usage URL token or cookie is needed. For now, we'll skipping token for this resource or use a query param token
def serve_document_content(loan_id, filename):
    """Serve the actual document content for preview"""
    # Verify loan existence
    # We can get the path from the DB
    doc = execute_one(
        "SELECT file_path FROM document_analysis WHERE loan_id = %s AND filename = %s",
        (loan_id, filename)
    )
    
    if not doc:
        # Fallback to checking disk if not in analysis yet (for raw view)
        loan = execute_one('SELECT document_location FROM loans WHERE id = %s', (loan_id,))
        if loan and loan['document_location']:
             potential_path = os.path.join(loan['document_location'], filename)
             if os.path.exists(potential_path):
                 return send_file(potential_path)
        
        return jsonify({'message': 'Document not found'}), 404
        
    if not os.path.exists(doc['file_path']):
        return jsonify({'message': 'File not found on disk'}), 404
        
    return send_file(doc['file_path'])

@app.route('/api/admin/loans/<int:loan_id>', methods=['DELETE'])
@token_required
@admin_required
def delete_loan(current_user, loan_id):
    """Delete a loan and all associated data"""
    loan = execute_one('SELECT * FROM loans WHERE id = %s', (loan_id,))
    
    if not loan:
        return jsonify({'message': 'Loan not found'}), 404
    
    try:
        # Delete associated data first (if any foreign key constraints exist)
        execute_query('DELETE FROM processing_logs WHERE loan_id = %s', (loan_id,), fetch=False)
        execute_query('DELETE FROM extracted_1008_data WHERE loan_id = %s', (loan_id,), fetch=False)
        
        # Delete the loan
        execute_query('DELETE FROM loans WHERE id = %s', (loan_id,), fetch=False)
        
        return jsonify({'message': 'Loan deleted successfully'})
    except Exception as e:
        return jsonify({'message': 'Error deleting loan', 'error': str(e)}), 500

@app.route('/api/admin/users', methods=['GET'])
@token_required
@admin_required
def get_users(current_user):
    """Get all users (admin only)"""
    users = execute_query(
        'SELECT id, username, email, role, created_at FROM users ORDER BY created_at DESC'
    )
    
    return jsonify({'users': [dict(user) for user in users]})

@app.route('/api/admin/attributes', methods=['GET'])
@token_required
@admin_required
def get_attributes(current_user):
    """Get all 1008 form attributes (admin only)"""
    attributes = execute_query(
        '''SELECT fa.*, 
           COALESCE(
               json_agg(
                   json_build_object(
                       'id', ed.id,
                       'document_type', ed.document_type,
                       'description', ed.description
                   )
               ) FILTER (WHERE ed.id IS NOT NULL), '[]'
           ) as evidence_types
           FROM form_1008_attributes fa
           LEFT JOIN evidence_documents ed ON fa.id = ed.attribute_id
           GROUP BY fa.id
           ORDER BY fa.display_order'''
    )
    
    return jsonify({'attributes': [dict(attr) for attr in attributes]})

@app.route('/api/admin/attributes', methods=['POST'])
@token_required
@admin_required
def create_attribute(current_user):
    """Create new 1008 form attribute (admin only)"""
    data = request.get_json()
    
    attribute = execute_one(
        '''INSERT INTO form_1008_attributes 
           (attribute_name, attribute_label, data_type, is_required, section, display_order)
           VALUES (%s, %s, %s, %s, %s, %s)
           RETURNING *''',
        (
            data.get('attribute_name'),
            data.get('attribute_label'),
            data.get('data_type', 'text'),
            data.get('is_required', False),
            data.get('section'),
            data.get('display_order', 999)
        )
    )
    
    return jsonify({'message': 'Attribute created', 'attribute': dict(attribute)}), 201

@app.route('/api/admin/attributes/<int:attr_id>/evidence', methods=['POST'])
@token_required
@admin_required
def add_evidence_type(current_user, attr_id):
    """Add evidence document type for an attribute (admin only)"""
    data = request.get_json()
    
    evidence = execute_one(
        '''INSERT INTO evidence_documents (attribute_id, document_type, description)
           VALUES (%s, %s, %s)
           RETURNING *''',
        (attr_id, data.get('document_type'), data.get('description'))
    )
    
    return jsonify({'message': 'Evidence type added', 'evidence': dict(evidence)}), 201

@app.route('/api/config/schemas', methods=['GET'])
@token_required
@admin_required
def get_schemas(current_user):
    """List available document schemas"""
    # Go up one level from backend/ to modda/ then to config/document_schemas
    schema_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'document_schemas')
    schemas = []
    if os.path.exists(schema_dir):
        for filename in os.listdir(schema_dir):
            if filename.endswith('.json'):
                schemas.append(filename)
    return jsonify({'schemas': schemas})

@app.route('/api/config/schemas/<filename>', methods=['GET'])
@token_required
@admin_required
def get_schema_content(current_user, filename):
    """Get content of a specific schema"""
    schema_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'document_schemas')
    filepath = os.path.join(schema_dir, filename)
    
    # Security check to prevent directory traversal
    if not os.path.abspath(filepath).startswith(os.path.abspath(schema_dir)):
        return jsonify({'message': 'Invalid filename'}), 400
        
    if not os.path.exists(filepath):
        return jsonify({'message': 'Schema not found'}), 404
        
    with open(filepath, 'r') as f:
        try:
            content = json.load(f)
            return jsonify(content)
        except json.JSONDecodeError:
            return jsonify({'message': 'Invalid JSON in schema file'}), 500

# ============= HEALTH CHECK =============

# Helper function for robust OCR localization
def find_best_bbox(ocr_data, target_label, target_value):
    import numpy as np
    import re
    
    def normalize_txt(s):
        return re.sub(r'[^\w\s]', '', str(s)).lower()

    if not target_value or not target_label:
        return None
    
    target_val_clean = normalize_txt(target_value)

    # 1. Try finding Label Candidates (Split word strategy)
    label_words = [w for w in target_label.split() if len(w) > 3]
    if not label_words: label_words = target_label.split()
    
    label_candidates = []
    for word in label_words:
        matches = ocr_data[ocr_data['text'].str.contains(word, case=False, regex=False)]
        if not matches.empty:
            label_candidates.append(matches)
    
    label_matches = pd.concat(label_candidates).drop_duplicates() if label_candidates else pd.DataFrame()

    if not label_matches.empty:
        # Search near label
        for _, l_row in label_matches.head(20).iterrows():
            l_left, l_top = int(l_row.left), int(l_row.top)
            l_bottom = int(l_row.top + l_row.height)
            
            value_tokens = target_value.split()
            found_tokens_bbox = []
            y_tolerance = 40
            
            # Line candidates to the right
            line_candidates = ocr_data[
                (ocr_data['top'] > l_top - y_tolerance) & 
                (ocr_data['top'] < l_bottom + y_tolerance) &
                (ocr_data['left'] > l_left)
            ]
            
            for token in value_tokens:
                token_clean = normalize_txt(token)
                if not token_clean: continue
                # Match against CLEAN text column (assumed passed in ocr_data)
                if 'text_clean' in line_candidates.columns:
                     match = line_candidates[line_candidates['text_clean'].str.contains(token_clean, regex=False)]
                else:
                     match = line_candidates[line_candidates['text'].str.contains(token_clean, regex=False, case=False)]
                     
                if not match.empty:
                    t_row = match.iloc[0]
                    found_tokens_bbox.append((int(t_row.left), int(t_row.top), int(t_row.width), int(t_row.height)))
            
            if found_tokens_bbox:
                min_x = min(x for x,_,_,_ in found_tokens_bbox)
                min_y = min(y for _,y,_,_ in found_tokens_bbox)
                max_x = max(x+w for x,_,w,_ in found_tokens_bbox)
                max_y = max(y+h for _,y,_,h in found_tokens_bbox)
                return (min_x, min_y, max_x - min_x, max_y - min_y)

    # 2. Fallback: Unique precise value match
    if 'text_clean' in ocr_data.columns:
        value_matches = ocr_data[ocr_data['text_clean'].str.contains(target_val_clean, regex=False)]
        if not value_matches.empty and len(value_matches) == 1:
            row = value_matches.iloc[0]
            return (int(row.left), int(row.top), int(row.width), int(row.height))
        
    return None

@app.route('/api/user/loans/<int:loan_id>/full_annotation', methods=['GET'])
@token_required
def get_full_annotation(current_user, loan_id):
    try:
        from PIL import ImageDraw, ImageFont
        from pdf2image import convert_from_path
        import pytesseract
        import io
        import base64
        import re

        # 1. Fetch ALL data
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT d.extracted_value, a.attribute_label, d.document_path
            FROM extracted_1008_data d
            JOIN form_1008_attributes a ON d.attribute_id = a.id
            WHERE d.loan_id = %s
        """, (loan_id,))
        attributes = cur.fetchall()
        cur.close()
        conn.close()

        if not attributes:
            return jsonify({'error': 'No data found'}), 404
            
        # 2. Get Document Path
        doc_path = attributes[0]['document_path']
        if not doc_path or not os.path.exists(doc_path):
             return jsonify({'error': 'Document file not found'}), 404

        # 3. Load PDF Image (Page 1)
        # Using 300 DPI for clarity
        images = convert_from_path(doc_path, first_page=1, last_page=1, dpi=300)
        img = images[0]

        # 4. Running OCR once
        ocr_df = pytesseract.image_to_data(img, output_type=pytesseract.Output.DATAFRAME)
        ocr_df = ocr_df[ocr_df.conf != -1]
        ocr_df['text'] = ocr_df['text'].fillna('').astype(str).str.strip()
        ocr_df = ocr_df[ocr_df['text'] != '']
        
        # Pre-calculate clean text for performance
        def normalize_txt(s):
            return re.sub(r'[^\w\s]', '', str(s)).lower()
        ocr_df['text_clean'] = ocr_df['text'].apply(normalize_txt)
        
        # 5. Draw Boxes
        draw = ImageDraw.Draw(img)
        try:
            # Try to start with a large font
            font = ImageFont.truetype("Arial.ttf", 30)
        except:
            font = ImageFont.load_default()

        count_found = 0
        for attr in attributes:
            bbox = find_best_bbox(ocr_df, attr['attribute_label'], attr['extracted_value'])
            if bbox:
                x, y, w, h = bbox
                # Draw Box (Red)
                draw.rectangle([x, y, x+w, y+h], outline="red", width=3)
                # Draw Label (Optional - might clutter, maybe just box?)
                # User asked for "annotated and extracted values". 
                # A small label tag is helpful.
                # Use semi-transparent background? PIL doesn't support transparency easily on RGB.
                # Just draw rectangle
                draw.rectangle([x, y-20, x+len(attr['attribute_label'])*10, y], fill="red")
                draw.text((x+2, y-18), attr['attribute_label'][:20], fill="white", font=font)
                count_found += 1
        
        print(f"Annotated {count_found}/{len(attributes)} fields")
        
        # 6. Return Image
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        
        return jsonify({'image_data': img_str})

    except Exception as e:
        print(f"Annotation Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'service': 'MODDA Backend'})

@app.route('/api/admin/loans/<int:loan_id>/evidence-documents', methods=['GET'])
@token_required
@admin_required
def get_evidence_documents(current_user, loan_id):
    """Get all documents used as evidence for 1008 attributes"""
    # Get unique PDF documents from evidence_files (exclude JSON files)
    evidence_docs = execute_query('''
        SELECT DISTINCT
            ef.file_name,
            ef.file_path,
            da.version_metadata->>'doc_type' as doc_type,
            da.individual_analysis as analysis
        FROM evidence_files ef
        LEFT JOIN document_analysis da ON da.filename = ef.file_name AND da.loan_id = ef.loan_id
        WHERE ef.loan_id = %s
        AND ef.file_name LIKE '%%.pdf'
        ORDER BY ef.file_name
    ''', (loan_id,))
    
    # For each document, get all attributes using it
    documents_with_usage = []
    for doc in evidence_docs:
        # Get evidence entries for this document
        evidence_entries = execute_query('''
            SELECT 
                fa.attribute_label,
                ed.extracted_value as attribute_value,
                ef.page_number,
                ef.verification_status,
                ef.notes,
                ef.attribute_id
            FROM evidence_files ef
            JOIN form_1008_attributes fa ON fa.id = ef.attribute_id
            LEFT JOIN extracted_1008_data ed ON ed.attribute_id = fa.id AND ed.loan_id = ef.loan_id
            WHERE ef.loan_id = %s AND ef.file_name = %s
            ORDER BY fa.display_order
        ''', (loan_id, doc['file_name']))
        
        # Parse usage - check if any attribute has a primary evidence with step_by_step_calculation
        detailed_usage = []
        processed_attributes = set()
        
        for entry in evidence_entries:
            attr_id = entry['attribute_id']
            
            # Skip if we already processed this attribute
            if attr_id in processed_attributes:
                continue
            processed_attributes.add(attr_id)
            
            # For each attribute, find its primary evidence (if any) and check for step_by_step_calculation
            primary_evidence = execute_query('''
                SELECT notes
                FROM evidence_files ef
                WHERE ef.loan_id = %s 
                AND ef.attribute_id = %s
                AND ef.notes IS NOT NULL
                LIMIT 10
            ''', (loan_id, attr_id))
            
            # Look for primary evidence with step_by_step_calculation
            found_steps = False
            for primary in primary_evidence:
                if primary['notes']:
                    try:
                        notes = json.loads(primary['notes']) if isinstance(primary['notes'], str) else primary['notes']
                        
                        if notes.get('document_classification') == 'primary' and 'step_by_step_calculation' in notes:
                            # Extract only steps that use the current document
                            for step in notes['step_by_step_calculation']:
                                step_source = step.get('source', '')
                                step_doc = step.get('document', '')
                                
                                # Skip calculated/formula steps (they don't come from documents)
                                if not step_source or step.get('formula'):
                                    continue
                                
                                # Skip steps without specific page numbers (they're usually final values)
                                if not step.get('page'):
                                    continue
                                
                                # Skip vague sources like "Counter Offer accepted" - we need specific locations
                                if any(keyword in step_source.lower() for keyword in ['accepted', 'shown on 1008', 'final', 'calculated']):
                                    continue
                                
                                # Check if this step references the current document
                                # Match by filename or by keywords in source
                                doc_name_lower = doc['file_name'].lower()
                                source_lower = step_source.lower()
                                
                                is_match = False
                                if doc_name_lower.endswith(step_doc):
                                    is_match = True
                                elif 'purchase' in doc_name_lower and 'purchase' in source_lower:
                                    is_match = True
                                elif 'tax' in doc_name_lower and 'tax' in source_lower:
                                    is_match = True
                                elif 'appraisal' in doc_name_lower and 'appraisal' in source_lower:
                                    is_match = True
                                elif 'urla' in doc_name_lower and 'urla' in source_lower:
                                    is_match = True
                                
                                if is_match:
                                    detailed_usage.append({
                                        'attribute_label': f"{entry['attribute_label']} - {step.get('description', 'Step ' + str(step.get('step', '')))}",
                                        'attribute_value': step.get('amount', ''),
                                        'page_number': step.get('page'),
                                        'verification_status': entry['verification_status'],
                                        'description': step.get('explanation', step.get('notes', '')),
                                        'step_number': step.get('step', 0)
                                    })
                                    found_steps = True
                    except (json.JSONDecodeError, TypeError):
                        pass
            
            # If no steps found, add the entry as-is (with description from notes if available)
            # But be very selective - only add if it has BOTH page number AND isn't in a step_by_step_calculation
            if not found_steps:
                # Skip if no page number
                if not entry['page_number']:
                    continue
                
                # Skip if this attribute has step_by_step in any of its evidence
                # (we only want to show the steps, not the summary)
                has_steps_elsewhere = False
                if entry['notes']:
                    try:
                        notes = json.loads(entry['notes']) if isinstance(entry['notes'], str) else entry['notes']
                        if notes.get('document_classification') == 'primary' and 'step_by_step_calculation' in notes:
                            has_steps_elsewhere = True
                    except:
                        pass
                
                if has_steps_elsewhere:
                    continue
                    
                description = ''
                specific_value = entry['attribute_value']  # Default to attribute value
                
                if entry['notes']:
                    try:
                        notes = json.loads(entry['notes']) if isinstance(entry['notes'], str) else entry['notes']
                        description = notes.get('verification_summary', notes.get('description', ''))
                        
                        # For supporting documents, use the specific amount from the document
                        if notes.get('document_classification') == 'supporting' and 'amount' in notes:
                            specific_value = notes['amount']
                    except:
                        pass
                
                detailed_usage.append({
                    'attribute_label': entry['attribute_label'],
                    'attribute_value': specific_value,  # Use specific value if available
                    'page_number': entry['page_number'],
                    'verification_status': entry['verification_status'],
                    'description': description,
                    'step_number': 999  # Put non-step entries at the end
                })
        
        # Group usage by unique values from the document and deduplicate
        values_map = {}
        seen_values = set()  # Track unique value+page combinations
        
        for usage in detailed_usage:
            value = usage['attribute_value']
            page = usage.get('page_number', 'N/A')
            step_num = usage.get('step_number', 999)
            
            # Skip if we've already seen this exact value+page combination
            value_key = f"{value}|{page}"
            if value_key in seen_values:
                continue
            seen_values.add(value_key)
            
            # Create a key based on value and page
            key = value_key
            
            if key not in values_map:
                values_map[key] = {
                    'value': value,
                    'page_number': page,
                    'description': usage.get('description', ''),
                    'attributes': [],
                    'step_number': step_num
                }
            
            # Add this attribute to the list
            values_map[key]['attributes'].append({
                'attribute_label': usage['attribute_label'],
                'verification_status': usage['verification_status']
            })
        
        # Convert to list and sort by step number, then page
        grouped_usage = sorted(
            values_map.values(),
            key=lambda x: (x.get('step_number', 999), x['page_number'] if isinstance(x['page_number'], int) else 999)
        )
        
        documents_with_usage.append({
            'file_name': doc['file_name'],
            'file_path': doc['file_path'],
            'doc_type': doc['doc_type'],
            'analysis': doc['analysis'],
            'usage': grouped_usage  # Now grouped by value instead of by attribute
        })
    
    return jsonify({'documents': documents_with_usage})

# =====================================================
# CALCULATION STEPS API (Graph-based approach)
# =====================================================

@app.route('/api/admin/loans/<int:loan_id>/calculation-steps', methods=['GET'])
@token_required
@admin_required  
def get_calculation_steps(current_user, loan_id):
    """Get calculation steps for a loan, optionally filtered by document or attribute"""
    document_name = request.args.get('document')
    step_id = request.args.get('step_id')
    attribute_id = request.args.get('attribute_id')
    
    if step_id:
        # Get single step by ID
        steps = execute_query('''
            SELECT 
                cs.id as step_id,
                cs.step_order,
                cs.value,
                cs.description,
                cs.rationale,
                cs.formula,
                cs.document_id,
                cs.document_name,
                cs.page_number,
                cs.source_location,
                cs.is_calculated,
                fa.id as attribute_id,
                fa.attribute_label
            FROM calculation_steps cs
            JOIN form_1008_attributes fa ON fa.id = cs.attribute_id
            WHERE cs.loan_id = %s AND cs.id = %s
        ''', (loan_id, step_id))
    elif attribute_id:
        # Get all steps for this attribute
        steps = execute_query('''
            SELECT 
                cs.id as step_id,
                cs.step_order,
                cs.value,
                cs.description,
                cs.rationale,
                cs.formula,
                cs.document_id,
                cs.document_name,
                cs.page_number,
                cs.source_location,
                cs.is_calculated,
                fa.id as attribute_id,
                fa.attribute_label
            FROM calculation_steps cs
            JOIN form_1008_attributes fa ON fa.id = cs.attribute_id
            WHERE cs.loan_id = %s AND cs.attribute_id = %s
            ORDER BY cs.step_order
        ''', (loan_id, attribute_id))
    elif document_name:
        # Get all steps referencing this document
        steps = execute_query('''
            SELECT 
                cs.id as step_id,
                cs.step_order,
                cs.value,
                cs.description,
                cs.rationale,
                cs.formula,
                cs.document_id,
                cs.document_name,
                cs.page_number,
                cs.source_location,
                cs.is_calculated,
                fa.id as attribute_id,
                fa.attribute_label
            FROM calculation_steps cs
            JOIN form_1008_attributes fa ON fa.id = cs.attribute_id
            WHERE cs.loan_id = %s 
            AND cs.document_name = %s
            AND cs.is_calculated = FALSE
            ORDER BY fa.attribute_label, cs.step_order
        ''', (loan_id, document_name))
    else:
        # Get all steps
        steps = execute_query('''
            SELECT 
                cs.id as step_id,
                cs.step_order,
                cs.value,
                cs.description,
                cs.rationale,
                cs.formula,
                cs.document_id,
                cs.document_name,
                cs.page_number,
                cs.source_location,
                cs.is_calculated,
                fa.id as attribute_id,
                fa.attribute_label
            FROM calculation_steps cs
            JOIN form_1008_attributes fa ON fa.id = cs.attribute_id
            WHERE cs.loan_id = %s
            ORDER BY fa.attribute_label, cs.step_order
        ''', (loan_id,))
    
    return jsonify({'steps': steps})

@app.route('/api/admin/loans/<int:loan_id>/evidence-documents-v2', methods=['GET'])
@token_required
@admin_required
def get_evidence_documents_v2(current_user, loan_id):
    """Get documents with usage from calculation_steps table (robust graph-based approach)"""
    
    # Get unique PDF documents that have calculation steps
    evidence_docs = execute_query('''
        SELECT DISTINCT
            cs.document_name as file_name,
            '/uploads/' || cs.document_name as file_path,
            da.version_metadata->>'doc_type' as doc_type,
            da.individual_analysis as analysis
        FROM calculation_steps cs
        LEFT JOIN document_analysis da ON da.filename = cs.document_name AND da.loan_id = cs.loan_id
        WHERE cs.loan_id = %s
        AND cs.document_name IS NOT NULL
        AND cs.is_calculated = FALSE
        ORDER BY cs.document_name
    ''', (loan_id,))
    
    documents_with_usage = []
    for doc in evidence_docs:
        # Get all steps for this document
        steps = execute_query('''
            SELECT 
                cs.id as step_id,
                cs.value,
                cs.description,
                cs.rationale,
                cs.page_number,
                cs.step_order,
                fa.attribute_label
            FROM calculation_steps cs
            JOIN form_1008_attributes fa ON fa.id = cs.attribute_id
            WHERE cs.loan_id = %s 
            AND cs.document_name = %s
            AND cs.is_calculated = FALSE
            ORDER BY cs.page_number, cs.step_order
        ''', (loan_id, doc['file_name']))
        
        # Format as usage entries
        usage = [{
            'step_id': step['step_id'],
            'value': step['value'],
            'page_number': step['page_number'],
            'description': step['rationale'] or step['description'],
            'attributes': [{
                'attribute_label': f"{step['attribute_label']} - {step['description']}"
            }]
        } for step in steps]
        
        documents_with_usage.append({
            'file_name': doc['file_name'],
            'file_path': doc['file_path'],
            'doc_type': doc['doc_type'],
            'analysis': doc['analysis'],
            'usage': usage
        })
    
    return jsonify({'documents': documents_with_usage})

# =====================================================
# COMPLIANCE ENDPOINTS
# =====================================================

@app.route('/api/admin/loans/<int:loan_id>/compliance', methods=['GET'])
@token_required
@admin_required
def get_loan_compliance(current_user, loan_id):
    """Get compliance check results for a loan using ComplianceEngine v3 with full document extraction"""
    try:
        from compliance_engine_v3 import ComplianceEngineV3
        
        # Check if we should force re-extraction
        force_extraction = request.args.get('force', 'false').lower() == 'true'
        
        # Run comprehensive compliance check with document extraction
        engine = ComplianceEngineV3(enable_extraction=True)
        report = engine.run_full_compliance_check(loan_id, force_extraction=force_extraction)
        
        # Convert report to JSON-serializable format
        report_dict = {
            'loan_id': report.loan_id,
            'loan_number': report.loan_number,
            'execution_id': report.execution_id,
            'execution_timestamp': report.execution_timestamp.isoformat(),
            'overall_status': report.overall_status.value,
            'total_rules': report.total_rules,
            'passed': report.passed,
            'failed': report.failed,
            'warnings': report.warnings,
            'pending_review': report.pending_review,
            'not_applicable': report.not_applicable,
            'qm_type': report.qm_type.value if report.qm_type else None,
            'atr_type': report.atr_type.value if report.atr_type else None,
            'is_hpml': report.is_hpml,
            'is_hoepa': report.is_hoepa,
            'calculated_apr': float(report.calculated_apr) if report.calculated_apr else None,
            'apor_spread': float(report.apor_spread) if report.apor_spread else None,
            'qm_points_fees_pct': float(report.qm_points_fees_pct) if report.qm_points_fees_pct else None,
            'back_end_dti': float(report.back_end_dti) if report.back_end_dti else None,
            'results': [
                {
                    'rule_code': r.rule_code,
                    'rule_name': r.rule_name,
                    'category': r.category.value,
                    'status': r.status.value,
                    'severity': r.severity.value,
                    'message': r.message,
                    'expected_value': str(r.expected_value) if r.expected_value else None,
                    'actual_value': str(r.actual_value) if r.actual_value else None,
                    'requires_manual_review': r.requires_manual_review,
                    'evidence': r.evidence if hasattr(r, 'evidence') and r.evidence else {}
                } for r in report.results
            ],
            'context': report.context_data
        }
        
        return jsonify(report_dict)
        
    except Exception as e:
        print(f"Compliance check error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e), 'message': 'Error running compliance check'}), 500

@app.route('/api/user/loans/<int:loan_id>/verification-summary/<verification_type>', methods=['GET'])
@token_required
def get_verification_summary(current_user, loan_id, verification_type):
    """Get professional executive summary for verification (pre-generated or generate on-the-fly)"""
    try:
        from db import execute_one
        
        # First, try to get pre-generated summary from database (INSTANT!)
        row = execute_one("""
            SELECT profile_data FROM loan_profiles WHERE loan_id = %s
        """, (loan_id,))
        
        if row and row['profile_data']:
            profile = row['profile_data']
            verification_status = profile.get('verification_status', {})
            
            # Check if we have a stored rich summary
            if verification_type in verification_status:
                rich_summary = verification_status[verification_type].get('rich_summary')
                
                if rich_summary:
                    # Return pre-generated summary (INSTANT - NO API CALL!)
                    return jsonify({
                        'loan_id': loan_id,
                        'verification_type': verification_type,
                        'summary': rich_summary.get('summary', ''),
                        'breakdown': rich_summary.get('breakdown', []),
                        'total_value': rich_summary.get('total_value'),
                        'documents': rich_summary.get('documents', []),
                        'statistics': rich_summary.get('statistics', {}),
                        'cached': True
                    })
        
        # Fallback: Generate on-the-fly if not cached (slower)
        from generate_verification_summary import get_income_verification_data, get_debt_verification_data, generate_professional_summary
        
        if verification_type == 'income':
            data = get_income_verification_data(loan_id)
        elif verification_type == 'debt':
            data = get_debt_verification_data(loan_id)
        else:
            return jsonify({'error': f'Verification type "{verification_type}" not yet implemented'}), 400
        
        # Generate professional summary using Claude (slower)
        summary_data = generate_professional_summary(data, verification_type)
        
        return jsonify({
            'loan_id': loan_id,
            'verification_type': verification_type,
            'summary': summary_data['summary'],
            'breakdown': summary_data.get('breakdown', []),
            'total_value': summary_data.get('total_value'),
            'documents': summary_data.get('documents', []),
            'statistics': summary_data.get('statistics', {}),
            'cached': False
        })
        
    except Exception as e:
        print(f"Verification summary error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e), 'message': 'Error generating verification summary'}), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8006))
    app.run(host='0.0.0.0', port=port, debug=False)
