"""Inference parameter definitions, defaults, provider compatibility, and validation.

Single source of truth for:
- Parameter specifications (ranges, types, defaults)
- Provider-to-supported-params compatibility map
- Capability-specific parameter support
- Presets (precise, balanced, creative)
- vLLM server-level parameters
"""

from dataclasses import dataclass

@dataclass
class ParamSpec:
    """Specification for a single inference parameter."""

    name: str
    type: str  # "float", "int", "string_list", "enum"
    min_val: float | int | None
    max_val: float | int | None
    default: float | int | list | str
    step: float | int
    label: str
    description: str

# ---------------------------------------------------------------------------
# Inference parameters (per-request, sent to LLM provider)
# ---------------------------------------------------------------------------

INFERENCE_PARAMS: dict[str, ParamSpec] = {
    "temperature": ParamSpec(
        "temperature",
        "float",
        0.0,
        2.0,
        0.7,
        0.05,
        "Temperature",
        "Controls randomness",
    ),
    "top_p": ParamSpec(
        "top_p",
        "float",
        0.0,
        1.0,
        0.9,
        0.05,
        "Top P",
        "Nucleus sampling threshold",
    ),
    "top_k": ParamSpec(
        "top_k",
        "int",
        -1,
        200,
        -1,
        1,
        "Top K",
        "Limits token candidates (-1=disabled)",
    ),
    "max_tokens": ParamSpec(
        "max_tokens",
        "int",
        1,
        131072,
        4096,
        1,
        "Max Tokens",
        "Maximum output length",
    ),
    "repetition_penalty": ParamSpec(
        "repetition_penalty",
        "float",
        0.0,
        2.0,
        1.0,
        0.05,
        "Repetition Penalty",
        "Penalizes repeated tokens",
    ),
    "frequency_penalty": ParamSpec(
        "frequency_penalty",
        "float",
        -2.0,
        2.0,
        0.0,
        0.1,
        "Frequency Penalty",
        "Penalizes frequent tokens",
    ),
    "presence_penalty": ParamSpec(
        "presence_penalty",
        "float",
        -2.0,
        2.0,
        0.0,
        0.1,
        "Presence Penalty",
        "Encourages new topics",
    ),
    "timeout": ParamSpec(
        "timeout",
        "int",
        5,
        600,
        120,
        5,
        "Timeout",
        "Request timeout (seconds)",
    ),
    "planner_timeout": ParamSpec(
        "planner_timeout",
        "int",
        30,
        900,
        300,
        15,
        "Planner Timeout",
        "Plan generation timeout (seconds)",
    ),
}

# ---------------------------------------------------------------------------
# vLLM server-level parameters (require restart, not per-request)
# ---------------------------------------------------------------------------

VLLM_SERVER_PARAMS: dict[str, ParamSpec] = {
    "gpu_memory_utilization": ParamSpec(
        "gpu_memory_utilization",
        "float",
        0.1,
        0.99,
        0.9,
        0.05,
        "GPU Memory Utilization",
        "Fraction of GPU memory to use",
    ),
    "tensor_parallel_size": ParamSpec(
        "tensor_parallel_size",
        "int",
        1,
        8,
        1,
        1,
        "Tensor Parallel Size",
        "Number of GPUs for tensor parallelism",
    ),
    "dtype": ParamSpec(
        "dtype",
        "enum",
        None,
        None,
        "auto",
        0,
        "Data Type",
        "Model precision (auto, float16, bfloat16, float32)",
    ),
}

# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------

PRESETS: dict[str, dict[str, float | int]] = {
    "precise": {
        "temperature": 0.1,
        "top_p": 0.5,
        "top_k": 40,
        "max_tokens": 4096,
        "repetition_penalty": 1.0,
        "frequency_penalty": 0.0,
        "presence_penalty": 0.0,
    },
    "balanced": {
        "temperature": 0.7,
        "top_p": 0.9,
        "top_k": -1,
        "max_tokens": 4096,
        "repetition_penalty": 1.0,
        "frequency_penalty": 0.0,
        "presence_penalty": 0.0,
    },
    "creative": {
        "temperature": 1.0,
        "top_p": 0.95,
        "top_k": -1,
        "max_tokens": 4096,
        "repetition_penalty": 1.1,
        "frequency_penalty": 0.3,
        "presence_penalty": 0.3,
    },
}

# ---------------------------------------------------------------------------
# Provider -> supported parameter names
# ---------------------------------------------------------------------------

PROVIDER_PARAM_SUPPORT: dict[str, set[str]] = {
    "openai": {
        "temperature",
        "top_p",
        "max_tokens",
        "frequency_penalty",
        "presence_penalty",
        "stop",
        "timeout",
    },
    "anthropic": {"temperature", "top_p", "top_k", "max_tokens", "stop", "timeout"},
    "vllm": {
        "temperature",
        "top_p",
        "top_k",
        "max_tokens",
        "repetition_penalty",
        "frequency_penalty",
        "presence_penalty",
        "stop",
        "timeout",
    },
    "ollama": {
        "temperature",
        "top_p",
        "top_k",
        "max_tokens",
        "repetition_penalty",
        "stop",
        "timeout",
    },
    "google": {"temperature", "top_p", "top_k", "max_tokens", "stop", "timeout"},
    "mistral": {"temperature", "top_p", "max_tokens", "stop", "timeout"},
    "deepseek": {
        "temperature",
        "top_p",
        "max_tokens",
        "frequency_penalty",
        "presence_penalty",
        "stop",
        "timeout",
    },
    "cohere": {
        "temperature",
        "top_p",
        "top_k",
        "max_tokens",
        "frequency_penalty",
        "presence_penalty",
        "stop",
        "timeout",
    },
    "groq": {"temperature", "top_p", "max_tokens", "stop", "timeout"},
    "together_ai": {
        "temperature",
        "top_p",
        "top_k",
        "max_tokens",
        "repetition_penalty",
        "stop",
        "timeout",
    },
    "xai": {
        "temperature",
        "top_p",
        "max_tokens",
        "frequency_penalty",
        "presence_penalty",
        "stop",
        "timeout",
    },
    "litellm_proxy": {
        "temperature",
        "top_p",
        "top_k",
        "max_tokens",
        "frequency_penalty",
        "presence_penalty",
        "repetition_penalty",
        "stop",
        "timeout",
    },
    "huggingface": {
        "temperature",
        "top_p",
        "top_k",
        "max_tokens",
        "repetition_penalty",
        "stop",
        "timeout",
    },
}

# ---------------------------------------------------------------------------
# Capability -> applicable inference params
# ---------------------------------------------------------------------------

CAPABILITY_PARAM_SUPPORT: dict[str, list[str]] = {
    "llm": list(INFERENCE_PARAMS.keys()),
    "vision": list(INFERENCE_PARAMS.keys()),
    "audio": ["timeout", "max_tokens"],
    "embedding": [],
}

# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def get_defaults() -> dict[str, float | int | list | str]:
    """Return hardcoded defaults for all inference params."""
    return {name: spec.default for name, spec in INFERENCE_PARAMS.items()}

def filter_params_for_provider(params: dict, provider: str) -> dict:
    """Filter inference params to only those supported by the given provider.

    Unknown provider returns empty dict (fail-closed).
    """
    supported = PROVIDER_PARAM_SUPPORT.get(provider, set())
    return {k: v for k, v in params.items() if k in supported}

def validate_params(params: dict) -> dict:
    """Validate and clamp param values to allowed ranges.

    Unknown param names are silently dropped.
    """
    validated = {}
    for name, value in params.items():
        spec = INFERENCE_PARAMS.get(name)
        if not spec:
            continue
        if spec.min_val is not None and value < spec.min_val:
            value = spec.min_val
        if spec.max_val is not None and value > spec.max_val:
            value = spec.max_val
        validated[name] = value
    return validated

def get_param_specs_for_api() -> dict:
    """Return serializable version of INFERENCE_PARAMS for API responses."""
    return {
        name: {
            "type": spec.type,
            "min": spec.min_val,
            "max": spec.max_val,
            "default": spec.default,
            "step": spec.step,
            "label": spec.label,
            "description": spec.description,
        }
        for name, spec in INFERENCE_PARAMS.items()
    }

def get_provider_params_for_api() -> dict[str, list[str]]:
    """Return serializable PROVIDER_PARAM_SUPPORT (sets converted to sorted lists)."""
    return {provider: sorted(params) for provider, params in PROVIDER_PARAM_SUPPORT.items()}
