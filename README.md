# AI Email Assistant with Telegram Interface

A powerful AI email assistant built on the Executive AI Assistant framework with a custom Telegram interface for mobile interaction.


## Overview

This project enhances the [Executive AI Assistant](https://github.com/langchain-ai/executive-ai-assistant) framework with a custom Telegram interface, allowing users to:

- Process and triage incoming emails automatically
- Receive AI-generated draft responses for approval
- Handle calendar invites and scheduling
- Manage interrupts and notifications on-the-go
- Interact with the AI assistant through a conversational interface

## Key Features

- 🧠 **AI Email Processing**: Intelligently categorizes, summarizes, and drafts responses to emails
- 📱 **Telegram Interface**: Human-in-the-loop interaction through a mobile-friendly Telegram bot
- 📅 **Calendar Management**: Step-by-step editing and approval of meeting invites
- 🔄 **Seamless Workflow**: Connect your email account once, then manage everything via Telegram
- 🛠️ **Customizable**: Configure email triage rules and personal preferences

## Components

### Core Email Assistant (EAIA)

The project builds on the Executive AI Assistant framework, which includes:

- Email retrieval and parsing
- Smart triage based on configurable rules
- AI-generated draft responses
- Calendar integration for scheduling
- Learning from human feedback

### Telegram Interface

The custom Telegram interface provides:

- Secure access through admin-only authentication
- Interrupt handling for questions, email drafts, notifications, and calendar invites
- Multi-step calendar editing with validation
- Persistent state between sessions
- Clean, intuitive UI for mobile interaction

## Getting Started

### Prerequisites

- Python 3.8+
- Gmail account for email integration
- Telegram account + bot token (get one from [BotFather](https://t.me/botfather))
- Your Telegram user ID (from [@userinfobot](https://t.me/userinfobot))
- LangChain API key

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/YOUR_USERNAME/ai-email-assistant.git
   cd ai-email-assistant
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure environment variables:
   ```bash
   # Copy the template and edit with your values
   cp config.json.template config.json
   ```

4. Set up email authentication:
   ```bash
   python scripts/setup_gmail.py
   ```

5. Start the LangGraph API:
   ```bash
   python -m langgraph.server
   ```

6. In a separate terminal, start the Telegram bot:
   ```bash
   python -m telegram_ui.run
   ```

## Usage

1. Start a chat with your bot on Telegram
2. Send `/start` to initialize the bot
3. Use `/check` to check for new emails requiring attention
4. Respond to different types of interrupts:
   - Questions: Respond or Ignore
   - Email Drafts: Approve, Edit, Respond, or Reject
   - Notifications: Respond or Ignore
   - Calendar Invites: Approve, Edit, Respond, or Reject

## Customization

Edit `eaia/main/config.yaml` to customize:
- Triage rules for handling different email types
- Response preferences and tone
- Schedule preferences
- Background information

## Deployment

For production use, consider:
- Setting up the system as a service
- Configuring scheduled email checking
- Using a dedicated server or cloud instance

See `docs/deployment.md` for detailed deployment instructions.

## Acknowledgments

- Based on the [Executive AI Assistant](https://github.com/langchain-ai/executive-ai-assistant) by LangChain
- Powered by LangGraph for workflow orchestration

---

Built by ([Mohobiz](https://github.com/mohobiz)) 
