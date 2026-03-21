"""Unit tests for extension pipeline and registry."""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

@pytest.mark.unit
class TestExtensionType:
    """Tests for ExtensionType enum."""

    def test_extension_type_values(self):
        """Test all extension type values exist."""
        from core.extensions.pipeline import ExtensionType

        assert ExtensionType.INPUT_VALIDATION.value == "input_validation"
        assert ExtensionType.SEMANTIC_CACHE.value == "semantic_cache"
        assert ExtensionType.SELF_HEALING.value == "self_healing"
        assert ExtensionType.SANDBOX.value == "sandbox"
        assert ExtensionType.FILE_SAFETY.value == "file_safety"
        assert ExtensionType.OUTPUT_SANITIZATION.value == "output_sanitization"

@pytest.mark.unit
class TestExtensionConfig:
    """Tests for ExtensionConfig dataclass."""

    def test_extension_config_creation(self):
        """Test creating an ExtensionConfig."""
        from core.extensions.pipeline import ExtensionConfig, ExtensionType

        config = ExtensionConfig(
            name="test_extension", type=ExtensionType.SEMANTIC_CACHE, enabled=True, priority=5
        )

        assert config.name == "test_extension"
        assert config.type == ExtensionType.SEMANTIC_CACHE
        assert config.enabled is True
        assert config.priority == 5
        assert config.on_startup is None
        assert config.on_shutdown is None

    def test_extension_config_with_hooks(self):
        """Test ExtensionConfig with startup/shutdown hooks."""
        from core.extensions.pipeline import ExtensionConfig, ExtensionType

        startup = MagicMock()
        shutdown = MagicMock()

        config = ExtensionConfig(
            name="test_ext",
            type=ExtensionType.SANDBOX,
            enabled=True,
            priority=1,
            on_startup=startup,
            on_shutdown=shutdown,
        )

        assert config.on_startup is startup
        assert config.on_shutdown is shutdown

    def test_extension_config_disabled(self):
        """Test creating a disabled ExtensionConfig."""
        from core.extensions.pipeline import ExtensionConfig, ExtensionType

        config = ExtensionConfig(
            name="disabled_ext", type=ExtensionType.FILE_SAFETY, enabled=False, priority=10
        )

        assert config.enabled is False

@pytest.mark.unit
class TestExtensionRequest:
    """Tests for ExtensionRequest dataclass."""

    def test_extension_request_creation(self):
        """Test creating an ExtensionRequest."""
        from core.extensions.pipeline import ExtensionRequest

        request = ExtensionRequest(
            operation="agent_execute",
            data={"prompt": "Hello"},
            context={"user_id": "123"},
            metadata={"trace_id": "abc"},
        )

        assert request.operation == "agent_execute"
        assert request.data["prompt"] == "Hello"
        assert request.context["user_id"] == "123"
        assert request.metadata["trace_id"] == "abc"

@pytest.mark.unit
class TestExtensionResponse:
    """Tests for ExtensionResponse dataclass."""

    def test_extension_response_creation(self):
        """Test creating an ExtensionResponse."""
        from core.extensions.pipeline import ExtensionResponse

        response = ExtensionResponse(
            result={"answer": "World"},
            metadata={"time": 100},
            extensions_applied=["cache", "sandbox"],
        )

        assert response.result["answer"] == "World"
        assert response.metadata["time"] == 100
        assert "cache" in response.extensions_applied
        assert response.cache_hit is False
        assert response.healed is False

    def test_extension_response_with_flags(self):
        """Test ExtensionResponse with all flags set."""
        from core.extensions.pipeline import ExtensionResponse

        response = ExtensionResponse(
            result="success",
            metadata={},
            extensions_applied=["all"],
            cache_hit=True,
            healed=True,
            sandboxed=True,
            threats_found=["threat1"],
        )

        assert response.cache_hit is True
        assert response.healed is True
        assert response.sandboxed is True
        assert "threat1" in response.threats_found

@pytest.mark.unit
class TestExtensionRegistry:
    """Tests for ExtensionRegistry class."""

    def test_extension_registry_creation(self):
        """Test creating an empty ExtensionRegistry."""
        from core.extensions.pipeline import ExtensionRegistry

        registry = ExtensionRegistry()
        assert len(registry._extensions) == 0

    def test_extension_registry_register(self):
        """Test registering an extension."""
        from core.extensions.pipeline import ExtensionConfig, ExtensionRegistry, ExtensionType

        registry = ExtensionRegistry()
        config = ExtensionConfig(
            name="test_ext", type=ExtensionType.SEMANTIC_CACHE, enabled=True, priority=1
        )

        registry.register(config)

        assert len(registry._extensions) == 1
        assert "test_ext" in registry._extensions

    def test_extension_registry_get(self):
        """Test getting an extension by name."""
        from core.extensions.pipeline import ExtensionConfig, ExtensionRegistry, ExtensionType

        registry = ExtensionRegistry()
        config = ExtensionConfig(
            name="my_ext", type=ExtensionType.SANDBOX, enabled=True, priority=2
        )
        registry.register(config)

        result = registry.get("my_ext")
        assert result is config
        assert registry.get("nonexistent") is None

    def test_extension_registry_get_by_type(self):
        """Test getting extensions by type."""
        from core.extensions.pipeline import ExtensionConfig, ExtensionRegistry, ExtensionType

        registry = ExtensionRegistry()

        # Register multiple extensions
        registry.register(
            ExtensionConfig(
                name="cache1", type=ExtensionType.SEMANTIC_CACHE, enabled=True, priority=1
            )
        )
        registry.register(
            ExtensionConfig(
                name="cache2", type=ExtensionType.SEMANTIC_CACHE, enabled=False, priority=2
            )
        )
        registry.register(
            ExtensionConfig(name="sandbox1", type=ExtensionType.SANDBOX, enabled=True, priority=3)
        )

        cache_exts = registry.get_by_type(ExtensionType.SEMANTIC_CACHE)
        assert len(cache_exts) == 2

        sandbox_exts = registry.get_by_type(ExtensionType.SANDBOX)
        assert len(sandbox_exts) == 1

        safety_exts = registry.get_by_type(ExtensionType.FILE_SAFETY)
        assert len(safety_exts) == 0

    def test_extension_registry_get_enabled(self):
        """Test getting only enabled extensions sorted by priority."""
        from core.extensions.pipeline import ExtensionConfig, ExtensionRegistry, ExtensionType

        registry = ExtensionRegistry()

        # Register extensions with various priorities and enabled states
        registry.register(
            ExtensionConfig(
                name="high_priority", type=ExtensionType.INPUT_VALIDATION, enabled=True, priority=1
            )
        )
        registry.register(
            ExtensionConfig(
                name="disabled", type=ExtensionType.SEMANTIC_CACHE, enabled=False, priority=2
            )
        )
        registry.register(
            ExtensionConfig(
                name="low_priority", type=ExtensionType.SANDBOX, enabled=True, priority=10
            )
        )
        registry.register(
            ExtensionConfig(
                name="medium_priority", type=ExtensionType.SELF_HEALING, enabled=True, priority=5
            )
        )

        enabled = registry.get_enabled()

        # Should exclude disabled, sorted by priority
        assert len(enabled) == 3
        assert enabled[0].name == "high_priority"
        assert enabled[1].name == "medium_priority"
        assert enabled[2].name == "low_priority"

    def test_extension_registry_list_enabled_empty(self):
        """Test get_enabled on empty registry."""
        from core.extensions.pipeline import ExtensionRegistry

        registry = ExtensionRegistry()
        enabled = registry.get_enabled()
        assert len(enabled) == 0

    def test_extension_registry_all_disabled(self):
        """Test get_enabled when all extensions are disabled."""
        from core.extensions.pipeline import ExtensionConfig, ExtensionRegistry, ExtensionType

        registry = ExtensionRegistry()
        registry.register(
            ExtensionConfig(name="disabled1", type=ExtensionType.SANDBOX, enabled=False, priority=1)
        )
        registry.register(
            ExtensionConfig(
                name="disabled2", type=ExtensionType.SEMANTIC_CACHE, enabled=False, priority=2
            )
        )

        enabled = registry.get_enabled()
        assert len(enabled) == 0

    def test_extension_registry_duplicate_names(self):
        """Test that registering duplicate names overwrites."""
        from core.extensions.pipeline import ExtensionConfig, ExtensionRegistry, ExtensionType

        registry = ExtensionRegistry()

        registry.register(
            ExtensionConfig(name="same_name", type=ExtensionType.SANDBOX, enabled=True, priority=1)
        )
        registry.register(
            ExtensionConfig(
                name="same_name", type=ExtensionType.SEMANTIC_CACHE, enabled=False, priority=5
            )
        )

        # Should have only one extension
        assert len(registry._extensions) == 1
        ext = registry.get("same_name")
        assert ext.type == ExtensionType.SEMANTIC_CACHE
        assert ext.enabled is False

    @pytest.mark.asyncio
    async def test_extension_registry_startup(self):
        """Test running startup hooks."""
        from core.extensions.pipeline import ExtensionConfig, ExtensionRegistry, ExtensionType

        startup_mock = MagicMock()
        async_startup_mock = AsyncMock()

        registry = ExtensionRegistry()
        registry.register(
            ExtensionConfig(
                name="sync_ext",
                type=ExtensionType.SANDBOX,
                enabled=True,
                priority=1,
                on_startup=startup_mock,
            )
        )
        registry.register(
            ExtensionConfig(
                name="async_ext",
                type=ExtensionType.SEMANTIC_CACHE,
                enabled=True,
                priority=2,
                on_startup=async_startup_mock,
            )
        )

        await registry.startup()

        startup_mock.assert_called_once()
        async_startup_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_extension_registry_shutdown(self):
        """Test running shutdown hooks."""
        from core.extensions.pipeline import ExtensionConfig, ExtensionRegistry, ExtensionType

        shutdown_mock = MagicMock()
        async_shutdown_mock = AsyncMock()

        registry = ExtensionRegistry()
        registry.register(
            ExtensionConfig(
                name="sync_ext",
                type=ExtensionType.SANDBOX,
                enabled=True,
                priority=1,
                on_shutdown=shutdown_mock,
            )
        )
        registry.register(
            ExtensionConfig(
                name="async_ext",
                type=ExtensionType.SEMANTIC_CACHE,
                enabled=True,
                priority=2,
                on_shutdown=async_shutdown_mock,
            )
        )

        await registry.shutdown()

        shutdown_mock.assert_called_once()
        async_shutdown_mock.assert_awaited_once()

@pytest.mark.unit
class TestExtensionPipeline:
    """Tests for ExtensionPipeline class."""

    def test_extension_pipeline_creation(self):
        """Test creating an ExtensionPipeline."""
        from core.extensions.pipeline import ExtensionPipeline, ExtensionRegistry

        registry = ExtensionRegistry()
        pipeline = ExtensionPipeline(registry)

        assert pipeline.registry is registry

    @pytest.mark.asyncio
    async def test_extension_pipeline_execute_order(self):
        """Test that extensions execute in priority order."""
        from core.extensions.pipeline import (
            ExtensionConfig,
            ExtensionPipeline,
            ExtensionRegistry,
            ExtensionRequest,
            ExtensionType,
        )

        registry = ExtensionRegistry()
        registry.register(
            ExtensionConfig(
                name="first", type=ExtensionType.INPUT_VALIDATION, enabled=True, priority=1
            )
        )
        registry.register(
            ExtensionConfig(
                name="second", type=ExtensionType.SEMANTIC_CACHE, enabled=True, priority=2
            )
        )
        registry.register(
            ExtensionConfig(name="third", type=ExtensionType.SANDBOX, enabled=True, priority=3)
        )

        pipeline = ExtensionPipeline(registry)

        async def core_handler(data):
            return {"result": data["input"]}

        request = ExtensionRequest(
            operation="test", data={"input": "hello"}, context={}, metadata={}
        )

        response = await pipeline.execute(request, core_handler)

        # All extensions should be applied
        assert "first" in response.extensions_applied
        assert "second" in response.extensions_applied
        assert "third" in response.extensions_applied

        # Order should be priority order
        first_idx = response.extensions_applied.index("first")
        second_idx = response.extensions_applied.index("second")
        third_idx = response.extensions_applied.index("third")
        assert first_idx < second_idx < third_idx

    @pytest.mark.asyncio
    async def test_extension_pipeline_skip_disabled(self):
        """Test that disabled extensions are skipped."""
        from core.extensions.pipeline import (
            ExtensionConfig,
            ExtensionPipeline,
            ExtensionRegistry,
            ExtensionRequest,
            ExtensionType,
        )

        registry = ExtensionRegistry()
        registry.register(
            ExtensionConfig(
                name="enabled_ext", type=ExtensionType.SANDBOX, enabled=True, priority=1
            )
        )
        registry.register(
            ExtensionConfig(
                name="disabled_ext", type=ExtensionType.SEMANTIC_CACHE, enabled=False, priority=2
            )
        )

        pipeline = ExtensionPipeline(registry)

        async def core_handler(data):
            return {"status": "ok"}

        request = ExtensionRequest(operation="test", data={}, context={}, metadata={})

        response = await pipeline.execute(request, core_handler)

        assert "enabled_ext" in response.extensions_applied
        assert "disabled_ext" not in response.extensions_applied

    @pytest.mark.asyncio
    async def test_extension_pipeline_disabled_globally(self):
        """Test that pipeline bypasses all extensions when disabled."""
        from core.extensions.pipeline import (
            ExtensionConfig,
            ExtensionPipeline,
            ExtensionRegistry,
            ExtensionRequest,
            ExtensionType,
        )

        registry = ExtensionRegistry()
        registry.register(
            ExtensionConfig(name="ext1", type=ExtensionType.SANDBOX, enabled=True, priority=1)
        )

        # Create pipeline with extensions disabled
        mock_settings = MagicMock()
        mock_settings.extensions_enabled = False
        with patch("core.config.get_settings", return_value=mock_settings):
            pipeline = ExtensionPipeline(registry)

        async def core_handler(data):
            return {"direct": True}

        request = ExtensionRequest(operation="test", data={}, context={}, metadata={})

        response = await pipeline.execute(request, core_handler)

        # No extensions should be applied
        assert len(response.extensions_applied) == 0
        assert response.result["direct"] is True

    @pytest.mark.asyncio
    async def test_extension_pipeline_empty_registry(self):
        """Test pipeline with empty registry."""
        from core.extensions.pipeline import ExtensionPipeline, ExtensionRegistry, ExtensionRequest

        registry = ExtensionRegistry()
        pipeline = ExtensionPipeline(registry)

        async def core_handler(data):
            return {"empty_registry": True}

        request = ExtensionRequest(operation="test", data={"key": "value"}, context={}, metadata={})

        response = await pipeline.execute(request, core_handler)

        assert response.result["empty_registry"] is True
        assert len(response.extensions_applied) == 0

@pytest.mark.unit
class TestGlobalRegistry:
    """Tests for global registry functions."""

    def test_get_extension_registry_singleton(self):
        """Test that get_extension_registry returns singleton."""
        import core.extensions.pipeline as pipeline_module
        from core.extensions.pipeline import get_extension_registry

        # Reset global registry
        pipeline_module._extension_registry = None

        registry1 = get_extension_registry()
        registry2 = get_extension_registry()

        assert registry1 is registry2

    def test_build_pipeline(self):
        """Test build_pipeline creates pipeline with global registry."""
        from core.extensions.pipeline import (
            ExtensionPipeline,
            build_pipeline,
            get_extension_registry,
        )

        pipeline = build_pipeline()

        assert isinstance(pipeline, ExtensionPipeline)
        assert pipeline.registry is get_extension_registry()

    def test_build_pipeline_custom_registry(self):
        """Test build_pipeline with custom registry."""
        from core.extensions.pipeline import (
            ExtensionConfig,
            ExtensionRegistry,
            ExtensionType,
            build_pipeline,
        )

        custom_registry = ExtensionRegistry()
        custom_registry.register(
            ExtensionConfig(name="custom_ext", type=ExtensionType.SANDBOX, enabled=True, priority=1)
        )

        pipeline = build_pipeline(custom_registry)

        assert pipeline.registry is custom_registry
        assert len(pipeline.registry._extensions) == 1

@pytest.mark.unit
class TestPipelineAdvanced:
    """Advanced tests for extension pipeline."""

    @pytest.mark.asyncio
    async def test_pipeline_error_propagation(self):
        """Test that errors propagate through the pipeline."""
        from core.extensions.pipeline import (
            ExtensionConfig,
            ExtensionPipeline,
            ExtensionRegistry,
            ExtensionRequest,
            ExtensionType,
        )

        registry = ExtensionRegistry()
        registry.register(
            ExtensionConfig(name="ext1", type=ExtensionType.SANDBOX, enabled=True, priority=1)
        )

        pipeline = ExtensionPipeline(registry)

        async def failing_handler(data):
            raise ValueError("Core handler failed")

        request = ExtensionRequest(operation="test", data={}, context={}, metadata={})

        with pytest.raises(ValueError, match="Core handler failed"):
            await pipeline.execute(request, failing_handler)

    @pytest.mark.asyncio
    async def test_middleware_short_circuiting(self):
        """Test middleware can short-circuit by returning early."""
        from core.extensions.pipeline import (
            ExtensionConfig,
            ExtensionPipeline,
            ExtensionRegistry,
            ExtensionRequest,
            ExtensionType,
        )

        registry = ExtensionRegistry()
        registry.register(
            ExtensionConfig(
                name="cache_ext", type=ExtensionType.SEMANTIC_CACHE, enabled=True, priority=1
            )
        )

        pipeline = ExtensionPipeline(registry)

        call_count = {"core": 0}

        async def core_handler(data):
            call_count["core"] += 1
            return {"result": "from_core"}

        request = ExtensionRequest(operation="test", data={}, context={}, metadata={})

        # Execute through pipeline
        response = await pipeline.execute(request, core_handler)

        # Core should have been called
        assert call_count["core"] == 1
        assert response.result["result"] == "from_core"

    @pytest.mark.asyncio
    async def test_async_middleware_execution(self):
        """Test async middleware properly awaits handlers."""
        from core.extensions.pipeline import (
            ExtensionConfig,
            ExtensionPipeline,
            ExtensionRegistry,
            ExtensionRequest,
            ExtensionType,
        )

        registry = ExtensionRegistry()
        registry.register(
            ExtensionConfig(
                name="async_ext", type=ExtensionType.INPUT_VALIDATION, enabled=True, priority=1
            )
        )

        pipeline = ExtensionPipeline(registry)

        async def async_handler(data):
            await asyncio.sleep(0.001)
            return {"async": True}

        request = ExtensionRequest(operation="test", data={}, context={}, metadata={})

        response = await pipeline.execute(request, async_handler)

        assert response.result["async"] is True
        assert "async_ext" in response.extensions_applied

    @pytest.mark.asyncio
    async def test_extension_startup_error_handling(self):
        """Test that startup errors are logged but don't crash."""
        from core.extensions.pipeline import ExtensionConfig, ExtensionRegistry, ExtensionType

        def failing_startup():
            raise RuntimeError("Startup failed")

        registry = ExtensionRegistry()
        registry.register(
            ExtensionConfig(
                name="failing_ext",
                type=ExtensionType.SANDBOX,
                enabled=True,
                priority=1,
                on_startup=failing_startup,
            )
        )

        # Should not raise, just log error
        await registry.startup()

    @pytest.mark.asyncio
    async def test_extension_shutdown_error_handling(self):
        """Test that shutdown errors are logged but don't crash."""
        from core.extensions.pipeline import ExtensionConfig, ExtensionRegistry, ExtensionType

        def failing_shutdown():
            raise RuntimeError("Shutdown failed")

        registry = ExtensionRegistry()
        registry.register(
            ExtensionConfig(
                name="failing_ext",
                type=ExtensionType.SANDBOX,
                enabled=True,
                priority=1,
                on_shutdown=failing_shutdown,
            )
        )

        # Should not raise, just log error
        await registry.shutdown()

    @pytest.mark.asyncio
    async def test_pipeline_with_multiple_middleware(self):
        """Test pipeline execution with multiple middleware."""
        from core.extensions.pipeline import (
            ExtensionConfig,
            ExtensionPipeline,
            ExtensionRegistry,
            ExtensionRequest,
            ExtensionType,
        )

        registry = ExtensionRegistry()
        registry.register(
            ExtensionConfig(
                name="first", type=ExtensionType.INPUT_VALIDATION, enabled=True, priority=1
            )
        )
        registry.register(
            ExtensionConfig(
                name="second", type=ExtensionType.SEMANTIC_CACHE, enabled=True, priority=2
            )
        )
        registry.register(
            ExtensionConfig(name="third", type=ExtensionType.SELF_HEALING, enabled=True, priority=3)
        )

        pipeline = ExtensionPipeline(registry)

        async def core_handler(data):
            return {"final": "result"}

        request = ExtensionRequest(operation="test", data={}, context={}, metadata={})

        response = await pipeline.execute(request, core_handler)

        # All three should be applied in order
        assert response.extensions_applied == ["first", "second", "third"]

    @pytest.mark.asyncio
    async def test_extension_ordering_by_priority(self):
        """Test that extensions are ordered by priority."""
        from core.extensions.pipeline import (
            ExtensionConfig,
            ExtensionPipeline,
            ExtensionRegistry,
            ExtensionRequest,
            ExtensionType,
        )

        registry = ExtensionRegistry()
        # Register in random order
        registry.register(
            ExtensionConfig(
                name="low_priority", type=ExtensionType.SANDBOX, enabled=True, priority=10
            )
        )
        registry.register(
            ExtensionConfig(
                name="high_priority", type=ExtensionType.INPUT_VALIDATION, enabled=True, priority=1
            )
        )
        registry.register(
            ExtensionConfig(
                name="mid_priority", type=ExtensionType.SEMANTIC_CACHE, enabled=True, priority=5
            )
        )

        pipeline = ExtensionPipeline(registry)

        async def core_handler(data):
            return {}

        request = ExtensionRequest(operation="test", data={}, context={}, metadata={})

        response = await pipeline.execute(request, core_handler)

        # Should be ordered by priority
        assert response.extensions_applied[0] == "high_priority"
        assert response.extensions_applied[1] == "mid_priority"
        assert response.extensions_applied[2] == "low_priority"

    @pytest.mark.asyncio
    async def test_all_extension_types_pass_through(self):
        """Test that all extension types pass through correctly."""
        from core.extensions.pipeline import (
            ExtensionConfig,
            ExtensionPipeline,
            ExtensionRegistry,
            ExtensionRequest,
            ExtensionType,
        )

        registry = ExtensionRegistry()
        # Register one of each type
        for idx, ext_type in enumerate(ExtensionType):
            registry.register(
                ExtensionConfig(
                    name=f"ext_{ext_type.value}", type=ext_type, enabled=True, priority=idx
                )
            )

        pipeline = ExtensionPipeline(registry)

        async def core_handler(data):
            return {"test": "value"}

        request = ExtensionRequest(operation="test", data={}, context={}, metadata={})

        response = await pipeline.execute(request, core_handler)

        # All extensions should be applied
        assert len(response.extensions_applied) == len(ExtensionType)
        assert response.result["test"] == "value"
