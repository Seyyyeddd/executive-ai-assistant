#!/usr/bin/env python3
"""
Entry point script for running the EAIA Telegram bot.
"""

import logging
import os
import sys

# Configure basic logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def setup_environment():
    """Setup environment variables if not already set."""
    if not os.environ.get("TELEGRAM_TOKEN"):
        token = input("Please enter your Telegram bot token: ")
        os.environ["TELEGRAM_TOKEN"] = token
    
    # Read ADMIN_USER_ID from .env file if it exists, otherwise prompt
    # This was already loaded by python-dotenv in the main script
    if not os.environ.get("ADMIN_USER_ID"):
        admin_id = input("Please enter your Telegram user ID: ")
        os.environ["ADMIN_USER_ID"] = admin_id
    else:
        logger.info(f"Using ADMIN_USER_ID from environment: {os.environ.get('ADMIN_USER_ID')}")
    
    if not os.environ.get("LANGGRAPH_URL"):
        langgraph_url = input("Please enter your LangGraph API URL [http://127.0.0.1:2024]: ")
        if not langgraph_url:
            langgraph_url = "http://127.0.0.1:2024"
        os.environ["LANGGRAPH_URL"] = langgraph_url
    
    if not os.environ.get("LANGSMITH_API_KEY") and input("Do you have a LangSmith API key? (y/n): ").lower() == "y":
        api_key = input("Please enter your LangSmith API key: ")
        os.environ["LANGSMITH_API_KEY"] = api_key

def main():
    """Main entry point for the bot."""
    try:
        # Setup environment variables
        setup_environment()
        
        # Import the bot (after environment variables are set)
        from .bot import main as bot_main
        
        # Run the bot
        logger.info("Starting EAIA Telegram bot...")
        bot_main()
    
    except KeyboardInterrupt:
        logger.info("Bot was stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 