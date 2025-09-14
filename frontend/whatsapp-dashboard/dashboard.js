/**
 * WhatsApp Integration Dashboard - Real-time Monitoring & Management
 * AI Agency Platform - Premium EA Services
 */

class WhatsAppDashboard {
    constructor() {
        this.config = {
            webhookServiceUrl: process.env.WEBHOOK_SERVICE_URL || 'https://your-webhook-service.ondigitalocean.app',
            customerId: this.getCustomerId(),
            refreshInterval: 30000 // 30 seconds
        };

        this.state = {
            connectionData: null,
            metrics: null,
            activities: [],
            isLoading: false,
            refreshTimer: null
        };

        this.charts = {
            messageVolume: null,
            responseTime: null
        };

        this.initialize();
    }

    /**
     * Initialize dashboard
     */
    async initialize() {
        this.bindEvents();
        this.showLoading('Loading your WhatsApp integration data...');

        try {
            await this.loadDashboardData();
            this.initializeCharts();
            this.startPeriodicRefresh();
            this.hideLoading();
        } catch (error) {
            console.error('Failed to initialize dashboard:', error);
            this.hideLoading();
            this.showError('Failed to load dashboard data');
        }
    }

    /**
     * Bind event listeners
     */
    bindEvents() {
        // Refresh button
        document.getElementById('refreshButton')?.addEventListener('click', () => {
            this.refreshDashboard();
        });

        // Quick actions
        document.getElementById('sendTestMessage')?.addEventListener('click', () => {
            this.openTestMessageModal();
        });

        document.getElementById('configureEA')?.addEventListener('click', () => {
            this.navigateToEAConfig();
        });

        document.getElementById('viewWorkflows')?.addEventListener('click', () => {
            this.navigateToWorkflows();
        });

        document.getElementById('downloadReports')?.addEventListener('click', () => {
            this.downloadReports();
        });

        // Test connection
        document.getElementById('testConnectionButton')?.addEventListener('click', () => {
            this.testWhatsAppConnection();
        });

        // Manage account
        document.getElementById('manageAccountButton')?.addEventListener('click', () => {
            this.manageWhatsAppAccount();
        });

        // View all activity
        document.getElementById('viewAllActivity')?.addEventListener('click', () => {
            this.viewAllActivity();
        });

        // Chart period selectors
        document.getElementById('volumePeriod')?.addEventListener('change', (e) => {
            this.updateMessageVolumeChart(e.target.value);
        });

        document.getElementById('responsePeriod')?.addEventListener('change', (e) => {
            this.updateResponseTimeChart(e.target.value);
        });

        // Test message modal
        document.getElementById('closeTestModal')?.addEventListener('click', () => {
            this.closeTestMessageModal();
        });

        document.getElementById('cancelTest')?.addEventListener('click', () => {
            this.closeTestMessageModal();
        });

        document.getElementById('sendTest')?.addEventListener('click', () => {
            this.sendTestMessage();
        });

        // Close modal on outside click
        document.getElementById('testMessageModal')?.addEventListener('click', (e) => {
            if (e.target.classList.contains('modal')) {
                this.closeTestMessageModal();
            }
        });
    }

    /**
     * Load dashboard data
     */
    async loadDashboardData() {
        const [connectionData, metrics, activities] = await Promise.all([
            this.fetchConnectionData(),
            this.fetchMetrics(),
            this.fetchRecentActivities()
        ]);

        this.state.connectionData = connectionData;
        this.state.metrics = metrics;
        this.state.activities = activities;

        this.updateConnectionInfo(connectionData);
        this.updateMetrics(metrics);
        this.updateActivities(activities);
        this.updateConnectionStatus(connectionData.status);
    }

    /**
     * Fetch connection data
     */
    async fetchConnectionData() {
        const response = await fetch(`${this.config.webhookServiceUrl}/api/ea/connection/${this.config.customerId}`, {
            headers: {
                'Authorization': `Bearer ${this.getAuthToken()}`
            }
        });

        if (!response.ok) {
            throw new Error('Failed to fetch connection data');
        }

        return await response.json();
    }

    /**
     * Fetch metrics
     */
    async fetchMetrics() {
        const response = await fetch(`${this.config.webhookServiceUrl}/api/ea/metrics/${this.config.customerId}`, {
            headers: {
                'Authorization': `Bearer ${this.getAuthToken()}`
            }
        });

        if (!response.ok) {
            throw new Error('Failed to fetch metrics');
        }

        return await response.json();
    }

    /**
     * Fetch recent activities
     */
    async fetchRecentActivities() {
        const response = await fetch(`${this.config.webhookServiceUrl}/api/ea/activities/${this.config.customerId}?limit=10`, {
            headers: {
                'Authorization': `Bearer ${this.getAuthToken()}`
            }
        });

        if (!response.ok) {
            throw new Error('Failed to fetch activities');
        }

        return await response.json();
    }

    /**
     * Update connection information
     */
    updateConnectionInfo(data) {
        document.getElementById('clientName').textContent = data.client_name || 'Premium EA Client';
        document.getElementById('phoneNumber').textContent = data.phone_number || '+1 (555) 123-4567';
        document.getElementById('wabaId').textContent = data.waba_id || '123456789012345';
        document.getElementById('businessId').textContent = data.business_id || '987654321098765';

        const connectedDate = data.connected_since ?
            new Date(data.connected_since).toLocaleDateString('en-US', {
                year: 'numeric',
                month: 'short',
                day: 'numeric'
            }) : 'Jan 15, 2024';

        document.getElementById('connectedSince').textContent = connectedDate;
    }

    /**
     * Update metrics display
     */
    updateMetrics(data) {
        const formatNumber = (num) => num.toLocaleString();
        const formatTime = (seconds) => `${seconds.toFixed(1)}s`;
        const formatRating = (rating) => `${rating.toFixed(1)}/5.0`;
        const formatChange = (change, type) => {
            const prefix = change >= 0 ? '+' : '';
            const suffix = type === 'percentage' ? '%' : type === 'time' ? 's' : '';
            return `${prefix}${change}${suffix}`;
        };

        // Update metric values
        document.getElementById('totalMessages').textContent =
            formatNumber(data.total_messages || 1247);

        document.getElementById('responseTime').textContent =
            formatTime(data.avg_response_time || 1.2);

        document.getElementById('workflowsCreated').textContent =
            formatNumber(data.workflows_created || 23);

        document.getElementById('satisfactionScore').textContent =
            formatRating(data.satisfaction_score || 4.8);

        // Update metric changes (you would calculate these from historical data)
        this.updateMetricChanges(data);
    }

    /**
     * Update metric change indicators
     */
    updateMetricChanges(data) {
        // In a real implementation, these would be calculated from historical data
        const changes = [
            { selector: '.metric-change', text: '+18% from last week', positive: true },
            { selector: '.metric-change:nth-child(2)', text: '-0.3s faster', positive: true },
            { selector: '.metric-change:nth-child(3)', text: '+4 new automations', positive: true },
            { selector: '.metric-change:nth-child(4)', text: '+0.2 improvement', positive: true }
        ];

        // This would be implemented with more sophisticated change tracking
    }

    /**
     * Update connection status
     */
    updateConnectionStatus(status) {
        const statusElement = document.getElementById('connectionStatus');
        const indicator = statusElement.querySelector('.status-indicator');
        const text = statusElement.querySelector('span');

        indicator.classList.remove('active', 'error', 'warning');

        switch (status) {
            case 'connected':
                indicator.classList.add('active');
                text.textContent = 'Connected';
                statusElement.className = 'connection-status';
                break;
            case 'disconnected':
                indicator.classList.add('error');
                text.textContent = 'Disconnected';
                statusElement.className = 'connection-status error';
                break;
            case 'warning':
                indicator.classList.add('warning');
                text.textContent = 'Issues Detected';
                statusElement.className = 'connection-status warning';
                break;
            default:
                indicator.classList.add('active');
                text.textContent = 'Connected';
                statusElement.className = 'connection-status';
        }
    }

    /**
     * Update activities list
     */
    updateActivities(activities) {
        const activityList = document.getElementById('activityList');

        // Clear existing activities (except sample ones for demo)
        // In production, this would replace all activities

        if (activities && activities.length > 0) {
            // Add real activities from API
            activities.forEach(activity => {
                const activityElement = this.createActivityElement(activity);
                activityList.appendChild(activityElement);
            });
        }
    }

    /**
     * Create activity element
     */
    createActivityElement(activity) {
        const div = document.createElement('div');
        div.className = 'activity-item';

        const iconClass = this.getActivityIconClass(activity.type);
        const statusClass = this.getActivityStatusClass(activity.status);
        const timeAgo = this.formatTimeAgo(activity.timestamp);

        div.innerHTML = `
            <div class="activity-icon ${iconClass}">
                ${this.getActivityIconSVG(activity.type)}
            </div>
            <div class="activity-content">
                <div class="activity-text">
                    <strong>${activity.title}</strong> ${activity.description}
                </div>
                <div class="activity-time">${timeAgo}</div>
            </div>
            <div class="activity-status ${statusClass}">${activity.status}</div>
        `;

        return div;
    }

    /**
     * Get activity icon class
     */
    getActivityIconClass(type) {
        const iconMap = {
            'message': 'message',
            'workflow': 'workflow',
            'response': 'response',
            'system': 'system'
        };
        return iconMap[type] || 'system';
    }

    /**
     * Get activity status class
     */
    getActivityStatusClass(status) {
        const statusMap = {
            'completed': 'success',
            'processed': 'success',
            'delivered': 'success',
            'active': 'success',
            'healthy': 'success',
            'failed': 'error',
            'error': 'error',
            'pending': 'pending'
        };
        return statusMap[status.toLowerCase()] || 'pending';
    }

    /**
     * Get activity icon SVG
     */
    getActivityIconSVG(type) {
        const icons = {
            'message': '<path d="M21 15C21 15.5304 20.7893 16.0391 20.4142 16.4142C20.0391 16.7893 19.5304 17 19 17H7L3 21V5C3 4.46957 3.21071 3.96086 3.58579 3.58579C3.96086 3.21071 4.46957 3 5 3H19C19.5304 3 20.0391 3.21071 20.4142 3.58579C20.7893 3.96086 21 4.46957 21 5V15Z" stroke="currentColor" stroke-width="2"/>',
            'workflow': '<path d="M13 10V3L4 14H11L11 21L20 10H13Z" stroke="currentColor" stroke-width="2"/>',
            'response': '<path d="M8 12H16M8 8H16M8 16H12M6 20H18C19.1046 20 20 19.1046 20 18V6C20 4.89543 19.1046 4 18 4H6C4.89543 4 4 4.89543 4 6V18C4 19.1046 4.89543 20 6 20Z" stroke="currentColor" stroke-width="2"/>',
            'system': '<circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="2"/><path d="M12 1V3M12 21V23M4.22 4.22L5.64 5.64M18.36 18.36L19.78 19.78M1 12H3M21 12H23M4.22 19.78L5.64 18.36M18.36 5.64L19.78 4.22" stroke="currentColor" stroke-width="2"/>'
        };

        return `<svg width="16" height="16" viewBox="0 0 24 24" fill="none">${icons[type] || icons['system']}</svg>`;
    }

    /**
     * Format time ago
     */
    formatTimeAgo(timestamp) {
        const now = Date.now();
        const diff = now - new Date(timestamp).getTime();
        const minutes = Math.floor(diff / 60000);
        const hours = Math.floor(diff / 3600000);
        const days = Math.floor(diff / 86400000);

        if (days > 0) return `${days} day${days > 1 ? 's' : ''} ago`;
        if (hours > 0) return `${hours} hour${hours > 1 ? 's' : ''} ago`;
        if (minutes > 0) return `${minutes} minute${minutes > 1 ? 's' : ''} ago`;
        return 'Just now';
    }

    /**
     * Initialize charts
     */
    initializeCharts() {
        this.initializeMessageVolumeChart();
        this.initializeResponseTimeChart();
    }

    /**
     * Initialize message volume chart
     */
    initializeMessageVolumeChart() {
        const ctx = document.getElementById('messageVolumeChart');
        if (!ctx) return;

        this.charts.messageVolume = new Chart(ctx, {
            type: 'line',
            data: {
                labels: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
                datasets: [{
                    label: 'Messages',
                    data: [120, 190, 160, 220, 180, 150, 200],
                    borderColor: '#25D366',
                    backgroundColor: '#25D36620',
                    fill: true,
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        grid: {
                            color: '#E5E7EB'
                        }
                    },
                    x: {
                        grid: {
                            display: false
                        }
                    }
                }
            }
        });
    }

    /**
     * Initialize response time chart
     */
    initializeResponseTimeChart() {
        const ctx = document.getElementById('responseTimeChart');
        if (!ctx) return;

        this.charts.responseTime = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
                datasets: [{
                    label: 'Response Time (s)',
                    data: [1.2, 0.9, 1.1, 1.0, 1.3, 0.8, 1.2],
                    backgroundColor: '#6366F1',
                    borderRadius: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        grid: {
                            color: '#E5E7EB'
                        }
                    },
                    x: {
                        grid: {
                            display: false
                        }
                    }
                }
            }
        });
    }

    /**
     * Update message volume chart
     */
    async updateMessageVolumeChart(period) {
        if (!this.charts.messageVolume) return;

        // Fetch new data based on period
        try {
            const data = await this.fetchChartData('message-volume', period);
            this.charts.messageVolume.data.labels = data.labels;
            this.charts.messageVolume.data.datasets[0].data = data.values;
            this.charts.messageVolume.update();
        } catch (error) {
            console.error('Failed to update message volume chart:', error);
        }
    }

    /**
     * Update response time chart
     */
    async updateResponseTimeChart(period) {
        if (!this.charts.responseTime) return;

        try {
            const data = await this.fetchChartData('response-time', period);
            this.charts.responseTime.data.labels = data.labels;
            this.charts.responseTime.data.datasets[0].data = data.values;
            this.charts.responseTime.update();
        } catch (error) {
            console.error('Failed to update response time chart:', error);
        }
    }

    /**
     * Fetch chart data
     */
    async fetchChartData(type, period) {
        const response = await fetch(`${this.config.webhookServiceUrl}/api/ea/charts/${this.config.customerId}/${type}?period=${period}`, {
            headers: {
                'Authorization': `Bearer ${this.getAuthToken()}`
            }
        });

        if (!response.ok) {
            throw new Error(`Failed to fetch ${type} chart data`);
        }

        return await response.json();
    }

    /**
     * Refresh dashboard
     */
    async refreshDashboard() {
        this.showLoading('Refreshing dashboard data...');

        try {
            await this.loadDashboardData();
            this.hideLoading();

            // Animate refresh button
            const refreshButton = document.getElementById('refreshButton');
            refreshButton.style.transform = 'rotate(180deg)';
            setTimeout(() => {
                refreshButton.style.transform = 'rotate(0deg)';
            }, 300);

        } catch (error) {
            console.error('Failed to refresh dashboard:', error);
            this.hideLoading();
            this.showError('Failed to refresh data');
        }
    }

    /**
     * Start periodic refresh
     */
    startPeriodicRefresh() {
        this.state.refreshTimer = setInterval(() => {
            this.refreshDashboard();
        }, this.config.refreshInterval);
    }

    /**
     * Stop periodic refresh
     */
    stopPeriodicRefresh() {
        if (this.state.refreshTimer) {
            clearInterval(this.state.refreshTimer);
            this.state.refreshTimer = null;
        }
    }

    /**
     * Test WhatsApp connection
     */
    async testWhatsAppConnection() {
        this.showLoading('Testing WhatsApp connection...');

        try {
            const response = await fetch(`${this.config.webhookServiceUrl}/api/ea/test`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.getAuthToken()}`
                },
                body: JSON.stringify({
                    customer_id: this.config.customerId,
                    phone_number: this.state.connectionData.phone_number
                })
            });

            this.hideLoading();

            if (response.ok) {
                const result = await response.json();
                this.showSuccess(`✅ Test message sent successfully! Message ID: ${result.message_id}`);
            } else {
                const error = await response.json();
                this.showError(`❌ Test failed: ${error.message}`);
            }

        } catch (error) {
            this.hideLoading();
            console.error('Test connection failed:', error);
            this.showError(`❌ Test failed: ${error.message}`);
        }
    }

    /**
     * Manage WhatsApp account
     */
    manageWhatsAppAccount() {
        // Navigate to WhatsApp Business Manager or account settings
        const wabaId = this.state.connectionData?.waba_id;
        if (wabaId) {
            window.open(`https://business.facebook.com/wa/manage/phone-numbers/?waba_id=${wabaId}`, '_blank');
        } else {
            window.open('https://business.facebook.com/', '_blank');
        }
    }

    /**
     * Open test message modal
     */
    openTestMessageModal() {
        const modal = document.getElementById('testMessageModal');
        const phoneInput = document.getElementById('testPhoneNumber');
        const messageTextarea = document.getElementById('testMessage');

        // Pre-fill with business phone number
        phoneInput.value = this.state.connectionData?.phone_number || '';
        messageTextarea.value = 'Hi EA, please tell me about my business performance this week';

        modal.classList.add('active');
        phoneInput.focus();
    }

    /**
     * Close test message modal
     */
    closeTestMessageModal() {
        const modal = document.getElementById('testMessageModal');
        modal.classList.remove('active');
    }

    /**
     * Send test message
     */
    async sendTestMessage() {
        const phoneNumber = document.getElementById('testPhoneNumber').value;
        const message = document.getElementById('testMessage').value;

        if (!phoneNumber || !message) {
            this.showError('Please fill in both phone number and message');
            return;
        }

        this.closeTestMessageModal();
        this.showLoading('Sending test message...');

        try {
            const response = await fetch(`${this.config.webhookServiceUrl}/api/ea/test-message`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.getAuthToken()}`
                },
                body: JSON.stringify({
                    customer_id: this.config.customerId,
                    phone_number: phoneNumber,
                    message: message
                })
            });

            this.hideLoading();

            if (response.ok) {
                const result = await response.json();
                this.showSuccess(`✅ Test message sent! Check ${phoneNumber} for EA response.`);
            } else {
                const error = await response.json();
                this.showError(`❌ Failed to send test: ${error.message}`);
            }

        } catch (error) {
            this.hideLoading();
            console.error('Failed to send test message:', error);
            this.showError(`❌ Test failed: ${error.message}`);
        }
    }

    /**
     * Navigate to EA configuration
     */
    navigateToEAConfig() {
        window.location.href = '/ea/config';
    }

    /**
     * Navigate to workflows
     */
    navigateToWorkflows() {
        window.location.href = '/workflows';
    }

    /**
     * Download reports
     */
    async downloadReports() {
        this.showLoading('Generating reports...');

        try {
            const response = await fetch(`${this.config.webhookServiceUrl}/api/ea/reports/${this.config.customerId}`, {
                headers: {
                    'Authorization': `Bearer ${this.getAuthToken()}`
                }
            });

            if (response.ok) {
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `whatsapp-ea-report-${this.config.customerId}-${new Date().toISOString().split('T')[0]}.pdf`;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);

                this.hideLoading();
                this.showSuccess('✅ Report downloaded successfully!');
            } else {
                this.hideLoading();
                this.showError('❌ Failed to generate report');
            }

        } catch (error) {
            this.hideLoading();
            console.error('Failed to download reports:', error);
            this.showError(`❌ Download failed: ${error.message}`);
        }
    }

    /**
     * View all activity
     */
    viewAllActivity() {
        window.location.href = '/activity';
    }

    /**
     * Show loading overlay
     */
    showLoading(message) {
        const overlay = document.getElementById('loadingOverlay');
        const text = overlay.querySelector('p');

        text.textContent = message;
        overlay.classList.add('active');
        this.state.isLoading = true;
    }

    /**
     * Hide loading overlay
     */
    hideLoading() {
        const overlay = document.getElementById('loadingOverlay');
        overlay.classList.remove('active');
        this.state.isLoading = false;
    }

    /**
     * Show success message
     */
    showSuccess(message) {
        // In a real implementation, this would show a toast notification
        alert(message);
    }

    /**
     * Show error message
     */
    showError(message) {
        // In a real implementation, this would show a toast notification
        console.error(message);
        alert(message);
    }

    /**
     * Get customer ID
     */
    getCustomerId() {
        const urlParams = new URLSearchParams(window.location.search);
        return urlParams.get('customer_id') ||
               localStorage.getItem('customer_id') ||
               'demo-customer-123';
    }

    /**
     * Get auth token
     */
    getAuthToken() {
        return localStorage.getItem('auth_token') ||
               sessionStorage.getItem('auth_token') ||
               'demo-auth-token';
    }

    /**
     * Destroy dashboard (cleanup)
     */
    destroy() {
        this.stopPeriodicRefresh();

        if (this.charts.messageVolume) {
            this.charts.messageVolume.destroy();
        }

        if (this.charts.responseTime) {
            this.charts.responseTime.destroy();
        }
    }
}

// Initialize dashboard when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.whatsappDashboard = new WhatsAppDashboard();
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (window.whatsappDashboard) {
        window.whatsappDashboard.destroy();
    }
});

// Export for testing
if (typeof module !== 'undefined' && module.exports) {
    module.exports = WhatsAppDashboard;
}