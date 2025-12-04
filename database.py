import sqlite3
import threading
from datetime import datetime, date
import os

DB_FILE = 'boomber.db'
db_lock = threading.Lock()

def get_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    
    # Jobs table
    c.execute('''
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT NOT NULL,
            masked_phone TEXT NOT NULL,
            added_by TEXT NOT NULL,
            password TEXT NOT NULL,
            total_rounds INTEGER NOT NULL,
            current_round INTEGER DEFAULT 0,
            status TEXT DEFAULT 'running',
            total_success INTEGER DEFAULT 0,
            total_fail INTEGER DEFAULT 0,
            start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            end_time TIMESTAMP
        )
    ''')
    
    # Job logs table (per-API results)
    c.execute('''
        CREATE TABLE IF NOT EXISTS job_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            target_name TEXT NOT NULL,
            success INTEGER NOT NULL,
            status_code INTEGER,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (job_id) REFERENCES jobs(id)
        )
    ''')
    
    # Daily stats table
    c.execute('''
        CREATE TABLE IF NOT EXISTS daily_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT UNIQUE NOT NULL,
            total_sent INTEGER DEFAULT 0,
            total_success INTEGER DEFAULT 0,
            total_fail INTEGER DEFAULT 0
        )
    ''')
    
    # Visitors table (Unique IPs)
    c.execute('''
        CREATE TABLE IF NOT EXISTS visitors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip TEXT UNIQUE NOT NULL,
            first_visit TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_visit TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            visit_count INTEGER DEFAULT 1
        )
    ''')
    
    conn.commit()
    conn.close()

def mask_phone(phone):
    """Mask phone number like 01882*****71"""
    if len(phone) < 6:
        return phone
    return phone[:5] + '*****' + phone[-2:]

def create_job(phone, added_by, password, total_rounds):
    with db_lock:
        conn = get_db()
        c = conn.cursor()
        masked = mask_phone(phone)
        c.execute('''
            INSERT INTO jobs (phone, masked_phone, added_by, password, total_rounds)
            VALUES (?, ?, ?, ?, ?)
        ''', (phone, masked, added_by, password, total_rounds))
        job_id = c.lastrowid
        conn.commit()
        conn.close()
        return job_id

def get_job(job_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM jobs WHERE id = ?', (job_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def get_all_jobs():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM jobs ORDER BY start_time DESC')
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_running_jobs():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM jobs WHERE status = "running"')
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def update_job_progress(job_id, current_round, success, fail):
    with db_lock:
        conn = get_db()
        c = conn.cursor()
        c.execute('''
            UPDATE jobs 
            SET current_round = ?, total_success = ?, total_fail = ?
            WHERE id = ?
        ''', (current_round, success, fail, job_id))
        conn.commit()
        conn.close()

def complete_job(job_id, status='completed'):
    with db_lock:
        conn = get_db()
        c = conn.cursor()
        c.execute('''
            UPDATE jobs 
            SET status = ?, end_time = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (status, job_id))
        conn.commit()
        conn.close()

def log_api_result(job_id, target_name, success, status_code=None):
    with db_lock:
        conn = get_db()
        c = conn.cursor()
        c.execute('''
            INSERT INTO job_logs (job_id, target_name, success, status_code)
            VALUES (?, ?, ?, ?)
        ''', (job_id, target_name, 1 if success else 0, status_code))
        conn.commit()
        conn.close()

def get_job_logs(job_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        SELECT target_name, 
               SUM(success) as success_count, 
               COUNT(*) - SUM(success) as fail_count,
               MAX(timestamp) as last_attempt
        FROM job_logs 
        WHERE job_id = ?
        GROUP BY target_name
    ''', (job_id,))
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def update_daily_stats(success, fail):
    with db_lock:
        today = date.today().isoformat()
        conn = get_db()
        c = conn.cursor()
        
        c.execute('SELECT * FROM daily_stats WHERE date = ?', (today,))
        row = c.fetchone()
        
        if row:
            c.execute('''
                UPDATE daily_stats 
                SET total_sent = total_sent + ?, 
                    total_success = total_success + ?,
                    total_fail = total_fail + ?
                WHERE date = ?
            ''', (success + fail, success, fail, today))
        else:
            c.execute('''
                INSERT INTO daily_stats (date, total_sent, total_success, total_fail)
                VALUES (?, ?, ?, ?)
            ''', (today, success + fail, success, fail))
        
        conn.commit()
        conn.close()

def log_visitor(ip):
    with db_lock:
        conn = get_db()
        c = conn.cursor()
        
        # Check if IP exists
        c.execute('SELECT * FROM visitors WHERE ip = ?', (ip,))
        row = c.fetchone()
        
        if row:
            # Update existing visitor
            c.execute('''
                UPDATE visitors 
                SET last_visit = CURRENT_TIMESTAMP, 
                    visit_count = visit_count + 1 
                WHERE ip = ?
            ''', (ip,))
        else:
            # New visitor
            c.execute('INSERT INTO visitors (ip) VALUES (?)', (ip,))
        
        conn.commit()
        
        # Get total unique visitors
        c.execute('SELECT COUNT(*) FROM visitors')
        count = c.fetchone()[0]
        
        conn.close()
        return count

def get_today_stats():
    today = date.today().isoformat()
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM daily_stats WHERE date = ?', (today,))
    row = c.fetchone()
    conn.close()
    if row:
        return dict(row)
    return {'total_sent': 0, 'total_success': 0, 'total_fail': 0}

# Initialize database on import
init_db()
