# Pokemon Center Lottery Bot - Web Interface

A beautiful, modern web interface for the Pokemon Center Lottery Bot that works on Windows, macOS, and Linux.

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the Web Interface

```bash
python run.py
```

Or directly:

```bash
python app.py
```

### 3. Open in Browser

Open your web browser and navigate to:

```
http://localhost:5000
```

## 📋 Features

### ✨ Modern UI/UX
- **Dark Theme**: Beautiful dark mode interface
- **Real-time Updates**: Live status updates via WebSocket
- **Progress Tracking**: Visual progress bar and statistics
- **Log Viewer**: Real-time log streaming with color coding
- **Error Display**: Dedicated error section for failed operations

### 🎮 Control Panel
- **Excel File Upload**: Drag and drop or click to upload
- **2Captcha API Key**: Enter your API key directly or use .env file
- **Start/Stop Controls**: Easy bot control with visual feedback

### 📊 Dashboard
- **Live Status**: Real-time bot status indicator
- **Progress Tracking**: Current email, progress count, and percentage
- **Activity Logs**: Color-coded logs (info, success, warning, error)
- **Error Management**: View and track errors per email

## 📁 Project Structure

```
.
├── app.py                 # Flask web application
├── run.py                 # Simple launcher script
├── bot.py                 # Bot logic (existing)
├── main.py                # Gmail API (existing)
├── templates/
│   └── index.html         # Main web interface
├── static/
│   ├── css/
│   │   └── style.css      # Modern styling
│   └── js/
│       └── app.js         # Frontend logic
└── uploads/               # Uploaded Excel files (auto-created)
```

## 🔧 Configuration

### Environment Variables

Create a `.env` file (optional if you want to set defaults):

```env
CAPTCHA_API_KEY=your_2captcha_api_key_here
EMAIL=your_email@example.com
PASSWORD=your_password_here
```

**Note**: You can also enter the CAPTCHA API key directly in the web interface.

### Excel File Format

Your Excel file should have:
- **Column A**: Email addresses
- **Column B**: Passwords (optional - if not provided, uses .env PASSWORD)

Example:
```
| Email                    | Password    |
|--------------------------|-------------|
| user1@example.com        | password1   |
| user2@example.com        | password2   |
```

## 🌐 Accessing from Other Devices

The web interface runs on `0.0.0.0:5000` by default, which means:

- **Local access**: `http://localhost:5000` or `http://127.0.0.1:5000`
- **Network access**: `http://YOUR_IP_ADDRESS:5000`

To find your IP address:
- **macOS/Linux**: Run `ifconfig` or `ip addr`
- **Windows**: Run `ipconfig`

## 🖥️ Platform-Specific Notes

### macOS
- Works out of the box
- Chrome/Chromium required for Selenium
- If Chrome is not in default location, you may need to specify the path

### Windows
- Works out of the box
- Chrome browser required

### Linux
- Works out of the box
- May need to install Chrome/Chromium:
  ```bash
  # Ubuntu/Debian
  sudo apt-get install chromium-browser
  
  # Or download Chrome from Google
  ```

## 🔒 Security Notes

- The web interface is **not password protected** by default
- For production use, consider adding authentication
- Don't expose the web interface to the public internet without proper security
- Keep your `.env` file secure and never commit it to version control

## 🐛 Troubleshooting

### Port Already in Use
If port 5000 is already in use, you can change it in `app.py`:

```python
socketio.run(app, host='0.0.0.0', port=5001, ...)  # Change port number
```

### Chrome/ChromeDriver Issues
- Make sure Chrome browser is installed
- ChromeDriver is automatically downloaded by webdriver-manager
- If issues persist, try updating Chrome browser

### File Upload Issues
- Maximum file size: 16MB
- Supported formats: .xlsx, .xls
- Make sure the Excel file is not open in another program

### WebSocket Connection Issues
- Make sure port 5000 is not blocked by firewall
- Check browser console for errors
- Try refreshing the page

## 📱 Mobile Responsive

The web interface is fully responsive and works on:
- Desktop computers
- Tablets
- Mobile phones

## 🎨 Customization

### Changing Colors
Edit `static/css/style.css` and modify the CSS variables:

```css
:root {
    --primary-color: #6366f1;  /* Change this */
    --secondary-color: #8b5cf6; /* Change this */
    /* ... */
}
```

### Changing Port
Edit `app.py` or `run.py`:

```python
socketio.run(app, host='0.0.0.0', port=8080, ...)  # Your port
```

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

## 📄 License

Same as the main project - for educational purposes only.

## 🤝 Support

For issues or questions:
1. Check the logs in the web interface
2. Check the terminal/console output
3. Review the troubleshooting section above

---

**Enjoy using the Pokemon Center Lottery Bot Web Interface! 🎮**

