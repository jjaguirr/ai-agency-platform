"""
Voice Integration Configuration
Centralized configuration management for the voice integration system
"""

import os
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
import yaml
from pathlib import Path

@dataclass
class VoiceIntegrationConfig:
    """Configuration for the voice integration system"""
    
    # API Keys and External Services
    elevenlabs_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    
    # Voice Processing
    whisper_model: str = "base"  # base, small, medium, large
    elevenlabs_model: str = "eleven_multilingual_v2"
    
    # Performance Settings
    response_time_sla: float = 2.0
    max_concurrent_sessions: int = 100
    max_audio_duration: int = 300  # seconds
    
    # Language Support
    supported_languages: List[str] = None
    default_language: str = "en"
    
    # Voice Configuration
    voice_stability: float = 0.75
    voice_similarity_boost: float = 0.8
    voice_style: float = 0.6
    use_speaker_boost: bool = True
    
    # Network and Security
    allowed_origins: List[str] = None
    max_request_size: int = 10 * 1024 * 1024  # 10MB
    rate_limit_requests: int = 60  # per minute
    
    # File Paths
    frontend_path: str = "frontend"
    logs_path: str = "logs"
    temp_path: str = "./temp/voice_integration"
    
    # Database and Memory
    enable_memory_integration: bool = True
    memory_cleanup_interval: int = 3600  # seconds
    conversation_retention_days: int = 30
    
    # Monitoring and Observability
    enable_metrics: bool = True
    metrics_port: int = 9090
    log_level: str = "INFO"
    
    # Development Settings
    debug_mode: bool = False
    enable_cors: bool = True
    reload_on_change: bool = False
    
    def __post_init__(self):
        """Post-initialization processing"""
        if self.supported_languages is None:
            self.supported_languages = ["en", "es"]
        
        if self.allowed_origins is None:
            self.allowed_origins = ["*"] if self.debug_mode else []
        
        # Load from environment variables if not set
        self._load_from_environment()
    
    def _load_from_environment(self):
        """Load configuration from environment variables"""
        env_mappings = {
            "elevenlabs_api_key": "ELEVENLABS_API_KEY",
            "openai_api_key": "OPENAI_API_KEY",
            "whisper_model": "WHISPER_MODEL",
            "response_time_sla": "VOICE_RESPONSE_TIME_SLA",
            "max_concurrent_sessions": "MAX_CONCURRENT_SESSIONS",
            "default_language": "DEFAULT_LANGUAGE",
            "log_level": "LOG_LEVEL",
            "debug_mode": "DEBUG_MODE",
        }
        
        for field_name, env_var in env_mappings.items():
            env_value = os.getenv(env_var)
            if env_value is not None:
                current_value = getattr(self, field_name)
                
                # Type conversion based on current value type
                if isinstance(current_value, bool):
                    setattr(self, field_name, env_value.lower() in ['true', '1', 'yes'])
                elif isinstance(current_value, int):
                    setattr(self, field_name, int(env_value))
                elif isinstance(current_value, float):
                    setattr(self, field_name, float(env_value))
                else:
                    setattr(self, field_name, env_value)
        
        # Handle list environment variables
        origins_env = os.getenv("ALLOWED_ORIGINS")
        if origins_env:
            self.allowed_origins = [origin.strip() for origin in origins_env.split(",")]
        
        languages_env = os.getenv("SUPPORTED_LANGUAGES")
        if languages_env:
            self.supported_languages = [lang.strip() for lang in languages_env.split(",")]
    
    @classmethod
    def from_file(cls, config_path: str) -> "VoiceIntegrationConfig":
        """Load configuration from YAML file"""
        config_file = Path(config_path)
        
        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
        with open(config_file, 'r') as f:
            config_data = yaml.safe_load(f)
        
        return cls(**config_data)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary"""
        return asdict(self)
    
    def to_file(self, config_path: str):
        """Save configuration to YAML file"""
        config_file = Path(config_path)
        config_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(config_file, 'w') as f:
            yaml.dump(self.to_dict(), f, default_flow_style=False, indent=2)
    
    def validate(self) -> List[str]:
        """Validate configuration and return list of issues"""
        issues = []
        
        # Check required API keys for production
        if not self.debug_mode and not self.elevenlabs_api_key:
            issues.append("ElevenLabs API key required for production")
        
        # Validate performance settings
        if self.response_time_sla <= 0:
            issues.append("Response time SLA must be positive")
        
        if self.max_concurrent_sessions <= 0:
            issues.append("Max concurrent sessions must be positive")
        
        if self.max_audio_duration <= 0:
            issues.append("Max audio duration must be positive")
        
        # Validate voice settings
        if not 0 <= self.voice_stability <= 1:
            issues.append("Voice stability must be between 0 and 1")
        
        if not 0 <= self.voice_similarity_boost <= 1:
            issues.append("Voice similarity boost must be between 0 and 1")
        
        if not 0 <= self.voice_style <= 1:
            issues.append("Voice style must be between 0 and 1")
        
        # Validate languages
        valid_languages = {"en", "es", "auto"}
        if not all(lang in valid_languages for lang in self.supported_languages):
            issues.append(f"Unsupported languages. Valid options: {valid_languages}")
        
        if self.default_language not in valid_languages:
            issues.append(f"Default language must be one of: {valid_languages}")
        
        # Validate paths
        paths_to_check = [
            ("frontend_path", self.frontend_path),
            ("logs_path", self.logs_path)
        ]
        
        for path_name, path_value in paths_to_check:
            path_obj = Path(path_value)
            if not path_obj.exists() and not self.debug_mode:
                issues.append(f"{path_name} does not exist: {path_value}")
        
        # Validate network settings
        if self.rate_limit_requests <= 0:
            issues.append("Rate limit requests must be positive")
        
        if self.max_request_size <= 0:
            issues.append("Max request size must be positive")
        
        return issues
    
    def get_voice_config_for_language(self, language: str) -> Dict[str, Any]:
        """Get voice configuration optimized for specific language"""
        base_config = {
            "stability": self.voice_stability,
            "similarity_boost": self.voice_similarity_boost,
            "style": self.voice_style,
            "use_speaker_boost": self.use_speaker_boost,
            "model": self.elevenlabs_model
        }
        
        # Language-specific optimizations
        if language == "es":
            # Spanish often benefits from slightly higher stability
            base_config["stability"] = min(1.0, self.voice_stability + 0.05)
            base_config["similarity_boost"] = min(1.0, self.voice_similarity_boost + 0.05)
        elif language == "en":
            # English can handle slightly more variation
            base_config["style"] = min(1.0, self.voice_style + 0.1)
        
        return base_config
    
    def get_whisper_config(self) -> Dict[str, Any]:
        """Get Whisper configuration"""
        return {
            "model": self.whisper_model,
            "language": None,  # Auto-detect by default
            "word_timestamps": True,
            "condition_on_previous_text": True
        }
    
    def get_performance_config(self) -> Dict[str, Any]:
        """Get performance monitoring configuration"""
        return {
            "response_time_sla": self.response_time_sla,
            "max_concurrent_sessions": self.max_concurrent_sessions,
            "enable_metrics": self.enable_metrics,
            "metrics_port": self.metrics_port
        }
    
    def get_security_config(self) -> Dict[str, Any]:
        """Get security configuration"""
        return {
            "allowed_origins": self.allowed_origins,
            "max_request_size": self.max_request_size,
            "rate_limit_requests": self.rate_limit_requests,
            "enable_cors": self.enable_cors
        }

# Default configurations for different environments

def get_development_config() -> VoiceIntegrationConfig:
    """Get configuration optimized for development"""
    return VoiceIntegrationConfig(
        debug_mode=True,
        log_level="DEBUG",
        reload_on_change=True,
        allowed_origins=["*"],
        enable_cors=True,
        max_concurrent_sessions=10,
        whisper_model="base"  # Faster for development
    )

def get_production_config() -> VoiceIntegrationConfig:
    """Get configuration optimized for production"""
    return VoiceIntegrationConfig(
        debug_mode=False,
        log_level="INFO",
        reload_on_change=False,
        allowed_origins=[],  # Must be explicitly set
        enable_cors=False,
        max_concurrent_sessions=100,
        whisper_model="small",  # Balance of speed and accuracy
        enable_metrics=True,
        memory_cleanup_interval=1800,  # 30 minutes
        conversation_retention_days=30
    )

def get_testing_config() -> VoiceIntegrationConfig:
    """Get configuration optimized for testing"""
    return VoiceIntegrationConfig(
        debug_mode=True,
        log_level="WARNING",  # Reduce noise in tests
        reload_on_change=False,
        allowed_origins=["*"],
        max_concurrent_sessions=5,
        whisper_model="base",
        enable_memory_integration=False,  # Disable for faster tests
        response_time_sla=5.0,  # More lenient for testing
        temp_path="/tmp/voice_integration_test"
    )

# Configuration factory
def create_config(
    environment: str = "development", 
    config_file: Optional[str] = None,
    overrides: Optional[Dict[str, Any]] = None
) -> VoiceIntegrationConfig:
    """
    Create configuration for specified environment
    
    Args:
        environment: "development", "production", "testing", or "custom"
        config_file: Optional YAML configuration file path
        overrides: Optional dictionary of configuration overrides
    
    Returns:
        VoiceIntegrationConfig instance
    """
    
    if config_file:
        config = VoiceIntegrationConfig.from_file(config_file)
    elif environment == "development":
        config = get_development_config()
    elif environment == "production":
        config = get_production_config()
    elif environment == "testing":
        config = get_testing_config()
    else:
        config = VoiceIntegrationConfig()
    
    # Apply overrides
    if overrides:
        for key, value in overrides.items():
            if hasattr(config, key):
                setattr(config, key, value)
    
    # Validate configuration
    issues = config.validate()
    if issues:
        if environment == "production":
            raise ValueError(f"Configuration validation failed: {'; '.join(issues)}")
        else:
            import logging
            logger = logging.getLogger(__name__)
            for issue in issues:
                logger.warning(f"Configuration issue: {issue}")
    
    return config