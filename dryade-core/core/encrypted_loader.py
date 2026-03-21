"""DEPRECATED: Import from core.ee instead.

This module exists only for backward compatibility.
Will be removed in v1.1.

Memory-only .dryadepkg loading requires a Dryade subscription.
See https://dryade.ai/pricing for details.
"""

from __future__ import annotations

import types
import warnings
from pathlib import Path
from typing import Any

warnings.warn(
    "Importing from core.encrypted_loader is deprecated. Use core.ee.encrypted_loader instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export from enterprise edition for backward compat
try:
    from core.ee.encrypted_loader import (  # noqa: F401
        MemoryModuleLoader,
        SecurityError,
        decrypt_and_extract_payload,
        load_encrypted_plugin,
        load_so_from_memory,
    )
except ImportError:
    # Community edition stubs

    class SecurityError(Exception):
        """Raised on signature verification failure."""

    class MemoryModuleLoader:
        """In-memory module loader. Requires Dryade subscription."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise NotImplementedError(
                "In-memory plugin loading requires a Dryade subscription. "
                "See https://dryade.ai/pricing"
            )

    def load_encrypted_plugin(
        pkg_path: Path,
        encryption_key: bytes,
        author_public_key: object | None = None,
    ) -> types.ModuleType:
        """Load encrypted .dryadepkg plugin. Requires Dryade subscription."""
        raise NotImplementedError(
            "Loading encrypted plugins requires a Dryade subscription. "
            "See https://dryade.ai/pricing"
        )

    def decrypt_and_extract_payload(
        pkg_bytes: bytes,
        encryption_key: bytes,
    ) -> dict[str, bytes]:
        """Decrypt .dryadepkg payload. Requires Dryade subscription."""
        raise NotImplementedError(
            "Decrypting plugin packages requires a Dryade subscription. "
            "See https://dryade.ai/pricing"
        )

    def load_so_from_memory(so_bytes: bytes, module_name: str) -> types.ModuleType:
        """Load .so from memory. Requires Dryade subscription."""
        raise NotImplementedError(
            "In-memory module loading requires a Dryade subscription. See https://dryade.ai/pricing"
        )
