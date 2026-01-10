
import base64
import os
import re
import time
from datetime import datetime, timedelta
from html import unescape
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# If modifying these scopes, delete token.json
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# ============================================================================
# CONFIGURATION - Customize what emails to fetch
# ============================================================================
# Change these settings to control which emails are displayed:

# Query options (Gmail search syntax):
#   - 'label:INBOX -category:promotions'  - INBOX excluding promotions (RECOMMENDED)
#   - 'label:INBOX'                       - All INBOX emails (includes promotions)
#   - 'category:primary'                  - Only Primary tab emails
#   - '-category:promotions'              - All emails except promotions
#   - 'is:unread'                         - Only unread emails
#   - 'label:INBOX is:unread'             - Unread inbox emails
#   - '' (empty string)                   - All messages

DEFAULT_QUERY = 'label:INBOX -category:promotions'  # INBOX excluding promotions
MAX_RESULTS = 10  # Number of messages to display
SHOW_FULL_CONTENT = True  # Set to True to show full email body, False for preview only
# ============================================================================

def get_service():
    creds = None
    
    # Check if credentials.json exists
    if not os.path.exists('credentials.json'):
        raise FileNotFoundError(
            "credentials.json file not found!\n\n"
            "To fix this:\n"
            "1. Go to https://console.cloud.google.com/\n"
            "2. Create a new project or select an existing one\n"
            "3. Enable the Gmail API\n"
            "4. Go to 'Credentials' → 'Create Credentials' → 'OAuth client ID'\n"
            "5. Choose 'Desktop app' as the application type\n"
            "6. Download the credentials and save it as 'credentials.json' in this directory"
        )
    
    # Check if credentials.json is the correct type (OAuth client, not service account)
    try:
        import json
        with open('credentials.json', 'r', encoding='utf-8') as f:
            cred_data = json.load(f)
        
        # Check if it's a service account (wrong type)
        if 'type' in cred_data and cred_data.get('type') == 'service_account':
            raise ValueError(
                "ERROR: Your credentials.json is a SERVICE ACCOUNT, but you need OAUTH CLIENT credentials!\n\n"
                "Service accounts cannot access personal Gmail accounts.\n\n"
                "To fix this:\n"
                "1. Go to https://console.cloud.google.com/\n"
                "2. Select your project\n"
                "3. Go to 'APIs & Services' → 'Credentials'\n"
                "4. Click 'Create Credentials' → 'OAuth client ID'\n"
                "5. If prompted, configure the OAuth consent screen first\n"
                "6. Choose 'Desktop app' as the application type\n"
                "7. Click 'Create' and then 'Download JSON'\n"
                "8. Replace your current credentials.json with the downloaded file\n\n"
                "Note: Make sure you download OAuth client credentials, NOT service account credentials!"
            )
        
        # Check if it has the required structure for OAuth
        if 'installed' not in cred_data and 'web' not in cred_data:
            raise ValueError(
                "ERROR: Invalid credentials.json format!\n\n"
                "Your credentials.json must contain either an 'installed' or 'web' key.\n"
                "This means you need OAuth 2.0 Client credentials, not service account credentials.\n\n"
                "To fix this:\n"
                "1. Go to https://console.cloud.google.com/\n"
                "2. Go to 'APIs & Services' → 'Credentials'\n"
                "3. Click 'Create Credentials' → 'OAuth client ID'\n"
                "4. Choose 'Desktop app' as the application type\n"
                "5. Download the JSON file and replace your credentials.json\n\n"
                f"Current keys in your file: {list(cred_data.keys())[:5]}..."
            )
    except ValueError:
        raise  # Re-raise our custom ValueError
    except Exception as e:
        # If JSON parsing fails, let it fail naturally below
        pass
    
    # Load saved credentials
    try:
        if os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    except Exception as e:
        print(f"Error loading token.json: {e}")
        creds = None

    # Proactive token refresh to prevent refresh token expiration
    # In testing mode, refresh tokens expire after 7 days of inactivity
    # By refreshing regularly, we keep the refresh token active
    if creds and creds.refresh_token:
        should_refresh = False
        
        # Refresh if token is expired
        if creds.expired:
            should_refresh = True
        # Proactively refresh if token expires soon (within 5 minutes)
        # This ensures we use the refresh token regularly to keep it active
        elif creds.expiry:
            # Calculate time until expiry (creds.expiry is typically timezone-aware UTC)
            # Handle both timezone-aware and naive datetime objects
            from datetime import timezone
            expiry = creds.expiry
            
            # Use timezone-aware datetime (fixes deprecation warning)
            if expiry.tzinfo is not None:
                now = datetime.now(timezone.utc)
            else:
                # If expiry is naive, convert to UTC for comparison
                now = datetime.now(timezone.utc).replace(tzinfo=None)
            
            time_until_expiry = (expiry - now).total_seconds()
            # Refresh if less than 5 minutes until expiry, or if it's been more than 6 days since last refresh
            # (to prevent refresh token expiration in testing mode)
            if time_until_expiry < 300:  # 5 minutes
                should_refresh = True
            else:
                # Check token.json modification time to see when we last refreshed
                try:
                    token_mtime = os.path.getmtime('token.json')
                    days_since_refresh = (time.time() - token_mtime) / (24 * 3600)
                    # Refresh proactively every 6 days to keep refresh token active
                    if days_since_refresh >= 6:
                        should_refresh = True
                except:
                    # If we can't check mtime, refresh if token is close to expiring
                    if time_until_expiry < 3600:  # 1 hour
                        should_refresh = True
        
        if should_refresh:
            try:
                creds.refresh(Request())
                # Save the refreshed credentials immediately to preserve refresh token
                try:
                    with open('token.json', 'w') as token:
                        token.write(creds.to_json())
                    print("Token refreshed successfully.")
                except Exception as e:
                    print(f"Warning: Could not save refreshed token: {e}")
            except Exception as e:
                error_msg = str(e).lower()
                print(f"Error refreshing token: {e}")
                
                # Check if refresh token has expired (common in testing mode)
                if 'invalid_grant' in error_msg or 'token has been expired or revoked' in error_msg:
                    print("\n" + "="*60)
                    print("Refresh token has expired or been revoked.")
                    print("This can happen if:")
                    print("  - The app is in 'Testing' mode and hasn't been used for 7+ days")
                    print("  - The refresh token was revoked in Google Account settings")
                    print("  - The OAuth consent screen configuration changed")
                    print("="*60 + "\n")
                
                # If refresh fails, the refresh token may have expired
                # Remove the invalid token file so user can re-authenticate
                if os.path.exists('token.json'):
                    try:
                        os.remove('token.json')
                        print("Removed expired token.json. Re-authentication will be required.")
                    except Exception as remove_error:
                        print(f"Warning: Could not remove expired token.json: {remove_error}")
                creds = None

    # If no valid credentials, run OAuth flow
    if not creds or not creds.valid:
        
        if not creds:
            print("\n" + "="*60)
            print("Starting OAuth authentication flow...")
            print("A browser window will open for authorization.")
            print("="*60 + "\n")
            try:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'credentials.json', SCOPES)
                # run_local_server automatically requests offline access (refresh token)
                creds = flow.run_local_server(port=0)
                
                # Verify we got valid credentials with refresh token
                if not creds or not creds.valid:
                    raise ValueError(
                        "OAuth flow completed but credentials are invalid.\n"
                        "This might indicate an access_denied error occurred in the browser.\n"
                        "Please check the browser for any error messages."
                    )
                
                # Verify we have a refresh token (critical for preventing expiration)
                if not creds.refresh_token:
                    raise ValueError(
                        "WARNING: No refresh token received!\n"
                        "This means tokens will expire permanently.\n"
                        "Make sure you're using OAuth 2.0 Desktop app credentials\n"
                        "and that the OAuth consent screen is properly configured."
                    )
            except ValueError as e:
                error_msg = str(e)
                if "Client secrets must be for a web or installed app" in error_msg:
                    raise ValueError(
                        "Invalid credentials.json format!\n\n"
                        "Your credentials.json must be for a 'Desktop app' (installed app) type.\n"
                        "The file should contain an 'installed' key with OAuth client credentials.\n\n"
                        "To fix this:\n"
                        "1. Go to Google Cloud Console → Credentials\n"
                        "2. Create OAuth client ID (NOT service account)\n"
                        "3. Choose 'Desktop app' as the application type\n"
                        "4. Download and replace credentials.json\n"
                        f"Original error: {e}"
                    )
                elif "access_denied" in error_msg or "403" in error_msg:
                    raise ValueError(
                        "ERROR 403: Access Denied - OAuth Consent Screen Issue!\n\n"
                        "Your app is in 'Testing' mode and your email is not approved as a test user.\n\n"
                        "HOW TO FIX THIS:\n"
                        "1. Go to https://console.cloud.google.com/\n"
                        "2. Select your project\n"
                        "3. Go to 'APIs & Services' → 'OAuth consent screen'\n"
                        "4. Under 'Test users', click '+ ADD USERS'\n"
                        "5. Add your Gmail address (the one you're trying to access)\n"
                        "6. Click 'SAVE'\n"
                        "7. Run this script again\n\n"
                        "IMPORTANT: Make sure you add the EXACT Gmail address you want to access!\n\n"
                        "Alternative: If you want to use the app in production mode (no test users needed),\n"
                        "you'll need to complete Google's verification process, which is more complex.\n"
                        "For personal use, adding yourself as a test user is the easiest solution.\n\n"
                        f"Original error: {e}"
                    )
                else:
                    raise
            except Exception as e:
                error_msg = str(e).lower()
                if "access_denied" in error_msg or "403" in error_msg or "consent" in error_msg:
                    raise ValueError(
                        "ERROR: OAuth Access Denied!\n\n"
                        "This usually means:\n"
                        "1. Your app is in 'Testing' mode (most common)\n"
                        "2. Your email is not added as a test user\n\n"
                        "HOW TO FIX:\n"
                        "Step 1: Configure OAuth Consent Screen\n"
                        "   - Go to https://console.cloud.google.com/\n"
                        "   - Select your project\n"
                        "   - Go to 'APIs & Services' → 'OAuth consent screen'\n"
                        "   - If not configured, set User Type to 'External' (or 'Internal' if using Google Workspace)\n"
                        "   - Fill in the required app information (App name, User support email, Developer contact)\n"
                        "   - Click 'SAVE AND CONTINUE'\n"
                        "   - Add scopes if needed (Gmail API scopes should already be there)\n"
                        "   - Click 'SAVE AND CONTINUE'\n"
                        "   - Add test users (skip if you'll publish the app)\n"
                        "   - Review and go back to dashboard\n\n"
                        "Step 2: Add Yourself as a Test User\n"
                        "   - In 'OAuth consent screen', scroll to 'Test users' section\n"
                        "   - Click '+ ADD USERS'\n"
                        "   - Enter your Gmail address (the one you want to access)\n"
                        "   - Click 'ADD'\n"
                        "   - Click 'SAVE'\n\n"
                        "Step 3: Try Again\n"
                        "   - Run this script again\n"
                        "   - When the browser opens, make sure you're logged in with the same Gmail address\n"
                        "   - Click 'Continue' on the consent screen\n\n"
                        f"Technical error: {e}"
                    )
                elif "FileNotFoundError" in str(type(e).__name__):
                    raise FileNotFoundError(
                        "credentials.json file not found!\n\n"
                        "Please download your OAuth credentials from Google Cloud Console\n"
                        "and save it as 'credentials.json' in this directory."
                    )
                else:
                    # Re-raise other exceptions with helpful context
                    raise Exception(
                        f"OAuth authentication failed: {e}\n\n"
                        "If you see an 'access_denied' or '403' error in the browser,\n"
                        "you need to add your email as a test user in Google Cloud Console:\n"
                        "1. Go to APIs & Services → OAuth consent screen\n"
                        "2. Add your email under 'Test users'\n"
                        "3. Try again"
                    ) from e
        
        # Save the credentials for next run
        # This preserves the refresh token, which is critical for preventing permanent expiration
        try:
            with open('token.json', 'w') as token:
                token.write(creds.to_json())
            
            # Verify refresh token was saved
            if not creds.refresh_token:
                print("WARNING: No refresh token in saved credentials. Tokens may expire permanently.")
        except Exception as e:
            print(f"Warning: Could not save token.json: {e}")

    service = build('gmail', 'v1', credentials=creds)
    return service

def html_to_text(html_content):
    """Convert HTML to readable text by stripping tags."""
    if not html_content:
        return ""
    
    # Remove script and style elements
    text = re.sub(r'<script[^>]*>.*?</script>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    
    # Replace common HTML entities
    text = unescape(text)
    
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    
    # Replace multiple newlines with double newline
    text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
    
    # Clean up whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    
    return text.strip()

def get_email_body(payload):
    """
    Extract the email body content from the payload.
    Handles plain text, HTML, and multipart emails.
    Returns the email body as plain text.
    """
    body_text = ""
    body_html = ""
    
    def extract_body_from_part(part):
        """Recursively extract body from email parts."""
        nonlocal body_text, body_html
        
        # Get the part's MIME type
        mime_type = part.get('mimeType', '').lower()
        
        # Get the body data
        body = part.get('body', {})
        body_data = body.get('data', '')
        attachment_id = body.get('attachmentId')
        
        # Skip attachments (they have attachmentId)
        if attachment_id:
            return
        
        if body_data:
            # Decode base64 data (Gmail uses URL-safe base64)
            try:
                # Add padding if needed (base64 strings should be multiple of 4)
                missing_padding = len(body_data) % 4
                if missing_padding:
                    body_data += '=' * (4 - missing_padding)
                
                data = base64.urlsafe_b64decode(body_data)
                content = data.decode('utf-8', errors='ignore')
                
                if 'text/plain' in mime_type and not body_text:
                    body_text = content
                elif 'text/html' in mime_type and not body_html:
                    body_html = content
            except Exception as e:
                # If decoding fails, it might already be decoded or have different encoding
                # Try to use it directly or skip
                pass
        
        # Handle multipart messages (recursively)
        if 'parts' in part:
            for subpart in part['parts']:
                extract_body_from_part(subpart)
    
    # Check if this is a simple message or multipart
    mime_type = payload.get('mimeType', '').lower()
    
    if 'multipart' in mime_type:
        # Multipart message - extract from all parts
        if 'parts' in payload:
            for part in payload['parts']:
                extract_body_from_part(part)
    else:
        # Simple message - extract directly
        extract_body_from_part(payload)
    
    # Return plain text if available, otherwise convert HTML to text
    if body_text:
        return body_text.strip()
    elif body_html:
        # Convert HTML to readable text
        return html_to_text(body_html)
    else:
        return ""

def list_messages(service, max_results=10, query=None, label_ids=None):
    """
    List messages from Gmail.
    
    Args:
        service: Gmail API service object
        max_results: Maximum number of messages to return
        query: Gmail search query (e.g., 'label:INBOX', '-category:promotions')
        label_ids: List of label IDs to filter by (e.g., ['INBOX'])
    
    Common queries:
        - 'label:INBOX' - Only inbox messages
        - '-category:promotions' - Exclude promotional emails
        - 'category:primary' - Only primary category emails
        - 'label:INBOX -category:promotions' - Inbox excluding promotions
    """
    # Build the request parameters
    request_params = {
        'userId': 'me',
        'maxResults': max_results
    }
    
    # Add query if provided
    if query:
        request_params['q'] = query
    
    # Add label IDs if provided (takes precedence over query for label filtering)
    if label_ids:
        request_params['labelIds'] = label_ids
    
    results = service.users().messages().list(**request_params).execute()
    messages = results.get('messages', [])
    return messages

def get_message(service, msg_id, include_body=True):
    """
    Get a full message from Gmail.
    
    Args:
        service: Gmail API service object
        msg_id: Message ID
        include_body: Whether to extract the full email body (default: True)
    
    Returns:
        Tuple of (subject, snippet, sender, date, categories, body_content)
    """
    message = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
    payload = message.get('payload', {})
    headers = payload.get('headers', [])
    subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '(No Subject)')
    sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
    to = next((h['value'] for h in headers if h['name'] == 'To'), 'Unknown')
    date = next((h['value'] for h in headers if h['name'] == 'Date'), 'Unknown')
    snippet = message.get('snippet', '')
    
    # Get labels to see categories
    labels = message.get('labelIds', [])
    categories = [label for label in labels if label.startswith('CATEGORY_')]
    
    # Extract full body content
    body_content = ""
    if include_body:
        body_content = get_email_body(payload)
    
    return subject, snippet, sender, to, date, categories, body_content

if __name__ == '__main__':
    # Fix Windows console encoding for UTF-8 characters
    import sys
    if sys.platform == 'win32':
        import io
        # Set UTF-8 encoding for stdout to handle Unicode characters in email subjects
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    
    service = get_service()
    
    # Display configuration
    if DEFAULT_QUERY:
        print(f"Query: {DEFAULT_QUERY}")
        print(f"Max results: {MAX_RESULTS}")
        print("=" * 70 + "\n")
    
    # Fetch messages using the configured query
    messages = list_messages(
        service, 
        max_results=MAX_RESULTS,
        query=DEFAULT_QUERY if DEFAULT_QUERY else None
    )
    
    # Fallback: if no messages found with query, try INBOX label only
    if not messages and DEFAULT_QUERY:
        print("No messages found with current query. Trying INBOX only...")
        messages = list_messages(
            service,
            max_results=MAX_RESULTS,
            label_ids=['INBOX']
        )
    
    # Final fallback: get any messages
    if not messages:
        print("No messages found. Fetching all messages...")
        messages = list_messages(service, max_results=MAX_RESULTS)
    
    # Display messages
    if messages:
        print(f"Found {len(messages)} message(s):\n")
        for i, msg in enumerate(messages, 1):
            try:
                subject, snippet, sender, to, date, categories, body_content = get_message(
                    service, msg['id'], include_body=SHOW_FULL_CONTENT
                )
                
                print("=" * 70)
                print(f"MESSAGE {i} of {len(messages)}")
                print("=" * 70)
                print(f"Subject: {subject}")
                print(f"From: {sender}")
                print(f"To: {to}")
                print(f"Date: {date}")
                
                if categories:
                    # Clean up category names for display
                    clean_categories = [cat.replace('CATEGORY_', '').lower() for cat in categories]
                    print(f"Categories: {', '.join(clean_categories)}")
                
                print("-" * 70)
                
                if SHOW_FULL_CONTENT and body_content:
                    print("FULL CONTENT:")
                    print("-" * 70)
                    print(body_content)
                elif snippet:
                    print("PREVIEW:")
                    print("-" * 70)
                    print(snippet)
                else:
                    print("(No content available)")
                
                print("=" * 70)
                print()  # Blank line between messages
                
            except Exception as e:
                print(f"[{i}] Error loading message: {e}")
                import traceback
                traceback.print_exc()
                print('-' * 70)
                print()
    else:
        print("No messages found.")
        print("\nTip: Try changing DEFAULT_QUERY in the configuration section")
        print("     to see different types of emails (e.g., 'label:INBOX' for all inbox emails)")