"""
Message formatter for converting LangGraph interrupts to Telegram messages.
Handles formatting different types of interrupts and creating appropriate inline keyboards.
"""

from typing import Dict, List, Any, Tuple
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import html
from datetime import datetime

# Interrupt types from test_all_interrupts.py
INTERRUPT_TYPES = {
    "Question": {
        "description": "A question that requires a direct answer",
        "allowed_responses": ["response", "ignore"],
        "handler_function": "send_message"
    },
    "ResponseEmailDraft": {
        "description": "A draft email requiring approval, edits, or rejection",
        "allowed_responses": ["accept", "edit", "ignore", "response"],
        "handler_function": "send_email_draft"
    },
    "Notify": {
        "description": "A notification requiring acknowledgment or response",
        "allowed_responses": ["response", "ignore"],
        "handler_function": "notify"
    },
    "SendCalendarInvite": {
        "description": "A calendar invite requiring approval, edits, or rejection",
        "allowed_responses": ["accept", "edit", "ignore", "response"],
        "handler_function": "send_cal_invite"
    }
}

def format_datetime(iso_datetime: str) -> str:
    """Format ISO datetime to a more readable format."""
    try:
        # Parse the ISO datetime string
        if not iso_datetime:
            return "not specified"
        
        dt = datetime.fromisoformat(iso_datetime.replace('Z', '+00:00'))
        
        # Format it in a user-friendly way
        return dt.strftime("%B %d, %Y at %I:%M %p")
    except Exception:
        # In case of parsing error, return the original string
        return iso_datetime

def normalize_action_type(action_type: str) -> str:
    """Normalize the action type to one of the defined interrupt types."""
    # Handle empty or unknown values
    if not action_type or action_type == "Unknown":
        return "Unknown"
    
    # Direct match (no changes needed)
    if action_type in INTERRUPT_TYPES:
        return action_type
    
    # Case-insensitive match
    action_lower = action_type.lower()
    for interrupt_type in INTERRUPT_TYPES:
        if interrupt_type.lower() == action_lower:
            return interrupt_type
    
    # Handle common variations
    if action_lower == "question":
        return "Question"
    elif action_lower in ["email", "responseemaildraft", "emaildraft"]:
        return "ResponseEmailDraft"
    elif action_lower == "notify":
        return "Notify"
    elif action_lower in ["invite", "calendar", "sendcalendarinvite"]:
        return "SendCalendarInvite"
    
    # If no match, return as is
    return action_type

def format_interrupt_message(thread_data: Dict[str, Any]) -> str:
    """Format an interrupt as a Telegram message based on its action type."""
    action_type = thread_data["action_type"]
    normalized_action = normalize_action_type(action_type)
    
    # Select icon based on action type
    icon = get_icon_for_action_type(normalized_action)
    
    # Start with a header showing action type
    message = f"{icon} <b>{normalized_action}</b>\n\n"
    
    # Add subject and sender info
    subject = html.escape(thread_data["email_subject"] if thread_data["email_subject"] != "Unknown" else "Email Draft")
    sender = html.escape(thread_data["email_sender"] if thread_data["email_sender"] != "Unknown" else "AI Assistant")
    
    message += f"<b>Subject:</b> {subject}\n"
    message += f"<b>From:</b> {sender}\n"
    
    # Format date if available
    if thread_data["send_time"]:
        try:
            date = format_datetime(thread_data["send_time"])
            message += f"<i>{date}</i>\n"
        except:
            pass
    
    message += "\n"
    
    # Add Gmail link or thread link
    thread_id = thread_data["thread_id"]
    # Use deep links that actually work on mobile devices
    # For Android, intent scheme works better; for iOS we use a different format
    # We'll provide just the web link since it's the most reliable across platforms
    message += f"<a href='https://mail.google.com/'>Open Gmail</a>\n\n"
    
    # Different formatting based on action type
    if normalized_action == "Question":
        # For questions, show the question content
        content = html.escape(thread_data.get('action_content', '') or "No question content available")
        message += f"<b>Question:</b>\n{content}\n"
        
    elif normalized_action == "ResponseEmailDraft":
        # For email drafts, show action content if available
        action_content = html.escape(thread_data.get('action_content', '') or "")
        if action_content:
            message += f"<b>Draft Summary:</b>\n{action_content}\n\n"
        else:
            # If no action content, show a preview of the email content
            email_content = thread_data.get('email_content', '')
            if email_content:
                # Take first 150 characters as preview
                preview = html.escape(email_content[:150] + ('...' if len(email_content) > 150 else ''))
                message += f"<b>Email Preview:</b>\n{preview}\n\n"
        
        message += "Please approve, edit, or reject this email draft."
        
    elif normalized_action == "Notify":
        # For notifications, show the notification content
        content = html.escape(thread_data.get('action_content', '') or "No notification content available")
        message += f"<b>Notification:</b>\n{content}\n"
        
    elif normalized_action == "SendCalendarInvite":
        # Show calendar invite details
        message += "<b>Calendar Invite</b>\n"
        
        calendar_data = thread_data.get('calendar_invite', {})
        title = html.escape(calendar_data.get('title', '') or 'No title')
        message += f"<b>Title:</b> {title}\n"
        
        start_time = format_datetime(calendar_data.get('start_time', '') or "")
        end_time = format_datetime(calendar_data.get('end_time', '') or "")
        
        message += f"<b>Start:</b> {start_time}\n"
        message += f"<b>End:</b> {end_time}\n"
        
        # Format attendees list if present
        if calendar_data.get('emails'):
            attendees = ", ".join([html.escape(email) for email in calendar_data['emails']])
            message += f"<b>Attendees:</b> {attendees}\n\n"
        else:
            message += "\n"
            
        message += "Please approve, edit, or reject this calendar invite."
    
    # Add thread ID for reference (small and at the bottom)
    message += f"\n<i>ID: {thread_id[:8]}</i>"
    
    return message

def get_icon_for_action_type(action_type: str) -> str:
    """Get an appropriate icon for an action type."""
    icons = {
        "Question": "❓",
        "ResponseEmailDraft": "📧",
        "Notify": "🔔",
        "SendCalendarInvite": "📅",
        "Unknown": "⚠️"
    }
    
    return icons.get(action_type, "🔷")

def create_response_keyboard(action_type: str, thread_id: str) -> InlineKeyboardMarkup:
    """Create inline keyboard buttons based on action type."""
    normalized_action = normalize_action_type(action_type)
    keyboard = []
    
    # Different buttons based on action type
    if normalized_action == "Question":
        # For questions, we need a custom response
        keyboard.append([
            InlineKeyboardButton("✏️ Respond", callback_data=f"respond_{thread_id}"),
            InlineKeyboardButton("❌ Ignore", callback_data=f"ignore_{thread_id}")
        ])
        
    elif normalized_action == "ResponseEmailDraft":
        # For email drafts, offer approve, edit, respond, or reject
        row1 = [
            InlineKeyboardButton("✅ Approve", callback_data=f"accept_{thread_id}"),
            InlineKeyboardButton("✏️ Edit", callback_data=f"edit_{thread_id}")
        ]
        row2 = [
            InlineKeyboardButton("💬 Respond", callback_data=f"respond_{thread_id}"),
            InlineKeyboardButton("❌ Ignore", callback_data=f"ignore_{thread_id}")
        ]
        keyboard.append(row1)
        keyboard.append(row2)
        
    elif normalized_action == "Notify":
        # For notifications, only offer respond or ignore to match EAIA configuration
        keyboard.append([
            InlineKeyboardButton("✏️ Respond", callback_data=f"respond_{thread_id}"),
            InlineKeyboardButton("❌ Ignore", callback_data=f"ignore_{thread_id}")
        ])
        
    elif normalized_action == "SendCalendarInvite":
        # For calendar invites, offer approve, edit, respond, or reject
        row1 = [
            InlineKeyboardButton("✅ Approve", callback_data=f"accept_{thread_id}"),
            InlineKeyboardButton("✏️ Edit", callback_data=f"edit_calendar_{thread_id}")
        ]
        row2 = [
            InlineKeyboardButton("💬 Respond", callback_data=f"respond_{thread_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"ignore_{thread_id}")
        ]
        keyboard.append(row1)
        keyboard.append(row2)
    
    return InlineKeyboardMarkup(keyboard)

def parse_callback_data(callback_data: str) -> Tuple[str, str]:
    """Parse callback data into action and thread_id."""
    # Special case for edit_calendar which contains an underscore
    if callback_data.startswith("edit_calendar_"):
        return "edit_calendar", callback_data[len("edit_calendar_"):]
        
    # Regular case - split at first underscore
    parts = callback_data.split('_', 1)
    if len(parts) != 2:
        return "unknown", ""
    
    action, thread_id = parts
    return action, thread_id 