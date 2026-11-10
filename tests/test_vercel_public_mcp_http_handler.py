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
