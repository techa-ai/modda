import psycopg2
from psycopg2.extras import RealDictCursor
import os
from dotenv import load_dotenv

load_dotenv()

def get_db_connection():
    """Create and return a database connection"""
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=os.getenv('DB_PORT', '5436'),
        database=os.getenv('DB_NAME', 'modda'),
        user=os.getenv('DB_USER', 'modda_user'),
        password=os.getenv('DB_PASSWORD', 'modda_password'),
        cursor_factory=RealDictCursor
    )
    return conn

def execute_query(query, params=None, fetch=True):
    """Execute a query and return results"""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(query, params)
        if fetch:
            result = cur.fetchall()
        else:
            result = None
        conn.commit()
        return result
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()

def execute_one(query, params=None):
    """Execute a query and return one result"""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(query, params)
        result = cur.fetchone()
        conn.commit()
        return result
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()
