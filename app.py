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
    'total_emails': 0,  # Total number of emails in the file
    'processed_emails': 0,  # Number of emails processed (including skipped ones that were already successful)
    'success_count': 0,  # Number of successful emails
    'failed_count': 0,  # Number of failed emails
    'skipped_count': 0,  # Number of emails skipped (already marked as successful in Excel)
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

def run_bot_task(excel_file_path, lottery_count=1):
    """Run the bot in a separate thread. CAPTCHA API key is loaded from environment variable in bot.py"""
    global bot_status
    
    try:
        bot_status['running'] = True
        bot_status['errors'] = []
        
        log_message("🚀 Starting bot...", 'info')
        
        # Load Excel file (convert to absolute path)
        abs_excel_file_path = os.path.abspath(excel_file_path)
        log_message(f"📄 Loading Excel file: {abs_excel_file_path}", 'info')
        log_message(f"📄 Excel file exists: {os.path.exists(abs_excel_file_path)}", 'info')
        log_message(f"📄 File size: {os.path.getsize(abs_excel_file_path) if os.path.exists(abs_excel_file_path) else 'N/A'} bytes", 'info')
        
        workbook = load_workbook(abs_excel_file_path)
        worksheet = workbook.active
        
        # Count total rows and track row numbers
        rows = list(worksheet.iter_rows(min_row=1, values_only=False))
        # Create list of (row_number, row) tuples for rows with email addresses
        # Skip rows where column C (column 3) has "成功" status
        data_rows = []
        skipped_count = 0
        total_email_count = 0
        for i, row in enumerate(rows, start=1):
            if row[0].value:
                total_email_count += 1
                # Check if column C (column 3) has "成功" status
                column_c_value = None
                if len(row) > 2 and row[2].value:
                    column_c_value = str(row[2].value).strip()
                
                if column_c_value == "成功":
                    skipped_count += 1
                    log_message(f"📋 Row {i}: {row[0].value} - Column C = '成功' (will be skipped)", 'info')
                else:
                    data_rows.append((i, row))  # i is the actual Excel row number (1-based)
        
        total_rows = len(data_rows)
        bot_status['total'] = total_rows
        bot_status['progress'] = 0
        bot_status['total_emails'] = total_email_count
        bot_status['processed_emails'] = skipped_count  # Already processed (skipped) emails are counted as processed
        bot_status['success_count'] = 0
        bot_status['failed_count'] = 0
        bot_status['skipped_count'] = skipped_count
        
        log_message(f"📊 Found {total_email_count} email(s) in Excel file", 'info')
        if skipped_count > 0:
            log_message(f"⏭️ Skipping {skipped_count} email(s) with '成功' status in Column C", 'info')
        log_message(f"📊 Will process {total_rows} email(s)", 'info')
        log_message(f"📄 Excel file path (absolute): {abs_excel_file_path}", 'info')
        log_message(f"📄 Excel file exists: {os.path.exists(abs_excel_file_path)}", 'info')
        
        # Update excel_file_path to use absolute path for consistency throughout the function
        excel_file_path = abs_excel_file_path
        
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
            row_num, row = row_tuple  # Unpack (row_number, row) tuple
            
            if not bot_status['running']:
                log_message("⏹️ Bot stopped by user", 'warning')
                break
                
            user_email = row[0].value
            user_password = row[1].value if len(row) > 1 else None
            
            if not user_email:
                continue
            
            # Check column C (column 3) for "成功" status - skip if already successful
            column_c_value = None
            if len(row) > 2 and row[2].value:
                column_c_value = str(row[2].value).strip()
            
            if column_c_value == "成功":
                log_message(f"⏭️ Skipping email {user_email} (Excel row {row_num}) - Column C already shows '成功'", 'info')
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
            
            log_message(f"📧 Processing email {progress_idx}/{total_rows}: {user_email} (Excel row {row_num})", 'info')
            
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
                    
                    # Write results to columns C and D in the current row
                    # row_num is the actual Excel row number
                    try:
                        # Convert to absolute path to ensure we're saving to the correct location
                        abs_file_path = os.path.abspath(excel_file_path)
                        log_message(f"📝 Attempting to write to Excel file (absolute path): {abs_file_path}", 'info')
                        log_message(f"📝 Excel row number: {row_num}, Column C (3): {final_status}, Column D (4): {result_message}", 'info')
                        
                        # Check file exists and get modification time before save
                        if os.path.exists(abs_file_path):
                            mtime_before = os.path.getmtime(abs_file_path)
                            log_message(f"📄 File exists. Modification time before save: {datetime.fromtimestamp(mtime_before)}", 'info')
                        else:
                            log_message(f"⚠️ File does not exist: {abs_file_path}", 'warning')
                        
                        # Close workbook if open, then reopen for writing
                        # This ensures we have exclusive access
                        try:
                            workbook.close()
                        except:
                            pass
                        
                        # Reopen workbook in read-write mode
                        workbook = load_workbook(abs_file_path)
                        worksheet = workbook.active
                        
                        # Write to column C (final status)
                        status_cell = worksheet.cell(row=row_num, column=3)
                        status_cell.value = final_status
                        log_message(f"✅ Set cell ({row_num}, 3) [Column C] value to: {final_status}", 'success')
                        
                        # Write to column D (detailed message)
                        result_cell = worksheet.cell(row=row_num, column=4)
                        result_cell.value = result_message
                        log_message(f"✅ Set cell ({row_num}, 4) [Column D] value to: {result_message}", 'success')
                        
                        # Save workbook with absolute path (MUST save before closing)
                        log_message(f"💾 Saving workbook to: {abs_file_path}", 'info')
                        workbook.save(abs_file_path)
                        
                        # IMPORTANT: Save before closing, then close to release file lock
                        workbook.close()
                        
                        # Wait a bit to ensure file system has written the changes
                        time.sleep(0.5)
                        
                        # Verify file was actually updated
                        if os.path.exists(abs_file_path):
                            mtime_after = os.path.getmtime(abs_file_path)
                            log_message(f"📄 File modification time after save: {datetime.fromtimestamp(mtime_after)}", 'info')
                            if mtime_after > mtime_before:
                                log_message(f"✅ File modification time updated - file was saved!", 'success')
                            else:
                                log_message(f"⚠️ File modification time did not change - file may not have been saved!", 'warning')
                        
                        # Reopen and verify content
                        verify_workbook = load_workbook(abs_file_path)
                        verify_worksheet = verify_workbook.active
                        verify_status_cell = verify_worksheet.cell(row=row_num, column=3)
                        verify_status_value = verify_status_cell.value
                        verify_result_cell = verify_worksheet.cell(row=row_num, column=4)
                        verify_result_value = verify_result_cell.value
                        verify_workbook.close()
                        
                        if verify_status_value == final_status and verify_result_value == result_message:
                            log_message(f"✅ Excel file saved and verified! Row {row_num}, Column C = '{verify_status_value}', Column D = '{verify_result_value}'", 'success')
                            log_message(f"✅ Full file path: {abs_file_path}", 'success')
                            log_message(f"📂 IMPORTANT: Please check this file path to see the results: {abs_file_path}", 'success')
                            log_message(f"📂 The file is saved in the 'uploads' folder, not in your original upload location", 'info')
                        else:
                            log_message(f"⚠️ Verification failed:", 'warning')
                            log_message(f"⚠️ Expected Column C: '{final_status}', got: '{verify_status_value}'", 'warning')
                            log_message(f"⚠️ Expected Column D: '{result_message}', got: '{verify_result_value}'", 'warning')
                            log_message(f"⚠️ Full file path: {abs_file_path}", 'warning')
                        
                        # Reopen workbook for next iteration
                        workbook = load_workbook(abs_file_path)
                        worksheet = workbook.active
                        
                    except Exception as e:
                        log_message(f"❌ Error writing to Excel: {e}", 'error')
                        log_message(f"❌ Excel file path (absolute): {abs_file_path}", 'error')
                        log_message(f"❌ Row: {row_num}, Columns: C (3) and D (4)", 'error')
                        traceback.print_exc()
                        # Try to reopen workbook even if save failed
                        try:
                            workbook = load_workbook(abs_file_path)
                            worksheet = workbook.active
                        except:
                            pass
                    
                    # Update success/failed counts based on final_status
                    if final_status == '成功':
                        bot_status['success_count'] += 1
                    elif final_status == '失敗':
                        bot_status['failed_count'] += 1
                    
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
                bot_status['processed_emails'] = skipped_count + progress_idx
                socketio.emit('status_update', bot_status)
                
                # Write error result to Excel columns C and D
                # C column: "失敗"
                # D column: Error details
                try:
                    error_status = '失敗'
                    error_msg = f'失敗: エラー - {str(e)[:100]}'
                    abs_file_path = os.path.abspath(excel_file_path)
                    log_message(f"📝 Writing error result to Excel row {row_num}, Column C: {error_status}, Column D: {error_msg}", 'info')
                    log_message(f"📝 Excel file path (absolute): {abs_file_path}", 'info')
                    
                    try:
                        workbook.close()
                    except:
                        pass
                    
                    workbook = load_workbook(abs_file_path)
                    worksheet = workbook.active
                    
                    # Write to column C (status)
                    status_cell = worksheet.cell(row=row_num, column=3)
                    status_cell.value = error_status
                    
                    # Write to column D (details)
                    result_cell = worksheet.cell(row=row_num, column=4)
                    result_cell.value = error_msg
                    
                    workbook.save(abs_file_path)
                    workbook.close()  # Explicitly close to ensure save
                    log_message(f"✅ Wrote error result to Excel: Column C = '{error_status}', Column D = '{error_msg}'", 'info')
                    log_message(f"✅ Saved to: {abs_file_path}", 'info')
                    
                    # Reopen for next iteration
                    time.sleep(0.3)
                    workbook = load_workbook(abs_file_path)
                    worksheet = workbook.active
                except Exception as save_error:
                    log_message(f"⚠️ Could not save error result to Excel: {save_error}", 'warning')
                    traceback.print_exc()
                    # Try to reopen workbook
                    try:
                        abs_file_path = os.path.abspath(excel_file_path)
                        workbook = load_workbook(abs_file_path)
                        worksheet = workbook.active
                    except:
                        pass
                
                traceback.print_exc()
                continue
        
        # Ensure workbook is closed to release file lock
        try:
            if 'workbook' in locals():
                workbook.close()
                log_message("📄 Workbook closed successfully", 'info')
        except Exception as e:
            log_message(f"⚠️ Error closing workbook: {e}", 'warning')
        
        # Final message with file location
        final_file_path = os.path.abspath(excel_file_path)
        log_message(f"📂 IMPORTANT: All results have been saved to: {final_file_path}", 'success')
        log_message(f"📂 The file is in the 'uploads' folder - this is NOT your original uploaded file!", 'warning')
        log_message(f"📂 Please download or check the file at: {final_file_path}", 'info')
        
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
        # Ensure workbook is closed in finally block to release file lock
        try:
            if 'workbook' in locals():
                workbook.close()
                log_message("📄 Workbook closed in finally block", 'info')
        except Exception as e:
            log_message(f"⚠️ Error closing workbook in finally block: {e}", 'warning')
        
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
    
    # Save file with unique filename if file already exists or is locked
    try:
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        # Check if file exists and if it's locked
        if os.path.exists(filepath):
            try:
                # Try to open the file in append mode to check if it's locked
                with open(filepath, 'ab'):
                    pass
                # File exists but not locked, generate unique name
                base_name, ext = os.path.splitext(filename)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
                filename = f"{base_name}_{timestamp}{ext}"
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            except (PermissionError, IOError):
                # File is locked, generate unique name
                base_name, ext = os.path.splitext(filename)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
                filename = f"{base_name}_{timestamp}{ext}"
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        # Save the file
        file.save(filepath)
        log_message(f"📄 File saved to: {filepath}", 'info')
        
    except PermissionError as e:
        # If still locked, try with unique timestamp filename
        base_name, ext = os.path.splitext(secure_filename(file.filename))
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        filename = f"{base_name}_{timestamp}{ext}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        log_message(f"⚠️ Original file was locked, saved with unique name: {filename}", 'warning')
        log_message(f"📄 File saved to: {filepath}", 'info')
    except Exception as e:
        error_msg = f"Failed to save uploaded file: {str(e)}"
        log_message(f"❌ {error_msg}", 'error')
        return jsonify({'success': False, 'message': error_msg}), 500
    
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
    bot_thread = threading.Thread(target=run_bot_task, args=(filepath, lottery_count))
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

