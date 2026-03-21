"""Orchestration context with scoped state, artifact storage, and history.

Provides OrchestrationContext as the structured replacement for ad-hoc
``context: dict[str, Any]`` passed through the orchestrator.  Features:

- Two-scope state: orchestration (persistent) and step (cleared per step).
- ArtifactStore: small artifacts in memory, large artifacts (>1 MB) on disk.
- ObservationHistory integration (imported from observation.py, NOT duplicated).
- ExecutionPlan tracking.

Design reference: 81-03-DESIGN Section 2.2 (OrchestrationContext).
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel

from core.orchestrator.observation import ObservationHistory

if TYPE_CHECKING:
    from core.orchestrator.models import ExecutionPlan, OrchestrationObservation

__all__ = ["OrchestrationContext", "ArtifactStore", "Artifact"]

# ---------------------------------------------------------------------------
# Artifact model and store
# ---------------------------------------------------------------------------

MAX_MEMORY_BYTES: int = 1_048_576  # 1 MB threshold

class Artifact(BaseModel):
    """A named artifact produced by an agent during orchestration."""

    name: str
    mime_type: str
    producer: str
    size_bytes: int
    path: Path | None = None
    data: bytes | None = None

    model_config = {"arbitrary_types_allowed": True}

class ArtifactStore:
    """Store for inter-agent artifact passing.

    Small artifacts (<=1 MB) are kept in memory.  Large artifacts are
    written to a temporary directory on disk and referenced by path.
    """

    def __init__(self, temp_dir: Path | None = None) -> None:
        self._artifacts: dict[str, Artifact] = {}
        if temp_dir is not None:
            self._temp_dir = temp_dir
            self._owns_temp_dir = False
        else:
            self._temp_dir = Path(tempfile.mkdtemp(prefix="dryade-artifacts-"))
            self._owns_temp_dir = True

    # -- public API --------------------------------------------------------

    def add(
        self,
        name: str,
        data: bytes,
        mime_type: str,
        producer: str,
    ) -> Artifact:
        """Store an artifact, choosing memory or disk based on size."""
        size = len(data)

        if size > MAX_MEMORY_BYTES:
            # Large artifact -> write to disk
            dest = self._temp_dir / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            artifact = Artifact(
                name=name,
                mime_type=mime_type,
                producer=producer,
                size_bytes=size,
                path=dest,
                data=None,
            )
        else:
            # Small artifact -> keep in memory
            artifact = Artifact(
                name=name,
                mime_type=mime_type,
                producer=producer,
                size_bytes=size,
                path=None,
                data=data,
            )

        self._artifacts[name] = artifact
        return artifact

    def get(self, name: str) -> Artifact | None:
        """Look up an artifact by name."""
        return self._artifacts.get(name)

    def get_data(self, name: str) -> bytes | None:
        """Return the raw bytes of an artifact (memory or disk)."""
        artifact = self._artifacts.get(name)
        if artifact is None:
            return None
        if artifact.data is not None:
            return artifact.data
        if artifact.path is not None:
            return artifact.path.read_bytes()
        return None

    def list_artifacts(self) -> list[str]:
        """Return names of all stored artifacts."""
        return list(self._artifacts.keys())

    def cleanup(self) -> None:
        """Remove the temporary directory and all disk-backed artifacts."""
        if self._owns_temp_dir and self._temp_dir.exists():
            shutil.rmtree(self._temp_dir, ignore_errors=True)

# ---------------------------------------------------------------------------
# Orchestration context
# ---------------------------------------------------------------------------

class OrchestrationContext:
    """Structured context for orchestration with scoped state.

    Replaces the ad-hoc ``context: dict[str, Any]`` with two-scope state
    management (orchestration-level persistent state and step-level
    ephemeral state), artifact storage, observation history integration,
    and execution plan tracking.

    State lookup order: step scope is checked first, then orchestration
    scope.  ``clear_step_scope()`` removes only step-scoped entries.
    """

    def __init__(
        self,
        initial_state: dict[str, Any] | None = None,
    ) -> None:
        self._state: dict[str, Any] = initial_state or {}
        self._step_context: dict[str, Any] = {}
        self._artifacts = ArtifactStore()
        self._history = ObservationHistory()
        self._plan: ExecutionPlan | None = None

    # -- state access ------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value, checking step scope first then orchestration scope."""
        if key in self._step_context:
            return self._step_context[key]
        return self._state.get(key, default)

    def set(
        self,
        key: str,
        value: Any,
        scope: Literal["orchestration", "step"] = "orchestration",
    ) -> None:
        """Set a value in the specified scope."""
        if scope == "step":
            self._step_context[key] = value
        else:
            self._state[key] = value

    def clear_step_scope(self) -> None:
        """Clear all step-scoped state without affecting orchestration state."""
        self._step_context.clear()

    # -- artifacts ---------------------------------------------------------

    def add_artifact(
        self,
        name: str,
        data: bytes,
        mime_type: str,
        producer: str,
    ) -> Artifact:
        """Store an artifact via the internal ArtifactStore."""
        return self._artifacts.add(name, data, mime_type, producer)

    def get_artifact(self, name: str) -> Artifact | None:
        """Look up an artifact by name."""
        return self._artifacts.get(name)

    def get_artifact_data(self, name: str) -> bytes | None:
        """Return the raw bytes of an artifact."""
        return self._artifacts.get_data(name)

    # -- observation history -----------------------------------------------

    def add_observation(self, obs: OrchestrationObservation) -> None:
        """Add an observation to the history."""
        self._history.add(obs)

    def get_observations(self) -> list[OrchestrationObservation]:
        """Return all observations in chronological order."""
        return self._history.get_all_observations()

    def format_history_for_llm(self, max_tokens: int = 2000) -> str:
        """Format observation history as structured XML for LLM injection."""
        return self._history.format_for_llm(max_tokens=max_tokens)

    def get_facts(self) -> list[str]:
        """Return accumulated facts from observation history."""
        return self._history.get_facts()

    # -- plan tracking -----------------------------------------------------

    def set_plan(self, plan: ExecutionPlan) -> None:
        """Attach an execution plan to this context."""
        self._plan = plan

    def get_plan(self) -> ExecutionPlan | None:
        """Return the current execution plan, if any."""
        return self._plan

    # -- serialization -----------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Produce a JSON-serializable representation of the context."""
        merged = {**self._state, **self._step_context}
        merged["artifacts"] = self._artifacts.list_artifacts()
        merged["facts"] = self._history.get_facts()
        return merged

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OrchestrationContext:
        """Create an OrchestrationContext from a plain dictionary."""
        return cls(initial_state=data)

    def cleanup(self) -> None:
        """Release resources (temp directory for disk-backed artifacts)."""
        self._artifacts.cleanup()
