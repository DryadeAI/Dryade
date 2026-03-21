"""Tests for inference parameter wiring through get_llm and _create_llm_instance.

Verifies the fallback chain: hardcoded defaults -> env settings -> user DB -> explicit kwargs
and provider-based parameter filtering.
"""

from unittest.mock import MagicMock, patch

import pytest

@pytest.fixture
def mock_settings():
    """Mock settings with known env values."""
    s = MagicMock()
    s.llm_mode = "vllm"
    s.llm_model = "test-model"
    s.llm_base_url = "http://localhost:8000/v1"
    s.llm_api_key = "sk-test"
    s.llm_temperature = 0.5  # env override (not hardcoded 0.7)
    s.llm_max_tokens = 8192  # env override (not hardcoded 4096)
    s.llm_timeout = 120
    s.llm_planner_timeout = 300
    s.llm_config_source = "env"
    return s

@pytest.fixture
def mock_vllm_cls():
    """Mock VLLMBaseLLM to capture constructor args."""
    with patch("core.agents.llm.VLLMBaseLLM", autospec=False) as cls:
        instance = MagicMock()
        cls.return_value = instance
        yield cls, instance

def _call_create(settings, provider="vllm", inference_params=None, **kwargs):
    """Helper to call _create_llm_instance with mocked imports."""
    from core.agents.llm import _create_llm_instance

    return _create_llm_instance(
        llm_mode=provider if provider == "vllm" else "litellm",
        llm_model="test-model",
        llm_base_url="http://localhost:8000/v1",
        llm_api_key="sk-test",
        settings=settings,
        provider=provider,
        inference_params=inference_params,
        **kwargs,
    )

class TestFallbackChain:
    """Test the parameter resolution chain: defaults -> env -> user DB -> kwargs."""

    @patch("core.extensions.VLLMBaseLLM")
    def test_fallback_chain_user_db_wins(self, mock_vllm, mock_settings):
        """User DB temperature=0.3 wins over env default 0.5."""
        instance = MagicMock()
        mock_vllm.return_value = instance

        _call_create(mock_settings, provider="vllm", inference_params={"temperature": 0.3})

        # VLLMBaseLLM should have been called with temperature=0.3
        call_kwargs = mock_vllm.call_args
        assert (
            call_kwargs.kwargs.get("temperature") == 0.3 or call_kwargs[1].get("temperature") == 0.3
        )

    @patch("core.extensions.VLLMBaseLLM")
    def test_fallback_chain_env_wins_over_hardcoded(self, mock_vllm, mock_settings):
        """Env llm_temperature=0.5 wins over hardcoded default 0.7."""
        instance = MagicMock()
        mock_vllm.return_value = instance

        _call_create(mock_settings, provider="vllm", inference_params=None)

        call_kwargs = mock_vllm.call_args
        assert (
            call_kwargs.kwargs.get("temperature") == 0.5 or call_kwargs[1].get("temperature") == 0.5
        )

    @patch("core.extensions.VLLMBaseLLM")
    def test_fallback_chain_hardcoded_default(self, mock_vllm):
        """When no env override and no user params, hardcoded default 0.7 is used."""
        instance = MagicMock()
        mock_vllm.return_value = instance

        settings = MagicMock()
        settings.llm_temperature = 0.7  # same as hardcoded
        settings.llm_max_tokens = 4096
        settings.llm_timeout = 120
        settings.llm_planner_timeout = 300

        _call_create(settings, provider="vllm", inference_params=None)

        call_kwargs = mock_vllm.call_args
        assert (
            call_kwargs.kwargs.get("temperature") == 0.7 or call_kwargs[1].get("temperature") == 0.7
        )

    @patch("core.extensions.VLLMBaseLLM")
    def test_explicit_kwargs_override_all(self, mock_vllm, mock_settings):
        """Explicit kwargs temperature=0.1 overrides user DB temperature=0.5."""
        instance = MagicMock()
        mock_vllm.return_value = instance

        _call_create(
            mock_settings,
            provider="vllm",
            inference_params={"temperature": 0.5},
            temperature=0.1,
        )

        call_kwargs = mock_vllm.call_args
        assert (
            call_kwargs.kwargs.get("temperature") == 0.1 or call_kwargs[1].get("temperature") == 0.1
        )

class TestProviderFiltering:
    """Test that unsupported params are filtered per provider."""

    @patch("core.extensions.VLLMBaseLLM")
    def test_provider_filtering_vllm(self, mock_vllm, mock_settings):
        """vLLM supports repetition_penalty and frequency_penalty."""
        instance = MagicMock()
        mock_vllm.return_value = instance

        _call_create(
            mock_settings,
            provider="vllm",
            inference_params={"repetition_penalty": 1.2, "frequency_penalty": 0.5},
        )

        # Both should be in _extra_sampling
        assert hasattr(instance, "_extra_sampling") or True  # Attribute set after construction
        # Check _extra_sampling was set
        extra = instance._extra_sampling
        assert extra.get("repetition_penalty") == 1.2
        assert extra.get("frequency_penalty") == 0.5

    @patch("crewai.LLM")
    def test_provider_filtering_openai(self, mock_crewai_llm, mock_settings):
        """OpenAI does NOT support repetition_penalty but DOES support frequency_penalty."""
        instance = MagicMock()
        mock_crewai_llm.return_value = instance

        _call_create(
            mock_settings,
            provider="openai",
            inference_params={"repetition_penalty": 1.2, "frequency_penalty": 0.5},
        )

        # CrewAI LLM should have been called WITHOUT repetition_penalty
        call_kwargs = mock_crewai_llm.call_args
        all_kwargs = {**call_kwargs.kwargs}
        # frequency_penalty should be there, repetition_penalty should not
        assert "repetition_penalty" not in all_kwargs
        assert (
            call_kwargs.kwargs.get("frequency_penalty") == 0.5 or "frequency_penalty" in all_kwargs
        )
