"""DEPRECATED: Import from core.ee instead.

This module exists only for backward compatibility.
Will be removed in v1.1.

The .dryadepkg v2 format library requires a Dryade subscription.
See https://dryade.ai/pricing for details.
"""

from __future__ import annotations

import warnings
from typing import Any

warnings.warn(
    "Importing from core.dryadepkg_format is deprecated. Use core.ee.dryadepkg_format instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export from enterprise edition for backward compat
try:
    from core.ee.dryadepkg_format import (  # noqa: F401
        FORMAT_VERSION,
        MAGIC_CONTENT,
        NONCE_SIZE,
        IntegrityError,
        build_dryadepkg,
        decrypt_dryadepkg_payload,
        read_dryadepkg_manifest,
        verify_dryadepkg,
    )
except ImportError:
    # Community edition stubs
    FORMAT_VERSION = "2.0"
    MAGIC_CONTENT = b"DRYADE_PKG_V1"
    NONCE_SIZE = 12

    class IntegrityError(Exception):
        """Raised when decrypted payload integrity check fails."""

    def build_dryadepkg(*args: Any, **kwargs: Any) -> bytes:
        """Build a .dryadepkg package. Requires Dryade subscription."""
        raise NotImplementedError(
            "Building .dryadepkg packages requires a Dryade subscription. "
            "See https://dryade.ai/pricing"
        )

    def read_dryadepkg_manifest(pkg_bytes: bytes) -> dict[str, Any]:
        """Read manifest from .dryadepkg. Requires Dryade subscription."""
        raise NotImplementedError(
            "Reading .dryadepkg packages requires a Dryade subscription. "
            "See https://dryade.ai/pricing"
        )

    def verify_dryadepkg(*args: Any, **kwargs: Any) -> tuple[bool, bool, bool, bool]:
        """Verify .dryadepkg signatures. Requires Dryade subscription."""
        raise NotImplementedError(
            "Verifying .dryadepkg packages requires a Dryade subscription. "
            "See https://dryade.ai/pricing"
        )

    def decrypt_dryadepkg_payload(pkg_bytes: bytes, encryption_key: bytes) -> bytes:
        """Decrypt .dryadepkg payload. Requires Dryade subscription."""
        raise NotImplementedError(
            "Decrypting .dryadepkg packages requires a Dryade subscription. "
            "See https://dryade.ai/pricing"
        )
