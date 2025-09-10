#!/usr/bin/env python3
"""
Start the chat demo server
"""

import os
import sys
import subprocess
import webbrowser
import time

def check_dependencies():
    """Check if required packages are installed"""
    try:
        import fastapi
        import uvicorn
        print("✅ FastAPI dependencies found")
        return True
    except ImportError:
        print("❌ Missing dependencies. Installing...")
        subprocess.run([sys.executable, "-m", "pip", "install", "fastapi", "uvicorn[standard]"])
        return True

def start_server():
    """Start the FastAPI server"""
    print("🚀 Starting AI Agency Chat Demo...")
    
    # Check dependencies
    check_dependencies()
    
    # Start server
    os.chdir(os.path.dirname(__file__))
    
    try:
        import uvicorn
        from api.chat_api import app
        
        print("✅ Starting server on http://localhost:8000")
        print("✅ Chat UI available at http://localhost:8000/static/chat/")
        
        # Open browser after a short delay
        def open_browser():
            time.sleep(2)
            webbrowser.open("http://localhost:8000/static/chat/")
        
        import threading
        threading.Thread(target=open_browser, daemon=True).start()
        
        # Start server
        uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
        
    except KeyboardInterrupt:
        print("\n👋 Chat demo stopped")
    except Exception as e:
        print(f"❌ Error starting server: {e}")
        print("\nTrying alternative startup method...")
        
        # Fallback to subprocess
        subprocess.run([
            sys.executable, "-m", "uvicorn", 
            "api.chat_api:app", 
            "--host", "0.0.0.0", 
            "--port", "8000", 
            "--reload"
        ])

if __name__ == "__main__":
    start_server()