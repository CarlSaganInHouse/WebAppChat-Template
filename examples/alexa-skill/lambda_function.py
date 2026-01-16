"""
WebAppChat Alexa Skill - AWS Lambda Handler

This Lambda function bridges Amazon Alexa with your WebAppChat instance,
enabling voice conversations through Alexa-enabled devices.

Prerequisites:
- WebAppChat instance with public HTTPS endpoint
- API key from: docker exec -it webchat-app python scripts/manage.py create-api-key "Alexa"
- AWS Lambda with Alexa Skills Kit trigger
- Environment variables configured (see below)

Environment Variables:
- WEBAPPCHAT_URL: Your WebAppChat base URL (e.g., https://your-domain.com)
- WEBAPPCHAT_API_KEY: API key for authentication
- DEFAULT_MODEL: (Optional) Default LLM model, defaults to gpt-4o-mini
- USE_RAG: (Optional) Enable RAG by default, defaults to true
- MAX_SPEECH_LENGTH: (Optional) Max characters for speech, defaults to 6000
"""

import json
import requests
import os
import re
from datetime import datetime
import logging

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Configuration from environment variables
WEBAPPCHAT_URL = os.environ.get('WEBAPPCHAT_URL', '').rstrip('/')
API_KEY = os.environ.get('WEBAPPCHAT_API_KEY', '')
DEFAULT_MODEL = os.environ.get('DEFAULT_MODEL', 'gpt-4o-mini')
USE_RAG = os.environ.get('USE_RAG', 'true').lower() == 'true'
MAX_SPEECH_LENGTH = int(os.environ.get('MAX_SPEECH_LENGTH', '6000'))
REQUEST_TIMEOUT = int(os.environ.get('REQUEST_TIMEOUT', '30'))

# Validate configuration
if not WEBAPPCHAT_URL:
    raise ValueError("WEBAPPCHAT_URL environment variable is required")
if not API_KEY:
    raise ValueError("WEBAPPCHAT_API_KEY environment variable is required")

# Alexa Skills Kit SDK imports
try:
    from ask_sdk_core.skill_builder import SkillBuilder
    from ask_sdk_core.dispatch_components import AbstractRequestHandler, AbstractExceptionHandler
    from ask_sdk_core.utils import is_request_type, is_intent_name
    from ask_sdk_model.ui import SimpleCard
except ImportError:
    raise ImportError(
        "Alexa Skills SDK not installed. Add to requirements.txt: ask-sdk-core==1.19.0"
    )

sb = SkillBuilder()

# =============================================================================
# Request Handlers
# =============================================================================

class LaunchRequestHandler(AbstractRequestHandler):
    """Handler for Skill Launch (e.g., 'Alexa, open web chat')"""

    def can_handle(self, handler_input):
        return is_request_type("LaunchRequest")(handler_input)

    def handle(self, handler_input):
        logger.info("LaunchRequest received")
        session_attr = handler_input.attributes_manager.session_attributes

        try:
            # Create new WebAppChat session
            chat_id = create_chat_session()
            session_attr['chat_id'] = chat_id
            session_attr['message_count'] = 0
            session_attr['created_at'] = datetime.now().isoformat()

            logger.info(f"Created new chat session: {chat_id}")

            speech_text = (
                "Welcome to Web App Chat! "
                "I can answer questions, search your notes, and help with various tasks. "
                "What would you like to know?"
            )

            return (
                handler_input.response_builder
                    .speak(speech_text)
                    .ask("How can I help you?")
                    .set_card(SimpleCard("WebAppChat", speech_text))
                    .response
            )

        except Exception as e:
            logger.error(f"Error in LaunchRequest: {e}", exc_info=True)
            speech_text = "Sorry, I had trouble connecting to Web App Chat. Please try again later."
            return (
                handler_input.response_builder
                    .speak(speech_text)
                    .set_should_end_session(True)
                    .response
            )


class AskIntentHandler(AbstractRequestHandler):
    """Handler for user questions (main conversation)"""

    def can_handle(self, handler_input):
        return is_intent_name("AskIntent")(handler_input)

    def handle(self, handler_input):
        session_attr = handler_input.attributes_manager.session_attributes

        # Extract user's question from slot
        slots = handler_input.request_envelope.request.intent.slots
        question = slots.get("Question")

        if not question or not question.value:
            speech_text = "I didn't catch that. What would you like to know?"
            return (
                handler_input.response_builder
                    .speak(speech_text)
                    .ask(speech_text)
                    .response
            )

        user_question = question.value
        logger.info(f"User question: {user_question}")

        # Get or create chat_id
        chat_id = session_attr.get('chat_id')
        if not chat_id:
            logger.info("No existing chat_id, creating new session")
            chat_id = create_chat_session()
            session_attr['chat_id'] = chat_id
            session_attr['message_count'] = 0

        # Send to WebAppChat
        try:
            response = ask_webappchat(user_question, chat_id)
            session_attr['message_count'] = session_attr.get('message_count', 0) + 1

            ai_response = response.get('response', '')
            logger.info(f"AI response length: {len(ai_response)} chars")

            # Clean response for speech (remove markdown, limit length)
            clean_response = clean_for_speech(ai_response)

            # Include brief usage info if desired
            cost = response.get('cost', {}).get('total', 0)
            if cost > 0:
                logger.info(f"Request cost: ${cost:.4f}")

            return (
                handler_input.response_builder
                    .speak(clean_response)
                    .ask("Is there anything else I can help with?")
                    .set_card(SimpleCard("WebAppChat Response", ai_response))
                    .response
            )

        except requests.exceptions.Timeout:
            logger.error("WebAppChat request timed out")
            speech_text = "Sorry, the request took too long. Please try asking something simpler."
            return (
                handler_input.response_builder
                    .speak(speech_text)
                    .ask("What else can I help you with?")
                    .response
            )

        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error: {e}", exc_info=True)
            if e.response.status_code == 429:
                speech_text = "Sorry, the rate limit was exceeded. Please try again in a moment."
            elif e.response.status_code == 402:
                speech_text = "Sorry, the budget limit has been exceeded. Please check your settings."
            else:
                speech_text = "Sorry, I encountered an error processing your request."

            return (
                handler_input.response_builder
                    .speak(speech_text)
                    .response
            )

        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            speech_text = "Sorry, something went wrong. Please try again."
            return (
                handler_input.response_builder
                    .speak(speech_text)
                    .response
            )


class HelpIntentHandler(AbstractRequestHandler):
    """Handler for AMAZON.HelpIntent"""

    def can_handle(self, handler_input):
        return is_intent_name("AMAZON.HelpIntent")(handler_input)

    def handle(self, handler_input):
        speech_text = (
            "I'm connected to your Web App Chat assistant. "
            "You can ask me anything! For example, "
            "try saying: 'what's in my daily notes' or 'explain quantum computing'. "
            "What would you like to know?"
        )

        return (
            handler_input.response_builder
                .speak(speech_text)
                .ask("What would you like to ask?")
                .set_card(SimpleCard("WebAppChat Help", speech_text))
                .response
        )


class CancelOrStopIntentHandler(AbstractRequestHandler):
    """Handler for AMAZON.CancelIntent and AMAZON.StopIntent"""

    def can_handle(self, handler_input):
        return (is_intent_name("AMAZON.CancelIntent")(handler_input) or
                is_intent_name("AMAZON.StopIntent")(handler_input))

    def handle(self, handler_input):
        session_attr = handler_input.attributes_manager.session_attributes
        message_count = session_attr.get('message_count', 0)

        if message_count > 0:
            speech_text = f"Goodbye! We exchanged {message_count} messages. Thanks for using WebAppChat."
        else:
            speech_text = "Goodbye! Thanks for using WebAppChat."

        return (
            handler_input.response_builder
                .speak(speech_text)
                .set_should_end_session(True)
                .response
        )


class SessionEndedRequestHandler(AbstractRequestHandler):
    """Handler for SessionEndedRequest (cleanup)"""

    def can_handle(self, handler_input):
        return is_request_type("SessionEndedRequest")(handler_input)

    def handle(self, handler_input):
        logger.info(f"Session ended: {handler_input.request_envelope.request.reason}")
        # Any cleanup logic here
        return handler_input.response_builder.response


class AllExceptionHandler(AbstractExceptionHandler):
    """Global exception handler"""

    def can_handle(self, handler_input, exception):
        return True

    def handle(self, handler_input, exception):
        logger.error(f"Unhandled exception: {exception}", exc_info=True)

        speech_text = "Sorry, I had trouble processing your request. Please try again."

        return (
            handler_input.response_builder
                .speak(speech_text)
                .ask("What would you like to try?")
                .response
        )


# =============================================================================
# WebAppChat API Functions
# =============================================================================

def create_chat_session():
    """
    Create a new chat session in WebAppChat.

    Returns:
        str: Chat ID for the new session

    Raises:
        requests.exceptions.RequestException: If API call fails
    """
    url = f"{WEBAPPCHAT_URL}/new-chat"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "title": f"Alexa Session - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    }

    logger.info(f"Creating new chat session at {url}")

    response = requests.post(
        url,
        json=data,
        headers=headers,
        timeout=10
    )
    response.raise_for_status()

    result = response.json()
    return result['id']


def ask_webappchat(prompt, chat_id, model=None, use_rag=None):
    """
    Send a question to WebAppChat.

    Args:
        prompt (str): User's question
        chat_id (str): Chat session ID
        model (str, optional): LLM model to use
        use_rag (bool, optional): Enable RAG search

    Returns:
        dict: API response with 'response', 'usage', 'cost', etc.

    Raises:
        requests.exceptions.RequestException: If API call fails
    """
    url = f"{WEBAPPCHAT_URL}/ask"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "prompt": prompt,
        "chatId": chat_id,
        "model": model or DEFAULT_MODEL,
        "temperature": 0.7,
        "useRag": use_rag if use_rag is not None else USE_RAG,
        "topK": 5
    }

    logger.info(f"Sending request to WebAppChat: {len(prompt)} chars, model={data['model']}, useRag={data['useRag']}")

    response = requests.post(
        url,
        json=data,
        headers=headers,
        timeout=REQUEST_TIMEOUT
    )
    response.raise_for_status()

    return response.json()


def clean_for_speech(text):
    """
    Clean markdown and formatting for Alexa speech output.

    Removes:
    - Markdown formatting (bold, italic, code blocks)
    - Links (keeps link text)
    - Headers
    - Bullet points

    Limits length to MAX_SPEECH_LENGTH for Alexa's 8000 char limit.

    Args:
        text (str): Raw text from LLM

    Returns:
        str: Cleaned text suitable for speech
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

    # Limit length for Alexa speech (8000 char max, use 6000 for safety)
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


# =============================================================================
# Register Handlers
# =============================================================================

sb.add_request_handler(LaunchRequestHandler())
sb.add_request_handler(AskIntentHandler())
sb.add_request_handler(HelpIntentHandler())
sb.add_request_handler(CancelOrStopIntentHandler())
sb.add_request_handler(SessionEndedRequestHandler())
sb.add_exception_handler(AllExceptionHandler())

# =============================================================================
# Lambda Handler Entry Point
# =============================================================================

def lambda_handler(event, context):
    """
    AWS Lambda entry point.

    Args:
        event (dict): Alexa request event
        context: AWS Lambda context

    Returns:
        dict: Alexa response
    """
    logger.info(f"Lambda invoked: {event.get('request', {}).get('type', 'unknown')}")

    try:
        return sb.lambda_handler()(event, context)
    except Exception as e:
        logger.error(f"Lambda handler error: {e}", exc_info=True)
        raise
