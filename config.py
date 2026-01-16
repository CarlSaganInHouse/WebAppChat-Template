"""
Application configuration using Pydantic Settings.
Centralizes all configuration with type safety, validation, and environment variable support.
"""

from pathlib import Path
from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings with environment variable support.

    Environment variables can be set in .env file or system environment.
    All settings have sensible defaults for development.
    """

    # ========== API Keys ==========
    openai_api_key: str = Field(
        default="",
        description="OpenAI API key for GPT models and embeddings"
    )
    anthropic_api_key: Optional[str] = Field(
        default=None,
        description="Anthropic API key for Claude models"
    )
    google_api_key: Optional[str] = Field(
        default=None,
        description="Google API key for Gemini models"
    )

    # ========== LLM Configuration ==========
    default_model: str = Field(
        default="gpt-4o-mini",
        description="Default LLM model to use for chat"
    )
    max_context_tokens: int = Field(
        default=8000,
        ge=1000,
        le=128000,
        description="Maximum tokens to keep in conversation context"
    )
    # ========== Agent Mode ==========
    agent_mode: str = Field(
        default="structured",
        description="Tool mode: 'structured' uses 30+ specific tools with routing, 'autonomous' uses 5 general tools with permissive prompts"
    )
    autonomous_verify_writes: bool = Field(
        default=False,
        description="Enable write verification in autonomous mode (disabled by default for speed)"
    )

    enable_enhanced_vault_guidance: bool = Field(
        default=True,
        description="Include the detailed vault guidance system prompt block for supporting providers"
    )
    require_tool_for_writes: bool = Field(
        default=True,
        description="Force a retry with an explicit reminder when write-intent requests omit tool calls"
    )
    require_tool_for_reads: bool = Field(
        default=True,
        description="Force a retry with an explicit reminder when read-intent requests omit tool calls"
    )
    verify_vault_writes: bool = Field(
        default=True,
        description="Perform a lightweight read-after-write check for note-creation/update tools"
    )
    verification_max_retries: int = Field(
        default=2,
        ge=0,
        le=5,
        description="Maximum retry attempts for failed write verifications (0 to disable retries)"
    )
    verification_retry_delay: float = Field(
        default=0.5,
        ge=0.0,
        le=5.0,
        description="Delay in seconds between verification retries"
    )
    verification_strict_mode: bool = Field(
        default=True,
        description="When True, mark operation as failed if verification fails; when False, log warning only"
    )

    # ========== RAG Configuration ==========
    chunk_size: int = Field(
        default=500,
        ge=100,
        le=2000,
        description="Maximum tokens per text chunk for RAG"
    )
    chunk_overlap: int = Field(
        default=50,
        ge=0,
        le=500,
        description="Token overlap between chunks (for future improvement)"
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of top results to return from RAG search"
    )
    embedding_model: str = Field(
        default="text-embedding-3-small",
        description="OpenAI embedding model for RAG"
    )

    # ========== Obsidian Vault ==========
    vault_path: Path = Field(
        default=Path("/app/vault"),
        description="Path to Obsidian vault directory"
    )
    vault_name: str = Field(
        default="obsidian-vault",
        description="Name of Obsidian vault for generating deep links"
    )
    timezone: str = Field(
        default="America/New_York",
        description="User's local timezone (e.g., 'America/New_York', 'Europe/London')"
    )

    # ========== Vault Folder Structure ==========
    inbox_folder: str = Field(
        default="00-Inbox",
        description="Folder for inbox captures (quick notes, voice memos, etc.)"
    )
    daily_notes_folder: str = Field(
        default="60-Calendar/Daily",
        description="Folder for daily notes"
    )
    templates_folder: str = Field(
        default="90-Meta/Templates",
        description="Folder for note templates"
    )
    attachments_folder: str = Field(
        default="90-Meta/Attachments",
        description="Folder for image uploads and attachments"
    )
    rag_exclude_folders: list[str] = Field(
        default=["00-Inbox", "90-Meta"],
        description="Folders to exclude from RAG indexing (comma-separated in env var)"
    )
    todo_sync_path: str = Field(
        default="60-Calendar/Task-List.md",
        description="Path for todo sync file relative to vault root"
    )

    # ========== Ollama Configuration ==========
    ollama_host: str = Field(
        default="http://ollama:11434",
        description="Ollama service URL (use http://localhost:11434 for local)"
    )
    ollama_prompt_variant: str = Field(
        default="NO_PROMPT",
        description="System prompt variant for Ollama tool calling: NO_PROMPT, TIME_ONLY, CURRENT, OBSIDIAN_ONLY, CLAUDE_STYLE, STRUCTURED_COMPACT, ACTION_FOCUSED"
    )
    ollama_temperature: float = Field(
        default=0.3,
        ge=0.0,
        le=2.0,
        description="Sampling temperature for Ollama models (0.0-2.0, lower = more deterministic)"
    )
    ollama_payload_debug_dir: Optional[Path] = Field(
        default=None,
        description="If set, write Ollama request payloads to this directory for debugging"
    )

    # ========== Flask/Server Configuration ==========
    flask_env: str = Field(
        default="production",
        description="Flask environment (development/production)"
    )
    flask_debug: bool = Field(
        default=False,
        description="Enable Flask debug mode"
    )
    port: int = Field(
        default=5000,
        ge=1,
        le=65535,
        description="Port to run Flask server on"
    )
    allow_debug_endpoint: bool = Field(
        default=False,
        description="Enable /_debug_env endpoint (development only)"
    )

    # ========== Rate Limiting ==========
    rate_limit_enabled: bool = Field(
        default=True,
        description="Enable rate limiting on API endpoints"
    )
    rate_limit_default: str = Field(
        default="200 per day, 50 per hour",
        description="Default rate limit for all endpoints"
    )
    rate_limit_ask: str = Field(
        default="20 per minute",
        description="Rate limit for /ask endpoint (most expensive)"
    )

    # ========== Database ==========
    rag_db_path: Path = Field(
        default=Path("rag.sqlite3"),
        description="Path to RAG SQLite database"
    )

    # ========== Chat Storage ==========
    use_sqlite_chats: bool = Field(
        default=False,
        description="Use SQLite for chat storage instead of JSON files (feature flag)"
    )
    chats_dir: Path = Field(
        default=Path("chats"),
        description="Directory for storing chat JSON files"
    )
    chat_db_path: Path = Field(
        default=Path("chats.sqlite3"),
        description="Path to chat SQLite database (when use_sqlite_chats=True)"
    )

    # ========== Usage Logging ==========
    usage_log_path: Path = Field(
        default=Path("chats/usage_log.csv"),
        description="Path to usage log CSV file (defaults under chats/)"
    )

    # ========== WebDAV Configuration ==========
    webdav_enabled: bool = Field(
        default=False,
        description="Enable WebDAV server for remote vault access"
    )
    webdav_port: int = Field(
        default=8080,
        ge=1,
        le=65535,
        description="Port for WebDAV server"
    )
    webdav_auth_users: str = Field(
        default="{}",
        description="JSON dict of username:bcrypt_hash for WebDAV authentication"
    )
    webdav_max_file_size: int = Field(
        default=104857600,  # 100MB
        ge=1024,
        description="Maximum file size for WebDAV uploads (bytes)"
    )
    webdav_log_level: str = Field(
        default="INFO",
        description="Log level for WebDAV server (DEBUG, INFO, WARNING, ERROR)"
    )

    # ========== MCP Filesystem Configuration ==========
    mcp_enabled: bool = Field(
        default=True,
        description="Enable MCP filesystem for compatible local models"
    )
    mcp_allowed_dirs: str = Field(
        default="/mnt/obsidian-vault",
        description="Comma-separated list of allowed directories for MCP filesystem access"
    )
    mcp_max_iterations: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum number of function call iterations to prevent infinite loops"
    )
    mcp_function_timeout: int = Field(
        default=30,
        ge=5,
        le=300,
        description="Timeout in seconds for MCP function execution"
    )
    mcp_log_function_calls: bool = Field(
        default=True,
        description="Log all function calls for debugging and analysis"
    )


    # ========== RAG Auto-Sync Configuration ==========
    rag_auto_sync_enabled: bool = Field(
        default=True,
        description="Enable automatic RAG synchronization of vault files"
    )
    rag_auto_sync_interval_minutes: int = Field(
        default=15,
        ge=5,
        le=60,
        description="Interval in minutes between automatic RAG syncs (5-60)"
    )
    rag_sync_on_startup: bool = Field(
        default=True,
        description="Perform RAG sync on application startup"
    )
    rag_sync_log_path: Path = Field(
        default=Path("logs/rag_sync.log"),
        description="Path to RAG sync log file"
    )

    # ========== Voice Assistant Configuration ==========
    voice_enabled: bool = Field(
        default=True,
        description="Enable voice assistant endpoints (/voice/*)"
    )
    whisper_model: str = Field(
        default="whisper-1",
        description="OpenAI Whisper model for speech-to-text"
    )
    tts_model: str = Field(
        default="tts-1",
        description="OpenAI TTS model for text-to-speech (tts-1, tts-1-hd)"
    )
    tts_voice: str = Field(
        default="alloy",
        description="OpenAI TTS voice (alloy, echo, fable, onyx, nova, shimmer)"
    )
    voice_chat_prefix: str = Field(
        default="Kitchen Voice",
        description="Prefix for voice assistant chat session names"
    )
    voice_max_audio_mb: int = Field(
        default=10,
        ge=1,
        le=25,
        description="Maximum audio upload size in MB (Whisper limit is 25MB)"
    )
    voice_default_model: str = Field(
        default="gpt-4o-mini",
        description="Default LLM model for voice interactions"
    )

    # ========== Authentication Configuration ==========
    flask_secret_key: str = Field(
        default="dev-secret-key-change-in-production",
        description="Flask session secret key (should be a random 32+ character string)"
    )
    session_lifetime_days: int = Field(
        default=30,
        ge=1,
        le=365,
        description="Session cookie lifetime in days"
    )
    bcrypt_rounds: int = Field(
        default=12,
        ge=10,
        le=14,
        description="Number of bcrypt rounds for password hashing"
    )
    login_rate_limit: str = Field(
        default="5/minute",
        description="Rate limit for login attempts (e.g., '5/minute', '10/hour')"
    )
    auth_enabled: bool = Field(
        default=True,
        description="Enable authentication on all protected routes"
    )

    # ========== Pydantic Configuration ==========
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"  # Ignore extra fields in .env
    )

    @field_validator("vault_path", "rag_db_path", "chats_dir", "chat_db_path", "usage_log_path")
    @classmethod
    def validate_paths(cls, v: Path) -> Path:
        """Ensure paths are Path objects"""
        if isinstance(v, str):
            return Path(v)
        return v

    @field_validator("rag_exclude_folders", mode="before")
    @classmethod
    def parse_rag_exclude_folders(cls, v) -> list[str]:
        """Parse rag_exclude_folders - accepts JSON array or comma-separated string"""
        if v is None:
            return []
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            # Try JSON first (e.g., '["00-Inbox","90-Meta"]')
            v_stripped = v.strip()
            if v_stripped.startswith('['):
                import json
                try:
                    return json.loads(v_stripped)
                except json.JSONDecodeError:
                    pass
            # Fall back to comma-separated (e.g., "00-Inbox,90-Meta")
            return [folder.strip() for folder in v.split(",") if folder.strip()]
        return []

    @field_validator("openai_api_key")
    @classmethod
    def validate_openai_key(cls, v: str) -> str:
        """Warn if OpenAI key is missing (required for embeddings)"""
        if not v or v == "":
            import warnings
            warnings.warn(
                "OPENAI_API_KEY not set. OpenAI models and embeddings will not work.",
                UserWarning
            )
        return v

    def get_model_config(self, model: str) -> dict:
        """
        Get configuration for a specific model.

        Args:
            model: Model name (e.g., "gpt-4", "llama3", etc.)

        Returns:
            Dictionary with model-specific config
        """
        # For future use with provider abstraction
        return {
            "max_context_tokens": self.max_context_tokens,
        }

    def ensure_directories(self) -> None:
        """
        Ensure all required directories exist.
        Call this at application startup.
        """
        self.chats_dir.mkdir(parents=True, exist_ok=True)
        # Note: vault_path should already exist (mounted in Docker)
        # Note: rag_db_path is a file, not a directory
        # Ensure usage log directory exists
        try:
            self.usage_log_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            # Non-fatal: leave creation to first writer if path is relative-only
            pass


# Global settings instance
# This will load from .env automatically
settings = Settings()


def get_settings() -> Settings:
    """
    Get the global settings instance.

    This function exists for:
    1. Dependency injection in tests
    2. Future FastAPI migration (FastAPI uses Depends(get_settings))
    3. Explicit over implicit

    Returns:
        Global settings instance
    """
    return settings
