class ChatUI {
    constructor() {
        this.messagesContainer = document.getElementById('chatMessages');
        this.messageInput = document.getElementById('messageInput');
        this.sendButton = document.getElementById('sendButton');
        this.customerId = 'demo-user-' + Date.now();
        this.conversationId = null;
        
        this.initializeEventListeners();
    }
    
    initializeEventListeners() {
        this.sendButton.addEventListener('click', () => this.sendMessage());
        this.messageInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                this.sendMessage();
            }
        });
    }
    
    async sendMessage() {
        const message = this.messageInput.value.trim();
        if (!message) return;
        
        // Add user message to chat
        this.addMessage(message, 'user');
        this.messageInput.value = '';
        this.sendButton.disabled = true;
        
        // Show typing indicator
        const typingIndicator = this.showTypingIndicator();
        
        try {
            // Send message to EA backend
            const response = await this.callExecutiveAssistant(message);
            
            // Remove typing indicator and add EA response
            this.removeTypingIndicator(typingIndicator);
            this.addMessage(response, 'assistant');
            
        } catch (error) {
            console.error('Error:', error);
            this.removeTypingIndicator(typingIndicator);
            this.addMessage('Sorry, I encountered an issue. Let me try again in a moment.', 'assistant');
        }
        
        this.sendButton.disabled = false;
        this.messageInput.focus();
    }
    
    addMessage(content, sender) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${sender}`;
        
        const messageContent = document.createElement('div');
        messageContent.className = 'message-content';
        messageContent.textContent = content;
        
        const messageTime = document.createElement('div');
        messageTime.className = 'message-time';
        messageTime.textContent = this.formatTime(new Date());
        
        messageDiv.appendChild(messageContent);
        messageDiv.appendChild(messageTime);
        
        this.messagesContainer.appendChild(messageDiv);
        this.scrollToBottom();
    }
    
    showTypingIndicator() {
        const typingDiv = document.createElement('div');
        typingDiv.className = 'message assistant typing';
        typingDiv.innerHTML = `
            <div class="typing-indicator">
                <span>Sarah is typing</span>
                <div class="typing-dots">
                    <span></span>
                    <span></span>
                    <span></span>
                </div>
            </div>
        `;
        
        this.messagesContainer.appendChild(typingDiv);
        this.scrollToBottom();
        return typingDiv;
    }
    
    removeTypingIndicator(indicator) {
        if (indicator && indicator.parentNode) {
            indicator.parentNode.removeChild(indicator);
        }
    }
    
    async callExecutiveAssistant(message) {
        try {
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    message: message,
                    customer_id: this.customerId,
                    conversation_id: this.conversationId
                })
            });
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const data = await response.json();
            this.conversationId = data.conversation_id;
            return data.response;
            
        } catch (error) {
            console.error('API call failed:', error);
            // Fallback to mock responses if API fails
            await this.delay(1000 + Math.random() * 2000);
            const responses = this.getMockResponse(message);
            return responses[Math.floor(Math.random() * responses.length)];
        }
    }
    
    getMockResponse(message) {
        const msg = message.toLowerCase();
        
        if (msg.includes('business') || msg.includes('company')) {
            return [
                "Great! Tell me more about your business. What industry are you in and what does a typical day look like for you?",
                "I'd love to learn about your business! What are the main challenges you're facing day-to-day?",
                "Excellent! I'm here to help automate your business processes. What tasks take up most of your time?"
            ];
        }
        
        if (msg.includes('automate') || msg.includes('workflow')) {
            return [
                "Perfect! I can help you automate that process. Let me analyze what you've described and create a workflow for you. This could save you several hours per week!",
                "I see a great automation opportunity here! I can create a workflow that handles this entire process automatically. Would you like me to set that up?",
                "That's exactly what I'm designed to help with! I can create an automated workflow for this process. Let me get started on that for you."
            ];
        }
        
        if (msg.includes('social media') || msg.includes('posts') || msg.includes('content')) {
            return [
                "Social media automation is one of my specialties! I can create workflows that handle content creation, scheduling, and even engagement tracking. What platforms are you using?",
                "I can definitely automate your social media workflow! From content creation to posting schedules, I'll handle it all. Tell me about your current process.",
                "Social media takes so much time when done manually! I can create an automation that generates content, schedules posts, and tracks performance across all your platforms."
            ];
        }
        
        if (msg.includes('marketing') || msg.includes('leads') || msg.includes('customers')) {
            return [
                "Marketing automation is crucial for business growth! I can help you create lead capture workflows, email sequences, and customer nurturing campaigns. What's your current process?",
                "I specialize in marketing automation! From lead generation to customer onboarding, I can create workflows that work 24/7. What's your biggest marketing challenge?",
                "Let me help you automate your marketing efforts! I can create systems for lead qualification, follow-up sequences, and customer communication. What would have the biggest impact?"
            ];
        }
        
        if (msg.includes('time') || msg.includes('hours') || msg.includes('daily') || msg.includes('every day')) {
            return [
                "Time is our most valuable resource! Let me help you reclaim those hours by automating repetitive tasks. What processes are eating up your time?",
                "I can definitely help you get time back in your day! The key is identifying which repetitive tasks can be automated. Tell me about your daily routine.",
                "Those hours add up quickly! I can create automations that handle routine tasks so you can focus on growing your business. What would you like to automate first?"
            ];
        }
        
        // Default responses
        return [
            "I'm here to learn about your business and create automations that save you time. What challenges are you facing?",
            "As your Executive Assistant, I want to understand how I can best help you. Tell me about your daily operations.",
            "I specialize in learning about businesses through conversation and creating real automations. What would you like to discuss?",
            "Let me help you streamline your business processes! What takes up most of your time each day?"
        ];
    }
    
    formatTime(date) {
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }
    
    scrollToBottom() {
        this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
    }
    
    delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
}

// Initialize chat when page loads
document.addEventListener('DOMContentLoaded', () => {
    new ChatUI();
});