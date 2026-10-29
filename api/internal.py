"""Private read-only EAP lookup for the Cronograma MCP on Vercel."""
from __future__ import annotations

import hmac
import json
import os

_REQUIRED = ("MCP_API_TOKEN", "TURSO_URL", "TURSO_TOKEN")
_missing = [name for name in _REQUIRED if not os.getenv(name)]
_lookup = None
if not _missing:
    from server import internal_eap_node as _lookup
    from starlette.requests import Request


async def _send_error(send, status: int, message: str) -> None:
    data = json.dumps({"ok": False, "error": message}).encode("utf-8")
    headers = [(b"content-type", b"application/json"), (b"cache-control", b"no-store")]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": data})


async def app(scope, receive, send):
    if scope["type"] != "http":
        if scope["type"] == "lifespan":
            while True:
                event = await receive()
                if event["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif event["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        return
    if scope.get("method") != "GET":
        await _send_error(send, 405, "Method not allowed")
        return
    if _missing:
        await _send_error(send, 503, "MCP configuration incomplete")
        return
    headers = {key.lower(): val for key, val in scope.get("headers", [])}
    expected = ("Bearer " + os.environ["MCP_API_TOKEN"]).encode("utf-8")
    if not hmac.compare_digest(headers.get(b"authorization", b""), expected):
        await _send_error(send, 401, "Authentication required")
        return
    lookup_scope = dict(scope)
    lookup_scope["path"] = "/internal/eap-node"
    lookup_scope["raw_path"] = b"/internal/eap-node"
    response = await _lookup(Request(lookup_scope, receive=receive))
    await response(lookup_scope, receive, send)
