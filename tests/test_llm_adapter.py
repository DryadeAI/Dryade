"""Tests for Unified LLM Configuration Adapter.

Tests the config toggle (env/database/auto) and contextvars behavior.
"""

from unittest.mock import MagicMock, patch

import pytest

from core.providers.llm_adapter import (
    LLMConfig,
    get_configured_llm,
    get_llm_config,
)
from core.providers.llm_context import (
    clear_user_llm_context,
    get_user_llm_context,
    set_user_llm_context,
)
from core.providers.user_config import UserLLMConfig

class TestLLMContext:
    """Tests for contextvars-based context management."""

    def setup_method(self):
        """Clear context before each test."""
        clear_user_llm_context()

    def teardown_method(self):
        """Clear context after each test."""
        clear_user_llm_context()

    def test_context_set_get_clear(self):
        """Test basic set/get/clear operations."""
        # Initially None
        assert get_user_llm_context() is None

        # Set config
        config = UserLLMConfig(provider="openai", model="gpt-4")
        set_user_llm_context(config)

        # Get returns same config
        retrieved = get_user_llm_context()
        assert retrieved is not None
        assert retrieved.provider == "openai"
        assert retrieved.model == "gpt-4"

        # Clear returns to None
        clear_user_llm_context()
        assert get_user_llm_context() is None

    def test_context_isolation(self):
        """Test that context is isolated (not shared across tests)."""
        # Should start as None in new test (due to setup_method)
        assert get_user_llm_context() is None

    def test_context_overwrite(self):
        """Test that setting context again overwrites previous value."""
        config1 = UserLLMConfig(provider="openai", model="gpt-4")
        config2 = UserLLMConfig(provider="anthropic", model="claude-3")

        set_user_llm_context(config1)
        assert get_user_llm_context().provider == "openai"

        set_user_llm_context(config2)
        assert get_user_llm_context().provider == "anthropic"

class TestLLMConfigDataclass:
    """Tests for LLMConfig dataclass."""

    def test_to_dict(self):
        """Test config converts to dict correctly."""
        config = LLMConfig(
            provider="openai",
            model="gpt-4",
            base_url=None,
            api_key="sk-test",
            temperature=0.7,
            max_tokens=4096,
            timeout=120,
            source="env",
        )
        d = config.to_dict()
        assert d["provider"] == "openai"
        assert d["model"] == "gpt-4"
        assert d["api_key"] == "sk-test"
        assert d["base_url"] is None
        assert d["temperature"] == 0.7
        assert d["max_tokens"] == 4096
        assert d["timeout"] == 120
        # source not in dict (internal field)
        assert "source" not in d

    def test_to_dict_with_base_url(self):
        """Test config with base_url converts correctly."""
        config = LLMConfig(
            provider="vllm",
            model="local-model",
            base_url="http://localhost:8000/v1",
            api_key=None,
            temperature=0.5,
            max_tokens=2048,
            timeout=60,
            source="env",
        )
        d = config.to_dict()
        assert d["provider"] == "vllm"
        assert d["base_url"] == "http://localhost:8000/v1"
        assert d["api_key"] is None

class TestGetLLMConfig:
    """Tests for get_llm_config() function."""

    def setup_method(self):
        """Clear context before each test."""
        clear_user_llm_context()

    def teardown_method(self):
        """Clear context after each test."""
        clear_user_llm_context()

    @patch("core.providers.llm_adapter.get_settings")
    def test_env_mode_always_uses_env(self, mock_settings):
        """Test that env mode ignores database config."""
        # Setup settings mock
        mock_settings.return_value.llm_config_source = "env"
        mock_settings.return_value.llm_mode = "vllm"
        mock_settings.return_value.llm_model = "local-model"
        mock_settings.return_value.llm_base_url = "http://localhost:8000/v1"
        mock_settings.return_value.llm_api_key = None
        mock_settings.return_value.llm_temperature = 0.7
        mock_settings.return_value.llm_max_tokens = 4096
        mock_settings.return_value.llm_timeout = 120

        # Set user config in context (should be ignored)
        user_config = UserLLMConfig(provider="openai", model="gpt-4", api_key="sk-user")
        set_user_llm_context(user_config)

        # Get config
        config = get_llm_config()

        # Should use env, not database
        assert config.source == "env"
        assert config.provider == "vllm"
        assert config.model == "local-model"

    @patch("core.providers.llm_adapter.get_settings")
    def test_auto_mode_uses_database_when_configured(self, mock_settings):
        """Test that auto mode prefers database config when available."""
        # Setup settings mock
        mock_settings.return_value.llm_config_source = "auto"
        mock_settings.return_value.llm_mode = "vllm"
        mock_settings.return_value.llm_model = "local-model"
        mock_settings.return_value.llm_base_url = "http://localhost:8000/v1"
        mock_settings.return_value.llm_api_key = None
        mock_settings.return_value.llm_temperature = 0.7
        mock_settings.return_value.llm_max_tokens = 4096
        mock_settings.return_value.llm_timeout = 120

        # Set user config in context
        user_config = UserLLMConfig(
            provider="openai",
            model="gpt-4",
            api_key="sk-user",
        )
        set_user_llm_context(user_config)

        # Get config
        config = get_llm_config()

        # Should use database
        assert config.source == "database"
        assert config.model == "gpt-4"

    @patch("core.providers.llm_adapter.get_settings")
    def test_auto_mode_falls_back_to_env(self, mock_settings):
        """Test that auto mode falls back to env when no database config."""
        # Setup settings mock
        mock_settings.return_value.llm_config_source = "auto"
        mock_settings.return_value.llm_mode = "vllm"
        mock_settings.return_value.llm_model = "local-model"
        mock_settings.return_value.llm_base_url = "http://localhost:8000/v1"
        mock_settings.return_value.llm_api_key = None
        mock_settings.return_value.llm_temperature = 0.7
        mock_settings.return_value.llm_max_tokens = 4096
        mock_settings.return_value.llm_timeout = 120

        # No user config in context
        clear_user_llm_context()

        # Get config
        config = get_llm_config()

        # Should use env
        assert config.source == "env"
        assert config.provider == "vllm"

    @patch("core.providers.llm_adapter.get_settings")
    def test_auto_mode_falls_back_when_unconfigured(self, mock_settings):
        """Test that auto mode falls back when user config exists but not configured."""
        # Setup settings mock
        mock_settings.return_value.llm_config_source = "auto"
        mock_settings.return_value.llm_mode = "vllm"
        mock_settings.return_value.llm_model = "local-model"
        mock_settings.return_value.llm_base_url = "http://localhost:8000/v1"
        mock_settings.return_value.llm_api_key = None
        mock_settings.return_value.llm_temperature = 0.7
        mock_settings.return_value.llm_max_tokens = 4096
        mock_settings.return_value.llm_timeout = 120

        # Set unconfigured user config (no provider/model)
        user_config = UserLLMConfig()
        set_user_llm_context(user_config)

        # Get config
        config = get_llm_config()

        # Should fall back to env
        assert config.source == "env"
        assert config.provider == "vllm"

    @patch("core.providers.llm_adapter.get_settings")
    def test_database_mode_requires_config(self, mock_settings):
        """Test that database mode raises error when no config."""
        # Setup settings mock
        mock_settings.return_value.llm_config_source = "database"

        # No user config
        clear_user_llm_context()

        # Should raise ValueError
        with pytest.raises(ValueError, match="user has no LLM configuration"):
            get_llm_config()

    @patch("core.providers.llm_adapter.get_settings")
    def test_database_mode_with_empty_config(self, mock_settings):
        """Test that database mode raises error when config not configured."""
        # Setup settings mock
        mock_settings.return_value.llm_config_source = "database"

        # Set unconfigured user config
        user_config = UserLLMConfig()  # No provider/model
        set_user_llm_context(user_config)

        # Should raise ValueError
        with pytest.raises(ValueError, match="user has no LLM configuration"):
            get_llm_config()

    @patch("core.providers.llm_adapter.get_settings")
    def test_database_mode_uses_database_config(self, mock_settings):
        """Test that database mode uses database config when available."""
        # Setup settings mock
        mock_settings.return_value.llm_config_source = "database"
        mock_settings.return_value.llm_base_url = "http://localhost:8000/v1"
        mock_settings.return_value.llm_api_key = "env-key"
        mock_settings.return_value.llm_temperature = 0.7
        mock_settings.return_value.llm_max_tokens = 4096
        mock_settings.return_value.llm_timeout = 120

        # Set configured user config
        user_config = UserLLMConfig(
            provider="openai",
            model="gpt-4-turbo",
            api_key="user-key",
        )
        set_user_llm_context(user_config)

        # Get config
        config = get_llm_config()

        # Should use database
        assert config.source == "database"
        assert config.model == "gpt-4-turbo"
        # User's API key should override env
        assert config.api_key == "user-key"

class TestGetConfiguredLLM:
    """Tests for get_configured_llm() function."""

    def setup_method(self):
        """Clear context before each test."""
        clear_user_llm_context()

    def teardown_method(self):
        """Clear context after each test."""
        clear_user_llm_context()

    @patch("core.agents.llm.get_llm")
    @patch("core.providers.llm_adapter.get_settings")
    def test_env_mode_calls_get_llm_without_user_config(self, mock_settings, mock_get_llm):
        """Test that env mode calls get_llm without user_config."""
        mock_settings.return_value.llm_config_source = "env"
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm

        result = get_configured_llm()

        mock_get_llm.assert_called_once()
        # Should NOT pass user_config in env mode
        call_kwargs = mock_get_llm.call_args.kwargs
        assert "user_config" not in call_kwargs or call_kwargs.get("user_config") is None

    @patch("core.agents.llm.get_llm")
    @patch("core.providers.llm_adapter.get_settings")
    def test_auto_mode_passes_user_config(self, mock_settings, mock_get_llm):
        """Test that auto mode passes user_config to get_llm."""
        mock_settings.return_value.llm_config_source = "auto"
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm

        # Set user config
        user_config = UserLLMConfig(provider="openai", model="gpt-4")
        set_user_llm_context(user_config)

        result = get_configured_llm()

        mock_get_llm.assert_called_once()
        call_kwargs = mock_get_llm.call_args.kwargs
        assert call_kwargs.get("user_config") == user_config

    @patch("core.agents.llm.get_llm")
    @patch("core.providers.llm_adapter.get_settings")
    def test_database_mode_passes_user_config(self, mock_settings, mock_get_llm):
        """Test that database mode passes user_config to get_llm."""
        mock_settings.return_value.llm_config_source = "database"
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm

        # Set user config
        user_config = UserLLMConfig(provider="anthropic", model="claude-3")
        set_user_llm_context(user_config)

        result = get_configured_llm()

        mock_get_llm.assert_called_once()
        call_kwargs = mock_get_llm.call_args.kwargs
        assert call_kwargs.get("user_config") == user_config

    @patch("core.agents.llm.get_llm")
    @patch("core.providers.llm_adapter.get_settings")
    def test_overrides_passed_through(self, mock_settings, mock_get_llm):
        """Test that overrides are passed to get_llm."""
        mock_settings.return_value.llm_config_source = "env"
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm

        result = get_configured_llm(timeout=300, temperature=0.5)

        mock_get_llm.assert_called_once()
        call_kwargs = mock_get_llm.call_args.kwargs
        assert call_kwargs.get("timeout") == 300
        assert call_kwargs.get("temperature") == 0.5

    @patch("core.providers.llm_adapter.get_settings")
    def test_database_mode_raises_without_config(self, mock_settings):
        """Test that database mode raises error when no config."""
        mock_settings.return_value.llm_config_source = "database"

        # No user config
        clear_user_llm_context()

        # Should raise ValueError
        with pytest.raises(ValueError, match="user has no LLM configuration"):
            get_configured_llm()

    @patch("core.providers.llm_adapter.get_settings")
    def test_database_mode_raises_with_unconfigured_config(self, mock_settings):
        """Test that database mode raises error when config not configured."""
        mock_settings.return_value.llm_config_source = "database"

        # Set unconfigured user config
        user_config = UserLLMConfig()  # No provider/model
        set_user_llm_context(user_config)

        # Should raise ValueError
        with pytest.raises(ValueError, match="user has no LLM configuration"):
            get_configured_llm()

class TestUserLLMConfig:
    """Tests for UserLLMConfig dataclass."""

    def test_is_configured_true(self):
        """Test is_configured returns True when provider and model set."""
        config = UserLLMConfig(provider="openai", model="gpt-4")
        assert config.is_configured() is True

    def test_is_configured_false_no_provider(self):
        """Test is_configured returns False when provider missing."""
        config = UserLLMConfig(model="gpt-4")
        assert config.is_configured() is False

    def test_is_configured_false_no_model(self):
        """Test is_configured returns False when model missing."""
        config = UserLLMConfig(provider="openai")
        assert config.is_configured() is False

    def test_is_configured_false_empty(self):
        """Test is_configured returns False when empty."""
        config = UserLLMConfig()
        assert config.is_configured() is False

    def test_optional_fields(self):
        """Test optional fields work correctly."""
        config = UserLLMConfig(
            provider="openai",
            model="gpt-4",
            endpoint="https://custom.api/v1",
            api_key="sk-custom",
        )
        assert config.provider == "openai"
        assert config.model == "gpt-4"
        assert config.endpoint == "https://custom.api/v1"
        assert config.api_key == "sk-custom"
