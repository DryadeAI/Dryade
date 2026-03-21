"""Abstract base class for orchestrate-mode tier handlers.

Minimal interface -- no shared logic in base (per research recommendation).
Imports nothing from sibling handler files.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from core.extensions.events import ChatEvent

if TYPE_CHECKING:
    from core.orchestrator.router import ExecutionContext

class OrchestrateHandlerBase(ABC):
    """Abstract base for tier-specific orchestrate handlers.

    Each tier handler (InstantHandler, SimpleHandler, ComplexHandler)
    subclasses this and implements handle().
    """

    @abstractmethod
    async def handle(
        self,
        message: str,
        context: "ExecutionContext",
        stream: bool = True,
    ) -> AsyncGenerator[ChatEvent, None]:
        """Handle a message for this tier.

        Args:
            message: User goal/request.
            context: Execution context with preferences.
            stream: Whether to stream output token-by-token.

        Yields:
            ChatEvent instances for the SSE stream.
        """
        ...  # pragma: no cover
        # Make this a valid async generator
        if False:  # pragma: no cover
            yield  # type: ignore[misc]
