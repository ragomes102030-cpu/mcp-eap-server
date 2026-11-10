import asyncio
import json

from api.index import app


def test_vercel_routed_api_restores_original_path_before_dispatch():
    messages = []
    scope = {
        "type": "http", "method": "GET", "path": "/api/index",
        "raw_path": b"/api/index",
        "query_string": b"__vercel_original_path=%2Fhealthz",
        "headers": [], "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1", "scheme": "https", "server": ("localhost", 443),
        "client": ("127.0.0.1", 1), "root_path": "",
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    asyncio.run(app(scope, receive, send))
    start = next(message for message in messages if message["type"] == "http.response.start")
    body = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
    assert start["status"] == 503
    assert json.loads(body) == {"ok": False, "configured": False}
