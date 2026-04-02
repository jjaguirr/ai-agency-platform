#!/usr/bin/env python3
"""Check health of all platform services."""
import sys
import requests


SERVICES = {
    "Security API": "http://localhost:8083/health",
    "LangFuse": "http://localhost:3000/api/public/health",
}


def check_services():
    """Check all service health endpoints."""
    all_healthy = True
    for name, url in SERVICES.items():
        try:
            r = requests.get(url, timeout=5)
            status = "OK" if r.status_code == 200 else f"HTTP {r.status_code}"
        except requests.ConnectionError:
            status = "UNREACHABLE"
            all_healthy = False
        except Exception as e:
            status = f"ERROR: {e}"
            all_healthy = False
        print(f"  {name}: {status}")

    return all_healthy


if __name__ == "__main__":
    print("AI Agency Platform Health Check")
    print("-" * 40)
    healthy = check_services()
    sys.exit(0 if healthy else 1)
