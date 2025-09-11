"""
Voice Integration Module
Handles speech-to-text and text-to-speech using ElevenLabs API
"""

import asyncio
import logging
import os
import io
import tempfile
from typing import Optional, Dict, Any
import aiohttp
import aiofiles

logger = logging.getLogger(__name__)

class VoiceIntegration:
    """
    Voice integration for speech processing with ElevenLabs
    
    Features:
    - Text-to-speech with premium voice quality
    - Speech-to-text transcription
    - Voice cloning capabilities (future)
    - Audio format conversion
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        config = config or {}
        
        # ElevenLabs API configuration
        self.api_key = config.get('api_key') or os.getenv('ELEVENLABS_API_KEY')
        self.base_url = "https://api.elevenlabs.io/v1"
        
        # Voice settings
        self.voice_id = config.get('voice_id', 'EXAVITQu4vr4xnSDxMaL')  # Bella voice
        self.voice_settings = config.get('voice_settings', {
            'stability': 0.5,
            'similarity_boost': 0.8,
            'style': 0.0,
            'use_speaker_boost': True
        })
        
        # Audio settings
        self.output_format = config.get('output_format', 'mp3_44100_128')
        self.model_id = config.get('model_id', 'eleven_multilingual_v2')
        
        # Validate configuration
        if not self.api_key:
            raise ValueError("ElevenLabs API key is required")
        
        logger.info(f"Voice integration initialized with voice ID: {self.voice_id}")
    
    async def text_to_speech(self, text: str, voice_id: Optional[str] = None) -> Optional[bytes]:
        """
        Convert text to speech using ElevenLabs API
        
        Args:
            text: Text to convert to speech
            voice_id: Optional voice ID override
            
        Returns:
            Audio data as bytes (MP3 format)
        """
        try:
            if not text or not text.strip():
                logger.warning("Empty text provided for TTS")
                return None
            
            voice_id = voice_id or self.voice_id
            
            url = f"{self.base_url}/text-to-speech/{voice_id}"
            headers = {
                'Accept': 'audio/mpeg',
                'Content-Type': 'application/json',
                'xi-api-key': self.api_key
            }
            
            data = {
                'text': text.strip(),
                'model_id': self.model_id,
                'voice_settings': self.voice_settings
            }
            
            logger.info(f"🎤 Converting text to speech: {len(text)} characters")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=data) as response:
                    if response.status == 200:
                        audio_data = await response.read()
                        logger.info(f"✅ TTS successful: {len(audio_data)} bytes")
                        return audio_data
                    else:
                        error_text = await response.text()
                        logger.error(f"❌ TTS failed: {response.status} - {error_text}")
                        return None
                        
        except Exception as e:
            logger.error(f"Error in text-to-speech: {e}")
            return None
    
    async def speech_to_text(self, audio_data: bytes, language: str = 'en') -> Optional[str]:
        """
        Convert speech to text using ElevenLabs API
        
        Args:
            audio_data: Audio data as bytes
            language: Language code for transcription
            
        Returns:
            Transcribed text
        """
        try:
            if not audio_data:
                logger.warning("No audio data provided for STT")
                return None
            
            # ElevenLabs speech-to-text endpoint
            url = f"{self.base_url}/speech-to-text"
            headers = {
                'xi-api-key': self.api_key
            }
            
            # Prepare multipart form data
            data = aiohttp.FormData()
            data.add_field('audio', audio_data, filename='audio.mp3', content_type='audio/mpeg')
            data.add_field('model_id', 'whisper-1')  # ElevenLabs Whisper model
            
            logger.info(f"🎧 Converting speech to text: {len(audio_data)} bytes")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, data=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        transcription = result.get('text', '').strip()
                        logger.info(f"✅ STT successful: {transcription}")
                        return transcription
                    else:
                        error_text = await response.text()
                        logger.error(f"❌ STT failed: {response.status} - {error_text}")
                        return None
                        
        except Exception as e:
            logger.error(f"Error in speech-to-text: {e}")
            return None
    
    async def get_available_voices(self) -> Dict[str, Any]:
        """Get list of available voices from ElevenLabs"""
        try:
            url = f"{self.base_url}/voices"
            headers = {'xi-api-key': self.api_key}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        result = await response.json()
                        voices = result.get('voices', [])
                        logger.info(f"Retrieved {len(voices)} available voices")
                        return {
                            'voices': voices,
                            'count': len(voices)
                        }
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to get voices: {response.status} - {error_text}")
                        return {'voices': [], 'count': 0}
                        
        except Exception as e:
            logger.error(f"Error getting voices: {e}")
            return {'voices': [], 'count': 0}
    
    async def get_voice_info(self, voice_id: Optional[str] = None) -> Dict[str, Any]:
        """Get information about a specific voice"""
        try:
            voice_id = voice_id or self.voice_id
            url = f"{self.base_url}/voices/{voice_id}"
            headers = {'xi-api-key': self.api_key}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        voice_info = await response.json()
                        logger.info(f"Retrieved voice info for: {voice_info.get('name', 'Unknown')}")
                        return voice_info
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to get voice info: {response.status} - {error_text}")
                        return {}
                        
        except Exception as e:
            logger.error(f"Error getting voice info: {e}")
            return {}
    
    async def check_quota(self) -> Dict[str, Any]:
        """Check ElevenLabs API quota and usage"""
        try:
            url = f"{self.base_url}/user"
            headers = {'xi-api-key': self.api_key}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        user_info = await response.json()
                        subscription = user_info.get('subscription', {})
                        
                        quota_info = {
                            'character_count': subscription.get('character_count', 0),
                            'character_limit': subscription.get('character_limit', 0),
                            'tier': subscription.get('tier', 'unknown'),
                            'status': subscription.get('status', 'unknown'),
                            'next_character_count_reset_unix': subscription.get('next_character_count_reset_unix', 0)
                        }
                        
                        logger.info(f"Quota: {quota_info['character_count']}/{quota_info['character_limit']} characters")
                        return quota_info
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to get quota: {response.status} - {error_text}")
                        return {}
                        
        except Exception as e:
            logger.error(f"Error checking quota: {e}")
            return {}
    
    async def convert_audio_format(self, audio_data: bytes, 
                                 input_format: str = 'mp3',
                                 output_format: str = 'wav') -> Optional[bytes]:
        """
        Convert audio between formats (requires additional processing)
        This is a placeholder for future audio format conversion
        """
        try:
            # For now, just return the original data
            # In production, would use ffmpeg or similar for conversion
            logger.info(f"Audio format conversion: {input_format} -> {output_format}")
            return audio_data
            
        except Exception as e:
            logger.error(f"Error converting audio format: {e}")
            return None
    
    async def save_audio_file(self, audio_data: bytes, 
                            file_path: str, 
                            format: str = 'mp3') -> bool:
        """Save audio data to file"""
        try:
            async with aiofiles.open(file_path, 'wb') as f:
                await f.write(audio_data)
            
            logger.info(f"Audio saved to: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving audio file: {e}")
            return False
    
    async def test_voice_integration(self) -> Dict[str, Any]:
        """Test voice integration functionality"""
        results = {
            'tts_test': False,
            'quota_check': False,
            'voice_info': False,
            'errors': []
        }
        
        try:
            # Test TTS
            test_text = "Hello! This is a test of the voice integration system."
            audio_data = await self.text_to_speech(test_text)
            if audio_data:
                results['tts_test'] = True
                logger.info("✅ TTS test passed")
            else:
                results['errors'].append("TTS test failed")
            
            # Test quota check
            quota_info = await self.check_quota()
            if quota_info:
                results['quota_check'] = True
                results['quota_info'] = quota_info
                logger.info("✅ Quota check passed")
            else:
                results['errors'].append("Quota check failed")
            
            # Test voice info
            voice_info = await self.get_voice_info()
            if voice_info:
                results['voice_info'] = True
                results['voice_name'] = voice_info.get('name', 'Unknown')
                logger.info("✅ Voice info test passed")
            else:
                results['errors'].append("Voice info test failed")
            
        except Exception as e:
            logger.error(f"Voice integration test error: {e}")
            results['errors'].append(str(e))
        
        return results

# Helper functions for easy usage

async def quick_tts(text: str, voice_id: Optional[str] = None) -> Optional[bytes]:
    """Quick text-to-speech conversion"""
    try:
        voice_integration = VoiceIntegration()
        return await voice_integration.text_to_speech(text, voice_id)
    except Exception as e:
        logger.error(f"Quick TTS error: {e}")
        return None

async def quick_stt(audio_data: bytes) -> Optional[str]:
    """Quick speech-to-text conversion"""
    try:
        voice_integration = VoiceIntegration()
        return await voice_integration.speech_to_text(audio_data)
    except Exception as e:
        logger.error(f"Quick STT error: {e}")
        return None

async def test_voice_system() -> None:
    """Test the complete voice system"""
    logger.info("🎤 Testing Voice Integration System")
    
    try:
        voice_integration = VoiceIntegration()
        results = await voice_integration.test_voice_integration()
        
        print("\n" + "="*50)
        print("🎤 VOICE INTEGRATION TEST RESULTS")
        print("="*50)
        
        print(f"TTS Test: {'✅ PASS' if results['tts_test'] else '❌ FAIL'}")
        print(f"Quota Check: {'✅ PASS' if results['quota_check'] else '❌ FAIL'}")
        print(f"Voice Info: {'✅ PASS' if results['voice_info'] else '❌ FAIL'}")
        
        if results.get('quota_info'):
            quota = results['quota_info']
            print(f"\nQuota: {quota.get('character_count', 0)}/{quota.get('character_limit', 0)} characters")
            print(f"Tier: {quota.get('tier', 'Unknown')}")
        
        if results.get('voice_name'):
            print(f"Voice: {results['voice_name']}")
        
        if results['errors']:
            print(f"\nErrors: {', '.join(results['errors'])}")
        
        print("="*50)
        
    except Exception as e:
        logger.error(f"Voice system test failed: {e}")
        print(f"❌ Voice system test failed: {e}")

if __name__ == "__main__":
    # Run voice integration test
    asyncio.run(test_voice_system())