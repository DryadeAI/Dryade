"""Unit tests for inference parameter specs, validation, filtering, and presets."""

import pytest

from core.providers.inference_params import (
    CAPABILITY_PARAM_SUPPORT,
    INFERENCE_PARAMS,
    PRESETS,
    PROVIDER_PARAM_SUPPORT,
    VLLM_SERVER_PARAMS,
    filter_params_for_provider,
    get_defaults,
    get_param_specs_for_api,
    get_provider_params_for_api,
    validate_params,
)

class TestGetDefaults:
    def test_get_defaults(self):
        """Returns dict with all 9 params and correct default values."""
        defaults = get_defaults()
        assert defaults["temperature"] == 0.7
        assert defaults["top_p"] == 0.9
        assert defaults["top_k"] == -1
        assert defaults["max_tokens"] == 4096
        assert defaults["repetition_penalty"] == 1.0
        assert defaults["frequency_penalty"] == 0.0
        assert defaults["presence_penalty"] == 0.0
        assert defaults["timeout"] == 120
        assert defaults["planner_timeout"] == 300
        assert len(defaults) == 9

class TestFilterParams:
    def test_filter_params_openai(self):
        """OpenAI only supports temperature, top_p, max_tokens, frequency_penalty, presence_penalty, stop, timeout."""
        params = {
            "temperature": 0.5,
            "top_p": 0.8,
            "top_k": 50,
            "max_tokens": 2048,
            "repetition_penalty": 1.2,
            "frequency_penalty": 0.5,
            "presence_penalty": 0.3,
            "stop": ["\n"],
            "timeout": 60,
        }
        filtered = filter_params_for_provider(params, "openai")
        assert "temperature" in filtered
        assert "top_p" in filtered
        assert "max_tokens" in filtered
        assert "frequency_penalty" in filtered
        assert "presence_penalty" in filtered
        assert "stop" in filtered
        assert "timeout" in filtered
        assert "top_k" not in filtered
        assert "repetition_penalty" not in filtered

    def test_filter_params_anthropic(self):
        """Anthropic supports temperature, top_p, top_k, max_tokens, stop, timeout only."""
        params = {
            "temperature": 0.5,
            "top_p": 0.8,
            "top_k": 50,
            "max_tokens": 2048,
            "repetition_penalty": 1.2,
            "frequency_penalty": 0.5,
            "presence_penalty": 0.3,
            "stop": ["Human:"],
            "timeout": 60,
        }
        filtered = filter_params_for_provider(params, "anthropic")
        assert "temperature" in filtered
        assert "top_p" in filtered
        assert "top_k" in filtered
        assert "max_tokens" in filtered
        assert "stop" in filtered
        assert "timeout" in filtered
        assert "repetition_penalty" not in filtered
        assert "frequency_penalty" not in filtered
        assert "presence_penalty" not in filtered

    def test_filter_params_vllm(self):
        """vLLM supports temperature, top_p, top_k, max_tokens, repetition_penalty, frequency_penalty, presence_penalty, stop, timeout."""
        params = {
            "temperature": 0.5,
            "top_p": 0.8,
            "top_k": 50,
            "max_tokens": 2048,
            "repetition_penalty": 1.2,
            "frequency_penalty": 0.5,
            "presence_penalty": 0.3,
            "stop": ["\n"],
            "timeout": 60,
        }
        filtered = filter_params_for_provider(params, "vllm")
        assert len(filtered) == 9  # All params supported

    def test_filter_unknown_provider(self):
        """Unknown provider returns empty dict."""
        params = {"temperature": 0.5, "max_tokens": 2048}
        filtered = filter_params_for_provider(params, "unknown_provider_xyz")
        assert filtered == {}

class TestValidateParams:
    def test_validate_params_clamps_high(self):
        """temperature=5.0 clamped to 2.0."""
        result = validate_params({"temperature": 5.0})
        assert result["temperature"] == 2.0

    def test_validate_params_clamps_low(self):
        """temperature=-1.0 clamped to 0.0."""
        result = validate_params({"temperature": -1.0})
        assert result["temperature"] == 0.0

    def test_validate_params_ignores_unknown(self):
        """Unknown param names are dropped."""
        result = validate_params({"temperature": 0.5, "bogus_param": 42})
        assert "temperature" in result
        assert "bogus_param" not in result

class TestPresets:
    def test_presets_precise(self):
        expected = {
            "temperature": 0.1,
            "top_p": 0.5,
            "top_k": 40,
            "max_tokens": 4096,
            "repetition_penalty": 1.0,
            "frequency_penalty": 0.0,
            "presence_penalty": 0.0,
        }
        assert PRESETS["precise"] == expected

    def test_presets_balanced(self):
        expected = {
            "temperature": 0.7,
            "top_p": 0.9,
            "top_k": -1,
            "max_tokens": 4096,
            "repetition_penalty": 1.0,
            "frequency_penalty": 0.0,
            "presence_penalty": 0.0,
        }
        assert PRESETS["balanced"] == expected

    def test_presets_creative(self):
        expected = {
            "temperature": 1.0,
            "top_p": 0.95,
            "top_k": -1,
            "max_tokens": 4096,
            "repetition_penalty": 1.1,
            "frequency_penalty": 0.3,
            "presence_penalty": 0.3,
        }
        assert PRESETS["creative"] == expected

class TestParamSpecs:
    def test_param_specs_have_required_fields(self):
        """Every ParamSpec has name, type, min_val, max_val, default, step, label, description."""
        for name, spec in INFERENCE_PARAMS.items():
            assert spec.name == name, f"{name}: name mismatch"
            assert spec.type in ("float", "int", "string_list", "enum"), f"{name}: bad type"
            assert spec.default is not None, f"{name}: missing default"
            assert spec.label, f"{name}: missing label"
            assert spec.description, f"{name}: missing description"
            # step should be positive for numeric types
            if spec.type in ("float", "int"):
                assert spec.step > 0, f"{name}: step must be positive"

    def test_provider_param_support_all_providers(self):
        """All providers have at least temperature and max_tokens."""
        for provider, params in PROVIDER_PARAM_SUPPORT.items():
            assert "temperature" in params, f"{provider}: missing temperature"
            assert "max_tokens" in params, f"{provider}: missing max_tokens"

class TestParamCounts:
    def test_inference_params_count(self):
        assert len(INFERENCE_PARAMS) == 9

    def test_provider_count(self):
        assert len(PROVIDER_PARAM_SUPPORT) >= 12

    def test_preset_count(self):
        assert len(PRESETS) == 3

    def test_capability_support_count(self):
        assert len(CAPABILITY_PARAM_SUPPORT) == 4
        assert "llm" in CAPABILITY_PARAM_SUPPORT
        assert "vision" in CAPABILITY_PARAM_SUPPORT
        assert "audio" in CAPABILITY_PARAM_SUPPORT
        assert "embedding" in CAPABILITY_PARAM_SUPPORT

    def test_vllm_server_params_count(self):
        assert len(VLLM_SERVER_PARAMS) == 3
        assert "gpu_memory_utilization" in VLLM_SERVER_PARAMS
        assert "tensor_parallel_size" in VLLM_SERVER_PARAMS
        assert "dtype" in VLLM_SERVER_PARAMS

class TestAPISerializers:
    def test_get_param_specs_for_api(self):
        specs = get_param_specs_for_api()
        assert "temperature" in specs
        temp = specs["temperature"]
        assert temp["type"] == "float"
        assert temp["min"] == 0.0
        assert temp["max"] == 2.0
        assert temp["default"] == 0.7
        assert temp["step"] == 0.05

    def test_get_provider_params_for_api(self):
        result = get_provider_params_for_api()
        assert "openai" in result
        # Should be a list (serializable), not a set
        assert isinstance(result["openai"], list)
        assert "temperature" in result["openai"]
