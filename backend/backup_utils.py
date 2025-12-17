"""
Backup and Restore utilities for loan processing data.
Ensures no data is lost during reprocessing.
"""

import json
from datetime import datetime
from db import execute_query, execute_one, get_db_connection

def create_backup_tables():
    """Create backup tables if they don't exist"""
    execute_query("""
        CREATE TABLE IF NOT EXISTS extracted_1008_data_backup (
            id SERIAL PRIMARY KEY,
            backup_id BIGINT NOT NULL,
            loan_id INTEGER NOT NULL,
            original_id INTEGER,
            attribute_id INTEGER,
            extracted_value TEXT,
            confidence_score DECIMAL(5,2),
            extraction_date TIMESTAMP,
            document_path TEXT,
            page_number INTEGER,
            bounding_box TEXT,
            ocr_verified BOOLEAN,
            backup_created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            restored BOOLEAN DEFAULT FALSE,
            restored_at TIMESTAMP
        )
    """, fetch=False)
    
    execute_query("""
        CREATE TABLE IF NOT EXISTS processing_logs_backup (
            id SERIAL PRIMARY KEY,
            backup_id BIGINT NOT NULL,
            loan_id INTEGER NOT NULL,
            original_id INTEGER,
            step VARCHAR(100),
            status VARCHAR(50),
            message TEXT,
            created_at TIMESTAMP,
            backup_created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            restored BOOLEAN DEFAULT FALSE,
            restored_at TIMESTAMP
        )
    """, fetch=False)
    
    execute_query("""
        CREATE TABLE IF NOT EXISTS backup_metadata (
            id SERIAL PRIMARY KEY,
            backup_id BIGINT UNIQUE NOT NULL,
            loan_id INTEGER NOT NULL,
            backup_type VARCHAR(50) NOT NULL,
            description TEXT,
            record_count INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            restored BOOLEAN DEFAULT FALSE,
            restored_at TIMESTAMP
        )
    """, fetch=False)
    
    # Create indexes
    execute_query("CREATE INDEX IF NOT EXISTS idx_backup_loan_id ON extracted_1008_data_backup(loan_id, backup_id)", fetch=False)
    execute_query("CREATE INDEX IF NOT EXISTS idx_backup_logs_loan_id ON processing_logs_backup(loan_id, backup_id)", fetch=False)
    execute_query("CREATE INDEX IF NOT EXISTS idx_backup_metadata_loan_id ON backup_metadata(loan_id)", fetch=False)

def backup_loan_data(loan_id, backup_type='reprocessing', description=None):
    """
    Backup extracted_1008_data and processing_logs for a loan before reprocessing.
    Returns backup_id that can be used for restoration.
    """
    create_backup_tables()
    
    # Generate backup_id (timestamp-based)
    backup_id = int(datetime.now().timestamp() * 1000)  # milliseconds
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Backup extracted_1008_data
        cursor.execute("""
            INSERT INTO extracted_1008_data_backup 
            (backup_id, loan_id, original_id, attribute_id, extracted_value, 
             confidence_score, extraction_date, document_path, page_number, bounding_box, ocr_verified)
            SELECT 
                %s, loan_id, id, attribute_id, extracted_value,
                confidence_score, extraction_date, document_path, page_number, bounding_box, ocr_verified
            FROM extracted_1008_data
            WHERE loan_id = %s
        """, (backup_id, loan_id))
        extracted_count = cursor.rowcount
        
        # Backup processing_logs
        cursor.execute("""
            INSERT INTO processing_logs_backup
            (backup_id, loan_id, original_id, step, status, message, created_at)
            SELECT 
                %s, loan_id, id, step, status, message, created_at
            FROM processing_logs
            WHERE loan_id = %s
        """, (backup_id, loan_id))
        logs_count = cursor.rowcount
        
        # Create backup metadata
        cursor.execute("""
            INSERT INTO backup_metadata (backup_id, loan_id, backup_type, description, record_count)
            VALUES (%s, %s, %s, %s, %s)
        """, (backup_id, loan_id, backup_type, description or f'Backup before {backup_type}', extracted_count + logs_count))
        
        conn.commit()
        
        print(f"✅ Backup created: backup_id={backup_id}, loan_id={loan_id}")
        print(f"   - Extracted data: {extracted_count} records")
        print(f"   - Processing logs: {logs_count} records")
        
        return backup_id
        
    except Exception as e:
        conn.rollback()
        raise Exception(f"Backup failed: {str(e)}")
    finally:
        cursor.close()
        conn.close()

def restore_loan_data(loan_id, backup_id=None):
    """
    Restore loan data from backup.
    If backup_id is None, restores from the most recent backup for this loan.
    """
    create_backup_tables()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Find backup_id if not provided
        if backup_id is None:
            cursor.execute("""
                SELECT backup_id FROM backup_metadata
                WHERE loan_id = %s AND restored = FALSE
                ORDER BY created_at DESC
                LIMIT 1
            """, (loan_id,))
            result = cursor.fetchone()
            if not result:
                raise Exception(f"No backup found for loan_id {loan_id}")
            backup_id = result[0]
        
        # Verify backup exists
        cursor.execute("""
            SELECT COUNT(*) as count FROM backup_metadata
            WHERE backup_id = %s AND loan_id = %s
        """, (backup_id, loan_id))
        if cursor.fetchone()['count'] == 0:
            raise Exception(f"Backup {backup_id} not found for loan_id {loan_id}")
        
        # Restore extracted_1008_data (only if not already exists)
        cursor.execute("""
            INSERT INTO extracted_1008_data 
            (loan_id, attribute_id, extracted_value, confidence_score, 
             extraction_date, document_path, page_number, bounding_box, ocr_verified)
            SELECT 
                loan_id, attribute_id, extracted_value, confidence_score,
                extraction_date, document_path, page_number, bounding_box, ocr_verified
            FROM extracted_1008_data_backup
            WHERE backup_id = %s AND loan_id = %s
            AND NOT EXISTS (
                SELECT 1 FROM extracted_1008_data ed
                WHERE ed.loan_id = extracted_1008_data_backup.loan_id
                AND ed.attribute_id = extracted_1008_data_backup.attribute_id
            )
        """, (backup_id, loan_id))
        restored_extracted = cursor.rowcount
        
        # Restore processing_logs
        cursor.execute("""
            INSERT INTO processing_logs (loan_id, step, status, message, created_at)
            SELECT loan_id, step, status, message, created_at
            FROM processing_logs_backup
            WHERE backup_id = %s AND loan_id = %s
        """, (backup_id, loan_id))
        restored_logs = cursor.rowcount
        
        # Mark backup as restored
        cursor.execute("""
            UPDATE backup_metadata
            SET restored = TRUE, restored_at = CURRENT_TIMESTAMP
            WHERE backup_id = %s
        """, (backup_id,))
        
        cursor.execute("""
            UPDATE extracted_1008_data_backup
            SET restored = TRUE, restored_at = CURRENT_TIMESTAMP
            WHERE backup_id = %s AND loan_id = %s
        """, (backup_id, loan_id))
        
        cursor.execute("""
            UPDATE processing_logs_backup
            SET restored = TRUE, restored_at = CURRENT_TIMESTAMP
            WHERE backup_id = %s AND loan_id = %s
        """, (backup_id, loan_id))
        
        conn.commit()
        
        print(f"✅ Restore completed: backup_id={backup_id}, loan_id={loan_id}")
        print(f"   - Restored extracted data: {restored_extracted} records")
        print(f"   - Restored processing logs: {restored_logs} records")
        
        return {
            'backup_id': backup_id,
            'restored_extracted': restored_extracted,
            'restored_logs': restored_logs
        }
        
    except Exception as e:
        conn.rollback()
        raise Exception(f"Restore failed: {str(e)}")
    finally:
        cursor.close()
        conn.close()

def list_backups(loan_id):
    """List all backups for a loan"""
    create_backup_tables()
    
    backups = execute_query("""
        SELECT 
            backup_id, backup_type, description, record_count,
            created_at, restored, restored_at
        FROM backup_metadata
        WHERE loan_id = %s
        ORDER BY created_at DESC
    """, (loan_id,))
    
    return backups

def get_latest_backup(loan_id):
    """Get the most recent backup for a loan"""
    backups = list_backups(loan_id)
    return backups[0] if backups else None

