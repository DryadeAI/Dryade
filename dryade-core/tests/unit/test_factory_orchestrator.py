"""Unit tests for core.factory.orchestrator.

Covers: FactoryPipeline, emit_factory_progress, PIPELINE_STEPS, _sanitize_name.

Gap 1 regression: verifies generate_config argument order.
Gap 6 regression: verifies autonomy check is called.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.factory.models import (
    ArtifactType,
    CreationRequest,
)
from core.factory.orchestrator import (
    PIPELINE_STEPS,
    FactoryPipeline,
    _sanitize_name,
    emit_factory_progress,
)

# ---------------------------------------------------------------------------
# PIPELINE_STEPS constant
# ---------------------------------------------------------------------------

class TestPipelineSteps:
    """Pipeline step definitions."""

    def test_step_count(self):
        """PIPELINE_STEPS has 8 entries."""
        assert len(PIPELINE_STEPS) == 8

    def test_step_names(self):
        expected = [
            "deduplication",
            "config_generation",
            "user_review",
            "scaffold",
            "register",
            "test",
            "discover",
            "complete",
        ]
        assert PIPELINE_STEPS == expected

# ---------------------------------------------------------------------------
# emit_factory_progress
# ---------------------------------------------------------------------------

class TestEmitFactoryProgress:
    """Factory progress event creation."""

    def test_creates_chat_event(self):
        """Returns a ChatEvent with correct type."""
        event = emit_factory_progress(1, "deduplication", "test_agent")
        assert event.type == "progress"

    def test_metadata_contains_factory_flag(self):
        event = emit_factory_progress(1, "deduplication", "test_agent")
        assert event.metadata["factory"] is True

    def test_metadata_contains_step_info(self):
        event = emit_factory_progress(3, "user_review", "my_agent")
        assert event.metadata["current_step"] == 3
        assert event.metadata["total_steps"] == 8
        assert event.metadata["artifact_name"] == "my_agent"

    def test_percentage_calculation(self):
        """Step 4 of 8 = 50%."""
        event = emit_factory_progress(4, "scaffold", "agent")
        assert event.metadata["percentage"] == 50

    def test_percentage_step_1(self):
        """Step 1 of 8 = round(1/8 * 100) = 12."""
        event = emit_factory_progress(1, "deduplication", "agent")
        assert event.metadata["percentage"] == round(1 / 8 * 100)

    def test_percentage_step_8(self):
        """Step 8 of 8 = 100%."""
        event = emit_factory_progress(8, "complete", "agent")
        assert event.metadata["percentage"] == 100

    def test_detail_in_content(self):
        event = emit_factory_progress(1, "deduplication", "agent", "checking duplicates")
        assert "checking duplicates" in event.content

    def test_current_agent_format(self):
        event = emit_factory_progress(2, "config_generation", "agent")
        assert event.metadata["current_agent"] == "factory:config_generation"

# ---------------------------------------------------------------------------
# _sanitize_name
# ---------------------------------------------------------------------------

class TestSanitizeName:
    """Name sanitization from goal strings."""

    def test_basic_sanitization(self):
        result = _sanitize_name("Build a websearch agent")
        assert result
        assert result[0].isalpha()

    def test_special_chars_removed(self):
        result = _sanitize_name("Build an agent!@# for $data")
        assert "!" not in result
        assert "@" not in result
        assert "#" not in result
        assert "$" not in result

    def test_lowercased(self):
        result = _sanitize_name("Build A WEBSEARCH Agent")
        assert result == result.lower()

    def test_truncated_to_64(self):
        long_goal = " ".join([f"word{i}" for i in range(100)])
        result = _sanitize_name(long_goal)
        assert len(result) <= 64

    def test_empty_goal(self):
        result = _sanitize_name("")
        assert result  # Should never be empty (falls back)

    def test_numeric_prefix_prepends_artifact(self):
        """Goals starting with digits get 'artifact_' prefix."""
        result = _sanitize_name("123 number agent")
        assert result[0].isalpha()

# ---------------------------------------------------------------------------
# FactoryPipeline.create: argument order regression (Gap 1)
# ---------------------------------------------------------------------------

class TestPipelineCreateArgumentOrder:
    """Verify generate_config is called with correct argument order."""

    @pytest.mark.asyncio
    async def test_generate_config_argument_order(self):
        """Gap 1 regression: generate_config(goal, name, framework, artifact_type).

        The orchestrator uses lazy imports inside create(), so we patch
        at the source module (core.factory.config_generator.generate_config).
        """
        request = CreationRequest(
            goal="Build a websearch agent",
            suggested_name="websearch_agent",
            framework="custom",
            artifact_type=ArtifactType.AGENT,
        )
        pipeline = FactoryPipeline()

        captured_args = {}

        async def mock_generate_config(goal, name=None, framework=None, artifact_type=None):
            captured_args["goal"] = goal
            captured_args["name"] = name
            captured_args["framework"] = framework
            captured_args["artifact_type"] = artifact_type
            return {
                "artifact_type": "agent",
                "framework": "custom",
                "name": "websearch_agent",
                "description": goal,
                "goal": goal,
                "tools": [],
                "mcp_servers": [],
            }

        with (
            patch(
                "core.factory.config_generator.generate_config",
                side_effect=mock_generate_config,
            ),
            patch(
                "core.factory.relevance.check_existing_capabilities",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "core.factory.scaffold.scaffold_artifact",
                return_value=(True, "/tmp/test", "OK"),
            ),
            patch(
                "core.factory.registry.FactoryRegistry.register",
                return_value="test-id",
            ),
            patch(
                "core.factory.registry.FactoryRegistry.update_status",
            ),
            patch(
                "core.factory.registry.FactoryRegistry.update_artifact",
            ),
            patch.object(
                pipeline,
                "_emit_progress",
                new_callable=AsyncMock,
            ),
            patch.object(
                pipeline,
                "_run_discovery",
                new_callable=AsyncMock,
            ),
            patch(
                "core.factory.tester.test_artifact",
                new_callable=AsyncMock,
                return_value=(True, 0, "OK"),
            ),
        ):
            result = await pipeline.create(request, skip_autonomy=True)

            # Verify generate_config was called with correct positional argument order
            assert captured_args["goal"] == "Build a websearch agent"
            assert captured_args["name"] == "websearch_agent"
            assert captured_args["framework"] == "custom"
            assert captured_args["artifact_type"] == ArtifactType.AGENT

# ---------------------------------------------------------------------------
# FactoryPipeline.create: autonomy check (Gap 6)
# ---------------------------------------------------------------------------

class TestPipelineAutonomyCheck:
    """Verify autonomy dispatch in create() Step 3."""

    @pytest.mark.asyncio
    async def test_create_calls_autonomy_when_not_skipped(self):
        """Gap 6 regression: create() calls check_autonomy when skip_autonomy=False.

        The orchestrator lazy-imports action_autonomy inside create(),
        so we patch at the source module.
        """
        request = CreationRequest(
            goal="Build a test agent for autonomy",
            framework="custom",
            artifact_type=ArtifactType.AGENT,
        )
        pipeline = FactoryPipeline()

        # Set up autonomy mock that returns AUTO level (not APPROVE/CONFIRM)
        mock_autonomy_instance = MagicMock()

        # Import the real AutonomyLevel if available, else mock it
        try:
            from core.orchestrator.action_autonomy import AutonomyLevel

            mock_autonomy_instance.check_autonomy.return_value = AutonomyLevel.AUTO
        except ImportError:
            mock_auto = MagicMock()
            mock_auto.value = "auto"
            mock_autonomy_instance.check_autonomy.return_value = mock_auto

        with (
            patch(
                "core.factory.config_generator.generate_config",
                new_callable=AsyncMock,
                return_value={
                    "artifact_type": "agent",
                    "framework": "custom",
                    "name": "test_autonomy",
                    "goal": "test",
                    "tools": [],
                    "mcp_servers": [],
                },
            ),
            patch(
                "core.factory.relevance.check_existing_capabilities",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "core.factory.scaffold.scaffold_artifact",
                return_value=(True, "/tmp/test", "OK"),
            ),
            patch(
                "core.factory.registry.FactoryRegistry.register",
                return_value="test-id",
            ),
            patch(
                "core.factory.registry.FactoryRegistry.update_status",
            ),
            patch(
                "core.factory.registry.FactoryRegistry.update_artifact",
            ),
            patch.object(
                pipeline,
                "_emit_progress",
                new_callable=AsyncMock,
            ),
            patch.object(
                pipeline,
                "_run_discovery",
                new_callable=AsyncMock,
            ),
            patch(
                "core.factory.tester.test_artifact",
                new_callable=AsyncMock,
                return_value=(True, 0, "OK"),
            ),
            patch(
                "core.orchestrator.action_autonomy.get_action_autonomy",
                return_value=mock_autonomy_instance,
            ),
        ):
            result = await pipeline.create(request, skip_autonomy=False)

            # The autonomy module was checked
            mock_autonomy_instance.check_autonomy.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_skips_autonomy_when_flagged(self):
        """skip_autonomy=True bypasses the autonomy check entirely."""
        request = CreationRequest(
            goal="Build a test agent skip autonomy",
            framework="custom",
            artifact_type=ArtifactType.AGENT,
        )
        pipeline = FactoryPipeline()

        with (
            patch(
                "core.factory.config_generator.generate_config",
                new_callable=AsyncMock,
                return_value={
                    "artifact_type": "agent",
                    "framework": "custom",
                    "name": "test_skip",
                    "goal": "test",
                    "tools": [],
                    "mcp_servers": [],
                },
            ),
            patch(
                "core.factory.relevance.check_existing_capabilities",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "core.factory.scaffold.scaffold_artifact",
                return_value=(True, "/tmp/test", "OK"),
            ),
            patch(
                "core.factory.registry.FactoryRegistry.register",
                return_value="test-id",
            ),
            patch(
                "core.factory.registry.FactoryRegistry.update_status",
            ),
            patch(
                "core.factory.registry.FactoryRegistry.update_artifact",
            ),
            patch.object(
                pipeline,
                "_emit_progress",
                new_callable=AsyncMock,
            ),
            patch.object(
                pipeline,
                "_run_discovery",
                new_callable=AsyncMock,
            ),
            patch(
                "core.factory.tester.test_artifact",
                new_callable=AsyncMock,
                return_value=(True, 0, "OK"),
            ),
        ):
            result = await pipeline.create(request, skip_autonomy=True)

            # Should succeed without importing action_autonomy at all
            assert result.success is True

    @pytest.mark.asyncio
    async def test_create_approve_returns_pending(self):
        """When autonomy is APPROVE, create() returns pending result."""
        request = CreationRequest(
            goal="Build agent needing approval",
            framework="custom",
            artifact_type=ArtifactType.AGENT,
        )
        pipeline = FactoryPipeline()

        try:
            from core.orchestrator.action_autonomy import AutonomyLevel

            approve_level = AutonomyLevel.APPROVE
        except ImportError:
            pytest.skip("action_autonomy not available")

        mock_autonomy_instance = MagicMock()
        mock_autonomy_instance.check_autonomy.return_value = approve_level

        with (
            patch(
                "core.factory.config_generator.generate_config",
                new_callable=AsyncMock,
                return_value={
                    "artifact_type": "agent",
                    "framework": "custom",
                    "name": "approval_test",
                    "goal": "test",
                    "tools": [],
                    "mcp_servers": [],
                },
            ),
            patch(
                "core.factory.relevance.check_existing_capabilities",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch.object(
                pipeline,
                "_emit_progress",
                new_callable=AsyncMock,
            ),
            patch(
                "core.orchestrator.action_autonomy.get_action_autonomy",
                return_value=mock_autonomy_instance,
            ),
            patch(
                "core.factory.registry.FactoryRegistry.register",
                return_value="pending-id",
            ),
        ):
            result = await pipeline.create(request, skip_autonomy=False)

            # APPROVE returns early with pending status
            assert result.success is False
            assert "approval" in result.message.lower() or "approve" in result.message.lower()

# ---------------------------------------------------------------------------
# FactoryPipeline: method existence checks
# ---------------------------------------------------------------------------

class TestPipelineMethodsExist:
    """Verify update() and rollback() are callable."""

    def test_update_method_exists(self):
        pipeline = FactoryPipeline()
        assert callable(getattr(pipeline, "update", None))

    def test_rollback_method_exists(self):
        pipeline = FactoryPipeline()
        assert callable(getattr(pipeline, "rollback", None))

    def test_create_method_exists(self):
        pipeline = FactoryPipeline()
        assert callable(getattr(pipeline, "create", None))

    def test_execute_approved_creation_method_exists(self):
        pipeline = FactoryPipeline()
        assert callable(getattr(pipeline, "execute_approved_creation", None))

# ---------------------------------------------------------------------------
# _run_discovery: agent registration
# ---------------------------------------------------------------------------

class TestRunDiscovery:
    """Verify _run_discovery passes correct agents_dir to AgentAutoDiscovery."""

    @pytest.mark.asyncio
    async def test_agent_discovery_uses_parent_dir(self, tmp_path):
        """AgentAutoDiscovery must receive the parent directory, not the agent path."""
        agent_dir = tmp_path / "agents" / "my_new_agent"
        agent_dir.mkdir(parents=True)

        pipeline = FactoryPipeline()

        mock_discovery = MagicMock()
        mock_discovery.discover_and_register.return_value = ["my_new_agent"]

        with patch(
            "core.adapters.auto_discovery.AgentAutoDiscovery",
            return_value=mock_discovery,
        ) as mock_cls:
            await pipeline._run_discovery(ArtifactType.AGENT, str(agent_dir))

        # Constructor must receive parent dir (agents/), not agent dir itself
        mock_cls.assert_called_once_with(agent_dir.parent)
        mock_discovery.discover_and_register.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_skill_discovery_skips_silently(self):
        """Skills rely on SkillWatcher — _run_discovery should not raise."""
        pipeline = FactoryPipeline()
        await pipeline._run_discovery(ArtifactType.SKILL, "/tmp/skills/foo")
