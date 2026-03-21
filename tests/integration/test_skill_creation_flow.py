"""Integration tests for autonomous skill creation flow.

Tests the complete pipeline:
1. Executor detects missing capability
2. Capability negotiation returns no_match with offer_generate
3. Executor triggers skill creation
4. Skill is created, validated, and registered
5. Skill is immediately available for use
"""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.autonomous.executor import DefaultSkillExecutor, ReActExecutor
from core.autonomous.models import ActionType, Thought
from core.skills import get_skill_registry, reset_skill_registry

class MockThinkingProviderForFlow:
    """Thinking provider that simulates the create-if-necessary flow."""

    def __init__(self):
        self.call_count = 0
        self.created_skill_name = None

    async def think(self, goal, observations, skills, context):
        self.call_count += 1

        # First call: Try to find existing capability
        if self.call_count == 1:
            return Thought(
                reasoning="I need Excel analysis capability. Let me check available capabilities.",
                action_type=ActionType.NEGOTIATE_CAPABILITY,
                capability_request="Excel file analysis",
                confidence=0.9,
            )

        # Second call: No capability found, create skill
        if self.call_count == 2:
            # Check if negotiation showed no match
            last_obs = observations[-1] if observations else None
            if last_obs and last_obs.result and last_obs.result.get("offer_generate"):
                return Thought(
                    reasoning="No Excel capability found. I'll create one.",
                    action_type=ActionType.CREATE_SKILL,
                    skill_creation_goal="Analyze Excel files and extract data",
                    inputs={"skill_name": "excel-analyzer"},
                    confidence=0.85,
                )

        # Third call: Use the created skill
        if self.call_count == 3:
            last_obs = observations[-1] if observations else None
            if last_obs and last_obs.success and last_obs.result:
                self.created_skill_name = last_obs.result.get("skill_name")
                return Thought(
                    reasoning=f"Skill created: {self.created_skill_name}. Now using it.",
                    action_type=ActionType.EXECUTE_SKILL,
                    skill_name=self.created_skill_name,
                    inputs={"files": ["data.xlsx"]},
                    confidence=0.95,
                )

        # Final: Done
        return Thought(
            reasoning="Excel analysis complete",
            is_final=True,
            answer="Successfully analyzed Excel files using the created skill",
            confidence=1.0,
        )

class MockCapabilityNegotiatorNoMatch:
    """Negotiator that returns no_match to trigger skill creation."""

    async def negotiate(self, request, user_prefs=None):
        return MagicMock(
            status="no_match",
            bound_tools=[],
            offer_generate=True,
            matches=[],
        )

class MockCapabilityNegotiatorMatch:
    """Negotiator that returns a match (no skill creation needed)."""

    def __init__(self, tools: list[str]):
        self.tools = tools

    async def negotiate(self, request, user_prefs=None):
        return MagicMock(
            status="auto_bound",
            bound_tools=self.tools,
            offer_generate=False,
            matches=self.tools,
        )

@pytest.fixture
def temp_skills_dir():
    """Create temporary skills directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)

@pytest.fixture(autouse=True)
def reset_registries():
    """Reset skill registry before each test."""
    reset_skill_registry()
    yield
    reset_skill_registry()

class TestSkillCreationFlow:
    """Integration tests for skill creation flow."""

    @pytest.mark.asyncio
    async def test_create_skill_end_to_end(self, temp_skills_dir):
        """Test complete flow: missing capability -> create skill -> use skill."""
        # Setup mocks
        thinking_provider = MockThinkingProviderForFlow()
        negotiator = MockCapabilityNegotiatorNoMatch()

        # Create a mock skill creator
        mock_skill_creator = MagicMock()
        mock_skill = MagicMock(name="excel-analyzer")

        async def mock_create_skill(goal, skill_name=None, context=None):
            return MagicMock(
                success=True,
                skill_name="excel-analyzer",
                skill=mock_skill,
                signed=False,
                staged_path=temp_skills_dir / "output",
                error=None,
                validation_issues=[],
            )

        mock_skill_creator.create_skill = mock_create_skill

        # Create skill executor that tracks executions
        skill_executor = MagicMock()
        skill_executor.execute_skill = AsyncMock(return_value="Excel analysis complete")

        # Create executor
        executor = ReActExecutor(
            thinking_provider=thinking_provider,
            skill_executor=skill_executor,
            capability_negotiator=negotiator,
            skill_creator=mock_skill_creator,
        )

        # Execute the flow
        result = await executor.execute(
            goal="Analyze all Excel files in the project",
            skills=[],  # Start with no skills
            context={"project": "test-project"},
        )

        # Verify flow completed
        assert result.success
        assert len(result.partial_results) >= 2  # negotiate + create at minimum

        # Verify negotiate_capability was called
        negotiate_obs = [
            o for o in result.partial_results if o.skill_name == "negotiate_capability"
        ]
        assert len(negotiate_obs) == 1
        assert negotiate_obs[0].result["offer_generate"] is True

        # Verify create_skill was called
        create_obs = [o for o in result.partial_results if o.skill_name == "create_skill"]
        assert len(create_obs) == 1
        assert create_obs[0].success

    @pytest.mark.asyncio
    async def test_skill_immediately_available_after_creation(self, temp_skills_dir):
        """Test that created skill is immediately available to router."""
        from core.autonomous.router import get_skill_router, reset_skill_router

        reset_skill_router()

        # Create a skill directly using the helper
        from core.skills import create_and_register_skill

        skill = create_and_register_skill(
            name="test-instant-skill",
            description="A skill for testing instant availability",
            instructions="Do the test thing",
            persist=False,
        )

        # Verify skill is in registry
        registry = get_skill_registry()
        registered = registry.get_skill("test-instant-skill")
        assert registered is not None
        assert registered.name == "test-instant-skill"

        # Verify skill is routable
        router = get_skill_router()
        results = router.route(
            "I need to test something",
            [skill],
            top_k=1,
            threshold=0.0,
        )
        assert len(results) > 0
        assert results[0][0].name == "test-instant-skill"

        reset_skill_router()

    @pytest.mark.asyncio
    async def test_audit_trail_captures_full_flow(self, temp_skills_dir):
        """Test that audit trail captures all events in the flow."""
        thinking_provider = MockThinkingProviderForFlow()
        negotiator = MockCapabilityNegotiatorNoMatch()

        # Create mock skill creator
        mock_creator = MagicMock()

        async def mock_create(goal, skill_name=None, context=None):
            return MagicMock(
                success=True,
                skill_name="audit-test-skill",
                skill=MagicMock(name="audit-test-skill"),
                signed=False,
                staged_path=temp_skills_dir / "output",
                error=None,
                validation_issues=[],
            )

        mock_creator.create_skill = mock_create

        skill_executor = MagicMock()
        skill_executor.execute_skill = AsyncMock(return_value="Done")

        executor = ReActExecutor(
            thinking_provider=thinking_provider,
            skill_executor=skill_executor,
            capability_negotiator=negotiator,
            skill_creator=mock_creator,
            session_id="audit-test-session",
        )

        await executor.execute(goal="Test audit", skills=[])

        # Get audit trail
        audit = executor.get_audit_trail()

        # Verify we have entries
        assert len(audit) > 0

        # Check for expected action types
        action_types = [e["action_type"] for e in audit]
        assert "thought" in action_types  # Thinking steps logged

    @pytest.mark.asyncio
    async def test_flow_continues_when_capability_found(self, temp_skills_dir):
        """Test that flow uses existing capability when found."""
        # Negotiator that returns a match
        negotiator = MockCapabilityNegotiatorMatch(tools=["excel-reader"])

        thoughts = [
            Thought(
                reasoning="Need Excel capability",
                action_type=ActionType.NEGOTIATE_CAPABILITY,
                capability_request="Excel file analysis",
                confidence=0.9,
            ),
            Thought(
                reasoning="Got capability, goal achieved",
                is_final=True,
                answer="Capability acquired",
                confidence=1.0,
            ),
        ]

        class SimpleProvider:
            def __init__(self, thoughts):
                self.thoughts = thoughts
                self.idx = 0

            async def think(self, *args, **kwargs):
                t = self.thoughts[self.idx]
                self.idx += 1
                return t

        executor = ReActExecutor(
            thinking_provider=SimpleProvider(thoughts),
            skill_executor=DefaultSkillExecutor(),
            capability_negotiator=negotiator,
        )

        result = await executor.execute(goal="Test", skills=[])

        assert result.success
        # No create_skill should be called when capability found
        create_obs = [o for o in result.partial_results if o.skill_name == "create_skill"]
        assert len(create_obs) == 0

class TestSkillCreatorUnit:
    """Unit tests for SkillCreator class (when available from 67.1-03)."""

    @pytest.mark.asyncio
    async def test_skill_creator_validation_failure(self, temp_skills_dir):
        """Test that validation failures are handled correctly."""
        # This test will work once 67.1-03 creates SkillCreator

        # For now, test with a mock that simulates validation failure
        mock_creator = MagicMock()

        async def mock_create_with_validation_error(goal, skill_name=None, context=None):
            return MagicMock(
                success=False,
                skill_name="bad-skill",
                skill=None,
                error="Validation failed",
                validation_issues=["Forbidden pattern: rm -rf"],
            )

        mock_creator.create_skill = mock_create_with_validation_error

        thoughts = [
            Thought(
                reasoning="Create a dangerous skill",
                action_type=ActionType.CREATE_SKILL,
                skill_creation_goal="Do something bad",
                confidence=0.9,
            ),
            Thought(
                reasoning="Validation failed, done",
                is_final=True,
                answer="Validation prevented bad action",
                confidence=1.0,
            ),
        ]

        class SimpleProvider:
            def __init__(self, thoughts):
                self.thoughts = thoughts
                self.idx = 0

            async def think(self, *args, **kwargs):
                t = self.thoughts[self.idx]
                self.idx += 1
                return t

        executor = ReActExecutor(
            thinking_provider=SimpleProvider(thoughts),
            skill_executor=DefaultSkillExecutor(),
            skill_creator=mock_creator,
        )

        result = await executor.execute(goal="Test validation", skills=[])

        assert result.success  # Overall goal achieved (loop continued)
        create_obs = [o for o in result.partial_results if o.skill_name == "create_skill"]
        assert len(create_obs) == 1
        assert not create_obs[0].success
        assert "Validation failed" in create_obs[0].error

    @pytest.mark.asyncio
    async def test_skill_creator_with_llm_generator(self, temp_skills_dir):
        """Test skill creation with custom LLM generator."""

        # Mock skill creator that simulates LLM generation
        mock_creator = MagicMock()

        async def mock_create_with_llm(goal, skill_name=None, context=None):
            # Simulate LLM generating skill content
            generated_name = skill_name or "llm-generated-skill"
            mock_skill = MagicMock(name=generated_name)
            return MagicMock(
                success=True,
                skill_name=generated_name,
                skill=mock_skill,
                signed=True,
                staged_path=temp_skills_dir / "output",
                error=None,
                validation_issues=[],
            )

        mock_creator.create_skill = mock_create_with_llm

        thoughts = [
            Thought(
                reasoning="Need JSON parsing skill",
                action_type=ActionType.CREATE_SKILL,
                skill_creation_goal="Parse JSON files",
                inputs={"skill_name": "json-parser"},
                confidence=0.9,
            ),
            Thought(
                reasoning="Skill created",
                is_final=True,
                answer="JSON parser ready",
                confidence=1.0,
            ),
        ]

        class SimpleProvider:
            def __init__(self, thoughts):
                self.thoughts = thoughts
                self.idx = 0

            async def think(self, *args, **kwargs):
                t = self.thoughts[self.idx]
                self.idx += 1
                return t

        executor = ReActExecutor(
            thinking_provider=SimpleProvider(thoughts),
            skill_executor=DefaultSkillExecutor(),
            skill_creator=mock_creator,
        )

        result = await executor.execute(goal="Test LLM generator", skills=[])

        assert result.success
        create_obs = [o for o in result.partial_results if o.skill_name == "create_skill"]
        assert len(create_obs) == 1
        assert create_obs[0].success
        assert create_obs[0].result["skill_name"] == "json-parser"

class TestSkillRegistrationHotReload:
    """Test skill registration and hot reload functionality."""

    @pytest.mark.asyncio
    async def test_registered_skill_in_snapshot(self):
        """Test that registered skill appears in registry snapshot."""
        from core.skills import create_and_register_skill

        skill = create_and_register_skill(
            name="snapshot-test-skill",
            description="For snapshot testing",
            instructions="Test instructions",
            persist=False,
        )

        registry = get_skill_registry()
        snapshot = registry.create_snapshot(eligible_only=False)

        # Skill should be in snapshot
        assert skill.name in snapshot

    @pytest.mark.asyncio
    async def test_router_reindex_on_new_skill(self):
        """Test that router receives new skill on registration."""
        from core.autonomous.router import get_skill_router, reset_skill_router
        from core.skills import create_and_register_skill

        reset_skill_router()
        router = get_skill_router()

        # Create and register skill
        skill = create_and_register_skill(
            name="router-test-skill",
            description="Test router reindexing",
            instructions="Test",
            persist=False,
        )

        # Router should be able to route to it
        results = router.route(
            "I need router testing",
            [skill],
            top_k=1,
            threshold=0.0,
        )

        assert len(results) > 0
        reset_skill_router()
