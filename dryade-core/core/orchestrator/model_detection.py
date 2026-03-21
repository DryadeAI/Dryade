"""Model capability detection for adaptive routing.

Phase 115.4 + Phase 181: Provider-based tier resolution with litellm enrichment.

Two-path resolution:
1. Cloud providers -> deterministic tier from _CLOUD_PROVIDER_TIER static map,
   enriched by litellm.get_model_info() when available.
2. Local providers (vLLM/ollama) -> model-family sub-classification heuristic.

Backward-compatible: get_model_tier(llm) still works without provider_hint,
falling back to the original _build_key + _heuristic_classify path.

Classification is cached per (provider, model) key and thread-safe.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

__all__ = [
    "ModelTier",
    "ModelProfile",
    "ModelDetector",
    "get_model_detector",
]

class ModelTier(str, Enum):
    """LLM capability tier for routing strategy selection."""

    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"
    FRONTIER = "frontier"

# Static provider-to-tier map for cloud providers.
# These providers have predictable, well-documented capabilities.
# The user already specifies provider in Settings (UserLLMConfig.provider),
# so we use it directly instead of fragile substring matching.
_CLOUD_PROVIDER_TIER: dict[str, ModelTier] = {
    "openai": ModelTier.FRONTIER,
    "anthropic": ModelTier.FRONTIER,
    "google": ModelTier.FRONTIER,
    "mistral": ModelTier.STRONG,
    "cohere": ModelTier.STRONG,
    "bedrock": ModelTier.FRONTIER,
    "deepseek": ModelTier.STRONG,
    "xai": ModelTier.FRONTIER,
    "groq": ModelTier.STRONG,
    "together_ai": ModelTier.STRONG,
    "qwen": ModelTier.STRONG,
    "moonshot": ModelTier.STRONG,
}

# Local providers that use model-family sub-classification
_LOCAL_PROVIDERS = {"vllm", "ollama"}

# Model families with reliable tool_calls on /v1/chat/completions
_STRONG_FAMILIES = (
    "qwen",
    "ministral",
    "mistral",
    "llama",
    "deepseek",
    "internlm",
    "glm",
    "granite",
    "hermes",
)

# Model families with broken tool_calls (text-only reasoning)
_MODERATE_FAMILIES = ("gpt-oss",)

@dataclass
class ModelProfile:
    """Detected model capabilities and classification."""

    tier: ModelTier
    supports_tools: bool
    supports_structured_output: bool
    calibration_score: float  # 0.0-1.0
    model_key: str
    max_tokens: int | None = field(default=None)

class ModelDetector:
    """Provider-based model tier classifier with litellm enrichment.

    Resolution paths:
    1. Cloud provider (provider_hint in _CLOUD_PROVIDER_TIER) -> static tier
       + optional litellm.get_model_info() enrichment.
    2. Local provider (vllm/ollama) -> model-family sub-classification.
    3. No hint / unknown -> legacy _heuristic_classify() + _calibration_probe().
    """

    def __init__(self):
        self._cache: dict[str, ModelProfile] = {}
        self._lock = threading.Lock()

    def get_model_tier(self, llm, provider_hint: str | None = None) -> ModelProfile:
        """Classify an LLM and return its ModelProfile.

        Results are cached by (provider_hint, model_key) for subsequent calls.

        Args:
            llm: A litellm-compatible LLM object with a .model attribute.
            provider_hint: Provider string from UserLLMConfig (e.g. "openai",
                "anthropic", "vllm"). When provided, enables deterministic
                tier resolution. When None, falls back to legacy heuristic.

        Returns:
            ModelProfile with tier, capabilities, and calibration score.
        """
        model_key = self._build_key(llm)
        cache_key = f"{provider_hint}:{model_key}" if provider_hint else model_key

        if cache_key in self._cache:
            return self._cache[cache_key]

        with self._lock:
            # Double-check after acquiring lock
            if cache_key in self._cache:
                return self._cache[cache_key]

            profile = self._resolve_tier(llm, model_key, provider_hint)
            self._cache[cache_key] = profile
            return profile

    def _build_key(self, llm) -> str:
        """Extract model identifier string from LLM object.

        CrewAI native provider classes (e.g. AnthropicCompletion) strip
        the provider prefix from llm.model. We reconstruct the canonical
        ``provider/model`` key using llm.provider when available so that
        heuristic patterns like ``anthropic/claude`` continue to match.
        """
        model = getattr(llm, "model", "") or ""
        provider = getattr(llm, "provider", None) or ""
        if provider and not model.startswith(f"{provider}/"):
            return f"{provider}/{model}"
        return model

    def _resolve_tier(self, llm, model_key: str, provider_hint: str | None) -> ModelProfile:
        """Resolve model tier via provider-based paths.

        Args:
            llm: The LLM object.
            model_key: Extracted model identifier string.
            provider_hint: Provider string or None.

        Returns:
            ModelProfile for the resolved tier.
        """
        # Path 1: Cloud provider -- deterministic tier from static map
        if provider_hint and provider_hint in _CLOUD_PROVIDER_TIER:
            return self._resolve_cloud(model_key, provider_hint)

        # Path 2: Local provider -- model-family sub-classification
        if provider_hint and provider_hint in _LOCAL_PROVIDERS:
            return self._resolve_local(llm, model_key, provider_hint)

        # Path 3: Unknown provider with hint -- default MODERATE (fail-safe)
        if provider_hint:
            logger.info(
                "[MODEL_DETECTION] Unknown provider '%s' for model '%s' -- "
                "defaulting to MODERATE tier.",
                provider_hint,
                model_key,
            )
            return ModelProfile(
                tier=ModelTier.MODERATE,
                supports_tools=True,
                supports_structured_output=False,
                calibration_score=self._tier_to_score(ModelTier.MODERATE),
                model_key=model_key,
                max_tokens=None,
            )

        # Path 4: No provider hint -- legacy heuristic for backward compat
        return self._detect_legacy(llm, model_key)

    def _resolve_cloud(self, model_key: str, provider_hint: str) -> ModelProfile:
        """Resolve tier for a cloud provider with optional litellm enrichment.

        Args:
            model_key: Model identifier string.
            provider_hint: Cloud provider name (must be in _CLOUD_PROVIDER_TIER).

        Returns:
            ModelProfile with tier from static map, enriched by litellm when available.
        """
        tier = _CLOUD_PROVIDER_TIER[provider_hint]

        # Default capabilities for cloud providers
        supports_tools = tier in (ModelTier.FRONTIER, ModelTier.STRONG)
        supports_structured = tier == ModelTier.FRONTIER
        max_tokens: int | None = None

        # Try litellm enrichment (lazy import -- litellm is heavy)
        try:
            import litellm

            info = litellm.get_model_info(model_key)
            fc = info.get("supports_function_calling")
            if fc is not None:
                supports_tools = bool(fc)
            # else: keep cloud default (True for FRONTIER/STRONG)
            mt = info.get("max_output_tokens")
            if mt is not None:
                max_tokens = int(mt)
        except Exception:
            # litellm doesn't know this model -- use static defaults
            pass

        return ModelProfile(
            tier=tier,
            supports_tools=supports_tools,
            supports_structured_output=supports_structured,
            calibration_score=self._tier_to_score(tier),
            model_key=model_key,
            max_tokens=max_tokens,
        )

    def _resolve_local(self, llm, model_key: str, provider_hint: str) -> ModelProfile:
        """Resolve tier for local providers (vLLM, ollama).

        Uses model-family sub-classification for vLLM. Ollama defaults to WEAK.

        Args:
            llm: The LLM object.
            model_key: Model identifier string.
            provider_hint: "vllm" or "ollama".

        Returns:
            ModelProfile with tier based on model family.
        """
        if provider_hint == "ollama":
            tier = ModelTier.WEAK
        else:
            # vLLM: classify by model family
            name = model_key.lower()
            # Strip provider prefix if present
            for prefix in ("vllm/", "ollama/", "ollama_chat/"):
                if name.startswith(prefix):
                    name = name[len(prefix) :]
                    break

            if any(f in name for f in _MODERATE_FAMILIES):
                tier = ModelTier.MODERATE
            elif any(f in name for f in _STRONG_FAMILIES):
                tier = ModelTier.STRONG
            else:
                tier = ModelTier.MODERATE

        supports_tools = tier in (ModelTier.FRONTIER, ModelTier.STRONG)
        supports_structured = tier == ModelTier.FRONTIER

        return ModelProfile(
            tier=tier,
            supports_tools=supports_tools,
            supports_structured_output=supports_structured,
            calibration_score=self._tier_to_score(tier),
            model_key=model_key,
            max_tokens=None,
        )

    def _detect_legacy(self, llm, model_key: str) -> ModelProfile:
        """Legacy detection via heuristic + calibration probe (no provider_hint).

        Preserves backward compatibility for call sites not yet updated.

        Args:
            llm: The LLM object.
            model_key: Extracted model identifier string.

        Returns:
            ModelProfile for the detected tier.
        """
        tier = self._heuristic_classify(model_key, llm)
        if tier is not None:
            supports_tools = tier in (ModelTier.FRONTIER, ModelTier.STRONG)
            supports_structured = tier == ModelTier.FRONTIER
            return ModelProfile(
                tier=tier,
                supports_tools=supports_tools,
                supports_structured_output=supports_structured,
                calibration_score=self._tier_to_score(tier),
                model_key=model_key,
                max_tokens=None,
            )
        return self._calibration_probe(llm, model_key)

    def _heuristic_classify(self, model_key: str, llm=None) -> ModelTier | None:
        """Pattern-match model key against known provider signatures.

        Legacy fallback for when no provider_hint is given. Kept intact
        for backward compatibility.

        Args:
            model_key: Model identifier string (e.g. "openai/gpt-4o").
            llm: Optional LLM object for capability checks.

        Returns:
            ModelTier if a pattern matches, None otherwise.
        """
        key_lower = model_key.lower()

        # Ollama models -> WEAK (local small models)
        if "ollama/" in key_lower or "ollama_chat/" in key_lower:
            return ModelTier.WEAK

        # Frontier models from major providers
        if any(
            prefix in key_lower
            for prefix in (
                "openai/gpt-4",
                "anthropic/claude",
                "gemini/gemini-1.5-pro",
                "gemini/gemini-2",
            )
        ):
            return ModelTier.FRONTIER

        # OpenAI GPT-3.5 -> STRONG (decent tool calling)
        if "openai/gpt-3.5" in key_lower:
            return ModelTier.STRONG

        # DeepSeek models -> STRONG (good tool calling)
        if "deepseek/" in key_lower:
            return ModelTier.STRONG

        # vLLM-served models: classify by model family from the served name.
        is_vllm = "vllm/" in key_lower or (llm is not None and "vllm" in type(llm).__name__.lower())
        if is_vllm:
            # Strip "vllm/" prefix for pattern matching
            name = key_lower.removeprefix("vllm/")
            if any(f in name for f in _MODERATE_FAMILIES):
                return ModelTier.MODERATE
            if any(f in name for f in _STRONG_FAMILIES):
                return ModelTier.STRONG
            return ModelTier.MODERATE

        return None

    def _calibration_probe(self, llm, model_key: str) -> ModelProfile:
        """Fallback for unknown models -- returns MODERATE as default.

        Actual LLM-based calibration probe is deferred per research
        recommendation ("Start with heuristic-only classification").

        Args:
            llm: The LLM object (unused in 115.4).
            model_key: Model identifier string.

        Returns:
            ModelProfile with MODERATE tier.
        """
        logger.warning(
            "[MODEL_DETECTION] Unknown model '%s' -- defaulting to MODERATE tier. "
            "Calibration probe not yet implemented.",
            model_key,
        )
        return ModelProfile(
            tier=ModelTier.MODERATE,
            supports_tools=True,
            supports_structured_output=False,
            calibration_score=self._tier_to_score(ModelTier.MODERATE),
            model_key=model_key,
            max_tokens=None,
        )

    def _tier_to_score(self, tier: ModelTier) -> float:
        """Convert tier to a numeric calibration score.

        Args:
            tier: The model tier.

        Returns:
            Float score from 0.0 to 1.0.
        """
        return {
            ModelTier.WEAK: 0.2,
            ModelTier.MODERATE: 0.5,
            ModelTier.STRONG: 0.75,
            ModelTier.FRONTIER: 1.0,
        }[tier]

    @staticmethod
    def downgrade_tier(tier: ModelTier) -> ModelTier:
        """Return one tier lower. WEAK stays WEAK (floor).

        Used by runtime adaptive fallback: when tool calling fails,
        the session tier is downgraded so the next ReAct iteration
        uses a lower-capability strategy (e.g. text-based JSON parsing).

        Args:
            tier: Current model tier.

        Returns:
            The next lower ModelTier, or WEAK if already at floor.
        """
        _DOWNGRADE: dict[ModelTier, ModelTier] = {
            ModelTier.FRONTIER: ModelTier.STRONG,
            ModelTier.STRONG: ModelTier.MODERATE,
            ModelTier.MODERATE: ModelTier.WEAK,
            ModelTier.WEAK: ModelTier.WEAK,
        }
        return _DOWNGRADE[tier]

    def clear_cache(self) -> None:
        """Clear the model profile cache."""
        with self._lock:
            self._cache.clear()

# Singleton pattern with double-checked locking
_model_detector: ModelDetector | None = None
_model_detector_lock = threading.Lock()

def get_model_detector() -> ModelDetector:
    """Get or create singleton ModelDetector instance."""
    global _model_detector
    if _model_detector is None:
        with _model_detector_lock:
            if _model_detector is None:
                _model_detector = ModelDetector()
    return _model_detector
