"""Tests for ComplexityEstimator.classify() -- tier classification.

Covers INSTANT, SIMPLE, and COMPLEX tier routing with
agent/tool name matching, action verb guards, and edge cases.
"""

import pytest

from core.adapters.protocol import (
    AgentCapability,
    AgentCard,
    AgentFramework,
)
from core.orchestrator.complexity import ComplexityEstimator
from core.orchestrator.models import Tier

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_agent(
    name: str = "test-agent",
    tools: list[str] | None = None,
) -> AgentCard:
    caps = [AgentCapability(name=t, description=f"{t} tool") for t in (tools or [])]
    return AgentCard(
        name=name,
        description=f"{name} agent",
        version="1.0",
        framework=AgentFramework.MCP,
        capabilities=caps,
    )

FILESYSTEM_AGENT = _make_agent("mcp-filesystem", ["search_files", "list_directory", "read_file"])
GIT_AGENT = _make_agent("mcp-git", ["git_log", "git_status", "git_diff"])
NO_AGENTS: list[AgentCard] = []
AGENTS = [FILESYSTEM_AGENT, GIT_AGENT]

@pytest.fixture
def estimator():
    return ComplexityEstimator()

# ---------------------------------------------------------------------------
# INSTANT tier tests
# ---------------------------------------------------------------------------

class TestInstantTier:
    """INSTANT: greetings, meta-questions, short factual (no agent signals)."""

    @pytest.mark.parametrize(
        "msg",
        [
            "hello",
            "hi",
            "hey",
            "howdy",
            "good morning",
            "good afternoon",
            "good evening",
            "greetings",
            "bonjour",
            "hola",
            "Hello there!",
            "Hi, how are you?",
        ],
    )
    def test_greetings_no_agents(self, estimator, msg):
        d = estimator.classify(msg, NO_AGENTS)
        assert d.tier == Tier.INSTANT, f"'{msg}' should be INSTANT, got {d.tier}: {d.reason}"
        assert d.confidence >= 0.9

    @pytest.mark.parametrize(
        "msg",
        [
            "what can you do?",
            "who are you?",
            "what do you know?",
            "how do you work?",
            "tell me about yourself",
            "what are your capabilities?",
        ],
    )
    def test_meta_questions_no_agents(self, estimator, msg):
        d = estimator.classify(msg, NO_AGENTS)
        assert d.tier == Tier.INSTANT, f"'{msg}' should be INSTANT, got {d.tier}: {d.reason}"
        assert d.confidence >= 0.85

    def test_short_factual_question(self, estimator):
        d = estimator.classify("what is python?", NO_AGENTS)
        assert d.tier == Tier.INSTANT

    def test_greeting_with_agents_present_but_not_mentioned(self, estimator):
        """Agents exist but not mentioned in message -> still INSTANT."""
        d = estimator.classify("hello", AGENTS)
        assert d.tier == Tier.INSTANT

class TestInstantGuards:
    """Pitfall 7: INSTANT must NOT trigger with agent/tool signals or action verbs."""

    def test_greeting_with_agent_name(self, estimator):
        d = estimator.classify("hello mcp-filesystem", AGENTS)
        assert d.tier != Tier.INSTANT, f"Should NOT be INSTANT with agent name: {d.reason}"

    def test_greeting_with_tool_name(self, estimator):
        d = estimator.classify("hi search_files", AGENTS)
        assert d.tier != Tier.INSTANT, f"Should NOT be INSTANT with tool name: {d.reason}"

    def test_greeting_with_action_verb(self, estimator):
        d = estimator.classify("hello can you search for files", NO_AGENTS)
        assert d.tier != Tier.INSTANT, f"Should NOT be INSTANT with action verb: {d.reason}"

    def test_meta_with_action_verb(self, estimator):
        d = estimator.classify("what can you do to list my files", NO_AGENTS)
        # "list" is an action verb
        assert d.tier != Tier.INSTANT

    def test_greeting_followed_by_complex_request(self, estimator):
        d = estimator.classify("hello, first analyze the repo then create a summary", NO_AGENTS)
        # Has action verbs and multi-step signals
        assert d.tier != Tier.INSTANT

# ---------------------------------------------------------------------------
# SIMPLE tier tests
# ---------------------------------------------------------------------------

class TestSimpleTier:
    """SIMPLE: single agent/tool match, short message."""

    def test_agent_and_tool_match(self, estimator):
        d = estimator.classify("use mcp-filesystem search_files", AGENTS)
        assert d.tier == Tier.SIMPLE
        assert d.confidence >= 0.9
        assert d.target_agent is not None
        assert d.target_tool is not None

    def test_agent_name_only(self, estimator):
        d = estimator.classify("ask mcp-filesystem for help", AGENTS)
        assert d.tier == Tier.SIMPLE
        assert d.target_agent is not None

    def test_tool_name_only(self, estimator):
        d = estimator.classify("run search_files in /home", AGENTS)
        assert d.tier == Tier.SIMPLE
        assert d.target_tool == "search_files"
        assert d.target_agent is not None  # resolved from tool

    def test_long_message_with_agent_name_not_simple(self, estimator):
        """Long message (>30 words) should not be SIMPLE even with agent match."""
        long_msg = "mcp-filesystem " + " ".join(["word"] * 35)
        d = estimator.classify(long_msg, AGENTS)
        # 36 words -> should be COMPLEX, not SIMPLE
        assert d.tier == Tier.COMPLEX

# ---------------------------------------------------------------------------
# COMPLEX tier tests
# ---------------------------------------------------------------------------

class TestComplexTier:
    """COMPLEX: multi-step, conditional, no agent match, default fallback."""

    def test_multi_step_message(self, estimator):
        d = estimator.classify(
            "first analyze the repo, then find issues, finally create a plan",
            NO_AGENTS,
        )
        assert d.tier == Tier.COMPLEX
        assert d.sub_mode is not None

    def test_conditional_message(self, estimator):
        d = estimator.classify(
            "if the file exists then update it otherwise create it",
            NO_AGENTS,
        )
        assert d.tier == Tier.COMPLEX

    def test_default_medium_length(self, estimator):
        """Medium-length message with no special signals -> COMPLEX."""
        msg = " ".join(["task"] * 20) + " do something complex here"
        d = estimator.classify(msg, NO_AGENTS)
        assert d.tier == Tier.COMPLEX

    def test_complex_has_sub_mode(self, estimator):
        """COMPLEX decisions should have sub_mode from estimate()."""
        d = estimator.classify("analyze this", NO_AGENTS)
        # "analyze" is an action verb, so not INSTANT
        # No agent match, so not SIMPLE
        # -> COMPLEX with sub_mode from estimate()
        assert d.tier == Tier.COMPLEX
        assert d.sub_mode is not None

# ---------------------------------------------------------------------------
# TierDecision structure tests
# ---------------------------------------------------------------------------

class TestTierDecision:
    def test_instant_has_no_agent(self, estimator):
        d = estimator.classify("hello", NO_AGENTS)
        assert d.target_agent is None
        assert d.target_tool is None
        assert d.sub_mode is None

    def test_simple_has_agent(self, estimator):
        d = estimator.classify("use mcp-filesystem", AGENTS)
        assert d.target_agent is not None

    def test_complex_has_sub_mode(self, estimator):
        d = estimator.classify("analyze this code and create a report", NO_AGENTS)
        assert d.tier == Tier.COMPLEX
        assert d.sub_mode is not None
