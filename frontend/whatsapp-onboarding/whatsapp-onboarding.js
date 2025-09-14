/**
 * WhatsApp Business Onboarding - Meta Embedded Signup Integration
 * AI Agency Platform - Premium EA Services
 */

class WhatsAppOnboarding {
    constructor() {
        this.config = {
            facebookAppId: process.env.FACEBOOK_APP_ID || '1234567890123456', // Replace with actual App ID
            configurationId: process.env.WHATSAPP_CONFIG_ID || 'YOUR_CONFIGURATION_ID',
            webhookServiceUrl: process.env.WEBHOOK_SERVICE_URL || 'https://your-webhook-service.ondigitalocean.app',
            redirectUrl: window.location.origin + '/whatsapp-onboarding/success',
            customerId: this.getCustomerId()
        };

        this.state = {
            currentSection: 'welcome-section',
            isProcessing: false,
            connectionData: null,
            errorDetails: null
        };

        this.initializeSDK();
        this.bindEvents();
        this.loadClientInfo();
    }

    /**
     * Initialize Facebook JavaScript SDK for WhatsApp Business
     */
    initializeSDK() {
        window.fbAsyncInit = () => {
            FB.init({
                appId: this.config.facebookAppId,
                autoLogAppEvents: true,
                xfbml: true,
                version: 'v18.0'
            });

            console.log('✅ Facebook SDK initialized for WhatsApp Business integration');
            this.checkSDKStatus();
        };

        // Load SDK asynchronously if not already loaded
        if (!window.FB) {
            const script = document.createElement('script');
            script.async = true;
            script.defer = true;
            script.crossOrigin = 'anonymous';
            script.src = 'https://connect.facebook.net/en_US/sdk.js';
            document.head.appendChild(script);
        }
    }

    /**
     * Check SDK loading status
     */
    checkSDKStatus() {
        if (window.FB) {
            document.getElementById('connectButton').disabled = false;
            console.log('🔗 WhatsApp Business connection ready');
        } else {
            console.error('❌ Facebook SDK failed to load');
            this.showError('SDK_LOAD_FAILED', 'Facebook SDK failed to load. Please refresh and try again.');
        }
    }

    /**
     * Bind event listeners
     */
    bindEvents() {
        // Connect WhatsApp Business Account
        document.getElementById('connectButton')?.addEventListener('click', () => {
            this.initiateWhatsAppConnection();
        });

        // Retry connection
        document.getElementById('retryButton')?.addEventListener('click', () => {
            this.retryConnection();
        });

        document.getElementById('retryConnectionButton')?.addEventListener('click', () => {
            this.retryConnection();
        });

        // Continue to dashboard
        document.getElementById('continueButton')?.addEventListener('click', () => {
            this.continueToDashboard();
        });

        // Test connection
        document.getElementById('testConnectionButton')?.addEventListener('click', () => {
            this.testWhatsAppConnection();
        });

        // Contact support
        document.getElementById('contactSupportButton')?.addEventListener('click', () => {
            this.contactSupport();
        });

        // Handle window message events from popup
        window.addEventListener('message', (event) => {
            this.handlePopupMessage(event);
        });

        // Handle popup blocked detection
        this.setupPopupBlockedDetection();
    }

    /**
     * Load client information
     */
    async loadClientInfo() {
        try {
            // In a real implementation, this would fetch from your backend
            const clientInfo = await this.fetchClientInfo(this.config.customerId);

            document.getElementById('clientName').textContent =
                clientInfo?.name || 'Premium EA Client';

        } catch (error) {
            console.warn('Could not load client info:', error);
            document.getElementById('clientName').textContent = 'EA Client';
        }
    }

    /**
     * Initiate WhatsApp Business connection using Meta Embedded Signup
     */
    async initiateWhatsAppConnection() {
        if (this.state.isProcessing) return;

        this.state.isProcessing = true;
        this.showSection('progress-section');
        this.updateProgress('step-popup', 'active');
        this.updateStatus('Initializing WhatsApp Connection...', 'Opening Meta\'s secure signup flow');

        try {
            // Launch Facebook Login for Business with WhatsApp configuration
            const response = await new Promise((resolve, reject) => {
                FB.login((response) => {
                    if (response.authResponse) {
                        resolve(response);
                    } else {
                        reject(new Error('User cancelled login or did not fully authorize.'));
                    }
                }, {
                    config_id: this.config.configurationId,
                    response_type: 'code',
                    override_default_response_type: true,
                    extras: {
                        setup: {
                            'messenger_welcome_flow': 'enabled',
                            'customer_chat_display_style': 'card'
                        }
                    }
                });
            });

            this.handleSignupResponse(response);

        } catch (error) {
            console.error('WhatsApp connection failed:', error);
            this.handleConnectionError(error);
        }
    }

    /**
     * Handle Meta signup response
     */
    async handleSignupResponse(response) {
        try {
            this.updateProgress('step-popup', 'completed');
            this.updateProgress('step-permissions', 'active');
            this.updateStatus('Processing Permissions...', 'Validating WhatsApp Business access');

            // Extract the code for token exchange (30-second TTL)
            const { code } = response;
            if (!code) {
                throw new Error('No authorization code received from Meta');
            }

            this.updateProgress('step-permissions', 'completed');
            this.updateProgress('step-exchange', 'active');
            this.updateStatus('Exchanging Tokens...', 'Securing your WhatsApp Business integration');

            // Exchange code for business tokens with our backend
            const tokenData = await this.exchangeCodeForTokens(code);

            this.updateProgress('step-exchange', 'completed');
            this.updateProgress('step-registration', 'active');
            this.updateStatus('Registering EA...', 'Connecting your EA to WhatsApp service');

            // Register with our centralized webhook service
            const registrationData = await this.registerWithWebhookService(tokenData);

            this.updateProgress('step-registration', 'completed');
            this.showConnectionSuccess(registrationData);

        } catch (error) {
            console.error('Token exchange/registration failed:', error);
            this.handleConnectionError(error);
        }
    }

    /**
     * Exchange authorization code for business access tokens
     */
    async exchangeCodeForTokens(code) {
        const response = await fetch('/api/whatsapp/exchange-token', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${this.getAuthToken()}`
            },
            body: JSON.stringify({
                code: code,
                customer_id: this.config.customerId,
                redirect_uri: this.config.redirectUrl
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.message || 'Token exchange failed');
        }

        return await response.json();
    }

    /**
     * Register EA with centralized webhook service
     */
    async registerWithWebhookService(tokenData) {
        const response = await fetch(`${this.config.webhookServiceUrl}/api/ea/register`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${this.getAuthToken()}`
            },
            body: JSON.stringify({
                customer_id: this.config.customerId,
                phone_number_id: tokenData.phone_number_id,
                waba_id: tokenData.waba_id,
                business_id: tokenData.business_id,
                access_token: tokenData.access_token,
                phone_number: tokenData.phone_number
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.message || 'EA registration failed');
        }

        return await response.json();
    }

    /**
     * Show connection success
     */
    showConnectionSuccess(registrationData) {
        this.state.connectionData = registrationData;
        this.showSection('success-section');

        // Update connection details
        document.getElementById('connectedPhone').textContent =
            registrationData.phone_number || '+1 (555) 123-4567';

        document.getElementById('connectedWaba').textContent =
            `WABA ID: ${registrationData.waba_id || '123456789012345'}`;

        // Track successful connection
        this.trackEvent('whatsapp_connection_success', {
            customer_id: this.config.customerId,
            phone_number_id: registrationData.phone_number_id,
            waba_id: registrationData.waba_id
        });

        this.state.isProcessing = false;
    }

    /**
     * Handle connection errors
     */
    handleConnectionError(error) {
        console.error('Connection error:', error);

        this.state.errorDetails = {
            type: error.name || 'CONNECTION_ERROR',
            message: error.message || 'Unknown error occurred',
            code: error.code || 'ERR_UNKNOWN'
        };

        this.showSection('error-section');

        document.getElementById('errorTitle').textContent =
            this.getErrorTitle(error);

        document.getElementById('errorDescription').textContent =
            this.getErrorDescription(error);

        document.getElementById('errorReason').textContent =
            error.message || 'The signup process encountered an unexpected error';

        document.getElementById('errorCode').textContent =
            error.code || 'ERR_SIGNUP_FAILED';

        // Track error for analytics
        this.trackEvent('whatsapp_connection_error', {
            customer_id: this.config.customerId,
            error_type: error.name || 'unknown',
            error_message: error.message || 'unknown'
        });

        this.state.isProcessing = false;
    }

    /**
     * Get user-friendly error titles
     */
    getErrorTitle(error) {
        const errorTitles = {
            'User cancelled login': 'Connection Cancelled',
            'Popup blocked': 'Popup Blocked',
            'Network error': 'Connection Failed',
            'Token exchange failed': 'Authorization Failed',
            'EA registration failed': 'Registration Failed'
        };

        return errorTitles[error.message] || 'Connection Failed';
    }

    /**
     * Get user-friendly error descriptions
     */
    getErrorDescription(error) {
        const errorDescriptions = {
            'User cancelled login': 'The WhatsApp Business signup was cancelled',
            'Popup blocked': 'The signup popup was blocked by your browser',
            'Network error': 'Unable to connect to WhatsApp services',
            'Token exchange failed': 'Could not authorize WhatsApp Business access',
            'EA registration failed': 'Could not register EA with webhook service'
        };

        return errorDescriptions[error.message] ||
               'We couldn\'t connect your WhatsApp Business account';
    }

    /**
     * Retry connection
     */
    retryConnection() {
        this.state.errorDetails = null;
        this.state.isProcessing = false;
        this.showSection('welcome-section');
        this.resetProgress();
    }

    /**
     * Continue to dashboard
     */
    continueToDashboard() {
        // Track dashboard navigation
        this.trackEvent('whatsapp_onboarding_complete', {
            customer_id: this.config.customerId,
            phone_number_id: this.state.connectionData?.phone_number_id
        });

        // Redirect to EA dashboard
        window.location.href = '/dashboard';
    }

    /**
     * Test WhatsApp connection
     */
    async testWhatsAppConnection() {
        this.showLoadingOverlay('Testing WhatsApp connection...');

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

            this.hideLoadingOverlay();

            if (response.ok) {
                alert('✅ Test message sent successfully! Check your WhatsApp Business account.');
            } else {
                const error = await response.json();
                alert(`❌ Test failed: ${error.message}`);
            }

        } catch (error) {
            this.hideLoadingOverlay();
            console.error('Test connection failed:', error);
            alert(`❌ Test failed: ${error.message}`);
        }
    }

    /**
     * Contact support
     */
    contactSupport() {
        const errorInfo = this.state.errorDetails ?
            `\n\nError Details:\nType: ${this.state.errorDetails.type}\nMessage: ${this.state.errorDetails.message}\nCode: ${this.state.errorDetails.code}` : '';

        const supportUrl = `mailto:support@aiagencyplatform.com?subject=WhatsApp Connection Issue&body=Customer ID: ${this.config.customerId}${errorInfo}`;
        window.location.href = supportUrl;
    }

    /**
     * Handle popup messages
     */
    handlePopupMessage(event) {
        // Verify origin for security
        if (event.origin !== 'https://www.facebook.com') return;

        const { type, data } = event.data;

        switch (type) {
            case 'facebook_connect_complete':
                this.handleSignupResponse(data);
                break;
            case 'facebook_connect_error':
                this.handleConnectionError(new Error(data.message || 'Popup connection failed'));
                break;
            case 'facebook_connect_cancelled':
                this.handleConnectionError(new Error('User cancelled login or did not fully authorize.'));
                break;
        }
    }

    /**
     * Setup popup blocked detection
     */
    setupPopupBlockedDetection() {
        let popupWindow;

        document.getElementById('connectButton')?.addEventListener('click', () => {
            // Test popup capability
            popupWindow = window.open('', 'popup-test', 'width=1,height=1');

            setTimeout(() => {
                if (!popupWindow || popupWindow.closed || popupWindow.outerHeight === 0) {
                    document.getElementById('retryButton').style.display = 'block';
                    this.handleConnectionError(new Error('Popup blocked'));
                } else {
                    popupWindow.close();
                }
            }, 1000);
        });
    }

    /**
     * Update progress steps
     */
    updateProgress(stepId, status) {
        const step = document.getElementById(stepId);
        if (!step) return;

        step.classList.remove('pending', 'active', 'completed');
        step.classList.add(status);
    }

    /**
     * Reset progress steps
     */
    resetProgress() {
        const steps = ['step-popup', 'step-permissions', 'step-exchange', 'step-registration'];
        steps.forEach(stepId => {
            this.updateProgress(stepId, 'pending');
        });
    }

    /**
     * Update status message
     */
    updateStatus(title, description) {
        document.getElementById('statusTitle').textContent = title;
        document.getElementById('statusDescription').textContent = description;
    }

    /**
     * Show specific section
     */
    showSection(sectionId) {
        // Hide all sections
        document.querySelectorAll('.content-section').forEach(section => {
            section.classList.remove('active');
        });

        // Show target section
        document.getElementById(sectionId)?.classList.add('active');
        this.state.currentSection = sectionId;

        // Update progress bar
        this.updateProgressBar(sectionId);
    }

    /**
     * Update progress bar based on section
     */
    updateProgressBar(sectionId) {
        const progressSteps = document.querySelectorAll('.progress-step');

        progressSteps.forEach(step => {
            step.classList.remove('active', 'completed');
        });

        switch (sectionId) {
            case 'welcome-section':
            case 'progress-section':
            case 'error-section':
                progressSteps[1]?.classList.add('active');
                break;
            case 'success-section':
                progressSteps[0]?.classList.add('completed');
                progressSteps[1]?.classList.add('completed');
                progressSteps[2]?.classList.add('active');
                break;
        }
    }

    /**
     * Show loading overlay
     */
    showLoadingOverlay(message) {
        const overlay = document.getElementById('loadingOverlay');
        const text = overlay.querySelector('p');

        text.textContent = message;
        overlay.classList.add('active');
    }

    /**
     * Hide loading overlay
     */
    hideLoadingOverlay() {
        document.getElementById('loadingOverlay')?.classList.remove('active');
    }

    /**
     * Get customer ID from URL or local storage
     */
    getCustomerId() {
        const urlParams = new URLSearchParams(window.location.search);
        return urlParams.get('customer_id') ||
               localStorage.getItem('customer_id') ||
               'demo-customer-123';
    }

    /**
     * Get authentication token
     */
    getAuthToken() {
        return localStorage.getItem('auth_token') ||
               sessionStorage.getItem('auth_token') ||
               'demo-auth-token';
    }

    /**
     * Fetch client information
     */
    async fetchClientInfo(customerId) {
        try {
            const response = await fetch(`/api/clients/${customerId}`, {
                headers: {
                    'Authorization': `Bearer ${this.getAuthToken()}`
                }
            });

            if (response.ok) {
                return await response.json();
            }
        } catch (error) {
            console.warn('Could not fetch client info:', error);
        }

        return null;
    }

    /**
     * Track events for analytics
     */
    trackEvent(eventName, properties = {}) {
        // Implement your analytics tracking here
        console.log(`📊 Event: ${eventName}`, properties);

        // Example integrations:
        // gtag('event', eventName, properties);
        // analytics.track(eventName, properties);
        // mixpanel.track(eventName, properties);
    }

    /**
     * Show error with specific type
     */
    showError(type, message) {
        this.handleConnectionError({
            name: type,
            message: message,
            code: type.toUpperCase()
        });
    }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new WhatsAppOnboarding();
});

// Export for testing
if (typeof module !== 'undefined' && module.exports) {
    module.exports = WhatsAppOnboarding;
}