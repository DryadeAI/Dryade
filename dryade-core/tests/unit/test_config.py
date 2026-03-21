"""Unit tests for configuration module."""

import os
from unittest.mock import patch

class TestSettings:
    """Tests for Settings class."""

    def test_default_values(self):
        """Test default configuration values."""
        from core.config import Settings

        settings = Settings()

        assert settings.env == "development"
        assert settings.debug is False
        assert settings.log_level == "INFO"
        assert settings.port == 8080
        assert settings.llm_mode == "vllm"

    def test_env_override(self):
        """Test environment variable overrides."""
        with patch.dict(os.environ, {"DRYADE_DEBUG": "true", "DRYADE_PORT": "9000"}):
            from core.config import Settings

            settings = Settings()
            assert settings.debug is True
            assert settings.port == 9000

    def test_llm_settings(self):
        """Test LLM configuration."""
        from core.config import Settings

        settings = Settings()

        assert settings.llm_temperature == 0.7
        assert settings.llm_max_tokens == 4096
        assert settings.llm_timeout == 120

    def test_rate_limit_settings(self):
        """Test rate limiting configuration."""
        from core.config import Settings

        settings = Settings()

        assert settings.rate_limit_enabled is True
        assert settings.rate_limit_default_rpm == 60
        assert settings.rate_limit_pro_rpm == 300
        assert settings.rate_limit_admin_rpm == 1000

    def test_semantic_cache_settings(self):
        """Test semantic cache configuration."""
        from core.config import Settings

        settings = Settings()

        assert settings.semantic_cache_enabled is True
        assert settings.semantic_cache_ttl == 3600
        assert settings.semantic_cache_threshold == 0.85

    def test_get_settings_cached(self):
        """Test settings caching."""
        from core.config import get_settings

        settings1 = get_settings()
        settings2 = get_settings()

        assert settings1 is settings2
