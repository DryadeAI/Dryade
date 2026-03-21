"""Unit tests for core.factory.registry.

Covers: FactoryRegistry CRUD, versioning, signals, get_factory_registry singleton.

Uses a per-test in-memory SQLAlchemy database for isolation.
"""

from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.database.models import Base
from core.factory.models import (
    ArtifactStatus,
    ArtifactType,
    ArtifactVersion,
    FactoryArtifact,
    RelevanceSignal,
)
from core.factory.registry import FactoryRegistry, get_factory_registry

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def registry():
    """Create a FactoryRegistry backed by an in-memory SQLAlchemy database."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    @contextmanager
    def _get_session():
        session = Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    reg = FactoryRegistry()
    # Patch _get_session to use the per-test in-memory database
    reg._get_session = staticmethod(_get_session)
    return reg

def _make_artifact(
    name: str = "test_artifact",
    artifact_type: ArtifactType = ArtifactType.AGENT,
    framework: str = "custom",
    status: ArtifactStatus = ArtifactStatus.SCAFFOLDED,
) -> FactoryArtifact:
    """Create a test FactoryArtifact with sensible defaults."""
    now = datetime.now(UTC)
    return FactoryArtifact(
        id=str(uuid4()),
        name=name,
        artifact_type=artifact_type,
        framework=framework,
        version=1,
        status=status,
        source_prompt=f"Test prompt for {name}",
        config_json={"name": name, "framework": framework},
        artifact_path=f"/tmp/test/{name}",
        trigger="user",
        created_at=now,
        updated_at=now,
    )

# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

class TestRegistrySingleton:
    """get_factory_registry() singleton behavior."""

    def test_returns_same_instance(self):
        r1 = get_factory_registry()
        r2 = get_factory_registry()
        assert r1 is r2

    def test_returns_factory_registry_type(self):
        r = get_factory_registry()
        assert isinstance(r, FactoryRegistry)

# ---------------------------------------------------------------------------
# Register and Get
# ---------------------------------------------------------------------------

class TestRegisterAndGet:
    """Artifact registration and retrieval."""

    def test_register_returns_id(self, registry):
        artifact = _make_artifact("reg_test")
        result_id = registry.register(artifact)
        assert result_id == artifact.id

    def test_get_by_name(self, registry):
        artifact = _make_artifact("get_name_test")
        registry.register(artifact)

        found = registry.get("get_name_test")
        assert found is not None
        assert found.name == "get_name_test"
        assert found.framework == "custom"

    def test_get_by_id(self, registry):
        artifact = _make_artifact("get_id_test")
        registry.register(artifact)

        found = registry.get_by_id(artifact.id)
        assert found is not None
        assert found.id == artifact.id

    def test_get_nonexistent_returns_none(self, registry):
        assert registry.get("nonexistent") is None

    def test_get_by_id_nonexistent_returns_none(self, registry):
        assert registry.get_by_id("fake-uuid-000") is None

# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

class TestListArtifacts:
    """Listing with optional filters."""

    def test_list_all_returns_registered(self, registry):
        registry.register(_make_artifact("list_a"))
        registry.register(_make_artifact("list_b"))

        items = registry.list_all()
        names = [a.name for a in items]
        assert "list_a" in names
        assert "list_b" in names

    def test_list_filter_by_type(self, registry):
        registry.register(_make_artifact("agent_x", artifact_type=ArtifactType.AGENT))
        registry.register(_make_artifact("tool_y", artifact_type=ArtifactType.TOOL))

        agents = registry.list_all(artifact_type=ArtifactType.AGENT)
        assert all(a.artifact_type == ArtifactType.AGENT for a in agents)

    def test_list_filter_by_status(self, registry):
        registry.register(_make_artifact("active_a", status=ArtifactStatus.ACTIVE))
        registry.register(_make_artifact("failed_b", status=ArtifactStatus.FAILED))

        active = registry.list_all(status=ArtifactStatus.ACTIVE)
        assert all(a.status == ArtifactStatus.ACTIVE for a in active)
        assert len(active) == 1

# ---------------------------------------------------------------------------
# Update status
# ---------------------------------------------------------------------------

class TestUpdateStatus:
    """Status transitions."""

    def test_update_status(self, registry):
        registry.register(_make_artifact("status_test"))
        registry.update_status("status_test", ArtifactStatus.ACTIVE)

        found = registry.get("status_test")
        assert found.status == ArtifactStatus.ACTIVE

# ---------------------------------------------------------------------------
# Versioning
# ---------------------------------------------------------------------------

class TestVersioning:
    """Version management."""

    def test_add_version(self, registry):
        artifact = _make_artifact("version_test")
        registry.register(artifact)

        version_id = registry.add_version(artifact.id, 2, {"updated": True}, ["/tmp/v2"])
        assert version_id  # Non-empty

    def test_get_versions(self, registry):
        artifact = _make_artifact("versions_list")
        registry.register(artifact)
        registry.add_version(artifact.id, 2, {}, [])

        versions = registry.get_versions(artifact.id)
        assert len(versions) >= 2  # v1 from register + v2
        assert isinstance(versions[0], ArtifactVersion)

    def test_versions_ordered(self, registry):
        artifact = _make_artifact("versions_order")
        registry.register(artifact)
        registry.add_version(artifact.id, 2, {}, [])
        registry.add_version(artifact.id, 3, {}, [])

        versions = registry.get_versions(artifact.id)
        version_nums = [v.version for v in versions]
        assert version_nums == sorted(version_nums)

# ---------------------------------------------------------------------------
# Archive and Delete
# ---------------------------------------------------------------------------

class TestArchiveAndDelete:
    """Soft and hard deletion."""

    def test_archive_artifact(self, registry):
        registry.register(_make_artifact("archive_test"))

        result = registry.archive("archive_test")
        assert result is True

        found = registry.get("archive_test")
        assert found.status == ArtifactStatus.ARCHIVED

    def test_archive_nonexistent_returns_false(self, registry):
        result = registry.archive("nonexistent_artifact")
        assert result is False

    def test_hard_delete(self, registry):
        registry.register(_make_artifact("delete_test"))

        result = registry.hard_delete("delete_test")
        assert result is True

        assert registry.get("delete_test") is None

    def test_hard_delete_nonexistent_returns_false(self, registry):
        result = registry.hard_delete("nonexistent_artifact")
        assert result is False

# ---------------------------------------------------------------------------
# Duplicate name handling
# ---------------------------------------------------------------------------

class TestDuplicateName:
    """Duplicate registration behavior."""

    def test_duplicate_name_raises(self, registry):
        """Explicit duplicate check raises ValueError before hitting UNIQUE constraint.

        The registry pre-checks for duplicate names and raises ValueError with
        a helpful message instead of letting SQLAlchemy raise IntegrityError.
        """
        registry.register(_make_artifact("dup_test"))

        with pytest.raises(ValueError, match="already exists"):
            registry.register(_make_artifact("dup_test"))

# ---------------------------------------------------------------------------
# Relevance signals
# ---------------------------------------------------------------------------

class TestRelevanceSignals:
    """Relevance signal CRUD."""

    def test_upsert_signal(self, registry):
        signal = RelevanceSignal(
            signal_type="routing_failure",
            pattern="test_hash_123",
            count=5,
            confidence=0.8,
        )
        signal_id = registry.upsert_signal(signal)
        assert signal_id  # Non-empty

    def test_upsert_same_signal_updates(self, registry):
        signal = RelevanceSignal(
            signal_type="routing_failure",
            pattern="update_test",
            count=3,
            confidence=0.5,
        )
        id1 = registry.upsert_signal(signal)

        signal2 = RelevanceSignal(
            signal_type="routing_failure",
            pattern="update_test",
            count=7,
            confidence=0.9,
        )
        id2 = registry.upsert_signal(signal2)

        # Same signal_type+pattern should reuse same ID
        assert id1 == id2

        # Should have updated count/confidence
        signals = registry.get_signals(signal_type="routing_failure")
        matching = [s for s in signals if s["pattern"] == "update_test"]
        assert len(matching) == 1
        assert matching[0]["count"] == 7

    def test_list_open_signals(self, registry):
        signal = RelevanceSignal(
            signal_type="escalation",
            pattern="test_open",
            count=2,
            confidence=0.6,
        )
        registry.upsert_signal(signal)

        open_signals = registry.list_open_signals()
        assert len(open_signals) >= 1

    def test_resolve_signal(self, registry):
        artifact = _make_artifact("resolve_target")
        registry.register(artifact)

        signal = RelevanceSignal(
            signal_type="routing_failure",
            pattern="resolve_test",
            count=4,
            confidence=0.7,
        )
        signal_id = registry.upsert_signal(signal)

        registry.resolve_signal(signal_id, artifact.id)

        # Should no longer be in open signals
        open_signals = registry.list_open_signals()
        resolved_patterns = [s["pattern"] for s in open_signals]
        assert "resolve_test" not in resolved_patterns

# ---------------------------------------------------------------------------
# Escalation history
# ---------------------------------------------------------------------------

class TestEscalationHistory:
    """Escalation recording and querying."""

    def test_record_escalation(self, registry):
        esc_id = registry.record_escalation(
            action_type="factory_create_agent",
            description="User wants a websearch agent",
            conversation_id="conv-123",
            suggested_name="websearch_agent",
        )
        assert esc_id  # Non-empty

    def test_get_escalation_history(self, registry):
        registry.record_escalation(
            action_type="factory_create_tool",
            description="Test",
            conversation_id="conv-456",
        )
        history = registry.get_escalation_history(since_hours=1)
        assert len(history) >= 1
        assert history[0]["action_type"] == "factory_create_tool"

# ---------------------------------------------------------------------------
# Suggestion log (rate limiting)
# ---------------------------------------------------------------------------

class TestSuggestionLog:
    """Suggestion recording and counting."""

    def test_record_suggestion(self, registry):
        sug_id = registry.record_suggestion(
            category="routing_gap",
            status="pending",
            session_id="sess-001",
        )
        assert sug_id  # Non-empty

    def test_count_suggestions(self, registry):
        registry.record_suggestion("cat_a", "pending", "sess-001")
        registry.record_suggestion("cat_a", "pending", "sess-001")
        registry.record_suggestion("cat_b", "pending", "sess-001")

        assert registry.count_suggestions() == 3
        assert registry.count_suggestions(category="cat_a") == 2
        assert registry.count_suggestions(session_id="sess-001") == 3

    def test_last_rejection(self, registry):
        """No rejections returns None."""
        result = registry.last_rejection("test_category")
        assert result is None

    def test_last_rejection_after_recording(self, registry):
        registry.record_suggestion("rej_cat", "rejected", "sess-001")
        result = registry.last_rejection("rej_cat")
        assert result is not None
        assert isinstance(result, datetime)

    def test_last_artifact_creation_empty(self, registry):
        """No artifacts returns None."""
        result = registry.last_artifact_creation()
        assert result is None

    def test_last_artifact_creation_after_register(self, registry):
        registry.register(_make_artifact("creation_time_test"))
        result = registry.last_artifact_creation()
        assert result is not None
        assert isinstance(result, datetime)

# ---------------------------------------------------------------------------
# Update artifact fields
# ---------------------------------------------------------------------------

class TestUpdateArtifact:
    """update_artifact with version field support."""

    def test_update_version(self, registry):
        """Version field can be updated (needed for update/rollback pipelines)."""
        artifact = _make_artifact("version_update_test")
        registry.register(artifact)

        registry.update_artifact("version_update_test", version=2)
        found = registry.get("version_update_test")
        assert found.version == 2

    def test_update_disallowed_field_raises(self, registry):
        artifact = _make_artifact("disallowed_test")
        registry.register(artifact)

        with pytest.raises(ValueError):
            registry.update_artifact("disallowed_test", created_by="hacker")
