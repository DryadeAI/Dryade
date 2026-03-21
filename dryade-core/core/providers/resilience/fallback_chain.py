"""FallbackChain — serializable provider fallback chain for LLM resilience.

Defines the ordered list of (provider, model) pairs that the FailoverEngine
iterates when the primary provider fails. Provides DB persistence helpers
to read/write the chain for a given user.
"""

import json
import logging
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

__all__ = [
    "FallbackChainEntry",
    "FallbackChain",
    "get_fallback_chain",
    "save_fallback_chain",
    "resolve_chain_configs",
]

@dataclass
class FallbackChainEntry:
    """A single provider+model pair in the fallback chain.

    Attributes:
        provider: Provider name (e.g., "openai", "anthropic", "vllm").
        model: Model name/ID (e.g., "gpt-4o", "claude-3-haiku").
    """

    provider: str
    model: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "FallbackChainEntry":
        return cls(provider=data["provider"], model=data["model"])

@dataclass
class FallbackChain:
    """Ordered list of provider+model fallback entries.

    Attributes:
        entries: Ordered list of FallbackChainEntry objects.
        enabled: Whether fallback is enabled for this chain.
    """

    entries: list[FallbackChainEntry]
    enabled: bool = True

    def to_json(self) -> str:
        """Serialize chain to JSON string for DB storage."""
        return json.dumps(
            {
                "entries": [e.to_dict() for e in self.entries],
                "enabled": self.enabled,
            }
        )

    @classmethod
    def from_json(cls, raw: str) -> "FallbackChain":
        """Deserialize chain from JSON string.

        Args:
            raw: JSON string previously produced by to_json().

        Returns:
            FallbackChain instance.
        """
        data = json.loads(raw)
        entries = [FallbackChainEntry.from_dict(e) for e in data.get("entries", [])]
        enabled = data.get("enabled", True)
        return cls(entries=entries, enabled=enabled)

def get_fallback_chain(user_id: str, db: "Session") -> "FallbackChain | None":
    """Load the user's fallback chain from the database.

    Args:
        user_id: The user's ID (from JWT sub claim).
        db: SQLAlchemy database session.

    Returns:
        FallbackChain if one is configured and enabled, else None.
    """
    from core.database.models import ModelConfig

    try:
        config = db.query(ModelConfig).filter(ModelConfig.user_id == user_id).first()

        if config is None:
            return None

        # Check both the enabled flag and the chain data
        if not getattr(config, "fallback_enabled", False):
            return None

        raw = getattr(config, "fallback_chain", None)
        if not raw:
            return None

        chain = FallbackChain.from_json(raw)
        if not chain.entries:
            return None

        return chain

    except Exception as e:
        logger.error("Failed to load fallback chain for user %s: %s", user_id, e)
        return None

def save_fallback_chain(user_id: str, chain: "FallbackChain", db: "Session") -> None:
    """Persist the user's fallback chain to the database.

    Creates ModelConfig row if it doesn't exist.

    Args:
        user_id: The user's ID (from JWT sub claim).
        chain: FallbackChain to persist.
        db: SQLAlchemy database session.
    """
    from core.database.models import ModelConfig

    try:
        config = db.query(ModelConfig).filter(ModelConfig.user_id == user_id).first()

        if config is None:
            config = ModelConfig(user_id=user_id)
            db.add(config)

        config.fallback_chain = chain.to_json()
        config.fallback_enabled = chain.enabled
        db.commit()

    except Exception as e:
        logger.error("Failed to save fallback chain for user %s: %s", user_id, e)
        db.rollback()
        raise

def resolve_chain_configs(
    chain: "FallbackChain",
    user_config_fn: Callable,
) -> list:
    """Resolve each chain entry to a full LLMConfig.

    Filters out entries for which the user has no configured API key,
    so the FailoverEngine only tries providers that are actually active.

    Args:
        chain: FallbackChain with ordered entries.
        user_config_fn: Callable(provider: str) -> UserLLMConfig-like object
            with .api_key and .endpoint attributes.

    Returns:
        List of LLMConfig objects (one per active entry, in chain order).
    """
    from core.providers.llm_adapter import LLMConfig

    resolved = []
    for entry in chain.entries:
        try:
            user_cfg = user_config_fn(entry.provider)
            api_key = getattr(user_cfg, "api_key", None)
            endpoint = getattr(user_cfg, "endpoint", None)

            # Filter out entries with no API key (provider not configured)
            # Local providers (vllm, ollama) don't need API keys
            local_providers = {"vllm", "ollama", "localai"}
            if not api_key and entry.provider not in local_providers:
                logger.debug(
                    "Skipping fallback entry %s:%s — no API key configured",
                    entry.provider,
                    entry.model,
                )
                continue

            from core.config import get_settings

            settings = get_settings()
            resolved.append(
                LLMConfig(
                    provider=entry.provider,
                    model=entry.model,
                    base_url=endpoint,
                    api_key=api_key,
                    temperature=settings.llm_temperature,
                    max_tokens=settings.llm_max_tokens,
                    timeout=settings.llm_timeout,
                    source="fallback_chain",
                )
            )
        except Exception as e:
            logger.warning(
                "Failed to resolve config for %s:%s: %s",
                entry.provider,
                entry.model,
                e,
            )
            continue

    return resolved
