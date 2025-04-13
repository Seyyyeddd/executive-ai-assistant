"""
Configuration settings for the Telegram UI.
"""

import os
from typing import Dict, Any

# Telegram Bot configuration
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ADMIN_USER_ID = os.environ.get("ADMIN_USER_ID")  # Telegram user ID authorized to use the bot

# LangGraph API configuration - reuse from test_all_interrupts.py
LANGGRAPH_URL = os.environ.get("LANGGRAPH_URL", "http://127.0.0.1:2024")
API_KEY = os.environ.get("LANGSMITH_API_KEY")

# State file for persistent storage
STATE_FILE = "telegram_ui/bot_state.json"

# Polling interval for checking new interrupts (seconds)
POLLING_INTERVAL = 120

def get_config() -> Dict[str, Any]:
    """Return all configuration settings as a dictionary."""
    return {
        "telegram_token": TELEGRAM_TOKEN,
        "admin_user_id": ADMIN_USER_ID,
        "langgraph_url": LANGGRAPH_URL,
        "api_key": API_KEY,
        "state_file": STATE_FILE,
        "polling_interval": POLLING_INTERVAL
    }

def validate_config() -> bool:
    """Validate that all required configuration settings are present."""
    if not TELEGRAM_TOKEN:
        print("❌ TELEGRAM_TOKEN environment variable is not set")
        return False
    
    if not ADMIN_USER_ID:
        print("❌ ADMIN_USER_ID environment variable is not set")
        return False
    
    if not LANGGRAPH_URL:
        print("⚠️ LANGGRAPH_URL is not set, using default: http://127.0.0.1:2024")
    
    return True 