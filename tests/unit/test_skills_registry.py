"""
Unit tests for SkillRegistry and SkillSnapshot.

Tests cover:
1. Singleton pattern (get_skill_registry)
2. Skill caching with TTL
3. Cache refresh
4. Change listeners for hot reload
5. Skill snapshots for session consistency
6. Search path management
7. Thread safety

Target: ~80 LOC
"""

import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.skills.models import Skill
from core.skills.registry import (
    SkillRegistry,
    SkillSnapshot,
    get_skill_registry,
    reset_skill_registry,
)

@pytest.fixture(autouse=True)
def reset_global_registry():
    """Reset global registry before and after each test."""
    reset_skill_registry()
    yield
    reset_skill_registry()

@pytest.fixture
def mock_loader():
    """Create a mock skill loader."""
    loader = MagicMock()
    loader.discover_skills.return_value = [
        Skill(
            name="skill-1",
            description="First skill",
            instructions="Do thing one",
            skill_dir="/tmp/skill1",
        ),
        Skill(
            name="skill-2",
            description="Second skill",
            instructions="Do thing two",
            skill_dir="/tmp/skill2",
        ),
    ]
    loader.check_skill_eligibility.return_value = MagicMock(eligible=True)
    return loader

@pytest.fixture
def registry_with_mock_loader(mock_loader):
    """Create a registry with a mocked loader and no MCP tools."""
    registry = SkillRegistry(search_paths=[Path("/tmp")], cache_ttl=10)
    registry._loader = mock_loader
    # Prevent MCP tools from being loaded (isolate from real filesystem)
    registry._load_mcp_tools_as_skills = lambda: 0
    registry._refresh_cache()
    return registry

# =============================================================================
# Test: Singleton Pattern
# =============================================================================

class TestSingleton:
    """Tests for singleton pattern."""

    def test_get_skill_registry_returns_singleton(self):
        """Test that get_skill_registry returns the same instance."""
        registry1 = get_skill_registry()
        registry2 = get_skill_registry()

        assert registry1 is registry2

    def test_reset_skill_registry_clears_singleton(self):
        """Test that reset_skill_registry clears the singleton."""
        registry1 = get_skill_registry()
        reset_skill_registry()
        registry2 = get_skill_registry()

        assert registry1 is not registry2

# =============================================================================
# Test: Skill Caching
# =============================================================================

class TestSkillCaching:
    """Tests for skill caching behavior."""

    def test_get_all_skills_returns_cached(self, registry_with_mock_loader, mock_loader):
        """Test that get_all_skills returns cached skills."""
        mock_loader.discover_skills.reset_mock()

        skills = registry_with_mock_loader.get_all_skills(refresh_if_stale=False)

        assert len(skills) == 2
        # Should not have called discover_skills again
        mock_loader.discover_skills.assert_not_called()

    def test_cache_expires_after_ttl(self, mock_loader):
        """Test that cache expires after TTL."""
        registry = SkillRegistry(search_paths=[Path("/tmp")], cache_ttl=0.1)
        registry._loader = mock_loader
        registry._refresh_cache()

        # Immediately should not be stale
        assert not registry._is_cache_stale()

        # Wait for TTL to expire
        time.sleep(0.15)
        assert registry._is_cache_stale()

    def test_get_all_skills_refreshes_when_stale(self, mock_loader):
        """Test that get_all_skills refreshes when cache is stale."""
        registry = SkillRegistry(search_paths=[Path("/tmp")], cache_ttl=0.1)
        registry._loader = mock_loader
        registry._refresh_cache()

        # Wait for stale
        time.sleep(0.15)
        mock_loader.discover_skills.reset_mock()

        # Should refresh
        registry.get_all_skills(refresh_if_stale=True)

        mock_loader.discover_skills.assert_called_once()

# =============================================================================
# Test: Cache Refresh
# =============================================================================

class TestCacheRefresh:
    """Tests for explicit cache refresh."""

    def test_refresh_reloads_skills(self, registry_with_mock_loader, mock_loader):
        """Test that refresh() reloads skills from disk."""
        mock_loader.discover_skills.reset_mock()

        registry_with_mock_loader.refresh()

        mock_loader.discover_skills.assert_called_once()

    def test_refresh_notifies_listeners(self, registry_with_mock_loader):
        """Test that refresh notifies change listeners."""
        callback = MagicMock()
        registry_with_mock_loader.add_change_listener(callback)

        registry_with_mock_loader.refresh()

        callback.assert_called_once()
        # Should be called with list of skills
        args = callback.call_args[0]
        assert isinstance(args[0], list)

# =============================================================================
# Test: Change Listeners
# =============================================================================

class TestChangeListeners:
    """Tests for change listener management."""

    def test_add_change_listener(self, registry_with_mock_loader):
        """Test adding a change listener."""
        callback = MagicMock()

        registry_with_mock_loader.add_change_listener(callback)

        assert callback in registry_with_mock_loader._listeners

    def test_remove_change_listener(self, registry_with_mock_loader):
        """Test removing a change listener."""
        callback = MagicMock()
        registry_with_mock_loader.add_change_listener(callback)

        registry_with_mock_loader.remove_change_listener(callback)

        assert callback not in registry_with_mock_loader._listeners

    def test_listener_exception_doesnt_break_others(self, registry_with_mock_loader):
        """Test that one listener's exception doesn't affect others."""
        bad_callback = MagicMock(side_effect=RuntimeError("oops"))
        good_callback = MagicMock()

        registry_with_mock_loader.add_change_listener(bad_callback)
        registry_with_mock_loader.add_change_listener(good_callback)

        # Should not raise
        registry_with_mock_loader.refresh()

        # Good callback should still be called
        good_callback.assert_called_once()

# =============================================================================
# Test: Skill Snapshots
# =============================================================================

class TestSkillSnapshots:
    """Tests for session-scoped skill snapshots."""

    def test_create_snapshot(self, registry_with_mock_loader):
        """Test creating a skill snapshot."""
        snapshot = registry_with_mock_loader.create_snapshot(eligible_only=False)

        assert isinstance(snapshot, SkillSnapshot)
        assert len(snapshot) == 2

    def test_snapshot_is_immutable(self, registry_with_mock_loader, mock_loader):
        """Test that snapshot is not affected by registry changes."""
        snapshot = registry_with_mock_loader.create_snapshot(eligible_only=False)

        # Change the registry
        mock_loader.discover_skills.return_value = []
        registry_with_mock_loader.refresh()

        # Snapshot should still have original skills
        assert len(snapshot) == 2

    def test_snapshot_get_by_name(self, registry_with_mock_loader):
        """Test getting skill from snapshot by name."""
        snapshot = registry_with_mock_loader.create_snapshot(eligible_only=False)

        skill = snapshot.get("skill-1")

        assert skill is not None
        assert skill.name == "skill-1"

    def test_snapshot_contains_check(self, registry_with_mock_loader):
        """Test 'in' operator on snapshot."""
        snapshot = registry_with_mock_loader.create_snapshot(eligible_only=False)

        assert "skill-1" in snapshot
        assert "nonexistent" not in snapshot

    def test_snapshot_iteration(self, registry_with_mock_loader):
        """Test iterating over snapshot."""
        snapshot = registry_with_mock_loader.create_snapshot(eligible_only=False)

        skills = list(snapshot)

        assert len(skills) == 2
        assert all(isinstance(s, Skill) for s in skills)

    def test_snapshot_timestamp(self, registry_with_mock_loader):
        """Test that snapshot has creation timestamp."""
        before = time.time()
        snapshot = registry_with_mock_loader.create_snapshot(eligible_only=False)
        after = time.time()

        assert before <= snapshot.timestamp <= after

# =============================================================================
# Test: Search Path Management
# =============================================================================

class TestSearchPaths:
    """Tests for search path management."""

    def test_get_search_paths(self, registry_with_mock_loader):
        """Test getting configured search paths."""
        paths = registry_with_mock_loader.get_search_paths()

        assert len(paths) > 0
        assert all(isinstance(p, Path) for p in paths)

    def test_add_search_path(self, registry_with_mock_loader, mock_loader):
        """Test adding a new search path."""
        new_path = Path("/new/path")
        mock_loader.discover_skills.reset_mock()

        registry_with_mock_loader.add_search_path(new_path)

        assert new_path in registry_with_mock_loader.get_search_paths()
        # Should have refreshed cache
        mock_loader.discover_skills.assert_called()

    def test_add_duplicate_path_ignored(self, registry_with_mock_loader, mock_loader):
        """Test that duplicate paths are not added."""
        existing_path = registry_with_mock_loader.get_search_paths()[0]
        mock_loader.discover_skills.reset_mock()

        registry_with_mock_loader.add_search_path(existing_path)

        # Should not refresh since path already exists
        mock_loader.discover_skills.assert_not_called()

# =============================================================================
# Test: Get Specific Skill
# =============================================================================

class TestGetSkill:
    """Tests for getting specific skills."""

    def test_get_skill_by_name(self, registry_with_mock_loader):
        """Test getting a skill by name."""
        skill = registry_with_mock_loader.get_skill("skill-1")

        assert skill is not None
        assert skill.name == "skill-1"

    def test_get_skill_not_found(self, registry_with_mock_loader):
        """Test getting a nonexistent skill returns None."""
        skill = registry_with_mock_loader.get_skill("nonexistent")

        assert skill is None

# =============================================================================
# Test: Eligible Skills Filter
# =============================================================================

class TestEligibleSkills:
    """Tests for filtering eligible skills."""

    def test_get_eligible_skills(self, registry_with_mock_loader, mock_loader):
        """Test getting only eligible skills."""

        # Make first skill ineligible
        def check_eligibility(skill):
            result = MagicMock()
            result.eligible = skill.name != "skill-1"
            return result

        mock_loader.check_skill_eligibility.side_effect = check_eligibility

        eligible = registry_with_mock_loader.get_eligible_skills()

        assert len(eligible) == 1
        assert eligible[0].name == "skill-2"

# =============================================================================
# Test: Thread Safety
# =============================================================================

class TestThreadSafety:
    """Tests for thread-safe operations."""

    def test_concurrent_access(self, registry_with_mock_loader):
        """Test that concurrent access is safe."""
        results = []
        errors = []

        def access_registry():
            try:
                for _ in range(10):
                    skills = registry_with_mock_loader.get_all_skills()
                    results.append(len(skills))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=access_registry) for _ in range(5)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert all(r == 2 for r in results)
