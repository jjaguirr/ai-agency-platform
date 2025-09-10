#!/usr/bin/env python3
"""
Voice Integration System Runner
Complete deployment script for ElevenLabs voice integration
"""

import asyncio
import logging
import os
import sys
import argparse
from pathlib import Path

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.voice_integration_system import create_voice_integration_system
from src.config.voice_config import create_config

def setup_logging(log_level: str = "INFO", log_file: str = None):
    """Setup logging configuration"""
    logging_config = {
        'level': getattr(logging, log_level.upper()),
        'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        'handlers': []
    }
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(logging_config['format']))
    logging_config['handlers'].append(console_handler)
    
    # File handler if specified
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path)
        file_handler.setFormatter(logging.Formatter(logging_config['format']))
        logging_config['handlers'].append(file_handler)
    
    logging.basicConfig(
        level=logging_config['level'],
        format=logging_config['format'],
        handlers=logging_config['handlers']
    )

def print_banner():
    """Print system banner"""
    banner = """
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║              🎤 AI Agency Platform - Voice Integration System                ║
║                                                                              ║
║                      ElevenLabs + Whisper + EA Integration                   ║
║                           Bilingual Spanish/English                          ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""
    print(banner)

def validate_environment():
    """Validate environment setup"""
    print("🔍 Validating environment...")
    
    issues = []
    
    # Check Python version
    if sys.version_info < (3, 8):
        issues.append(f"Python 3.8+ required (current: {sys.version_info.major}.{sys.version_info.minor})")
    
    # Check required environment variables
    required_env_vars = ["ELEVENLABS_API_KEY"]
    for env_var in required_env_vars:
        if not os.getenv(env_var):
            issues.append(f"Environment variable {env_var} not set")
    
    # Check optional but recommended environment variables
    recommended_env_vars = {
        "OPENAI_API_KEY": "for enhanced EA functionality",
        "WHISPER_MODEL": "for speech recognition model selection"
    }
    
    for env_var, description in recommended_env_vars.items():
        if not os.getenv(env_var):
            print(f"⚠️  Optional: {env_var} not set ({description})")
    
    if issues:
        print("❌ Environment validation failed:")
        for issue in issues:
            print(f"   • {issue}")
        return False
    
    print("✅ Environment validation passed")
    return True

def check_dependencies():
    """Check if required dependencies are installed"""
    print("📦 Checking dependencies...")
    
    required_packages = [
        "elevenlabs",
        "openai",
        "whisper",
        "fastapi",
        "uvicorn",
        "websockets",
        "aiohttp",
        "prometheus_client",
        "pydantic",
        "numpy"
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        print("❌ Missing required packages:")
        for package in missing_packages:
            print(f"   • {package}")
        print("\nInstall with: pip install -r requirements.txt")
        return False
    
    print("✅ All dependencies available")
    return True

def run_system_tests():
    """Run basic system tests"""
    print("🧪 Running system tests...")
    
    try:
        # Test configuration loading
        config = create_config("testing")
        print("✅ Configuration loading")
        
        # Test voice system creation
        voice_system = create_voice_integration_system(config.to_dict())
        print("✅ Voice system creation")
        
        print("✅ Basic system tests passed")
        return True
        
    except Exception as e:
        print(f"❌ System tests failed: {e}")
        return False

async def run_voice_integration_system(args):
    """Run the voice integration system"""
    print_banner()
    
    # Validate environment
    if not validate_environment():
        sys.exit(1)
    
    # Check dependencies
    if not check_dependencies():
        sys.exit(1)
    
    # Run tests if requested
    if args.test:
        if not run_system_tests():
            sys.exit(1)
        print("🎉 All tests passed! System is ready.")
        return
    
    # Setup logging
    setup_logging(
        log_level=args.log_level,
        log_file=args.log_file
    )
    
    logger = logging.getLogger(__name__)
    
    try:
        # Create configuration
        config_overrides = {}
        
        if args.elevenlabs_key:
            config_overrides["elevenlabs_api_key"] = args.elevenlabs_key
        
        if args.whisper_model:
            config_overrides["whisper_model"] = args.whisper_model
        
        if args.max_sessions:
            config_overrides["max_concurrent_sessions"] = args.max_sessions
        
        config = create_config(
            environment=args.environment,
            config_file=args.config,
            overrides=config_overrides
        )
        
        logger.info("Configuration loaded successfully")
        logger.info(f"Environment: {args.environment}")
        logger.info(f"Whisper model: {config.whisper_model}")
        logger.info(f"Max concurrent sessions: {config.max_concurrent_sessions}")
        logger.info(f"Response time SLA: {config.response_time_sla}s")
        
        # Create voice integration system
        voice_system = create_voice_integration_system(config.to_dict())
        
        # Initialize system
        logger.info("Initializing voice integration system...")
        if not await voice_system.initialize():
            logger.error("System initialization failed")
            sys.exit(1)
        
        logger.info("✅ Voice integration system initialized successfully")
        
        # Print system information
        print(f"""
🚀 System Information:
   • Host: {args.host}:{args.port}
   • Environment: {args.environment}
   • Voice Interface: http://{args.host}:{args.port}/
   • API Documentation: http://{args.host}:{args.port}/voice/docs
   • Health Check: http://{args.host}:{args.port}/health
   • Performance Dashboard: http://{args.host}:{args.port}/performance
   • Prometheus Metrics: http://{args.host}:{args.port}/metrics

🎤 Voice Capabilities:
   • Languages: {', '.join(config.supported_languages)}
   • Whisper Model: {config.whisper_model}
   • Response SLA: {config.response_time_sla}s
   • Max Sessions: {config.max_concurrent_sessions}
   
🔧 Press Ctrl+C to gracefully shutdown
""")
        
        # Run server
        await voice_system.run_server(
            host=args.host,
            port=args.port,
            workers=args.workers,
            reload=args.reload
        )
        
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    except Exception as e:
        logger.error(f"System error: {e}")
        sys.exit(1)

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="AI Agency Platform Voice Integration System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Development mode with auto-reload
  python run_voice_system.py --environment development --reload
  
  # Production mode
  python run_voice_system.py --environment production --host 0.0.0.0 --port 8001
  
  # Custom configuration file
  python run_voice_system.py --config config/production.yaml
  
  # Run system tests only
  python run_voice_system.py --test
        """
    )
    
    parser.add_argument(
        "--environment", "-e",
        choices=["development", "production", "testing"],
        default="development",
        help="Environment configuration (default: development)"
    )
    
    parser.add_argument(
        "--config", "-c",
        help="Configuration file path (YAML format)"
    )
    
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)"
    )
    
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=8001,
        help="Port to bind to (default: 8001)"
    )
    
    parser.add_argument(
        "--workers", "-w",
        type=int,
        default=1,
        help="Number of worker processes (default: 1)"
    )
    
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Auto-reload on code changes (development only)"
    )
    
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO)"
    )
    
    parser.add_argument(
        "--log-file",
        help="Log file path (default: console only)"
    )
    
    parser.add_argument(
        "--elevenlabs-key",
        help="ElevenLabs API key (overrides environment variable)"
    )
    
    parser.add_argument(
        "--whisper-model",
        choices=["base", "small", "medium", "large"],
        help="Whisper model to use"
    )
    
    parser.add_argument(
        "--max-sessions",
        type=int,
        help="Maximum concurrent voice sessions"
    )
    
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run system tests and exit"
    )
    
    parser.add_argument(
        "--version",
        action="version",
        version="AI Agency Platform Voice Integration v2.0.0"
    )
    
    args = parser.parse_args()
    
    # Run the system
    asyncio.run(run_voice_integration_system(args))

if __name__ == "__main__":
    main()