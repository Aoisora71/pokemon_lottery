from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
import os
import sys
import threading
import queue
import time
from datetime import datetime
import json
from werkzeug.utils import secure_filename
from openpyxl import load_workbook
import traceback

# Import bot functions
try:
    from bot import lottery_begin
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.support.ui import WebDriverWait
    from webdriver_manager.chrome import ChromeDriverManager
except ImportError as e:
    print(f"Warning: Could not import bot modules: {e}")
    print("Make sure all dependencies are installed: pip install -r requirements.txt")

app = Flask(__name__)
app.config['SECRET_KEY'] = 'pokemon-lottery-bot-secret-key-2024'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['LOG_FOLDER'] = 'logs'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Create necessary directories if they don't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['LOG_FOLDER'], exist_ok=True)

# Global state
bot_status = {
    'running': False,
    'current_email': None,
    'progress': 0,
    'total': 0,
    'current_step': 'Idle',
    'logs': [],
    'errors': []
}

bot_thread = None
log_queue = queue.Queue()
_log_id_counter = 0
_log_file_lock = threading.Lock()
_current_log_file = None

def get_log_filename():
    """Get the log filename for today"""
    today = datetime.now().strftime('%Y-%m-%d')
    return os.path.join(app.config['LOG_FOLDER'], f'bot_{today}.log')

def write_log_to_file(log_entry):
    """Write log entry to file in a thread-safe manner"""
    global _current_log_file
    
    try:
        log_filename = get_log_filename()
        
        # Check if we need to rotate (new day)
        if _current_log_file != log_filename:
            _current_log_file = log_filename
        
        # Format log entry for file
        log_line = f"[{log_entry['timestamp']}] [{log_entry['level'].upper()}] {log_entry['message']}\n"
        
        # Thread-safe file writing
        with _log_file_lock:
            with open(log_filename, 'a', encoding='utf-8') as f:
                f.write(log_line)
                f.flush()  # Ensure immediate write
        
    except Exception as e:
        # Don't break the application if file logging fails
        print(f"Error writing to log file: {e}")

def cleanup_old_logs(days_to_keep=30):
    """Remove log files older than specified days"""
    try:
        log_folder = app.config['LOG_FOLDER']
        if not os.path.exists(log_folder):
            return
        
        current_time = time.time()
        cutoff_time = current_time - (days_to_keep * 24 * 60 * 60)
        
        for filename in os.listdir(log_folder):
            if filename.startswith('bot_') and filename.endswith('.log'):
                filepath = os.path.join(log_folder, filename)
                try:
                    if os.path.getmtime(filepath) < cutoff_time:
                        os.remove(filepath)
                        print(f"Removed old log file: {filename}")
                except Exception as e:
                    print(f"Error removing log file {filename}: {e}")
    except Exception as e:
        print(f"Error cleaning up old logs: {e}")

def log_message(message, level='info'):
    """Add log message to queue and emit via WebSocket, and always print to terminal"""
    global _log_id_counter
    _log_id_counter += 1
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = {
        'id': _log_id_counter,  # Unique ID for duplicate detection
        'timestamp': timestamp,
        'level': level,
        'message': message
    }
    bot_status['logs'].append(log_entry)
    # Keep only last 1000 logs
    if len(bot_status['logs']) > 1000:
        bot_status['logs'] = bot_status['logs'][-1000:]
    
    # Write to log file
    write_log_to_file(log_entry)
    
    # Always print to terminal with detailed formatting
    colors = {
        'info': '\033[36m',      # Cyan
        'success': '\033[32m',   # Green
        'warning': '\033[33m',   # Yellow
        'error': '\033[31m',     # Red
    }
    reset_color = '\033[0m'
    bold = '\033[1m'
    
    # Check if terminal supports colors
    use_colors = True
    try:
        if sys.platform == 'win32':
            use_colors = sys.stdout.isatty()
    except:
        use_colors = False
    
    color = colors.get(level, colors['info']) if use_colors else ''
    reset = reset_color if use_colors else ''
    bold_prefix = bold if use_colors else ''
    level_prefix = level.upper().ljust(8)
    
    if use_colors:
        terminal_message = f"[{timestamp}] [{bold_prefix}{color}{level_prefix}{reset}] {message}"
    else:
        terminal_message = f"[{timestamp}] [{level_prefix}] {message}"
    
    # Print to terminal (stdout)
    print(terminal_message, flush=True)
    
    # Put in queue for background thread to emit (removed direct emit to avoid duplicates)
    log_queue.put(log_entry)

def run_bot_task(excel_file_path, captcha_api_key):
    """Run the bot in a separate thread"""
    global bot_status
    
    try:
        bot_status['running'] = True
        bot_status['errors'] = []
        
        log_message("🚀 Starting bot...", 'info')
        
        # Load Excel file
        log_message(f"📄 Loading Excel file: {excel_file_path}", 'info')
        workbook = load_workbook(excel_file_path)
        worksheet = workbook.active
        
        # Count total rows
        rows = list(worksheet.iter_rows(min_row=1, values_only=False))
        total_rows = sum(1 for row in rows if row[0].value)
        bot_status['total'] = total_rows
        bot_status['progress'] = 0
        
        log_message(f"📊 Found {total_rows} email(s) to process", 'info')
        
        # Setup Chrome driver
        log_message("🌐 Setting up Chrome browser...", 'info')
        chrome_options = Options()
        chrome_options.add_argument('--start-maximized')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option('useAutomationExtension', False)
        # Suppress Chrome warnings and errors
        chrome_options.add_argument('--log-level=3')  # Only show fatal errors
        chrome_options.add_argument('--disable-logging')
        chrome_options.add_argument('--disable-gpu-logging')
        chrome_options.add_argument('--disable-background-networking')  # Disable GCM/background services
        chrome_options.add_experimental_option('excludeSwitches', ['enable-automation', 'enable-logging'])
        # Run in headless mode for server (comment out to see browser)
        # chrome_options.add_argument('--headless')
        
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': 'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
        })
        wait = WebDriverWait(driver, 30)
        
        # Process each row
        for idx, row in enumerate(rows, 1):
            if not bot_status['running']:
                log_message("⏹️ Bot stopped by user", 'warning')
                break
                
            user_email = row[0].value
            user_password = row[1].value if len(row) > 1 else None
            
            if not user_email:
                continue
            
            bot_status['current_email'] = user_email
            bot_status['progress'] = idx
            bot_status['current_step'] = f'Processing {user_email}'
            
            log_message(f"📧 Processing email {idx}/{total_rows}: {user_email}", 'info')
            
            try:
                # Update global EMAIL and PASSWORD for bot.py
                import bot
                bot.EMAIL = user_email
                if user_password:
                    bot.PASSWORD = user_password
                elif not bot.PASSWORD:
                    raise ValueError("PASSWORD is not set. Please include it in column B of the Excel file or set it in .env file.")
                
                # Set up logging callback for bot.py
                bot.set_logger(log_message)
                
                # Set up stop check callback for bot.py
                bot.set_stop_check(lambda: bot_status['running'])
                
                # Run lottery process
                bot_status['current_step'] = f'Logging in as {user_email}'
                log_message(f"🔐 Starting login process for {user_email}", 'info')
                try:
                    lottery_begin(driver, wait)
                except StopIteration:
                    log_message("⏹️ Login process stopped by user", 'warning')
                    break
                
                log_message(f"✅ Successfully processed: {user_email}", 'success')
                
            except Exception as e:
                error_msg = f"❌ Error processing {user_email}: {str(e)}"
                log_message(error_msg, 'error')
                bot_status['errors'].append({
                    'email': user_email,
                    'error': str(e),
                    'timestamp': datetime.now().isoformat()
                })
                traceback.print_exc()
                continue
        
        workbook.close()
        
        # Close driver gracefully
        try:
            driver.quit()
            log_message("🌐 Browser closed", 'info')
        except Exception as e:
            log_message(f"⚠️ Error closing browser: {e}", 'warning')
        
        if bot_status['running']:
            log_message("🎉 All emails processed successfully!", 'success')
            bot_status['current_step'] = 'Completed'
        else:
            log_message("⏹️ Bot stopped by user", 'warning')
            bot_status['current_step'] = 'Stopped'
        
    except Exception as e:
        error_msg = f"❌ Fatal error: {str(e)}"
        log_message(error_msg, 'error')
        bot_status['errors'].append({
            'email': 'System',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        })
        traceback.print_exc()
    finally:
        bot_status['running'] = False
        bot_status['current_step'] = 'Idle'
        socketio.emit('status_update', bot_status)

@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('index.html')

@app.route('/api/status', methods=['GET'])
def get_status():
    """Get current bot status"""
    return jsonify(bot_status)

@app.route('/api/start', methods=['POST'])
def start_bot():
    """Start the bot"""
    global bot_thread, bot_status
    
    if bot_status['running']:
        return jsonify({'success': False, 'message': 'Bot is already running'}), 400
    
    # Get uploaded file
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'No file uploaded'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'No file selected'}), 400
    
    if not file.filename.endswith(('.xlsx', '.xls')):
        return jsonify({'success': False, 'message': 'Invalid file type. Please upload Excel file (.xlsx or .xls)'}), 400
    
    # Save file
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    
    # Get CAPTCHA API key from request or env
    captcha_api_key = request.form.get('captcha_api_key') or os.getenv('CAPTCHA_API_KEY')
    if not captcha_api_key:
        return jsonify({'success': False, 'message': 'CAPTCHA API key is required'}), 400
    
    # Reset status
    bot_status = {
        'running': True,
        'current_email': None,
        'progress': 0,
        'total': 0,
        'current_step': 'Starting...',
        'logs': [],
        'errors': []
    }
    
    # Start bot in separate thread
    bot_thread = threading.Thread(target=run_bot_task, args=(filepath, captcha_api_key))
    bot_thread.daemon = True
    bot_thread.start()
    
    return jsonify({'success': True, 'message': 'Bot started successfully'})

@app.route('/api/stop', methods=['POST'])
def stop_bot():
    """Stop the bot"""
    global bot_status
    
    if not bot_status['running']:
        return jsonify({'success': False, 'message': 'Bot is not running'}), 400
    
    bot_status['running'] = False
    log_message("⏹️ Stop request received", 'warning')
    
    return jsonify({'success': True, 'message': 'Stop request sent'})

@app.route('/api/logs', methods=['GET'])
def get_logs():
    """Get recent logs"""
    limit = request.args.get('limit', 100, type=int)
    logs = bot_status['logs'][-limit:]
    return jsonify(logs)

@app.route('/api/clear-logs', methods=['POST'])
def clear_logs():
    """Clear logs from memory (does not delete log files)"""
    bot_status['logs'] = []
    return jsonify({'success': True})

@app.route('/api/logs/download', methods=['GET'])
def download_logs():
    """Download today's log file"""
    try:
        log_filename = get_log_filename()
        if os.path.exists(log_filename):
            return send_from_directory(
                app.config['LOG_FOLDER'],
                os.path.basename(log_filename),
                as_attachment=True,
                download_name=f'bot_log_{datetime.now().strftime("%Y-%m-%d")}.log'
            )
        else:
            return jsonify({'success': False, 'message': 'Log file not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/logs/list', methods=['GET'])
def list_log_files():
    """List available log files"""
    try:
        log_folder = app.config['LOG_FOLDER']
        if not os.path.exists(log_folder):
            return jsonify({'success': True, 'files': []})
        
        log_files = []
        for filename in sorted(os.listdir(log_folder), reverse=True):
            if filename.startswith('bot_') and filename.endswith('.log'):
                filepath = os.path.join(log_folder, filename)
                file_size = os.path.getsize(filepath)
                file_mtime = datetime.fromtimestamp(os.path.getmtime(filepath)).isoformat()
                log_files.append({
                    'filename': filename,
                    'size': file_size,
                    'modified': file_mtime
                })
        
        return jsonify({'success': True, 'files': log_files})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# WebSocket events
@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    emit('status_update', bot_status)
    log_message("👤 Client connected", 'info')

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    log_message("👤 Client disconnected", 'info')

# Background task to emit logs
def emit_logs():
    """Emit logs from queue via WebSocket"""
    last_status_update = 0
    while True:
        try:
            log_entry = log_queue.get(timeout=1)
            socketio.emit('log', log_entry)
            # Only emit status update every 2 seconds to avoid excessive updates
            import time
            current_time = time.time()
            if current_time - last_status_update >= 2:
                socketio.emit('status_update', bot_status)
                last_status_update = current_time
        except queue.Empty:
            continue
        except Exception as e:
            print(f"Error emitting log: {e}")

# Start background task
log_thread = threading.Thread(target=emit_logs)
log_thread.daemon = True
log_thread.start()

if __name__ == '__main__':
    print("=" * 60)
    print("🎮 Pokemon Center Lottery Bot - Web Interface")
    print("=" * 60)
    print("🌐 Starting web server...")
    print("📱 Open your browser and go to: http://localhost:5000")
    print("=" * 60)
    # Disable reloader on Windows to avoid socket errors
    use_reloader = sys.platform != 'win32'
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, use_reloader=use_reloader, allow_unsafe_werkzeug=True)

