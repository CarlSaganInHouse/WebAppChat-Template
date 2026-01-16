"""
Voice Assistant Routes - ESP32 and other voice device integration

Endpoints:
- POST /voice/process - Combined STT -> LLM -> TTS pipeline
- POST /voice/transcribe - STT only (Whisper)
- POST /voice/tts - TTS only (OpenAI Speech)
- GET /voice/status - Health check

Hardware Target: ESP32-S3 with INMP441 microphone and MAX98357A amplifier
"""

from flask import Blueprint, request, jsonify, Response, current_app
from datetime import datetime
import logging
import io
import struct
import re
from typing import Dict, Any, Tuple

from config import get_settings
from storage import new_chat, load_chat

# OpenAI client
from openai import OpenAI

logger = logging.getLogger(__name__)
voice_bp = Blueprint('voice', __name__, url_prefix='/voice')

# Constants
MAX_SPEECH_LENGTH = 2000  # Character limit for TTS (cost control)


def _get_settings():
    """Get settings lazily to avoid import-time issues."""
    return get_settings()


def _validate_wav_header(audio_data: bytes) -> Tuple[bool, str]:
    """
    Validate WAV file header and extract format info.

    Returns:
        (is_valid, error_message_or_format_info)
    """
    if len(audio_data) < 44:
        return False, "Audio data too short for WAV header"

    # Check RIFF header
    if audio_data[:4] != b'RIFF':
        return False, "Missing RIFF header"
    if audio_data[8:12] != b'WAVE':
        return False, "Missing WAVE format marker"

    # Parse fmt chunk
    if audio_data[12:16] != b'fmt ':
        return False, "Missing fmt chunk"

    # Extract format info (little-endian)
    audio_format = struct.unpack('<H', audio_data[20:22])[0]
    num_channels = struct.unpack('<H', audio_data[22:24])[0]
    sample_rate = struct.unpack('<I', audio_data[24:28])[0]
    bits_per_sample = struct.unpack('<H', audio_data[34:36])[0]

    if audio_format != 1:  # PCM
        return False, f"Unsupported audio format: {audio_format} (expected PCM=1)"

    format_info = f"{sample_rate}Hz, {bits_per_sample}-bit, {num_channels}ch"
    return True, format_info


def _transcribe_audio(audio_data: bytes, filename: str = "audio.wav") -> Tuple[str, Dict[str, Any]]:
    """
    Transcribe audio using OpenAI Whisper API.

    Args:
        audio_data: WAV audio bytes
        filename: Filename hint for API

    Returns:
        (transcription_text, usage_info)
    """
    settings = _get_settings()
    client = OpenAI(api_key=settings.openai_api_key)

    # Create file-like object for API
    audio_file = io.BytesIO(audio_data)
    audio_file.name = filename

    response = client.audio.transcriptions.create(
        model=settings.whisper_model,
        file=audio_file,
        response_format="text"
    )

    # Whisper pricing: $0.006 per minute
    # Estimate duration from file size (16kHz, 16-bit mono = 32KB/sec)
    estimated_seconds = len(audio_data) / 32000
    estimated_cost = (estimated_seconds / 60) * 0.006

    usage_info = {
        "model": settings.whisper_model,
        "estimated_duration_seconds": round(estimated_seconds, 2),
        "estimated_cost": round(estimated_cost, 6)
    }

    return response.strip(), usage_info


def _synthesize_speech(text: str, voice: str = None) -> Tuple[bytes, Dict[str, Any]]:
    """
    Convert text to speech using OpenAI TTS API.

    Args:
        text: Text to synthesize
        voice: Optional voice override

    Returns:
        (audio_bytes_mp3, usage_info)
    """
    settings = _get_settings()
    client = OpenAI(api_key=settings.openai_api_key)

    voice = voice or settings.tts_voice

    response = client.audio.speech.create(
        model=settings.tts_model,
        voice=voice,
        input=text,
        response_format="mp3"
    )

    audio_bytes = response.content

    # TTS pricing: $15.00/1M characters (tts-1), $30.00/1M (tts-1-hd)
    char_count = len(text)
    price_per_char = 0.000015 if settings.tts_model == "tts-1" else 0.000030
    estimated_cost = char_count * price_per_char

    usage_info = {
        "model": settings.tts_model,
        "voice": voice,
        "character_count": char_count,
        "audio_size_bytes": len(audio_bytes),
        "estimated_cost": round(estimated_cost, 6)
    }

    return audio_bytes, usage_info


def _process_chat_request(prompt: str, chat_id: str, model: str,
                          use_rag: bool = True, temperature: float = 0.7) -> Dict[str, Any]:
    """
    Send transcription to chat backend using internal test client.

    Follows pattern from alexa_handler.py.
    """
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
            error_data = response.get_json() or {}
            error_msg = error_data.get('error', 'Unknown error')
            logger.error(f"Error from /ask endpoint: {error_msg} (status {response.status_code})")
            raise Exception(f"Chat request failed: {error_msg}")


def _clean_for_speech(text: str) -> str:
    """
    Clean markdown formatting for TTS output.

    Based on alexa_handler.py clean_for_speech().
    """
    # Remove markdown formatting
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)  # Bold
    text = re.sub(r'\*(.+?)\*', r'\1', text)      # Italic
    text = re.sub(r'__(.+?)__', r'\1', text)      # Bold alt
    text = re.sub(r'_(.+?)_', r'\1', text)        # Italic alt
    text = re.sub(r'`(.+?)`', r'\1', text)        # Inline code
    text = re.sub(r'```[\s\S]*?```', '', text)    # Code blocks (remove entirely)
    text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)  # Links (keep text)
    text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE)  # Headers

    # Clean list formatting
    text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)

    # Clean whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()

    # Limit length for TTS (cost control and reasonable response time)
    if len(text) > MAX_SPEECH_LENGTH:
        logger.warning(f"Response truncated from {len(text)} to {MAX_SPEECH_LENGTH} chars")
        truncated = text[:MAX_SPEECH_LENGTH]
        last_sentence = max(
            truncated.rfind('.'),
            truncated.rfind('?'),
            truncated.rfind('!')
        )
        if last_sentence > MAX_SPEECH_LENGTH * 0.7:
            truncated = truncated[:last_sentence + 1]
        text = truncated + " Response truncated."

    return text


@voice_bp.route('/process', methods=['POST'])
def voice_process():
    """
    Combined voice processing endpoint: STT -> LLM -> TTS

    Accepts:
        multipart/form-data with:
        - audio: WAV file (16kHz, 16-bit, mono recommended)
        - session_id: Optional session ID for conversation continuity
        - model: Optional LLM model override
        - use_rag: Optional RAG toggle (default: true)

    Returns:
        audio/mpeg binary (MP3) on success
        application/json with error on failure
    """
    settings = _get_settings()

    if not settings.voice_enabled:
        return jsonify({"error": "voice_disabled"}), 503

    if not settings.openai_api_key:
        return jsonify({"error": "openai_key_missing"}), 500

    # Get audio file
    if 'audio' not in request.files:
        return jsonify({"error": "no_audio_file"}), 400

    audio_file = request.files['audio']
    audio_data = audio_file.read()

    # Validate size
    max_size = settings.voice_max_audio_mb * 1024 * 1024
    if len(audio_data) > max_size:
        return jsonify({
            "error": "audio_too_large",
            "max_mb": settings.voice_max_audio_mb
        }), 400

    if len(audio_data) < 1000:
        return jsonify({"error": "audio_too_small"}), 400

    # Validate WAV format
    is_valid, format_info = _validate_wav_header(audio_data)
    if not is_valid:
        return jsonify({"error": "invalid_wav", "detail": format_info}), 400

    logger.info(f"Voice request received: {len(audio_data)} bytes, {format_info}")

    # Get optional parameters
    session_id = request.form.get('session_id', '')
    model = request.form.get('model', settings.voice_default_model)
    use_rag = request.form.get('use_rag', 'true').lower() == 'true'

    try:
        # Step 1: Transcribe audio (STT)
        transcription, stt_usage = _transcribe_audio(audio_data)

        if not transcription.strip():
            return jsonify({"error": "empty_transcription", "detail": "No speech detected"}), 400

        logger.info(f"Transcription: '{transcription[:100]}{'...' if len(transcription) > 100 else ''}'")

        # Step 2: Get or create chat session
        if session_id:
            chat = load_chat(session_id)
            if not chat:
                # Session expired or invalid, create new
                logger.info(f"Session {session_id} not found, creating new")
                session_id = ""

        if not session_id:
            today = datetime.now().strftime('%Y-%m-%d')
            chat = new_chat(title=f"{settings.voice_chat_prefix} - {today}")
            session_id = chat['id']
            logger.info(f"Created new voice session: {session_id}")

        # Step 3: Process through LLM (reuse /ask logic)
        llm_response = _process_chat_request(
            prompt=transcription,
            chat_id=session_id,
            model=model,
            use_rag=use_rag
        )

        response_text = llm_response.get('text', '')
        llm_usage = llm_response.get('usage', {})

        if not response_text:
            return jsonify({"error": "empty_llm_response"}), 500

        # Step 4: Clean and synthesize speech (TTS)
        clean_text = _clean_for_speech(response_text)
        audio_response, tts_usage = _synthesize_speech(clean_text)

        logger.info(f"TTS complete: {tts_usage['audio_size_bytes']} bytes, {tts_usage['character_count']} chars")

        # Calculate total cost
        total_cost = (
            stt_usage.get('estimated_cost', 0) +
            llm_usage.get('cost_total', 0) +
            tts_usage.get('estimated_cost', 0)
        )

        # Return MP3 audio with metadata headers
        response = Response(
            audio_response,
            mimetype='audio/mpeg',
            headers={
                'X-Session-Id': session_id,
                'X-Transcription': transcription[:200].replace('\n', ' '),
                'X-STT-Cost': f"{stt_usage.get('estimated_cost', 0):.6f}",
                'X-LLM-Cost': f"{llm_usage.get('cost_total', 0):.6f}",
                'X-TTS-Cost': f"{tts_usage.get('estimated_cost', 0):.6f}",
                'X-Total-Cost': f"{total_cost:.6f}",
                'Content-Disposition': 'inline; filename="response.mp3"'
            }
        )

        return response

    except Exception as e:
        logger.error(f"Voice processing error: {e}", exc_info=True)
        return jsonify({"error": "processing_failed", "detail": str(e)}), 500


@voice_bp.route('/transcribe', methods=['POST'])
def voice_transcribe():
    """
    Speech-to-text only endpoint.

    Accepts:
        multipart/form-data with audio file (WAV)

    Returns:
        JSON with transcription text and usage info
    """
    settings = _get_settings()

    if not settings.voice_enabled:
        return jsonify({"error": "voice_disabled"}), 503

    if not settings.openai_api_key:
        return jsonify({"error": "openai_key_missing"}), 500

    if 'audio' not in request.files:
        return jsonify({"error": "no_audio_file"}), 400

    audio_file = request.files['audio']
    audio_data = audio_file.read()

    # Validate size
    max_size = settings.voice_max_audio_mb * 1024 * 1024
    if len(audio_data) > max_size:
        return jsonify({
            "error": "audio_too_large",
            "max_mb": settings.voice_max_audio_mb
        }), 400

    try:
        transcription, usage = _transcribe_audio(audio_data)
        return jsonify({
            "text": transcription,
            "usage": usage
        })
    except Exception as e:
        logger.error(f"Transcription error: {e}", exc_info=True)
        return jsonify({"error": "transcription_failed", "detail": str(e)}), 500


@voice_bp.route('/tts', methods=['POST'])
def voice_tts():
    """
    Text-to-speech only endpoint.

    Accepts:
        JSON with:
        - text: Text to synthesize (required)
        - voice: Optional voice override

    Returns:
        audio/mpeg binary (MP3)
    """
    settings = _get_settings()

    if not settings.voice_enabled:
        return jsonify({"error": "voice_disabled"}), 503

    if not settings.openai_api_key:
        return jsonify({"error": "openai_key_missing"}), 500

    data = request.get_json(force=True) or {}
    text = (data.get('text') or '').strip()

    if not text:
        return jsonify({"error": "empty_text"}), 400

    # Limit text length for cost control
    if len(text) > 4000:
        return jsonify({"error": "text_too_long", "max_chars": 4000}), 400

    voice = data.get('voice', settings.tts_voice)

    try:
        audio_bytes, usage = _synthesize_speech(text, voice)

        return Response(
            audio_bytes,
            mimetype='audio/mpeg',
            headers={
                'X-Voice': voice,
                'X-Character-Count': str(len(text)),
                'X-Estimated-Cost': f"{usage['estimated_cost']:.6f}",
                'Content-Disposition': 'inline; filename="tts.mp3"'
            }
        )
    except Exception as e:
        logger.error(f"TTS error: {e}", exc_info=True)
        return jsonify({"error": "tts_failed", "detail": str(e)}), 500


@voice_bp.route('/status', methods=['GET'])
def voice_status():
    """
    Health check endpoint for voice services.

    Returns status of voice configuration and API connectivity.
    """
    settings = _get_settings()

    return jsonify({
        "enabled": settings.voice_enabled,
        "whisper_model": settings.whisper_model,
        "tts_model": settings.tts_model,
        "tts_voice": settings.tts_voice,
        "voice_chat_prefix": settings.voice_chat_prefix,
        "voice_default_model": settings.voice_default_model,
        "max_audio_mb": settings.voice_max_audio_mb,
        "openai_configured": bool(settings.openai_api_key)
    })
