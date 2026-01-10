import time
import re
import sys
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import requests
from dotenv import load_dotenv
import os
from openpyxl import load_workbook

load_dotenv()

from main import get_service, list_messages, get_message

# Enable ANSI color codes on Windows 10+
if sys.platform == 'win32':
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except:
        pass  # If it fails, continue without colors

CAPTCHA_API_KEY = os.getenv("CAPTCHA_API_KEY")
EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")
LOGIN_URL = "https://www.pokemoncenter-online.com/lottery/login.html"
APPLY_URL = "https://www.pokemoncenter-online.com/lottery/apply.html"

# Logger callback - will be set by app.py
_logger = None
_stop_check = None

def set_logger(logger_func):
    """Set the logging function to use instead of print()"""
    global _logger
    _logger = logger_func

def set_stop_check(stop_check_func):
    """Set the stop check function to check if bot should stop"""
    global _stop_check
    _stop_check = stop_check_func

def check_stop():
    """Check if bot should stop. Raises StopIteration if stopped."""
    if _stop_check and not _stop_check():
        raise StopIteration("Bot stopped by user")

def log(message, level='info'):
    """Log a message using the logger callback if available, and always print to terminal with detailed formatting"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Color codes for terminal output (ANSI escape codes)
    colors = {
        'info': '\033[36m',      # Cyan
        'success': '\033[32m',   # Green
        'warning': '\033[33m',   # Yellow
        'error': '\033[31m',     # Red
    }
    reset_color = '\033[0m'
    bold = '\033[1m'
    
    # Check if terminal supports colors (try-except for safety)
    use_colors = True
    try:
        # Test if colors work
        if sys.platform == 'win32':
            # Windows might not support colors in all terminals
            use_colors = sys.stdout.isatty()
    except:
        use_colors = False
    
    color = colors.get(level, colors['info']) if use_colors else ''
    reset = reset_color if use_colors else ''
    bold_prefix = bold if use_colors else ''
    
    level_prefix = level.upper().ljust(8)
    
    # Format: [TIMESTAMP] [LEVEL] message
    if use_colors:
        terminal_message = f"[{timestamp}] [{bold_prefix}{color}{level_prefix}{reset}] {message}"
    else:
        # Fallback without colors
        terminal_message = f"[{timestamp}] [{level_prefix}] {message}"
    
    # If logger callback is set (from app.py), it will handle terminal output
    # Otherwise, print directly to terminal (when running bot.py directly)
    if _logger:
        # Web app mode: logger callback handles terminal output
        _logger(message, level)
    else:
        # Direct execution mode: print directly to terminal
        print(terminal_message, flush=True)

def check_login_status_message(driver, wait=None):
    """Check and log the login status message from the page xpath: //*[@id="main"]/div/div[2]/div/div[1]/p"""
    try:
        if wait is None:
            wait = WebDriverWait(driver, 3)  # Short timeout for status check
        
        # Primary check: Try to find the login status message element at the specified xpath
        status_xpath = '//*[@id="main"]/div/div[2]/div/div[1]/p'
        try:
            # Use find_elements instead of wait.until to avoid exceptions if element doesn't exist
            status_elements = driver.find_elements(By.XPATH, status_xpath)
            if status_elements:
                status_element = status_elements[0]
                # Check if element is visible
                if status_element.is_displayed():
                    status_message = status_element.text.strip()
                    if status_message:
                        # Determine log level based on message content
                        if any(keyword in status_message for keyword in ['失敗', '失敗しました', 'エラー', 'error', 'fail']):
                            log(f"❌ Login status message (FAILURE): {status_message}", 'error')
                        elif any(keyword in status_message for keyword in ['成功', 'success', '完了', 'complete']):
                            log(f"✅ Login status message (SUCCESS): {status_message}", 'success')
                        else:
                            log(f"📋 Login status message: {status_message}", 'info')
                        return status_message
                else:
                    # Element exists but is not visible
                    status_message = status_element.text.strip()
                    if status_message:
                        log(f"📋 Login status message (hidden): {status_message}", 'info')
                        return status_message
        except Exception as e:
            # Element not found or error accessing it - this is normal if login was successful
            pass
        
        # Secondary check: If we're still on login page, try to find any error messages in common locations
        if "login.html" in driver.current_url or "login-mfa.html" in driver.current_url:
            try:
                # Check for error messages in various possible locations
                error_selectors = [
                    '//*[@id="main"]//p[contains(@class, "error")]',
                    '//*[@id="main"]//div[contains(@class, "error")]',
                    '//*[@id="main"]//span[contains(@class, "error")]',
                    '//*[@id="main"]//*[contains(text(), "認証に失敗")]',
                    '//*[@id="main"]//*[contains(text(), "失敗")]',
                ]
                for selector in error_selectors:
                    try:
                        error_elements = driver.find_elements(By.XPATH, selector)
                        for elem in error_elements:
                            if elem.is_displayed():
                                error_text = elem.text.strip()
                                if error_text:
                                    log(f"⚠️ Error message found on page: {error_text}", 'warning')
                                    return error_text
                    except:
                        continue
            except:
                pass
        
        return None
    except Exception as e:
        # Don't fail the login process if status check fails
        log(f"⚠️ Could not check login status message: {e}", 'warning')
        return None

def solve_recaptcha(site_key, url, max_retries=5):
    log(f"🔐 Starting CAPTCHA solving process... (Site key: {site_key[:20]}...)", 'info')
    for attempt in range(1, max_retries + 1):
        try:
            check_stop()  # Check if stopped before starting attempt
            log(f"🔄 Solving CAPTCHA... (Attempt {attempt}/{max_retries})", 'info')
            submit_url = f"http://2captcha.com/in.php?key={CAPTCHA_API_KEY}&method=userrecaptcha&googlekey={site_key}&pageurl={url}&invisible=1"
            response = requests.get(submit_url)
            
            if "OK|" not in response.text:
                error_msg = response.text
                log(f"❌ 2Captcha submit error: {error_msg}", 'error')
                if attempt < max_retries:
                    log(f"⏳ Retrying in 3 seconds...", 'warning')
                    for _ in range(3):
                        check_stop()  # Check stop during wait
                        time.sleep(1)
                    continue
                else:
                    raise Exception(f"2captcha error: {error_msg}")
            
            captcha_id = response.text.split("|")[1]
            log(f"📝 CAPTCHA submitted successfully. ID: {captcha_id}", 'info')
            
            result_url = f"http://2captcha.com/res.php?key={CAPTCHA_API_KEY}&action=get&id={captcha_id}"
            
            for i in range(30):
                check_stop()  # Check stop before each wait
                time.sleep(5)
                check_stop()  # Check stop after wait
                result = requests.get(result_url)
                
                if "CAPCHA_NOT_READY" in result.text:
                    log(f"⏳ Waiting for CAPTCHA solution... ({i+1}/30)", 'info')
                    continue
                elif "OK|" in result.text:
                    solution = result.text.split("|")[1]
                    log(f"✅ CAPTCHA solved successfully! (Solution length: {len(solution)} chars)", 'success')
                    return solution
                elif "ERROR_CAPTCHA_UNSOLVABLE" in result.text:
                    log(f"⚠️ CAPTCHA unsolvable, retrying... (Attempt {attempt}/{max_retries})", 'warning')
                    if attempt < max_retries:
                        for _ in range(3):
                            check_stop()
                            time.sleep(1)
                        break  # Break inner loop to retry from start
                    else:
                        raise Exception(f"2captcha error: {result.text}")
                else:
                    error_msg = result.text
                    log(f"❌ 2Captcha result error: {error_msg}", 'error')
                    if attempt < max_retries:
                        for _ in range(3):
                            check_stop()
                            time.sleep(1)
                        break  # Break inner loop to retry from start
                    else:
                        raise Exception(f"2captcha error: {error_msg}")
            else:
                # If we exhausted the 30 attempts without success, retry
                if attempt < max_retries:
                    log(f"⏱️ CAPTCHA timeout, retrying... (Attempt {attempt}/{max_retries})", 'warning')
                    for _ in range(3):
                        check_stop()
                        time.sleep(1)
                    continue
                else:
                    raise Exception("CAPTCHA timeout after all retries")
        except StopIteration:
            log("⏹️ CAPTCHA solving stopped by user", 'warning')
            raise
        except Exception as e:
            if attempt < max_retries and "2captcha error" in str(e):
                log(f"⚠️ Error occurred: {e}, retrying... (Attempt {attempt}/{max_retries})", 'warning')
                for _ in range(3):
                    check_stop()
                    time.sleep(1)
                continue
            else:
                raise
    
    raise Exception("CAPTCHA solving failed after all retries")

def get_otp_from_gmail():
    log("📧 Checking Gmail for OTP email...", 'info')
    check_stop()  # Check stop before starting
    service = get_service()
    
    # Use the current EMAIL variable instead of hardcoded email
    target_email = EMAIL.lower() if EMAIL else None
    if not target_email:
        raise ValueError("EMAIL is not set. Cannot retrieve OTP.")
    
    log(f"🔍 Looking for OTP emails sent to: {target_email}", 'info')
    
    for attempt in range(12):
        try:
            check_stop()  # Check stop before each attempt
            messages = list_messages(service, max_results=5, query='ポケモンセンターオンライン ログイン用パスコード')
            
            log(f"📬 Attempt {attempt+1}/12: Found {len(messages) if messages else 0} message(s) matching query", 'info')
            
            if messages:
                for msg in messages:
                    try:
                        msg_id = msg['id']
                        subject, snippet, sender, to, date, categories, body = get_message(service, msg_id)
                        
                        log(f"  📨 Checking email: Subject='{subject[:50]}...', To='{to}', Date='{date}'", 'info')
                        
                        # Check if email is sent to the current user's email
                        # Handle multiple recipients (to field can be a comma-separated list)
                        to_emails = [email.strip().lower() for email in to.split(',')] if to else []
                        
                        if target_email in to_emails or any(target_email in email for email in to_emails):
                            log(f"  ✅ Email recipient matches: {target_email}", 'success')
                            log(f"  📄 Body length: {len(body)} characters", 'info')
                            log(f"  👁️ Body preview: {body[:200]}...", 'info')
                            
                            # Try multiple regex patterns to find OTP
                            patterns = [
                                r'【パスコード】(\d{6})',  # Original pattern
                                r'パスコード[：:]\s*(\d{6})',  # Alternative format
                                r'認証コード[：:]\s*(\d{6})',  # Alternative format
                                r'コード[：:]\s*(\d{6})',  # Generic code
                                r'(\d{6})',  # Any 6-digit number (fallback)
                            ]
                            
                            for pattern in patterns:
                                match = re.search(pattern, body)
                                if match:
                                    otp = match.group(1)
                                    log(f"  ✅ OTP found with pattern '{pattern}': {otp}", 'success')
                                    return otp
                            
                            log(f"  ❌ No OTP pattern matched in email body", 'error')
                        else:
                            log(f"  ⚠️ Email recipient doesn't match. Expected: {target_email}, Got: {to}", 'warning')
                    except Exception as e:
                        log(f"  ❌ Error processing message {msg_id}: {e}", 'error')
                        import traceback
                        traceback.print_exc()
                        continue
            else:
                log(f"  📭 No messages found with query 'ポケモンセンターオンライン ログイン用パスコード'", 'info')
                # Try a broader search
                if attempt == 2:  # After 3 attempts, try broader search
                    log("  🔍 Trying broader search (searching for 'パスコード' or 'passcode')...", 'info')
                    broader_messages = list_messages(service, max_results=10, query='パスコード OR passcode')
                    log(f"  📬 Broader search found {len(broader_messages) if broader_messages else 0} message(s)", 'info')
        
        except StopIteration:
            log("⏹️ OTP retrieval stopped by user", 'warning')
            raise
        except Exception as e:
            log(f"  ❌ Error during Gmail search: {e}", 'error')
            import traceback
            traceback.print_exc()
        
        log(f"⏳ Waiting for OTP email... ({attempt+1}/12)", 'info')
        # Check stop during wait (split 5 seconds into 5 checks)
        for _ in range(5):
            check_stop()
            time.sleep(1)
    
    raise Exception("OTP not received after 12 attempts (60 seconds). Check if email was sent and verify email address matches.")
def lottery_begin(driver, wait=None):
    if wait is None:
        wait = WebDriverWait(driver, 30)
    try:
        check_stop()  # Check stop before starting
        log(f"🌐 Opening login page: {LOGIN_URL}", 'info')
        driver.get(LOGIN_URL)
        log("⏳ Waiting for page to load...", 'info')
        # Check stop during page load wait
        for _ in range(10):
            check_stop()
            time.sleep(1)
        
        check_stop()  # Check stop before entering credentials
        log(f"📧 Entering email: {EMAIL}", 'info')
        email_field = wait.until(EC.presence_of_element_located((By.ID, "email")))
        email_field.send_keys(EMAIL)
        log("✅ Email entered successfully", 'success')
        check_stop()
        time.sleep(1)
        
        check_stop()
        log("🔒 Entering password...", 'info')
        if PASSWORD is None:
            raise ValueError("PASSWORD is not set. Please set it in .env file or include it in column B of the Excel file.")
        password_field = driver.find_element(By.ID, "password")
        password_field.send_keys(PASSWORD)
        log("✅ Password entered successfully", 'success')
        check_stop()
        time.sleep(1)
        
        check_stop()
        log("🖱️ Clicking login button...", 'info')
        login_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a.loginBtn")))
        driver.execute_script("arguments[0].click();", login_btn)
        log("⏳ Waiting for login response...", 'info')
        # Check stop during login wait
        for _ in range(8):
            check_stop()
            time.sleep(1)
        
        current_url = driver.current_url
        log(f"📍 Current URL after login attempt: {current_url}", 'info')
        
        # Check and display login status message immediately after login attempt
        log("🔍 Checking login status message from page...", 'info')
        status_message = check_login_status_message(driver, wait)
        if not status_message:
            log("ℹ️ No login status message found (this may indicate successful redirect)", 'info')
        
        check_stop()  # Check stop before CAPTCHA
        if "login.html" in current_url and "認証に失敗" in driver.page_source:
            log("⚠️ Login failed - CAPTCHA required. Starting CAPTCHA solving...", 'warning')
            
            match = re.search(r'6Le[a-zA-Z0-9_-]+', driver.page_source)
            if match:
                site_key = match.group(0)
                log(f"🔑 Found reCAPTCHA site key: {site_key[:30]}...", 'info')
                
                try:
                    captcha_solution = solve_recaptcha(site_key, driver.current_url)
                except StopIteration:
                    log("⏹️ Login process stopped during CAPTCHA solving", 'warning')
                    raise
                
                log("💉 Injecting CAPTCHA solution into page...", 'info')
                driver.execute_script(f'''
                    var callback = function(token) {{
                        var textareas = document.getElementsByName("g-recaptcha-response");
                        for (var i = 0; i < textareas.length; i++) {{
                            textareas[i].value = token;
                        }}
                    }};
                    callback("{captcha_solution}");
                    
                    if (typeof ___grecaptcha_cfg !== 'undefined') {{
                        Object.keys(___grecaptcha_cfg.clients).forEach(function(key) {{
                            var client = ___grecaptcha_cfg.clients[key];
                            if (client && client.callback) {{
                                client.callback("{captcha_solution}");
                            }}
                        }});
                    }}
                ''')
                log("✅ CAPTCHA solution injected", 'success')
                time.sleep(2)
                
                log("🔄 Re-entering credentials after CAPTCHA...", 'info')
                email_field = driver.find_element(By.ID, "email")
                email_field.clear()
                email_field.send_keys(EMAIL)
                log("✅ Email re-entered", 'success')
                
                password_field = driver.find_element(By.ID, "password")
                password_field.clear()
                password_field.send_keys(PASSWORD)
                log("✅ Password re-entered", 'success')
                time.sleep(1)
                
                log("🖱️ Clicking login button again...", 'info')
                login_btn = driver.find_element(By.CSS_SELECTOR, "a.loginBtn")
                driver.execute_script("arguments[0].click();", login_btn)
                log("⏳ Waiting for login response after CAPTCHA...", 'info')
                # Check stop during login wait
                for _ in range(8):
                    check_stop()
                    time.sleep(1)
                
                # Check login status message after CAPTCHA retry
                log("🔍 Checking login status message after CAPTCHA submission...", 'info')
                status_message = check_login_status_message(driver, wait)
                if status_message:
                    log(f"📋 Login status message after CAPTCHA: {status_message}", 'info')
                else:
                    log("ℹ️ No login status message found after CAPTCHA", 'info')
        
        check_stop()  # Check stop before OTP
        if "login-mfa" in driver.current_url or "パスコード" in driver.page_source:
            log("🔐 OTP (One-Time Password) required for login", 'info')
            
            log("⏳ Waiting for OTP email to be sent (5 seconds)...", 'info')
            # Check stop during OTP wait
            for _ in range(5):
                check_stop()
                time.sleep(1)
            
            try:
                otp = get_otp_from_gmail()
                log(f"✅ OTP retrieved from Gmail: {otp}", 'success')
            except StopIteration:
                log("⏹️ Login process stopped during OTP retrieval", 'warning')
                raise
            
            check_stop()
            log("⌨️ Entering OTP into form...", 'info')
            otp_field = wait.until(EC.presence_of_element_located((By.ID, "authCode")))
            otp_field.clear()
            otp_field.send_keys(otp)
            log("✅ OTP entered successfully", 'success')
            check_stop()
            time.sleep(1)
            
            check_stop()
            log("🖱️ Submitting OTP...", 'info')
            submit_btn = wait.until(EC.element_to_be_clickable((By.ID, "certify")))
            driver.execute_script("arguments[0].click();", submit_btn)
            log("⏳ OTP submitted, waiting for authentication response...", 'info')
            # Check stop during OTP response wait
            for _ in range(10):
                check_stop()
                time.sleep(1)
            
            log(f"📍 Current URL after OTP submission: {driver.current_url}", 'info')
            
            # Check login status message after OTP submission
            log("🔍 Checking login status message after OTP submission...", 'info')
            status_message = check_login_status_message(driver, wait)
            if status_message:
                log(f"📋 Login status message after OTP: {status_message}", 'info')
            else:
                log("ℹ️ No login status message found after OTP", 'info')
            
            if "login-mfa" in driver.current_url and "認証に失敗" in driver.page_source:
                log("⚠️ OTP authentication failed - retrieving fresh OTP and retrying...", 'warning')
                for _ in range(3):
                    check_stop()
                    time.sleep(1)
                
                try:
                    otp = get_otp_from_gmail()
                    log(f"✅ Fresh OTP retrieved: {otp}", 'success')
                except StopIteration:
                    log("⏹️ Login process stopped during OTP retry", 'warning')
                    raise
                
                check_stop()
                log(f"⌨️ Entering fresh OTP: {otp}", 'info')
                otp_field = driver.find_element(By.ID, "authCode")
                otp_field.clear()
                otp_field.send_keys(otp)
                log("✅ Fresh OTP entered", 'success')
                check_stop()
                time.sleep(1)
                
                check_stop()
                log("🖱️ Submitting fresh OTP...", 'info')
                submit_btn = driver.find_element(By.ID, "certify")
                driver.execute_script("arguments[0].click();", submit_btn)
                log("⏳ Waiting for authentication response after retry...", 'info')
                # Check stop during retry wait
                for _ in range(10):
                    check_stop()
                    time.sleep(1)
                
                    log(f"📍 Current URL after OTP retry: {driver.current_url}", 'info')
                    
                    # Check login status message after OTP retry
                    log("🔍 Checking login status message after OTP retry...", 'info')
                    status_message = check_login_status_message(driver, wait)
                    if status_message:
                        log(f"📋 Login status message after OTP retry: {status_message}", 'info')
                    else:
                        log("ℹ️ No login status message found after OTP retry", 'info')
        
        log(f"📍 Final URL after login process: {driver.current_url}", 'info')
        
        # Final login status check
        log("🔍 Performing final login status message check...", 'info')
        status_message = check_login_status_message(driver, wait)
        if status_message:
            log(f"📋 Final login status message: {status_message}", 'info')
        else:
            log("ℹ️ No login status message found in final check", 'info')
        
        # Navigate to apply page if not already there
        if "apply.html" not in driver.current_url:
            log(f"🌐 Navigating to application page: {APPLY_URL}", 'info')
            driver.get(APPLY_URL)
            for _ in range(5):
                check_stop()
                time.sleep(1)
        else:
            log("✅ Already on application page", 'success')
        
        pop04_reloaded = False  # Flag to track if page was reloaded due to exception
        try:
            pop04_element = driver.find_element(By.ID, "pop04")
            if pop04_element.is_displayed():
                log("🔔 Popup (pop04) detected, checking content...", 'info')
                
                # Check if pop04 contains "意図しない例外が発生しました。" message
                try:
                    pop04_message_xpath = '//*[@id="pop04"]/div/div[1]/p'
                    pop04_message_element = driver.find_element(By.XPATH, pop04_message_xpath)
                    pop04_message_text = pop04_message_element.text.strip()
                    log(f"📋 Pop04 message: {pop04_message_text}", 'info')
                    
                    if "意図しない例外が発生しました。" in pop04_message_text:
                        log("⚠️ Exception message detected in pop04: '意図しない例外が発生しました。' - Reloading page (F5)...", 'warning')
                        
                        # Reload the page when exception message is detected
                        check_stop()
                        try:
                            # Method 1: Use F5 key (most reliable)
                            log("🔄 Pressing F5 to reload page...", 'info')
                            driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.F5)
                            check_stop()
                            time.sleep(3)  # Wait for page to reload
                            log("✅ Page reloaded via F5 key", 'success')
                            pop04_reloaded = True
                        except Exception as e:
                            log(f"⚠️ Could not reload via F5: {e}. Trying refresh() method...", 'warning')
                            try:
                                # Method 2: Use driver.refresh() as fallback
                                driver.refresh()
                                check_stop()
                                time.sleep(3)  # Wait for page to reload
                                log("✅ Page reloaded via refresh()", 'success')
                                pop04_reloaded = True
                            except Exception as e2:
                                log(f"⚠️ Could not reload via refresh(): {e2}. Trying get() method...", 'warning')
                                try:
                                    # Method 3: Use driver.get() as last resort
                                    current_url = driver.current_url
                                    driver.get(current_url)
                                    check_stop()
                                    time.sleep(3)  # Wait for page to reload
                                    log("✅ Page reloaded via get()", 'success')
                                    pop04_reloaded = True
                                except Exception as e3:
                                    log(f"❌ Failed to reload page: {e3}. Proceeding anyway...", 'error')
                                    time.sleep(2)
                        
                        # After reload, break out of pop04 check and proceed directly to lottery entry
                        if pop04_reloaded:
                            check_stop()
                            log("🔍 Page reloaded. Waiting for page to stabilize...", 'info')
                            time.sleep(3)  # Additional wait for page to fully load after reload
                            log("🎰 Proceeding directly to lottery entry process after reload...", 'info')
                            # Break out of pop04 handling and proceed to lottery entry
                            pass  # Will continue to lottery entry below
                        else:
                            # If reload failed, try to close pop04 normally
                            try:
                                pop04_link_xpath = '//*[@id="pop04"]/div/div[1]/ul/li/a'
                                pop04_link = wait.until(EC.element_to_be_clickable((By.XPATH, pop04_link_xpath)))
                                driver.execute_script("arguments[0].click();", pop04_link)
                                log("✅ Pop04 modal closed after reload attempt", 'success')
                                time.sleep(1)
                            except:
                                pass
                    else:
                        # Normal pop04 handling (not exception case)
                        log("ℹ️ Pop04 detected but no exception message. Handling normally...", 'info')
                        try:
                            pop04_link_xpath = '//*[@id="pop04"]/div/div[1]/ul/li/a'
                            pop04_link = wait.until(EC.element_to_be_clickable((By.XPATH, pop04_link_xpath)))
                            driver.execute_script("arguments[0].click();", pop04_link)
                            log("✅ Popup link clicked", 'success')
                            time.sleep(1)
                        except Exception as e:
                            log(f"⚠️ Could not click pop04 link: {e}", 'warning')
                except Exception as e:
                    log(f"⚠️ Could not read pop04 message: {e}. Trying to close pop04...", 'warning')
                    try:
                        pop04_link_xpath = '//*[@id="pop04"]/div/div[1]/ul/li/a'
                        pop04_link = wait.until(EC.element_to_be_clickable((By.XPATH, pop04_link_xpath)))
                        driver.execute_script("arguments[0].click();", pop04_link)
                        log("✅ Popup link clicked (fallback)", 'success')
                        time.sleep(1)
                    except:
                        pass
        except Exception as e:
            log(f"ℹ️ Pop04 not present or error checking: {e}. Continuing normally...", 'info')
            pass  # pop04 not present, continue normally
        
        # If page was reloaded due to exception, check if pop04 appears again (should be cleared after reload)
        if pop04_reloaded:
            check_stop()
            log("🔍 Checking if pop04 appears again after reload...", 'info')
            time.sleep(2)  # Wait a bit for any popups to appear
            try:
                pop04_check = driver.find_elements(By.ID, "pop04")
                if pop04_check and pop04_check[0].is_displayed():
                    log("⚠️ Pop04 still present after reload. Attempting to close...", 'warning')
                    try:
                        pop04_link_xpath = '//*[@id="pop04"]/div/div[1]/ul/li/a'
                        pop04_link = wait.until(EC.element_to_be_clickable((By.XPATH, pop04_link_xpath)))
                        driver.execute_script("arguments[0].click();", pop04_link)
                        log("✅ Pop04 closed after reload", 'success')
                        time.sleep(1)
                    except:
                        log("⚠️ Could not close pop04 after reload. Proceeding anyway...", 'warning')
                else:
                    log("✅ No pop04 detected after reload. Proceeding with lottery entry...", 'success')
            except:
                log("✅ No pop04 detected after reload. Proceeding with lottery entry...", 'success')
            
            # After reload, check lottery status with retry mechanism (max 3 attempts including initial check)
            check_stop()
            log("🔍 Checking lottery status after reload with retry mechanism (max 3 attempts)...", 'info')
            status_valid = False
            max_reload_attempts = 3
            
            for check_attempt in range(1, max_reload_attempts + 1):
                check_stop()
                log(f"📊 Checking lottery status (attempt {check_attempt}/{max_reload_attempts})...", 'info')
                time.sleep(2)  # Wait for page to stabilize before checking
                
                try:
                    status_xpath = '//*[@id="main"]/div[1]/ul/li[1]/div[2]/div/span[1]'
                    status_elements = driver.find_elements(By.XPATH, status_xpath)
                    
                    if status_elements and len(status_elements) > 0:
                        status_element = status_elements[0]
                        if status_element.is_displayed():
                            status_text = status_element.text.strip()
                            log(f"📋 Lottery status found: '{status_text}'", 'info')
                            
                            if status_text in ["受付完了", "受付中"]:
                                log(f"✅ Valid lottery status found: '{status_text}'. Proceeding with lottery entry...", 'success')
                                status_valid = True
                                break
                            else:
                                log(f"⚠️ Lottery status is '{status_text}', expected '受付完了' or '受付中'...", 'warning')
                        else:
                            log(f"⚠️ Lottery status element exists but is not visible...", 'warning')
                    else:
                        log(f"⚠️ Lottery status element not found...", 'warning')
                except Exception as e:
                    log(f"⚠️ Error checking lottery status: {e}. Error details: {str(e)[:100]}...", 'warning')
                
                # If status is not valid and we haven't reached max attempts, reload page
                if not status_valid and check_attempt < max_reload_attempts:
                    check_stop()
                    log(f"🔄 Reloading page (F5) - attempt {check_attempt + 1}/{max_reload_attempts}...", 'info')
                    try:
                        driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.F5)
                        check_stop()
                        time.sleep(3)  # Wait for page to reload
                        log(f"✅ Page reloaded via F5 (attempt {check_attempt + 1})", 'success')
                        # Close pop04 if it appears after reload
                        try:
                            pop04_after_reload = driver.find_elements(By.ID, "pop04")
                            if pop04_after_reload and pop04_after_reload[0].is_displayed():
                                log("🔔 Pop04 detected after reload, closing...", 'info')
                                pop04_link_xpath = '//*[@id="pop04"]/div/div[1]/ul/li/a'
                                pop04_link = wait.until(EC.element_to_be_clickable((By.XPATH, pop04_link_xpath)))
                                driver.execute_script("arguments[0].click();", pop04_link)
                                time.sleep(1)
                        except:
                            pass
                    except Exception as e:
                        log(f"⚠️ Could not reload via F5: {e}. Trying refresh()...", 'warning')
                        try:
                            driver.refresh()
                            check_stop()
                            time.sleep(3)
                            log(f"✅ Page reloaded via refresh() (attempt {check_attempt + 1})", 'success')
                        except Exception as e2:
                            log(f"⚠️ Could not reload via refresh(): {e2}. Trying get()...", 'warning')
                            try:
                                current_url = driver.current_url
                                driver.get(current_url)
                                check_stop()
                                time.sleep(3)
                                log(f"✅ Page reloaded via get() (attempt {check_attempt + 1})", 'success')
                            except Exception as e3:
                                log(f"❌ All reload methods failed: {e3}", 'error')
            
            # If status is still not valid after all attempts, restart from login
            if not status_valid:
                log(f"❌ Could not find valid lottery status ('受付完了' or '受付中') after {max_reload_attempts} attempts.", 'error')
                log(f"🔄 Restarting from login process...", 'info')
                # Restart from login by calling lottery_begin recursively
                lottery_begin(driver, wait)
                return
            
            # If status is valid after reload, proceed directly to lottery processing
            log("✅ Status validated after reload. Proceeding directly to lottery entry...", 'success')
            check_stop()
            time.sleep(1)  # Brief wait before proceeding
            
            # Final check: verify status again and determine which lottery to process
            status_xpath = '//*[@id="main"]/div[1]/ul/li[1]/div[2]/div/span[1]'
            try:
                status_element = wait.until(EC.presence_of_element_located((By.XPATH, status_xpath)))
                status_text = status_element.text.strip()
                log(f"📊 Final status check after reload: {status_text}", 'info')
                
                if status_text == "受付終了":
                    log("⚠️ First lottery is already closed (受付終了). Moving to second lottery...", 'warning')
                    _process_lottery_entry(driver, wait, lottery_number=2)
                    return
                elif status_text in ["受付完了", "受付中"]:
                    log(f"✅ Confirmed valid status: '{status_text}'. Proceeding with first lottery...", 'success')
                    _process_lottery_entry(driver, wait, lottery_number=1)
                    log("🎉 Lottery entry process completed!", 'success')
                    return
                else:
                    log(f"⚠️ Unexpected status '{status_text}' after reload validation. Restarting from login...", 'error')
                    lottery_begin(driver, wait)
                    return
            except Exception as e:
                log(f"⚠️ Could not verify final status after reload: {e}. Restarting from login...", 'error')
                lottery_begin(driver, wait)
                return
        
        # Normal flow (no reload): Check status of first lottery
        log("🎰 Starting lottery entry process...", 'info')
        check_stop()
        
        status_xpath = '//*[@id="main"]/div[1]/ul/li[1]/div[2]/div/span[1]'
        try:
            status_element = wait.until(EC.presence_of_element_located((By.XPATH, status_xpath)))
            status_text = status_element.text.strip()
            log(f"📊 First lottery status: {status_text}", 'info')
            
            # Handle different status values
            if status_text == "受付終了":
                log("⚠️ First lottery is already closed (受付終了). Moving to second lottery...", 'warning')
                # Process second lottery (li[2])
                _process_lottery_entry(driver, wait, lottery_number=2)
                return
            
            # Check if status is valid (受付完了 or 受付中)
            if status_text in ["受付完了", "受付中"]:
                log(f"✅ Valid lottery status: '{status_text}'. Proceeding with lottery entry...", 'success')
            else:
                log(f"⚠️ Lottery status is '{status_text}', expected '受付完了' or '受付中'. This may cause issues...", 'warning')
                # For normal flow, we'll still try to proceed but log warning
        except Exception as e:
            log(f"⚠️ Could not check lottery status: {e}. Proceeding with caution...", 'warning')
        
        # Process first lottery (li[1])
        _process_lottery_entry(driver, wait, lottery_number=1)
        
        log("🎉 Lottery entry process completed!", 'success')

    except StopIteration:
        log("⏹️ Login process stopped by user", 'warning')
        raise
    except Exception as e:
        log(f"❌ Fatal error in login process: {e}", 'error')
        import traceback
        traceback.print_exc()
        raise

def _process_lottery_entry(driver, wait, lottery_number=1):
    """Process lottery entry for a specific lottery number"""
    try:
        check_stop()
        log(f"🎰 Processing lottery #{lottery_number}...", 'info')
        
        # Step 2: Click on dt element to expand details
        check_stop()
        log(f"🖱️ Clicking lottery #{lottery_number} details (dt)...", 'info')
        dt_xpath = f'//*[@id="main"]/div[1]/ul/li[{lottery_number}]/div[2]/dl/dt'
        dt_element = wait.until(EC.element_to_be_clickable((By.XPATH, dt_xpath)))
        driver.execute_script("arguments[0].click();", dt_element)
        check_stop()
        time.sleep(1)
        
        # Step 3: Click radio button - try multiple strategies to ensure it works
        check_stop()
        log(f"☑️ Selecting radio button for lottery #{lottery_number}...", 'info')
        
        radio_clicked = False
        
        # Strategy 1: Find and click p.radio element (most reliable - clicking p will trigger label/input)
        try:
            check_stop()
            log(f"  🔍 Strategy 1: Looking for p.radio element...", 'info')
            p_radio_xpath = f'//*[@id="main"]/div[1]/ul/li[{lottery_number}]/div[2]/dl/dd/div[3]/form/ul[1]/li/p[@class="radio"]'
            p_radio_element = wait.until(EC.presence_of_element_located((By.XPATH, p_radio_xpath)))
            
            if p_radio_element.is_displayed():
                # Find the input inside p.radio
                input_elem = p_radio_element.find_element(By.TAG_NAME, 'input')
                # Set checked and trigger events
                driver.execute_script("""
                    arguments[0].checked = true;
                    arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
                    arguments[0].dispatchEvent(new Event('click', { bubbles: true }));
                """, input_elem)
                # Also click the label to ensure it's properly selected
                try:
                    label_elem = p_radio_element.find_element(By.TAG_NAME, 'label')
                    driver.execute_script("arguments[0].click();", label_elem)
                except:
                    pass
                
                # Verify it's checked
                is_checked = driver.execute_script("return arguments[0].checked;", input_elem)
                if is_checked:
                    log(f"✅ Radio button selected successfully via p.radio element for lottery #{lottery_number}", 'success')
                    radio_clicked = True
        except Exception as e:
            log(f"  ⚠️ Strategy 1 failed: {str(e)[:80]}...", 'warning')
        
        # Strategy 2: Find and click label element (label click automatically selects input)
        if not radio_clicked:
            try:
                check_stop()
                log(f"  🔍 Strategy 2: Looking for label element...", 'info')
                label_xpath = f'//*[@id="main"]/div[1]/ul/li[{lottery_number}]/div[2]/dl/dd/div[3]/form/ul[1]/li/p[@class="radio"]/label'
                label_element = wait.until(EC.element_to_be_clickable((By.XPATH, label_xpath)))
                
                driver.execute_script("arguments[0].click();", label_element)
                
                # Verify input is checked
                input_elem = label_element.find_element(By.TAG_NAME, 'input')
                is_checked = driver.execute_script("return arguments[0].checked;", input_elem)
                if is_checked:
                    log(f"✅ Radio button selected successfully via label element for lottery #{lottery_number}", 'success')
                    radio_clicked = True
            except Exception as e:
                log(f"  ⚠️ Strategy 2 failed: {str(e)[:80]}...", 'warning')
        
        # Strategy 3: Find and click input[type="radio"] directly
        if not radio_clicked:
            try:
                check_stop()
                log(f"  🔍 Strategy 3: Looking for input[type=\"radio\"] element...", 'info')
                input_xpath = f'//*[@id="main"]/div[1]/ul/li[{lottery_number}]/div[2]/dl/dd/div[3]/form/ul[1]/li/p[@class="radio"]/label/input[@type="radio"]'
                input_element = wait.until(EC.presence_of_element_located((By.XPATH, input_xpath)))
                
                # Set checked property and trigger events
                driver.execute_script("""
                    arguments[0].checked = true;
                    arguments[0].click();
                    arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
                """, input_element)
                
                # Verify it's checked
                is_checked = driver.execute_script("return arguments[0].checked;", input_element)
                if is_checked:
                    log(f"✅ Radio button selected successfully via input element for lottery #{lottery_number}", 'success')
                    radio_clicked = True
            except Exception as e:
                log(f"  ⚠️ Strategy 3 failed: {str(e)[:80]}...", 'warning')
        
        # Strategy 4: Fallback - try span element
        if not radio_clicked:
            try:
                check_stop()
                log(f"  🔍 Strategy 4: Looking for span element (fallback)...", 'info')
                span_xpath = f'//*[@id="main"]/div[1]/ul/li[{lottery_number}]/div[2]/dl/dd/div[3]/form/ul[1]/li/p[@class="radio"]/label/span'
                span_element = wait.until(EC.element_to_be_clickable((By.XPATH, span_xpath)))
                
                driver.execute_script("arguments[0].click();", span_element)
                
                # Find and verify input is checked
                p_parent = span_element.find_element(By.XPATH, './ancestor::p[@class="radio"]')
                input_elem = p_parent.find_element(By.TAG_NAME, 'input')
                is_checked = driver.execute_script("return arguments[0].checked;", input_elem)
                if is_checked:
                    log(f"✅ Radio button selected successfully via span element for lottery #{lottery_number}", 'success')
                    radio_clicked = True
            except Exception as e:
                log(f"  ⚠️ Strategy 4 failed: {str(e)[:80]}...", 'warning')
        
        # Strategy 5: Last resort - find first radio input in form
        if not radio_clicked:
            try:
                check_stop()
                log(f"  🔍 Strategy 5: Looking for first radio input in form (last resort)...", 'info')
                form_xpath = f'//*[@id="main"]/div[1]/ul/li[{lottery_number}]/div[2]/dl/dd/div[3]/form'
                form_element = driver.find_element(By.XPATH, form_xpath)
                input_element = form_element.find_element(By.XPATH, './/input[@type="radio"]')
                
                driver.execute_script("""
                    arguments[0].checked = true;
                    arguments[0].click();
                    arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
                """, input_element)
                
                is_checked = driver.execute_script("return arguments[0].checked;", input_element)
                if is_checked:
                    log(f"✅ Radio button selected successfully via fallback method for lottery #{lottery_number}", 'success')
                    radio_clicked = True
            except Exception as e:
                log(f"  ⚠️ Strategy 5 failed: {str(e)[:80]}...", 'warning')
        
        if not radio_clicked:
            log(f"❌ Could not select radio button using any strategy for lottery #{lottery_number}", 'error')
            raise Exception(f"Failed to select radio button for lottery #{lottery_number} after trying all strategies")
        
        check_stop()
        time.sleep(1)
        
        # Step 4: Check checkbox
        check_stop()
        log(f"✅ Checking checkbox for lottery #{lottery_number}...", 'info')
        checkbox_xpath = f'//*[@id="main"]/div[1]/ul/li[{lottery_number}]/div[2]/dl/dd/div[3]/form/div/div'
        checkbox_element = wait.until(EC.element_to_be_clickable((By.XPATH, checkbox_xpath)))
        driver.execute_script("arguments[0].click();", checkbox_element)
        log(f"✅ Checkbox checked for lottery #{lottery_number}", 'success')
        check_stop()
        time.sleep(1)
        
        # Step 5: Click submit button to open modal
        check_stop()
        log(f"🔔 Clicking submit button for lottery #{lottery_number} to open modal...", 'info')
        submit_xpath = f'//*[@id="main"]/div[1]/ul/li[{lottery_number}]/div[2]/dl/dd/div[3]/form/ul[2]/li/a'
        submit_element = wait.until(EC.element_to_be_clickable((By.XPATH, submit_xpath)))
        driver.execute_script("arguments[0].click();", submit_element)
        check_stop()
        time.sleep(2)  # Wait for modal to appear
        
        # Step 6: Wait for modal to appear and click apply button
        check_stop()
        log(f"🎯 Waiting for modal (pop01) to appear for lottery #{lottery_number}...", 'info')
        modal_xpath = '//*[@id="pop01"]/div/div[1]'
        try:
            modal_element = wait.until(EC.presence_of_element_located((By.XPATH, modal_xpath)))
            log("✅ Modal appeared", 'success')
        except Exception as e:
            log(f"⚠️ Modal element not found with xpath {modal_xpath}: {e}. Trying to proceed anyway...", 'warning')
            # Try alternative: just wait for applyBtn
            pass
        
        check_stop()
        log(f"🎯 Clicking apply button (applyBtn) in modal for lottery #{lottery_number}...", 'info')
        apply_btn = wait.until(EC.element_to_be_clickable((By.ID, "applyBtn")))
        driver.execute_script("arguments[0].click();", apply_btn)
        log(f"✅ Application submitted successfully for lottery #{lottery_number}!", 'success')
        
        # Wait for confirmation
        for _ in range(3):
            check_stop()
            time.sleep(1)
        
        log(f"🎉 Lottery #{lottery_number} entry process completed!", 'success')
        
    except StopIteration:
        log(f"⏹️ Lottery #{lottery_number} entry process stopped by user", 'warning')
        raise
    except Exception as e:
        log(f"❌ Error processing lottery #{lottery_number}: {e}", 'error')
        import traceback
        traceback.print_exc()
        raise

# Load data from Excel file row by row
def load_data_from_excel():
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
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
        'source': 'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
    })
    wait = WebDriverWait(driver, 30)
    
    try:
        excel_file = "V0vMwOh.xlsx"
        workbook = load_workbook(excel_file)
        worksheet = workbook.active

        for row in worksheet.iter_rows(min_row=1, values_only=False):
            user_email = row[0].value  # Column A is the first column (index 0)
            user_password = row[1].value if len(row) > 1 else None  # Column B is the second column (index 1)
            if user_email:  
                global EMAIL, PASSWORD
                EMAIL = user_email  # Update module-level EMAIL variable
                # Update PASSWORD from Excel if available, otherwise use env variable
                if user_password:
                    PASSWORD = user_password
                elif PASSWORD is None:
                    raise ValueError("PASSWORD is not set. Please set it in .env file or include it in column B of the Excel file.")
                log(f"📧 Processing email: {user_email}", 'info')
                lottery_begin(driver, wait)
                # user_email variable is now assigned for this row

        workbook.close()
    except Exception as e:
        log(f"❌ Error: {e}", 'error')
        import traceback
        traceback.print_exc()
    finally:
        driver.quit()
        input("\nPress Enter to stop the project...")




if __name__ == "__main__":
    load_data_from_excel()
