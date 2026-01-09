# OTP Code Logic Analysis

## Overview
The OTP (One-Time Password) system retrieves authentication codes from Gmail and uses them to complete multi-factor authentication on the Pokemon Center Online website.

---

## 1. OTP Detection Flow

### Location: `lottery_begin()` function (lines 187, 393)

**Detection Logic:**
```python
if "login-mfa" in driver.current_url or "パスコード" in driver.page_source:
    print("OTP required!")
```

**How it works:**
- Checks if URL contains `"login-mfa"` (MFA login page)
- OR checks if page source contains `"パスコード"` (Japanese for "passcode")
- If either condition is true, OTP flow is triggered

**Potential Issues:**
- ✅ Good: Uses two detection methods (URL + page content)
- ⚠️ **Issue**: No timeout or explicit wait for OTP page to load
- ⚠️ **Issue**: Hardcoded Japanese text might break if website changes

---

## 2. OTP Retrieval Function

### Location: `get_otp_from_gmail()` (lines 91-113)

### Flow Diagram:
```
1. Initialize Gmail service
   ↓
2. Loop up to 12 times (60 seconds total)
   ↓
3. Search Gmail for emails matching query
   ↓
4. For each message found:
   - Extract message details
   - Check if sent to 'gratins_poker6r@icloud.com'
   - Search body for pattern: 【パスコード】(\d{6})
   - If found, return OTP
   ↓
5. Wait 5 seconds, repeat
   ↓
6. If no OTP found after 12 attempts → Raise Exception
```

### Code Breakdown:

```python
def get_otp_from_gmail():
    service = get_service()  # Gets Gmail API service
    
    for attempt in range(12):  # Max 12 attempts = 60 seconds
        # Search for emails with specific subject
        messages = list_messages(service, max_results=5, 
                                query='ポケモンセンターオンライン ログイン用パスコード')
        
        if messages:
            for msg in messages:
                # Get full message details
                subject, snippet, sender, to, date, categories, body = get_message(service, msg_id)
                
                # Filter by recipient email
                if 'gratins_poker6r@icloud.com' in to:
                    # Extract 6-digit OTP from body
                    match = re.search(r'【パスコード】(\d{6})', body)
                    if match:
                        otp = match.group(1)
                        return otp
        
        time.sleep(5)  # Wait 5 seconds between attempts
    
    raise Exception("OTP not received")
```

### Issues Identified:

#### 🔴 **Critical Issues:**

1. **Hardcoded Email Address**
   - Line 103: `if 'gratins_poker6r@icloud.com' in to:`
   - **Problem**: Only works for one specific email address
   - **Impact**: Won't work for other users
   - **Fix**: Should use the `EMAIL` variable from the current login session

2. **No Message Filtering by Time**
   - **Problem**: Could retrieve old OTP codes from previous sessions
   - **Impact**: Might use expired OTP codes
   - **Fix**: Filter messages by timestamp (only last 5-10 minutes)

3. **No Message Deduplication**
   - **Problem**: If multiple OTP emails exist, it might return the first one found (could be old)
   - **Impact**: Could use stale OTP codes
   - **Fix**: Sort by date descending, use most recent

4. **Regex Pattern Might Be Fragile**
   - Pattern: `r'【パスコード】(\d{6})'`
   - **Problem**: Exact Japanese characters required, might break if email format changes
   - **Impact**: OTP extraction could fail silently

#### ⚠️ **Moderate Issues:**

5. **Fixed Wait Time**
   - Line 111: `time.sleep(5)` - Always waits 5 seconds
   - **Problem**: If OTP arrives quickly, wastes time; if slow, might timeout
   - **Fix**: Exponential backoff or adaptive timing

6. **Limited Retry Attempts**
   - Only 12 attempts = 60 seconds total
   - **Problem**: OTP emails might take longer to arrive
   - **Fix**: Increase attempts or make it configurable

7. **No Error Handling for Gmail API**
   - **Problem**: If Gmail API fails, entire function crashes
   - **Fix**: Add try-except blocks

---

## 3. OTP Entry and Submission

### Location: `lottery_begin()` function (lines 195-226, 401-432)

### Flow:
```
1. Wait 5 seconds (for email to be sent)
   ↓
2. Call get_otp_from_gmail() to retrieve OTP
   ↓
3. Find OTP input field (ID: "authCode")
   ↓
4. Clear field and enter OTP
   ↓
5. Find submit button (ID: "certify")
   ↓
6. Click submit button
   ↓
7. Wait 10 seconds for navigation
   ↓
8. Check if OTP failed (URL still "login-mfa" + "認証に失敗" in page)
   ↓
9. If failed: Get fresh OTP and retry once
```

### Issues Identified:

#### 🔴 **Critical Issues:**

1. **No OTP Validation Before Submission**
   - **Problem**: Doesn't verify OTP format (should be 6 digits)
   - **Impact**: Could submit invalid OTP
   - **Fix**: Validate OTP before sending

2. **Hardcoded Wait Times**
   - Line 191: `time.sleep(5)` - Wait for email
   - Line 205: `time.sleep(10)` - Wait after submission
   - **Problem**: Fixed times might not be enough or too much
   - **Fix**: Use WebDriverWait for dynamic waiting

3. **Only One Retry Attempt**
   - **Problem**: If second OTP also fails, gives up
   - **Impact**: Login fails even if third attempt would work
   - **Fix**: Add configurable retry limit

4. **No OTP Expiry Check**
   - **Problem**: OTPs typically expire after 5-10 minutes
   - **Impact**: Might use expired OTP
   - **Fix**: Check email timestamp and reject old OTPs

#### ⚠️ **Moderate Issues:**

5. **Duplicate Code**
   - OTP entry logic is duplicated (lines 195-226 and 401-432)
   - **Problem**: Hard to maintain, easy to introduce bugs
   - **Fix**: Extract to separate function

6. **No Feedback on OTP Status**
   - **Problem**: Doesn't log which OTP was used
   - **Impact**: Hard to debug failures
   - **Fix**: Log OTP (masked) and timestamp

---

## 4. Complete Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│ User submits login credentials                              │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ Check if OTP required                                        │
│ (URL contains "login-mfa" OR page has "パスコード")          │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼ YES
┌─────────────────────────────────────────────────────────────┐
│ Wait 5 seconds (for email to be sent)                        │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ get_otp_from_gmail()                                         │
│ ├─ Search Gmail for OTP email                                │
│ ├─ Filter by recipient email                                │
│ ├─ Extract 6-digit code with regex                          │
│ └─ Return OTP (or retry up to 12 times)                     │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ Enter OTP in form field (ID: "authCode")                    │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ Click submit button (ID: "certify")                          │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ Wait 10 seconds for page navigation                          │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ Check if OTP failed                                          │
│ (URL still "login-mfa" AND "認証に失敗" in page)            │
└────────────────────┬────────────────────────────────────────┘
                     │
         ┌───────────┴───────────┐
         │                        │
         ▼ YES                    ▼ NO
┌──────────────────┐    ┌──────────────────────┐
│ Get fresh OTP    │    │ Login successful!    │
│ Retry once       │    │ Continue to lottery  │
└──────────────────┘    └──────────────────────┘
```

---

## 5. Recommended Improvements

### Priority 1 (Critical Fixes):

1. **Use Dynamic Email Address**
   ```python
   # Instead of hardcoded email
   if EMAIL in to or user_email in to:
   ```

2. **Filter Messages by Time**
   ```python
   # Only get messages from last 10 minutes
   from datetime import datetime, timedelta
   cutoff_time = datetime.now() - timedelta(minutes=10)
   # Filter messages by date
   ```

3. **Sort Messages by Date (Most Recent First)**
   ```python
   # Sort messages by internalDate descending
   messages.sort(key=lambda x: x.get('internalDate', 0), reverse=True)
   ```

4. **Extract OTP Entry to Function**
   ```python
   def enter_otp(driver, wait, otp):
       otp_field = wait.until(EC.presence_of_element_located((By.ID, "authCode")))
       otp_field.clear()
       otp_field.send_keys(otp)
       # ... rest of logic
   ```

### Priority 2 (Important Improvements):

5. **Add OTP Validation**
   ```python
   if not otp or len(otp) != 6 or not otp.isdigit():
       raise ValueError(f"Invalid OTP format: {otp}")
   ```

6. **Use WebDriverWait Instead of Fixed Sleeps**
   ```python
   # Instead of time.sleep(10)
   wait.until(lambda driver: "apply.html" in driver.current_url or 
                              "login-mfa" in driver.current_url)
   ```

7. **Add Configurable Retry Logic**
   ```python
   MAX_OTP_RETRIES = 3  # Configurable
   for retry in range(MAX_OTP_RETRIES):
       # retry logic
   ```

8. **Add Better Error Messages**
   ```python
   except Exception as e:
       print(f"Failed to retrieve OTP: {e}")
       print(f"Last checked {attempt+1} times over {(attempt+1)*5} seconds")
   ```

### Priority 3 (Nice to Have):

9. **Log OTP Usage (Masked)**
   ```python
   masked_otp = f"{otp[:2]}****"
   print(f"Using OTP: {masked_otp} (from email received at {email_time})")
   ```

10. **Add OTP Expiry Check**
    ```python
    email_time = datetime.fromtimestamp(int(message['internalDate'])/1000)
    if datetime.now() - email_time > timedelta(minutes=10):
        print("OTP email is too old, skipping...")
        continue
    ```

---

## 6. Summary of Issues

| Issue | Severity | Location | Impact |
|-------|----------|----------|--------|
| Hardcoded email address | 🔴 Critical | Line 103 | Won't work for other users |
| No time-based filtering | 🔴 Critical | Line 96-108 | Might use old OTPs |
| No message sorting | 🔴 Critical | Line 99 | Might use wrong OTP |
| Duplicate code | ⚠️ Moderate | Lines 195-226, 401-432 | Maintenance issues |
| Fixed wait times | ⚠️ Moderate | Multiple | Inefficient timing |
| Only one retry | ⚠️ Moderate | Line 209-226 | Low resilience |
| No OTP validation | ⚠️ Moderate | Line 198 | Could submit invalid OTP |

---

## 7. Testing Recommendations

1. **Test with multiple email addresses** - Verify dynamic email works
2. **Test with delayed OTP emails** - Verify timeout handling
3. **Test with old OTP emails in inbox** - Verify time filtering works
4. **Test OTP failure scenarios** - Verify retry logic
5. **Test with invalid OTP format** - Verify error handling

---

## Conclusion

The OTP logic is **functional but has several critical issues** that prevent it from working reliably for multiple users and could cause it to use expired or incorrect OTP codes. The main improvements needed are:

1. ✅ Use dynamic email address instead of hardcoded
2. ✅ Filter OTP emails by timestamp
3. ✅ Sort messages to get most recent OTP
4. ✅ Refactor duplicate code into reusable functions
5. ✅ Add better error handling and validation

