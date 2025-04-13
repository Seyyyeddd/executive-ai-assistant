"""
Interrupt client for communicating with LangGraph API.
A direct adaptation of test_all_interrupts.py for the Telegram UI.
"""

import sys
import os
import logging
import json
import re
import requests
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from pathlib import Path

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def load_deployment_url() -> str:
    """
    Load the LangGraph deployment URL from configuration.
    
    Priority:
    1. Environment variable LANGGRAPH_URL
    2. Configuration file (config.json)
    3. Default localhost URL as fallback
    
    Returns:
        The LangGraph deployment URL
    """
    # First check environment variable
    url = os.environ.get("LANGGRAPH_URL")
    if url:
        logger.info(f"Using LangGraph URL from environment: {url}")
        return url
    
    # Next try to load from config file
    try:
        config_path = Path("config.json")
        if config_path.exists():
            with open(config_path, "r") as f:
                config = json.load(f)
                if "deployment_url" in config:
                    url = config["deployment_url"]
                    logger.info(f"Using LangGraph URL from config file: {url}")
                    return url
    except Exception as e:
        logger.warning(f"Failed to load config file: {e}")
    
    # Fallback to default
    default_url = "http://127.0.0.1:2024"
    logger.warning(f"No LangGraph URL found, using default: {default_url}")
    logger.warning("Please set the LANGGRAPH_URL environment variable or add deployment_url to config.json")
    return default_url

# LangGraph API configuration
# This URL should be set to the LangGraph deployment URL provided in the configuration
LANGGRAPH_URL = load_deployment_url()
API_KEY = os.environ.get("LANGSMITH_API_KEY")

# Define response types
RESPONSE_TYPES = ["accept", "ignore", "response", "edit"]

# Define interrupt action types
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

class InterruptClient:
    """Client for interacting with LangGraph API to fetch and respond to interrupts."""
    
    def __init__(self, deployment_url: Optional[str] = None, api_key: Optional[str] = None):
        """
        Initialize the InterruptClient with the deployment URL and API key.
        
        Args:
            deployment_url: The URL of the LangGraph deployment (defaults to env var LANGGRAPH_URL)
            api_key: The API key for authenticating with LangGraph (defaults to env var LANGSMITH_API_KEY)
        """
        self.deployment_url = deployment_url or os.environ.get("LANGGRAPH_URL", "http://127.0.0.1:2024")
        self.api_key = api_key or os.environ.get("LANGSMITH_API_KEY")
        
        # Log initialization info
        logger.info(f"Initialized InterruptClient with URL: {self.deployment_url}")
        if self.api_key:
            logger.info("API key is set")
        else:
            logger.warning("No API key provided - authentication may fail")
        
        # Verify connectivity
        self.verify_connectivity()
    
    def verify_connectivity(self) -> bool:
        """
        Verify that we can connect to the LangGraph API endpoint.
        Returns True if connection is successful, False otherwise.
        """
        try:
            # Try to connect to the base API endpoint
            endpoint = f"{self.deployment_url}/health"
            
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            
            logger.info(f"Verifying connectivity to {endpoint}")
            response = requests.get(endpoint, headers=headers, timeout=5)
            
            if response.status_code == 200:
                logger.info("✅ Successfully connected to LangGraph API")
                return True
            else:
                logger.warning(f"⚠️ Could connect to LangGraph API, but got status code {response.status_code}")
                logger.warning(f"Response: {response.text[:200]}")
                
                # Try an alternate health check endpoint
                alternate_endpoint = self.deployment_url
                logger.info(f"Trying alternate endpoint: {alternate_endpoint}")
                alt_response = requests.get(alternate_endpoint, headers=headers, timeout=5)
                
                if alt_response.status_code in [200, 404]:
                    logger.info(f"✅ Connected to {alternate_endpoint} with status {alt_response.status_code}")
                    return True
                else:
                    logger.warning(f"⚠️ Could not connect to alternate endpoint. Status: {alt_response.status_code}")
                    return False
                
        except requests.RequestException as e:
            logger.error(f"❌ Failed to connect to LangGraph API: {e}")
            logger.error("Please check your LANGGRAPH_URL environment variable or deployment_url parameter")
            return False
        except Exception as e:
            logger.error(f"❌ Unexpected error checking connectivity: {e}")
            return False
    
    def get_interrupts(self) -> List[Dict[str, Any]]:
        """Fetch all interrupted threads from LangGraph API."""
        try:
            logger.info("Fetching interrupted threads")
            
            # Get all interrupted threads from the API
            threads = self._get_interrupted_threads()
            
            if not threads:
                logger.info("No interrupted threads found")
                return []
            
            logger.info(f"Found {len(threads)} interrupted threads")
            
            # Process each thread to extract data
            thread_data_list = []
            for thread in threads:
                thread_id = thread.get("thread_id")
                if not thread_id:
                    continue
                
                try:
                    # Extract thread data - trust that the API already identified this as interrupted
                    thread_data = self._extract_thread_data(thread_id)
                    if thread_data:
                        # Add the thread data to our list regardless of the state check
                        # The API already told us it's interrupted
                        thread_data_list.append(thread_data)
                        logger.info(f"Extracted data for thread {thread_id[:8]}: {thread_data['action_type']}")
                    else:
                        logger.warning(f"Could not extract data for thread {thread_id}")
                except Exception as e:
                    logger.error(f"Error extracting data for thread {thread_id}: {e}")
            
            if not thread_data_list:
                logger.warning("No threads had extractable data")
                
            logger.info(f"Returning {len(thread_data_list)} thread data items")
            return thread_data_list
        
        except Exception as e:
            logger.error(f"Error fetching interrupts: {e}")
            return []
    
    def get_interrupt(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a specific interrupt thread by ID."""
        try:
            return self._extract_thread_data(thread_id)
        except Exception as e:
            logger.error(f"Error fetching interrupt {thread_id}: {e}")
            return None
    
    def send_response(self, thread_id: str, response_type: str, 
                     response_content: str, action_type: str) -> bool:
        """Send a response to an interrupted thread."""
        try:
            # Log the request details
            logger.info(f"Preparing to send response to thread {thread_id}")
            logger.info(f"Response type: {response_type}")
            logger.info(f"Action type: {action_type}")
            
            # Validate that response_type is one of the allowed types for this action
            normalized_action = self.normalize_action_type(action_type)
            allowed_responses = self.get_allowed_responses(normalized_action)
            
            if response_type not in allowed_responses:
                logger.error(f"Invalid response type '{response_type}' for action '{normalized_action}'")
                logger.error(f"Allowed response types: {allowed_responses}")
                return False
            
            # Get the thread data to extract assistant_id
            thread_data = self.get_interrupt(thread_id)
            
            if not thread_data:
                logger.error(f"Thread data not found for {thread_id}")
                return False
            
            # Create the response payload
            payload = self.format_response_payload(
                thread_id=thread_id,
                response_type=response_type,
                response_content=response_content,
                action_type=action_type,
                assistant_id=thread_data.get("assistant_id")
            )
            
            # Validate the payload structure
            if "command" not in payload or "resume" not in payload["command"]:
                logger.error("Invalid payload structure: missing 'command.resume'")
                return False
                
            if not isinstance(payload["command"]["resume"], list) or not payload["command"]["resume"]:
                logger.error("Invalid payload structure: 'command.resume' must be a non-empty list")
                return False
            
            # Try sending the standard format payload first
            success = self._send_response_to_thread(thread_id, payload)
            
            if success:
                logger.info(f"Response sent successfully to thread {thread_id} with standard format")
                return True
            
            # If that didn't work, try simplified format
            logger.info(f"Standard format failed, trying simplified format for thread {thread_id}")
            
            # Create a simplified payload - directly using the resume items
            # This is the format expected by older LangGraph versions
            simplified_payload = payload["command"]["resume"][0]
            if "assistant_id" in payload:
                simplified_payload["assistant_id"] = payload["assistant_id"]
            
            # Try with the simplified payload
            success = self._send_response_to_thread(thread_id, simplified_payload)
            
            if success:
                logger.info(f"Response sent successfully to thread {thread_id} with simplified format")
                return True
            
            # If both formats fail, try the test_all_interrupts.py format from the sample code
            logger.info(f"Trying test_all_interrupts.py format for thread {thread_id}")
            
            # Create a payload that exactly matches the test_all_interrupts.py format
            if response_type == "response":
                response_value = response_content
            elif response_type == "accept" or response_type == "ignore":
                response_value = None
            elif response_type == "edit":
                # Structure based on action type
                if normalized_action == "ResponseEmailDraft":
                    response_value = {
                        "action": "ResponseEmailDraft",
                        "args": {
                            "content": response_content,
                            "new_recipients": []
                        }
                    }
                elif normalized_action == "SendCalendarInvite":
                    try:
                        calendar_data = json.loads(response_content)
                        response_value = {
                            "action": "SendCalendarInvite",
                            "args": {
                                "emails": calendar_data.get("emails", []),
                                "title": calendar_data.get("title", ""),
                                "start_time": calendar_data.get("start_time", ""),
                                "end_time": calendar_data.get("end_time", "")
                            }
                        }
                    except:
                        response_value = {
                            "action": "SendCalendarInvite",
                            "args": {
                                "content": response_content
                            }
                        }
                else:
                    response_value = {
                        "action": normalized_action,
                        "args": {
                            "content": response_content
                        }
                    }
                    
            exact_payload = {
                "command": {
                    "resume": [
                        {
                            "type": response_type,
                            "args": response_value
                        }
                    ]
                }
            }
            
            if thread_data.get("assistant_id"):
                exact_payload["assistant_id"] = thread_data["assistant_id"]
            else:
                exact_payload["assistant_id"] = "main"
                
            # Try with the exact format from test_all_interrupts.py
            success = self._send_response_to_thread(thread_id, exact_payload)
            
            if success:
                logger.info(f"Response sent successfully to thread {thread_id} with exact format")
                return True
            
            logger.error(f"All payload formats failed for thread {thread_id}")
            return False
        
        except Exception as e:
            logger.error(f"Error sending response to thread {thread_id}: {e}")
            # Log the full stack trace for debugging
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def _get_interrupted_threads(self) -> List[Dict[str, Any]]:
        """Get all interrupted threads from the LangGraph API using this client's deployment URL."""
        endpoint = f"{self.deployment_url}/threads/search"
        
        headers = {
            "Content-Type": "application/json"
        }
        
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        # Search for interrupted threads - use exact same parameters as the working script
        data = {
            "status": "interrupted",
            "limit": 20
        }
        
        try:
            logger.info(f"Searching for interrupted threads at {endpoint}")
            response = requests.post(endpoint, headers=headers, json=data)
            
            # Log the response for debugging
            logger.info(f"Search response status: {response.status_code}")
            
            if response.status_code == 200:
                threads = response.json()
                logger.info(f"Found {len(threads)} interrupted threads from API")
                
                # IMPORTANT: Trust the API's classification of interrupted threads
                # The API knows which threads are interrupted even if they don't have the
                # explicit status or interrupts in the thread state
                return threads
            else:
                logger.error(f"Error searching for threads: {response.status_code}")
                # Try to get all threads as a fallback, but prefer the search API
                all_threads_endpoint = f"{self.deployment_url}/threads"
                logger.info(f"Falling back to getting all threads at {all_threads_endpoint}")
                
                all_response = requests.get(all_threads_endpoint, headers=headers)
                
                if all_response.status_code == 200:
                    all_threads = all_response.json()
                    logger.info(f"Found {len(all_threads)} total threads")
                    
                    # Return all threads so we can at least try to process them
                    # Rather than failing to find any interrupted threads
                    return all_threads
                
                logger.error(f"Error getting all threads: {all_response.status_code}")
                return []
        except Exception as e:
            logger.error(f"Exception while searching for interrupted threads: {e}")
            return []
    
    def _get_thread_state(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """Get the complete state of a thread from LangGraph API using this client's deployment URL."""
        endpoint = f"{self.deployment_url}/threads/{thread_id}/state"
        
        headers = {
            "Content-Type": "application/json"
        }
        
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        try:
            response = requests.get(endpoint, headers=headers)
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Error fetching thread state: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Exception occurred: {e}")
            return None
    
    def _get_thread_history(self, thread_id: str) -> Optional[List[Dict[str, Any]]]:
        """Get thread history from LangGraph API using this client's deployment URL."""
        endpoint = f"{self.deployment_url}/threads/{thread_id}/history"
        
        headers = {
            "Content-Type": "application/json"
        }
        
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        try:
            response = requests.get(endpoint, headers=headers)
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Error fetching thread history: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Exception occurred: {e}")
            return None
    
    def _send_response_to_thread(self, thread_id: str, payload: Dict[str, Any]) -> bool:
        """Send a response to an interrupted thread using this client's deployment URL."""
        endpoint = f"{self.deployment_url}/threads/{thread_id}/runs/wait"
        
        headers = {
            "Content-Type": "application/json"
        }
        
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        try:
            # Log thorough debugging information
            debug_msg = (
                f"\n===== SENDING RESPONSE TO LANGGRAPH =====\n"
                f"Thread ID: {thread_id}\n"
                f"Endpoint: {endpoint}\n"
                f"Headers: {headers}\n"
                f"Payload: {json.dumps(payload, indent=2)}\n"
                f"=======================================\n"
            )
            logger.info(debug_msg)
            
            # Check if API_KEY is missing but required (common issue)
            if API_KEY is None:
                logger.warning("LANGSMITH_API_KEY environment variable is not set!")
            
            # Send the resume command with a longer timeout
            response = requests.post(endpoint, headers=headers, json=payload, timeout=30)
            
            # Always log the complete response for debugging
            logger.info(f"Response status code: {response.status_code}")
            logger.info(f"Response headers: {response.headers}")
            logger.info(f"Response text: {response.text[:500]}")
            
            if response.status_code == 200:
                logger.info("✅ Response sent successfully!")
                try:
                    result = response.json()
                    logger.info(f"Response data: {json.dumps(result, indent=2)}")
                    return True
                except json.JSONDecodeError:
                    logger.info("Response received but couldn't parse JSON data")
                    # Even if we can't parse the JSON, consider it successful if status is 200
                    return True
            elif response.status_code == 401 or response.status_code == 403:
                logger.error(f"❌ Authentication error: {response.status_code}")
                logger.error("Check your API key configuration")
                logger.error(f"Response body: {response.text}")
                return False
            elif response.status_code == 404:
                logger.error(f"❌ Thread not found: {thread_id}")
                # Provide troubleshooting steps
                logger.error("Make sure the thread_id is correct and the thread exists")
                logger.error(f"Response body: {response.text}")
                return False
            elif response.status_code == 400:
                logger.error(f"❌ Bad request: {response.status_code}")
                logger.error("The server could not understand the request (likely issue with payload format)")
                logger.error(f"Response body: {response.text}")
                
                # Try a different format as fallback
                if "command" in payload and "resume" in payload["command"]:
                    logger.info("Attempting fallback with simplified payload format...")
                    
                    # Get original payload values
                    original_type = payload["command"]["resume"][0].get("type", "")
                    original_args = payload["command"]["resume"][0].get("args", "")
                    
                    # Create simplified payload - just using the first resume item directly
                    simplified_payload = {
                        "type": original_type,
                        "args": original_args
                    }
                    
                    if "assistant_id" in payload:
                        simplified_payload["assistant_id"] = payload["assistant_id"]
                    
                    logger.info(f"Fallback payload: {json.dumps(simplified_payload, indent=2)}")
                    
                    # Try with the simplified format
                    fallback_response = requests.post(endpoint, headers=headers, json=simplified_payload, timeout=30)
                    logger.info(f"Fallback response status: {fallback_response.status_code}")
                    logger.info(f"Fallback response: {fallback_response.text[:500]}")
                    
                    if fallback_response.status_code == 200:
                        logger.info("✅ Fallback response sent successfully!")
                        return True
                
                return False
            else:
                logger.error(f"❌ Error sending response: {response.status_code}")
                logger.error(f"Response body: {response.text}")
                return False
        except requests.RequestException as e:
            logger.error(f"❌ Request exception sending response: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Exception sending response: {e}")
            return False
    
    def _extract_thread_data(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """
        Extract essential data for a thread including interrupt information.
        
        This method follows a clear hierarchy of data sources to ensure consistency:
        1. Extract data from interrupt tasks (most reliable source)
        2. Extract data from the current thread state
        3. Extract data from thread history if needed
        4. Set reasonable defaults for missing values
        """
        # Initialize result with default values
        result = {
            "thread_id": thread_id,
            "action_type": "Unknown",
            "action_content": "",
            "email_sender": "Unknown",
            "email_subject": "Unknown",
            "email_content": "",
            "send_time": "",
            "assistant_id": None,
            "interrupt_details": {
                "config": {},
                "description": ""
            },
            "calendar_invite": {
                "title": "",
                "start_time": "",
                "end_time": "",
                "emails": []
            },
            "email": {"id": ""} # Added for compatibility
        }

        # Get thread state
        thread_state = self._get_thread_state(thread_id)
        if not thread_state:
            logger.error(f"Failed to get state for thread {thread_id}")
            return None
        
        # Save raw state for debugging
        try:
            debug_dir = "debug_states"
            os.makedirs(debug_dir, exist_ok=True)
            with open(f"{debug_dir}/thread_state_{thread_id[:8]}.json", "w") as f:
                json.dump(thread_state, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save debug state: {e}")
        
        # Get thread history for additional context
        history = self._get_thread_history(thread_id)
        if history:
            try:
                with open(f"{debug_dir}/history_{thread_id[:8]}.json", "w") as f:
                    json.dump(history, f, indent=2)
            except Exception as e:
                logger.error(f"Failed to save history: {e}")
        
        # PHASE 1: Extract from metadata (assistant_id, etc.)
        if "metadata" in thread_state:
            metadata = thread_state["metadata"]
            if "assistant_id" in metadata:
                result["assistant_id"] = metadata["assistant_id"]
            elif "graph_id" in metadata:
                result["assistant_id"] = metadata["graph_id"]
            
            # Add debugging for email_id
            if "email_id" in metadata:
                logger.info(f"Found email_id in metadata: {metadata['email_id']}")
                result["email"]["id"] = metadata["email_id"]
        
        # PHASE 2: PRIORITY SOURCE - Extract from interrupts array
        # This is the most reliable source for action types and often has the best content
        interrupt_found = False
        
        if "values" in thread_state and "interrupts" in thread_state["values"]:
            interrupts = thread_state["values"]["interrupts"]
            if interrupts and len(interrupts) > 0:
                interrupt_found = True
                interrupt_info = self.extract_interrupt_info(thread_id, interrupts)
                result.update(interrupt_info)
                logger.info(f"Found interrupts in thread values {thread_id[:8]}")
        
        # Check for traditional interrupts format (inside tasks)
        if not interrupt_found and "tasks" in thread_state:
            for task in thread_state["tasks"]:
                if "interrupts" in task and task["interrupts"]:
                    interrupt = task["interrupts"][0]
                    interrupt_found = True
                    logger.info(f"Found interrupt in thread {thread_id[:8]}")
                    
                    if "value" in interrupt and isinstance(interrupt["value"], list):
                        interrupt_value = interrupt["value"][0]
                        
                        # Extract action request info (highest priority)
                        if "action_request" in interrupt_value:
                            action_request = interrupt_value["action_request"]
                            
                            # Get the action type
                            if "action" in action_request:
                                result["action_type"] = action_request["action"]
                                logger.info(f"Extracted action type from interrupt: {result['action_type']}")
                            
                            # Get the args
                            if "args" in action_request:
                                args = action_request["args"]
                                
                                # Extract content from various possible fields
                                if "content" in args:
                                    result["action_content"] = args["content"]
                                elif "question" in args:
                                    result["action_content"] = args["question"]
                                elif "message" in args:
                                    result["action_content"] = args["message"]
                                
                                # Extract calendar invite details if present
                                if result["action_type"] == "SendCalendarInvite":
                                    for key in ["title", "start_time", "end_time", "emails"]:
                                        if key in args:
                                            result["calendar_invite"][key] = args[key]
                        
                        # Extract config and description
                        if "config" in interrupt_value:
                            result["interrupt_details"]["config"] = interrupt_value["config"]
                        
                        # Description often contains valuable info for emails and questions
                        if "description" in interrupt_value:
                            description = interrupt_value["description"]
                            result["interrupt_details"]["description"] = description
                            
                            # For question types, description often contains the question
                            if (result["action_type"].lower() == "question" and 
                                not result["action_content"]):
                                result["action_content"] = description.strip()
                            
                            # Try to parse email details from description
                            # This is especially useful for ResponseEmailDraft interrupts
                            email_details = self.parse_email_from_description(description)
                            if email_details:
                                # Only update if we don't already have this info
                                if result["email_sender"] == "Unknown" and email_details["email_sender"] != "Unknown":
                                    result["email_sender"] = email_details["email_sender"]
                                    logger.info(f"Got email sender from description: {result['email_sender']}")
                                if result["email_subject"] == "Unknown" and email_details["email_subject"] != "Unknown":
                                    result["email_subject"] = email_details["email_subject"]
                                    logger.info(f"Got email subject from description: {result['email_subject']}")
                                if not result["email_content"] and email_details["email_content"]:
                                    result["email_content"] = email_details["email_content"]
        
        if not interrupt_found:
            logger.warning(f"No interrupts found in thread {thread_id[:8]}")
        
        # PHASE 3: Extract data from writes in thread state
        # Checking both metadata.writes and values.writes paths
        writes_locations = []
        
        # First check metadata.writes (original path)
        if "metadata" in thread_state and "writes" in thread_state["metadata"]:
            writes_locations.append(thread_state["metadata"]["writes"])
            
        # Now check values.writes (new path observed in test data)
        if "values" in thread_state and "writes" in thread_state["values"]:
            writes_locations.append(thread_state["values"]["writes"])
        
        for writes in writes_locations:
            if not writes:
                continue
                
            logger.info(f"Extracting from writes for {thread_id[:8]}")
            
            # Extract email info
            email_info = self.extract_email_info_from_writes(writes)
            
            # Email sender
            if result["email_sender"] == "Unknown" and email_info["email_sender"] != "Unknown":
                result["email_sender"] = email_info["email_sender"]
                logger.info(f"Got email sender from writes: {result['email_sender']}")
            
            # Email subject
            if result["email_subject"] == "Unknown" and email_info["email_subject"] != "Unknown":
                result["email_subject"] = email_info["email_subject"]
                logger.info(f"Got email subject from writes: {result['email_subject']}")
            
            # Email content - very important to get this right
            if not result["email_content"] and email_info["email_content"]:
                result["email_content"] = email_info["email_content"]
                logger.info(f"Got email content from writes, length: {len(result['email_content'])}")
            
            # Send time
            if not result["send_time"] and email_info["send_time"]:
                result["send_time"] = email_info["send_time"]
            
            # Email ID for links
            if "id" in email_info:
                result["email"]["id"] = email_info["id"]
                logger.info(f"Got email ID from writes: {result['email']['id']}")
            
            # Action information - but don't override interrupt info (lower priority)
            if result["action_type"] == "Unknown":
                action_info = self.extract_action_info_from_writes(writes)
                if action_info["action_type"] != "Unknown":
                    result["action_type"] = action_info["action_type"]
                    logger.info(f"Got action type from writes: {result['action_type']}")
                if not result["action_content"] and action_info["action_content"]:
                    result["action_content"] = action_info["action_content"]
        
        # PHASE 4: If still missing information, check thread history
        if history and (result["email_sender"] == "Unknown" or 
                       result["email_subject"] == "Unknown" or 
                       not result["email_content"] or
                       result["action_type"] == "Unknown"):
            
            logger.info(f"Checking thread history for {thread_id[:8]} to fill in missing data")
            # Process history entries from newest to oldest
            for state in history:
                # Check both possible locations for writes
                history_writes = None
                
                if "metadata" in state and "writes" in state["metadata"]:
                    history_writes = state["metadata"]["writes"]
                elif "values" in state and "writes" in state["values"]:
                    history_writes = state["values"]["writes"]
                
                if history_writes:
                    email_info = self.extract_email_info_from_writes(history_writes)
                    
                    # Only update fields still missing information
                    if result["email_sender"] == "Unknown" and email_info["email_sender"] != "Unknown":
                        result["email_sender"] = email_info["email_sender"]
                        logger.info(f"Got email sender from history: {result['email_sender']}")
                    if result["email_subject"] == "Unknown" and email_info["email_subject"] != "Unknown":
                        result["email_subject"] = email_info["email_subject"]
                        logger.info(f"Got email subject from history: {result['email_subject']}")
                    if not result["email_content"] and email_info["email_content"]:
                        result["email_content"] = email_info["email_content"]
                        logger.info(f"Got email content from history, length: {len(result['email_content'])}")
                    if not result["send_time"] and email_info["send_time"]:
                        result["send_time"] = email_info["send_time"]
                    
                    # Action info - still at lower priority than interrupts
                    if result["action_type"] == "Unknown":
                        action_info = self.extract_action_info_from_writes(history_writes)
                        if action_info["action_type"] != "Unknown":
                            result["action_type"] = action_info["action_type"]
                            logger.info(f"Got action type from history: {result['action_type']}")
                        if not result["action_content"] and action_info["action_content"]:
                            result["action_content"] = action_info["action_content"]
        
        # PHASE 5: INFERENCE - If action type is still unknown, infer from content
        # This is our least reliable approach but still needed as a fallback
        if result["action_type"] == "Unknown":
            if result["email_content"]:
                result["action_type"] = "ResponseEmailDraft"
                logger.info("Inferred action type as ResponseEmailDraft from email content")
            elif result["calendar_invite"]["title"] or result["calendar_invite"]["start_time"]:
                result["action_type"] = "SendCalendarInvite"
                logger.info("Inferred action type as SendCalendarInvite from calendar data")
            elif result["action_content"]:
                result["action_type"] = "Question"
                logger.info("Inferred action type as Question from action content")
        
        # PHASE 6: CLEANUP & DEFAULTS
        # Clean up text content
        for key in ["action_content", "email_content"]:
            if result[key]:
                # Fix common encoding issues
                result[key] = result[key].replace('\\n', '\n').replace('\r\n', '\n')
                result[key] = result[key].replace('\\t', '\t').replace('\\u00a0', ' ')
        
        # Normalize action type to ensure consistent case
        result["action_type"] = self.normalize_action_type(result["action_type"])
        
        # Final defaults for email data if we have content but still missing metadata
        # This ensures we never display "Unknown" in the UI
        if result["email_content"]:
            if result["email_subject"] == "Unknown":
                result["email_subject"] = "Email Draft"
            if result["email_sender"] == "Unknown":
                result["email_sender"] = "AI Assistant"
        
        # Log the final extracted results
        logger.info(f"Final extraction for thread {thread_id[:8]}:")
        logger.info(f"  Action type: {result['action_type']}")
        logger.info(f"  Email sender: {result['email_sender']}")
        logger.info(f"  Email subject: {result['email_subject']}")
        logger.info(f"  Email content length: {len(result['email_content'])}")
        
        return result

    def debug_thread(self, thread_id: str) -> Dict[str, Any]:
        """
        Debug helper to check the state of a specific thread
        
        Args:
            thread_id: The ID of the thread to debug
            
        Returns:
            A dictionary with debug information about the thread
        """
        debug_info = {
            "thread_id": thread_id,
            "thread_exists": False,
            "is_interrupted": False,
            "has_tasks": False, 
            "has_interrupts": False,
            "has_metadata": False,
            "metadata_status": "none",
            "extraction_success": False,
            "thread_data": None,
            "error": None
        }
        
        try:
            # Get thread state
            thread_state = self._get_thread_state(thread_id)
            
            if not thread_state:
                debug_info["error"] = "Thread state not found"
                return debug_info
                
            debug_info["thread_exists"] = True
            
            # Check if the thread is interrupted
            debug_info["is_interrupted"] = self.is_thread_interrupted(thread_state)
            
            # Check if the thread has tasks
            debug_info["has_tasks"] = "tasks" in thread_state and len(thread_state["tasks"]) > 0
            
            # Check if any tasks have interrupts
            if debug_info["has_tasks"]:
                for task in thread_state["tasks"]:
                    if "interrupts" in task and task["interrupts"]:
                        debug_info["has_interrupts"] = True
                        break
            
            # Check metadata
            debug_info["has_metadata"] = "metadata" in thread_state
            if debug_info["has_metadata"] and "status" in thread_state["metadata"]:
                debug_info["metadata_status"] = thread_state["metadata"]["status"]
            
            # Try to extract thread data
            try:
                thread_data = self._extract_thread_data(thread_id)
                if thread_data:
                    debug_info["extraction_success"] = True
                    debug_info["thread_data"] = thread_data
            except Exception as inner_e:
                debug_info["error"] = f"Extraction error: {str(inner_e)}"
            
            return debug_info
        except Exception as e:
            debug_info["error"] = f"Debug error: {str(e)}"
            return debug_info

    # Helper methods that delegate to standalone functions
    
    def extract_email_info_from_writes(self, writes: Dict) -> Dict[str, str]:
        """
        Extract email information from writes object, which could be in different locations.
        Returns a dictionary with email_sender, email_subject, email_content, and send_time.
        
        This implementation has been enhanced to handle the specific structure observed
        in the test data, particularly focusing on tool calls in "rewrite" and "draft_response".
        """
        result = {
            "email_sender": "Unknown",
            "email_subject": "Unknown",
            "email_content": "",
            "send_time": ""
        }
        
        if not writes or not isinstance(writes, dict):
            return result
        
        # Check email_id in metadata if available
        if "email_id" in writes:
            result["email_id"] = writes["email_id"]
        
        # PHASE 1: Check tool calls in 'rewrite' section (highest priority from test data)
        if "rewrite" in writes and isinstance(writes["rewrite"], dict):
            if "messages" in writes["rewrite"] and writes["rewrite"]["messages"]:
                messages = writes["rewrite"]["messages"]
                for message in messages:
                    # Check for tool_calls attribute in message
                    if "tool_calls" in message and message["tool_calls"]:
                        for tool_call in message["tool_calls"]:
                            if isinstance(tool_call, dict):
                                # Check if tool call is for email
                                if ("name" in tool_call and 
                                    tool_call["name"] == "ResponseEmailDraft" and 
                                    "args" in tool_call):
                                    args = tool_call["args"]
                                    if "content" in args and not result["email_content"]:
                                        result["email_content"] = args["content"]
                                        logger.info(f"Extracted email content from rewrite.messages.tool_calls, length={len(result['email_content'])}")
        
        # PHASE 2: Check tool calls in 'draft_response' section
        if "draft_response" in writes and isinstance(writes["draft_response"], dict):
            if "messages" in writes["draft_response"] and writes["draft_response"]["messages"]:
                messages = writes["draft_response"]["messages"]
                for message in messages:
                    # Direct tool_calls format
                    if "tool_calls" in message and message["tool_calls"]:
                        for tool_call in message["tool_calls"]:
                            if isinstance(tool_call, dict):
                                if ("name" in tool_call and 
                                    tool_call["name"] == "ResponseEmailDraft" and 
                                    "args" in tool_call):
                                    args = tool_call["args"]
                                    if "content" in args and not result["email_content"]:
                                        result["email_content"] = args["content"]
                                        logger.info(f"Extracted email content from draft_response.messages.tool_calls, length={len(result['email_content'])}")
                    
                    # OpenAI style tool_calls in additional_kwargs
                    if "additional_kwargs" in message and "tool_calls" in message["additional_kwargs"]:
                        tool_calls = message["additional_kwargs"]["tool_calls"]
                        for tool_call in tool_calls:
                            if "function" in tool_call and "name" in tool_call["function"]:
                                if tool_call["function"]["name"] == "ResponseEmailDraft":
                                    try:
                                        if "arguments" in tool_call["function"]:
                                            args = json.loads(tool_call["function"]["arguments"])
                                            if "content" in args and not result["email_content"]:
                                                result["email_content"] = args["content"]
                                                logger.info(f"Extracted email content from draft_response.messages.additional_kwargs.tool_calls, length={len(result['email_content'])}")
                                    except (json.JSONDecodeError, TypeError):
                                        logger.warning("Failed to parse tool call arguments")
        
        # PHASE 3: Check legacy locations from the standard structure
        # Check __start__ location
        if "__start__" in writes and isinstance(writes["__start__"], dict):
            if "email" in writes["__start__"]:
                email = writes["__start__"]["email"]
                if "from_email" in email:
                    result["email_sender"] = email["from_email"]
                if "subject" in email:
                    result["email_subject"] = email["subject"]
                if "page_content" in email and not result["email_content"]:
                    result["email_content"] = email["page_content"]
                if "send_time" in email:
                    result["send_time"] = email["send_time"]
        
        # Look in other common locations
        for section in ["triage_input", "read_email"]:
            if section in writes and isinstance(writes[section], dict):
                if "email" in writes[section]:
                    email = writes[section]["email"]
                    if "from_email" in email and result["email_sender"] == "Unknown":
                        result["email_sender"] = email["from_email"]
                    if "subject" in email and result["email_subject"] == "Unknown":
                        result["email_subject"] = email["subject"]
                    if "page_content" in email and not result["email_content"]:
                        result["email_content"] = email["page_content"]
                    if "send_time" in email and not result["send_time"]:
                        result["send_time"] = email["send_time"]
        
        # Check in specific fields from triage path
        if "triage_input" in writes and isinstance(writes["triage_input"], dict):
            triage = writes["triage_input"].get("triage", {})
            if isinstance(triage, dict) and "email_subject" in triage and result["email_subject"] == "Unknown":
                result["email_subject"] = triage["email_subject"]
            if isinstance(triage, dict) and "email_sender" in triage and result["email_sender"] == "Unknown":
                result["email_sender"] = triage["email_sender"]
        
        return result
    
    def extract_action_info_from_writes(self, writes: Dict) -> Dict[str, Any]:
        """
        Extract action type and content from writes object, checking all possible locations.
        
        This implementation prioritizes tool calls in rewrite and draft_response sections
        based on the structure observed in test data.
        
        Returns a dictionary with "action_type", "action_content", and "calendar_invite" for calendar invites.
        """
        result = {
            "action_type": "Unknown",
            "action_content": "",
            "calendar_invite": {
                "title": "",
                "start_time": "",
                "end_time": "",
                "emails": []
            }
        }
        
        if not writes or not isinstance(writes, dict):
            return result
        
        # PHASE 1: Check tool calls in 'rewrite' section (highest priority)
        if "rewrite" in writes and isinstance(writes["rewrite"], dict):
            if "messages" in writes["rewrite"] and writes["rewrite"]["messages"]:
                messages = writes["rewrite"]["messages"]
                for message in messages:
                    # Check for tool_calls attribute in message
                    if "tool_calls" in message and message["tool_calls"]:
                        for tool_call in message["tool_calls"]:
                            if isinstance(tool_call, dict) and "name" in tool_call:
                                # Get action type from tool call name
                                result["action_type"] = tool_call["name"]
                                logger.info(f"Found action type in rewrite.messages.tool_calls: {result['action_type']}")
                                
                                # Extract content from args
                                if "args" in tool_call and isinstance(tool_call["args"], dict):
                                    if "content" in tool_call["args"]:
                                        result["action_content"] = tool_call["args"]["content"]
                                    elif "question" in tool_call["args"]:
                                        result["action_content"] = tool_call["args"]["question"]
                                    elif "message" in tool_call["args"]:
                                        result["action_content"] = tool_call["args"]["message"]
                                    
                                    # Extract calendar data if present
                                    if result["action_type"] == "SendCalendarInvite":
                                        for key in ["title", "start_time", "end_time", "emails"]:
                                            if key in tool_call["args"]:
                                                result["calendar_invite"][key] = tool_call["args"][key]
                                
                                # For Question type, often the content is directly in the args
                                if result["action_type"] == "Question" and not result["action_content"] and "args" in tool_call:
                                    # If args is a string or can be converted to one, use it
                                    if isinstance(tool_call["args"], str):
                                        result["action_content"] = tool_call["args"]
                                    elif isinstance(tool_call["args"], dict):
                                        # For Question, content is often in "content" field
                                        if "content" in tool_call["args"]:
                                            result["action_content"] = tool_call["args"]["content"]
        
        # PHASE 2: Check tool calls in 'draft_response' section
        if result["action_type"] == "Unknown" and "draft_response" in writes and isinstance(writes["draft_response"], dict):
            if "messages" in writes["draft_response"] and writes["draft_response"]["messages"]:
                messages = writes["draft_response"]["messages"]
                for message in messages:
                    # Direct tool_calls format
                    if "tool_calls" in message and message["tool_calls"]:
                        for tool_call in message["tool_calls"]:
                            if isinstance(tool_call, dict) and "name" in tool_call:
                                result["action_type"] = tool_call["name"]
                                logger.info(f"Found action type in draft_response.messages.tool_calls: {result['action_type']}")
                                
                                # Get content
                                if "args" in tool_call and isinstance(tool_call["args"], dict):
                                    if "content" in tool_call["args"]:
                                        result["action_content"] = tool_call["args"]["content"]
                                    elif "question" in tool_call["args"]:
                                        result["action_content"] = tool_call["args"]["question"]
                                    elif "message" in tool_call["args"]:
                                        result["action_content"] = tool_call["args"]["message"]
                                    
                                    # Extract calendar data if present
                                    if result["action_type"] == "SendCalendarInvite":
                                        for key in ["title", "start_time", "end_time", "emails"]:
                                            if key in tool_call["args"]:
                                                result["calendar_invite"][key] = tool_call["args"][key]
                    
                    # OpenAI style tool_calls in additional_kwargs
                    if "additional_kwargs" in message and "tool_calls" in message["additional_kwargs"]:
                        tool_calls = message["additional_kwargs"]["tool_calls"]
                        for tool_call in tool_calls:
                            if "function" in tool_call and "name" in tool_call["function"]:
                                result["action_type"] = tool_call["function"]["name"]
                                logger.info(f"Found action type in draft_response.messages.additional_kwargs.tool_calls: {result['action_type']}")
                                
                                # Extract content from arguments
                                try:
                                    if "arguments" in tool_call["function"]:
                                        args = json.loads(tool_call["function"]["arguments"])
                                        if isinstance(args, dict):
                                            if "content" in args:
                                                result["action_content"] = args["content"]
                                            elif "question" in args:
                                                result["action_content"] = args["question"]
                                            elif "message" in args:
                                                result["action_content"] = args["message"]
                                            
                                            # Extract calendar data if present
                                            if result["action_type"] == "SendCalendarInvite":
                                                for key in ["title", "start_time", "end_time", "emails"]:
                                                    if key in args:
                                                        result["calendar_invite"][key] = args[key]
                                                logger.info(f"Extracted calendar data from tool_call arguments: {result['calendar_invite']}")
                                except (json.JSONDecodeError, TypeError):
                                    logger.warning("Failed to parse tool call arguments")
        
        # PHASE 3: Check in traditional locations 
        # Only if we haven't found an action type in the tool calls
        if result["action_type"] == "Unknown":
            # Check in triage sections
            for section in ["__start__", "triage_input"]:
                if section in writes and isinstance(writes[section], dict):
                    if "triage" in writes[section] and isinstance(writes[section]["triage"], dict):
                        # Direct response field
                        if "response" in writes[section]["triage"]:
                            response = writes[section]["triage"]["response"]
                            if response and response.lower() != "no":
                                result["action_type"] = response
                        
                        # Email-specific fields
                        if "action" in writes[section]["triage"]:
                            result["action_type"] = writes[section]["triage"]["action"]
                        
                        # Content might be in various fields
                        if "content" in writes[section]["triage"]:
                            result["action_content"] = writes[section]["triage"]["content"]
                        elif "question" in writes[section]["triage"]:
                            result["action_content"] = writes[section]["triage"]["question"]
                        elif "message" in writes[section]["triage"]:
                            result["action_content"] = writes[section]["triage"]["message"]
            
            # Check in tasks results
            if "tasks" in writes:
                tasks = writes["tasks"]
                for task in tasks:
                    if "result" in task and isinstance(task["result"], dict):
                        result_data = task["result"]
                        # Check for action field
                        if "action" in result_data:
                            result["action_type"] = result_data["action"]
                        # Check for content field
                        if "content" in result_data:
                            result["action_content"] = result_data["content"]
                        # Check in triage subfield
                        if "triage" in result_data and isinstance(result_data["triage"], dict):
                            if "response" in result_data["triage"]:
                                result["action_type"] = result_data["triage"]["response"]
                            if "content" in result_data["triage"]:
                                result["action_content"] = result_data["triage"]["content"]
        
        # PHASE 4: Infer the action type from the structure if still unknown
        if result["action_type"] == "Unknown":
            # Look for specific tool names as keys
            for key in writes.keys():
                # Look for any field that might be a tool name matching our interrupt types
                lower_key = key.lower()
                if lower_key in ["question", "notify", "responseemaildraft", "sendcalendarinvite"]:
                    result["action_type"] = key
                    # Try to extract content from this section
                    if isinstance(writes[key], dict) and "content" in writes[key]:
                        result["action_content"] = writes[key]["content"]
                    elif isinstance(writes[key], str):
                        result["action_content"] = writes[key]
            
            # Check content for message to determine if it might be a question
            if result["action_type"] == "Unknown" and "messages" in writes:
                for message in writes["messages"]:
                    if "content" in message and message["content"] and not result["action_content"]:
                        result["action_content"] = message["content"]
                        if not result["action_type"] and "?" in message["content"]:
                            result["action_type"] = "Question"
        
        return result
    
    def parse_email_from_description(self, description: str) -> Dict[str, str]:
        """
        Parse email metadata and content from an interrupt description.
        This is especially useful for ResponseEmailDraft interrupts where
        the email information is often embedded in the description.
        
        Args:
            description: The description text from an interrupt
            
        Returns:
            Dictionary with email_sender, email_subject, and email_content
        """
        result = {
            "email_sender": "Unknown",
            "email_subject": "Unknown",
            "email_content": ""
        }
        
        if not description:
            return result
            
        # Some interrupt descriptions contain a formatted email
        if "From:" in description and "Subject:" in description:
            lines = description.split('\n')
            
            # Extract sender
            for i, line in enumerate(lines):
                if line.startswith("From:"):
                    result["email_sender"] = line[5:].strip()
                    logger.info(f"Found sender in description: {result['email_sender']}")
                    break
            
            # Extract subject
            for i, line in enumerate(lines):
                if line.startswith("Subject:"):
                    result["email_subject"] = line[8:].strip()
                    logger.info(f"Found subject in description: {result['email_subject']}")
                    break
            
            # Extract content - usually starts after a blank line following headers
            content_start = False
            content_lines = []
            
            for line in lines:
                if content_start:
                    content_lines.append(line)
                elif line.strip() == "":
                    # First empty line after headers marks the start of content
                    content_start = True
            
            if content_lines:
                result["email_content"] = "\n".join(content_lines).strip()
        
        # Alternative format: some descriptions just contain the draft without headers
        # For these, we don't try to infer sender/subject to avoid incorrect attribution
        elif not result["email_content"]:
            # If description looks like an email body, use it as content
            if len(description) > 20 and "\n" in description:
                result["email_content"] = description.strip()
        
        return result
    
    def normalize_action_type(self, action_type: str) -> str:
        """
        Normalize action type to match our INTERRUPT_TYPES dictionary.
        Handles case sensitivity and common name variations.
        """
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

    def is_thread_interrupted(self, thread_state: Dict[str, Any]) -> bool:
        """Delegates to standalone is_thread_interrupted function"""
        return is_thread_interrupted(thread_state)

    def format_response_payload(
        self,
        thread_id: str, 
        response_type: str, 
        response_content: str, 
        action_type: str,
        assistant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Format the appropriate payload for responding to an interrupt"""
        # Initialize payload with the correct structure for LangGraph API
        payload = {
            "command": {
                "resume": []  # This will be populated based on response type - using a list format
            }
        }
        
        # Add assistant_id if provided
        if assistant_id:
            payload["assistant_id"] = assistant_id
        else:
            # Default to "main" graph if no assistant_id provided
            payload["assistant_id"] = "main"
        
        # Handle different response types
        normalized_action = self.normalize_action_type(action_type)
        
        if response_type == "response":
            # Add a response object to the resume list
            payload["command"]["resume"] = [
                {
                    "type": "response",
                    "args": response_content
                }
            ]
            
        elif response_type == "accept":
            # For accepting email drafts and calendar invites
            payload["command"]["resume"] = [
                {
                    "type": "accept",
                    "args": None
                }
            ]
                
        elif response_type == "ignore":
            # For ignoring any interrupt
            payload["command"]["resume"] = [
                {
                    "type": "ignore",
                    "args": None
                }
            ]
            
        elif response_type == "edit":
            # Handle edit differently based on action type
            if normalized_action == "ResponseEmailDraft":
                # Format according to Agent Inbox structure for email drafts
                payload["command"]["resume"] = [
                    {
                        "type": "edit",
                        "args": {
                            "action": "ResponseEmailDraft",
                            "args": {
                                "content": response_content,
                                "new_recipients": []
                            }
                        }
                    }
                ]
            elif normalized_action == "SendCalendarInvite":
                # For calendar invites, parse the JSON if provided
                if response_content.strip().startswith('{') and response_content.strip().endswith('}'):
                    try:
                        # Parse the JSON to extract calendar details
                        calendar_data = json.loads(response_content)
                        
                        # Format according to Agent Inbox structure for calendar invites
                        payload["command"]["resume"] = [
                            {
                                "type": "edit",
                                "args": {
                                    "action": "SendCalendarInvite",
                                    "args": {
                                        "emails": calendar_data.get("emails", []),
                                        "title": calendar_data.get("title", ""),
                                        "start_time": calendar_data.get("start_time", ""),
                                        "end_time": calendar_data.get("end_time", "")
                                    }
                                }
                            }
                        ]
                    except json.JSONDecodeError:
                        # If JSON is invalid, use a simplified format
                        payload["command"]["resume"] = [
                            {
                                "type": "edit",
                                "args": {
                                    "action": "SendCalendarInvite",
                                    "args": {
                                        "content": response_content
                                    }
                                }
                            }
                        ]
                else:
                    # For non-JSON input, use a simplified format
                    payload["command"]["resume"] = [
                        {
                            "type": "edit",
                            "args": {
                                "action": "SendCalendarInvite",
                                "args": {
                                    "content": response_content
                                }
                            }
                        }
                    ]
            else:
                # For other action types, use a generic format
                payload["command"]["resume"] = [
                    {
                        "type": "edit",
                        "args": {
                            "action": normalized_action,
                            "args": {
                                "content": response_content
                            }
                        }
                    }
                ]
        
        # Save the payload to a debug file for inspection
        try:
            debug_dir = "debug_payloads"
            os.makedirs(debug_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            with open(f"{debug_dir}/payload_{thread_id[:8]}_{timestamp}.json", "w") as f:
                json.dump(payload, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save debug payload: {e}")
        
        return payload
        
    def get_allowed_responses(self, action_type: str) -> List[str]:
        """Get allowed response types for a specific action type"""
        # Normalize the action type
        normalized_action = self.normalize_action_type(action_type)
        
        # Check if normalized action exists in INTERRUPT_TYPES
        if normalized_action in INTERRUPT_TYPES:
            return INTERRUPT_TYPES[normalized_action]["allowed_responses"]
        
        # Default to allowing all response types if unknown
        logger.warning(f"⚠️ Unknown action type: {action_type}, allowing all response types")
        return ["accept", "ignore", "response", "edit"]

    def extract_interrupt_info(self, thread_id: str, interrupts: List[Dict]) -> Dict[str, Any]:
        """
        Extract information from interrupt objects, prioritizing the most recent one.
        
        Args:
            thread_id: The thread ID
            interrupts: List of interrupt dictionaries
            
        Returns:
            Dictionary with extracted information from interrupts
        """
        if not interrupts:
            return {}
        
        # Sort interrupts by timestamp in descending order (newest first)
        sorted_interrupts = sorted(
            interrupts, 
            key=lambda x: x.get("timestamp", 0), 
            reverse=True
        )
        
        # Get the most recent interrupt
        latest_interrupt = sorted_interrupts[0]
        interrupt_type = latest_interrupt.get("interrupt_type", "Unknown")
        description = latest_interrupt.get("description", "")
        
        logger.info(f"Latest interrupt type for thread {thread_id}: {interrupt_type}")
        
        result = {
            "action_type": interrupt_type,
            "action_content": description
        }
        
        # Extract different information based on interrupt type
        if interrupt_type == "ResponseEmailDraft":
            # Email drafts often have the email content in the description
            email_info = self.parse_email_from_description(description)
            result.update(email_info)
            result["action_type"] = "email"
            
        elif interrupt_type == "SendCalendarInvite" or interrupt_type == "ResponseCalendarInvite":
            # Calendar invites might have details in the description or value field
            result["action_type"] = "SendCalendarInvite"
            
            # Check if there's a value field with tool_calls data
            value = latest_interrupt.get("value", [])
            if isinstance(value, list) and len(value) > 0:
                interrupt_value = value[0]
                if "action_request" in interrupt_value and "args" in interrupt_value["action_request"]:
                    args = interrupt_value["action_request"]["args"]
                    # Extract calendar fields from args
                    calendar_data = {
                        "title": args.get("title", ""),
                        "start_time": args.get("start_time", ""),
                        "end_time": args.get("end_time", ""),
                        "emails": args.get("emails", [])
                    }
                    result["calendar_invite"] = calendar_data
                    logger.info(f"Extracted calendar data from interrupt value: {calendar_data}")
            
            # Also try to find calendar data in the thread history - will be searched later
            
        elif interrupt_type == "ResponseTask":
            # Tasks might have details in the description
            result["action_type"] = "task"
            result["task_description"] = description
            
        elif interrupt_type == "ResponseMessage":
            # Direct messages
            result["action_type"] = "message"
            result["message_content"] = description
            
        return result

# Directly imported from test_all_interrupts.py

def get_interrupted_threads() -> List[Dict[str, Any]]:
    """Get all interrupted threads from the LangGraph API"""
    endpoint = f"{LANGGRAPH_URL}/threads/search"
    
    headers = {
        "Content-Type": "application/json"
    }
    
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    
    # Search for interrupted threads
    data = {
        "status": "interrupted",
        "limit": 20
    }
    
    try:
        response = requests.post(endpoint, headers=headers, json=data)
        if response.status_code == 200:
            return response.json()
        else:
            # Try to get all threads and filter manually
            all_threads_endpoint = f"{LANGGRAPH_URL}/threads"
            all_response = requests.get(all_threads_endpoint, headers=headers)
            
            if all_response.status_code == 200:
                threads = all_response.json()
                # Filter for interrupted threads by checking each thread's state
                interrupted_threads = []
                for thread in threads:
                    thread_id = thread["thread_id"]
                    thread_state = get_thread_state(thread_id)
                    if thread_state and is_thread_interrupted(thread_state):
                        interrupted_threads.append(thread)
                return interrupted_threads
            
            logger.error(f"Error searching for threads: {response.status_code}")
            return []
    except Exception as e:
        logger.error(f"Exception occurred: {e}")
        return []

def is_thread_interrupted(thread_state: Dict[str, Any]) -> bool:
    """Check if a thread is interrupted based on its state"""
    thread_id = thread_state.get("checkpoint", {}).get("thread_id", "unknown")
    logger.info(f"Checking if thread {thread_id[:8]} is interrupted")
    
    # Check for tasks with interrupts
    if "tasks" in thread_state:
        for task in thread_state["tasks"]:
            if "interrupts" in task and task["interrupts"]:
                logger.info(f"Thread {thread_id[:8]} has interrupts in tasks")
                return True
    else:
        logger.info(f"Thread {thread_id[:8]} has no tasks section")
    
    # Check for metadata status
    if "metadata" in thread_state and "status" in thread_state["metadata"]:
        status = thread_state["metadata"]["status"]
        if status == "interrupted":
            logger.info(f"Thread {thread_id[:8]} has interrupted status in metadata")
            return True
        else:
            logger.info(f"Thread {thread_id[:8]} has status: {status} in metadata")
    else:
        logger.info(f"Thread {thread_id[:8]} has no status in metadata")
    
    logger.info(f"Thread {thread_id[:8]} is not interrupted")
    return False

def get_thread_state(thread_id: str) -> Optional[Dict[str, Any]]:
    """Get the complete state of a thread from LangGraph API"""
    endpoint = f"{LANGGRAPH_URL}/threads/{thread_id}/state"
    
    headers = {
        "Content-Type": "application/json"
    }
    
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    
    try:
        response = requests.get(endpoint, headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Error fetching thread state: {response.status_code}")
            return None
    except Exception as e:
        logger.error(f"Exception occurred: {e}")
        return None

def get_thread_history(thread_id: str) -> Optional[List[Dict[str, Any]]]:
    """Get thread history from LangGraph API"""
    endpoint = f"{LANGGRAPH_URL}/threads/{thread_id}/history"
    
    headers = {
        "Content-Type": "application/json"
    }
    
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    
    try:
        response = requests.get(endpoint, headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Error fetching thread history: {response.status_code}")
            return None
    except Exception as e:
        logger.error(f"Exception occurred: {e}")
        return None

def format_datetime(iso_datetime: str) -> str:
    """Format ISO datetime to a more readable format"""
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

def send_response_to_thread(thread_id: str, payload: Dict[str, Any]) -> bool:
    """Send a response to an interrupted thread"""
    endpoint = f"{LANGGRAPH_URL}/threads/{thread_id}/runs/wait"
    
    headers = {
        "Content-Type": "application/json"
    }
    
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    
    try:
        logger.info(f"Sending payload to {endpoint}")
        logger.info(json.dumps(payload, indent=2))
        
        # Send the resume command directly
        response = requests.post(endpoint, headers=headers, json=payload)
        
        if response.status_code == 200:
            logger.info("✅ Response sent successfully!")
            try:
                result = response.json()
                logger.info(f"Response data: {json.dumps(result, indent=2)}")
                return True
            except json.JSONDecodeError:
                logger.info("Response received but couldn't parse JSON data")
                logger.info(f"Raw response: {response.text[:200]}...")
                return True
        else:
            logger.error(f"❌ Error sending response: {response.status_code}")
            logger.error(f"Response body: {response.text}")
            return False
    except Exception as e:
        logger.error(f"❌ Exception sending response: {e}")
        return False 