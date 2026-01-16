"""
Amazon Alexa Skills handler for WebAppChat.

This module provides Alexa request handling directly in Flask,
eliminating the need for AWS Lambda.

Usage:
    from alexa_handler import alexa_bp
    app.register_blueprint(alexa_bp)

Endpoint:
    POST /alexa - Alexa skill webhook endpoint

Configuration in Alexa Developer Console:
    Endpoint Type: HTTPS
    Default Region: https://your-domain.com/alexa
    SSL Certificate: Trusted certificate authority
"""

from flask import Blueprint, request, jsonify
import logging
import re
from datetime import datetime
from typing import Dict, Any, Optional

# Import from your existing modules
from storage import new_chat, append_message, load_chat
from prices import DEFAULT_MODEL

logger = logging.getLogger(__name__)

# Create Blueprint
alexa_bp = Blueprint('alexa', __name__)

# Configuration
MAX_SPEECH_LENGTH = 6000  # Alexa has 8000 char limit, use 6000 for safety
DEFAULT_ALEXA_MODEL = DEFAULT_MODEL  # Use your configured default model
USE_RAG_BY_DEFAULT = True  # Enable RAG for vault access


# =============================================================================
# Alexa Request Handlers
# =============================================================================

@alexa_bp.route('/alexa', methods=['POST'])
def alexa_webhook():
    """
    Main Alexa webhook endpoint.

    Handles all Alexa skill requests:
    - LaunchRequest: "Alexa, open web chat"
    - IntentRequest: User questions and commands
    - SessionEndedRequest: Session cleanup

    Returns:
        JSON response in Alexa skill format
    """
    try:
        alexa_request = request.get_json()

        # Log request for debugging
        request_type = alexa_request.get('request', {}).get('type', 'unknown')
        logger.info(f"Alexa request received: {request_type}")

        # Route to appropriate handler
        if request_type == 'LaunchRequest':
            return handle_launch_request(alexa_request)
        elif request_type == 'IntentRequest':
            return handle_intent_request(alexa_request)
        elif request_type == 'SessionEndedRequest':
            return handle_session_ended_request(alexa_request)
        else:
            logger.warning(f"Unknown request type: {request_type}")
            return build_response("Sorry, I didn't understand that request.")

    except Exception as e:
        logger.error(f"Error handling Alexa request: {e}", exc_info=True)
        return build_response(
            "Sorry, I encountered an error. Please try again.",
            should_end_session=True
        )


def handle_launch_request(alexa_request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle skill launch (e.g., "Alexa, open web chat").

    Creates a new chat session and welcomes the user.
    """
    try:
        # Create new WebAppChat session
        chat_id = new_chat(title=f"Alexa Session - {datetime.now().strftime('%Y-%m-%d %H:%M')}")

        logger.info(f"Created new chat session: {chat_id}")

        speech_text = (
            "Welcome to Web App Chat! "
            "I can answer questions, search your notes, and help with various tasks. "
            "What would you like to know?"
        )

        return build_response(
            speech_text,
            reprompt_text="How can I help you?",
            session_attributes={'chat_id': chat_id, 'message_count': 0},
            should_end_session=False
        )

    except Exception as e:
        logger.error(f"Error in launch request: {e}", exc_info=True)
        return build_response(
            "Sorry, I had trouble starting. Please try again.",
            should_end_session=True
        )


def handle_intent_request(alexa_request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle intent requests (user questions and commands).

    Routes to specific intent handlers based on intent name.
    """
    intent = alexa_request.get('request', {}).get('intent', {})
    intent_name = intent.get('name', '')

    logger.info(f"Intent received: {intent_name}")

    # Route to appropriate intent handler
    if intent_name == 'AskIntent':
        return handle_ask_intent(alexa_request)
    elif intent_name == 'AMAZON.HelpIntent':
        return handle_help_intent(alexa_request)
    elif intent_name in ['AMAZON.CancelIntent', 'AMAZON.StopIntent']:
        return handle_cancel_intent(alexa_request)
    elif intent_name == 'AMAZON.NavigateHomeIntent':
        return handle_launch_request(alexa_request)
    else:
        logger.warning(f"Unhandled intent: {intent_name}")
        return build_response(
            "I'm not sure how to help with that. Try asking me a question.",
            reprompt_text="What would you like to know?"
        )


def handle_ask_intent(alexa_request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle user questions (main conversation).

    Sends question to WebAppChat /ask endpoint and returns response.
    """
    try:
        # Extract session attributes
        session = alexa_request.get('session', {})
        session_attributes = session.get('attributes', {})

        # Extract user's question from slot
        intent = alexa_request.get('request', {}).get('intent', {})
        slots = intent.get('slots', {})
        question_slot = slots.get('Question', {})
        user_question = question_slot.get('value', '')

        if not user_question:
            return build_response(
                "I didn't catch that. What would you like to know?",
                reprompt_text="Please ask me a question.",
                session_attributes=session_attributes
            )

        logger.info(f"User question: {user_question}")

        # Get or create chat_id
        chat_id = session_attributes.get('chat_id')
        if not chat_id:
            logger.info("No existing chat_id, creating new session")
            chat_id = new_chat(title=f"Alexa Session - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
            session_attributes['chat_id'] = chat_id
            session_attributes['message_count'] = 0

        # Process question through WebAppChat
        # Import here to avoid circular imports
        from app import process_chat_request

        ai_response = process_chat_request(
            prompt=user_question,
            chat_id=chat_id,
            model=DEFAULT_ALEXA_MODEL,
            use_rag=USE_RAG_BY_DEFAULT,
            temperature=0.7
        )

        # Update session
        session_attributes['message_count'] = session_attributes.get('message_count', 0) + 1

        # Clean response for speech
        response_text = ai_response.get('response', '')
        clean_response = clean_for_speech(response_text)

        logger.info(f"Response length: {len(clean_response)} chars")

        # Log cost if available
        cost = ai_response.get('cost', {}).get('total', 0)
        if cost > 0:
            logger.info(f"Request cost: ${cost:.4f}")

        return build_response(
            clean_response,
            reprompt_text="Is there anything else I can help with?",
            session_attributes=session_attributes,
            card_title="WebAppChat Response",
            card_content=response_text  # Full response in card
        )

    except Exception as e:
        logger.error(f"Error processing question: {e}", exc_info=True)
        return build_response(
            "Sorry, I had trouble processing that. Please try again.",
            reprompt_text="What else can I help you with?",
            session_attributes=session_attributes
        )


def handle_help_intent(alexa_request: Dict[str, Any]) -> Dict[str, Any]:
    """Handle help request."""
    session_attributes = alexa_request.get('session', {}).get('attributes', {})

    speech_text = (
        "I'm connected to your Web App Chat assistant. "
        "You can ask me anything! For example, "
        "try saying: 'what's in my daily notes' or 'explain quantum computing'. "
        "What would you like to know?"
    )

    return build_response(
        speech_text,
        reprompt_text="What would you like to ask?",
        session_attributes=session_attributes,
        card_title="WebAppChat Help",
        card_content=speech_text
    )


def handle_cancel_intent(alexa_request: Dict[str, Any]) -> Dict[str, Any]:
    """Handle cancel/stop request."""
    session_attributes = alexa_request.get('session', {}).get('attributes', {})
    message_count = session_attributes.get('message_count', 0)

    if message_count > 0:
        speech_text = f"Goodbye! We exchanged {message_count} messages. Thanks for using WebAppChat."
    else:
        speech_text = "Goodbye! Thanks for using WebAppChat."

    return build_response(speech_text, should_end_session=True)


def handle_session_ended_request(alexa_request: Dict[str, Any]) -> Dict[str, Any]:
    """Handle session end (cleanup)."""
    reason = alexa_request.get('request', {}).get('reason', 'unknown')
    logger.info(f"Session ended: {reason}")

    # Any cleanup logic here
    return build_response("", should_end_session=True)


# =============================================================================
# Helper Functions
# =============================================================================

def process_chat_request(prompt: str, chat_id: str, model: str,
                        use_rag: bool = False, temperature: float = 0.7) -> Dict[str, Any]:
    """
    Process a chat request through WebAppChat's /ask endpoint.

    This makes an internal call to the existing /ask endpoint to avoid
    duplicating complex logic. All features (RAG, presets, budget checking,
    tool calling) work automatically.

    Args:
        prompt: User's question
        chat_id: Chat session ID
        model: LLM model to use
        use_rag: Enable RAG search
        temperature: Temperature setting

    Returns:
        Response dict from /ask endpoint

    Raises:
        Exception: If the request fails
    """
    from flask import current_app

    # Make internal request to /ask endpoint using test client
    with current_app.test_client() as client:
        response = client.post('/ask',
            json={
                'prompt': prompt,
                'chatId': chat_id,
                'model': model,
                'temperature': temperature,
                'useRag': use_rag,
                'topK': 5
            },
            content_type='application/json'
        )

        if response.status_code == 200:
            return response.get_json()
        else:
            # Handle error responses
            error_data = response.get_json() or {}
            error_msg = error_data.get('error', 'Unknown error')
            logger.error(f"Error from /ask endpoint: {error_msg} (status {response.status_code})")

            # Re-raise as exception to be caught by caller
            raise Exception(f"Chat request failed: {error_msg}")


def clean_for_speech(text: str) -> str:
    """
    Clean markdown and formatting for Alexa speech output.

    Removes:
    - Markdown formatting (bold, italic, code blocks)
    - Links (keeps link text)
    - Headers
    - Bullet points

    Limits length to MAX_SPEECH_LENGTH for Alexa's 8000 char limit.
    """
    # Remove markdown formatting
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)  # Bold
    text = re.sub(r'\*(.+?)\*', r'\1', text)      # Italic
    text = re.sub(r'__(.+?)__', r'\1', text)      # Bold (alternative)
    text = re.sub(r'_(.+?)_', r'\1', text)        # Italic (alternative)
    text = re.sub(r'`(.+?)`', r'\1', text)        # Inline code
    text = re.sub(r'```[\s\S]*?```', '[code block]', text)  # Code blocks
    text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)  # Links (keep text)
    text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE)  # Headers

    # Replace bullet points with natural speech pauses
    text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)

    # Clean up extra whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()

    # Limit length for Alexa speech
    if len(text) > MAX_SPEECH_LENGTH:
        logger.warning(f"Response truncated from {len(text)} to {MAX_SPEECH_LENGTH} chars")

        # Try to truncate at sentence boundary
        truncated = text[:MAX_SPEECH_LENGTH]
        last_period = truncated.rfind('.')
        last_question = truncated.rfind('?')
        last_exclamation = truncated.rfind('!')

        best_end = max(last_period, last_question, last_exclamation)

        # Only use sentence boundary if it's in the last 20% of allowed length
        if best_end > MAX_SPEECH_LENGTH * 0.8:
            truncated = truncated[:best_end + 1]

        text = truncated + " ... The response was truncated. Check your chat history for the full answer."

    return text


def build_response(speech_text: str,
                  reprompt_text: Optional[str] = None,
                  session_attributes: Optional[Dict[str, Any]] = None,
                  should_end_session: bool = False,
                  card_title: Optional[str] = None,
                  card_content: Optional[str] = None) -> Dict[str, Any]:
    """
    Build an Alexa skill response.

    Args:
        speech_text: Text for Alexa to speak
        reprompt_text: Text to speak if user doesn't respond (keeps session open)
        session_attributes: Session data to persist
        should_end_session: Whether to close the session
        card_title: Optional card title for Alexa app
        card_content: Optional card content for Alexa app

    Returns:
        Alexa skill response JSON
    """
    response = {
        'version': '1.0',
        'response': {
            'outputSpeech': {
                'type': 'PlainText',
                'text': speech_text
            },
            'shouldEndSession': should_end_session
        }
    }

    # Add reprompt if provided (keeps session open)
    if reprompt_text:
        response['response']['reprompt'] = {
            'outputSpeech': {
                'type': 'PlainText',
                'text': reprompt_text
            }
        }

    # Add session attributes if provided
    if session_attributes:
        response['sessionAttributes'] = session_attributes

    # Add card if provided (shows in Alexa app)
    if card_title and card_content:
        response['response']['card'] = {
            'type': 'Simple',
            'title': card_title,
            'content': card_content
        }

    return jsonify(response)
