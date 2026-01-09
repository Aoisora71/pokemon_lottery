# OAuth Setup Guide - Fixing "Error 403: access_denied"

If you're seeing the error: **"Error 403: access_denied - The app is currently being tested, and can only be accessed by developer-approved testers"**, follow these steps:

## Quick Fix: Add Yourself as a Test User

### Step 1: Go to Google Cloud Console
1. Open https://console.cloud.google.com/
2. Select your project (the one where you created the OAuth credentials)

### Step 2: Configure OAuth Consent Screen (if not already done)
1. Go to **APIs & Services** → **OAuth consent screen**
2. If not configured:
   - Choose **User Type**: Select **External** (for personal Gmail accounts) or **Internal** (if using Google Workspace)
   - Click **CREATE**
   - Fill in the required information:
     - **App name**: e.g., "Gmail Reader"
     - **User support email**: Your email
     - **Developer contact information**: Your email
   - Click **SAVE AND CONTINUE**
   - On the **Scopes** page, click **SAVE AND CONTINUE** (scopes should already include Gmail API)
   - On the **Test users** page, proceed to next step
   - Review and go back to dashboard

### Step 3: Add Yourself as a Test User
1. In the **OAuth consent screen** page, scroll down to the **Test users** section
2. Click **+ ADD USERS**
3. Enter your **Gmail address** (the exact email you want to access)
4. Click **ADD**
5. Click **SAVE** at the bottom of the page

### Step 4: Run the Script Again
1. Run `py main.py` again
2. When the browser opens, make sure you're logged in with the **same Gmail address** you added as a test user
3. Click **Continue** on the consent screen
4. The script should now work!

## Important Notes

- **Exact Email Match**: The Gmail address you add as a test user must match exactly the email you use when logging into Google in the browser
- **Testing Mode**: While in testing mode, only users in the test users list can access the app
- **Production Mode**: To use the app without test users, you'll need to complete Google's verification process, which is more complex and typically not needed for personal use

## Troubleshooting

### Still getting access_denied?
- Make sure you added the correct Gmail address (check for typos)
- Make sure you're logged into the browser with the same Gmail address
- Wait a few minutes after adding test users (changes can take a moment to propagate)
- Clear your browser cache and try again

### Can't find "Test users" section?
- Make sure you're on the OAuth consent screen page
- The Test users section only appears when the app is in "Testing" publishing status
- If your app is in "Production" status, you won't see test users (but also shouldn't need them)

### Need help?
The script will now provide detailed error messages if something goes wrong. Read the error message carefully - it contains step-by-step instructions.

