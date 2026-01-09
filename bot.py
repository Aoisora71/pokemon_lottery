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

def solve_recaptcha(site_key, url, max_retries=5):
    for attempt in range(1, max_retries + 1):
        try:
            print(f"Solving CAPTCHA... (Attempt {attempt}/{max_retries})")
            submit_url = f"http://2captcha.com/in.php?key={CAPTCHA_API_KEY}&method=userrecaptcha&googlekey={site_key}&pageurl={url}&invisible=1"
            response = requests.get(submit_url)
            
            if "OK|" not in response.text:
                error_msg = response.text
                print(f"2captcha submit error: {error_msg}")
                if attempt < max_retries:
                    print(f"Retrying in 3 seconds...")
                    time.sleep(3)
                    continue
                else:
                    raise Exception(f"2captcha error: {error_msg}")
            
            captcha_id = response.text.split("|")[1]
            print(f"CAPTCHA ID: {captcha_id}")
            
            result_url = f"http://2captcha.com/res.php?key={CAPTCHA_API_KEY}&action=get&id={captcha_id}"
            
            for i in range(30):
                time.sleep(5)
                result = requests.get(result_url)
                
                if "CAPCHA_NOT_READY" in result.text:
                    print(f"Waiting for CAPTCHA solution... ({i+1}/30)")
                    continue
                elif "OK|" in result.text:
                    solution = result.text.split("|")[1]
                    print("CAPTCHA solved!")
                    return solution
                elif "ERROR_CAPTCHA_UNSOLVABLE" in result.text:
                    print(f"CAPTCHA unsolvable, retrying... (Attempt {attempt}/{max_retries})")
                    if attempt < max_retries:
                        time.sleep(3)
                        break  # Break inner loop to retry from start
                    else:
                        raise Exception(f"2captcha error: {result.text}")
                else:
                    error_msg = result.text
                    print(f"2captcha result error: {error_msg}")
                    if attempt < max_retries:
                        time.sleep(3)
                        break  # Break inner loop to retry from start
                    else:
                        raise Exception(f"2captcha error: {error_msg}")
            else:
                # If we exhausted the 30 attempts without success, retry
                if attempt < max_retries:
                    print(f"CAPTCHA timeout, retrying... (Attempt {attempt}/{max_retries})")
                    time.sleep(3)
                    continue
                else:
                    raise Exception("CAPTCHA timeout after all retries")
        except Exception as e:
            if attempt < max_retries and "2captcha error" in str(e):
                print(f"Error occurred: {e}, retrying... (Attempt {attempt}/{max_retries})")
                time.sleep(3)
                continue
            else:
                raise
    
    raise Exception("CAPTCHA solving failed after all retries")

def get_otp_from_gmail():
    print("Checking Gmail for OTP...")
    service = get_service()
    
    # Use the current EMAIL variable instead of hardcoded email
    target_email = EMAIL.lower() if EMAIL else None
    if not target_email:
        raise ValueError("EMAIL is not set. Cannot retrieve OTP.")
    
    print(f"Looking for OTP emails sent to: {target_email}")
    
    for attempt in range(12):
        try:
            messages = list_messages(service, max_results=5, query='ポケモンセンターオンライン ログイン用パスコード')
            
            print(f"Attempt {attempt+1}/12: Found {len(messages) if messages else 0} message(s) matching query")
            
            if messages:
                for msg in messages:
                    try:
                        msg_id = msg['id']
                        subject, snippet, sender, to, date, categories, body = get_message(service, msg_id)
                        
                        print(f"  - Checking email: Subject='{subject[:50]}...', To='{to}', Date='{date}'")
                        
                        # Check if email is sent to the current user's email
                        # Handle multiple recipients (to field can be a comma-separated list)
                        to_emails = [email.strip().lower() for email in to.split(',')] if to else []
                        
                        if target_email in to_emails or any(target_email in email for email in to_emails):
                            print(f"  ✓ Email recipient matches: {target_email}")
                            print(f"  - Body length: {len(body)} characters")
                            print(f"  - Body preview: {body[:200]}...")
                            
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
                                    print(f"  ✓ OTP found with pattern '{pattern}': {otp}")
                                    return otp
                            
                            print(f"  ✗ No OTP pattern matched in email body")
                        else:
                            print(f"  ✗ Email recipient doesn't match. Expected: {target_email}, Got: {to}")
                    except Exception as e:
                        print(f"  ✗ Error processing message {msg_id}: {e}")
                        import traceback
                        traceback.print_exc()
                        continue
            else:
                print(f"  No messages found with query 'ポケモンセンターオンライン ログイン用パスコード'")
                # Try a broader search
                if attempt == 2:  # After 3 attempts, try broader search
                    print("  Trying broader search (searching for 'パスコード' or 'passcode')...")
                    broader_messages = list_messages(service, max_results=10, query='パスコード OR passcode')
                    print(f"  Broader search found {len(broader_messages) if broader_messages else 0} message(s)")
        
        except Exception as e:
            print(f"  ✗ Error during Gmail search: {e}")
            import traceback
            traceback.print_exc()
        
        print(f"Waiting for OTP email... ({attempt+1}/12)")
        time.sleep(5)
    
    raise Exception("OTP not received after 12 attempts (60 seconds). Check if email was sent and verify email address matches.")
def lottery_begin(driver, wait=None):
    if wait is None:
        wait = WebDriverWait(driver, 30)
    try:
        print(f"Opening {LOGIN_URL}")
        driver.get(LOGIN_URL)
        time.sleep(10)
        
        print("Entering email...")
        email_field = wait.until(EC.presence_of_element_located((By.ID, "email")))
        email_field.send_keys(EMAIL)
        time.sleep(1)
        
        print("Entering password...")
        if PASSWORD is None:
            raise ValueError("PASSWORD is not set. Please set it in .env file or include it in column B of the Excel file.")
        password_field = driver.find_element(By.ID, "password")
        password_field.send_keys(PASSWORD)
        time.sleep(1)
        
        print("Clicking login...")
        login_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a.loginBtn")))
        driver.execute_script("arguments[0].click();", login_btn)
        time.sleep(8)
        
        current_url = driver.current_url
        print(f"After login: {current_url}")
        
        if "login.html" in current_url and "認証に失敗" in driver.page_source:
            print("Login failed - solving captcha...")
            
            match = re.search(r'6Le[a-zA-Z0-9_-]+', driver.page_source)
            if match:
                site_key = match.group(0)
                print(f"Site key: {site_key}")
                
                captcha_solution = solve_recaptcha(site_key, driver.current_url)
                
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
                time.sleep(2)
                
                print("Re-entering credentials...")
                email_field = driver.find_element(By.ID, "email")
                email_field.clear()
                email_field.send_keys(EMAIL)
                
                password_field = driver.find_element(By.ID, "password")
                password_field.clear()
                password_field.send_keys(PASSWORD)
                time.sleep(1)
                
                print("Clicking login again...")
                login_btn = driver.find_element(By.CSS_SELECTOR, "a.loginBtn")
                driver.execute_script("arguments[0].click();", login_btn)
                time.sleep(8)
        
        if "login-mfa" in driver.current_url or "パスコード" in driver.page_source:
            print("OTP required!")
            
            print("Waiting for OTP email to be sent...")
            time.sleep(5)
            
            otp = get_otp_from_gmail()
            
            print("Entering OTP...")
            otp_field = wait.until(EC.presence_of_element_located((By.ID, "authCode")))
            otp_field.clear()
            otp_field.send_keys(otp)
            time.sleep(1)
            
            print("Submitting OTP...")
            submit_btn = wait.until(EC.element_to_be_clickable((By.ID, "certify")))
            driver.execute_script("arguments[0].click();", submit_btn)
            print("OTP submitted, waiting for navigation...")
            time.sleep(10)
            
            print(f"After OTP: {driver.current_url}")
            
            if "login-mfa" in driver.current_url and "認証に失敗" in driver.page_source:
                print("OTP failed - getting fresh OTP and retrying...")
                time.sleep(3)
                
                otp = get_otp_from_gmail()
                
                print(f"Entering fresh OTP: {otp}")
                otp_field = driver.find_element(By.ID, "authCode")
                otp_field.clear()
                otp_field.send_keys(otp)
                time.sleep(1)
                
                print("Submitting fresh OTP...")
                submit_btn = driver.find_element(By.ID, "certify")
                driver.execute_script("arguments[0].click();", submit_btn)
                time.sleep(10)
                
                print(f"After retry: {driver.current_url}")
        
        print(f"✅ Final URL: {driver.current_url}")
        
        if "apply.html" in driver.current_url:
            print("✅ Login successful!")
            try:
                pop04_element = driver.find_element(By.ID, "pop04")
                if pop04_element.is_displayed():
                    print("pop04 detected, clicking link...")
                    # Click the link in pop04
                    pop04_link_xpath = '//*[@id="pop04"]/div/div[1]/ul/li/a'
                    pop04_link = wait.until(EC.element_to_be_clickable((By.XPATH, pop04_link_xpath)))
                    driver.execute_script("arguments[0].click();", pop04_link)
                    time.sleep(1)
                    lottery_begin(driver, wait)
            except:
                pass  # pop04 not present, continue normally
                        
            for i in range(1, 6):
                print(f"Processing item {i}...")
                try:
                    # Check if the acceptBox element exists
                    accept_box_xpath = f'//*[@id="main"]/div[1]/ul/li[{i}]/div[2]/div'
                    accept_box_elements = driver.find_elements(By.XPATH, accept_box_xpath)
                    
                    # If element doesn't exist, no more items to process
                    if not accept_box_elements:
                        print(f"Item {i} does not exist. No more items to process.")
                        break
                    
                    accept_box = accept_box_elements[0]
                    accept_box_class = accept_box.get_attribute("class")
                    print(f"Item {i} acceptBox class: {accept_box_class}")
                    # If class contains "finish", terminate the loop
                    if "acceptBox flexB finish" in accept_box_class:
                        print(f"Item {i} is finished. Terminating loop.")
                        break
                    if "acceptBox flexB afoot" in accept_box_class:
                        print(f"Item {i} is afoot. Terminating loop.")
                        continue
                    # If class contains "accepting", execute the clicks
                    if "acceptBox flexB accepting" in accept_box_class:
                        print(f"Processing item {i}...")
                        
                        # Click the dl tag with class="subDl"
                        sub_dl_xpath = f'//*[@id="main"]/div[1]/ul/li[{i}]/div[2]/dl/dt'
                        sub_dl = wait.until(EC.element_to_be_clickable((By.XPATH, sub_dl_xpath)))
                        driver.execute_script("arguments[0].click();", sub_dl)
                        time.sleep(1)
                        
                        # Click the span element
                        span_xpath = f'//*[@id="main"]/div[1]/ul/li[{i}]/div[2]/dl/dd/div[3]/form/ul[1]/li/p/label/span'
                        span = wait.until(EC.element_to_be_clickable((By.XPATH, span_xpath)))
                        driver.execute_script("arguments[0].click();", span)
                        time.sleep(1)
                        
                        # Click the input tag with class="-check"
                        check_input_xpath = f'//*[@id="main"]/div[1]/ul/li[{i}]//input[@class="-check"]'
                        check_input = wait.until(EC.element_to_be_clickable((By.XPATH, check_input_xpath)))
                        driver.execute_script("arguments[0].click();", check_input)
                        time.sleep(1)
                        
                        # Click the a tag with class="popup-modal"
                        popup_modal_xpath = f'//*[@id="main"]/div[1]/ul/li[{i}]/div[2]/dl/dd/div[3]/form/ul[2]/li/a'
                        popup_modal = wait.until(EC.element_to_be_clickable((By.XPATH, popup_modal_xpath)))
                        driver.execute_script("arguments[0].click();", popup_modal)
                        time.sleep(1)
                        
                        # Check if pop04 exists and handle it
                        try:
                            pop04_element = driver.find_element(By.ID, "pop04")
                            if pop04_element.is_displayed():
                                print(f"pop04 detected for item {i}, clicking link...")
                                # Click the link in pop04
                                pop04_link_xpath = '//*[@id="pop04"]/div/div[1]/ul/li/a'
                                pop04_link = wait.until(EC.element_to_be_clickable((By.XPATH, pop04_link_xpath)))
                                driver.execute_script("arguments[0].click();", pop04_link)
                                lottery_begin(driver, wait)
                                time.sleep(1)
                        except:
                            pass  # pop04 not present, continue normally
                        
                        # Click the a tag with id="applyBtn"
                        apply_btn = wait.until(EC.element_to_be_clickable((By.ID, "applyBtn")))
                        driver.execute_script("arguments[0].click();", apply_btn)
                        time.sleep(2)
                        
                        print(f"Item {i} processed successfully.")
                        
                except Exception as e:
                    print(f"Error processing item {i}: {e}")
                    continue
  
        else:
            print("⚠️ Still on login page, re-running login process...")
            
            # Re-run the login section
            print(f"Opening {LOGIN_URL}")
            driver.get(LOGIN_URL)
            time.sleep(10)
            
            wait = WebDriverWait(driver, 30)
            
            print("Entering email...")
            email_field = wait.until(EC.presence_of_element_located((By.ID, "email")))
            email_field.send_keys(EMAIL)
            time.sleep(1)
            
            print("Entering password...")
            password_field = driver.find_element(By.ID, "password")
            password_field.send_keys(PASSWORD)
            time.sleep(1)
            
            print("Clicking login...")
            login_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a.loginBtn")))
            driver.execute_script("arguments[0].click();", login_btn)
            time.sleep(8)
            
            current_url = driver.current_url
            print(f"After login: {current_url}")
            
            if "login.html" in current_url and "認証に失敗" in driver.page_source:
                print("Login failed - solving captcha...")
                
                match = re.search(r'6Le[a-zA-Z0-9_-]+', driver.page_source)
                if match:
                    site_key = match.group(0)
                    print(f"Site key: {site_key}")
                    
                    captcha_solution = solve_recaptcha(site_key, driver.current_url)
                    
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
                    time.sleep(2)
                    
                    print("Re-entering credentials...")
                    email_field = driver.find_element(By.ID, "email")
                    email_field.clear()
                    email_field.send_keys(EMAIL)
                    
                    password_field = driver.find_element(By.ID, "password")
                    password_field.clear()
                    password_field.send_keys(PASSWORD)
                    time.sleep(1)
                    
                    print("Clicking login again...")
                    login_btn = driver.find_element(By.CSS_SELECTOR, "a.loginBtn")
                    driver.execute_script("arguments[0].click();", login_btn)
                    time.sleep(8)
            
            if "login-mfa" in driver.current_url or "パスコード" in driver.page_source:
                print("OTP required!")
                
                print("Waiting for OTP email to be sent...")
                time.sleep(5)
                
                otp = get_otp_from_gmail()
                
                print("Entering OTP...")
                otp_field = wait.until(EC.presence_of_element_located((By.ID, "authCode")))
                otp_field.clear()
                otp_field.send_keys(otp)
                time.sleep(1)
                
                print("Submitting OTP...")
                submit_btn = wait.until(EC.element_to_be_clickable((By.ID, "certify")))
                driver.execute_script("arguments[0].click();", submit_btn)
                print("OTP submitted, waiting for navigation...")
                time.sleep(10)
                
                print(f"After OTP: {driver.current_url}")
                
                if "login-mfa" in driver.current_url and "認証に失敗" in driver.page_source:
                    print("OTP failed - getting fresh OTP and retrying...")
                    time.sleep(3)
                    
                    otp = get_otp_from_gmail()
                    
                    print(f"Entering fresh OTP: {otp}")
                    otp_field = driver.find_element(By.ID, "authCode")
                    otp_field.clear()
                    otp_field.send_keys(otp)
                    time.sleep(1)
                    
                    print("Submitting fresh OTP...")
                    submit_btn = driver.find_element(By.ID, "certify")
                    driver.execute_script("arguments[0].click();", submit_btn)
                    time.sleep(10)
                    
                    print(f"After retry: {driver.current_url}")
            
            print(f"✅ Final URL after retry: {driver.current_url}")
            
            # After re-running login, check if we're now on apply.html and process items
            if "apply.html" in driver.current_url:
                print("✅ Login successful after retry!")
                try:
                    pop04_element = driver.find_element(By.ID, "pop04")
                    if pop04_element.is_displayed():
                        print("pop04 detected, clicking link...")
                        # Click the link in pop04
                        pop04_link_xpath = '//*[@id="pop04"]/div/div[1]/ul/li/a'
                        pop04_link = wait.until(EC.element_to_be_clickable((By.XPATH, pop04_link_xpath)))
                        driver.execute_script("arguments[0].click();", pop04_link)
                        lottery_begin(driver, wait)
                        time.sleep(1)
                except:
                    pass  # pop04 not present, continue normally
                
                for i in range(1, 6):
                    print(f"Processing item {i}...")
                    try:
                        # Check if the acceptBox element exists
                        accept_box_xpath = f'//*[@id="main"]/div[1]/ul/li[{i}]/div[2]/div'
                        accept_box_elements = driver.find_elements(By.XPATH, accept_box_xpath)
                        
                        # If element doesn't exist, no more items to process
                        if not accept_box_elements:
                            print(f"Item {i} does not exist. No more items to process.")
                            break
                        
                        accept_box = accept_box_elements[0]
                        accept_box_class = accept_box.get_attribute("class")
                        print(f"Item {i} acceptBox class: {accept_box_class}")
                        # If class contains "finish", terminate the loop
                        if "acceptBox flexB finish" in accept_box_class:
                            print(f"Item {i} is finished. Terminating loop.")
                            break
                        if "acceptBox flexB afoot" in accept_box_class:
                            print(f"Item {i} is afoot. Terminating loop.")
                            continue
                        # If class contains "accepting", execute the clicks
                        if "acceptBox flexB accepting" in accept_box_class:
                            print(f"Processing item {i}...")
                            
                            # Click the dl tag with class="subDl"
                            sub_dl_xpath = f'//*[@id="main"]/div[1]/ul/li[{i}]/div[2]/dl/dt'
                            sub_dl = wait.until(EC.element_to_be_clickable((By.XPATH, sub_dl_xpath)))
                            driver.execute_script("arguments[0].click();", sub_dl)
                            time.sleep(1)
                            
                            # Click the span element
                            span_xpath = f'//*[@id="main"]/div[1]/ul/li[{i}]/div[2]/dl/dd/div[3]/form/ul[1]/li/p/label/span'
                            span = wait.until(EC.element_to_be_clickable((By.XPATH, span_xpath)))
                            driver.execute_script("arguments[0].click();", span)
                            time.sleep(1)
                            
                            # Click the input tag with class="-check"
                            check_input_xpath = f'//*[@id="main"]/div[1]/ul/li[{i}]//input[@class="-check"]'
                            check_input = wait.until(EC.element_to_be_clickable((By.XPATH, check_input_xpath)))
                            driver.execute_script("arguments[0].click();", check_input)
                            time.sleep(1)
                                                        
                            # Check if pop04 div is displayed and handle it
                            try:
                                pop04_element = driver.find_element(By.ID, "pop04")
                                if pop04_element.is_displayed():
                                    print(f"pop04 detected for item {i}, clicking link...")
                                    # Click the link in pop04
                                    pop04_link_xpath = '//*[@id="pop04"]/div/div[1]/ul/li/a'
                                    pop04_link = wait.until(EC.element_to_be_clickable((By.XPATH, pop04_link_xpath)))
                                    driver.execute_script("arguments[0].click();", pop04_link)
                                    lottery_begin(driver, wait)
                                    time.sleep(1)
                            except:
                                pass  # pop04 not present, continue normally
                            
                            # Click the a tag with id="applyBtn"
                            apply_btn = wait.until(EC.element_to_be_clickable((By.ID, "applyBtn")))
                            driver.execute_script("arguments[0].click();", apply_btn)
                            time.sleep(2)
                            
                            print(f"Item {i} processed successfully.")
                            
                    except Exception as e:
                        print(f"Error processing item {i}: {e}")
                        continue
            else:
                print("⚠️ Still on login page after retry")
        
      
        # input("\nPress Enter to close...")
      
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        # input("\nPress Enter to close...")
      
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
                print(f"Processing email: {user_email}")
                lottery_begin(driver, wait)
                # user_email variable is now assigned for this row

        workbook.close()
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        driver.quit()
        input("\nPress Enter to stop the project...")




if __name__ == "__main__":
    load_data_from_excel()
