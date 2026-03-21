"""Unit tests for FallbackChain serialization, filtering, and ordering.

Covers: to_json/from_json roundtrip, empty chain handling, resolve_chain_configs
filtering (unconfigured providers removed), and ordering preservation.
"""

from core.providers.llm_adapter import LLMConfig
from core.providers.resilience.fallback_chain import (
    FallbackChain,
    FallbackChainEntry,
    resolve_chain_configs,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_entry(provider: str, model: str) -> FallbackChainEntry:
    return FallbackChainEntry(provider=provider, model=model)

def _make_llm_config(provider: str, model: str, api_key: str | None = "test-key") -> LLMConfig:
    return LLMConfig(
        provider=provider,
        model=model,
        base_url=None,
        api_key=api_key,
        temperature=0.7,
        max_tokens=1024,
        timeout=30,
        source="test",
    )

# ---------------------------------------------------------------------------
# FallbackChainEntry tests
# ---------------------------------------------------------------------------

class TestFallbackChainEntry:
    def test_to_dict_roundtrip(self) -> None:
        entry = FallbackChainEntry(provider="openai", model="gpt-4o")
        d = entry.to_dict()
        restored = FallbackChainEntry.from_dict(d)
        assert restored.provider == entry.provider
        assert restored.model == entry.model

    def test_from_dict_preserves_values(self) -> None:
        data = {"provider": "anthropic", "model": "claude-3-haiku"}
        entry = FallbackChainEntry.from_dict(data)
        assert entry.provider == "anthropic"
        assert entry.model == "claude-3-haiku"

# ---------------------------------------------------------------------------
# FallbackChain serialization tests
# ---------------------------------------------------------------------------

class TestFallbackChainSerialization:
    def test_to_json_from_json_roundtrip(self) -> None:
        chain = FallbackChain(
            entries=[
                _make_entry("openai", "gpt-4o"),
                _make_entry("anthropic", "claude-3-haiku"),
            ],
            enabled=True,
        )
        raw = chain.to_json()
        restored = FallbackChain.from_json(raw)

        assert len(restored.entries) == 2
        assert restored.entries[0].provider == "openai"
        assert restored.entries[0].model == "gpt-4o"
        assert restored.entries[1].provider == "anthropic"
        assert restored.entries[1].model == "claude-3-haiku"
        assert restored.enabled is True

    def test_roundtrip_preserves_enabled_false(self) -> None:
        chain = FallbackChain(entries=[_make_entry("openai", "gpt-4o")], enabled=False)
        restored = FallbackChain.from_json(chain.to_json())
        assert restored.enabled is False

    def test_from_json_empty_entries(self) -> None:
        raw = '{"entries": [], "enabled": true}'
        chain = FallbackChain.from_json(raw)
        assert chain.entries == []
        assert chain.enabled is True

    def test_from_json_missing_enabled_defaults_true(self) -> None:
        """Backward compat: old serialized chains without 'enabled' field."""
        raw = '{"entries": [{"provider": "openai", "model": "gpt-4o"}]}'
        chain = FallbackChain.from_json(raw)
        assert chain.enabled is True

    def test_to_json_is_valid_json_string(self) -> None:
        import json

        chain = FallbackChain(entries=[_make_entry("openai", "gpt-4o")], enabled=True)
        raw = chain.to_json()
        # Should not raise
        parsed = json.loads(raw)
        assert "entries" in parsed
        assert "enabled" in parsed

# ---------------------------------------------------------------------------
# resolve_chain_configs tests
# ---------------------------------------------------------------------------

class TestResolveChainConfigs:
    def test_filters_unconfigured_providers(self) -> None:
        """Providers for which user_config_fn returns no API key are filtered out."""
        chain = FallbackChain(
            entries=[
                _make_entry("openai", "gpt-4o"),
                _make_entry("anthropic", "claude-3-haiku"),  # no key
                _make_entry("vllm", "local-model"),  # local — no key required
            ],
            enabled=True,
        )

        def config_fn(provider: str) -> object:
            class MockConfig:
                api_key: str | None = None
                endpoint: str | None = None

            cfg = MockConfig()
            if provider == "openai":
                cfg.api_key = "sk-test-openai"
            elif provider == "vllm":
                cfg.api_key = None  # local provider — allowed without key
            # anthropic: api_key=None, not a local provider -> filtered
            return cfg

        resolved = resolve_chain_configs(chain, config_fn)

        # anthropic should be filtered out (no API key, not a local provider)
        providers_in_result = [c.provider for c in resolved]
        assert "openai" in providers_in_result
        assert "vllm" in providers_in_result
        assert "anthropic" not in providers_in_result

    def test_preserves_chain_order(self) -> None:
        """Resolved configs are in the same order as chain entries."""
        chain = FallbackChain(
            entries=[
                _make_entry("anthropic", "claude-3-haiku"),
                _make_entry("openai", "gpt-4o"),
                _make_entry("vllm", "local-model"),
            ],
            enabled=True,
        )

        def config_fn(provider: str) -> object:
            class MockConfig:
                api_key: str | None = "some-key"
                endpoint: str | None = None

            return MockConfig()

        resolved = resolve_chain_configs(chain, config_fn)

        assert len(resolved) == 3
        assert resolved[0].provider == "anthropic"
        assert resolved[1].provider == "openai"
        assert resolved[2].provider == "vllm"

    def test_all_unconfigured_returns_empty(self) -> None:
        chain = FallbackChain(
            entries=[
                _make_entry("openai", "gpt-4o"),
                _make_entry("anthropic", "claude-3-haiku"),
            ],
            enabled=True,
        )

        def config_fn(provider: str) -> object:
            class MockConfig:
                api_key: str | None = None
                endpoint: str | None = None

            return MockConfig()

        resolved = resolve_chain_configs(chain, config_fn)
        assert resolved == []

    def test_empty_chain_returns_empty(self) -> None:
        chain = FallbackChain(entries=[], enabled=True)

        def config_fn(provider: str) -> object:
            class MockConfig:
                api_key: str | None = "key"
                endpoint: str | None = None

            return MockConfig()

        resolved = resolve_chain_configs(chain, config_fn)
        assert resolved == []

    def test_resolved_config_has_correct_attributes(self) -> None:
        """Resolved LLMConfig objects should have provider/model from chain entries."""
        chain = FallbackChain(
            entries=[_make_entry("openai", "gpt-4o-mini")],
            enabled=True,
        )

        def config_fn(provider: str) -> object:
            class MockConfig:
                api_key: str | None = "sk-test"
                endpoint: str | None = None

            return MockConfig()

        resolved = resolve_chain_configs(chain, config_fn)
        assert len(resolved) == 1
        assert resolved[0].provider == "openai"
        assert resolved[0].model == "gpt-4o-mini"
        assert resolved[0].api_key == "sk-test"
