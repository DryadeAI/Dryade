"""DEPRECATED: Import from core.ee instead.

This module exists only for backward compatibility.
Will be removed in v1.1.

Encrypted plugin bridge (route obfuscation, response encryption)
requires a Dryade subscription.
See https://dryade.ai/pricing for details.
"""

from __future__ import annotations

import warnings
from typing import Any

warnings.warn(
    "Importing from core.encrypted_bridge is deprecated. Use core.ee.encrypted_bridge instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export from enterprise edition for backward compat
try:
    from core.ee.encrypted_bridge import (  # noqa: F401
        EncryptedPluginBridge,
        RouteNotFoundError,
        decrypt_response,
        derive_session_key,
        encrypt_response,
        encrypt_route_path,
    )
except ImportError:
    # Community edition stubs

    class RouteNotFoundError(Exception):
        """Raised when an encrypted route token cannot be resolved."""

    class EncryptedPluginBridge:
        """Encrypted plugin bridge. Requires Dryade subscription."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise NotImplementedError(
                "Encrypted plugin bridge requires a Dryade subscription. "
                "See https://dryade.ai/pricing"
            )

    def encrypt_route_path(original_path: str, bridge_key: bytes) -> str:
        """Compute HMAC route token. Requires Dryade subscription."""
        raise NotImplementedError(
            "Route encryption requires a Dryade subscription. See https://dryade.ai/pricing"
        )

    def encrypt_response(response_bytes: bytes, session_key: bytes) -> bytes:
        """Encrypt response body. Requires Dryade subscription."""
        raise NotImplementedError(
            "Response encryption requires a Dryade subscription. See https://dryade.ai/pricing"
        )

    def decrypt_response(encrypted_bytes: bytes, session_key: bytes) -> bytes:
        """Decrypt response body. Requires Dryade subscription."""
        raise NotImplementedError(
            "Response decryption requires a Dryade subscription. See https://dryade.ai/pricing"
        )

    def derive_session_key(jwt_sub: str, jwt_exp: int, server_secret: bytes) -> bytes:
        """Derive session key. Requires Dryade subscription."""
        raise NotImplementedError(
            "Session key derivation requires a Dryade subscription. See https://dryade.ai/pricing"
        )
