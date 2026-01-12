# 🎮 Pokemon Center Lottery Bot

An automated bot for entering Pokemon Center Online lotteries with a modern web interface. Features automated login, CAPTCHA solving, OTP handling via Gmail API, and batch processing of multiple accounts.

## ✨ Features

- **🌐 Web Interface**: Modern, responsive web UI with real-time updates
- **🤖 Automated Login**: Handles login process automatically
- **🔐 CAPTCHA Solving**: Integrated 2Captcha API support
- **📧 OTP Handling**: Automatic OTP retrieval from Gmail
- **📊 Batch Processing**: Process multiple accounts from Excel file
- **📈 Real-time Monitoring**: Live progress tracking and logs
- **🎯 Error Handling**: Comprehensive error tracking and reporting

## 📋 Prerequisites

- Python 3.7 or higher
- Google Cloud Project with Gmail API enabled
- OAuth 2.0 credentials for Gmail API
- 2Captcha API key (for CAPTCHA solving)
- Chrome browser (for Selenium automation)

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Set Up Gmail API Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the **Gmail API**:
   - Go to "APIs & Services" → "Library"
   - Search for "Gmail API"
   - Click "Enable"
4. Create OAuth 2.0 credentials:
   - Go to "APIs & Services" → "Credentials"
   - Click "Create Credentials" → "OAuth client ID"
   - Choose "Desktop app" as the application type
   - Download the JSON file
   - Save it as `credentials.json` in this project directory
5. Configure OAuth Consent Screen:
   - Go to "APIs & Services" → "OAuth consent screen"
   - Set User Type to "External" (for personal Gmail) or "Internal" (for Google Workspace)
   - Fill in required app information
   - Add your Gmail address as a test user (if in Testing mode)
   - See `OAUTH_SETUP_GUIDE.md` for detailed instructions

### 3. Create Environment Variables File

Create a `.env` file in the project root:

```env
CAPTCHA_API_KEY=your_2captcha_api_key_here
PASSWORD=your_password_here
```

**Note:** Replace the placeholder values with your actual credentials:
- `CAPTCHA_API_KEY`: Get this from [2Captcha.com](https://2captcha.com/)
- `PASSWORD`: Your login password (optional - can also be provided in Excel file column B)

**Important:**
- **EMAIL**: Must be provided in the Excel file (Column A), not in `.env` file
- **PASSWORD**: Can be provided in `.env` file OR in Excel file (Column B). If provided in both, Excel file takes precedence.

### 4. Run the Web Interface

```bash
python app.py
```

Or use the launcher:

```bash
python run.py
```

### 5. Open in Browser

Navigate to: **http://localhost:5000**

## 📖 Usage

### Web Interface

1. **Upload Excel File**: 
   - Click "Choose Excel file" and select your Excel file
   - Column A: Email addresses
   - Column B: Passwords (optional - uses .env PASSWORD if not provided)

2. **Enter 2Captcha API Key**: 
   - Enter your API key in the field
   - Or leave empty to use value from `.env` file

3. **Start Bot**: Click "Start Bot" to begin processing

4. **Monitor Progress**: 
   - Watch real-time logs
   - See progress bar
   - Check for errors

5. **Stop if Needed**: Click "Stop Bot" to pause

### Excel File Format

```
| Email                    | Password    |
|--------------------------|-------------|
| user1@example.com        | password1   |
| user2@example.com        | password2   |
```

### Command Line Usage

#### Gmail Reader (`main.py`)

Reads and displays emails from your Gmail inbox:

```bash
python main.py
```

**First Run:**
- A browser window will open for OAuth authentication
- Sign in with your Gmail account
- Grant permissions
- A `token.json` file will be created automatically

**Configuration:**
You can customize email filtering in `main.py`:
- `DEFAULT_QUERY`: Gmail search query (e.g., `'label:INBOX -category:promotions'`)
- `MAX_RESULTS`: Number of messages to display (default: 10)
- `SHOW_FULL_CONTENT`: Set to `True` for full email body, `False` for preview only

#### Automated Login Bot (`bot.py`)

Automates the login process for Pokemon Center Online:

```bash
python bot.py
```

**What it does:**
1. Opens the login page in Chrome
2. Enters your email and password
3. Solves reCAPTCHA using 2Captcha API
4. Handles OTP (One-Time Password) from Gmail
5. Completes the login process

## 📁 Project Structure

```
pokemon_lottery/
├── app.py                 # Flask web application
├── run.py                 # Simple launcher script
├── bot.py                 # Bot automation logic
├── main.py                # Gmail API integration
├── requirements.txt       # Python dependencies
├── .env                   # Environment variables (create this)
├── credentials.json       # Gmail OAuth credentials (download from Google)
├── token.json             # Gmail OAuth token (auto-generated)
├── templates/
│   └── index.html         # Web interface HTML
├── static/
│   ├── css/
│   │   └── style.css      # Web interface styling
│   └── js/
│       └── app.js         # Frontend JavaScript
└── uploads/               # Uploaded Excel files (auto-created)
```

## 🔧 Configuration

### Environment Variables

Create a `.env` file with:

```env
CAPTCHA_API_KEY=your_2captcha_api_key_here
EMAIL=your_email@example.com
PASSWORD=your_password_here
```

### Gmail API Configuration

See `OAUTH_SETUP_GUIDE.md` for detailed Gmail API setup instructions.

## 🐛 Troubleshooting

### Gmail API Issues

- **"credentials.json not found"**: Download OAuth credentials from Google Cloud Console
- **"Error 403: access_denied"**: Add your email as a test user in OAuth consent screen
- **"Refresh token expired"**: Delete `token.json` and re-authenticate

See `OAUTH_SETUP_GUIDE.md` for detailed troubleshooting.

### Bot Issues

- **CAPTCHA solving fails**: Check your 2Captcha API key and account balance
- **OTP not found**: Make sure Gmail API is working and emails are being received
- **ChromeDriver errors**: ChromeDriver is auto-downloaded, but ensure Chrome browser is installed

### Web Interface Issues

- **Port already in use**: Change the port in `app.py` (default: 5000)
- **File upload fails**: Check file size (max 16MB) and format (.xlsx or .xls)
- **WebSocket connection issues**: Check firewall settings and browser console

## 🔒 Security Notes

- **Never commit** `credentials.json`, `token.json`, or `.env` to version control
- These files are automatically excluded via `.gitignore`
- The web interface is **not password protected** by default
- For production use, consider adding authentication
- Don't expose the web interface to the public internet without proper security

## 📚 Additional Documentation

- `QUICK_START.md` - Quick start guide for web interface
- `WEB_UI_README.md` - Detailed web interface documentation
- `OAUTH_SETUP_GUIDE.md` - Gmail API OAuth setup guide
- `OTP_LOGIC_ANALYSIS.md` - OTP handling logic documentation

## 🌐 Network Access

The web interface runs on `0.0.0.0:5000` by default, which means:

- **Local access**: `http://localhost:5000` or `http://127.0.0.1:5000`
- **Network access**: `http://YOUR_IP_ADDRESS:5000`

To find your IP address:
- **macOS/Linux**: Run `ifconfig` or `ip addr`
- **Windows**: Run `ipconfig`

## 🖥️ Platform Support

- ✅ Windows
- ✅ macOS
- ✅ Linux

Chrome browser is required for Selenium automation. ChromeDriver is automatically downloaded.

## 📝 API Endpoints

The web interface provides REST API endpoints:

- `GET /api/status` - Get current bot status
- `POST /api/start` - Start the bot (requires Excel file)
- `POST /api/stop` - Stop the bot
- `GET /api/logs` - Get recent logs
- `POST /api/clear-logs` - Clear logs

## 🔄 Real-time Updates

The interface uses WebSocket (Socket.IO) for real-time updates:
- Status changes
- New log entries
- Progress updates
- Error notifications

## 💡 Tips

1. **Keep the browser tab open** to receive real-time updates
2. **Check the logs** if something goes wrong
3. **Use the stop button** if you need to pause the bot
4. **Clear logs** periodically to improve performance with many entries
5. **Test with one account first** before processing large batches

## 📄 License

This project is for educational purposes only. Use responsibly and in accordance with the terms of service of the websites you interact with.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## ⚠️ Disclaimer

This bot is for educational purposes only. Users are responsible for ensuring their use complies with:
- Pokemon Center Online's terms of service
- Google's API terms of service
- 2Captcha's terms of service
- Applicable laws and regulations

Use at your own risk.

---**Made with ❤️ for Pokemon fans**
