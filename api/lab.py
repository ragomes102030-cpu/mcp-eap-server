"""Full EAP MCP tools in a throwaway, unauthenticated Vercel laboratory.

SECURITY BOUNDARY:
- This entrypoint is enabled ONLY in the separate public-lab Vercel project.
- Turso credentials are removed before any model modules are imported.
- SQLite is redirected to /tmp, never the Git checkout or real Turso.
- All operations are explicitly demonstrative; data may disappear at any time.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

if os.environ.get("MCP_PUBLIC_LAB") != "1":
    raise RuntimeError("Full public EAP lab requires MCP_PUBLIC_LAB=1 on its own project")

# Clear both legacy and Marketplace names before any database module is imported.
# These are project-level safeguards, not just a 'skip authentication' switch.
for _env_name in ("TURSO_URL", "TURSO_TOKEN", "TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN"):
    os.environ.pop(_env_name, None)

import models
models.DB_PATH = Path("/tmp/arquimedes_public_eap_lab.db")

from server import app as _mcp_app

# Defense-in-depth: no remote Turso client must be initialized by the lab.
from models import db as _database
assert _database._TURSO_URL == "", "Public lab must never connect to Turso"

async def _reply(send, code: int, body: dict, method: str = "GET"):
    value = json.dumps(body).encode("utf-8")
    await send({"type": "http.response.start", "status": code,
                "headers": [(b"content-type", b"application/json"),
                            (b"cache-control", b"no-store"),
                            (b"x-robots-tag", b"noindex, nofollow")]})
    await send({"type": "http.response.body", "body": b"" if method == "HEAD" else value})

async def app(scope, receive, send):
    if scope["type"] == "lifespan":
        await _mcp_app(scope, receive, send)
        return
    if scope["type"] != "http":
        return
    path = scope.get("path", "/")
    method = scope.get("method", "GET")
    if path.rstrip("/") in ("/healthz", "/api/healthz"):
        await _reply(send, 200, {"ok": True, "service": "mcp-eap-lab",
              "authentication": "none", "storage": "temporary-sqlite",
              "real_turso_connected": False, "durability": "none"}, method)
        return
    if path.rstrip("/") not in ("/mcp", "/public-mcp", "/api/index"):
        await _reply(send, 404, {"error": "Route not found"}, method)
        return
    if method in ("GET", "HEAD") and b"text/event-stream" not in dict(
            (key.lower(), val) for key, val in scope.get("headers", [])
    ).get(b"accept", b""):
        await _reply(send, 200, {"ok": True, "endpoint": "/mcp",
              "transport": "streamable-http", "auth": "none",
              "mode": "throwaway-public-lab", "real_turso_connected": False}, method)
        return
    if method == "OPTIONS":
        await send({"type": "http.response.start", "status": 204,
                    "headers": [(b"allow", b"GET, HEAD, POST, OPTIONS")]})
        await send({"type": "http.response.body", "body": b""})
        return
    # Anonymously expose the ORIGINAL complete FastMCP tool registry,
    # using only the isolated /tmp SQLite DB set above.
    public_scope = dict(scope)
    public_scope["path"] = "/mcp"
    public_scope["raw_path"] = b"/mcp"
    await _mcp_app(public_scope, receive, send)
