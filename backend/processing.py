import time
import os
import threading
import json
import base64
import io
import traceback
from pathlib import Path
from pdf2image import convert_from_path, pdfinfo_from_path
from db import execute_query, execute_one
from bedrock_config import call_bedrock
from backup_utils import backup_loan_data

def log_progress(loan_id, step, status, message):
    """Log processing progress to database"""
    execute_query(
        '''INSERT INTO processing_logs (loan_id, step, status, message) 
           VALUES (%s, %s, %s, %s)''',
        (loan_id, step, status, message),
        fetch=False
    )

def pdf_to_base64(pdf_path):
    try:
        # Convert first page only (1008 is typically 1 page)
        images = convert_from_path(str(pdf_path), dpi=300, first_page=1, last_page=1)
        if not images:
            return None, None
        
        img = images[0]
        
        # Save debug copy to verify what we're sending to Claude
        debug_path = '/tmp/claude_input_image.png'
        img.save(debug_path, format='PNG')
        print(f"DEBUG: Saved image sent to Claude at {debug_path} - Size: {img.width}x{img.height}")
        
        buffered = io.BytesIO()
        img.save(buffered, format="JPEG", quality=85)
        img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
        
        # Return both base64 and dimensions
        return img_base64, (img.width, img.height)
    except Exception as e:
        print(f"Error converting PDF: {e}")
        return None, None

def extract_json_from_text(text):
    """Extract JSON object from text response"""
    try:
        # Try finding JSON block
        if "```json" in text:
            json_str = text.split("```json")[1].split("```")[0]
            return json.loads(json_str)
        elif "{" in text:
            # Simple heuristic to find first outer brace
            start = text.find("{")
            end = text.rfind("}") + 1
            json_str = text[start:end]
            return json.loads(json_str)
        return None
    except:
        return None

def process_loan(loan_id, document_location):
    """
    Trigger the V3 Pipeline Orchestrator.
    Legacy: This used to do extraction inline. Now it delegates to run_loan_pipeline.py
    """
    try:
        log_progress(loan_id, 'Pipeline', 'started', 'Starting Refined Document Pipeline (V3)...')
        
        # Trigger the main orchestrator
        from run_loan_pipeline import run_loan_pipeline
        success = run_loan_pipeline(loan_id)
        
        if success:
            execute_query(
                "UPDATE loans SET status = 'completed' WHERE id = %s",
                (loan_id,),
                fetch=False
            )
            log_progress(loan_id, 'Generic', 'completed', 'Loan processing completed successfully')
        else:
            execute_query(
                "UPDATE loans SET status = 'failed' WHERE id = %s",
                (loan_id,),
                fetch=False
            )
            log_progress(loan_id, 'Generic', 'failed', 'Pipeline completed with errors')

    except Exception as e:
        # Log full traceback
        tb = traceback.format_exc()
        execute_query(
            "UPDATE loans SET status = 'failed' WHERE id = %s",
            (loan_id,),
            fetch=False
        )
        log_progress(loan_id, 'Generic', 'failed', f'Processing failed: {str(e)}')
        print(f"Error processing loan {loan_id}: {e}")
        print(tb)

def start_loan_processing(loan_id, document_location):
    """Start processing in a background thread"""
    thread = threading.Thread(target=process_loan, args=(loan_id, document_location))
    thread.daemon = True
    thread.start()
