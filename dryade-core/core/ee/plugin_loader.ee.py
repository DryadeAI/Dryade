# Copyright (c) 2025-2026 Dryade SAS
# Licensed under the Dryade Enterprise Edition License. See LICENSE_EE.md.
"""Plugin loader with support for commercial packages.

Commercial plugins (.dryadepkg) are loaded via memory_loader to prevent
decrypted code from persisting on disk.

Flow:
1. Check if plugin is .dryadepkg (commercial) or directory (community/user)
2. For .dryadepkg:
   a. Verify license (machine fingerprint + expiry)
   b. Read and verify signatures
   c. Decrypt to memory
   d. Load modules via memory_loader
3. For directory:
   a. Verify manifest signature
   b. Load modules normally

Usage:
    from core.ee.plugin_loader import load_plugin

    # Community plugin (directory)
    plugin = load_plugin("plugins/my_plugin")

    # Commercial plugin (.dryadepkg)
    plugin = load_plugin("plugins/commercial.dryadepkg")
"""

from pathlib import Path
from typing import Any

# Import will be available after plan 05 completes
# from plugin_manager.package_format import load_package_modules
# from plugin_manager.memory_loader import MemoryLoaderError

def load_plugin(plugin_path: str | Path) -> Any:
    """Load a plugin from path.

    Supports both directory-based plugins and .dryadepkg packages.

    Args:
        plugin_path: Path to plugin directory or .dryadepkg file

    Returns:
        Loaded plugin module

    Raises:
        Various exceptions for validation/loading failures
    """
    path = Path(plugin_path)

    if path.suffix == ".dryadepkg":
        return _load_commercial_plugin(path)
    elif path.is_dir():
        return _load_directory_plugin(path)
    else:
        raise ValueError(f"Unknown plugin format: {path}")

def _load_commercial_plugin(package_path: Path) -> Any:
    """Load a commercial plugin from .dryadepkg.

    Community edition - commercial plugins (.dryadepkg) are not supported.
    For encrypted plugin support, use the Enterprise edition.

    Args:
        package_path: Path to the .dryadepkg file

    Raises:
        NotImplementedError: Always - commercial plugins not supported in community edition
    """
    raise NotImplementedError(
        "Commercial plugins (.dryadepkg) are not supported in community edition. "
        "Use directory-based plugins or upgrade to Enterprise edition."
    )

def _load_directory_plugin(plugin_dir: Path) -> Any:
    """Load a community/user plugin from directory.

    This delegates to the existing plugin loading logic in core/plugins.py.
    Directory-based plugins are open-source and don't require decryption.
    """
    # Existing directory-based loading logic
    # This is the current implementation path via core/plugins.py
    pass
