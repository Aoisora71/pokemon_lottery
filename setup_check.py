"""
Setup Checker for Pokemon Lottery Bot
This script checks if all required files and configurations are in place.
"""

import os
import sys

def check_credentials():
    """Check if credentials.json exists and is valid"""
    if not os.path.exists('credentials.json'):
        print("\n" + "="*70)
        print("MISSING: credentials.json")
        print("="*70)
        print("\n📋 STEP-BY-STEP INSTRUCTIONS TO CREATE credentials.json:\n")
        print("1. Go to https://console.cloud.google.com/")
        print("2. Create a new project or select an existing one")
        print("3. Enable the Gmail API:")
        print("   - Go to 'APIs & Services' → 'Library'")
        print("   - Search for 'Gmail API'")
        print("   - Click 'Enable'")
        print("4. Create OAuth 2.0 credentials:")
        print("   - Go to 'APIs & Services' → 'Credentials'")
        print("   - Click 'Create Credentials' → 'OAuth client ID'")
        print("   - If prompted, configure OAuth consent screen first:")
        print("     * Choose 'External' (for personal Gmail) or 'Internal' (for Workspace)")
        print("     * Fill in app name, support email, developer contact")
        print("     * Click 'Save and Continue' through all steps")
        print("   - Choose 'Desktop app' as the application type")
        print("   - Click 'Create'")
        print("   - Click 'Download JSON'")
        print("   - Save the downloaded file as 'credentials.json' in this directory")
        print("5. Configure OAuth Consent Screen (if not done):")
        print("   - Go to 'APIs & Services' → 'OAuth consent screen'")
        print("   - Add your Gmail address as a test user (if in Testing mode)")
        print("   - See OAUTH_SETUP_GUIDE.md for detailed instructions")
        print("\n" + "="*70 + "\n")
        return False
    
    # Check if it's a valid OAuth client credentials file
    try:
        import json
        with open('credentials.json', 'r', encoding='utf-8') as f:
            cred_data = json.load(f)
        
        # Check if it's a service account (wrong type)
        if 'type' in cred_data and cred_data.get('type') == 'service_account':
            print("\n" + "="*70)
            print("ERROR: credentials.json is a SERVICE ACCOUNT")
            print("="*70)
            print("\nYou need OAUTH CLIENT credentials, not service account credentials!")
            print("Service accounts cannot access personal Gmail accounts.\n")
            print("To fix:")
            print("1. Go to Google Cloud Console → Credentials")
            print("2. Create OAuth client ID (NOT service account)")
            print("3. Choose 'Desktop app' as application type")
            print("4. Download and replace credentials.json\n")
            return False
        
        # Check if it has the required structure
        if 'installed' not in cred_data and 'web' not in cred_data:
            print("\n" + "="*70)
            print("ERROR: Invalid credentials.json format")
            print("="*70)
            print("\nYour credentials.json must contain an 'installed' or 'web' key.")
            print("This means you need OAuth 2.0 Client credentials.\n")
            return False
        
        print("OK: credentials.json found and appears valid")
        return True
        
    except json.JSONDecodeError:
        print("\n" + "="*70)
        print("ERROR: credentials.json is not valid JSON")
        print("="*70)
        print("\nPlease check that the file is a valid JSON file downloaded from Google Cloud Console.\n")
        return False
    except Exception as e:
        print(f"\n⚠️  Warning: Could not validate credentials.json: {e}")
        return True  # Assume it's okay if we can't validate

def check_env_file():
    """Check if .env file exists"""
    if not os.path.exists('.env'):
        print("\n" + "="*70)
        print("OPTIONAL: .env file not found")
        print("="*70)
        print("\nThe .env file is optional but recommended for storing:")
        print("- CAPTCHA_API_KEY")
        print("- EMAIL")
        print("- PASSWORD")
        print("\nYou can also provide these values through the web interface.")
        print("See README.md for .env file format.\n")
        return False
    else:
        print("OK: .env file found")
        return True

def check_token():
    """Check if token.json exists (optional, will be created on first run)"""
    if os.path.exists('token.json'):
        print("OK: token.json found (OAuth token already configured)")
        return True
    else:
        print("INFO: token.json will be created automatically on first run")
        return True

def main():
    # Set UTF-8 encoding for Windows console
    if sys.platform == 'win32':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    
    print("\n" + "="*70)
    print("Pokemon Lottery Bot - Setup Checker")
    print("="*70)
    
    all_ok = True
    
    # Check credentials.json
    if not check_credentials():
        all_ok = False
    
    # Check .env file
    check_env_file()
    
    # Check token.json
    check_token()
    
    print("\n" + "="*70)
    if all_ok:
        print("Setup looks good! You can run the application now.")
        print("\nTo run:")
        print("  - Web interface: python app.py")
        print("  - Gmail reader:  python main.py")
    else:
        print("Setup incomplete. Please fix the issues above.")
    print("="*70 + "\n")
    
    return 0 if all_ok else 1

if __name__ == '__main__':
    sys.exit(main())

