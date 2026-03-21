"""Unit tests for autonomous execution audit logging (Phase 67.1).

Tests:
- AuditLogger initialization
- All log methods
- Entry retrieval and filtering
- JSON export
- New capability negotiation and skill creation events
"""

from uuid import UUID

from core.autonomous.audit import AuditEntry, AuditLogger
from core.autonomous.models import ActionType, Thought

class TestAuditEntry:
    """Tests for AuditEntry model."""

    def test_audit_entry_defaults(self):
        """Test AuditEntry default values."""
        entry = AuditEntry(
            session_id="test-session",
            initiator_id="test-user",
            action_type="thought",
        )
        assert entry.entry_id is not None
        assert isinstance(entry.entry_id, UUID)
        assert entry.timestamp is not None
        assert entry.success is True
        assert entry.human_review_required is False

    def test_audit_entry_all_action_types(self):
        """Test all action_type values are valid."""
        valid_types = [
            "thought",
            "tool_call",
            "skill_exec",
            "plan",
            "replan",
            "escalation",
            "leash_exceeded",
            "approval_granted",
            "approval_denied",
            "self_dev_start",
            "self_dev_artifact",
            "self_dev_staged",
            "capability_negotiation",
            "skill_creation_request",
            "skill_creation_complete",
        ]

        for action_type in valid_types:
            entry = AuditEntry(
                session_id="test",
                initiator_id="test",
                action_type=action_type,  # type: ignore
            )
            assert entry.action_type == action_type

    def test_audit_entry_serialization(self):
        """Test AuditEntry serializes to JSON correctly."""
        entry = AuditEntry(
            session_id="test-session",
            initiator_id="test-user",
            action_type="skill_exec",
            skill_name="test-skill",
            success=True,
            duration_ms=150,
        )
        data = entry.model_dump(mode="json")

        assert data["session_id"] == "test-session"
        assert data["action_type"] == "skill_exec"
        assert data["skill_name"] == "test-skill"
        # UUID should be serialized as string
        assert isinstance(data["entry_id"], str)

class TestAuditLoggerInit:
    """Tests for AuditLogger initialization."""

    def test_default_init(self):
        """Test AuditLogger with default parameters."""
        logger = AuditLogger()
        assert logger.session_id is not None
        assert logger.initiator_id == "system"
        assert len(logger._entries) == 0

    def test_custom_session_id(self):
        """Test AuditLogger with custom session ID."""
        logger = AuditLogger(session_id="custom-session")
        assert logger.session_id == "custom-session"

    def test_custom_initiator_id(self):
        """Test AuditLogger with custom initiator ID."""
        logger = AuditLogger(initiator_id="user-123")
        assert logger.initiator_id == "user-123"

class TestAuditLoggerThought:
    """Tests for logging thoughts."""

    def test_log_thought_basic(self):
        """Test logging a basic thought."""
        logger = AuditLogger(session_id="test")
        thought = Thought(
            reasoning="I should analyze the data",
            confidence=0.9,
        )

        entry = logger.log_thought(thought)

        assert entry.action_type == "thought"
        assert entry.reasoning == "I should analyze the data"
        assert entry.confidence == 0.9
        assert entry.session_id == "test"

    def test_log_thought_with_action_type(self):
        """Test logging thought with action type."""
        logger = AuditLogger()
        thought = Thought(
            reasoning="Need capability",
            action_type=ActionType.NEGOTIATE_CAPABILITY,
            capability_request="database access",
            confidence=0.85,
        )

        entry = logger.log_thought(thought)

        assert entry.action_type == "thought"
        assert entry.confidence == 0.85

    def test_log_thought_final(self):
        """Test logging final thought with answer."""
        logger = AuditLogger()
        thought = Thought(
            reasoning="Task complete",
            confidence=1.0,
            is_final=True,
            answer="Successfully processed",
        )

        entry = logger.log_thought(thought)

        assert entry.action_details["is_final"] is True
        assert entry.action_details["answer"] == "Successfully processed"

class TestAuditLoggerAction:
    """Tests for logging skill executions."""

    def test_log_action_success(self):
        """Test logging successful action."""
        logger = AuditLogger()
        entry = logger.log_action(
            skill_name="data-processor",
            inputs={"data": [1, 2, 3]},
            result={"processed": True},
            success=True,
            duration_ms=250,
        )

        assert entry.action_type == "skill_exec"
        assert entry.skill_name == "data-processor"
        assert entry.inputs == {"data": [1, 2, 3]}
        assert entry.success is True
        assert entry.duration_ms == 250

    def test_log_action_failure(self):
        """Test logging failed action."""
        logger = AuditLogger()
        entry = logger.log_action(
            skill_name="failing-skill",
            inputs={},
            result=None,
            success=False,
            error="Skill not found",
        )

        assert entry.success is False
        assert entry.error == "Skill not found"

    def test_log_action_with_tokens(self):
        """Test logging action with token usage."""
        logger = AuditLogger()
        entry = logger.log_action(
            skill_name="llm-skill",
            inputs={"prompt": "test"},
            result="output",
            success=True,
            tokens_used=500,
        )

        assert entry.tokens_used == 500

class TestAuditLoggerPlan:
    """Tests for logging plan events."""

    def test_log_plan(self):
        """Test logging plan creation."""
        logger = AuditLogger()
        entry = logger.log_plan(
            plan=["Step 1", "Step 2", "Step 3"],
            goal="Process all files",
        )

        assert entry.action_type == "plan"
        assert entry.action_details["goal"] == "Process all files"
        assert entry.action_details["step_count"] == 3
        assert entry.action_details["steps"] == ["Step 1", "Step 2", "Step 3"]

    def test_log_replan(self):
        """Test logging plan revision."""
        logger = AuditLogger()
        entry = logger.log_replan(
            reason="Step 2 failed, need alternative",
            new_plan=["Step 1", "Step 2a", "Step 3"],
        )

        assert entry.action_type == "replan"
        assert entry.action_details["reason"] == "Step 2 failed, need alternative"
        assert entry.action_details["step_count"] == 3

class TestAuditLoggerLeash:
    """Tests for logging leash events."""

    def test_log_leash_exceeded(self):
        """Test logging leash exceeded event."""
        logger = AuditLogger()
        entry = logger.log_leash_exceeded(reasons=["Max actions reached", "Cost limit exceeded"])

        assert entry.action_type == "leash_exceeded"
        assert entry.success is False
        assert entry.action_details["reasons"] == ["Max actions reached", "Cost limit exceeded"]

class TestAuditLoggerEscalation:
    """Tests for logging escalation events."""

    def test_log_escalation(self):
        """Test logging escalation request."""
        logger = AuditLogger()
        entry = logger.log_escalation(
            reason="Low confidence on critical operation",
            context={"operation": "delete_all", "confidence": 0.3},
            requires_human=True,
        )

        assert entry.action_type == "escalation"
        assert entry.action_details["reason"] == "Low confidence on critical operation"
        assert entry.human_review_required is True

    def test_log_escalation_no_human(self):
        """Test logging escalation without human requirement."""
        logger = AuditLogger()
        entry = logger.log_escalation(
            reason="Informational only",
            context={},
            requires_human=False,
        )

        assert entry.human_review_required is False

class TestAuditLoggerApproval:
    """Tests for logging approval events."""

    def test_log_approval_granted(self):
        """Test logging approval granted."""
        logger = AuditLogger()
        entry = logger.log_approval(
            approved=True,
            reviewer_id="admin-user",
            notes="Looks good",
        )

        assert entry.action_type == "approval_granted"
        assert entry.human_reviewer_id == "admin-user"
        assert entry.human_decision == "approved"
        assert entry.human_notes == "Looks good"

    def test_log_approval_denied(self):
        """Test logging approval denied."""
        logger = AuditLogger()
        entry = logger.log_approval(
            approved=False,
            reviewer_id="admin-user",
            notes="Too risky",
        )

        assert entry.action_type == "approval_denied"
        assert entry.human_decision == "denied"

class TestAuditLoggerSelfDev:
    """Tests for logging self-development events."""

    def test_log_self_dev_start(self):
        """Test logging self-dev session start."""
        logger = AuditLogger()
        entry = logger.log_self_dev_start(
            goal="Create Excel parser skill",
            dev_session_id="dev-123",
        )

        assert entry.action_type == "self_dev_start"
        assert entry.action_details["goal"] == "Create Excel parser skill"
        assert entry.action_details["dev_session_id"] == "dev-123"

    def test_log_self_dev_artifact(self):
        """Test logging self-dev artifact creation."""
        logger = AuditLogger()
        entry = logger.log_self_dev_artifact(
            artifact_type="skill",
            path="/tmp/skills/excel-parser/SKILL.md",
            signed=True,
        )

        assert entry.action_type == "self_dev_artifact"
        assert entry.action_details["artifact_type"] == "skill"
        assert entry.action_details["signed"] is True

    def test_log_self_dev_staged(self):
        """Test logging self-dev staging completion."""
        logger = AuditLogger()
        entry = logger.log_self_dev_staged(
            output_path="/tmp/output",
            artifacts=["SKILL.md", "README.md"],
        )

        assert entry.action_type == "self_dev_staged"
        assert entry.action_details["artifact_count"] == 2

class TestAuditLoggerCapabilityNegotiation:
    """Tests for logging capability negotiation (Phase 67.1)."""

    def test_log_capability_negotiation_auto_bound(self):
        """Test logging successful auto-bound negotiation."""
        logger = AuditLogger()
        entry = logger.log_capability_negotiation(
            request="filesystem read/write access",
            status="auto_bound",
            bound_tools=["fs-reader", "fs-writer"],
        )

        assert entry.action_type == "capability_negotiation"
        assert entry.action_details["request"] == "filesystem read/write access"
        assert entry.action_details["status"] == "auto_bound"
        assert entry.action_details["bound_tools"] == ["fs-reader", "fs-writer"]
        assert entry.success is True

    def test_log_capability_negotiation_no_match(self):
        """Test logging negotiation with no match."""
        logger = AuditLogger()
        entry = logger.log_capability_negotiation(
            request="quantum computing access",
            status="no_match",
            bound_tools=[],
            alternatives=["classical-compute", "gpu-compute"],
        )

        assert entry.action_type == "capability_negotiation"
        assert entry.action_details["status"] == "no_match"
        assert entry.action_details["alternatives"] == ["classical-compute", "gpu-compute"]
        assert entry.success is False  # no_match is not successful

    def test_log_capability_negotiation_degraded(self):
        """Test logging degraded capability negotiation."""
        logger = AuditLogger()
        entry = logger.log_capability_negotiation(
            request="high-performance database",
            status="degraded",
            bound_tools=["sqlite-fallback"],
        )

        assert entry.action_details["status"] == "degraded"
        assert entry.success is True  # degraded is considered success

class TestAuditLoggerSkillCreation:
    """Tests for logging skill creation (Phase 67.1)."""

    def test_log_skill_creation_request(self):
        """Test logging skill creation request."""
        logger = AuditLogger()
        entry = logger.log_skill_creation_request(
            goal="Parse and analyze Excel spreadsheets",
            skill_name="excel-analyzer",
            triggered_by="capability_gap",
        )

        assert entry.action_type == "skill_creation_request"
        assert entry.action_details["goal"] == "Parse and analyze Excel spreadsheets"
        assert entry.action_details["requested_name"] == "excel-analyzer"
        assert entry.action_details["triggered_by"] == "capability_gap"

    def test_log_skill_creation_request_no_name(self):
        """Test logging skill creation request without name."""
        logger = AuditLogger()
        entry = logger.log_skill_creation_request(
            goal="Do something",
            # No skill_name provided
        )

        assert entry.action_details["requested_name"] is None
        assert entry.action_details["triggered_by"] == "capability_gap"

    def test_log_skill_creation_request_user_triggered(self):
        """Test logging user-triggered skill creation."""
        logger = AuditLogger()
        entry = logger.log_skill_creation_request(
            goal="Custom skill",
            skill_name="user-skill",
            triggered_by="user_request",
        )

        assert entry.action_details["triggered_by"] == "user_request"

    def test_log_skill_creation_complete_success(self):
        """Test logging successful skill creation."""
        logger = AuditLogger()
        entry = logger.log_skill_creation_complete(
            skill_name="excel-analyzer",
            success=True,
            signed=True,
        )

        assert entry.action_type == "skill_creation_complete"
        assert entry.skill_name == "excel-analyzer"
        assert entry.success is True
        assert entry.action_details["signed"] is True
        assert entry.action_details["validation_issues"] == []

    def test_log_skill_creation_complete_failure(self):
        """Test logging failed skill creation."""
        logger = AuditLogger()
        entry = logger.log_skill_creation_complete(
            skill_name="bad-skill",
            success=False,
            error="Validation failed",
            validation_issues=["Forbidden pattern: eval()", "Unsafe import"],
        )

        assert entry.action_type == "skill_creation_complete"
        assert entry.success is False
        assert entry.error == "Validation failed"
        assert len(entry.action_details["validation_issues"]) == 2

class TestAuditLoggerRetrieval:
    """Tests for entry retrieval methods."""

    def test_get_entries(self):
        """Test getting all entries."""
        logger = AuditLogger()
        thought = Thought(reasoning="test", confidence=1.0)

        logger.log_thought(thought)
        logger.log_action("skill1", {}, "result", True)
        logger.log_capability_negotiation("test", "auto_bound", ["tool1"])

        entries = logger.get_entries()
        assert len(entries) == 3

    def test_get_entries_by_type(self):
        """Test filtering entries by type."""
        logger = AuditLogger()
        thought = Thought(reasoning="test", confidence=1.0)

        logger.log_thought(thought)
        logger.log_thought(thought)
        logger.log_action("skill1", {}, "result", True)

        thought_entries = logger.get_entries_by_type("thought")
        action_entries = logger.get_entries_by_type("skill_exec")

        assert len(thought_entries) == 2
        assert len(action_entries) == 1

    def test_get_entries_empty(self):
        """Test getting entries when none exist."""
        logger = AuditLogger()
        entries = logger.get_entries()
        assert entries == []

    def test_to_json(self):
        """Test JSON export."""
        logger = AuditLogger(session_id="json-test")
        thought = Thought(reasoning="test", confidence=0.9)
        logger.log_thought(thought)

        json_entries = logger.to_json()

        assert len(json_entries) == 1
        assert json_entries[0]["session_id"] == "json-test"
        assert json_entries[0]["action_type"] == "thought"
        # Should be JSON-serializable
        import json

        json.dumps(json_entries)  # Should not raise

class TestAuditLoggerImmutability:
    """Tests for entry list immutability."""

    def test_get_entries_returns_copy(self):
        """Test that get_entries returns a copy."""
        logger = AuditLogger()
        thought = Thought(reasoning="test", confidence=1.0)
        logger.log_thought(thought)

        entries = logger.get_entries()
        entries.clear()

        # Original should be unchanged
        assert len(logger.get_entries()) == 1
