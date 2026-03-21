"""Dryade Command System.

Slash command infrastructure for chat interface.
"""

from core.commands.protocol import Command
from core.commands.registry import (
    CommandRegistry,
    get_command,
    get_registry,
    list_commands,
    register_command,
    unregister_command,
)

__all__ = [
    "Command",
    "CommandRegistry",
    "get_command",
    "get_registry",
    "list_commands",
    "register_command",
    "unregister_command",
]
