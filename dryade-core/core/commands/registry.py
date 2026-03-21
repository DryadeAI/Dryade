"""Command Registry - Central registry for slash commands.

Target: ~80 LOC
"""

import difflib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.commands.protocol import Command

class CommandRegistry:
    """Central registry for all slash commands.

    Features:
    - Dynamic command registration
    - Lookup by name
    - List all available commands
    - Fuzzy matching for typo suggestions
    """

    def __init__(self):
        """Initialize an empty command registry."""
        self._commands: dict[str, Command] = {}

    def register(self, command: "Command") -> None:
        """Register a command.

        Args:
            command: Command instance to register
        """
        name = command.get_name()
        self._commands[name] = command

    def unregister(self, name: str) -> None:
        """Unregister a command by name.

        Args:
            name: Command name to unregister
        """
        self._commands.pop(name, None)

    def get(self, name: str) -> "Command | None":
        """Get a command by name.

        Args:
            name: Command name (without "/" prefix)

        Returns:
            Command instance or None if not found
        """
        return self._commands.get(name)

    def list_commands(self) -> list[dict[str, str]]:
        """List all registered commands.

        Returns:
            List of dicts with name and description
        """
        return [
            {"name": cmd.get_name(), "description": cmd.get_description()}
            for cmd in self._commands.values()
        ]

    def suggest_similar(self, name: str, n: int = 3) -> list[str]:
        """Suggest similar command names for typo correction.

        Args:
            name: Mistyped command name
            n: Maximum number of suggestions

        Returns:
            List of similar command names
        """
        command_names = list(self._commands.keys())
        return difflib.get_close_matches(name, command_names, n=n, cutoff=0.6)

    def clear(self) -> None:
        """Clear all registered commands."""
        self._commands.clear()

    def __len__(self) -> int:
        """Return number of registered commands."""
        return len(self._commands)

    def __contains__(self, name: str) -> bool:
        """Check if a command is registered."""
        return name in self._commands

# Global registry instance
_registry: CommandRegistry | None = None

def get_registry() -> CommandRegistry:
    """Get or create global command registry."""
    global _registry
    if _registry is None:
        _registry = CommandRegistry()
    return _registry

def register_command(command: "Command") -> None:
    """Convenience function to register a command."""
    get_registry().register(command)

def get_command(name: str) -> "Command | None":
    """Convenience function to get a command."""
    return get_registry().get(name)

def list_commands() -> list[dict[str, str]]:
    """Convenience function to list all commands."""
    return get_registry().list_commands()

def unregister_command(name: str) -> None:
    """Convenience function to unregister a command."""
    get_registry().unregister(name)
