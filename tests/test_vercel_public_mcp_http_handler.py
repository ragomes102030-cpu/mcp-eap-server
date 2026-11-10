import json
import threading
from http.server import HTTPServer
from urllib.request import Request, urlopen
from types import SimpleNamespace

from api.public_mcp import handler


def test_direct_vercel_handler_sets_content_length_and_never_sets_chunked_transfer():
    sent_headers = []
    written = []
    response = SimpleNamespace(
        headers={}, command="POST", close_connection=False,
        send_response=lambda status: setattr(response, "status", status),
        send_header=lambda key, value: sent_headers.append((key, value)),
        end_headers=lambda: None,
        wfile=SimpleNamespace(write=written.append),
    )

    handler._reply(response, 200, b'{"ok":true}', [
        ("content-length", "999"),
        ("content-type", "application/json"),
        ("transfer-encoding", "chunked"),
    ])

    headers = {key.lower(): value for key, value in sent_headers}
    assert response.status == 200
    assert headers["content-length"] == "11"
    assert "transfer-encoding" not in headers
    assert headers["connection"] == "close"
    assert written == [b'{"ok":true}']


def test_modern_mcp_reply_is_a_valid_complete_chunked_http_response():
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        payload = {
            "jsonrpc": "2.0", "id": 1, "method": "server/discover",
            "params": {"_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28"}},
        }
        request = Request(
            f"http://127.0.0.1:{server.server_port}/public-mcp",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json",
                     "Accept": "application/json, text/event-stream",
                     "MCP-Protocol-Version": "2026-07-28",
                     "Mcp-Method": "server/discover"},
            method="POST",
        )
        with urlopen(request, timeout=10) as response:
            result = json.loads(response.read())
            assert response.status == 200
            assert response.headers.get("Transfer-Encoding") == "chunked"
        assert "2026-07-28" in result["result"]["supportedVersions"]
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
