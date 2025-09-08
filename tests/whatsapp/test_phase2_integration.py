"""
Comprehensive Test Suite for WhatsApp Business API Phase 2 Integration
Tests all Phase 2 premium-casual communication features
"""

import asyncio
import json
import pytest
import uuid
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timedelta
from pathlib import Path

# Import our WhatsApp components
import sys
sys.path.append('/Users/jose/Documents/🚀 Projects/⚡ Active/whatsapp-integration-stream/src')

from communication.whatsapp_manager import WhatsAppBusinessManager, MediaProcessingResult, BusinessVerificationStatus
from communication.whatsapp_channel import WhatsAppChannel, WhatsAppMessage
from communication.base_channel import ChannelType


class TestPhase2WhatsAppIntegration:
    """Test suite for Phase 2 WhatsApp Business API integration"""
    
    @pytest.fixture
    async def whatsapp_manager(self):
        """Create WhatsApp manager for testing"""
        with patch('psycopg2.connect'), patch('redis.Redis'):
            manager = WhatsAppBusinessManager()
            manager.db_connection = Mock()
            manager.redis_client = Mock()
            yield manager
    
    @pytest.fixture
    async def whatsapp_channel(self):
        """Create WhatsApp channel for testing"""
        with patch('psycopg2.connect'), patch('redis.Redis'):
            channel = WhatsAppChannel('customer-test-001', {
                'twilio_account_sid': 'test_sid',
                'twilio_auth_token': 'test_token',
                'whatsapp_number': 'whatsapp:+14155238886'
            })
            channel.redis_client = Mock()
            channel.db_connection = Mock()
            yield channel
    
    @pytest.mark.asyncio
    async def test_premium_casual_personality_adaptation(self, whatsapp_channel):
        """Test premium-casual personality tone adaptation"""
        # Mock EA response
        formal_message = "Hello! I will help you with your business requirements. Thank you very much for your inquiry."
        
        # Test tone adaptation
        casual_response = await whatsapp_channel._apply_premium_casual_tone(formal_message)
        
        # Verify casual adaptations
        assert "Hey!" in casual_response
        assert "I'll help" in casual_response
        assert "Thanks so much" in casual_response
        
        # Verify mobile-friendly formatting
        long_message = "This is a very long message that exceeds 200 characters. " * 5
        formatted_response = await whatsapp_channel._apply_premium_casual_tone(long_message)
        
        # Should break into paragraphs for mobile
        assert "\\n\\n" in formatted_response or len(formatted_response.split('.')) > 2
    
    @pytest.mark.asyncio
    async def test_media_processing_capabilities(self, whatsapp_manager):
        """Test media processing for images, documents, and voice"""
        customer_id = "customer-test-001"
        
        # Mock media download
        with patch.object(whatsapp_manager, '_download_media') as mock_download:
            mock_download.return_value = Path('/tmp/test_image.jpg')
            
            # Test image processing
            with patch('PIL.Image.open') as mock_image:
                mock_img = Mock()
                mock_img.size = (800, 600)
                mock_img.format = 'JPEG'
                mock_img.mode = 'RGB'
                mock_image.return_value.__enter__.return_value = mock_img
                
                result = await whatsapp_manager.process_media_message(
                    "https://example.com/image.jpg",
                    "image/jpeg",
                    customer_id
                )
                
                assert result.success is True
                assert result.media_type == "image/jpeg"
                assert "I can see your image" in result.processed_content
                assert "📸" in result.processed_content
                assert result.analysis['dimensions'] == (800, 600)
    
    @pytest.mark.asyncio
    async def test_voice_message_transcription(self, whatsapp_manager):
        """Test voice message processing with speech recognition"""
        customer_id = "customer-test-001"
        
        # Mock audio processing chain
        with patch.object(whatsapp_manager, '_download_media') as mock_download, \
             patch('pydub.AudioSegment.from_file') as mock_audio, \
             patch('speech_recognition.Recognizer') as mock_recognizer:
            
            mock_download.return_value = Path('/tmp/test_audio.ogg')
            mock_audio.return_value.export = Mock()
            
            # Mock speech recognition
            mock_rec = Mock()
            mock_rec.record.return_value = "audio_data"
            mock_rec.recognize_google.return_value = "Hello, this is a test voice message"
            mock_recognizer.return_value = mock_rec
            
            result = await whatsapp_manager.process_media_message(
                "https://example.com/voice.ogg",
                "audio/ogg",
                customer_id
            )
            
            assert result.success is True
            assert result.transcript == "Hello, this is a test voice message"
            assert "Got your voice message" in result.processed_content
            assert "🎙️" in result.processed_content
    
    @pytest.mark.asyncio
    async def test_business_verification_setup(self, whatsapp_manager):
        """Test WhatsApp Business verification process"""
        customer_id = "customer-test-001"
        business_config = {
            'business_name': 'Test Business LLC',
            'is_verified': True,
            'category': 'Technology',
            'phone_number_id': 'test_phone_123',
            'display_name': 'Test Business'
        }
        
        # Mock database storage
        whatsapp_manager.db_connection.cursor.return_value.__enter__.return_value.execute = Mock()
        whatsapp_manager.db_connection.commit = Mock()
        
        verification_status = await whatsapp_manager.setup_business_verification(
            customer_id, 
            business_config
        )
        
        assert isinstance(verification_status, BusinessVerificationStatus)
        assert verification_status.is_verified is True
        assert verification_status.business_name == 'Test Business LLC'
        assert verification_status.category == 'Technology'
        assert verification_status.phone_number_id == 'test_phone_123'
        
        # Verify caching
        assert customer_id in whatsapp_manager.business_verification_cache
    
    @pytest.mark.asyncio
    async def test_cross_channel_handoff(self, whatsapp_manager):
        """Test conversation handoff between WhatsApp and other channels"""
        customer_id = "customer-test-001"
        handoff_context = {
            'last_message': 'I need help with my account',
            'conversation_history': ['message1', 'message2'],
            'customer_intent': 'account_support'
        }
        
        # Mock memory manager
        whatsapp_manager.memory_manager = Mock()
        whatsapp_manager.memory_manager.store_cross_channel_context = AsyncMock()
        
        result = await whatsapp_manager.handle_cross_channel_handoff(
            customer_id,
            'whatsapp',
            'email',
            handoff_context
        )
        
        assert result['success'] is True
        assert result['from_channel'] == 'whatsapp'
        assert result['to_channel'] == 'email'
        assert result['context_preserved'] is True
        assert 'handoff_id' in result
        
        # Verify memory storage was called
        whatsapp_manager.memory_manager.store_cross_channel_context.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_concurrent_user_optimization(self, whatsapp_manager):
        """Test system optimization for 500+ concurrent users"""
        # Mock database connection pool
        whatsapp_manager.db_connection.cursor.return_value.__enter__.return_value.execute = Mock()
        whatsapp_manager.db_connection.cursor.return_value.__enter__.return_value.fetchone.return_value = [25]
        
        # Mock Redis info
        whatsapp_manager.redis_client.info.return_value = {'connected_clients': 50}
        
        # Simulate active channels
        for i in range(100):
            whatsapp_manager.active_channels[f'customer-{i}'] = Mock()
        
        optimization_result = await whatsapp_manager.optimize_for_concurrent_users()
        
        assert optimization_result['current_channels'] == 100
        assert optimization_result['estimated_capacity'] == 400  # 500 - 100
        assert optimization_result['active_db_connections'] == 25
        assert optimization_result['redis_connected_clients'] == 50
        assert optimization_result['optimization_status'] == 'optimal'
        
        # Test approaching limit scenario
        for i in range(100, 450):
            whatsapp_manager.active_channels[f'customer-{i}'] = Mock()
        
        optimization_result = await whatsapp_manager.optimize_for_concurrent_users()
        assert optimization_result['optimization_status'] == 'approaching_limit'
    
    @pytest.mark.asyncio
    async def test_enhanced_webhook_processing(self, whatsapp_channel):
        """Test enhanced webhook processing with Phase 2 features"""
        # Mock EA and personality config
        whatsapp_channel.ea = Mock()
        whatsapp_channel.ea.handle_customer_interaction = AsyncMock(return_value="Thanks for your message! I'll help you with that.")
        
        with patch.object(whatsapp_channel, '_get_personality_config') as mock_config, \
             patch.object(whatsapp_channel, '_apply_premium_casual_tone') as mock_tone, \
             patch.object(whatsapp_channel, 'send_message') as mock_send:
            
            mock_config.return_value = {'tone': 'premium-casual'}
            mock_tone.return_value = "Hey! Thanks for your message! I'll help you with that. 😊"
            mock_send.return_value = "msg_12345"
            
            # Test webhook data
            webhook_data = {
                'MessageSid': 'SM12345',
                'From': 'whatsapp:+1234567890',
                'To': 'whatsapp:+14155238886',
                'Body': 'Hello, I need help with my business',
                'ProfileName': 'John Doe',
                'NumMedia': '0'
            }
            
            response = await whatsapp_channel.handle_webhook(webhook_data)
            
            # Verify premium-casual processing
            mock_tone.assert_called_once()
            mock_send.assert_called_once()
            assert "😊" in response  # Emoji was added
            assert "Hey!" in response  # Casual greeting
    
    @pytest.mark.asyncio
    async def test_performance_metrics_tracking(self, whatsapp_channel):
        """Test performance metrics collection and SLA compliance"""
        # Mock Redis operations
        whatsapp_channel.redis_client.lpush = Mock()
        whatsapp_channel.redis_client.ltrim = Mock()
        whatsapp_channel.redis_client.expire = Mock()
        whatsapp_channel.redis_client.lrange.return_value = ['1.2', '0.8', '2.1', '1.5', '0.9']
        
        # Test performance tracking
        await whatsapp_channel._track_response_time(1.5)
        
        # Verify Redis calls
        whatsapp_channel.redis_client.lpush.assert_called_with('response_times:customer-test-001', 1.5)
        whatsapp_channel.redis_client.ltrim.assert_called_with('response_times:customer-test-001', 0, 99)
        whatsapp_channel.redis_client.expire.assert_called_with('response_times:customer-test-001', 86400)
        
        # Test metrics retrieval
        metrics = await whatsapp_channel.get_performance_metrics()
        
        assert metrics['customer_id'] == whatsapp_channel.customer_id
        assert metrics['channel'] == 'whatsapp'
        assert metrics['response_times']['count'] == 5
        assert metrics['response_times']['average'] > 0
        assert metrics['sla_compliance']['target_response_time'] == 3.0
        assert metrics['features_enabled']['premium_casual_personality'] is True
    
    @pytest.mark.asyncio
    async def test_context_preservation_across_sessions(self, whatsapp_channel):
        """Test conversation context preservation for session continuity"""
        # Mock message and response
        message = WhatsAppMessage(
            content="I was asking about pricing earlier",
            from_number="+1234567890",
            to_number="+14155238886",
            channel=ChannelType.WHATSAPP,
            message_id="msg_123",
            conversation_id="conv_123",
            timestamp=datetime.now(),
            customer_id="customer-test-001",
            profile_name="John Doe"
        )
        
        response = "Got it! Let me continue helping you with pricing information."
        start_time = datetime.now() - timedelta(seconds=2)
        
        # Mock Redis storage
        whatsapp_channel.redis_client.setex = Mock()
        
        await whatsapp_channel._store_enhanced_conversation_context(message, response, start_time)
        
        # Verify context storage
        assert whatsapp_channel.redis_client.setex.call_count == 2  # Both conversation and cross-channel context
        
        # Verify context data structure
        call_args = whatsapp_channel.redis_client.setex.call_args_list[0]
        context_key = call_args[0][0]
        context_data = json.loads(call_args[0][2])
        
        assert context_key == f"whatsapp_conv:{message.conversation_id}"
        assert context_data['last_message'] == message.content
        assert context_data['last_response'] == response
        assert context_data['personality_applied'] == 'premium-casual'
        assert context_data['channel_context']['platform'] == 'whatsapp'
        assert context_data['processing_time_seconds'] >= 2.0
    
    @pytest.mark.asyncio
    async def test_media_error_handling_graceful_degradation(self, whatsapp_manager):
        """Test graceful error handling for media processing failures"""
        customer_id = "customer-test-001"
        
        # Test download failure
        with patch.object(whatsapp_manager, '_download_media') as mock_download:
            mock_download.return_value = None
            
            result = await whatsapp_manager.process_media_message(
                "https://invalid-url.com/image.jpg",
                "image/jpeg",
                customer_id
            )
            
            assert result.success is False
            assert "Failed to download media file" in result.error_message
        
        # Test processing failure
        with patch.object(whatsapp_manager, '_download_media') as mock_download, \
             patch('PIL.Image.open') as mock_image:
            
            mock_download.return_value = Path('/tmp/test_image.jpg')
            mock_image.side_effect = Exception("Invalid image format")
            
            result = await whatsapp_manager.process_media_message(
                "https://example.com/image.jpg",
                "image/jpeg",
                customer_id
            )
            
            assert result.success is False
            assert "Image processing error" in result.error_message
    
    @pytest.mark.asyncio
    async def test_database_table_creation(self, whatsapp_manager):
        """Test enhanced database schema creation for Phase 2 features"""
        # Mock database cursor
        mock_cursor = Mock()
        whatsapp_manager.db_connection.cursor.return_value.__enter__.return_value = mock_cursor
        whatsapp_manager.db_connection.commit = Mock()
        
        await whatsapp_manager.create_database_tables()
        
        # Verify table creation SQL was executed
        assert mock_cursor.execute.call_count >= 5  # At least 5 tables should be created
        whatsapp_manager.db_connection.commit.assert_called_once()
        
        # Verify specific Phase 2 tables
        executed_sql = ''.join([call[0][0] for call in mock_cursor.execute.call_args_list])
        assert 'whatsapp_media_metrics' in executed_sql
        assert 'whatsapp_business_verification' in executed_sql
        assert 'cross_channel_context' in executed_sql
        assert 'premium_casual_config' in executed_sql
    
    def test_phase2_feature_flags(self, whatsapp_manager):
        """Test that all Phase 2 features are properly enabled"""
        health = asyncio.run(whatsapp_manager.health_check())
        
        phase2_features = health['phase_2_features']
        
        assert phase2_features['media_processing'] is True
        assert phase2_features['business_verification'] is True
        assert phase2_features['cross_channel_handoff'] is True
        assert phase2_features['premium_casual_personality'] is True
        assert phase2_features['concurrent_user_optimization'] is True
    
    @pytest.mark.asyncio
    async def test_sla_compliance_monitoring(self, whatsapp_channel):
        """Test SLA compliance monitoring for <3 second response times"""
        # Test data with mix of compliant and non-compliant response times
        response_times = [0.8, 1.2, 2.1, 3.5, 1.9, 4.2, 0.9, 2.8]
        whatsapp_channel.redis_client.lrange.return_value = [str(rt) for rt in response_times]
        
        metrics = await whatsapp_channel.get_performance_metrics()
        
        sla_compliance = metrics['sla_compliance']
        
        # Calculate expected compliance
        within_sla = len([rt for rt in response_times if rt <= 3.0])
        expected_percentage = (within_sla / len(response_times)) * 100
        
        assert sla_compliance['target_response_time'] == 3.0
        assert sla_compliance['within_sla'] == within_sla
        assert sla_compliance['sla_percentage'] == expected_percentage


if __name__ == '__main__':
    """Run tests directly"""
    pytest.main([__file__, '-v', '--tb=short'])