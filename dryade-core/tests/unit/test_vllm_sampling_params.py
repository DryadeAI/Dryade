"""Tests for VLLMBaseLLM receiving extra sampling parameters.

Verifies that _extra_sampling is correctly populated with non-constructor
params and that constructor params (temperature, max_tokens, timeout) are excluded.
"""

from unittest.mock import MagicMock, patch

import pytest

@pytest.fixture
def mock_settings():
    """Mock settings with known env values."""
    s = MagicMock()
    s.llm_temperature = 0.7
    s.llm_max_tokens = 4096
    s.llm_timeout = 120
    s.llm_planner_timeout = 300
    return s

def _create_vllm(settings, inference_params=None, **kwargs):
    """Helper to create a vLLM instance via _create_llm_instance."""
    from core.agents.llm import _create_llm_instance

    return _create_llm_instance(
        llm_mode="vllm",
        llm_model="test-model",
        llm_base_url="http://localhost:8000/v1",
        llm_api_key="sk-test",
        settings=settings,
        provider="vllm",
        inference_params=inference_params,
        **kwargs,
    )

class TestVLLMExtraSampling:
    """Test _extra_sampling dict on VLLMBaseLLM instances."""

    @patch("core.providers.vllm_llm.VLLMBaseLLM")
    def test_vllm_receives_extra_sampling(self, mock_vllm, mock_settings):
        """VLLMBaseLLM instance gets _extra_sampling with top_p, top_k, repetition_penalty."""
        instance = MagicMock()
        mock_vllm.return_value = instance

        _create_vllm(
            mock_settings,
            inference_params={
                "top_p": 0.85,
                "top_k": 50,
                "repetition_penalty": 1.2,
                "frequency_penalty": 0.3,
                "presence_penalty": 0.1,
            },
        )

        extra = instance._extra_sampling
        assert extra["top_p"] == 0.85
        assert extra["top_k"] == 50
        assert extra["repetition_penalty"] == 1.2
        assert extra["frequency_penalty"] == 0.3
        assert extra["presence_penalty"] == 0.1

    @patch("core.providers.vllm_llm.VLLMBaseLLM")
    def test_vllm_extra_sampling_excludes_constructor_params(self, mock_vllm, mock_settings):
        """_extra_sampling does NOT contain temperature, max_tokens, timeout, planner_timeout, stop."""
        instance = MagicMock()
        mock_vllm.return_value = instance

        _create_vllm(mock_settings, inference_params={"top_p": 0.9})

        extra = instance._extra_sampling
        for excluded in ("temperature", "max_tokens", "timeout", "planner_timeout", "stop"):
            assert excluded not in extra, f"{excluded} should not be in _extra_sampling"

    @patch("core.providers.vllm_llm.VLLMBaseLLM")
    def test_vllm_sampling_params_from_user_config(self, mock_vllm, mock_settings):
        """User-configured top_k=50 and repetition_penalty=1.2 propagate to _extra_sampling."""
        instance = MagicMock()
        mock_vllm.return_value = instance

        _create_vllm(
            mock_settings,
            inference_params={"top_k": 50, "repetition_penalty": 1.2},
        )

        extra = instance._extra_sampling
        assert extra["top_k"] == 50
        assert extra["repetition_penalty"] == 1.2

    @patch("core.providers.vllm_llm.VLLMBaseLLM")
    def test_vllm_empty_extra_sampling_when_no_extra_params(self, mock_vllm, mock_settings):
        """When only constructor params are present, _extra_sampling is empty or has defaults only."""
        instance = MagicMock()
        mock_vllm.return_value = instance

        _create_vllm(mock_settings, inference_params=None)

        extra = instance._extra_sampling
        # Should not contain constructor params
        for excluded in ("temperature", "max_tokens", "timeout", "planner_timeout", "stop"):
            assert excluded not in extra
