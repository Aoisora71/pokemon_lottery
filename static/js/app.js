// Initialize Socket.IO
const socket = io();

// DOM Elements
const botForm = document.getElementById('botForm');
const startBtn = document.getElementById('startBtn');
const stopBtn = document.getElementById('stopBtn');
const spreadsheetIdInput = document.getElementById('spreadsheetId');
const worksheetNameInput = document.getElementById('worksheetName');
const spreadsheetStatus = document.getElementById('spreadsheetStatus');
const statusIndicator = document.getElementById('statusIndicator');
const statusDot = document.getElementById('statusDot');
const statusText = document.getElementById('statusText');
const currentEmail = document.getElementById('currentEmail');
const currentStep = document.getElementById('currentStep');
const progressFill = document.getElementById('progressFill');
const progressPercentage = document.getElementById('progressPercentage');
const errorsSection = document.getElementById('errorsSection');
const errorsContainer = document.getElementById('errorsContainer');
const loadingOverlay = document.getElementById('loadingOverlay');

// State
let isRunning = false;
let restartCountdownInterval = null;

// Spreadsheet ID input handler - check access on blur
spreadsheetIdInput.addEventListener('blur', async () => {
    const spreadsheetId = spreadsheetIdInput.value.trim();
    if (!spreadsheetId) {
        spreadsheetStatus.textContent = '';
        spreadsheetStatus.style.color = '';
        return;
    }
    
    spreadsheetStatus.textContent = 'Checking access...';
    spreadsheetStatus.style.color = '#6b7280';
    
    try {
        const response = await fetch('/api/check-spreadsheet', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                spreadsheet_id: spreadsheetId,
                worksheet_name: worksheetNameInput.value.trim() || null
            })
        });
        
        const data = await response.json();
        if (data.success) {
            spreadsheetStatus.textContent = '✓ Spreadsheet accessible';
            spreadsheetStatus.style.color = '#10b981';
        } else {
            spreadsheetStatus.textContent = '✗ ' + (data.message || 'Cannot access spreadsheet');
            spreadsheetStatus.style.color = '#ef4444';
        }
    } catch (error) {
        spreadsheetStatus.textContent = '✗ Error checking access';
        spreadsheetStatus.style.color = '#ef4444';
    }
});

// Restart mode toggle handler
restartModeMinutes.addEventListener('change', () => {
    if (restartModeMinutes.checked) {
        restartMinutesGroup.style.display = 'block';
        restartDatetimeGroup.style.display = 'none';
        restartMinutes.required = true;
        restartDatetime.required = false;
    }
});

restartModeDatetime.addEventListener('change', () => {
    if (restartModeDatetime.checked) {
        restartMinutesGroup.style.display = 'none';
        restartDatetimeGroup.style.display = 'block';
        restartMinutes.required = false;
        restartDatetime.required = true;
    }
});

// Form submission
botForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    if (isRunning) {
        return;
    }
    
    const formData = new FormData(botForm);
    const spreadsheetId = spreadsheetIdInput.value.trim();
    
    if (!spreadsheetId) {
        showNotification('Please enter a Google Spreadsheet ID or URL', 'error');
        return;
    }
    
    formData.append('spreadsheet_id', spreadsheetId);
    
    const worksheetName = worksheetNameInput.value.trim();
    if (worksheetName) {
        formData.append('worksheet_name', worksheetName);
    }
    
    // Get restart mode and validate
    const restartMode = document.querySelector('input[name="restart_mode"]:checked').value;
    formData.append('restart_mode', restartMode);
    
    if (restartMode === 'minutes') {
        const minutes = parseInt(restartMinutes.value);
        if (!minutes || minutes < 1) {
            showNotification('Please enter a valid number of minutes (at least 1)', 'error');
            return;
        }
        formData.append('restart_minutes', minutes);
    } else if (restartMode === 'datetime') {
        const datetime = restartDatetime.value;
        if (!datetime) {
            showNotification('Please select a date and time for restart', 'error');
            return;
        }
        // Validate that datetime is in the future
        const selectedDate = new Date(datetime);
        const now = new Date();
        if (selectedDate <= now) {
            showNotification('Please select a future date and time', 'error');
            return;
        }
        formData.append('restart_datetime', datetime);
    }
    
    try {
        loadingOverlay.style.display = 'flex';
        const response = await fetch('/api/start', {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (data.success) {
            showNotification('Bot started successfully!', 'success');
            isRunning = true;
            updateUI();
        } else {
            showNotification(data.message || 'Failed to start bot', 'error');
        }
    } catch (error) {
        showNotification('Error starting bot: ' + error.message, 'error');
    } finally {
        loadingOverlay.style.display = 'none';
    }
});

// Stop button
stopBtn.addEventListener('click', async () => {
    try {
        const response = await fetch('/api/stop', {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (data.success) {
            showNotification('Stop request sent', 'warning');
        } else {
            showNotification(data.message || 'Failed to stop bot', 'error');
        }
    } catch (error) {
        showNotification('Error stopping bot: ' + error.message, 'error');
    }
});

// Socket.IO event handlers
socket.on('connect', () => {
    console.log('Connected to server');
    fetchStatus();
});

socket.on('disconnect', () => {
    console.log('Disconnected from server');
});

socket.on('status_update', (status) => {
    updateStatus(status);
});

// Functions
async function fetchStatus() {
    try {
        const response = await fetch('/api/status');
        const status = await response.json();
        updateStatus(status);
    } catch (error) {
        console.error('Error fetching status:', error);
    }
}

function updateStatus(status) {
    isRunning = status.running;
    
    // Update status indicator
    statusDot.className = 'status-dot';
    if (status.running) {
        statusDot.classList.add('running');
        statusText.textContent = 'Running';
    } else {
        statusText.textContent = 'Idle';
    }
    
    // Update progress statistics
    const totalEmails = status.total_emails || 0;
    const processedEmails = status.processed_emails || 0;
    const successCount = status.success_count || 0;
    const failedCount = status.failed_count || 0;
    // Update progress display elements
    document.getElementById('totalEmails').textContent = totalEmails;
    document.getElementById('processedEmails').textContent = `${processedEmails} / ${totalEmails}`;
    document.getElementById('successCount').textContent = successCount;
    document.getElementById('failedCount').textContent = failedCount;
    
    currentEmail.textContent = status.current_email || '-';
    currentStep.textContent = status.current_step || 'Idle';
    
    // Update scheduled restart time
    const scheduledRestartItem = document.getElementById('scheduledRestartItem');
    const scheduledRestart = document.getElementById('scheduledRestart');
    
    // Clear existing countdown interval
    if (restartCountdownInterval) {
        clearInterval(restartCountdownInterval);
        restartCountdownInterval = null;
    }
    
    if (status.scheduled_restart_time) {
        scheduledRestartItem.style.display = 'block';
        
        // Store restart time in data attribute for countdown function
        scheduledRestart.setAttribute('data-restart-time', status.scheduled_restart_time);
        
        // Function to update countdown
        const updateCountdown = () => {
            try {
                const restartTimeStr = scheduledRestart.getAttribute('data-restart-time');
                if (!restartTimeStr) {
                    if (restartCountdownInterval) {
                        clearInterval(restartCountdownInterval);
                        restartCountdownInterval = null;
                    }
                    return;
                }
                
                const restartTime = new Date(restartTimeStr);
                const now = new Date();
                const diffMs = restartTime - now;
                
                if (diffMs <= 0) {
                    scheduledRestart.textContent = '再試行中...';
                    if (restartCountdownInterval) {
                        clearInterval(restartCountdownInterval);
                        restartCountdownInterval = null;
                    }
                    return;
                }
                
                // Calculate hours, minutes, and seconds
                const totalSeconds = Math.floor(diffMs / 1000);
                const hours = Math.floor(totalSeconds / 3600);
                const minutes = Math.floor((totalSeconds % 3600) / 60);
                const seconds = totalSeconds % 60;
                
                // Format as "残りX時Y分Z秒後" (only show non-zero values)
                let timeString = '残り';
                if (hours > 0) {
                    timeString += `${hours}時`;
                }
                if (minutes > 0) {
                    timeString += `${minutes}分`;
                }
                timeString += `${seconds}秒後`;
                
                scheduledRestart.textContent = timeString;
            } catch (e) {
                console.error('Error calculating countdown:', e);
                scheduledRestart.textContent = status.scheduled_restart_message || '再試行予定';
            }
        };
        
        // Update immediately
        updateCountdown();
        
        // Update every second
        restartCountdownInterval = setInterval(updateCountdown, 1000);
    } else {
        scheduledRestartItem.style.display = 'none';
        scheduledRestart.removeAttribute('data-restart-time');
    }
    
    // Update progress bar (based on processed emails out of total emails)
    const percentage = totalEmails > 0 ? (processedEmails / totalEmails) * 100 : 0;
    progressFill.style.width = `${percentage}%`;
    progressPercentage.textContent = `${Math.round(percentage)}%`;
    
    // Update errors
    if (status.errors && status.errors.length > 0) {
        errorsSection.style.display = 'block';
        errorsContainer.innerHTML = status.errors.map(error => `
            <div class="error-item">
                <div class="error-email">${error.email}</div>
                <div class="error-message">${error.error}</div>
            </div>
        `).join('');
    } else {
        errorsSection.style.display = 'none';
    }
    
    // Update UI
    updateUI();
}

function updateUI() {
    startBtn.disabled = isRunning;
    stopBtn.disabled = !isRunning;
    
    if (isRunning) {
        startBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Running...';
    } else {
        startBtn.innerHTML = '<i class="fas fa-play"></i> Start Bot';
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showNotification(message, type = 'info') {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 16px 24px;
        background: ${type === 'success' ? 'var(--success-color)' : type === 'error' ? 'var(--error-color)' : 'var(--primary-color)'};
        color: white;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        z-index: 10000;
        animation: slideInRight 0.3s ease;
    `;
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.style.animation = 'slideOutRight 0.3s ease';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// Add CSS animations
const style = document.createElement('style');
style.textContent = `
    @keyframes slideInRight {
        from {
            transform: translateX(100%);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
    
    @keyframes slideOutRight {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(100%);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);

// Initial status fetch
fetchStatus();

// Poll for status updates every 2 seconds (fallback)
setInterval(fetchStatus, 2000);

