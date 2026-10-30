"""Authenticated, stateless ASGI adapter for Vercel Python Functions.

Root app.py explicitly imports this entrypoint, so server.py stays available
for Render without triggering its SQLite startup side effects on Vercel.
"""
from __future__ import annotations

import hmac
import json
import os
from contextlib import AsyncExitStack

from public_mcp import public_app as _public_app

# Vercel Marketplace Turso provides different names from the legacy Render setup.
if os.environ.get("VERCEL") == "1":
    if not os.environ.get("TURSO_URL") and os.environ.get("TURSO_DATABASE_URL"):
        os.environ["TURSO_URL"] = os.environ["TURSO_DATABASE_URL"]
    if not os.environ.get("TURSO_TOKEN") and os.environ.get("TURSO_AUTH_TOKEN"):
        os.environ["TURSO_TOKEN"] = os.environ["TURSO_AUTH_TOKEN"]

_REQUIRED_DB = ("TURSO_URL", "TURSO_TOKEN")
_MISSING = [key for key in ("MCP_API_TOKEN", *_REQUIRED_DB) if not os.environ.get(key)]
_mcp_app = None
_internal_lookup = None
if not _MISSING:
    from server import app as _mcp_app, internal_eap_node as _internal_lookup
    from starlette.requests import Request


async def _send_json(send, status, payload, *, challenge=False):
    data = json.dumps(payload).encode("utf-8")
    headers = [(b"content-type", b"application/json"), (b"cache-control", b"no-store")]
    if challenge:
        headers.append((b"www-authenticate", b'Bearer realm="mcp"'))
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": data})


async def _empty_lifespan(receive, send):
    while True:
        event = await receive()
        if event["type"] == "lifespan.startup":
            await send({"type": "lifespan.startup.complete"})
        elif event["type"] == "lifespan.shutdown":
            await send({"type": "lifespan.shutdown.complete"})
            return


async def _lifespan_both(receive, send):
    """Start the public and private FastMCP session managers independently."""
    event = await receive()
    if event["type"] != "lifespan.startup":
        return
    try:
        async with AsyncExitStack() as stack:
            await stack.enter_async_context(_public_app.router.lifespan_context(_public_app))
            if _mcp_app is not None:
                await stack.enter_async_context(_mcp_app.router.lifespan_context(_mcp_app))
            await send({"type": "lifespan.startup.complete"})
            while True:
                event = await receive()
                if event["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return
    except Exception as exc:
        await send({"type": "lifespan.startup.failed", "message": str(exc)})


async def _reject_unsupported_sse_get(scope, send):
    """GET listener SSE is optional in MCP; serverless must not hold it open."""
    if scope.get("method") != "GET":
        return False
    headers = {key.lower(): val for key, val in scope.get("headers", [])}
    if b"text/event-stream" not in headers.get(b"accept", b""):
        return False
    await send({"type": "http.response.start", "status": 405,
                "headers": [(b"allow", b"POST, OPTIONS"),
                            (b"cache-control", b"no-store")]})
    await send({"type": "http.response.body", "body": b""})
    return True



# Only the stateless anonymous calculation endpoint may be called from a
# browser origin. Private /mcp retains its authentication and no open CORS.
_PUBLIC_CORS = (
    (b"access-control-allow-origin", b"*"),
    (b"access-control-allow-methods", b"POST, GET, HEAD, OPTIONS"),
    (b"access-control-allow-headers",
     b"Accept, Content-Type, MCP-Protocol-Version, Mcp-Method, Mcp-Name, "
     b"Mcp-Session-Id, Last-Event-ID"),
    (b"access-control-expose-headers", b"MCP-Protocol-Version, Mcp-Session-Id"),
    (b"access-control-max-age", b"600"),
)


def _public_cors_sender(send):
    async def send_public(message):
        if message["type"] == "http.response.start":
            message = dict(message, headers=list(message.get("headers", [])) + list(_PUBLIC_CORS))
        await send(message)

    return send_public


async def app(scope, receive, send):
    if scope["type"] == "lifespan":
        await _lifespan_both(receive, send)
        return
    if scope["type"] != "http":
        return
    path = scope.get("path", "")
    if path in ("/healthz", "/api/healthz"):
        configured = not bool(_MISSING)
        await _send_json(send, 200 if configured else 503, {"ok": configured, "configured": configured})
        return
    # Public endpoint has its OWN tools and no access to project storage.
    # Private /mcp and /internal/eap-node still require MCP_API_TOKEN.
    if path.rstrip("/") == "/public-mcp":
        send_public = _public_cors_sender(send)
        # Claude may first probe the URL with an ordinary GET/HEAD before
        # negotiating MCP Streamable HTTP. Such probes need a stable success
        # status; real SSE GET and JSON-RPC POST continue to the MCP transport.
        method = scope.get("method", "GET")
        if method in ("GET", "HEAD") and b"text/event-stream" not in dict(
            (key.lower(), val) for key, val in scope.get("headers", [])
        ).get(b"accept", b""):
            if method == "HEAD":
                await send_public({"type": "http.response.start", "status": 200,
                            "headers": [(b"cache-control", b"no-store")]})
                await send_public({"type": "http.response.body", "body": b""})
            else:
                await _send_json(send_public, 200, {"ok": True,
                    "transport": "streamable-http", "endpoint": "/public-mcp",
                    "auth": "none", "capabilities": "stateless-calculations-only"})
            return
        if method == "OPTIONS":
            await send_public({"type": "http.response.start", "status": 204,
                        "headers": [(b"allow", b"GET, HEAD, POST, OPTIONS"),
                                    (b"cache-control", b"no-store")]})
            await send_public({"type": "http.response.body", "body": b""})
            return
        if await _reject_unsupported_sse_get(scope, send_public):
            return
        public_scope = dict(scope)
        public_scope["path"] = "/mcp"
        public_scope["raw_path"] = b"/mcp"
        await _public_app(public_scope, receive, send_public)
        return
    if path not in ("/mcp", "/api/index", "/internal/eap-node", "/api/internal"):
        await _send_json(send, 404, {"ok": False, "error": "Not found"})
        return
    if _MISSING:
        await _send_json(send, 503, {"ok": False, "error": "MCP configuration incomplete"})
        return
    headers = {key.lower(): val for key, val in scope.get("headers", [])}
    expected = ("Bearer " + os.environ["MCP_API_TOKEN"]).encode("utf-8")
    if not hmac.compare_digest(headers.get(b"authorization", b""), expected):
        await _send_json(send, 401, {"ok": False, "error": "Authentication required"}, challenge=True)
        return

    if path in ("/internal/eap-node", "/api/internal"):
        if scope.get("method") != "GET":
            await _send_json(send, 405, {"ok": False, "error": "Method not allowed"})
            return
        internal_scope = dict(scope)
        internal_scope["path"] = "/internal/eap-node"
        internal_scope["raw_path"] = b"/internal/eap-node"
        response = await _internal_lookup(Request(internal_scope, receive=receive))
        await response(internal_scope, receive, send)
        return

    if await _reject_unsupported_sse_get(scope, send):
        return
    mcp_scope = dict(scope)
    mcp_scope["path"] = "/mcp"
    mcp_scope["raw_path"] = b"/mcp"
    await _mcp_app(mcp_scope, receive, send)
