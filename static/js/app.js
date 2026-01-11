// Initialize Socket.IO
const socket = io();

// DOM Elements
const botForm = document.getElementById('botForm');
const startBtn = document.getElementById('startBtn');
const stopBtn = document.getElementById('stopBtn');
const excelFileInput = document.getElementById('excelFile');
const fileName = document.getElementById('fileName');
const logsContainer = document.getElementById('logsContainer');
const clearLogsBtn = document.getElementById('clearLogsBtn');
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

// File input handler
excelFileInput.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (file) {
        fileName.textContent = file.name;
        fileName.style.color = 'var(--text-primary)';
    } else {
        fileName.textContent = 'Choose Excel file (.xlsx or .xls)';
        fileName.style.color = 'var(--text-secondary)';
    }
});

// Form submission
botForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    if (isRunning) {
        return;
    }
    
    const formData = new FormData(botForm);
    const file = excelFileInput.files[0];
    
    if (!file) {
        showNotification('Please select an Excel file', 'error');
        return;
    }
    
    formData.append('file', file);
    
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

// Clear logs
clearLogsBtn.addEventListener('click', async () => {
    try {
        await fetch('/api/clear-logs', { method: 'POST' });
        logsContainer.innerHTML = '<div class="log-empty"><i class="fas fa-inbox"></i><p>No logs yet. Start the bot to see activity.</p></div>';
    } catch (error) {
        showNotification('Error clearing logs: ' + error.message, 'error');
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

socket.on('log', (logEntry) => {
    addLog(logEntry);
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
    const skippedCount = status.skipped_count || 0;
    
    // Update progress display elements
    document.getElementById('totalEmails').textContent = totalEmails;
    document.getElementById('processedEmails').textContent = `${processedEmails} / ${totalEmails}`;
    document.getElementById('successCount').textContent = successCount;
    document.getElementById('failedCount').textContent = failedCount;
    document.getElementById('skippedCount').textContent = skippedCount;
    
    currentEmail.textContent = status.current_email || '-';
    currentStep.textContent = status.current_step || 'Idle';
    
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

// Track seen logs to prevent duplicates
const seenLogIds = new Set();

function addLog(logEntry) {
    // Use unique ID if available, otherwise fall back to timestamp + message
    const logKey = logEntry.id ? `id-${logEntry.id}` : `${logEntry.timestamp}-${logEntry.message}`;
    
    // Skip if we've already seen this log
    if (seenLogIds.has(logKey)) {
        return;
    }
    
    // Mark as seen
    seenLogIds.add(logKey);
    
    // Keep only last 1000 seen log IDs to prevent memory issues
    if (seenLogIds.size > 1000) {
        const firstKey = seenLogIds.values().next().value;
        seenLogIds.delete(firstKey);
    }
    
    // Remove empty state if exists
    const emptyState = logsContainer.querySelector('.log-empty');
    if (emptyState) {
        emptyState.remove();
    }
    
    const logElement = document.createElement('div');
    logElement.className = `log-entry ${logEntry.level}`;
    
    const timestamp = new Date(logEntry.timestamp).toLocaleTimeString();
    
    logElement.innerHTML = `
        <span class="log-timestamp">[${timestamp}]</span>
        <span class="log-message">${escapeHtml(logEntry.message)}</span>
    `;
    
    logsContainer.appendChild(logElement);
    
    // Auto-scroll to bottom
    logsContainer.scrollTop = logsContainer.scrollHeight;
    
    // Keep only last 500 logs in DOM
    const logs = logsContainer.querySelectorAll('.log-entry');
    if (logs.length > 500) {
        logs[0].remove();
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

