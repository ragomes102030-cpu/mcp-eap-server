"""Browser preflight coverage; private MCP must not inherit public CORS."""
from starlette.testclient import TestClient

from api.index import app


def test_public_cors_preflight_and_private_isolation():
    base_url = "https://arquimedes-mcp-eap.vercel.app"
    with TestClient(app, base_url=base_url) as client:
        preflight = client.options("/public-mcp", headers={
            "Origin": "https://independent-client.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers":
                "content-type,mcp-protocol-version,mcp-method,mcp-name",
        })
        assert preflight.status_code == 204, preflight.text[:250]
        assert preflight.headers["access-control-allow-origin"] == "https://independent-client.example"
        headers = preflight.headers["access-control-allow-headers"].lower()
        for name in ("content-type", "mcp-protocol-version", "mcp-method", "mcp-name"):
            assert name in headers

        public_get = client.get("/public-mcp", headers={
            "Accept": "application/json",
            "Origin": "https://independent-client.example",
        })
        assert public_get.status_code == 200
        assert public_get.headers["access-control-allow-origin"] == "https://independent-client.example"

        # MCP POST/call coverage is exercised by the SDK2 dual-protocol suite
        # and by independent Python/TypeScript clients. This CORS case checks
        # preflight and the stateless HTTP response without initiating a session.

        denied = client.options("/public-mcp", headers={
            "Origin": "https://unapproved-browser.example",
            "Access-Control-Request-Method": "POST",
        })
        assert denied.status_code == 403
        assert "access-control-allow-origin" not in denied.headers

        private_probe = client.options("/mcp", headers={
            "Origin": "https://independent-client.example",
            "Access-Control-Request-Method": "POST",
        })
        assert "access-control-allow-origin" not in private_probe.headers

        health = client.get("/healthz", headers={"Origin": "https://independent-client.example"})
        assert "access-control-allow-origin" not in health.headers
