"""Vercel's stateless ASGI endpoint; never expose mutating tools without auth.

The publicly advertised path is /mcp (rewritten internally to /api/index).
This adapter does not alter local/Render startup behavior.
"""
from __future__ import annotations

import hmac
import json
import os

_REQUIRED_DB = ("TURSO_URL", "TURSO_TOKEN")
_MISSING = [key for key in ("MCP_API_TOKEN", *_REQUIRED_DB) if not os.getenv(key)]
_mcp_app = None
if not _MISSING:
    from server import app as _mcp_app


async def _reply(send, status: int, message: str, *, challenge: bool = False) -> None:
    body = json.dumps({"ok": False, "error": message}).encode("utf-8")
    headers = [(b"content-type", b"application/json"), (b"cache-control", b"no-store")]
    if challenge:
        headers.append((b"www-authenticate", b'Bearer realm="mcp"'))
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


async def app(scope, receive, send):
    """Reject unconfigured or unauthenticated requests before running MCP."""
    if scope["type"] != "http":
        if _mcp_app is not None:
            await _mcp_app(scope, receive, send)
        return
    if _MISSING:
        await _reply(send, 503, "MCP configuration incomplete")
        return
    headers = {key.lower(): val for key, val in scope.get("headers", [])}
    provided = headers.get(b"authorization", b"")
    expected = ("Bearer " + os.environ["MCP_API_TOKEN"]).encode("utf-8")
    if not hmac.compare_digest(provided, expected):
        await _reply(send, 401, "Authentication required", challenge=True)
        return
    # Rewrites may expose either /mcp or /api/index in the ASGI scope.
    mcp_scope = dict(scope)
    mcp_scope["path"] = "/mcp"
    mcp_scope["raw_path"] = b"/mcp"
    await _mcp_app(mcp_scope, receive, send)
