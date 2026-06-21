# app.py - Main Flask application for Railway
import os
import sys
import json
import time
import threading
import queue
import logging
from datetime import datetime
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
import subprocess
import re

# Import the checker functionality
from checker import AntraxRblxChecker, VerificationMode, Account

app = Flask(__name__, 
            static_folder='rob',
            static_url_path='')
CORS(app)

# Global variables
checker_instance = None
verification_thread = None
is_running = False
current_status = {
    'total': 0,
    'verified': 0,
    'valid': 0,
    'premium_accounts': 0,
    'total_robux': 0,
    'high_value_accounts': 0,
    'wrong_password': 0,
    'captcha': 0,
    'rate_limit': 0,
    'timeout': 0,
    'blocked': 0,
    'driver_error': 0,
    'other_errors': 0,
    'start_time': None,
    'recent_results': []
}

# Create uploads directory if it doesn't exist
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

@app.route('/')
def index():
    """Serve the main HTML page"""
    return send_from_directory('static', 'index.html')

@app.route('/api/status', methods=['GET'])
def get_status():
    """Get current checker status"""
    global current_status, is_running, checker_instance
    
    if checker_instance:
        # Update status from checker
        stats = checker_instance.stats
        current_status.update({
            'total': stats.get('total', 0),
            'verified': stats.get('verified', 0),
            'valid': stats.get('valid', 0),
            'premium_accounts': stats.get('premium_accounts', 0),
            'total_robux': stats.get('total_robux', 0),
            'high_value_accounts': stats.get('high_value_accounts', 0),
            'wrong_password': stats.get('wrong_password', 0),
            'captcha': stats.get('captcha', 0),
            'rate_limit': stats.get('rate_limit', 0),
            'timeout': stats.get('timeout', 0),
            'blocked': stats.get('blocked', 0),
            'driver_error': stats.get('driver_error', 0),
            'other_errors': stats.get('other_errors', 0),
            'start_time': stats.get('start_time'),
            'recent_results': checker_instance.recent_results[-10:] if checker_instance.recent_results else []
        })
    
    return jsonify({
        'is_running': is_running,
        'status': current_status,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/start', methods=['POST'])
def start_checker():
    """Start the checker with provided configuration"""
    global checker_instance, verification_thread, is_running, current_status
    
    if is_running:
        return jsonify({'error': 'Checker is already running'}), 400
    
    try:
        # Get configuration from request
        data = request.json
        
        # Save uploaded files
        combo_content = data.get('combo_content', '')
        proxy_content = data.get('proxy_content', '')
        
        if not combo_content:
            return jsonify({'error': 'No combo file content provided'}), 400
        
        # Save combo file
        combo_path = os.path.join(UPLOAD_FOLDER, f'combo_{int(time.time())}.txt')
        with open(combo_path, 'w', encoding='utf-8') as f:
            f.write(combo_content)
        
        # Save proxy file if provided
        proxy_path = None
        if proxy_content:
            proxy_path = os.path.join(UPLOAD_FOLDER, f'proxies_{int(time.time())}.txt')
            with open(proxy_path, 'w', encoding='utf-8') as f:
                f.write(proxy_content)
        
        # Create checker instance
        checker_instance = AntraxRblxChecker()
        
        # Configure checker
        mode_map = {
            'normal': VerificationMode.NORMAL,
            'headless': VerificationMode.HEADLESS,
            'stealth': VerificationMode.STEALTH,
            'rapid': VerificationMode.RAPID
        }
        
        checker_instance.mode = mode_map.get(data.get('mode', 'headless'), VerificationMode.HEADLESS)
        checker_instance.max_workers = int(data.get('threads', 3))
        checker_instance.min_delay = float(data.get('min_delay', 3))
        checker_instance.max_delay = float(data.get('max_delay', 8))
        
        # Load accounts
        if not checker_instance.load_accounts(combo_path):
            return jsonify({'error': 'Failed to load accounts'}), 400
        
        # Load proxies if provided
        if proxy_path:
            checker_instance.load_proxies(proxy_path)
        
        # Reset status
        current_status = {
            'total': len(checker_instance.accounts),
            'verified': 0,
            'valid': 0,
            'premium_accounts': 0,
            'total_robux': 0,
            'high_value_accounts': 0,
            'wrong_password': 0,
            'captcha': 0,
            'rate_limit': 0,
            'timeout': 0,
            'blocked': 0,
            'driver_error': 0,
            'other_errors': 0,
            'start_time': time.time(),
            'recent_results': []
        }
        
        # Start verification in background thread
        is_running = True
        verification_thread = threading.Thread(
            target=run_checker_thread,
            daemon=True
        )
        verification_thread.start()
        
        return jsonify({
            'success': True,
            'message': 'Checker started successfully',
            'total_accounts': len(checker_instance.accounts)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/stop', methods=['POST'])
def stop_checker():
    """Stop the checker"""
    global checker_instance, is_running
    
    if checker_instance:
        checker_instance.running = False
    
    is_running = False
    
    return jsonify({
        'success': True,
        'message': 'Checker stopped'
    })

@app.route('/api/download/<filename>', methods=['GET'])
def download_file(filename):
    """Download result files"""
    safe_files = ['valid_result.txt', 'cookie_result.txt', 'hits_summary.txt']
    
    if filename not in safe_files:
        return jsonify({'error': 'Invalid file'}), 400
    
    if os.path.exists(filename):
        return send_file(filename, as_attachment=True)
    
    return jsonify({'error': 'File not found'}), 404

@app.route('/api/files', methods=['GET'])
def list_files():
    """List available result files"""
    files = []
    result_files = ['valid_result.txt', 'cookie_result.txt', 'hits_summary.txt']
    
    for filename in result_files:
        if os.path.exists(filename):
            size = os.path.getsize(filename)
            modified = datetime.fromtimestamp(os.path.getmtime(filename))
            files.append({
                'name': filename,
                'size': size,
                'modified': modified.isoformat()
            })
    
    return jsonify({'files': files})

def run_checker_thread():
    """Run the checker in a background thread"""
    global checker_instance, is_running, current_status
    
    try:
        # Start verification
        checker_instance.start_verification()
        
    except Exception as e:
        print(f"Checker error: {e}")
    
    finally:
        is_running = False
        
        # Cleanup
        if checker_instance:
            checker_instance.driver_manager.cleanup_drivers()

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint for Railway"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat()
    })

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    # Get port from environment variable for Railway
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)