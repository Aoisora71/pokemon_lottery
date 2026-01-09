# 🚀 Quick Start Guide - Web Interface

## Step 1: Install Dependencies

```bash
pip install -r requirements.txt
```

## Step 2: Run the Web Server

```bash
python run.py
```

Or:

```bash
python app.py
```

## Step 3: Open in Browser

Open your browser and go to:

**http://localhost:5000**

## Step 4: Use the Interface

1. **Upload Excel File**: Click "Choose Excel file" and select your Excel file
   - Column A: Email addresses
   - Column B: Passwords (optional)

2. **Enter 2Captcha API Key**: 
   - Enter your API key in the field
   - Or leave empty to use value from `.env` file

3. **Click "Start Bot"**: The bot will begin processing

4. **Monitor Progress**: 
   - Watch real-time logs
   - See progress bar
   - Check for errors

5. **Stop if Needed**: Click "Stop Bot" to pause

## 📋 Excel File Format

```
| Email                    | Password    |
|--------------------------|-------------|
| user1@example.com        | password1   |
| user2@example.com        | password2   |
```

## 🔧 Configuration (Optional)

Create a `.env` file:

```env
CAPTCHA_API_KEY=your_key_here
EMAIL=default@example.com
PASSWORD=default_password
```

## ✅ That's It!

The web interface will handle everything else automatically.

For more details, see `WEB_UI_README.md`

