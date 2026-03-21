"""Unit tests for enhanced ReActExecutor with capability negotiation and skill creation."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.autonomous.executor import DefaultSkillExecutor, ReActExecutor
from core.autonomous.leash import LeashConfig
from core.autonomous.models import ActionType, Thought

class MockThinkingProvider:
    """Mock thinking provider for tests."""

    def __init__(self, thoughts: list[Thought]):
        self.thoughts = thoughts
        self.call_count = 0

    async def think(self, goal, observations, skills, context):
        thought = self.thoughts[self.call_count]
        self.call_count += 1
        return thought

class MockCapabilityNegotiator:
    """Mock capability negotiator for tests."""

    def __init__(self, status: str = "auto_bound", bound_tools: list[str] | None = None):
        self.status = status
        self.bound_tools = bound_tools or []
        self.negotiate_called = False

    async def negotiate(self, request: str, user_prefs: dict | None = None):
        self.negotiate_called = True
        return MagicMock(
            status=self.status,
            bound_tools=self.bound_tools,
            offer_generate=self.status == "no_match",
        )

class MockSkillCreator:
    """Mock skill creator for tests."""

    def __init__(self, success: bool = True, skill_name: str = "test-skill"):
        self.success = success
        self.skill_name = skill_name
        self.create_called = False

    async def create_skill(self, goal, skill_name=None, context=None):
        self.create_called = True
        if self.success:
            mock_skill = MagicMock(name=self.skill_name)
            return MagicMock(
                success=True,
                skill_name=self.skill_name,
                skill=mock_skill,
                signed=True,
                staged_path=None,
                error=None,
                validation_issues=[],
            )
        return MagicMock(
            success=False,
            skill_name=None,
            skill=None,
            error="Creation failed",
            validation_issues=["test issue"],
        )

@pytest.fixture
def mock_skill():
    """Create a mock skill."""
    skill = MagicMock()
    skill.name = "existing-skill"
    skill.description = "An existing skill"
    return skill

class TestReActExecutorActionRouting:
    """Test action type routing in ReActExecutor."""

    @pytest.mark.asyncio
    async def test_negotiate_capability_action_calls_negotiator(self, mock_skill):
        """Test that negotiate_capability action calls capability negotiator."""
        negotiator = MockCapabilityNegotiator(
            status="auto_bound",
            bound_tools=["tool1", "tool2"],
        )

        thoughts = [
            Thought(
                reasoning="I need filesystem access",
                action_type=ActionType.NEGOTIATE_CAPABILITY,
                capability_request="filesystem operations",
                confidence=0.9,
            ),
            Thought(
                reasoning="Goal achieved",
                is_final=True,
                answer="Done",
                confidence=1.0,
            ),
        ]

        executor = ReActExecutor(
            thinking_provider=MockThinkingProvider(thoughts),
            skill_executor=DefaultSkillExecutor(),
            capability_negotiator=negotiator,
        )

        result = await executor.execute(
            goal="Test capability negotiation",
            skills=[mock_skill],
        )

        assert negotiator.negotiate_called
        assert result.success
        assert len(result.partial_results) == 1
        assert result.partial_results[0].skill_name == "negotiate_capability"

    @pytest.mark.asyncio
    async def test_negotiate_capability_without_negotiator(self, mock_skill):
        """Test negotiate_capability action without negotiator configured."""
        thoughts = [
            Thought(
                reasoning="I need filesystem access",
                action_type=ActionType.NEGOTIATE_CAPABILITY,
                capability_request="filesystem operations",
                confidence=0.9,
            ),
            Thought(
                reasoning="Goal achieved",
                is_final=True,
                answer="Done",
                confidence=1.0,
            ),
        ]

        executor = ReActExecutor(
            thinking_provider=MockThinkingProvider(thoughts),
            skill_executor=DefaultSkillExecutor(),
            # No capability_negotiator
        )

        result = await executor.execute(
            goal="Test capability negotiation",
            skills=[mock_skill],
        )

        # Should continue with error observation
        assert result.success  # Goal still achieved
        assert len(result.partial_results) == 1
        assert not result.partial_results[0].success
        assert "No capability negotiator" in result.partial_results[0].error

    @pytest.mark.asyncio
    async def test_create_skill_action_calls_creator(self, mock_skill):
        """Test that create_skill action calls skill creator."""
        creator = MockSkillCreator(success=True, skill_name="new-skill")

        thoughts = [
            Thought(
                reasoning="I need a new skill to handle Excel files",
                action_type=ActionType.CREATE_SKILL,
                skill_creation_goal="Analyze Excel files",
                inputs={"skill_name": "excel-analyzer"},
                confidence=0.9,
            ),
            Thought(
                reasoning="Now I can use the new skill",
                is_final=True,
                answer="Skill created and ready",
                confidence=1.0,
            ),
        ]

        executor = ReActExecutor(
            thinking_provider=MockThinkingProvider(thoughts),
            skill_executor=DefaultSkillExecutor(),
            skill_creator=creator,
        )

        result = await executor.execute(
            goal="Test skill creation",
            skills=[mock_skill],
        )

        assert creator.create_called
        assert result.success
        # Check partial results - find create_skill observation
        create_obs = [o for o in result.partial_results if o.skill_name == "create_skill"]
        assert len(create_obs) == 1
        assert create_obs[0].success

    @pytest.mark.asyncio
    async def test_create_skill_failure_continues_loop(self, mock_skill):
        """Test that skill creation failure allows loop to continue."""
        creator = MockSkillCreator(success=False)

        thoughts = [
            Thought(
                reasoning="I need a new skill",
                action_type=ActionType.CREATE_SKILL,
                skill_creation_goal="Do something complex",
                confidence=0.9,
            ),
            Thought(
                reasoning="Creation failed, will try another approach",
                is_final=True,
                answer="Alternative approach taken",
                confidence=1.0,
            ),
        ]

        executor = ReActExecutor(
            thinking_provider=MockThinkingProvider(thoughts),
            skill_executor=DefaultSkillExecutor(),
            skill_creator=creator,
        )

        result = await executor.execute(
            goal="Test skill creation failure",
            skills=[mock_skill],
        )

        assert creator.create_called
        assert result.success  # Overall goal still achieved
        # Check that create_skill observation exists and shows failure
        create_obs = [o for o in result.partial_results if o.skill_name == "create_skill"]
        assert len(create_obs) == 1
        assert not create_obs[0].success

    @pytest.mark.asyncio
    async def test_execute_skill_action_still_works(self, mock_skill):
        """Test that standard execute_skill action still works."""
        mock_executor = AsyncMock()
        mock_executor.execute_skill.return_value = "Skill executed!"

        thoughts = [
            Thought(
                reasoning="I'll use an existing skill",
                action_type=ActionType.EXECUTE_SKILL,
                skill_name="existing-skill",
                inputs={"param": "value"},
                confidence=0.9,
            ),
            Thought(
                reasoning="Done",
                is_final=True,
                answer="Complete",
                confidence=1.0,
            ),
        ]

        executor = ReActExecutor(
            thinking_provider=MockThinkingProvider(thoughts),
            skill_executor=mock_executor,
        )

        result = await executor.execute(
            goal="Test standard skill execution",
            skills=[mock_skill],
        )

        mock_executor.execute_skill.assert_called_once()
        assert result.success

    @pytest.mark.asyncio
    async def test_create_skill_uses_default_creator_when_none_provided(self, mock_skill):
        """Test create_skill action falls back to default creator when none provided."""
        # When no skill_creator is passed, the executor will use get_skill_creator()
        # which returns a real SkillCreator that attempts actual skill creation
        thoughts = [
            Thought(
                reasoning="I need a new skill",
                action_type=ActionType.CREATE_SKILL,
                skill_creation_goal="Do something",
                confidence=0.9,
            ),
            Thought(
                reasoning="Done anyway",
                is_final=True,
                answer="Complete",
                confidence=1.0,
            ),
        ]

        executor = ReActExecutor(
            thinking_provider=MockThinkingProvider(thoughts),
            skill_executor=DefaultSkillExecutor(),
            # No skill_creator - will use default
        )

        result = await executor.execute(
            goal="Test skill creation with default creator",
            skills=[mock_skill],
        )

        # Loop should continue regardless of creation outcome
        assert result.success
        create_obs = [o for o in result.partial_results if o.skill_name == "create_skill"]
        assert len(create_obs) == 1
        # Default creator may succeed or fail depending on environment
        # The key is that execution continues either way

class TestReActExecutorAuditTrail:
    """Test audit trail for new actions."""

    @pytest.mark.asyncio
    async def test_negotiate_capability_logged(self, mock_skill):
        """Test that capability negotiation is logged."""
        negotiator = MockCapabilityNegotiator(status="auto_bound", bound_tools=["tool1"])

        thoughts = [
            Thought(
                reasoning="Need capability",
                action_type=ActionType.NEGOTIATE_CAPABILITY,
                capability_request="test capability",
                confidence=0.9,
            ),
            Thought(reasoning="Done", is_final=True, answer="OK", confidence=1.0),
        ]

        executor = ReActExecutor(
            thinking_provider=MockThinkingProvider(thoughts),
            skill_executor=DefaultSkillExecutor(),
            capability_negotiator=negotiator,
        )

        await executor.execute(goal="Test", skills=[mock_skill])

        audit = executor.get_audit_trail()
        action_types = [e["action_type"] for e in audit]
        assert "skill_exec" in action_types  # negotiate_capability logged as skill_exec

    @pytest.mark.asyncio
    async def test_create_skill_logged(self, mock_skill):
        """Test that skill creation is logged."""
        creator = MockSkillCreator(success=True)

        thoughts = [
            Thought(
                reasoning="Create skill",
                action_type=ActionType.CREATE_SKILL,
                skill_creation_goal="test skill",
                confidence=0.9,
            ),
            Thought(reasoning="Done", is_final=True, answer="OK", confidence=1.0),
        ]

        executor = ReActExecutor(
            thinking_provider=MockThinkingProvider(thoughts),
            skill_executor=DefaultSkillExecutor(),
            skill_creator=creator,
        )

        await executor.execute(goal="Test", skills=[mock_skill])

        audit = executor.get_audit_trail()
        action_types = [e["action_type"] for e in audit]
        assert "skill_exec" in action_types  # create_skill logged as skill_exec

    @pytest.mark.asyncio
    async def test_thoughts_logged(self, mock_skill):
        """Test that all thoughts are logged to audit trail."""
        negotiator = MockCapabilityNegotiator(status="auto_bound", bound_tools=["tool1"])

        thoughts = [
            Thought(
                reasoning="First thought",
                action_type=ActionType.NEGOTIATE_CAPABILITY,
                capability_request="test",
                confidence=0.9,  # High enough to pass default leash
            ),
            Thought(
                reasoning="Second thought",
                is_final=True,
                answer="Done",
                confidence=1.0,
            ),
        ]

        executor = ReActExecutor(
            thinking_provider=MockThinkingProvider(thoughts),
            skill_executor=DefaultSkillExecutor(),
            capability_negotiator=negotiator,  # Add negotiator to avoid error path
        )

        await executor.execute(goal="Test audit", skills=[mock_skill])

        audit = executor.get_audit_trail()
        thought_entries = [e for e in audit if e["action_type"] == "thought"]
        assert len(thought_entries) == 2

    @pytest.mark.asyncio
    async def test_audit_trail_has_session_id(self, mock_skill):
        """Test that audit entries have session ID."""
        thoughts = [
            Thought(
                reasoning="Done",
                is_final=True,
                answer="OK",
                confidence=1.0,
            ),
        ]

        executor = ReActExecutor(
            thinking_provider=MockThinkingProvider(thoughts),
            skill_executor=DefaultSkillExecutor(),
            session_id="test-session-123",
        )

        await executor.execute(goal="Test", skills=[mock_skill])

        audit = executor.get_audit_trail()
        assert len(audit) > 0
        assert audit[0]["session_id"] == "test-session-123"

class TestReActExecutorLeash:
    """Test leash constraint checking."""

    @pytest.mark.asyncio
    async def test_leash_exceeded_stops_execution(self, mock_skill):
        """Test that exceeding leash stops execution.

        Leash uses > comparison, so max_actions=1 allows action at count 0 and 1,
        then stops when count becomes 2 (2 > 1 = exceeded).
        To trigger immediately, we need max_actions=0 which blocks at first check.
        """
        # Create a leash that allows no actions (0 > 0 is False, but we need
        # the action to happen and THEN check, so we use max_actions=0)
        # Actually with the way it's coded, check happens FIRST in loop.
        # At start: actions_taken=0, 0 > 0 = False, continues
        # So even max_actions=0 allows one iteration before the action increments counter.
        #
        # Let's test with max_actions=1 and provide negotiator to not trigger error path
        # After 2 actions: 2 > 1 = True, exceeded
        leash = LeashConfig(max_actions=1)
        negotiator = MockCapabilityNegotiator(status="auto_bound", bound_tools=["tool1"])

        thoughts = [
            Thought(
                reasoning="First action",
                action_type=ActionType.NEGOTIATE_CAPABILITY,
                capability_request="test",
                confidence=0.9,
            ),
            Thought(
                reasoning="Second action",
                action_type=ActionType.NEGOTIATE_CAPABILITY,
                capability_request="test2",
                confidence=0.9,
            ),
            Thought(
                reasoning="Third - should not reach",
                is_final=True,
                answer="Done",
                confidence=1.0,
            ),
        ]

        executor = ReActExecutor(
            thinking_provider=MockThinkingProvider(thoughts),
            skill_executor=DefaultSkillExecutor(),
            capability_negotiator=negotiator,
            leash=leash,
        )

        result = await executor.execute(goal="Test leash", skills=[mock_skill])

        assert not result.success
        assert "leash exceeded" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_low_confidence_without_handler_fails(self, mock_skill):
        """Test that low confidence without human handler fails."""
        leash = LeashConfig(confidence_threshold=0.9)

        thoughts = [
            Thought(
                reasoning="Low confidence action",
                skill_name="existing-skill",
                inputs={},
                confidence=0.5,  # Below threshold
            ),
        ]

        executor = ReActExecutor(
            thinking_provider=MockThinkingProvider(thoughts),
            skill_executor=DefaultSkillExecutor(),
            leash=leash,
            # No human_handler
        )

        result = await executor.execute(goal="Test", skills=[mock_skill])

        assert not result.success
        assert "confidence" in result.reason.lower()
