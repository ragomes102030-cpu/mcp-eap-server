"""Strict Host allowlist for MCP SDK v2 / Vercel.

SDK v2 matches allowed_hosts exactly (or base hostname plus :* for port
patterns). "*.vercel.app" is NOT a hostname wildcard and must not be used
as a substitute for explicitly trusted deployment hostnames.
"""
from __future__ import annotations

import os
import re
from urllib.parse import urlsplit


_CUSTOM_HOST = re.compile(r"^[a-z0-9][a-z0-9.-]*(?::\*)?$")
_VERCEL_ENV = (
    "VERCEL_URL",
    "VERCEL_BRANCH_URL",
    "VERCEL_PROJECT_PRODUCTION_URL",
)


def _host(value: str) -> str:
    raw = value.strip().lower()
    if not raw:
        return ""
    parsed = urlsplit(raw if "://" in raw else "//" + raw)
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        return ""
    return parsed.netloc


def allowed_mcp_hosts(canonical: str, render: str) -> list[str]:
    """Accept only service hosts, configured admin hosts, and Vercel-provided aliases.

    This MUST NOT inspect or trust the incoming request Host header.
    """
    allowed = {canonical.lower(), render.lower(), "localhost", "localhost:*",
               "127.0.0.1", "127.0.0.1:*"}

    for key in _VERCEL_ENV:
        host = _host(os.environ.get(key, ""))
        # Vercel-owned env only; no arbitrary domain admitted automatically.
        if host.endswith(".vercel.app") and _CUSTOM_HOST.fullmatch(host):
            allowed.add(host)

    for raw in os.environ.get("MCP_ALLOWED_HOSTS", "").split(","):
        host = _host(raw)
        # Optional explicit operator override for alternate public domains.
        if host and _CUSTOM_HOST.fullmatch(host):
            allowed.add(host)

    return sorted(allowed)
