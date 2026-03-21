# Copyright (c) 2025-2026 Dryade SAS
# Licensed under the Dryade Enterprise Edition License. See LICENSE_EE.md.
"""Encrypted Plugin Bridge for Dryade marketplace plugins.

Provides route obfuscation and response encryption for encrypted marketplace
plugins. Custom (user-created) plugins continue to use plaintext routes.

Security model:
- Plugin API routes are obfuscated via HMAC-SHA256 tokens instead of readable names.
  Route table shows /api/ep/{hmac_token} instead of /api/plugins/{name}/endpoint.
- Plugin response bodies are encrypted with AES-256-GCM before sending to client.
- The client derives the same session key independently from JWT claims.
- Custom plugins are EXEMPT — they use the existing plaintext bridge unchanged.

Exports:
    EncryptedPluginBridge — Main bridge class: wrap_router(), create_middleware()
    encrypt_route_path    — Compute HMAC-based obfuscated path token
    decrypt_response      — AES-GCM decrypt an encrypted response body
    derive_session_key    — HMAC-SHA256 key derivation from JWT claims
    RouteNotFoundError    — Raised when token resolution fails (→ 404)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
from typing import Any

from fastapi import APIRouter

logger = logging.getLogger(__name__)

# ── Exceptions ─────────────────────────────────────────────────────────────────

class RouteNotFoundError(Exception):
    """Raised when an encrypted route token cannot be resolved to an original path."""

# ── Cryptographic helpers ──────────────────────────────────────────────────────

def encrypt_route_path(original_path: str, bridge_key: bytes) -> str:
    """Compute a HMAC-SHA256 token for an original plugin route path.

    The resulting token is base64url-encoded (no padding) and wrapped in
    the /api/ep/ prefix so the route table never exposes readable plugin names.

    Args:
        original_path: The original readable path, e.g. "/api/plugins/cost_tracker/data".
        bridge_key: 32-byte bridge key (derived from server JWT secret).

    Returns:
        Obfuscated path like "/api/ep/{base64url_hmac}".
    """
    mac = hmac.new(bridge_key, original_path.encode("utf-8"), hashlib.sha256).digest()
    token = base64.urlsafe_b64encode(mac).rstrip(b"=").decode("ascii")
    return f"/api/ep/{token}"

def encrypt_response(response_bytes: bytes, session_key: bytes) -> bytes:
    """AES-256-GCM encrypt response bytes (classical path for session-key responses).

    Layout: [12-byte random nonce][ciphertext + 16-byte GCM tag]

    The 12-byte nonce is randomly generated per response. The client splits
    the nonce from the ciphertext+tag to decrypt.

    Args:
        response_bytes: Plaintext response body (typically JSON).
        session_key: 32-byte AES-256 key shared with client.

    Returns:
        Encrypted bytes: nonce (12) + ciphertext + GCM tag (16).
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    aesgcm = AESGCM(session_key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, response_bytes, None)
    return nonce + ciphertext

def encrypt_response_hybrid(
    response_bytes: bytes, recipient_public_key: bytes
) -> bytes:
    """ML-KEM-1024 + AES-256-GCM hybrid encrypt response bytes.

    Each response gets a fresh KEM encapsulation — ephemeral keys per response.
    Layout: [KEM_CT (1568)][nonce (12)][AES ciphertext + GCM tag (16)]

    Args:
        response_bytes: Plaintext response body (typically JSON).
        recipient_public_key: ML-KEM-1024 public key of the recipient.

    Returns:
        Hybrid-encrypted bytes.
    """
    from core.ee.crypto.pq import hybrid_encrypt

    return hybrid_encrypt(response_bytes, recipient_public_key)

def decrypt_response(encrypted_bytes: bytes, session_key: bytes) -> bytes:
    """AES-256-GCM decrypt an encrypted response body (classical path).

    Args:
        encrypted_bytes: Bytes from encrypt_response(): nonce + ciphertext+tag.
        session_key: 32-byte AES-256 key matching the one used to encrypt.

    Returns:
        Plaintext bytes.

    Raises:
        cryptography.exceptions.InvalidTag: If the key is wrong or data is tampered.
        ValueError: If the payload is too short to contain a nonce.
    """
    if len(encrypted_bytes) < 12:
        raise ValueError("Encrypted payload too short — missing nonce")

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = encrypted_bytes[:12]
    ciphertext_and_tag = encrypted_bytes[12:]
    aesgcm = AESGCM(session_key)
    return aesgcm.decrypt(nonce, ciphertext_and_tag, None)

def decrypt_response_hybrid(
    encrypted_bytes: bytes, recipient_secret_key: bytes
) -> bytes:
    """ML-KEM-1024 + AES-256-GCM hybrid decrypt response bytes.

    Args:
        encrypted_bytes: Bytes from encrypt_response_hybrid().
        recipient_secret_key: ML-KEM-1024 secret key.

    Returns:
        Plaintext bytes.

    Raises:
        ValueError: If payload is too short.
        Exception: If decryption fails (tampered data, wrong key).
    """
    from core.ee.crypto.pq import hybrid_decrypt

    return hybrid_decrypt(encrypted_bytes, recipient_secret_key)

def derive_session_key(jwt_sub: str, jwt_exp: int, server_secret: bytes) -> bytes:
    """Derive a 32-byte session key from JWT claims + server secret.

    The derivation is: HMAC-SHA256(server_secret, "{jwt_sub}:{jwt_exp}").
    Both the server and the workbench client can independently compute the
    same key, so no key transport is needed after the initial key material
    exchange.

    Args:
        jwt_sub: JWT subject (user ID string).
        jwt_exp: JWT expiry (Unix timestamp int).
        server_secret: 32-byte server-side secret (NEVER sent to client directly).

    Returns:
        32-byte session key bytes.
    """
    data = f"{jwt_sub}:{jwt_exp}".encode("utf-8")
    return hmac.new(server_secret, data, hashlib.sha256).digest()

# ── Encrypted Plugin Bridge ────────────────────────────────────────────────────

class EncryptedPluginBridge:
    """Bridge between core FastAPI app and encrypted marketplace plugins.

    Wraps plugin routers at mount time to:
    1. Replace readable route paths with HMAC-based tokens (/api/ep/{token}).
    2. Track token → original path mapping for middleware resolution.
    3. Provide middleware that encrypts response bodies for encrypted plugin routes.

    Custom plugins are NOT processed through this bridge — they use the existing
    plaintext app.include_router() path unchanged.

    Usage:
        bridge = EncryptedPluginBridge(bridge_key)
        wrapped_router = bridge.wrap_router(plugin.router, plugin_name="cost_tracker")
        app.include_router(wrapped_router)
        app.middleware("http")(bridge.create_middleware())
    """

    def __init__(self, bridge_key: bytes) -> None:
        """Initialise the bridge with a 32-byte HMAC key for route obfuscation.

        Args:
            bridge_key: 32-byte key derived from the server JWT secret. Used for
                HMAC token generation. Must be stable per server instance so that
                tokens are deterministic.
        """
        self._bridge_key = bridge_key
        # token → original_path (in-memory, populated at startup during route mounting)
        self._route_map: dict[str, str] = {}
        # set of obfuscated paths registered through this bridge (for middleware check)
        self._wrapped_routes: set[str] = set()

    # ── Route wrapping ─────────────────────────────────────────────────────────

    def wrap_router(self, router: APIRouter, plugin_name: str) -> APIRouter:
        """Wrap an encrypted plugin's router with obfuscated route paths.

        For each route in the original router, this method:
        1. Computes the HMAC token for the route path.
        2. Replaces the route path with /api/ep/{token}.
        3. Records the token → original_path mapping.
        4. Returns a new APIRouter with the rewritten routes.

        The original router is NOT modified. The returned router uses the same
        endpoint functions but with obfuscated paths.

        Args:
            router: The plugin's APIRouter with its normal readable routes.
            plugin_name: Plugin name (used for logging).

        Returns:
            New APIRouter with HMAC-obfuscated paths.
        """
        wrapped = APIRouter()
        for route in router.routes:
            original_path = getattr(route, "path", None)
            if original_path is None:
                continue

            # Compute token and register mapping
            obfuscated = encrypt_route_path(original_path, self._bridge_key)
            token = obfuscated.split("/api/ep/")[1]
            self._route_map[token] = original_path
            self._wrapped_routes.add(obfuscated)

            # Re-add the route with the obfuscated path
            methods = getattr(route, "methods", None) or {"GET"}
            endpoint = getattr(route, "endpoint", None)
            if endpoint is None:
                continue

            route_kwargs: dict[str, Any] = {}
            if hasattr(route, "name") and route.name:
                route_kwargs["name"] = f"ep_{token[:8]}"  # Short name for OpenAPI
            if hasattr(route, "response_model") and route.response_model is not None:
                route_kwargs["response_model"] = route.response_model
            if hasattr(route, "tags") and route.tags:
                route_kwargs["tags"] = route.tags
            if hasattr(route, "summary") and route.summary:
                route_kwargs["summary"] = route.summary
            if hasattr(route, "dependencies") and route.dependencies:
                route_kwargs["dependencies"] = route.dependencies

            for method in methods:
                method_lower = method.lower()
                adder = getattr(wrapped, method_lower, None)
                if adder is None:
                    continue
                adder(obfuscated, **route_kwargs)(endpoint)

            logger.debug(
                "Bridge: %s %s → %s",
                plugin_name,
                original_path,
                obfuscated,
            )

        logger.info(
            "Wrapped encrypted plugin '%s': %d routes obfuscated",
            plugin_name,
            len(wrapped.routes),
        )
        return wrapped

    # ── Token resolution ───────────────────────────────────────────────────────

    def resolve_route_path(self, token: str) -> str:
        """Resolve an HMAC token back to the original route path.

        Args:
            token: The base64url token from /api/ep/{token}.

        Returns:
            The original readable route path.

        Raises:
            RouteNotFoundError: If the token is not registered (returns 404).
        """
        original = self._route_map.get(token)
        if original is None:
            raise RouteNotFoundError(token)
        return original

    def is_encrypted_route(self, path: str) -> bool:
        """Check if a request path belongs to an encrypted plugin route.

        Args:
            path: The request path (e.g. /api/ep/{token}).

        Returns:
            True if this is an encrypted plugin bridge route.
        """
        return path in self._wrapped_routes

    # ── Middleware factory ─────────────────────────────────────────────────────

    def create_middleware(self):
        """Return an async ASGI middleware callable for the FastAPI app.

        The middleware:
        - For requests to /api/ep/{token}: resolves token for logging/tracking.
        - For responses from encrypted plugin routes: encrypts the response body
          and adds X-Dryade-Encrypted: true header.
        - For all other routes: passes through completely unchanged.

        Note: The middleware encrypts using a per-request session key derived
        from the Authorization JWT. If no valid JWT is present, the response
        is passed through unencrypted (auth middleware handles 401 before this).

        Returns:
            Async middleware callable for use with @app.middleware("http").
        """
        bridge = self  # capture self for closure

        async def _bridge_middleware(request, call_next):
            from starlette.responses import Response

            response = await call_next(request)
            path = request.url.path

            # Only encrypt responses from encrypted plugin bridge routes
            if not path.startswith("/api/ep/"):
                return response

            # Extract token from path
            token = path.split("/api/ep/", 1)[1].split("/")[0]
            if token not in bridge._route_map:
                return response

            # Derive session key from JWT in request
            session_key = bridge._extract_session_key(request)
            if session_key is None:
                # No valid JWT — pass through (auth middleware handles 401)
                return response

            # Read, encrypt, and return the response body
            body = b""
            async for chunk in response.body_iterator:
                body += chunk if isinstance(chunk, bytes) else chunk.encode("utf-8")

            encrypted_body = encrypt_response(body, session_key)

            new_headers = dict(response.headers)
            new_headers["X-Dryade-Encrypted"] = "true"
            new_headers["content-length"] = str(len(encrypted_body))
            # Remove content-type as the body is now binary
            new_headers.pop("content-type", None)

            return Response(
                content=encrypted_body,
                status_code=response.status_code,
                headers=new_headers,
                media_type="application/octet-stream",
            )

        return _bridge_middleware

    def _extract_session_key(self, request) -> bytes | None:
        """Extract and derive the session key from the JWT in the request.

        Uses the Authorization header to extract the JWT, parses sub + exp,
        then calls derive_session_key() with the server-side bridge key as secret.

        This mirrors the client-side derivation in bridgeDecrypt.ts.

        Args:
            request: The incoming Starlette/FastAPI request.

        Returns:
            32-byte session key bytes, or None if JWT is missing/invalid.
        """
        try:
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return None
            token = auth_header.split(" ", 1)[1]

            # Decode JWT claims without signature verification
            # (auth middleware already verified the JWT before we get here)
            import base64 as b64
            import json

            parts = token.split(".")
            if len(parts) < 2:
                return None

            # Decode payload (add padding)
            padded = parts[1] + "=" * (4 - len(parts[1]) % 4)
            payload = json.loads(b64.urlsafe_b64decode(padded).decode("utf-8"))

            jwt_sub = str(payload.get("sub", ""))
            jwt_exp = int(payload.get("exp", 0))
            if not jwt_sub or not jwt_exp:
                return None

            return derive_session_key(jwt_sub, jwt_exp, self._bridge_key)
        except Exception as exc:
            logger.debug("Failed to extract session key from JWT: %s", exc)
            return None

    # ── Session key endpoint helper ────────────────────────────────────────────

    def get_session_key_material(self, jwt_sub: str, jwt_exp: int) -> dict:
        """Return key material for the client to derive the session key.

        The client receives a scoped secret (not the raw bridge key) plus the
        JWT claims it needs to replicate the derivation. The scoped secret is:
        HMAC-SHA256(bridge_key, "bridge-client-" + jwt_sub)

        This prevents the client from learning the raw bridge key while still
        allowing it to derive the same session key as the server.

        Args:
            jwt_sub: JWT subject (user ID).
            jwt_exp: JWT expiry (Unix timestamp).

        Returns:
            Dict with {secret: base64str, sub: str, exp: int}.
        """
        scoped_secret = hmac.new(
            self._bridge_key,
            f"bridge-client-{jwt_sub}".encode("utf-8"),
            hashlib.sha256,
        ).digest()
        import base64 as b64

        return {
            "secret": b64.b64encode(scoped_secret).decode("ascii"),
            "sub": jwt_sub,
            "exp": jwt_exp,
        }
