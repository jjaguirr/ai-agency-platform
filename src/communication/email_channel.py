"""
Email Communication Channel
Handles email-based communication for the AI Agency Platform
"""

import asyncio
import logging
import json
import hashlib
import hmac
import os
from datetime import datetime
from typing import Dict, Any, Optional, List
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib
import imaplib
import email
import email.utils
from email.header import decode_header

from .base_channel import BaseCommunicationChannel, BaseMessage, ChannelType

logger = logging.getLogger(__name__)

class EmailMessage(BaseMessage):
    """Enhanced message class for email-specific properties"""
    
    def __init__(self, content: str, from_email: str, to_email: str, 
                 subject: str = "", message_id: str = "", conversation_id: str = "",
                 customer_id: Optional[str] = None, **kwargs):
        # Map email addresses to the base class phone number fields for compatibility
        super().__init__(
            content=content,
            from_number=from_email,
            to_number=to_email,
            channel=ChannelType.EMAIL,
            message_id=message_id,
            conversation_id=conversation_id,
            timestamp=datetime.now(),
            customer_id=customer_id,
            metadata=kwargs
        )
        self.subject = subject
        self.from_email = from_email
        self.to_email = to_email

class EmailChannel(BaseCommunicationChannel):
    """Email communication channel implementation"""
    
    def __init__(self, customer_id: str, config: Dict[str, Any] = None):
        super().__init__(customer_id, config)
        
        # Email configuration
        self.smtp_server = self.config.get('smtp_server', os.getenv('SMTP_SERVER', 'smtp.gmail.com'))
        self.smtp_port = int(self.config.get('smtp_port', os.getenv('SMTP_PORT', '587')))
        self.smtp_username = self.config.get('smtp_username', os.getenv('SMTP_USERNAME', ''))
        self.smtp_password = self.config.get('smtp_password', os.getenv('SMTP_PASSWORD', ''))
        self.smtp_use_tls = self.config.get('smtp_use_tls', os.getenv('SMTP_USE_TLS', 'true').lower() == 'true')
        
        # IMAP configuration for receiving emails
        self.imap_server = self.config.get('imap_server', os.getenv('IMAP_SERVER', 'imap.gmail.com'))
        self.imap_port = int(self.config.get('imap_port', os.getenv('IMAP_PORT', '993')))
        
        # Default from address
        self.from_email = self.config.get('from_email', os.getenv('EMAIL_FROM_ADDRESS', self.smtp_username))
        
        # Webhook validation secret for email webhooks (if using email service webhooks)
        self.webhook_secret = self.config.get('webhook_secret', os.getenv('EMAIL_WEBHOOK_SECRET', ''))
    
    def _get_channel_type(self) -> ChannelType:
        """Return EMAIL channel type"""
        return ChannelType.EMAIL
    
    async def initialize(self) -> bool:
        """Initialize the email channel"""
        try:
            # Test SMTP connection
            await self._test_smtp_connection()
            
            # Test IMAP connection  
            await self._test_imap_connection()
            
            self.is_initialized = True
            logger.info(f"Email channel initialized for customer {self.customer_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize email channel for customer {self.customer_id}: {e}")
            return False
    
    async def _test_smtp_connection(self):
        """Test SMTP connection"""
        def _sync_test():
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                if self.smtp_use_tls:
                    server.starttls()
                if self.smtp_username and self.smtp_password:
                    server.login(self.smtp_username, self.smtp_password)
                return True
        
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _sync_test)
    
    async def _test_imap_connection(self):
        """Test IMAP connection"""
        def _sync_test():
            with imaplib.IMAP4_SSL(self.imap_server, self.imap_port) as imap:
                if self.smtp_username and self.smtp_password:
                    imap.login(self.smtp_username, self.smtp_password)
                return True
        
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _sync_test)
    
    async def send_message(self, to_email: str, content: str, subject: str = "", **kwargs) -> str:
        """Send an email message"""
        try:
            def _send_email():
                # Create message
                msg = MIMEMultipart('alternative')
                msg['From'] = self.from_email
                msg['To'] = to_email
                msg['Subject'] = subject or "Message from AI Assistant"
                msg['Date'] = email.utils.formatdate(localtime=True)
                
                # Generate message ID
                message_id = f"<{datetime.now().timestamp()}@{self.customer_id}.aiagency.platform>"
                msg['Message-ID'] = message_id
                
                # Add content
                if kwargs.get('html_content'):
                    # HTML and text version
                    text_part = MIMEText(content, 'plain', 'utf-8')
                    html_part = MIMEText(kwargs['html_content'], 'html', 'utf-8')
                    msg.attach(text_part)
                    msg.attach(html_part)
                else:
                    # Text only
                    text_part = MIMEText(content, 'plain', 'utf-8')
                    msg.attach(text_part)
                
                # Send email
                with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                    if self.smtp_use_tls:
                        server.starttls()
                    if self.smtp_username and self.smtp_password:
                        server.login(self.smtp_username, self.smtp_password)
                    server.send_message(msg)
                
                return message_id.strip('<>')
            
            loop = asyncio.get_event_loop()
            message_id = await loop.run_in_executor(None, _send_email)
            
            logger.info(f"Email sent to {to_email} with message ID {message_id}")
            return message_id
            
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            raise
    
    async def handle_incoming_message(self, message_data: Dict[str, Any]) -> EmailMessage:
        """Parse incoming email message data"""
        try:
            # Extract email fields from message_data
            from_email = message_data.get('from', message_data.get('sender', ''))
            to_email = message_data.get('to', message_data.get('recipient', self.from_email))
            subject = message_data.get('subject', '')
            content = message_data.get('content', message_data.get('text', message_data.get('body', '')))
            message_id = message_data.get('message_id', message_data.get('id', ''))
            
            # Generate conversation ID from thread or subject
            conversation_id = message_data.get('conversation_id', 
                                             message_data.get('thread_id',
                                             hashlib.md5(f"{from_email}:{subject}".encode()).hexdigest()))
            
            # Create EmailMessage
            email_message = EmailMessage(
                content=content,
                from_email=from_email,
                to_email=to_email,
                subject=subject,
                message_id=message_id,
                conversation_id=conversation_id,
                customer_id=self.customer_id,
                **message_data.get('metadata', {})
            )
            
            logger.debug(f"Parsed incoming email from {from_email} with subject '{subject}'")
            return email_message
            
        except Exception as e:
            logger.error(f"Failed to parse incoming email: {e}")
            raise
    
    async def validate_webhook_signature(self, payload: str, signature: str) -> bool:
        """Validate webhook signature for email webhooks"""
        if not self.webhook_secret:
            logger.warning("No webhook secret configured, skipping signature validation")
            return True
        
        try:
            # Compute expected signature
            expected_signature = hmac.new(
                self.webhook_secret.encode(),
                payload.encode(),
                hashlib.sha256
            ).hexdigest()
            
            # Compare signatures (constant-time comparison)
            return hmac.compare_digest(f"sha256={expected_signature}", signature)
            
        except Exception as e:
            logger.error(f"Webhook signature validation failed: {e}")
            return False
    
    async def get_recent_messages(self, folder: str = 'INBOX', limit: int = 10) -> List[EmailMessage]:
        """Get recent email messages from IMAP"""
        try:
            def _get_messages():
                messages = []
                
                with imaplib.IMAP4_SSL(self.imap_server, self.imap_port) as imap:
                    if self.smtp_username and self.smtp_password:
                        imap.login(self.smtp_username, self.smtp_password)
                    
                    imap.select(folder)
                    
                    # Search for recent messages
                    typ, data = imap.search(None, 'ALL')
                    if typ == 'OK':
                        message_ids = data[0].split()
                        # Get the last 'limit' messages
                        recent_ids = message_ids[-limit:] if len(message_ids) > limit else message_ids
                        
                        for msg_id in recent_ids:
                            typ, msg_data = imap.fetch(msg_id, '(RFC822)')
                            if typ == 'OK':
                                email_body = msg_data[0][1]
                                email_message = email.message_from_bytes(email_body)
                                
                                # Parse email
                                from_email = email_message.get('From', '')
                                to_email = email_message.get('To', '')
                                subject = email_message.get('Subject', '')
                                message_id = email_message.get('Message-ID', '').strip('<>')
                                
                                # Decode subject if needed
                                if subject:
                                    decoded_subject = decode_header(subject)
                                    subject = ''.join([
                                        text.decode(encoding or 'utf-8') if isinstance(text, bytes) else text
                                        for text, encoding in decoded_subject
                                    ])
                                
                                # Get email content
                                content = self._extract_email_content(email_message)
                                
                                messages.append(EmailMessage(
                                    content=content,
                                    from_email=from_email,
                                    to_email=to_email,
                                    subject=subject,
                                    message_id=message_id,
                                    conversation_id=hashlib.md5(f"{from_email}:{subject}".encode()).hexdigest(),
                                    customer_id=self.customer_id
                                ))
                
                return messages
            
            loop = asyncio.get_event_loop()
            messages = await loop.run_in_executor(None, _get_messages)
            
            logger.info(f"Retrieved {len(messages)} recent emails from {folder}")
            return messages
            
        except Exception as e:
            logger.error(f"Failed to get recent messages: {e}")
            return []
    
    def _extract_email_content(self, email_message) -> str:
        """Extract text content from email message"""
        content = ""
        
        if email_message.is_multipart():
            for part in email_message.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))
                
                if content_type == "text/plain" and "attachment" not in content_disposition:
                    payload = part.get_payload(decode=True)
                    if payload:
                        content = payload.decode()
                        break
        else:
            payload = email_message.get_payload(decode=True)
            if payload:
                content = payload.decode()
        
        return content.strip()
    
    async def health_check(self) -> Dict[str, Any]:
        """Check email channel health"""
        base_health = await super().health_check()
        
        # Add email-specific health checks
        smtp_ok = False
        imap_ok = False
        
        try:
            await self._test_smtp_connection()
            smtp_ok = True
        except Exception as e:
            logger.warning(f"SMTP health check failed: {e}")
        
        try:
            await self._test_imap_connection()
            imap_ok = True
        except Exception as e:
            logger.warning(f"IMAP health check failed: {e}")
        
        base_health.update({
            "smtp_server": self.smtp_server,
            "smtp_port": self.smtp_port,
            "smtp_healthy": smtp_ok,
            "imap_server": self.imap_server,
            "imap_port": self.imap_port,
            "imap_healthy": imap_ok,
            "from_email": self.from_email,
            "overall_healthy": smtp_ok and imap_ok
        })
        
        return base_health