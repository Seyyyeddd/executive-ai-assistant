# EAIA Telegram Interface

A Telegram bot interface for the Executive AI Assistant (EAIA). This bot allows you to interact with the AI assistant through Telegram, handling interrupt flows and providing responses to AI-generated questions and tasks.

![Telegram UI Screenshot](https://user-images.githubusercontent.com/YOUR_GITHUB_ID/telegram-eaia-ui/main/screenshots/telegram-ui-preview.png)

## Features

- ✅ Fetch and manage interrupts from LangGraph API
- ✅ Display various interrupt types (questions, email drafts, notifications, calendar invites)
- ✅ Handle human-in-the-loop responses with intuitive UI
- ✅ Multi-step calendar editing with validation
- ✅ Secure admin-only access
- ✅ Persistent state between bot restarts

## Interrupt Types Supported

| Type | Description | Available Actions |
|------|-------------|------------------|
| Question | Direct questions requiring human input | Respond, Ignore |
| Email Draft | AI-generated email drafts | Approve, Edit, Respond, Reject |
| Notification | FYI notifications from the system | Respond, Ignore |
| Calendar Invite | Meeting scheduling assistance | Approve, Edit, Respond, Reject |

## Prerequisites

- Python 3.8+
- A Telegram bot token (get one from [BotFather](https://t.me/botfather))
- Your Telegram user ID (you can get it from [@userinfobot](https://t.me/userinfobot))
- A running LangGraph API instance with the EAIA backend

## Setup

1. Install the required dependencies:

```bash
pip install -r telegram_ui/requirements.txt
```

2. Set up environment variables:

```bash
# Required
export TELEGRAM_TOKEN="your_telegram_bot_token"
export ADMIN_USER_ID="your_telegram_user_id"

# Optional (defaults to http://127.0.0.1:2024)
export LANGGRAPH_URL="your_langgraph_api_url"

# Optional (if your LangGraph API requires authentication)
export LANGSMITH_API_KEY="your_langsmith_api_key"
```

Alternatively, you can run the bot without setting these environment variables, and you'll be prompted to enter them when starting the bot.

## Running the Bot

```bash
# From the project root directory
python -m telegram_ui.run
```

## Technical Details

The Telegram UI is built with a modular architecture:

- **bot.py**: Main Telegram bot implementation with conversation flows
- **interrupt_client.py**: Client for interacting with LangGraph API
- **message_formatter.py**: Formats LangGraph data for Telegram UI
- **state_manager.py**: Manages conversation state with file-based persistence
- **config.py**: Handles configuration and environment variables

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Future Improvements

- Add support for attachment handling
- Implement notification polling
- Integrate with more messaging platforms
- Add support for multi-user mode

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgements

- Based on the [Executive AI Assistant](https://github.com/langchain-ai/executive-assistant) by LangChain
- Uses [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) for Telegram integration

---

Created by [Your Name] - [Your GitHub Profile](https://github.com/YOUR_GITHUB_HANDLE) 