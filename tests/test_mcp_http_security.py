import os
from unittest.mock import patch

from mcp_http_security import allowed_mcp_hosts


def test_host_allowlist_is_exact_and_supports_preview():
    env = {
        "VERCEL_URL": "arquimedes-mcp-abc123-rafael-5864.vercel.app",
        "VERCEL_BRANCH_URL": "arquimedes-mcp-git-feat-9c5.vercel.app",
        "VERCEL_PROJECT_PRODUCTION_URL": "arquimedes-mcp-eap.vercel.app",
        "MCP_ALLOWED_HOSTS": "mcp.example.org, bad/path, invalid_host,https://safe.example.com",
    }
    with patch.dict(os.environ, env, clear=True):
        result = allowed_mcp_hosts("arquimedes-mcp-eap.vercel.app",
                                   "mcp-eap-server.onrender.com")
    assert "arquimedes-mcp-eap.vercel.app" in result
    assert "arquimedes-mcp-abc123-rafael-5864.vercel.app" in result
    assert "arquimedes-mcp-git-feat-9c5.vercel.app" in result
    assert "mcp.example.org" in result
    assert "safe.example.com" in result
    assert "*.vercel.app" not in result
    assert "invalid_host" not in result
    assert "bad" not in result


def test_host_is_never_read_from_inbound_request():
    with patch.dict(os.environ, {"VERCEL_URL": "https://legitimate.vercel.app",
                                 "MCP_ALLOWED_HOSTS": ""}, clear=True):
        assert "attacker.vercel.app" not in allowed_mcp_hosts(
            "canonical.example.org", "render.example.org"
        )
