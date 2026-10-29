"""Authenticated, stateless ASGI adapter for Vercel Python Functions.

Root app.py explicitly imports this entrypoint, so server.py stays available
for Render without triggering its SQLite startup side effects on Vercel.
"""
from __future__ import annotations

import hmac
import json
import os

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


async def app(scope, receive, send):
    if scope["type"] == "lifespan":
        if _mcp_app is None:
            await _empty_lifespan(receive, send)
        else:
            await _mcp_app(scope, receive, send)
        return
    if scope["type"] != "http":
        return
    path = scope.get("path", "")
    if path in ("/healthz", "/api/healthz"):
        configured = not bool(_MISSING)
        await _send_json(send, 200 if configured else 503, {"ok": configured, "configured": configured})
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

    mcp_scope = dict(scope)
    mcp_scope["path"] = "/mcp"
    mcp_scope["raw_path"] = b"/mcp"
    await _mcp_app(mcp_scope, receive, send)
