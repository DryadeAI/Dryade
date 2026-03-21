"""Command Protocol - Abstract base class for slash commands.

Target: ~40 LOC
"""

from abc import ABC, abstractmethod
from typing import Any

class Command(ABC):
    """Abstract base class for slash commands.

    All slash commands must implement this protocol to be registered
    and executed through the command system.
    """

    @abstractmethod
    def get_name(self) -> str:
        """Get the command name (without "/" prefix).

        Returns:
            Command name, e.g., "agent", "flow", "help"
        """
        ...

    @abstractmethod
    def get_description(self) -> str:
        """Get a human-readable description (< 80 chars).

        Returns:
            Brief description of what the command does
        """
        ...

    @abstractmethod
    async def execute(self, args: dict[str, Any], context: dict[str, Any]) -> Any:
        """Execute the command with given arguments and context.

        Args:
            args: Command arguments (varies by command)
            context: Execution context (user_id, conversation_id, etc.)

        Returns:
            Command result (varies by command)

        Raises:
            ValueError: For invalid arguments
            RuntimeError: For execution errors
        """
        ...

    def get_schema(self) -> dict[str, Any] | None:
        """Get JSON schema for argument validation (optional).

        Returns:
            JSON schema dict or None if no validation needed
        """
        return None
