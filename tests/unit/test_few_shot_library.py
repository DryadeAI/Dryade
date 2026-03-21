"""Tests for core.orchestrator.few_shot_library -- Phase 115.4.

Covers example retrieval, formatting, category filtering, and singleton.
"""

from core.orchestrator.few_shot_library import (
    FewShotExample,
    FewShotLibrary,
    get_few_shot_library,
)

class TestGetExamples:
    def test_get_all_examples(self):
        lib = FewShotLibrary()
        examples = lib.get_examples(limit=100)
        assert len(examples) > 0
        assert all(isinstance(e, FewShotExample) for e in examples)

    def test_filter_by_category(self):
        lib = FewShotLibrary()
        examples = lib.get_examples(category="agent_creation", limit=100)
        assert len(examples) > 0
        assert all(e.category == "agent_creation" for e in examples)

    def test_limit(self):
        lib = FewShotLibrary()
        examples = lib.get_examples(limit=2)
        assert len(examples) <= 2

    def test_curated_minimum(self):
        """At least 8 curated examples should exist."""
        lib = FewShotLibrary()
        examples = lib.get_examples(limit=100)
        assert len(examples) >= 8

class TestFormat:
    def test_format_xml(self):
        lib = FewShotLibrary()
        examples = lib.get_examples(limit=2)
        xml = lib.format_for_prompt(examples)
        assert "<routing_examples>" in xml
        assert "</routing_examples>" in xml
        assert "<example>" in xml
        assert "<user>" in xml
        assert "<tool>" in xml
        assert "<arguments>" in xml

    def test_format_empty(self):
        lib = FewShotLibrary()
        result = lib.format_for_prompt([])
        assert result == ""

class TestAddFromMetric:
    def test_add_from_metric(self):
        lib = FewShotLibrary()
        initial_count = len(lib.get_examples(limit=100))
        lib.add_from_metric(
            user_message="Deploy my app",
            tool_called="deploy_tool",
            arguments={"target": "prod"},
            category="deployment",
        )
        new_count = len(lib.get_examples(limit=100))
        assert new_count == initial_count + 1

        # Verify the new example is retrievable
        deployment_examples = lib.get_examples(category="deployment", limit=100)
        assert len(deployment_examples) == 1
        assert deployment_examples[0].user_message == "Deploy my app"

class TestSingleton:
    def test_singleton(self):
        # Reset singleton for test isolation
        import core.orchestrator.few_shot_library as mod

        mod._few_shot_library = None
        l1 = get_few_shot_library()
        l2 = get_few_shot_library()
        assert l1 is l2
