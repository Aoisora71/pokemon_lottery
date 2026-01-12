"""
Google Sheets helper functions for reading and writing data
"""
import gspread
from google.oauth2 import service_account
import os
from typing import List, Tuple, Optional

# Path to Google Sheets API credentials JSON file
SHEETS_CREDENTIALS_PATH = 'groovy-electron-478008-k6-38538c9620a5.json'

def get_sheets_client():
    """
    Get authenticated Google Sheets client
    Returns: gspread.Client instance
    """
    if not os.path.exists(SHEETS_CREDENTIALS_PATH):
        raise FileNotFoundError(f"Google Sheets credentials file not found: {SHEETS_CREDENTIALS_PATH}")
    
    scope = [
        'https://spreadsheets.google.com/feeds',
        'https://www.googleapis.com/auth/drive'
    ]
    
    creds = service_account.Credentials.from_service_account_file(
        SHEETS_CREDENTIALS_PATH,
        scopes=scope
    )
    
    client = gspread.authorize(creds)
    return client

def extract_spreadsheet_id(spreadsheet_input: str) -> str:
    """
    Extract spreadsheet ID from URL or use as-is if it's already an ID
    
    Examples:
        - "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit"
        - "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
    
    Returns: Spreadsheet ID string
    """
    spreadsheet_input = spreadsheet_input.strip()
    
    # Check if it's a URL
    if 'docs.google.com/spreadsheets/d/' in spreadsheet_input:
        # Extract ID from URL
        parts = spreadsheet_input.split('/d/')
        if len(parts) > 1:
            spreadsheet_id = parts[1].split('/')[0]
            return spreadsheet_id
    
    # If it's not a URL, assume it's already an ID
    return spreadsheet_input

def read_sheets_data(spreadsheet_id: str, worksheet_name: str = None) -> Tuple[List[Tuple], int, int]:
    """
    Read data from Google Sheets
    
    Column mapping:
        - Column A (index 0): Email address (ログイン情報)
        - Column B (index 1): Password (パスワード)
        - Column C (index 2): Status (状態) - "成功"の場合はスキップ
        - Column D (index 3): Detailed message (具体的な状態) - 読み取り専用
        - Column E (index 4): Timestamp (最終進行時間) - 読み取り専用
    
    Args:
        spreadsheet_id: Google Spreadsheet ID or URL
        worksheet_name: Name of the worksheet (default: first sheet)
    
    Returns:
        Tuple of (data_rows, total_email_count, skipped_count) where:
        - data_rows: List of (row_number, email, password) tuples for rows to process
        - total_email_count: Total number of rows with email addresses
        - skipped_count: Number of rows skipped (already "成功" in column C)
    """
    try:
        client = get_sheets_client()
        spreadsheet_id = extract_spreadsheet_id(spreadsheet_id)
        spreadsheet = client.open_by_key(spreadsheet_id)
        
        # Get worksheet (same worksheet used for writing)
        if worksheet_name:
            worksheet = spreadsheet.worksheet(worksheet_name)
        else:
            worksheet = spreadsheet.sheet1  # Use first sheet
        
        # Get all values from the same spreadsheet
        all_values = worksheet.get_all_values()
        
        data_rows = []
        skipped_count = 0
        total_email_count = 0
        
        # Process each row (skip header row if exists)
        for i, row in enumerate(all_values, start=1):
            if not row or not row[0] or not row[0].strip():
                continue  # Skip empty rows
            
            # Column A: Email address (ログイン情報)
            email = row[0].strip()
            
            # Column B: Password (パスワード)
            password = row[1].strip() if len(row) > 1 and row[1] else None
            
            if not email:
                continue
            
            total_email_count += 1
            
            # Column C: Check for "成功" status (状態)
            column_c_value = None
            if len(row) > 2 and row[2]:
                column_c_value = str(row[2]).strip()
            
            # Skip rows that are already "成功"
            if column_c_value == "成功":
                skipped_count += 1
            else:
                # Add to processing list: (row_number, email, password)
                data_rows.append((i, email, password))
        
        return data_rows, total_email_count, skipped_count
    
    except Exception as e:
        raise Exception(f"Error reading Google Sheets: {str(e)}")

def write_sheets_result(spreadsheet_id: str, row_number: int, status: str, message: str, timestamp: str, worksheet_name: str = None):
    """
    Write result to Google Sheets (same spreadsheet used for reading)
    
    Args:
        spreadsheet_id: Google Spreadsheet ID or URL (same as used for reading)
        row_number: Row number (1-based)
        status: Status to write to column C (状態)
        message: Message to write to column D (具体的な状態)
        timestamp: Timestamp to write to column E (最終進行時間)
        worksheet_name: Name of the worksheet (default: first sheet, same as used for reading)
    
    Column mapping:
        - Column A (index 0): Email address (読み込み専用)
        - Column B (index 1): Password (読み込み専用)
        - Column C (index 2): Status (書き込み: 成功/失敗)
        - Column D (index 3): Detailed message (書き込み: 具体的な状態)
        - Column E (index 4): Timestamp (書き込み: 最終進行時間)
    """
    try:
        client = get_sheets_client()
        spreadsheet_id = extract_spreadsheet_id(spreadsheet_id)
        spreadsheet = client.open_by_key(spreadsheet_id)
        
        # Get worksheet (same worksheet used for reading)
        if worksheet_name:
            worksheet = spreadsheet.worksheet(worksheet_name)
        else:
            worksheet = spreadsheet.sheet1  # Use first sheet
        
        # Use batch update for better performance and atomicity
        # Update columns C, D, E in a single batch operation
        range_name = f"C{row_number}:E{row_number}"
        values = [[status, message, timestamp]]
        worksheet.update(range_name, values, value_input_option='USER_ENTERED')
        
    except Exception as e:
        raise Exception(f"Error writing to Google Sheets (row {row_number}): {str(e)}")

def check_sheets_access(spreadsheet_id: str, worksheet_name: str = None) -> bool:
    """
    Check if we can access the spreadsheet
    
    Args:
        spreadsheet_id: Google Spreadsheet ID or URL
        worksheet_name: Name of the worksheet (default: first sheet)
    
    Returns:
        True if accessible, False otherwise
    """
    try:
        client = get_sheets_client()
        spreadsheet_id = extract_spreadsheet_id(spreadsheet_id)
        spreadsheet = client.open_by_key(spreadsheet_id)
        
        if worksheet_name:
            worksheet = spreadsheet.worksheet(worksheet_name)
        else:
            worksheet = spreadsheet.sheet1
        
        # Try to read first row to verify access
        worksheet.get('A1')
        return True
    except Exception as e:
        return False
