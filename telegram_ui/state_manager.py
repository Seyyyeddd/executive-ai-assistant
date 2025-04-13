"""
Simple state management for the Telegram bot.
Handles storing and retrieving interrupt state using JSON.
"""

import json
import os
from typing import Dict, List, Any, Optional
from datetime import datetime

class StateManager:
    """Simple file-based state management for the Telegram bot."""
    
    def __init__(self, state_file: str):
        """Initialize the state manager with the path to the state file."""
        self.state_file = state_file
        self.state = self._load_state()
    
    def _load_state(self) -> Dict[str, Any]:
        """Load state from the state file, or create a new state if file doesn't exist."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                print(f"⚠️ Error decoding state file: {self.state_file}")
                return self._create_initial_state()
        else:
            return self._create_initial_state()
    
    def _create_initial_state(self) -> Dict[str, Any]:
        """Create an initial state structure."""
        return {
            "interrupts": {},  # Map of thread_id -> interrupt data
            "user_state": {},  # Map of user_id -> user state
            "last_checked": None,  # Timestamp of last interrupt check
            "version": 1  # State format version
        }
    
    def _save_state(self) -> None:
        """Save the current state to the state file."""
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        
        with open(self.state_file, 'w') as f:
            json.dump(self.state, f, indent=2)
    
    def add_interrupt(self, thread_id: str, interrupt_data: Dict[str, Any]) -> None:
        """Add or update an interrupt in the state."""
        self.state["interrupts"][thread_id] = {
            "data": interrupt_data,
            "status": "pending",  # pending, sent, awaiting_response, completed
            "timestamp": datetime.now().isoformat(),
            "message_id": None,  # Telegram message ID once sent
            "chat_id": None      # Telegram chat ID once sent
        }
        self._save_state()
    
    def get_interrupt(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """Get an interrupt from the state by thread_id."""
        return self.state["interrupts"].get(thread_id)
    
    def get_all_interrupts(self) -> Dict[str, Dict[str, Any]]:
        """Get all interrupts from the state."""
        return self.state["interrupts"]
    
    def get_pending_interrupts(self) -> Dict[str, Dict[str, Any]]:
        """Get all pending interrupts (not yet sent to the user)."""
        return {
            thread_id: interrupt
            for thread_id, interrupt in self.state["interrupts"].items()
            if interrupt["status"] == "pending"
        }
    
    def get_awaiting_response_interrupts(self) -> Dict[str, Dict[str, Any]]:
        """Get all interrupts awaiting response."""
        return {
            thread_id: interrupt
            for thread_id, interrupt in self.state["interrupts"].items()
            if interrupt["status"] == "awaiting_response"
        }
    
    def update_interrupt_status(self, thread_id: str, status: str, 
                               message_id: Optional[int] = None, 
                               chat_id: Optional[int] = None) -> None:
        """Update the status of an interrupt."""
        if thread_id in self.state["interrupts"]:
            interrupt = self.state["interrupts"][thread_id]
            interrupt["status"] = status
            
            if message_id is not None:
                interrupt["message_id"] = message_id
            
            if chat_id is not None:
                interrupt["chat_id"] = chat_id
            
            self._save_state()
    
    def remove_interrupt(self, thread_id: str) -> None:
        """Remove an interrupt from the state."""
        if thread_id in self.state["interrupts"]:
            del self.state["interrupts"][thread_id]
            self._save_state()
    
    def set_user_state(self, user_id: int, key: str, value: Any) -> None:
        """Set a value in a user's state."""
        if str(user_id) not in self.state["user_state"]:
            self.state["user_state"][str(user_id)] = {}
        
        self.state["user_state"][str(user_id)][key] = value
        self._save_state()
    
    def get_user_state(self, user_id: int, key: str, default: Any = None) -> Any:
        """Get a value from a user's state."""
        if str(user_id) not in self.state["user_state"]:
            return default
        
        return self.state["user_state"][str(user_id)].get(key, default)
    
    def clear_user_state(self, user_id: int) -> None:
        """Clear a user's state."""
        if str(user_id) in self.state["user_state"]:
            self.state["user_state"][str(user_id)] = {}
            self._save_state()
    
    def update_last_checked(self) -> None:
        """Update the timestamp of the last interrupt check."""
        self.state["last_checked"] = datetime.now().isoformat()
        self._save_state()
    
    def get_last_checked(self) -> Optional[str]:
        """Get the timestamp of the last interrupt check."""
        return self.state["last_checked"] 