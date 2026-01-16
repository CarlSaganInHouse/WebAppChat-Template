"""
Tests for config.py - Pydantic Settings configuration

Tests cover:
- Default values
- Environment variable loading
- Type validation
- Path handling
- Custom validators
"""

import pytest
import os
from pathlib import Path
from pydantic import ValidationError
from config import Settings, get_settings


class TestConfigDefaults:
    """Test that default values are set correctly"""

    def test_default_model_settings(self):
        """Test LLM default settings"""
        settings = Settings()
        assert settings.default_model == "gpt-4o-mini"
        assert settings.max_context_tokens == 8000

    def test_default_rag_settings(self):
        """Test RAG default settings"""
        settings = Settings()
        assert settings.chunk_size == 500
        assert settings.chunk_overlap == 50
        assert settings.top_k == 5
        assert settings.embedding_model == "text-embedding-3-small"

    def test_default_paths(self):
        """Test that default paths are Path objects"""
        settings = Settings()
        assert isinstance(settings.vault_path, Path)
        assert isinstance(settings.rag_db_path, Path)
        assert isinstance(settings.chats_dir, Path)
        assert settings.vault_path == Path("/app/vault")
        assert settings.rag_db_path == Path("rag.sqlite3")
        assert settings.chats_dir == Path("chats")

    def test_default_flask_settings(self):
        """Test Flask/Server defaults"""
        settings = Settings()
        assert settings.flask_env == "production"
        assert settings.flask_debug is False
        assert settings.port == 5000
        assert settings.allow_debug_endpoint is False

    def test_default_rate_limiting(self):
        """Test rate limiting defaults"""
        settings = Settings()
        assert settings.rate_limit_enabled is True
        assert settings.rate_limit_default == "200 per day, 50 per hour"
        assert settings.rate_limit_ask == "20 per minute"

    def test_default_ollama_host(self):
        """Test Ollama default configuration"""
        settings = Settings()
        assert settings.ollama_host == "http://ollama:11434"


class TestConfigValidation:
    """Test Pydantic validation"""

    def test_max_context_tokens_bounds(self):
        """Test that max_context_tokens is validated"""
        # Valid values
        Settings(max_context_tokens=1000)
        Settings(max_context_tokens=8000)
        Settings(max_context_tokens=128000)

        # Invalid: too small
        with pytest.raises(ValidationError) as exc_info:
            Settings(max_context_tokens=500)
        assert "greater than or equal to 1000" in str(exc_info.value)

        # Invalid: too large
        with pytest.raises(ValidationError) as exc_info:
            Settings(max_context_tokens=200000)
        assert "less than or equal to 128000" in str(exc_info.value)

    def test_chunk_size_bounds(self):
        """Test that chunk_size is validated"""
        # Valid values
        Settings(chunk_size=100)
        Settings(chunk_size=500)
        Settings(chunk_size=2000)

        # Invalid: too small
        with pytest.raises(ValidationError):
            Settings(chunk_size=50)

        # Invalid: too large
        with pytest.raises(ValidationError):
            Settings(chunk_size=3000)

    def test_top_k_bounds(self):
        """Test that top_k is validated"""
        # Valid values
        Settings(top_k=1)
        Settings(top_k=5)
        Settings(top_k=20)

        # Invalid: too small
        with pytest.raises(ValidationError):
            Settings(top_k=0)

        # Invalid: too large
        with pytest.raises(ValidationError):
            Settings(top_k=50)

    def test_port_bounds(self):
        """Test that port is validated"""
        # Valid values
        Settings(port=5000)
        Settings(port=8080)
        Settings(port=65535)

        # Invalid: too small
        with pytest.raises(ValidationError):
            Settings(port=0)

        # Invalid: too large
        with pytest.raises(ValidationError):
            Settings(port=70000)


class TestEnvironmentVariables:
    """Test loading from environment variables"""

    def test_load_from_env(self, monkeypatch):
        """Test that settings load from environment variables"""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key-123")
        monkeypatch.setenv("DEFAULT_MODEL", "gpt-4")
        monkeypatch.setenv("MAX_CONTEXT_TOKENS", "16000")
        monkeypatch.setenv("CHUNK_SIZE", "1000")
        monkeypatch.setenv("PORT", "8080")

        settings = Settings()
        assert settings.openai_api_key == "sk-test-key-123"
        assert settings.default_model == "gpt-4"
        assert settings.max_context_tokens == 16000
        assert settings.chunk_size == 1000
        assert settings.port == 8080

    def test_optional_keys(self, monkeypatch, tmp_path):
        """Test that optional API keys can be set"""
        # Create a test .env file without the optional keys
        test_env = tmp_path / ".env"
        test_env.write_text("OPENAI_API_KEY=test-key\n")

        # Point to the test .env file
        monkeypatch.chdir(tmp_path)

        settings = Settings()
        # Default values for optional keys
        assert settings.anthropic_api_key is None
        assert settings.google_api_key is None

        # Now set them via environment
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("GOOGLE_API_KEY", "google-test")
        settings = Settings()
        assert settings.anthropic_api_key == "sk-ant-test"
        assert settings.google_api_key == "google-test"

    def test_boolean_parsing(self, monkeypatch):
        """Test that boolean env vars are parsed correctly"""
        # Test various boolean representations
        monkeypatch.setenv("FLASK_DEBUG", "true")
        settings = Settings()
        assert settings.flask_debug is True

        monkeypatch.setenv("FLASK_DEBUG", "false")
        settings = Settings()
        assert settings.flask_debug is False

        monkeypatch.setenv("FLASK_DEBUG", "1")
        settings = Settings()
        assert settings.flask_debug is True

        monkeypatch.setenv("FLASK_DEBUG", "0")
        settings = Settings()
        assert settings.flask_debug is False

    def test_case_insensitive_env_vars(self, monkeypatch):
        """Test that env var names are case-insensitive"""
        monkeypatch.setenv("default_model", "gpt-4")
        monkeypatch.setenv("DEFAULT_MODEL", "gpt-4")
        settings = Settings()
        assert settings.default_model == "gpt-4"


class TestPathHandling:
    """Test path validation and conversion"""

    def test_string_to_path_conversion(self, monkeypatch):
        """Test that string paths are converted to Path objects"""
        monkeypatch.setenv("VAULT_PATH", "/custom/vault")
        monkeypatch.setenv("RAG_DB_PATH", "custom_rag.db")

        settings = Settings()
        assert isinstance(settings.vault_path, Path)
        assert isinstance(settings.rag_db_path, Path)
        assert settings.vault_path == Path("/custom/vault")
        assert settings.rag_db_path == Path("custom_rag.db")

    def test_ensure_directories(self, tmp_path):
        """Test ensure_directories creates missing directories"""
        test_chats_dir = tmp_path / "test_chats"
        settings = Settings(chats_dir=test_chats_dir)

        assert not test_chats_dir.exists()
        settings.ensure_directories()
        assert test_chats_dir.exists()
        assert test_chats_dir.is_dir()


class TestGetSettings:
    """Test get_settings function"""

    def test_get_settings_returns_global(self):
        """Test that get_settings returns the global instance"""
        from config import settings as global_settings
        assert get_settings() is global_settings

    def test_get_settings_is_callable(self):
        """Test that get_settings can be called multiple times"""
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2  # Should be same instance


class TestModelConfig:
    """Test get_model_config method"""

    def test_get_model_config(self):
        """Test get_model_config returns correct config"""
        settings = Settings(max_context_tokens=16000)
        config = settings.get_model_config("gpt-4")

        assert isinstance(config, dict)
        assert "max_context_tokens" in config
        assert config["max_context_tokens"] == 16000


class TestValidators:
    """Test custom validators"""

    def test_openai_key_warning(self):
        """Test that missing OpenAI key triggers warning"""
        import warnings

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            Settings(openai_api_key="")

            # Should have warning about missing key
            assert len(w) >= 1
            assert "OPENAI_API_KEY not set" in str(w[0].message)

    def test_openai_key_no_warning_when_set(self):
        """Test that no warning when OpenAI key is set"""
        import warnings

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            Settings(openai_api_key="sk-test-key")

            # Should not have warning about OpenAI key
            openai_warnings = [warning for warning in w
                             if "OPENAI_API_KEY" in str(warning.message)]
            assert len(openai_warnings) == 0


class TestIntegration:
    """Integration tests for config usage"""

    def test_production_config(self):
        """Test a typical production configuration"""
        settings = Settings(
            openai_api_key="sk-prod-key",
            default_model="gpt-4",
            vault_path=Path("/app/vault"),
            flask_env="production",
            flask_debug=False,
            rate_limit_enabled=True
        )

        assert settings.openai_api_key == "sk-prod-key"
        assert settings.default_model == "gpt-4"
        assert settings.flask_env == "production"
        assert settings.flask_debug is False
        assert settings.rate_limit_enabled is True

    def test_development_config(self):
        """Test a typical development configuration"""
        settings = Settings(
            openai_api_key="sk-dev-key",
            vault_path=Path("./test_vault"),
            flask_env="development",
            flask_debug=True,
            allow_debug_endpoint=True,
            rate_limit_enabled=False
        )

        assert settings.flask_env == "development"
        assert settings.flask_debug is True
        assert settings.allow_debug_endpoint is True
        assert settings.rate_limit_enabled is False
