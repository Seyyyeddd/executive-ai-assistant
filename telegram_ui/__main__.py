#!/usr/bin/env python3
"""
Main entry point for the telegram_ui package.
Loads environment variables from .env file and runs the bot.
"""

import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def main():
    """Main function to load environment and start the bot."""
    try:
        # Load .env file from project root
        env_path = Path(__file__).parent.parent / '.env'
        if env_path.exists():
            logger.info(f"Loading environment from {env_path}")
            load_dotenv(dotenv_path=env_path)
            logger.info("Environment loaded successfully")
            logger.info(f"ADMIN_USER_ID: {os.environ.get('ADMIN_USER_ID')}")
            logger.info(f"LANGGRAPH_URL: {os.environ.get('LANGGRAPH_URL')}")
        else:
            logger.warning(f".env file not found at {env_path}")
        
        # Import and run the bot
        from telegram_ui.run import main as run_main
        run_main()
    
    except KeyboardInterrupt:
        logger.info("Bot was stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 