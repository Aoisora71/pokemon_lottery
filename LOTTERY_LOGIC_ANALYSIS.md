# 🎰 Pokemon Center Lottery Bot - Logic Analysis

## 📋 Overview

This document explains the complete lottery entry logic flow implemented in `bot.py`.

---

## 🔄 Main Flow: `lottery_begin()` Function

### Phase 1: Authentication (Lines 334-546)

```
1. Navigate to Login Page
   └─> https://www.pokemoncenter-online.com/lottery/login.html

2. Enter Credentials
   ├─> Email (from .env or Excel)
   └─> Password (from .env or Excel)

3. Click Login Button

4. Handle CAPTCHA (if required)
   ├─> Detect reCAPTCHA site key from page
   ├─> Submit to 2Captcha API
   ├─> Wait for solution (max 30 attempts × 5 seconds)
   ├─> Inject solution into page via JavaScript
   └─> Re-enter credentials and submit again

5. Handle OTP (One-Time Password) if required
   ├─> Wait 5 seconds for email
   ├─> Query Gmail API for OTP email
   ├─> Extract 6-digit code using regex patterns
   ├─> Enter OTP code
   └─> Submit OTP
   └─> Retry with fresh OTP if authentication fails
```

### Phase 2: Navigate to Application Page (Lines 548-556)

```
6. Check Current URL
   ├─> If already on apply.html → Continue
   └─> If not → Navigate to apply.html
```

### Phase 3: Handle Pop04 Modal (Lines 558-648)

```
7. Check for Pop04 Modal
   ├─> If pop04 is displayed:
   │   ├─> Read message from //*[@id="pop04"]/div/div[1]/p
   │   │
   │   ├─> If message = "意図しない例外が発生しました。"
   │   │   ├─> Reload page (F5 key)
   │   │   ├─> Fallback: driver.refresh()
   │   │   ├─> Fallback: driver.get(current_url)
   │   │   └─> Set pop04_reloaded = True
   │   │
   │   └─> Else (normal pop04)
   │       └─> Click close link: //*[@id="pop04"]/div/div[1]/ul/li/a
   │
   └─> If pop04 not present → Continue normally
```

### Phase 4: Post-Reload Status Validation (Lines 650-780)

**Only executed if `pop04_reloaded = True`:**

```
8. Check Lottery Status with Retry (Max 3 attempts)
   
   Attempt 1:
   ├─> Check: //*[@id="main"]/div[1]/ul/li[1]/div[2]/div/span[1]
   ├─> If status = "受付完了" or "受付中" → ✅ Valid, proceed
   └─> If status invalid/missing → Reload page (F5)
   
   Attempt 2:
   ├─> Reload page (F5)
   ├─> Close pop04 if appears
   ├─> Check status again
   ├─> If valid → ✅ Proceed
   └─> If invalid → Reload again
   
   Attempt 3:
   ├─> Reload page (F5)
   ├─> Close pop04 if appears
   ├─> Check status again
   ├─> If valid → ✅ Proceed
   └─> If invalid → ❌ Restart from login (recursive call to lottery_begin)
   
   After validation:
   ├─> Final status check
   ├─> If "受付終了" → Process lottery #2
   ├─> If "受付完了" or "受付中" → Process lottery #1
   └─> If unexpected → Restart from login
```

### Phase 5: Normal Flow Status Check (Lines 782-809)

**Only executed if `pop04_reloaded = False`:**

```
9. Check First Lottery Status
   ├─> XPath: //*[@id="main"]/div[1]/ul/li[1]/div[2]/div/span[1]
   │
   ├─> If status = "受付終了"
   │   └─> Process lottery #2 (second lottery)
   │
   ├─> If status = "受付完了" or "受付中"
   │   └─> Process lottery #1 (first lottery)
   │
   └─> If status is unexpected
       └─> Log warning but proceed anyway
```

---

## 🎯 Lottery Entry Processing: `_process_lottery_entry()` Function

This function handles the actual lottery entry for a specific lottery number.

### Step-by-Step Process:

#### Step 1: Expand Lottery Details
```
XPath: //*[@id="main"]/div[1]/ul/li[{lottery_number}]/div[2]/dl/dt
Action: Click to expand lottery details
```

#### Step 2: Select Radio Button (5 Strategies with Fallback)

**Strategy 1: p.radio Element (Most Reliable)**
```
XPath: //*[@id="main"]/div[1]/ul/li[{lottery_number}]/div[2]/dl/dd/div[3]/form/ul[1]/li/p[@class="radio"]
Method:
  1. Find input element inside p.radio
  2. Set checked = true via JavaScript
  3. Dispatch 'change' and 'click' events
  4. Click label element for extra assurance
  5. Verify input.checked = true
```

**Strategy 2: Label Element**
```
XPath: //*[@id="main"]/div[1]/ul/li[{lottery_number}]/div[2]/dl/dd/div[3]/form/ul[1]/li/p[@class="radio"]/label
Method: Click label (automatically selects input)
```

**Strategy 3: Input Element Direct**
```
XPath: //*[@id="main"]/div[1]/ul/li[{lottery_number}]/div[2]/dl/dd/div[3]/form/ul[1]/li/p[@class="radio"]/label/input[@type="radio"]
Method: Set checked and trigger events
```

**Strategy 4: Span Element (Fallback)**
```
XPath: //*[@id="main"]/div[1]/ul/li[{lottery_number}]/div[2]/dl/dd/div[3]/form/ul[1]/li/p[@class="radio"]/label/span
Method: Click span, then verify parent input
```

**Strategy 5: First Radio in Form (Last Resort)**
```
XPath: //*[@id="main"]/div[1]/ul/li[{lottery_number}]/div[2]/dl/dd/div[3]/form//input[@type="radio"]
Method: Find first radio input in form
```

#### Step 3: Check Checkbox
```
XPath: //*[@id="main"]/div[1]/ul/li[{lottery_number}]/div[2]/dl/dd/div[3]/form/div/div
Action: Click checkbox to confirm agreement
```

#### Step 4: Submit Form (Open Modal)
```
XPath: //*[@id="main"]/div[1]/ul/li[{lottery_number}]/div[2]/dl/dd/div[3]/form/ul[2]/li/a
Action: Click submit button to open confirmation modal
Wait: 2 seconds for modal to appear
```

#### Step 5: Confirm in Modal
```
Modal XPath: //*[@id="pop01"]/div/div[1]
Button ID: applyBtn
Action: Click apply button to finalize entry
Wait: 3 seconds for confirmation
```

---

## 🔀 Decision Tree

```
lottery_begin()
│
├─> Login Process
│   ├─> Enter credentials
│   ├─> Solve CAPTCHA (if needed)
│   └─> Enter OTP (if needed)
│
├─> Navigate to apply.html
│
├─> Check Pop04
│   ├─> Exception message? → Reload page (F5)
│   │   └─> Validate status (3 attempts)
│   │       ├─> Success → Process lottery
│   │       └─> Fail → Restart from login
│   │
│   └─> Normal pop04? → Close and continue
│
└─> Check Lottery Status
    ├─> "受付終了" → Process lottery #2
    ├─> "受付完了" or "受付中" → Process lottery #1
    └─> Other → Log warning, try to proceed
```

---

## 📊 Status Values

| Status | Meaning | Action |
|--------|---------|--------|
| **受付中** | Accepting applications | ✅ Process lottery #1 |
| **受付完了** | Applications completed | ✅ Process lottery #1 |
| **受付終了** | Applications closed | ⚠️ Process lottery #2 |
| **Other/Empty** | Unknown/Error | ⚠️ Warning, try to proceed or restart |

---

## 🔄 Retry and Recovery Mechanisms

### 1. CAPTCHA Solving
- **Max retries**: 5 attempts
- **Wait time**: 5 seconds per check (max 30 checks = 150 seconds)
- **Fallback**: None (raises exception if all fail)

### 2. OTP Retrieval
- **Max attempts**: 12 attempts
- **Wait time**: 5 seconds between attempts (max 60 seconds)
- **Retry on failure**: Yes, retrieves fresh OTP if authentication fails

### 3. Pop04 Exception Handling
- **Reload methods**: F5 → refresh() → get()
- **Status validation**: 3 attempts with page reload
- **Failure action**: Restart from login (recursive)

### 4. Radio Button Selection
- **Strategies**: 5 different methods
- **Verification**: Checks `input.checked` property after each attempt
- **Failure action**: Raises exception (stops processing)

---

## 🎯 Key Features

### 1. **Robust Error Handling**
- Multiple fallback strategies for each critical step
- Graceful degradation when elements are not found
- Comprehensive logging at each step

### 2. **State Management**
- Tracks if page was reloaded (`pop04_reloaded` flag)
- Validates status before proceeding
- Handles different lottery states appropriately

### 3. **User Control**
- `check_stop()` called frequently to allow user cancellation
- `StopIteration` exception propagates cleanly
- Logs provide clear feedback on progress

### 4. **Recursive Recovery**
- If status validation fails after 3 attempts → Restart from login
- Prevents infinite loops by using flags and return statements
- Ensures fresh authentication if page state is corrupted

---

## 🔍 Critical XPath Locations

### Status Check
```
//*[@id="main"]/div[1]/ul/li[1]/div[2]/div/span[1]
```
- **Lottery #1**: `li[1]`
- **Lottery #2**: `li[2]` (when #1 is closed)

### Lottery Entry Form
```
//*[@id="main"]/div[1]/ul/li[{lottery_number}]/div[2]/dl/dt                    # Expand details
//*[@id="main"]/div[1]/ul/li[{lottery_number}]/div[2]/dl/dd/div[3]/form/ul[1]/li/p[@class="radio"]  # Radio button
//*[@id="main"]/div[1]/ul/li[{lottery_number}]/div[2]/dl/dd/div[3]/form/div/div  # Checkbox
//*[@id="main"]/div[1]/ul/li[{lottery_number}]/div[2]/dl/dd/div[3]/form/ul[2]/li/a  # Submit button
```

### Modal Confirmation
```
//*[@id="pop01"]/div/div[1]  # Modal container
//*[@id="applyBtn"]          # Final apply button
```

---

## ⚠️ Important Notes

1. **Status Validation is Critical**
   - Only "受付完了" or "受付中" allow lottery entry
   - Invalid status triggers retry or restart

2. **Pop04 Exception is Expected**
   - "意図しない例外が発生しました。" is normal behavior
   - Page reload resolves the issue
   - Status must be validated after reload

3. **Radio Button Selection is Complex**
   - Multiple strategies ensure reliability
   - JavaScript events are triggered manually
   - Verification confirms selection succeeded

4. **Recursive Restart Mechanism**
   - Used when status validation fails completely
   - Ensures fresh login session
   - Prevents getting stuck in invalid states

---

## 📈 Execution Flow Summary

```
START
  ↓
Login → CAPTCHA → OTP → Apply Page
  ↓
Pop04 Check
  ├─> Exception? → Reload → Validate Status (3x) → Process
  └─> Normal? → Close → Continue
  ↓
Status Check
  ├─> "受付終了" → Lottery #2
  ├─> "受付完了"/"受付中" → Lottery #1
  └─> Invalid → Warning/Retry
  ↓
Process Lottery
  ├─> Expand details
  ├─> Select radio (5 strategies)
  ├─> Check checkbox
  ├─> Submit form
  └─> Confirm in modal
  ↓
COMPLETE
```

---

## 🐛 Potential Issues & Solutions

### Issue 1: Radio Button Not Clicking
- **Solution**: 5 fallback strategies implemented
- **Verification**: Checks `checked` property after each attempt

### Issue 2: Status Element Not Found
- **Solution**: 3 reload attempts with status validation
- **Fallback**: Restart from login if all fail

### Issue 3: Pop04 After Reload
- **Solution**: Checks and closes pop04 after each reload
- **Prevention**: Waits for page to stabilize

### Issue 4: Infinite Loop Risk
- **Solution**: Uses flags (`pop04_reloaded`) and return statements
- **Protection**: Max retry limits (3 attempts)

---

## 🔧 Configuration Points

- **Max CAPTCHA retries**: 5 (line 117)
- **Max OTP attempts**: 12 (line 212)
- **Max status validation retries**: 3 (line 676)
- **Wait times**: Configurable via `time.sleep()` calls

---

**Last Updated**: Based on `bot.py` version with lottery entry functionality
