"""Observation history with sliding window summarization.

Keeps a sliding window of recent observations at full detail while
summarizing older observations to one-line summaries.  Extracts
running facts (file paths, agent outcomes, UUIDs) so the LLM retains
key information even as raw observations age out.

Design reference: 81-03-DESIGN Section 6 (Observation Summarization).
"""

import logging
import re
from collections import deque
from typing import Any

from core.orchestrator.config import get_orchestration_config
from core.orchestrator.models import OrchestrationObservation

__all__ = ["ObservationHistory"]

logger = logging.getLogger(__name__)

# Pre-compiled regexes for fact extraction
# Two-phase path matching: quoted paths first (highest confidence), then unquoted
_QUOTED_PATH_RE = re.compile(r'"(/[^"]{5,})"')
_UNQUOTED_PATH_RE = re.compile(r"/[a-zA-Z0-9_. /-]{5,}(?:\.[a-zA-Z0-9]{1,10}|/)")
_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)

class ObservationHistory:
    """Sliding-window observation history for LLM context optimization.

    Maintains:
    - ``RECENT_WINDOW_SIZE`` most recent observations at full detail.
    - One-line summaries for all older observations.
    - A running list of extracted facts (paths, outcomes, UUIDs).

    After 8+ steps the formatted output is at least 40% smaller than
    sending every raw observation truncated to 500 chars.
    """

    def __init__(self) -> None:
        cfg = get_orchestration_config()
        self.RECENT_WINDOW_SIZE = cfg.obs_window_size
        self.SUMMARY_MAX_CHARS = cfg.obs_summary_max_chars
        self.FACTS_MAX_COUNT = cfg.obs_facts_max_count
        self.MAX_OBSERVATIONS = cfg.obs_max_observations
        self._recent: deque[OrchestrationObservation] = deque(maxlen=self.RECENT_WINDOW_SIZE)
        self._older: list[OrchestrationObservation] = []
        self._summaries: list[str] = []
        self._facts: list[str] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add(self, obs: OrchestrationObservation) -> None:
        """Add an observation to the history.

        Extracts facts, evicts the oldest recent observation (if the
        window is full) into the summaries list, and appends *obs* to
        the recent window.
        """
        # Extract facts first (before any eviction)
        new_facts = self._extract_facts(obs)
        self._facts.extend(new_facts)
        # Trim facts to max count, keeping most recent
        if len(self._facts) > self.FACTS_MAX_COUNT:
            self._facts = self._facts[-self.FACTS_MAX_COUNT :]

        # Evict oldest recent observation if window is full
        if len(self._recent) >= self.RECENT_WINDOW_SIZE:
            evicted = self._recent[0]  # will be dropped by deque maxlen
            self._older.append(evicted)
            self._summaries.append(self._summarize_observation(evicted))

        self._recent.append(obs)

        # Cap total observations to prevent unbounded context growth
        total = len(self._older) + len(self._recent)
        if total > self.MAX_OBSERVATIONS:
            self._compress_oldest()

    def format_for_llm(self, max_tokens: int = 2000) -> str:
        """Format the observation history as structured XML for LLM injection.

        Returns XML with three sections:
        - ``<facts>``              -- bullet list of extracted facts
        - ``<recent_observations>`` -- full detail for the recent window
        - ``<history>``            -- one-line summaries of older observations

        When there are no observations at all, returns a short placeholder.
        """
        if not self._recent and not self._summaries:
            return "<observations>No actions taken yet</observations>"

        parts: list[str] = ["<observations>"]

        # Facts section
        parts.append("  <facts>")
        if self._facts:
            for fact in self._facts:
                parts.append(f"    - {fact}")
        else:
            parts.append("    (none yet)")
        parts.append("  </facts>")

        # Recent observations -- full detail
        parts.append("  <recent_observations>")
        for i, obs in enumerate(self._recent, 1):
            status = "success" if obs.success else "failed"
            parts.append(
                f'    <observation step="{len(self._summaries) + i}" '
                f'agent="{obs.agent_name}" status="{status}">'
            )
            parts.append(f"      <task>{obs.task}</task>")
            result_str = str(obs.result)[:300] if obs.result else "None"
            parts.append(f"      <result>{result_str}</result>")
            if obs.error:
                parts.append(f"      <error>{obs.error}</error>")
            parts.append("    </observation>")
        parts.append("  </recent_observations>")

        # History section -- one-line summaries
        parts.append("  <history>")
        if self._summaries:
            for summary in self._summaries:
                parts.append(f"    - {summary}")
        else:
            parts.append("    (no older observations)")
        parts.append("  </history>")

        parts.append("</observations>")
        return "\n".join(parts)

    def get_facts(self) -> list[str]:
        """Return a copy of the accumulated facts list."""
        return list(self._facts)

    def get_all_observations(self) -> list[OrchestrationObservation]:
        """Return all observations (older + recent) in chronological order."""
        return self._older + list(self._recent)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-safe dict for escalation persistence."""
        return {
            "recent": [obs.model_dump(mode="json") for obs in self._recent],
            "older": [obs.model_dump(mode="json") for obs in self._older],
            "summaries": list(self._summaries),
            "facts": list(self._facts),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ObservationHistory":
        """Restore from serialized dict.

        Bypasses add() to preserve exact internal state (no re-extraction
        of facts, no re-summarization).
        """
        history = cls()
        for obs_dict in data.get("older", []):
            history._older.append(OrchestrationObservation(**obs_dict))
        for obs_dict in data.get("recent", []):
            history._recent.append(OrchestrationObservation(**obs_dict))
        history._summaries = data.get("summaries", [])
        history._facts = data.get("facts", [])
        return history

    def context_size_chars(self) -> int:
        """Return the character count of the formatted observation context.

        This is the exact size of the string that gets injected into the LLM
        prompt via ``format_for_llm()``.  Used by context overflow detection
        (85% threshold) in the CONTEXT_REDUCE failure action handler.
        """
        return len(self.format_for_llm())

    def compress_aggressive(self, target_reduction: float = 0.5) -> None:
        """Aggressively compress observation history.

        Reduces the history to approximately ``target_reduction`` of its
        current size by:

        1. Compressing ALL older observations into a single aggregate summary.
        2. Shrinking the recent window to at most 1 entry.
        3. Trimming facts to half (minimum 3).

        This is the core mechanism for the CONTEXT_REDUCE failure action.
        Rule-based only -- NO LLM calls.
        """
        before_size = self.context_size_chars()

        # No-op if fewer than 2 total observations
        total = len(self._older) + len(self._recent)
        if total < 2:
            return

        # Step 1: Compress ALL _older observations into a single aggregate
        if self._older:
            success_count = sum(1 for o in self._older if o.success)
            fail_count = len(self._older) - success_count
            agents = {o.agent_name for o in self._older}
            aggregate = (
                f"[COMPRESSED {len(self._older)} steps] "
                f"{success_count} OK, {fail_count} FAIL, "
                f"agents: {', '.join(sorted(agents))}"
            )
            # Keep summaries that correspond to items still in _recent,
            # plus the new aggregate replacing all older summaries.
            # _summaries has one entry per evicted item; older items are
            # the first len(_older) entries (possibly already aggregated).
            recent_count = len(self._recent)
            # Summaries for recent-window items are at the tail
            recent_summaries = (
                self._summaries[-recent_count:]
                if recent_count and len(self._summaries) >= recent_count
                else []
            )
            self._summaries = [aggregate] + recent_summaries
            self._older.clear()

        # Step 2: Shrink the recent window to 1
        if len(self._recent) > 1:
            # Evict all but the last entry into a summary line
            evicted = list(self._recent)[:-1]
            kept = self._recent[-1]
            success_count = sum(1 for o in evicted if o.success)
            fail_count = len(evicted) - success_count
            agents = {o.agent_name for o in evicted}
            evicted_summary = (
                f"[COMPRESSED {len(evicted)} recent steps] "
                f"{success_count} OK, {fail_count} FAIL, "
                f"agents: {', '.join(sorted(agents))}"
            )
            self._summaries.append(evicted_summary)
            self._recent.clear()
            self._recent.append(kept)

        # Step 3: Trim facts to half (minimum 3)
        if self._facts:
            keep_count = max(len(self._facts) // 2, 3)
            self._facts = self._facts[-keep_count:]

        after_size = self.context_size_chars()
        if before_size > 0:
            reduction_pct = (1 - after_size / before_size) * 100
        else:
            reduction_pct = 0.0
        logger.info(
            "[OBSERVATION] compress_aggressive: %d -> %d chars (%.0f%% reduction)",
            before_size,
            after_size,
            reduction_pct,
        )

    # ------------------------------------------------------------------
    # Internal helpers (rule-based, NO LLM calls)
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_facts(obs: OrchestrationObservation) -> list[str]:
        """Extract key facts from an observation using regex rules.

        Extracts:
        - Unix file paths (up to 3)
        - Agent outcome (success / failure summary)
        - UUIDs (up to 2)
        """
        facts: list[str] = []
        result_str = str(obs.result) if obs.result else ""

        # File paths (cap at 3) -- two-phase: quoted first, then unquoted
        paths_found: list[str] = []
        seen: set[str] = set()
        # Phase 1: quoted paths (highest confidence)
        for m in _QUOTED_PATH_RE.finditer(result_str):
            p = m.group(1).strip()
            if p and p not in seen:
                seen.add(p)
                paths_found.append(p)
        # Phase 2: unquoted paths (strip trailing spaces)
        if len(paths_found) < 3:
            for m in _UNQUOTED_PATH_RE.finditer(result_str):
                p = m.group(0).rstrip()  # strip trailing spaces
                if p and p not in seen:
                    seen.add(p)
                    paths_found.append(p)

        for p in paths_found[:3]:
            # Quote paths containing spaces for LLM clarity
            if " " in p:
                facts.append(f'path: "{p}"')
            else:
                facts.append(f"path: {p}")

        # Agent outcome
        if obs.success:
            task_preview = obs.task[:60] if obs.task else ""
            facts.append(f"{obs.agent_name} completed: {task_preview}")
        else:
            error_preview = (obs.error or "unknown error")[:80]
            facts.append(f"{obs.agent_name} FAILED: {error_preview}")

        # UUIDs (cap at 2)
        uuids = _UUID_RE.findall(result_str)
        for uid in uuids[:2]:
            facts.append(f"uuid: {uid}")

        return facts

    def _compress_oldest(self, batch_size: int = 10) -> None:
        """Compress oldest batch of observations into a single aggregate summary.

        Removes the oldest ``batch_size`` entries from ``_older`` and their
        corresponding summaries from ``_summaries``, then prepends a single
        aggregate summary line to ``_summaries``.

        After compression, ``_summaries`` will be longer than ``_older`` by
        the number of aggregate summaries accumulated. This is safe because
        ``format_for_llm()`` iterates ``_summaries`` independently -- it does
        not index into ``_older``.

        Rule-based only -- NO LLM calls.
        """
        if len(self._older) < batch_size:
            return

        batch = self._older[:batch_size]
        success_count = sum(1 for o in batch if o.success)
        fail_count = len(batch) - success_count
        agents = {o.agent_name for o in batch}
        aggregate = (
            f"[COMPRESSED {len(batch)} steps] "
            f"{success_count} OK, {fail_count} FAIL, "
            f"agents: {', '.join(sorted(agents))}"
        )

        # Remove compressed observations and their summaries
        self._older = self._older[batch_size:]
        self._summaries = [aggregate] + self._summaries[batch_size:]

    def _summarize_observation(self, obs: OrchestrationObservation) -> str:
        """Create a one-line summary of an observation (rule-based).

        Format:
            [agent_name] task_preview -> OK|FAIL: error (result_preview) [Xms]
        """
        task_preview = (obs.task[:40] if obs.task else "?").rstrip()
        if obs.success:
            status_part = "OK"
        else:
            err = (obs.error or "unknown")[:30]
            status_part = f"FAIL: {err}"

        result_preview = (str(obs.result)[:60] if obs.result else "").rstrip()
        summary = (
            f"[{obs.agent_name}] {task_preview} -> {status_part} "
            f"({result_preview}) [{obs.duration_ms}ms]"
        )
        return summary[: self.SUMMARY_MAX_CHARS]
