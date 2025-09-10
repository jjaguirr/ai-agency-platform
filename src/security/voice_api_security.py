"""
Voice API Security Module
Critical security implementation for voice integration endpoints

This module provides comprehensive API security including:
- JWT authentication and authorization
- Customer isolation validation
- Voice data encryption at rest
- API rate limiting
- Request/response sanitization
- Security audit logging
"""

import asyncio
import base64
import hashlib
import hmac
import json
import jwt
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from pathlib import Path
import secrets

from fastapi import HTTPException, Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import redis

logger = logging.getLogger(__name__)

@dataclass
class AuthenticatedUser:
    """Authenticated user information"""
    customer_id: str
    user_id: str
    role: str
    permissions: List[str]
    exp: int

@dataclass
class VoiceSecurityConfig:
    """Configuration for voice API security"""
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expiry_hours: int = 24
    max_voice_file_size: int = 50 * 1024 * 1024  # 50MB
    allowed_audio_formats: List[str] = None
    rate_limit_per_user: int = 100  # requests per minute
    voice_encryption_enabled: bool = True
    
    def __post_init__(self):
        if self.allowed_audio_formats is None:
            self.allowed_audio_formats = [
                'audio/mpeg',
                'audio/wav', 
                'audio/x-wav',
                'audio/webm',
                'audio/ogg',
                'audio/mp4'
            ]

class VoiceAPIAuth:
    """JWT-based authentication for voice API endpoints"""
    
    def __init__(self, config: VoiceSecurityConfig):
        self.config = config
        self.security = HTTPBearer()
        self.redis_client = redis.Redis(
            host=os.getenv('REDIS_HOST', 'localhost'),
            port=int(os.getenv('REDIS_PORT', 6379)),
            db=13,  # Use DB 13 for voice API security
            password=os.getenv('REDIS_PASSWORD'),
            decode_responses=True
        )
    
    async def authenticate_user(
        self, 
        credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())
    ) -> AuthenticatedUser:
        """
        Authenticate user via JWT token
        
        Args:
            credentials: Bearer token from Authorization header
            
        Returns:
            AuthenticatedUser with customer_id and permissions
            
        Raises:
            HTTPException: If authentication fails
        """
        try:
            # Extract and validate token
            token = credentials.credentials
            
            # Check if token is blacklisted
            if await self._is_token_blacklisted(token):
                raise HTTPException(
                    status_code=401,
                    detail="Token has been revoked"
                )
            
            # Decode JWT token
            payload = jwt.decode(
                token,
                self.config.jwt_secret,
                algorithms=[self.config.jwt_algorithm]
            )
            
            # Extract user information
            user = AuthenticatedUser(
                customer_id=payload.get('customer_id'),
                user_id=payload.get('user_id'),
                role=payload.get('role', 'user'),
                permissions=payload.get('permissions', []),
                exp=payload.get('exp')
            )
            
            # Validate required fields
            if not user.customer_id or not user.user_id:
                raise HTTPException(
                    status_code=401,
                    detail="Invalid token payload"
                )
            
            # Check token expiry
            if user.exp < time.time():
                raise HTTPException(
                    status_code=401,
                    detail="Token has expired"
                )
            
            # Log successful authentication
            await self._log_auth_event(user, "AUTH_SUCCESS", token)
            
            return user
            
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=401,
                detail="Token has expired"
            )
        except jwt.InvalidTokenError as e:
            raise HTTPException(
                status_code=401,
                detail=f"Invalid token: {str(e)}"
            )
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            raise HTTPException(
                status_code=401,
                detail="Authentication failed"
            )
    
    async def authorize_customer_access(
        self,
        user: AuthenticatedUser,
        requested_customer_id: str
    ) -> bool:
        """
        Validate that user can access requested customer data
        
        Args:
            user: Authenticated user
            requested_customer_id: Customer ID being accessed
            
        Returns:
            True if access is allowed
            
        Raises:
            HTTPException: If access is denied
        """
        # Basic customer isolation check
        if user.customer_id != requested_customer_id:
            # Check if user has cross-customer permissions (admin role)
            if user.role != 'admin' and 'cross_customer_access' not in user.permissions:
                await self._log_auth_event(
                    user, 
                    "UNAUTHORIZED_ACCESS_ATTEMPT", 
                    None,
                    {"requested_customer_id": requested_customer_id}
                )
                raise HTTPException(
                    status_code=403,
                    detail=f"Access denied: User cannot access customer {requested_customer_id}"
                )
        
        return True
    
    async def check_rate_limit(self, user: AuthenticatedUser) -> bool:
        """
        Check API rate limiting for user
        
        Args:
            user: Authenticated user
            
        Returns:
            True if under rate limit
            
        Raises:
            HTTPException: If rate limit exceeded
        """
        rate_limit_key = f"rate_limit:voice_api:{user.customer_id}:{user.user_id}"
        current_time = time.time()
        window_start = current_time - 60  # 1 minute window
        
        try:
            # Remove old entries
            self.redis_client.zremrangebyscore(rate_limit_key, 0, window_start)
            
            # Count current requests
            current_requests = self.redis_client.zcard(rate_limit_key)
            
            if current_requests >= self.config.rate_limit_per_user:
                await self._log_auth_event(
                    user,
                    "RATE_LIMIT_EXCEEDED",
                    None,
                    {"current_requests": current_requests, "limit": self.config.rate_limit_per_user}
                )
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded: {current_requests}/{self.config.rate_limit_per_user} requests per minute"
                )
            
            # Add current request
            self.redis_client.zadd(rate_limit_key, {str(current_time): current_time})
            self.redis_client.expire(rate_limit_key, 120)  # 2 minute TTL
            
            return True
            
        except Exception as e:
            logger.error(f"Rate limiting error: {e}")
            # Fail open for availability
            return True
    
    async def generate_token(
        self,
        customer_id: str,
        user_id: str,
        role: str = "user",
        permissions: List[str] = None
    ) -> str:
        """
        Generate JWT token for user
        
        Args:
            customer_id: Customer ID
            user_id: User ID
            role: User role
            permissions: List of permissions
            
        Returns:
            JWT token string
        """
        if permissions is None:
            permissions = []
        
        payload = {
            'customer_id': customer_id,
            'user_id': user_id,
            'role': role,
            'permissions': permissions,
            'iat': int(time.time()),
            'exp': int(time.time()) + (self.config.jwt_expiry_hours * 3600)
        }
        
        token = jwt.encode(
            payload,
            self.config.jwt_secret,
            algorithm=self.config.jwt_algorithm
        )
        
        await self._log_auth_event(
            AuthenticatedUser(customer_id, user_id, role, permissions, payload['exp']),
            "TOKEN_GENERATED",
            token
        )
        
        return token
    
    async def revoke_token(self, token: str):
        """
        Revoke a JWT token by adding it to blacklist
        
        Args:
            token: JWT token to revoke
        """
        try:
            # Add token to blacklist
            blacklist_key = f"blacklisted_token:{hashlib.sha256(token.encode()).hexdigest()}"
            
            # Decode token to get expiry
            payload = jwt.decode(
                token,
                self.config.jwt_secret,
                algorithms=[self.config.jwt_algorithm],
                options={"verify_exp": False}
            )
            
            exp = payload.get('exp', 0)
            ttl = max(0, exp - int(time.time()))
            
            self.redis_client.setex(blacklist_key, ttl, "revoked")
            
            logger.info(f"Token revoked for user {payload.get('user_id')}")
            
        except Exception as e:
            logger.error(f"Error revoking token: {e}")
    
    async def _is_token_blacklisted(self, token: str) -> bool:
        """Check if token is blacklisted"""
        try:
            blacklist_key = f"blacklisted_token:{hashlib.sha256(token.encode()).hexdigest()}"
            return self.redis_client.exists(blacklist_key)
        except:
            return False
    
    async def _log_auth_event(
        self,
        user: AuthenticatedUser,
        event_type: str,
        token: str = None,
        extra_data: Dict[str, Any] = None
    ):
        """Log authentication events for audit"""
        event = {
            'timestamp': datetime.now().isoformat(),
            'event_type': event_type,
            'customer_id': user.customer_id,
            'user_id': user.user_id,
            'role': user.role,
            'token_hash': hashlib.sha256(token.encode()).hexdigest() if token else None,
            'extra_data': extra_data or {}
        }
        
        try:
            # Store in Redis for real-time monitoring
            self.redis_client.lpush('voice_auth_events', json.dumps(event))
            self.redis_client.ltrim('voice_auth_events', 0, 1000)  # Keep last 1000 events
            self.redis_client.expire('voice_auth_events', 86400)  # 24 hours
            
            # Log to application logs
            if event_type in ['UNAUTHORIZED_ACCESS_ATTEMPT', 'RATE_LIMIT_EXCEEDED']:
                logger.warning(f"Voice API Security Event: {json.dumps(event)}")
            else:
                logger.info(f"Voice API Auth Event: {event_type} for {user.user_id}")
                
        except Exception as e:
            logger.error(f"Failed to log auth event: {e}")

class VoiceDataSecurity:
    """Security for voice data processing and storage"""
    
    def __init__(self, config: VoiceSecurityConfig):
        self.config = config
        self.encryption_key = self._load_encryption_key()
    
    def _load_encryption_key(self) -> bytes:
        """Load or generate encryption key for voice data"""
        key_file = Path("/secure/keys/voice_encryption.key")
        key_file.parent.mkdir(parents=True, exist_ok=True)
        
        if key_file.exists():
            with open(key_file, 'rb') as f:
                return f.read()
        else:
            # Generate new encryption key
            key = secrets.token_bytes(32)  # 256-bit key
            with open(key_file, 'wb') as f:
                f.write(key)
            os.chmod(key_file, 0o600)  # Secure permissions
            return key
    
    async def validate_voice_upload(
        self,
        file_content: bytes,
        content_type: str,
        customer_id: str
    ) -> Tuple[bool, List[str]]:
        """
        Validate voice file upload for security
        
        Args:
            file_content: Raw file content
            content_type: MIME type
            customer_id: Customer ID
            
        Returns:
            (is_valid, list_of_errors)
        """
        errors = []
        
        # Check file size
        if len(file_content) > self.config.max_voice_file_size:
            errors.append(f"File size {len(file_content)} exceeds maximum {self.config.max_voice_file_size}")
        
        # Check content type
        if content_type not in self.config.allowed_audio_formats:
            errors.append(f"Content type {content_type} not allowed")
        
        # Basic malware check - look for suspicious patterns
        suspicious_patterns = [
            b'<script',
            b'javascript:',
            b'eval(',
            b'exec(',
            b'\x00' * 10  # Null byte sequences
        ]
        
        for pattern in suspicious_patterns:
            if pattern in file_content:
                errors.append(f"Suspicious content pattern detected")
                break
        
        # Check if file is actually audio (basic magic number check)
        if not self._is_valid_audio_file(file_content, content_type):
            errors.append("File does not appear to be valid audio")
        
        return len(errors) == 0, errors
    
    def _is_valid_audio_file(self, content: bytes, content_type: str) -> bool:
        """Basic audio file validation using magic numbers"""
        if len(content) < 12:
            return False
        
        # Check common audio file signatures
        audio_signatures = {
            'audio/mpeg': [b'ID3', b'\xff\xfb'],  # MP3
            'audio/wav': [b'RIFF'],               # WAV
            'audio/ogg': [b'OggS'],               # OGG
            'audio/webm': [b'\x1a\x45\xdf\xa3'], # WebM
            'audio/mp4': [b'ftyp']                # MP4
        }
        
        signatures = audio_signatures.get(content_type, [])
        for signature in signatures:
            if content.startswith(signature) or signature in content[:50]:
                return True
        
        return False
    
    async def encrypt_voice_data(
        self,
        voice_data: bytes,
        customer_id: str,
        recording_id: str
    ) -> bytes:
        """
        Encrypt voice data for secure storage
        
        Args:
            voice_data: Raw voice data
            customer_id: Customer ID
            recording_id: Unique recording ID
            
        Returns:
            Encrypted voice data
        """
        if not self.config.voice_encryption_enabled:
            return voice_data
        
        try:
            from cryptography.fernet import Fernet
            
            # Create customer-specific encryption context
            context = f"{customer_id}:{recording_id}".encode()
            
            # Generate key using HKDF
            from cryptography.hazmat.primitives.kdf.hkdf import HKDF
            from cryptography.hazmat.primitives import hashes
            
            derived_key = HKDF(
                algorithm=hashes.SHA256(),
                length=32,
                salt=context,
                info=b'voice_encryption'
            ).derive(self.encryption_key)
            
            # Encrypt data
            fernet = Fernet(base64.urlsafe_b64encode(derived_key))
            encrypted_data = fernet.encrypt(voice_data)
            
            logger.info(f"Voice data encrypted for customer {customer_id}, recording {recording_id}")
            return encrypted_data
            
        except Exception as e:
            logger.error(f"Voice encryption failed: {e}")
            raise
    
    async def decrypt_voice_data(
        self,
        encrypted_data: bytes,
        customer_id: str,
        recording_id: str
    ) -> bytes:
        """
        Decrypt voice data
        
        Args:
            encrypted_data: Encrypted voice data
            customer_id: Customer ID
            recording_id: Unique recording ID
            
        Returns:
            Decrypted voice data
        """
        if not self.config.voice_encryption_enabled:
            return encrypted_data
        
        try:
            from cryptography.fernet import Fernet
            from cryptography.hazmat.primitives.kdf.hkdf import HKDF
            from cryptography.hazmat.primitives import hashes
            
            # Recreate customer-specific encryption context
            context = f"{customer_id}:{recording_id}".encode()
            
            # Derive same key
            derived_key = HKDF(
                algorithm=hashes.SHA256(),
                length=32,
                salt=context,
                info=b'voice_encryption'
            ).derive(self.encryption_key)
            
            # Decrypt data
            fernet = Fernet(base64.urlsafe_b64encode(derived_key))
            decrypted_data = fernet.decrypt(encrypted_data)
            
            return decrypted_data
            
        except Exception as e:
            logger.error(f"Voice decryption failed for customer {customer_id}: {e}")
            raise
    
    async def secure_delete_voice_data(
        self,
        file_path: Path,
        customer_id: str
    ) -> bool:
        """
        Securely delete voice data file
        
        Args:
            file_path: Path to voice file
            customer_id: Customer ID
            
        Returns:
            True if successfully deleted
        """
        try:
            if not file_path.exists():
                return True
            
            # Secure overwrite before deletion
            file_size = file_path.stat().st_size
            
            with open(file_path, 'r+b') as f:
                # Overwrite with random data 3 times
                for _ in range(3):
                    f.seek(0)
                    f.write(secrets.token_bytes(file_size))
                    f.flush()
                    os.fsync(f.fileno())
            
            # Delete file
            file_path.unlink()
            
            logger.info(f"Securely deleted voice file for customer {customer_id}: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Secure deletion failed for {file_path}: {e}")
            return False

class VoiceAPISecurityMiddleware:
    """Security middleware for voice API endpoints"""
    
    def __init__(self, config: VoiceSecurityConfig):
        self.config = config
        self.auth = VoiceAPIAuth(config)
        self.data_security = VoiceDataSecurity(config)
    
    async def validate_request(
        self,
        request: Request,
        user: AuthenticatedUser,
        customer_id: str = None
    ):
        """
        Comprehensive request validation
        
        Args:
            request: FastAPI request
            user: Authenticated user
            customer_id: Customer ID being accessed (if applicable)
        """
        # Check rate limiting
        await self.auth.check_rate_limit(user)
        
        # Validate customer access if customer_id provided
        if customer_id:
            await self.auth.authorize_customer_access(user, customer_id)
        
        # Validate request size
        content_length = request.headers.get('content-length')
        if content_length and int(content_length) > self.config.max_voice_file_size:
            raise HTTPException(
                status_code=413,
                detail=f"Request too large: {content_length} bytes"
            )
        
        # Log request for audit
        await self._log_api_request(request, user)
    
    async def _log_api_request(self, request: Request, user: AuthenticatedUser):
        """Log API request for audit trail"""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'customer_id': user.customer_id,
            'user_id': user.user_id,
            'method': request.method,
            'url': str(request.url),
            'user_agent': request.headers.get('user-agent', ''),
            'client_ip': request.client.host
        }
        
        logger.info(f"Voice API Request: {json.dumps(log_entry)}")

# Global configuration and instances
voice_security_config = VoiceSecurityConfig(
    jwt_secret=os.getenv('JWT_SECRET', secrets.token_urlsafe(32))
)

voice_api_auth = VoiceAPIAuth(voice_security_config)
voice_data_security = VoiceDataSecurity(voice_security_config)
voice_security_middleware = VoiceAPISecurityMiddleware(voice_security_config)

# Dependency functions for FastAPI
async def get_authenticated_user(
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())
) -> AuthenticatedUser:
    """FastAPI dependency for user authentication"""
    return await voice_api_auth.authenticate_user(credentials)

async def validate_customer_access(
    customer_id: str,
    user: AuthenticatedUser = Depends(get_authenticated_user)
) -> AuthenticatedUser:
    """FastAPI dependency for customer access validation"""
    await voice_api_auth.authorize_customer_access(user, customer_id)
    return user