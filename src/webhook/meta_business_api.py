#!/usr/bin/env python3
"""
Meta Business API Integration for WhatsApp Embedded Signup
Handles token exchange, WABA management, and business account operations
"""

import asyncio
import logging
import json
import hmac
import hashlib
import aiohttp
import requests
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import os
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

# Meta Graph API configuration
META_GRAPH_API_BASE = "https://graph.facebook.com"
META_API_VERSION = os.getenv('META_API_VERSION', 'v20.0')
META_APP_ID = os.getenv('META_APP_ID', '')
META_APP_SECRET = os.getenv('META_APP_SECRET', '')


@dataclass
class MetaTokenExchangeResult:
    """Result of Meta token exchange"""
    success: bool
    access_token: Optional[str] = None
    token_type: Optional[str] = None
    expires_in: Optional[int] = None
    granted_scopes: Optional[List[str]] = None
    error_message: Optional[str] = None


@dataclass
class MetaWABAInfo:
    """WhatsApp Business Account information"""
    waba_id: str
    name: str
    currency: str
    timezone_id: str
    message_template_namespace: str
    account_review_status: str
    business_verification_status: str
    phone_numbers: List[Dict[str, Any]]


@dataclass
class MetaBusinessPhoneNumber:
    """Meta business phone number information"""
    id: str
    verified_name: str
    display_phone_number: str
    quality_rating: str
    platform: str
    throughput: Dict[str, Any]
    webhook_configuration: Optional[Dict[str, Any]] = None


class MetaBusinessAPI:
    """Meta Business API client for WhatsApp integration"""

    def __init__(self):
        self.app_id = META_APP_ID
        self.app_secret = META_APP_SECRET
        self.api_version = META_API_VERSION
        self.base_url = f"{META_GRAPH_API_BASE}/{self.api_version}"

        if not self.app_id or not self.app_secret:
            logger.warning("⚠️ Meta App ID or App Secret not configured - Embedded Signup will not work")

    async def exchange_authorization_code(self, authorization_code: str) -> MetaTokenExchangeResult:
        """
        Exchange 30-second authorization code for long-lived business token
        Meta requirement: Must be completed within 30 seconds of receiving code
        """
        try:
            url = f"{self.base_url}/oauth/access_token"
            params = {
                'client_id': self.app_id,
                'client_secret': self.app_secret,
                'code': authorization_code
            }

            logger.info("🔄 Exchanging Meta authorization code for business token")

            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    result_data = await response.json()

                    if response.status == 200 and 'access_token' in result_data:
                        logger.info("✅ Successfully exchanged authorization code for Meta business token")

                        return MetaTokenExchangeResult(
                            success=True,
                            access_token=result_data['access_token'],
                            token_type=result_data.get('token_type', 'bearer'),
                            expires_in=result_data.get('expires_in'),
                            granted_scopes=result_data.get('scope', '').split(',') if result_data.get('scope') else []
                        )
                    else:
                        error_msg = result_data.get('error', {}).get('message', 'Unknown error during token exchange')
                        logger.error(f"❌ Meta token exchange failed: {error_msg}")

                        return MetaTokenExchangeResult(
                            success=False,
                            error_message=error_msg
                        )

        except asyncio.TimeoutError:
            error_msg = "Token exchange timed out - Meta requires completion within 30 seconds"
            logger.error(f"❌ {error_msg}")
            return MetaTokenExchangeResult(success=False, error_message=error_msg)

        except Exception as e:
            error_msg = f"Error during token exchange: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return MetaTokenExchangeResult(success=False, error_message=error_msg)

    async def get_business_accounts(self, access_token: str) -> List[Dict[str, Any]]:
        """Get list of WhatsApp Business Accounts associated with the token"""
        try:
            url = f"{self.base_url}/me/businesses"
            headers = {'Authorization': f'Bearer {access_token}'}

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        businesses = data.get('data', [])

                        logger.info(f"📊 Retrieved {len(businesses)} business accounts")
                        return businesses
                    else:
                        error_data = await response.json()
                        error_msg = error_data.get('error', {}).get('message', 'Unknown error')
                        logger.error(f"❌ Failed to get business accounts: {error_msg}")
                        return []

        except Exception as e:
            logger.error(f"Error getting business accounts: {e}")
            return []

    async def get_whatsapp_business_accounts(self, access_token: str, business_id: str) -> List[MetaWABAInfo]:
        """Get WhatsApp Business Accounts for a specific business"""
        try:
            url = f"{self.base_url}/{business_id}/whatsapp_business_accounts"
            headers = {'Authorization': f'Bearer {access_token}'}

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        wabas = []

                        for waba_data in data.get('data', []):
                            # Get phone numbers for this WABA
                            phone_numbers = await self.get_waba_phone_numbers(access_token, waba_data['id'])

                            waba = MetaWABAInfo(
                                waba_id=waba_data['id'],
                                name=waba_data.get('name', ''),
                                currency=waba_data.get('currency', 'USD'),
                                timezone_id=waba_data.get('timezone_id', 'UTC'),
                                message_template_namespace=waba_data.get('message_template_namespace', ''),
                                account_review_status=waba_data.get('account_review_status', 'PENDING'),
                                business_verification_status=waba_data.get('business_verification_status', 'PENDING'),
                                phone_numbers=phone_numbers
                            )
                            wabas.append(waba)

                        logger.info(f"📱 Retrieved {len(wabas)} WhatsApp Business Accounts")
                        return wabas

                    else:
                        error_data = await response.json()
                        error_msg = error_data.get('error', {}).get('message', 'Unknown error')
                        logger.error(f"❌ Failed to get WABA accounts: {error_msg}")
                        return []

        except Exception as e:
            logger.error(f"Error getting WABA accounts: {e}")
            return []

    async def get_waba_phone_numbers(self, access_token: str, waba_id: str) -> List[Dict[str, Any]]:
        """Get phone numbers for a WhatsApp Business Account"""
        try:
            url = f"{self.base_url}/{waba_id}/phone_numbers"
            headers = {'Authorization': f'Bearer {access_token}'}

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        phone_numbers = data.get('data', [])

                        logger.info(f"📞 Retrieved {len(phone_numbers)} phone numbers for WABA {waba_id}")
                        return phone_numbers
                    else:
                        logger.error(f"❌ Failed to get phone numbers for WABA {waba_id}")
                        return []

        except Exception as e:
            logger.error(f"Error getting WABA phone numbers: {e}")
            return []

    async def subscribe_to_webhooks(self, access_token: str, waba_id: str, callback_url: str,
                                   verify_token: str, webhook_fields: List[str] = None) -> bool:
        """Subscribe WABA to webhook notifications"""
        try:
            if webhook_fields is None:
                webhook_fields = ['messages', 'message_status', 'account_alerts', 'message_template_status_update']

            url = f"{self.base_url}/{waba_id}/subscribed_apps"
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }

            data = {
                'callback_url': callback_url,
                'verify_token': verify_token,
                'webhook_fields': webhook_fields
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        success = result.get('success', False)

                        if success:
                            logger.info(f"✅ Successfully subscribed WABA {waba_id} to webhooks")
                        else:
                            logger.error(f"❌ Webhook subscription returned success=false for WABA {waba_id}")

                        return success
                    else:
                        error_data = await response.json()
                        error_msg = error_data.get('error', {}).get('message', 'Unknown error')
                        logger.error(f"❌ Webhook subscription failed for WABA {waba_id}: {error_msg}")
                        return False

        except Exception as e:
            logger.error(f"Error subscribing to webhooks: {e}")
            return False

    async def validate_business_token(self, access_token: str) -> Dict[str, Any]:
        """Validate and get information about a business access token"""
        try:
            url = f"{self.base_url}/me"
            headers = {'Authorization': f'Bearer {access_token}'}
            params = {'fields': 'id,name,type'}

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"✅ Token validated for {data.get('type', 'unknown')} account: {data.get('name', data.get('id'))}")
                        return data
                    else:
                        error_data = await response.json()
                        error_msg = error_data.get('error', {}).get('message', 'Invalid token')
                        logger.error(f"❌ Token validation failed: {error_msg}")
                        return {'error': error_msg}

        except Exception as e:
            logger.error(f"Error validating token: {e}")
            return {'error': str(e)}

    def validate_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Validate Meta webhook signature"""
        try:
            if not self.app_secret:
                logger.warning("⚠️ Meta App Secret not configured - skipping signature validation")
                return True

            # Meta sends signature as 'sha256=<hash>'
            expected_signature = hmac.new(
                self.app_secret.encode(),
                payload,
                hashlib.sha256
            ).hexdigest()

            # Remove 'sha256=' prefix if present
            signature = signature.replace('sha256=', '')

            is_valid = hmac.compare_digest(expected_signature, signature)

            if not is_valid:
                logger.warning("⚠️ Invalid Meta webhook signature")

            return is_valid

        except Exception as e:
            logger.error(f"Error validating webhook signature: {e}")
            return False

    async def send_message(self, access_token: str, business_phone_number_id: str,
                          to_number: str, message_type: str, content: Dict[str, Any]) -> Optional[str]:
        """Send message via Meta WhatsApp Business API"""
        try:
            url = f"{self.base_url}/{business_phone_number_id}/messages"
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }

            message_data = {
                "messaging_product": "whatsapp",
                "to": to_number.replace('+', '').replace(' ', '').replace('-', ''),
                "type": message_type,
                **content
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=message_data) as response:
                    if response.status == 200:
                        result = await response.json()
                        message_id = result.get('messages', [{}])[0].get('id', 'unknown')
                        logger.info(f"✅ Message sent via Meta API: {message_id}")
                        return message_id
                    else:
                        error_data = await response.json()
                        error_msg = error_data.get('error', {}).get('message', 'Unknown error')
                        logger.error(f"❌ Failed to send message via Meta API: {error_msg}")
                        return None

        except Exception as e:
            logger.error(f"Error sending message via Meta API: {e}")
            return None

    async def get_media_url(self, access_token: str, media_id: str) -> Optional[str]:
        """Get media URL from Meta API"""
        try:
            url = f"{self.base_url}/{media_id}"
            headers = {'Authorization': f'Bearer {access_token}'}

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get('url')
                    else:
                        logger.error(f"❌ Failed to get media URL for {media_id}")
                        return None

        except Exception as e:
            logger.error(f"Error getting media URL: {e}")
            return None

    async def download_media(self, access_token: str, media_url: str) -> Optional[bytes]:
        """Download media from Meta API"""
        try:
            headers = {'Authorization': f'Bearer {access_token}'}

            async with aiohttp.ClientSession() as session:
                async with session.get(media_url, headers=headers) as response:
                    if response.status == 200:
                        return await response.read()
                    else:
                        logger.error(f"❌ Failed to download media from {media_url}")
                        return None

        except Exception as e:
            logger.error(f"Error downloading media: {e}")
            return None


# Global Meta Business API client
meta_business_api = MetaBusinessAPI()