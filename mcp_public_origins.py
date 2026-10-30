"""Opt-in browser client origins for public, stateless MCP only.

No wildcard: callers must configure MCP_PUBLIC_ALLOWED_ORIGINS explicitly.
Native/desktop/CLI clients do not send an Origin header and need no setting.
"""
from __future__ import annotations

import os
import re
from urllib.parse import urlsplit


_DOMAIN = re.compile(r"^[a-z0-9][a-z0-9.-]*$")


def allowed_public_origins() -> list[str]:
    result = set()
    for raw in os.environ.get("MCP_PUBLIC_ALLOWED_ORIGINS", "").split(","):
        raw = raw.strip().lower()
        if not raw or raw in ("*", "null"):
            continue
        parsed = urlsplit(raw)
        host = parsed.hostname or ""
        if parsed.username or parsed.password or parsed.path not in ("", "/"):
            continue
        if parsed.query or parsed.fragment or not _DOMAIN.fullmatch(host):
            continue
        is_loopback = host in ("localhost", "127.0.0.1")
        if parsed.scheme != "https" and not (parsed.scheme == "http" and is_loopback):
            continue
        try:
            port = parsed.port
        except ValueError:
            continue
        normal = f"{parsed.scheme}://{host}" + (f":{port}" if port else "")
        if raw == normal or raw == normal + "/":
            result.add(normal)
    return sorted(result)
