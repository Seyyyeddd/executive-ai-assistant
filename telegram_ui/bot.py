"""
Telegram bot for interacting with the EAIA system.
Handles fetching interrupts from LangGraph API and sending user responses.
"""

import asyncio
import logging
import json
import os
import html
from typing import Dict, List, Any, Optional, Union, Tuple
import sys
from datetime import datetime

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

# Import local modules
from .config import validate_config, get_config
from .state_manager import StateManager
from .message_formatter import (
    format_interrupt_message, 
    create_response_keyboard,
    parse_callback_data
)
from .interrupt_client import InterruptClient

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class EAIABot:
    """
    Telegram bot for the Executive AI Assistant (EAIA).
    Handles fetching and responding to interrupts from LangGraph.
    """
    
    def __init__(self):
        """Initialize the bot with configuration and components."""
        # Validate configuration
        if not validate_config():
            logger.error("Invalid configuration. Please check your environment variables.")
            sys.exit(1)
        
        # Load configuration
        self.config = get_config()
        
        # Initialize components
        self.state_manager = StateManager(self.config["state_file"])
        self.interrupt_client = InterruptClient()
        
        # Create the application
        self.application = Application.builder().token(self.config["telegram_token"]).build()
        
        # Add handlers
        self._add_handlers()
    
    def _add_handlers(self) -> None:
        """Add command and message handlers to the application."""
        # Command handlers
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("help", self.cmd_help))
        self.application.add_handler(CommandHandler("check", self.cmd_check))
        
        # Callback query handler for buttons
        self.application.add_handler(CallbackQueryHandler(self.button_callback))
        
        # Message handler for text messages
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        
        # Add error handler
        self.application.add_error_handler(self.error_handler)
        
        # Set up commands for the menu
        self.application.post_init = self.post_init
    
    async def post_init(self, application: Application) -> None:
        """Set up bot commands after initialization."""
        commands = [
            BotCommand("start", "Start the bot"),
            BotCommand("check", "Check for new interrupts"),
            BotCommand("help", "Show help information")
        ]
        await application.bot.set_my_commands(commands)
        logger.info("Bot commands have been set up")
    
    def run(self) -> None:
        """Start the bot."""
        # Start the Bot
        self.application.run_polling()
    
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send a message when the command /start is issued."""
        user_id = update.effective_user.id
        
        # Check if user is authorized
        if str(user_id) != self.config["admin_user_id"]:
            await update.message.reply_text("Sorry, you are not authorized to use this bot.")
            return
            
        await update.message.reply_text(
            "👋 Welcome to the Executive AI Assistant!\n\n"
            "I'll notify you when there are any tasks that require your input.\n\n"
            "Commands:\n"
            "/check - Check for new interrupts\n"
            "/help - Show this help menu"
        )
    
    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send a message when the command /help is issued."""
        await update.message.reply_text(
            "📋 Executive AI Assistant Commands:\n\n"
            "/check - Check for new interrupts\n"
            "/help - Show this help menu"
        )
    
    async def cmd_check(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Check for new interrupts from LangGraph."""
        user_id = update.effective_user.id
        
        # Check if user is authorized
        if str(user_id) != self.config["admin_user_id"]:
            await update.message.reply_text("Sorry, you are not authorized to use this bot.")
            return
        
        # Send typing indicator
        await update.message.reply_chat_action("typing")
        
        # Get interrupted threads
        status_message = await update.message.reply_text("Checking for interrupts...")
        
        try:
            # Get all interrupted threads
            thread_data_list = self.interrupt_client.get_interrupts()
            
            if not thread_data_list:
                await status_message.edit_text("No interrupts found. All tasks are proceeding normally.")
                return
            
            # Update status message
            await status_message.edit_text(f"Found {len(thread_data_list)} interrupt(s). Processing...")
            
            # Process each interrupt and send as a message
            sent_count = 0
            for thread_data in thread_data_list:
                thread_id = thread_data["thread_id"]
                
                # Add/update the interrupt in state 
                self.state_manager.add_interrupt(thread_id, thread_data)
                
                try:
                    # Format the message
                    message_text = format_interrupt_message(thread_data)
                    
                    # Create keyboard buttons
                    reply_markup = create_response_keyboard(thread_data["action_type"], thread_id)
                    
                    # Send the message with inline keyboard
                    message = await context.bot.send_message(
                        chat_id=user_id,
                        text=message_text,
                        reply_markup=reply_markup,
                        parse_mode="HTML"
                    )
                    
                    # Update interrupt status to 'sent' with message ID
                    self.state_manager.update_interrupt_status(
                        thread_id, 
                        "sent", 
                        message_id=message.message_id, 
                        chat_id=user_id
                    )
                    
                    sent_count += 1
                except Exception as e:
                    logger.error(f"Error sending message for thread {thread_id}: {e}")
                    # Try with a simplified message if we encounter HTML formatting errors
                    try:
                        simple_message = f"Thread {thread_id[:8]}: {thread_data['action_type']}\n\n"
                        simple_message += "I couldn't properly format this message. Please check logs for details."
                        
                        message = await context.bot.send_message(
                            chat_id=user_id,
                            text=simple_message,
                            reply_markup=reply_markup
                        )
                        
                        self.state_manager.update_interrupt_status(
                            thread_id, 
                            "sent", 
                            message_id=message.message_id, 
                            chat_id=user_id
                        )
                        
                        sent_count += 1
                    except Exception as inner_e:
                        logger.error(f"Failed to send simplified message: {inner_e}")
            
            # Update the last checked timestamp
            self.state_manager.update_last_checked()
            
            # If we've processed all threads, update the status message
            if sent_count > 0:
                await status_message.edit_text(
                    f"✅ Processed {sent_count} interrupt(s). Please respond to each one."
                )
            else:
                await status_message.edit_text("No actionable interrupts found.")
        
        except Exception as e:
            logger.error(f"Error checking interrupts: {e}")
            await status_message.edit_text(f"❌ Error checking interrupts: {str(e)}")
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle button press callbacks."""
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        
        # Check if user is authorized
        if str(user_id) != self.config["admin_user_id"]:
            await query.edit_message_text("Sorry, you are not authorized to perform this action.")
            return
        
        # Parse the callback data
        action, thread_id = parse_callback_data(query.data)
        logger.debug(f"Button pressed: action={action}, thread_id={thread_id}")
        
        # Get the interrupt data from state
        interrupt = self.state_manager.get_interrupt(thread_id)
        if not interrupt:
            logger.error(f"Interrupt not found: thread_id={thread_id}")
            await query.edit_message_text("This interrupt is no longer active or has expired.")
            return
        
        thread_data = interrupt["data"]
        
        # Handle different button actions
        if action == "ignore":
            # Handle ignore action
            await self._process_ignore_response(query, context, thread_id, thread_data)
            
        elif action == "accept":
            # Handle accept action
            await self._process_accept_response(query, context, thread_id, thread_data)
            
        elif action == "respond":
            # Start conversation to get user's text response
            self.state_manager.set_user_state(user_id, "awaiting_response", {
                "thread_id": thread_id,
                "response_type": "response"
            })
            
            # Edit message to show we're waiting for a response
            try:
                await query.edit_message_text(
                    f"{query.message.text}\n\n<b>✏️ Please type your response:</b>",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Error editing message: {e}")
                # Try without HTML if there's a parsing error
                await query.edit_message_text(
                    f"{query.message.text}\n\n✏️ Please type your response:"
                )
            
        elif action == "edit":
            # Start conversation to get user's edit
            self.state_manager.set_user_state(user_id, "awaiting_response", {
                "thread_id": thread_id,
                "response_type": "edit"
            })
            
            try:
                await query.edit_message_text(
                    f"{query.message.text}\n\n<b>✏️ Please provide your edited version:</b>",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Error editing message: {e}")
                # Try without HTML if there's a parsing error
                await query.edit_message_text(
                    f"{query.message.text}\n\n✏️ Please provide your edited version:"
                )
            
        elif action == "edit_calendar":
            # Start step-by-step calendar editing flow
            logger.info(f"Starting calendar edit flow for thread_id={thread_id}")
            
            # Double check thread_id format
            if not thread_id or len(thread_id) < 8:
                logger.error(f"Invalid thread_id format: '{thread_id}' from callback data: '{query.data}'")
                await query.edit_message_text(
                    f"{query.message.text}\n\n<b>❌ Error: Invalid thread ID format.</b>",
                    parse_mode="HTML"
                )
                return
                
            # Check if calendar_invite exists in thread_data
            if "calendar_invite" not in thread_data or not thread_data["calendar_invite"]:
                logger.error(f"Calendar data missing for thread_id={thread_id}")
                await query.edit_message_text(
                    f"{query.message.text}\n\n<b>❌ Error: Calendar data is missing or invalid.</b>",
                    parse_mode="HTML"
                )
                return
                
            current_calendar = thread_data["calendar_invite"]
            
            # Initialize calendar editing state with default values for safety
            self.state_manager.set_user_state(user_id, "calendar_edit", {
                "thread_id": thread_id,
                "step": "title",
                "current_data": {
                    "title": current_calendar.get("title", ""),
                    "start_time": current_calendar.get("start_time", ""),
                    "end_time": current_calendar.get("end_time", ""),
                    "emails": current_calendar.get("emails", [])
                }
            })
            
            # IMPORTANT: Also set awaiting_response state so handle_message will recognize this as an active conversation
            self.state_manager.set_user_state(user_id, "awaiting_response", {
                "thread_id": thread_id,
                "response_type": "calendar_edit_flow"
            })
            
            # Show the title editing prompt
            current_title = current_calendar.get("title", "No title")
            try:
                await query.edit_message_text(
                    f"{query.message.text}\n\n<b>Step 1/3: Edit Meeting Title</b>\n\n"
                    f"Current title: <i>{html.escape(current_title)}</i>\n\n"
                    f"Please enter the new meeting title or type <code>/keep</code> to keep the current title:",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Error editing message: {e}")
                # Try without HTML if there's a parsing error
                await query.edit_message_text(
                    f"{query.message.text}\n\nStep 1/3: Edit Meeting Title\n\n"
                    f"Current title: {current_title}\n\n"
                    f"Please enter the new meeting title or type /keep to keep the current title:"
                )
    
    async def _process_ignore_response(self, query, context, thread_id, thread_data):
        """Process an ignore response."""
        action_type = thread_data["action_type"]
        
        # Send the response to LangGraph
        success = self.interrupt_client.send_response(
            thread_id=thread_id,
            response_type="ignore",
            response_content="",
            action_type=action_type
        )
        
        if success:
            # Update the message to show it was ignored
            try:
                await query.edit_message_text(
                    f"{query.message.text}\n\n<b>✅ Ignored successfully</b>",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Error editing message: {e}")
                # Try without HTML if there's a parsing error
                await query.edit_message_text(
                    f"{query.message.text}\n\n✅ Ignored successfully"
                )
            
            # Update the interrupt status in state
            self.state_manager.update_interrupt_status(thread_id, "completed")
        else:
            try:
                await query.edit_message_text(
                    f"{query.message.text}\n\n<b>❌ Failed to ignore. Please try again.</b>",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Error editing message: {e}")
                # Try without HTML if there's a parsing error
                await query.edit_message_text(
                    f"{query.message.text}\n\n❌ Failed to ignore. Please try again."
                )
    
    async def _process_accept_response(self, query, context, thread_id, thread_data):
        """Process an accept response."""
        action_type = thread_data["action_type"]
        
        # Send the response to LangGraph
        success = self.interrupt_client.send_response(
            thread_id=thread_id,
            response_type="accept",
            response_content="",
            action_type=action_type
        )
        
        if success:
            # Update the message to show it was accepted
            try:
                await query.edit_message_text(
                    f"{query.message.text}\n\n<b>✅ Approved successfully</b>",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Error editing message: {e}")
                # Try without HTML if there's a parsing error
                await query.edit_message_text(
                    f"{query.message.text}\n\n✅ Approved successfully"
                )
            
            # Update the interrupt status in state
            self.state_manager.update_interrupt_status(thread_id, "completed")
        else:
            try:
                await query.edit_message_text(
                    f"{query.message.text}\n\n<b>❌ Failed to approve. Please try again.</b>",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Error editing message: {e}")
                # Try without HTML if there's a parsing error
                await query.edit_message_text(
                    f"{query.message.text}\n\n❌ Failed to approve. Please try again."
                )
    
    async def _process_text_response(self, query, context, thread_id, thread_data, text, response_type):
        """Process a text response or edit."""
        action_type = thread_data["action_type"]
        
        # Send the response to LangGraph
        success = self.interrupt_client.send_response(
            thread_id=thread_id,
            response_type=response_type,
            response_content=text,
            action_type=action_type
        )
        
        if success:
            # Determine success message based on response type
            success_message = "✅ Response sent successfully"
            if response_type == "edit":
                success_message = "✅ Edit submitted successfully"
            
            # HTML escape the text to prevent parsing errors
            safe_text = html.escape(text)
            
            # Update the message to show the response was sent
            try:
                await query.edit_message_text(
                    f"{query.message.text}\n\n<b>{success_message}</b>\n\nYour response:\n{safe_text}",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Error editing message: {e}")
                # Try without HTML if there's a parsing error
                await query.edit_message_text(
                    f"{query.message.text}\n\n{success_message}\n\nYour response:\n{text}"
                )
            
            # Update the interrupt status in state
            self.state_manager.update_interrupt_status(thread_id, "completed")
        else:
            try:
                await query.edit_message_text(
                    f"{query.message.text}\n\n<b>❌ Failed to send response. Please try again.</b>",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Error editing message: {e}")
                # Try without HTML if there's a parsing error
                await query.edit_message_text(
                    f"{query.message.text}\n\n❌ Failed to send response. Please try again."
                )
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle user messages."""
        user_id = update.effective_user.id
        
        # Check if user is authorized
        if str(user_id) != self.config["admin_user_id"]:
            await update.message.reply_text("Sorry, you are not authorized to use this bot.")
            return
        
        # Check if we're waiting for a response
        awaiting_response = self.state_manager.get_user_state(user_id, "awaiting_response")
        calendar_edit = self.state_manager.get_user_state(user_id, "calendar_edit")
        
        logger.debug(f"Message received with states: awaiting_response={bool(awaiting_response)}, calendar_edit={bool(calendar_edit)}")
        
        if awaiting_response:
            logger.debug(f"Processing response: type={awaiting_response.get('response_type')}")
            await self._process_awaited_response(update, context, awaiting_response)
        else:
            # Recovery for orphaned calendar edit states
            if calendar_edit:
                logger.warning(f"Recovering orphaned calendar edit session")
                try:
                    synthetic_response = {
                        "thread_id": calendar_edit["thread_id"],
                        "response_type": "calendar_edit_flow"
                    }
                    self.state_manager.set_user_state(user_id, "awaiting_response", synthetic_response)
                    await self._process_awaited_response(update, context, synthetic_response)
                    return
                except Exception as e:
                    logger.error(f"Failed to recover session: {e}")
                    self.state_manager.set_user_state(user_id, "calendar_edit", None)
            
            # Default response
            await update.message.reply_text(
                "I'm waiting for interrupts from your AI Assistant. Use /check to check for new interrupts."
            )
    
    async def _process_awaited_response(self, update, context, awaiting_response):
        """Process a response that was awaited."""
        user_id = update.effective_user.id
        text = update.message.text
        thread_id = awaiting_response["thread_id"]
        response_type = awaiting_response["response_type"]
        
        # Special case for calendar editing flow
        if response_type == "calendar_edit_flow":
            calendar_edit = self.state_manager.get_user_state(user_id, "calendar_edit")
            if calendar_edit and calendar_edit["thread_id"] == thread_id:
                logger.info(f"Continuing calendar edit flow for thread_id={thread_id}")
                await self._process_calendar_edit_step(update, context, calendar_edit)
                return
            else:
                logger.error(f"Calendar edit state missing but awaiting calendar edit response for thread_id={thread_id}")
                self.state_manager.set_user_state(user_id, "awaiting_response", None)
                await update.message.reply_text("Error: Calendar editing session expired. Please try again.")
                return
                
        # Check for calendar edit flow (backward compatibility)
        calendar_edit = self.state_manager.get_user_state(user_id, "calendar_edit")
        if calendar_edit and calendar_edit["thread_id"] == thread_id:
            await self._process_calendar_edit_step(update, context, calendar_edit)
            return
            
        # Clear the awaiting response state
        self.state_manager.set_user_state(user_id, "awaiting_response", None)
        
        # Get the interrupt from state
        interrupt = self.state_manager.get_interrupt(thread_id)
        if not interrupt:
            await update.message.reply_text("This interrupt is no longer active or has expired.")
            return
        
        thread_data = interrupt["data"]
        
        # Send typing indicator
        await update.message.reply_chat_action("typing")
        
        try:
            # Process different response types
            if response_type == "edit_calendar":
                # Try to parse the calendar edit as JSON
                try:
                    # Parse the user's JSON input
                    calendar_data = json.loads(text)
                    
                    # Validate the required fields
                    validation_errors = []
                    if not calendar_data.get("title"):
                        validation_errors.append("Meeting title is required")
                    
                    # Validate time formats
                    for time_field in ["start_time", "end_time"]:
                        if not calendar_data.get(time_field):
                            validation_errors.append(f"{time_field.replace('_', ' ').title()} is required")
                        else:
                            # Check time format
                            try:
                                datetime.fromisoformat(calendar_data[time_field])
                            except (ValueError, TypeError):
                                validation_errors.append(f"{time_field.replace('_', ' ').title()} must be in ISO format (YYYY-MM-DDThh:mm:ss)")
                    
                    # Validate emails
                    if not calendar_data.get("emails") or not isinstance(calendar_data["emails"], list):
                        validation_errors.append("Emails must be a list of email addresses")
                    elif not all(isinstance(email, str) for email in calendar_data["emails"]):
                        validation_errors.append("All emails must be strings")
                    
                    # If validation fails, return with errors
                    if validation_errors:
                        await update.message.reply_text(
                            "❌ Calendar data validation failed:\n• " + "\n• ".join(validation_errors) + 
                            "\n\nPlease try again with valid data."
                        )
                        return
                    
                    # Format as a proper JSON string for the API
                    text = json.dumps(calendar_data)
                    response_type = "edit"
                except json.JSONDecodeError:
                    await update.message.reply_text(
                        "❌ Invalid calendar data format. Please provide valid JSON."
                    )
                    return
            
            # Determine the correct response type
            api_response_type = "response" if response_type in ["response", "respond"] else "edit"
            
            # Send the response to LangGraph
            success = self.interrupt_client.send_response(
                thread_id=thread_id,
                response_type=api_response_type,
                response_content=text,
                action_type=thread_data["action_type"]
            )
            
            if success:
                # Format success message based on response type
                if api_response_type == "response":
                    success_message = "✅ Response sent successfully"
                else:
                    success_message = "✅ Edit submitted successfully"
                
                # HTML escape the text to prevent parsing errors
                safe_text = html.escape(text)
                
                try:
                    await update.message.reply_text(
                        f"<b>{success_message}</b>\n\nYour response:\n{safe_text}",
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.error(f"Error sending response message: {e}")
                    # Try without HTML if there's a parsing error
                    await update.message.reply_text(
                        f"{success_message}\n\nYour response:\n{text}"
                    )
                
                # Update the interrupt status in state
                self.state_manager.update_interrupt_status(thread_id, "completed")
                
            else:
                await update.message.reply_text(
                    "❌ Failed to send response to LangGraph. Please try again."
                )
        
        except Exception as e:
            logger.error(f"Error processing response: {e}")
            await update.message.reply_text(f"❌ Error: {str(e)}")
    
    async def _process_calendar_edit_step(self, update, context, calendar_edit):
        """Process a step in the calendar editing flow."""
        user_id = update.effective_user.id
        text = update.message.text
        thread_id = calendar_edit["thread_id"]
        current_step = calendar_edit["step"]
        current_data = calendar_edit["current_data"]
        
        logger.info(f"Processing calendar edit step: {current_step} for thread_id={thread_id}")
        
        # Get the interrupt from state
        interrupt = self.state_manager.get_interrupt(thread_id)
        if not interrupt:
            logger.error(f"Interrupt not found in calendar edit step: thread_id={thread_id}, step={current_step}")
            await update.message.reply_text("This interrupt is no longer active or has expired.")
            self.state_manager.set_user_state(user_id, "calendar_edit", None)
            return
            
        thread_data = interrupt["data"]
        
        # User can cancel at any step
        if text.lower() == "/cancel":
            self.state_manager.set_user_state(user_id, "calendar_edit", None)
            self.state_manager.set_user_state(user_id, "awaiting_response", None)
            await update.message.reply_text("Calendar editing cancelled.")
            return
            
        # Process current step and move to next
        if current_step == "title":
            # Handle title step
            if text.lower() == "/keep":
                # Keep current title
                pass
            else:
                # Update title
                current_data["title"] = text
                
            # Move to date/time step
            self.state_manager.set_user_state(user_id, "calendar_edit", {
                "thread_id": thread_id,
                "step": "datetime",
                "current_data": current_data
            })
            
            # Also update awaiting_response to maintain the flow
            self.state_manager.set_user_state(user_id, "awaiting_response", {
                "thread_id": thread_id,
                "response_type": "calendar_edit_flow"
            })
            
            # Format current date/time for display
            start_time = current_data["start_time"]
            end_time = current_data["end_time"]
            
            # Show date/time format examples based on current values
            format_example = "YYYY-MM-DDThh:mm:ss"
            if start_time:
                try:
                    dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                    format_example = dt.strftime("%Y-%m-%dT%H:%M:%S")
                except:
                    pass
                    
            await update.message.reply_text(
                f"<b>Step 2/3: Edit Date and Time</b>\n\n"
                f"Current start: <i>{start_time}</i>\n"
                f"Current end: <i>{end_time}</i>\n\n"
                f"Please enter the new date and time in this format:\n"
                f"<code>START_TIME | END_TIME</code>\n\n"
                f"Example: <code>{format_example} | {format_example}</code>\n\n"
                f"Or type <code>/keep</code> to keep the current date/time.",
                parse_mode="HTML"
            )
                
        elif current_step == "datetime":
            # Handle date/time step
            if text.lower() == "/keep":
                # Keep current date/time
                pass
            else:
                # Try to parse start and end times
                try:
                    parts = [part.strip() for part in text.split("|")]
                    if len(parts) != 2:
                        await update.message.reply_text(
                            "❌ Please provide both start and end times separated by |.\n"
                            "Example: 2024-04-16T14:00:00 | 2024-04-16T15:00:00\n\n"
                            "Please try again:"
                        )
                        return
                        
                    start_time, end_time = parts
                    
                    # Validate times
                    try:
                        start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                        end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                        
                        # Check if end is after start
                        if end_dt <= start_dt:
                            await update.message.reply_text(
                                "❌ End time must be after start time.\n\n"
                                "Please try again:"
                            )
                            return
                            
                        # Update date/time
                        current_data["start_time"] = start_time
                        current_data["end_time"] = end_time
                    except ValueError:
                        await update.message.reply_text(
                            "❌ Invalid date/time format. Please use ISO format: YYYY-MM-DDThh:mm:ss\n\n"
                            "Please try again:"
                        )
                        return
                except Exception as e:
                    await update.message.reply_text(
                        f"❌ Error processing date/time: {str(e)}\n\n"
                        "Please try again with format: START_TIME | END_TIME"
                    )
                    return
                    
            # Move to emails step
            self.state_manager.set_user_state(user_id, "calendar_edit", {
                "thread_id": thread_id,
                "step": "emails",
                "current_data": current_data
            })
            
            # Also update awaiting_response to maintain the flow
            self.state_manager.set_user_state(user_id, "awaiting_response", {
                "thread_id": thread_id,
                "response_type": "calendar_edit_flow"
            })
            
            # Format current emails for display
            current_emails = current_data["emails"]
            emails_display = "\n".join([f"• {email}" for email in current_emails]) if current_emails else "None"
            
            await update.message.reply_text(
                f"<b>Step 3/3: Edit Attendees</b>\n\n"
                f"Current attendees:\n{emails_display}\n\n"
                f"Please enter email addresses separated by commas, or type <code>/keep</code> to keep the current attendees:",
                parse_mode="HTML"
            )
                
        elif current_step == "emails":
            # Handle emails step
            if text.lower() == "/keep":
                # Keep current emails
                pass
            else:
                # Parse and validate emails
                emails = [email.strip() for email in text.split(",")]
                
                # Basic email validation
                invalid_emails = []
                for email in emails:
                    if not "@" in email or not "." in email:
                        invalid_emails.append(email)
                        
                if invalid_emails:
                    await update.message.reply_text(
                        f"❌ Invalid email address(es): {', '.join(invalid_emails)}\n\n"
                        "Please enter valid email addresses separated by commas:"
                    )
                    return
                    
                # Update emails
                current_data["emails"] = emails
                
            # Complete the flow and submit the calendar edit
            self.state_manager.set_user_state(user_id, "calendar_edit", None)
            self.state_manager.set_user_state(user_id, "awaiting_response", None)
            
            # Format calendar data for display and confirmation
            display_data = {
                "title": current_data["title"],
                "start_time": current_data["start_time"],
                "end_time": current_data["end_time"],
                "emails": current_data["emails"]
            }
            
            # Show confirmation with the final data
            await update.message.reply_text(
                f"<b>Calendar Editing Complete!</b>\n\n"
                f"Title: {html.escape(display_data['title'])}\n"
                f"Start: {display_data['start_time']}\n"
                f"End: {display_data['end_time']}\n"
                f"Attendees: {', '.join(display_data['emails'])}\n\n"
                f"Submitting your changes...",
                parse_mode="HTML"
            )
            
            # Format calendar data as required by LangGraph API
            calendar_json = json.dumps(display_data)
            
            # Send the edit to LangGraph
            success = self.interrupt_client.send_response(
                thread_id=thread_id,
                response_type="edit",
                response_content=calendar_json,
                action_type=thread_data["action_type"]
            )
            
            if success:
                await update.message.reply_text("✅ Calendar changes submitted successfully!")
                
                # Update the interrupt status in state
                self.state_manager.update_interrupt_status(thread_id, "completed")
            else:
                await update.message.reply_text(
                    "❌ Failed to submit calendar changes. Please try again."
                )
        else:
            # Unknown step
            self.state_manager.set_user_state(user_id, "calendar_edit", None)
            await update.message.reply_text("❌ Unknown calendar editing step. Please try again.")
    
    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle errors in the telegram-python-bot library."""
        logger.error(f"Exception while handling an update: {context.error}")

def main():
    """Entry point for the bot."""
    # Create and run the bot
    bot = EAIABot()
    bot.run()

if __name__ == "__main__":
    main() 