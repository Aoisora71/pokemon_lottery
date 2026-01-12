from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
import os
import sys
import threading
import queue
import time
from datetime import datetime, timedelta
import json
from werkzeug.utils import secure_filename
from openpyxl import load_workbook
import traceback
from sheets_helper import read_sheets_data, write_sheets_result, check_sheets_access, extract_spreadsheet_id

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
    'total_emails': 0,  # Total number of emails in the file
    'processed_emails': 0,  # Number of emails processed (including skipped ones that were already successful)
    'success_count': 0,  # Number of successful emails
    'failed_count': 0,  # Number of failed emails
    'skipped_count': 0,  # Number of emails skipped (already marked as successful in Excel)
    'current_step': 'Idle',
    'logs': [],
    'errors': [],
    'scheduled_restart_time': None,  # Scheduled restart time (ISO format string)
    'scheduled_restart_message': None  # Human-readable restart message
}

bot_thread = None
log_queue = queue.Queue()
_log_id_counter = 0
_log_file_lock = threading.Lock()
_current_log_file = None

# Auto-restart scheduler
_auto_restart_timer = None
_auto_restart_spreadsheet_id = None
_auto_restart_worksheet_name = None
_auto_restart_lottery_count = 1
_auto_restart_max_failures = 5
_auto_restart_mode = 'minutes'
_auto_restart_minutes = 60
_auto_restart_datetime = None

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

def start_bot_auto_restart():
    """Start the bot automatically (for auto-restart)"""
    global bot_thread, bot_status, _auto_restart_spreadsheet_id, _auto_restart_worksheet_name, _auto_restart_lottery_count, _auto_restart_max_failures, _auto_restart_mode, _auto_restart_minutes, _auto_restart_datetime
    
    if bot_status['running']:
        log_message("⚠️ Bot is already running, skipping auto-restart", 'warning')
        return
    
    if not _auto_restart_spreadsheet_id:
        log_message("⚠️ No spreadsheet ID stored for auto-restart", 'warning')
        return
    
    # Check if spreadsheet is accessible
    if not check_sheets_access(_auto_restart_spreadsheet_id, _auto_restart_worksheet_name):
        log_message(f"⚠️ Cannot access Google Spreadsheet for auto-restart: {_auto_restart_spreadsheet_id}", 'warning')
        return
    
    log_message(f"🔄 Auto-restarting bot with spreadsheet: {_auto_restart_spreadsheet_id}", 'info')
    
    # Reset status
    bot_status = {
        'running': True,
        'current_email': None,
        'progress': 0,
        'total': 0,
        'total_emails': 0,
        'processed_emails': 0,
        'success_count': 0,
        'failed_count': 0,
        'skipped_count': 0,
        'current_step': 'Auto-restarting...',
        'scheduled_restart_time': None,  # Clear scheduled restart time on auto-restart
        'scheduled_restart_message': None,
        'logs': [],
        'errors': []
    }
    
    # Use stored restart settings or defaults
    max_failures = _auto_restart_max_failures if '_auto_restart_max_failures' in globals() else 5
    restart_mode = _auto_restart_mode if '_auto_restart_mode' in globals() else 'minutes'
    restart_minutes = _auto_restart_minutes if '_auto_restart_minutes' in globals() else 60
    restart_datetime = _auto_restart_datetime if '_auto_restart_datetime' in globals() else None
    
    # Start bot in separate thread with stored settings
    bot_thread = threading.Thread(target=run_bot_task, args=(_auto_restart_spreadsheet_id, _auto_restart_worksheet_name, _auto_restart_lottery_count, max_failures, restart_mode, restart_minutes, restart_datetime))
    bot_thread.daemon = True
    bot_thread.start()
    
    log_message("✅ Bot auto-restarted successfully", 'success')

def run_bot_task(spreadsheet_id, worksheet_name=None, lottery_count=1, max_consecutive_failures=5, restart_mode='minutes', restart_minutes=60, restart_datetime=None):
    """Run the bot in a separate thread. CAPTCHA API key is loaded from environment variable in bot.py"""
    global bot_status, _auto_restart_timer, _auto_restart_file_path, _auto_restart_lottery_count, _auto_restart_max_failures, _auto_restart_mode, _auto_restart_minutes, _auto_restart_datetime
    
    try:
        bot_status['running'] = True
        bot_status['errors'] = []
        bot_status['scheduled_restart_time'] = None  # Clear scheduled restart time when starting
        bot_status['scheduled_restart_message'] = None
        
        # Initialize consecutive failure counter
        consecutive_failures = 0
        MAX_CONSECUTIVE_FAILURES = max_consecutive_failures
        
        log_message("🚀 Starting bot...", 'info')
        
        # Load Google Sheets data
        log_message(f"📄 Loading Google Spreadsheet: {spreadsheet_id}", 'info')
        if worksheet_name:
            log_message(f"📄 Using worksheet: {worksheet_name}", 'info')
        else:
            log_message(f"📄 Using first worksheet (default)", 'info')
        
        # Read data from Google Sheets
        data_rows, total_email_count, skipped_count = read_sheets_data(spreadsheet_id, worksheet_name)
        
        total_rows = len(data_rows)
        bot_status['total'] = total_rows
        bot_status['progress'] = 0
        bot_status['total_emails'] = total_email_count
        bot_status['processed_emails'] = skipped_count  # Already processed (skipped) emails are counted as processed
        bot_status['success_count'] = 0
        bot_status['failed_count'] = 0
        bot_status['skipped_count'] = skipped_count
        
        log_message(f"📊 Found {total_email_count} email(s) in Google Spreadsheet", 'info')
        if skipped_count > 0:
            log_message(f"⏭️ Skipping {skipped_count} email(s) with '成功' status in Column C", 'info')
        log_message(f"📊 Will process {total_rows} email(s)", 'info')
        
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
        for progress_idx, row_tuple in enumerate(data_rows, start=1):
            row_num, user_email, user_password = row_tuple  # Unpack (row_number, email, password) tuple
            
            if not bot_status['running']:
                log_message("⏹️ Bot stopped by user", 'warning')
                break
            
            if not user_email:
                continue
            
            # Note: data_rows already excludes rows with "成功" status, so no need to check again
                bot_status['current_email'] = user_email
                bot_status['progress'] = progress_idx
                bot_status['processed_emails'] = skipped_count + progress_idx  # Update processed count (skipped + processed so far)
                bot_status['success_count'] += 1  # Count skipped emails as success
                bot_status['current_step'] = f'Skipped {user_email} (already successful)'
                socketio.emit('status_update', bot_status)  # Emit update for skipped email
                continue  # Skip this email and proceed to next one
            
            bot_status['current_email'] = user_email
            bot_status['progress'] = progress_idx
            bot_status['processed_emails'] = skipped_count + progress_idx  # Update processed count
            bot_status['current_step'] = f'Processing {user_email}'
            socketio.emit('status_update', bot_status)  # Emit update before processing
            
            log_message(f"📧 Processing email {progress_idx}/{total_rows}: {user_email} (Spreadsheet row {row_num})", 'info')
            
            try:
                # Update global EMAIL and PASSWORD for bot.py
                # EMAIL must be from Excel file (not from .env)
                # PASSWORD can be from Excel file or .env file
                import bot
                bot.EMAIL = user_email  # Required from Excel
                if user_password:
                    bot.PASSWORD = user_password
                elif not bot.PASSWORD:
                    raise ValueError("PASSWORD is not set. Please include it in column B of the Excel file or set it in .env file.")
                
                # Set up logging callback for bot.py
                bot.set_logger(log_message)
                
                # Set up stop check callback for bot.py
                bot.set_stop_check(lambda: bot_status['running'])
                
                # Set maximum number of lotteries to process
                bot.set_max_lotteries(lottery_count)
                
                # Run lottery process
                bot_status['current_step'] = f'Logging in as {user_email}'
                log_message(f"🔐 Starting login process for {user_email}. Will process up to {lottery_count} lotteries.", 'info')
                lottery_result = None
                try:
                    lottery_result = lottery_begin(driver, wait)
                except StopIteration:
                    log_message("⏹️ Login process stopped by user", 'warning')
                    break
                except Exception as e:
                    log_message(f"❌ Error during lottery process: {str(e)}", 'error')
                    # Set failure result if exception occurs
                    lottery_result = {
                        'results': [],
                        'final_status': '失敗',
                        'message': f'エラー: {str(e)[:100]}'
                    }
                
                # Write result to Excel columns C and D
                # C column (3): Final status (成功/失敗)
                # D column (4): Detailed message
                if lottery_result:
                    final_status = lottery_result.get('final_status', '不明')
                    result_message = lottery_result.get('message', '不明')
                    log_message(f"📊 Lottery result for {user_email}: Status={final_status}, Details={result_message}", 'info')
                    
                    # Write results to columns C, D, and E in Google Sheets
                    try:
                        # Get current timestamp first
                        timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        
                        log_message(f"📝 Writing to Google Spreadsheet row {row_num}, Column C: {final_status}, Column D: {result_message}, Column E: {timestamp_str}", 'info')
                        
                        # Write to Google Sheets
                        write_sheets_result(spreadsheet_id, row_num, final_status, result_message, timestamp_str, worksheet_name)
                        
                        log_message(f"✅ Successfully wrote to Google Spreadsheet row {row_num}", 'success')
                    except Exception as e:
                        log_message(f"❌ Error writing to Google Sheets: {str(e)}", 'error')
                        import traceback
                        log_message(f"❌ Traceback: {traceback.format_exc()}", 'error')
                    
                    # Update success/failed counts based on final_status
                    if final_status == '成功':
                        bot_status['success_count'] += 1
                        # Reset consecutive failure counter on success
                        consecutive_failures = 0
                        log_message(f"✅ Success! Consecutive failures reset to 0", 'success')
                    elif final_status == '失敗':
                        bot_status['failed_count'] += 1
                        # Increment consecutive failure counter
                        consecutive_failures += 1
                        log_message(f"⚠️ Failure detected. Consecutive failures: {consecutive_failures}/{MAX_CONSECUTIVE_FAILURES}", 'warning')
                        
                        # Check if we've reached the maximum consecutive failures
                        if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                            log_message(f"🛑 {MAX_CONSECUTIVE_FAILURES} consecutive failures detected! Stopping bot...", 'error')
                            
                            # Stop the bot
                            bot_status['running'] = False
                            
                            # Schedule auto-restart based on mode
                            _auto_restart_spreadsheet_id = spreadsheet_id
                            _auto_restart_worksheet_name = worksheet_name
                            _auto_restart_lottery_count = lottery_count
                            _auto_restart_max_failures = max_consecutive_failures
                            _auto_restart_mode = restart_mode
                            _auto_restart_minutes = restart_minutes
                            _auto_restart_datetime = restart_datetime
                            
                            # Cancel existing timer if any
                            if _auto_restart_timer:
                                try:
                                    _auto_restart_timer.cancel()
                                except:
                                    pass
                            
                            # Calculate restart time based on mode
                            restart_time = None
                            restart_seconds = 0
                            
                            if restart_mode == 'minutes':
                                # Restart after specified minutes
                                restart_seconds = restart_minutes * 60
                                restart_time = datetime.now() + timedelta(seconds=restart_seconds)
                                log_message(f"⏰ Bot will automatically restart after {restart_minutes} minutes...", 'info')
                            else:
                                # Restart at specific datetime
                                if restart_datetime:
                                    try:
                                        # Parse datetime string (format: YYYY-MM-DDTHH:MM)
                                        restart_dt = datetime.strptime(restart_datetime, '%Y-%m-%dT%H:%M')
                                        now = datetime.now()
                                        
                                        if restart_dt <= now:
                                            log_message(f"⚠️ Specified restart time is in the past. Restarting immediately...", 'warning')
                                            restart_seconds = 0
                                            restart_time = now
                                        else:
                                            restart_seconds = int((restart_dt - now).total_seconds())
                                            restart_time = restart_dt
                                        
                                        log_message(f"⏰ Bot will automatically restart at {restart_time.strftime('%Y-%m-%d %H:%M:%S')}...", 'info')
                                    except Exception as e:
                                        log_message(f"❌ Error parsing restart datetime: {e}. Using default 60 minutes...", 'error')
                                        restart_seconds = 3600
                                        restart_time = datetime.now() + timedelta(hours=1)
                                else:
                                    # Fallback to 60 minutes if datetime not provided
                                    restart_seconds = 3600
                                    restart_time = datetime.now() + timedelta(hours=1)
                                    log_message(f"⏰ Bot will automatically restart after 60 minutes (default)...", 'info')
                            
                            # Update bot_status with scheduled restart time
                            if restart_time:
                                bot_status['scheduled_restart_time'] = restart_time.isoformat()
                                socketio.emit('status_update', bot_status)
                            
                            # Schedule auto-restart using threading.Timer
                            def schedule_restart():
                                if not bot_status['running']:
                                    log_message(f"🔄 Auto-restarting bot...", 'info')
                                    start_bot_auto_restart()
                            
                            _auto_restart_timer = threading.Timer(restart_seconds, schedule_restart)
                            _auto_restart_timer.daemon = True
                            _auto_restart_timer.start()
                            
                            if restart_time:
                                log_message(f"⏰ Auto-restart scheduled for {restart_time.strftime('%Y-%m-%d %H:%M:%S')}", 'info')
                            break  # Exit the loop
                    
                    # Update processed count (skipped_count already included, now add this processed one)
                    bot_status['processed_emails'] = skipped_count + progress_idx
                    
                    # Emit status update
                    socketio.emit('status_update', bot_status)
                
                log_message(f"✅ Successfully processed: {user_email}", 'success')
                
            except Exception as e:
                error_msg = f"❌ Error processing {user_email}: {str(e)}"
                log_message(error_msg, 'error')
                bot_status['errors'].append({
                    'email': user_email,
                    'error': str(e),
                    'timestamp': datetime.now().isoformat()
                })
                
                # Update failed count for exception
                bot_status['failed_count'] += 1
                # Increment consecutive failure counter for exceptions too
                consecutive_failures += 1
                log_message(f"⚠️ Exception failure detected. Consecutive failures: {consecutive_failures}/{MAX_CONSECUTIVE_FAILURES}", 'warning')
                
                bot_status['processed_emails'] = skipped_count + progress_idx
                socketio.emit('status_update', bot_status)
                
                # Check if we've reached the maximum consecutive failures
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    log_message(f"🛑 {MAX_CONSECUTIVE_FAILURES} consecutive failures detected! Stopping bot...", 'error')
                    
                    # Stop the bot
                    bot_status['running'] = False
                    
                    # Schedule auto-restart based on mode
                    _auto_restart_spreadsheet_id = spreadsheet_id
                    _auto_restart_worksheet_name = worksheet_name
                    _auto_restart_lottery_count = lottery_count
                    _auto_restart_max_failures = max_consecutive_failures
                    _auto_restart_mode = restart_mode
                    _auto_restart_minutes = restart_minutes
                    _auto_restart_datetime = restart_datetime
                    
                    # Cancel existing timer if any
                    if _auto_restart_timer:
                        try:
                            _auto_restart_timer.cancel()
                        except:
                            pass
                    
                    # Calculate restart time based on mode
                    restart_time = None
                    restart_seconds = 0
                    
                    if restart_mode == 'minutes':
                        # Restart after specified minutes
                        restart_seconds = restart_minutes * 60
                        restart_time = datetime.now() + timedelta(seconds=restart_seconds)
                        log_message(f"⏰ Bot will automatically restart after {restart_minutes} minutes...", 'info')
                    else:
                        # Restart at specific datetime
                        if restart_datetime:
                            try:
                                # Parse datetime string (format: YYYY-MM-DDTHH:MM)
                                restart_dt = datetime.strptime(restart_datetime, '%Y-%m-%dT%H:%M')
                                now = datetime.now()
                                
                                if restart_dt <= now:
                                    log_message(f"⚠️ Specified restart time is in the past. Restarting immediately...", 'warning')
                                    restart_seconds = 0
                                    restart_time = now
                                else:
                                    restart_seconds = int((restart_dt - now).total_seconds())
                                    restart_time = restart_dt
                                
                                log_message(f"⏰ Bot will automatically restart at {restart_time.strftime('%Y-%m-%d %H:%M:%S')}...", 'info')
                            except Exception as e:
                                log_message(f"❌ Error parsing restart datetime: {e}. Using default 60 minutes...", 'error')
                                restart_seconds = 3600
                                restart_time = datetime.now() + timedelta(hours=1)
                        else:
                            # Fallback to 60 minutes if datetime not provided
                            restart_seconds = 3600
                            restart_time = datetime.now() + timedelta(hours=1)
                            log_message(f"⏰ Bot will automatically restart after 60 minutes (default)...", 'info')
                    
                    # Update bot_status with scheduled restart time
                    if restart_time:
                        bot_status['scheduled_restart_time'] = restart_time.isoformat()
                        socketio.emit('status_update', bot_status)
                    
                    # Schedule auto-restart using threading.Timer
                    def schedule_restart():
                        if not bot_status['running']:
                            log_message(f"🔄 Auto-restarting bot...", 'info')
                            start_bot_auto_restart()
                    
                    _auto_restart_timer = threading.Timer(restart_seconds, schedule_restart)
                    _auto_restart_timer.daemon = True
                    _auto_restart_timer.start()
                    
                    if restart_time:
                        log_message(f"⏰ Auto-restart scheduled for {restart_time.strftime('%Y-%m-%d %H:%M:%S')}", 'info')
                    break  # Exit the loop
                
                # Write error result to Google Sheets columns C, D, and E
                # C column: "失敗"
                # D column: Error details
                # E column: Timestamp
                try:
                    error_status = '失敗'
                    error_msg = f'失敗: エラー - {str(e)[:100]}'
                    error_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    log_message(f"📝 Writing error result to Google Spreadsheet row {row_num}, Column C: {error_status}, Column D: {error_msg}, Column E: {error_timestamp}", 'info')
                    
                    # Write to Google Sheets
                    write_sheets_result(spreadsheet_id, row_num, error_status, error_msg, error_timestamp, worksheet_name)
                    
                    log_message(f"✅ Wrote error result to Google Spreadsheet: Column C = '{error_status}', Column D = '{error_msg}', Column E = '{error_timestamp}'", 'info')
                except Exception as save_error:
                    log_message(f"⚠️ Could not save error result to Google Sheets: {save_error}", 'warning')
                    traceback.print_exc()
                
                traceback.print_exc()
                continue
        
        # Ensure workbook is closed to release file lock
        # Final message
        log_message(f"📂 IMPORTANT: All results have been saved to Google Spreadsheet: {spreadsheet_id}", 'success')
        if worksheet_name:
            log_message(f"📂 Worksheet: {worksheet_name}", 'info')
        
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
        # Cleanup completed
        pass
        
        # Ensure driver is closed
        try:
            if 'driver' in locals():
                driver.quit()
                log_message("🌐 Browser closed in finally block", 'info')
        except Exception as e:
            log_message(f"⚠️ Error closing browser in finally block: {e}", 'warning')
        
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
    global bot_thread, bot_status, _auto_restart_spreadsheet_id, _auto_restart_worksheet_name, _auto_restart_lottery_count
    
    if bot_status['running']:
        return jsonify({'success': False, 'message': 'Bot is already running'}), 400
    
    # Get Google Spreadsheet ID
    spreadsheet_id = request.form.get('spreadsheet_id', '').strip()
    if not spreadsheet_id:
        return jsonify({'success': False, 'message': 'Please enter a Google Spreadsheet ID or URL'}), 400
    
    # Get worksheet name (optional)
    worksheet_name = request.form.get('worksheet_name', '').strip()
    if not worksheet_name:
        worksheet_name = None
    
    # Check if spreadsheet is accessible
    try:
        if not check_sheets_access(spreadsheet_id, worksheet_name):
            return jsonify({'success': False, 'message': 'Cannot access Google Spreadsheet. Please check the ID/URL and ensure the service account has access.'}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error accessing Google Spreadsheet: {str(e)}'}), 400
    
    log_message(f"📄 Using Google Spreadsheet: {spreadsheet_id}", 'info')
    if worksheet_name:
        log_message(f"📄 Using worksheet: {worksheet_name}", 'info')
    
    # CAPTCHA API key is loaded from environment variable in bot.py
    # Check if CAPTCHA API key is set in environment
    captcha_api_key = os.getenv('CAPTCHA_API_KEY')
    if not captcha_api_key:
        return jsonify({'success': False, 'message': 'CAPTCHA API key is required. Please set CAPTCHA_API_KEY in .env file.'}), 400
    
    # Get lottery count from form (default: 1 if not provided)
    try:
        lottery_count = int(request.form.get('lottery_count', 1))
        if lottery_count < 1 or lottery_count > 5:
            return jsonify({'success': False, 'message': 'Lottery count must be between 1 and 5'}), 400
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Invalid lottery count. Please enter a number between 1 and 5'}), 400
    
    # Get max consecutive failures from form (default: 5 if not provided)
    try:
        max_consecutive_failures = int(request.form.get('max_consecutive_failures', 5))
        if max_consecutive_failures < 1 or max_consecutive_failures > 20:
            return jsonify({'success': False, 'message': 'Max consecutive failures must be between 1 and 20'}), 400
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Invalid max consecutive failures. Please enter a number between 1 and 20'}), 400
    
    # Get restart mode and settings
    restart_mode = request.form.get('restart_mode', 'minutes')
    restart_minutes = None
    restart_datetime = None
    
    if restart_mode == 'minutes':
        try:
            restart_minutes = int(request.form.get('restart_minutes', 60))
            if restart_minutes < 1:
                return jsonify({'success': False, 'message': 'Restart minutes must be at least 1'}), 400
        except (ValueError, TypeError):
            return jsonify({'success': False, 'message': 'Invalid restart minutes. Please enter a valid number'}), 400
    elif restart_mode == 'datetime':
        restart_datetime = request.form.get('restart_datetime')
        if not restart_datetime:
            return jsonify({'success': False, 'message': 'Please select a restart date and time'}), 400
        try:
            # Validate datetime format and check if it's in the future
            restart_dt = datetime.strptime(restart_datetime, '%Y-%m-%dT%H:%M')
            if restart_dt <= datetime.now():
                return jsonify({'success': False, 'message': 'Restart datetime must be in the future'}), 400
        except ValueError:
            return jsonify({'success': False, 'message': 'Invalid datetime format. Please use YYYY-MM-DDTHH:MM format'}), 400
    
    # Cancel any existing auto-restart timer
    global _auto_restart_timer
    if _auto_restart_timer:
        try:
            _auto_restart_timer.cancel()
            log_message("⏹️ Cancelled existing auto-restart timer", 'info')
        except:
            pass
    
    # Store spreadsheet ID and settings for potential auto-restart
    _auto_restart_spreadsheet_id = spreadsheet_id
    _auto_restart_worksheet_name = worksheet_name
    _auto_restart_lottery_count = lottery_count
    _auto_restart_max_failures = max_consecutive_failures
    _auto_restart_mode = restart_mode
    _auto_restart_minutes = restart_minutes
    _auto_restart_datetime = restart_datetime
    
    # Reset status
    bot_status = {
        'running': True,
        'current_email': None,
        'progress': 0,
        'total': 0,
        'total_emails': 0,
        'processed_emails': 0,
        'success_count': 0,
        'failed_count': 0,
        'skipped_count': 0,
        'current_step': 'Starting...',
        'logs': [],
        'errors': []
    }
    
    # Start bot in separate thread (CAPTCHA API key is loaded from env in bot.py)
    bot_thread = threading.Thread(target=run_bot_task, args=(spreadsheet_id, worksheet_name, lottery_count, max_consecutive_failures, restart_mode, restart_minutes, restart_datetime))
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

@app.route('/api/check-spreadsheet', methods=['POST'])
def check_spreadsheet():
    """Check if Google Spreadsheet is accessible"""
    try:
        data = request.get_json()
        spreadsheet_id = data.get('spreadsheet_id', '').strip()
        worksheet_name = data.get('worksheet_name')
        
        if not spreadsheet_id:
            return jsonify({'success': False, 'message': 'Spreadsheet ID is required'}), 400
        
        if worksheet_name and not worksheet_name.strip():
            worksheet_name = None
        elif worksheet_name:
            worksheet_name = worksheet_name.strip()
        
        if check_sheets_access(spreadsheet_id, worksheet_name):
            return jsonify({'success': True, 'message': 'Spreadsheet is accessible'})
        else:
            return jsonify({'success': False, 'message': 'Cannot access spreadsheet. Please check the ID/URL and ensure the service account has access.'}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error checking spreadsheet: {str(e)}'}), 500

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
