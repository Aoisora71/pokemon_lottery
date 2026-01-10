import time
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
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
    """Log a message using the logger callback if available, otherwise use print()"""
    if _logger:
        _logger(message, level)
    else:
        print(message)

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
        
        if "apply.html" in driver.current_url:
            log("✅ Login successful! Redirected to application page", 'success')
            try:
                pop04_element = driver.find_element(By.ID, "pop04")
                if pop04_element.is_displayed():
                    log("🔔 Popup (pop04) detected, clicking link to continue...", 'info')
                    # Click the link in pop04
                    pop04_link_xpath = '//*[@id="pop04"]/div/div[1]/ul/li/a'
                    pop04_link = wait.until(EC.element_to_be_clickable((By.XPATH, pop04_link_xpath)))
                    driver.execute_script("arguments[0].click();", pop04_link)
                    log("✅ Popup link clicked", 'success')
                    time.sleep(1)
                    lottery_begin(driver, wait)
            except:
                pass  # pop04 not present, continue normally
                        
            log("🎰 Starting lottery item processing...", 'info')
            for i in range(1, 6):
                check_stop()  # Check stop before each item
                log(f"📦 Processing lottery item {i}/5...", 'info')
                try:
                    # Check if the acceptBox element exists
                    accept_box_xpath = f'//*[@id="main"]/div[1]/ul/li[{i}]/div[2]/div'
                    accept_box_elements = driver.find_elements(By.XPATH, accept_box_xpath)
                    
                    # If element doesn't exist, no more items to process
                    if not accept_box_elements:
                        log(f"📭 Item {i} does not exist. No more items to process.", 'info')
                        break
                    
                    accept_box = accept_box_elements[0]
                    accept_box_class = accept_box.get_attribute("class")
                    log(f"📋 Item {i} status class: {accept_box_class}", 'info')
                    # If class contains "finish", terminate the loop
                    if "acceptBox flexB finish" in accept_box_class:
                        log(f"✅ Item {i} is already finished. Skipping.", 'success')
                        break
                    if "acceptBox flexB afoot" in accept_box_class:
                        log(f"⏳ Item {i} is in progress (afoot). Skipping.", 'info')
                        continue
                    # If class contains "accepting", execute the clicks
                    if "acceptBox flexB accepting" in accept_box_class:
                        log(f"🎯 Item {i} is accepting applications. Processing...", 'info')
                        
                        # Click the dl tag with class="subDl"
                        check_stop()
                        log(f"  🖱️ Clicking item {i} details...", 'info')
                        sub_dl_xpath = f'//*[@id="main"]/div[1]/ul/li[{i}]/div[2]/dl/dt'
                        sub_dl = wait.until(EC.element_to_be_clickable((By.XPATH, sub_dl_xpath)))
                        driver.execute_script("arguments[0].click();", sub_dl)
                        check_stop()
                        time.sleep(1)
                        
                        # Click the span element
                        check_stop()
                        log(f"  ☑️ Selecting checkbox for item {i}...", 'info')
                        span_xpath = f'//*[@id="main"]/div[1]/ul/li[{i}]/div[2]/dl/dd/div[3]/form/ul[1]/li/p/label/span'
                        span = wait.until(EC.element_to_be_clickable((By.XPATH, span_xpath)))
                        driver.execute_script("arguments[0].click();", span)
                        check_stop()
                        time.sleep(1)
                        
                        # Click the input tag with class="-check"
                        check_stop()
                        log(f"  ✅ Confirming selection for item {i}...", 'info')
                        check_input_xpath = f'//*[@id="main"]/div[1]/ul/li[{i}]//input[@class="-check"]'
                        check_input = wait.until(EC.element_to_be_clickable((By.XPATH, check_input_xpath)))
                        driver.execute_script("arguments[0].click();", check_input)
                        check_stop()
                        time.sleep(1)
                        
                        # Click the a tag with class="popup-modal"
                        check_stop()
                        log(f"  🔔 Opening modal for item {i}...", 'info')
                        popup_modal_xpath = f'//*[@id="main"]/div[1]/ul/li[{i}]/div[2]/dl/dd/div[3]/form/ul[2]/li/a'
                        popup_modal = wait.until(EC.element_to_be_clickable((By.XPATH, popup_modal_xpath)))
                        driver.execute_script("arguments[0].click();", popup_modal)
                        check_stop()
                        time.sleep(1)
                        
                        # Check if pop04 exists and handle it
                        try:
                            pop04_element = driver.find_element(By.ID, "pop04")
                            if pop04_element.is_displayed():
                                log(f"  🔔 Popup (pop04) detected for item {i}, clicking link...", 'info')
                                # Click the link in pop04
                                pop04_link_xpath = '//*[@id="pop04"]/div/div[1]/ul/li/a'
                                pop04_link = wait.until(EC.element_to_be_clickable((By.XPATH, pop04_link_xpath)))
                                driver.execute_script("arguments[0].click();", pop04_link)
                                lottery_begin(driver, wait)
                                time.sleep(1)
                        except:
                            pass  # pop04 not present, continue normally
                        
                        # Click the a tag with id="applyBtn"
                        check_stop()
                        log(f"  🎯 Submitting application for item {i}...", 'info')
                        apply_btn = wait.until(EC.element_to_be_clickable((By.ID, "applyBtn")))
                        driver.execute_script("arguments[0].click();", apply_btn)
                        # Check stop during submission wait
                        for _ in range(2):
                            check_stop()
                            time.sleep(1)
                        
                        log(f"✅ Item {i} processed successfully!", 'success')
                        
                except StopIteration:
                    log(f"⏹️ Item processing stopped by user at item {i}", 'warning')
                    raise
                except Exception as e:
                    log(f"❌ Error processing item {i}: {e}", 'error')
                    import traceback
                    traceback.print_exc()
                    continue
  
        else:
            log("⚠️ Still on login page, re-running login process...", 'warning')
            
            # Re-run the login section
            check_stop()
            log(f"🔄 Re-opening login page: {LOGIN_URL}", 'info')
            driver.get(LOGIN_URL)
            # Check stop during page load
            for _ in range(10):
                check_stop()
                time.sleep(1)
            
            wait = WebDriverWait(driver, 30)
            
            check_stop()
            log(f"📧 Entering email (retry): {EMAIL}", 'info')
            email_field = wait.until(EC.presence_of_element_located((By.ID, "email")))
            email_field.send_keys(EMAIL)
            check_stop()
            time.sleep(1)
            
            check_stop()
            log("🔒 Entering password (retry)...", 'info')
            password_field = driver.find_element(By.ID, "password")
            password_field.send_keys(PASSWORD)
            check_stop()
            time.sleep(1)
            
            check_stop()
            log("🖱️ Clicking login button (retry)...", 'info')
            login_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a.loginBtn")))
            driver.execute_script("arguments[0].click();", login_btn)
            # Check stop during login wait
            for _ in range(8):
                check_stop()
                time.sleep(1)
            
            current_url = driver.current_url
            log(f"📍 Current URL after retry login attempt: {current_url}", 'info')
            
            # Check login status message after retry attempt
            log("🔍 Checking login status message after retry login attempt...", 'info')
            status_message = check_login_status_message(driver, wait)
            if status_message:
                log(f"📋 Login status message after retry: {status_message}", 'info')
            else:
                log("ℹ️ No login status message found after retry", 'info')
            
            if "login.html" in current_url and "認証に失敗" in driver.page_source:
                log("⚠️ Login failed again - solving CAPTCHA (retry)...", 'warning')
                
                match = re.search(r'6Le[a-zA-Z0-9_-]+', driver.page_source)
                if match:
                    site_key = match.group(0)
                    log(f"🔑 Found reCAPTCHA site key (retry): {site_key[:30]}...", 'info')
                    
                    try:
                        captcha_solution = solve_recaptcha(site_key, driver.current_url)
                    except StopIteration:
                        log("⏹️ Login process stopped during CAPTCHA solving (retry)", 'warning')
                        raise
                    
                    check_stop()
                    log("💉 Injecting CAPTCHA solution into page (retry)...", 'info')
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
                    for _ in range(2):
                        check_stop()
                        time.sleep(1)
                    
                    check_stop()
                    log("🔄 Re-entering credentials after CAPTCHA (retry)...", 'info')
                    email_field = driver.find_element(By.ID, "email")
                    email_field.clear()
                    email_field.send_keys(EMAIL)
                    
                    password_field = driver.find_element(By.ID, "password")
                    password_field.clear()
                    password_field.send_keys(PASSWORD)
                    check_stop()
                    time.sleep(1)
                    
                    check_stop()
                    log("🖱️ Clicking login button again (retry)...", 'info')
                    login_btn = driver.find_element(By.CSS_SELECTOR, "a.loginBtn")
                    driver.execute_script("arguments[0].click();", login_btn)
                    # Check stop during login wait
                    for _ in range(8):
                        check_stop()
                        time.sleep(1)
                    
                    # Check login status message after CAPTCHA retry (retry section)
                    log("🔍 Checking login status message after CAPTCHA retry (retry section)...", 'info')
                    status_message = check_login_status_message(driver, wait)
                    if status_message:
                        log(f"📋 Login status message after CAPTCHA retry: {status_message}", 'info')
                    else:
                        log("ℹ️ No login status message found after CAPTCHA retry", 'info')
            
            check_stop()
            if "login-mfa" in driver.current_url or "パスコード" in driver.page_source:
                log("🔐 OTP required (retry)!", 'info')
                
                log("⏳ Waiting for OTP email to be sent (retry)...", 'info')
                # Check stop during OTP wait
                for _ in range(5):
                    check_stop()
                    time.sleep(1)
                
                try:
                    otp = get_otp_from_gmail()
                except StopIteration:
                    log("⏹️ Login process stopped during OTP retrieval (retry)", 'warning')
                    raise
                
                check_stop()
                log("⌨️ Entering OTP (retry)...", 'info')
                otp_field = wait.until(EC.presence_of_element_located((By.ID, "authCode")))
                otp_field.clear()
                otp_field.send_keys(otp)
                check_stop()
                time.sleep(1)
                
                check_stop()
                log("🖱️ Submitting OTP (retry)...", 'info')
                submit_btn = wait.until(EC.element_to_be_clickable((By.ID, "certify")))
                driver.execute_script("arguments[0].click();", submit_btn)
                log("⏳ OTP submitted, waiting for navigation (retry)...", 'info')
                # Check stop during OTP response wait
                for _ in range(10):
                    check_stop()
                    time.sleep(1)
                
                log(f"📍 Current URL after OTP (retry): {driver.current_url}", 'info')
                
                # Check login status message after OTP (retry section)
                log("🔍 Checking login status message after OTP (retry section)...", 'info')
                status_message = check_login_status_message(driver, wait)
                if status_message:
                    log(f"📋 Login status message after OTP: {status_message}", 'info')
                else:
                    log("ℹ️ No login status message found after OTP", 'info')
                
                if "login-mfa" in driver.current_url and "認証に失敗" in driver.page_source:
                    log("⚠️ OTP failed - getting fresh OTP and retrying again...", 'warning')
                    for _ in range(3):
                        check_stop()
                        time.sleep(1)
                    
                    try:
                        otp = get_otp_from_gmail()
                    except StopIteration:
                        log("⏹️ Login process stopped during OTP retry", 'warning')
                        raise
                    
                    check_stop()
                    log(f"⌨️ Entering fresh OTP (retry): {otp}", 'info')
                    otp_field = driver.find_element(By.ID, "authCode")
                    otp_field.clear()
                    otp_field.send_keys(otp)
                    check_stop()
                    time.sleep(1)
                    
                    check_stop()
                    log("🖱️ Submitting fresh OTP (retry)...", 'info')
                    submit_btn = driver.find_element(By.ID, "certify")
                    driver.execute_script("arguments[0].click();", submit_btn)
                    # Check stop during retry wait
                    for _ in range(10):
                        check_stop()
                        time.sleep(1)
                    
                    log(f"📍 Current URL after OTP retry: {driver.current_url}", 'info')
                    
                    # Check login status message after OTP retry (retry section)
                    log("🔍 Checking login status message after OTP retry (retry section)...", 'info')
                    status_message = check_login_status_message(driver, wait)
                    if status_message:
                        log(f"📋 Login status message after OTP retry: {status_message}", 'info')
                    else:
                        log("ℹ️ No login status message found after OTP retry", 'info')
            
            log(f"📍 Final URL after retry: {driver.current_url}", 'info')
            
            # Final login status check (retry section)
            log("🔍 Performing final login status message check (retry section)...", 'info')
            status_message = check_login_status_message(driver, wait)
            if status_message:
                log(f"📋 Final login status message (retry section): {status_message}", 'info')
            else:
                log("ℹ️ No login status message found in final check", 'info')
            
            # After re-running login, check if we're now on apply.html and process items
            if "apply.html" in driver.current_url:
                log("✅ Login successful after retry! Redirected to application page", 'success')
                try:
                    pop04_element = driver.find_element(By.ID, "pop04")
                    if pop04_element.is_displayed():
                        log("🔔 Popup (pop04) detected, clicking link (retry)...", 'info')
                        # Click the link in pop04
                        pop04_link_xpath = '//*[@id="pop04"]/div/div[1]/ul/li/a'
                        pop04_link = wait.until(EC.element_to_be_clickable((By.XPATH, pop04_link_xpath)))
                        driver.execute_script("arguments[0].click();", pop04_link)
                        try:
                            lottery_begin(driver, wait)
                        except StopIteration:
                            log("⏹️ Login process stopped during pop04 handling (retry)", 'warning')
                            raise
                        check_stop()
                        time.sleep(1)
                except:
                    pass  # pop04 not present, continue normally
                
                log("🎰 Starting lottery item processing (retry)...", 'info')
                for i in range(1, 6):
                    check_stop()  # Check stop before each item
                    log(f"📦 Processing lottery item {i}/5 (retry)...", 'info')
                    try:
                        # Check if the acceptBox element exists
                        accept_box_xpath = f'//*[@id="main"]/div[1]/ul/li[{i}]/div[2]/div'
                        accept_box_elements = driver.find_elements(By.XPATH, accept_box_xpath)
                        
                        # If element doesn't exist, no more items to process
                        if not accept_box_elements:
                            log(f"📭 Item {i} does not exist. No more items to process.", 'info')
                            break
                        
                        accept_box = accept_box_elements[0]
                        accept_box_class = accept_box.get_attribute("class")
                        log(f"📋 Item {i} status class: {accept_box_class}", 'info')
                        # If class contains "finish", terminate the loop
                        if "acceptBox flexB finish" in accept_box_class:
                            log(f"✅ Item {i} is already finished. Skipping.", 'success')
                            break
                        if "acceptBox flexB afoot" in accept_box_class:
                            log(f"⏳ Item {i} is in progress (afoot). Skipping.", 'info')
                            continue
                        # If class contains "accepting", execute the clicks
                        if "acceptBox flexB accepting" in accept_box_class:
                            log(f"🎯 Item {i} is accepting applications. Processing (retry)...", 'info')
                            
                            # Click the dl tag with class="subDl"
                            check_stop()
                            sub_dl_xpath = f'//*[@id="main"]/div[1]/ul/li[{i}]/div[2]/dl/dt'
                            sub_dl = wait.until(EC.element_to_be_clickable((By.XPATH, sub_dl_xpath)))
                            driver.execute_script("arguments[0].click();", sub_dl)
                            check_stop()
                            time.sleep(1)
                            
                            # Click the span element
                            check_stop()
                            span_xpath = f'//*[@id="main"]/div[1]/ul/li[{i}]/div[2]/dl/dd/div[3]/form/ul[1]/li/p/label/span'
                            span = wait.until(EC.element_to_be_clickable((By.XPATH, span_xpath)))
                            driver.execute_script("arguments[0].click();", span)
                            check_stop()
                            time.sleep(1)
                            
                            # Click the input tag with class="-check"
                            check_stop()
                            check_input_xpath = f'//*[@id="main"]/div[1]/ul/li[{i}]//input[@class="-check"]'
                            check_input = wait.until(EC.element_to_be_clickable((By.XPATH, check_input_xpath)))
                            driver.execute_script("arguments[0].click();", check_input)
                            check_stop()
                            time.sleep(1)
                                                        
                            # Check if pop04 div is displayed and handle it
                            try:
                                pop04_element = driver.find_element(By.ID, "pop04")
                                if pop04_element.is_displayed():
                                    log(f"  🔔 Popup (pop04) detected for item {i}, clicking link...", 'info')
                                    # Click the link in pop04
                                    pop04_link_xpath = '//*[@id="pop04"]/div/div[1]/ul/li/a'
                                    pop04_link = wait.until(EC.element_to_be_clickable((By.XPATH, pop04_link_xpath)))
                                    driver.execute_script("arguments[0].click();", pop04_link)
                                    try:
                                        lottery_begin(driver, wait)
                                    except StopIteration:
                                        log("⏹️ Login process stopped during pop04 handling (retry)", 'warning')
                                        raise
                                    check_stop()
                                    time.sleep(1)
                            except StopIteration:
                                raise
                            except:
                                pass  # pop04 not present, continue normally
                            
                            # Click the a tag with id="applyBtn"
                            check_stop()
                            apply_btn = wait.until(EC.element_to_be_clickable((By.ID, "applyBtn")))
                            driver.execute_script("arguments[0].click();", apply_btn)
                            # Check stop during submission wait
                            for _ in range(2):
                                check_stop()
                                time.sleep(1)
                            
                            log(f"✅ Item {i} processed successfully (retry)!", 'success')
                            
                    except StopIteration:
                        log(f"⏹️ Item processing stopped by user at item {i} (retry)", 'warning')
                        raise
                    except Exception as e:
                        log(f"❌ Error processing item {i} (retry): {e}", 'error')
                        import traceback
                        traceback.print_exc()
                        continue
            else:
                log("⚠️ Still on login page after retry", 'warning')
        
      
        # input("\nPress Enter to close...")
      
    except StopIteration:
        log("⏹️ Login process stopped by user", 'warning')
        raise
    except Exception as e:
        log(f"❌ Fatal error in login process: {e}", 'error')
        import traceback
        traceback.print_exc()
        raise
      
# Load data from Excel file row by row
def load_data_from_excel():
    chrome_options = Options()
    chrome_options.add_argument('--start-maximized')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
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
