"""ASGI response framing helpers for serverless HTTP adapters."""


def buffer_json_response(send):
    """Buffer a JSON response and emit a single body with Content-Length.

    Vercel's ASGI adapter has emitted raw JSON bytes while advertising chunked
    transfer encoding for modern MCP responses. The stateless public MCP uses
    JSON responses only; streaming GETs are rejected by the route adapter.
    """
    response_start = None
    body_parts = []

    async def send_buffered(message):
        nonlocal response_start
        if message["type"] == "http.response.start":
            response_start = dict(message)
            return
        if message["type"] == "http.response.body":
            body_parts.append(message.get("body", b""))
            if message.get("more_body", False):
                return
            if response_start is None:
                raise RuntimeError("MCP public response body started before headers")
            headers = [
                (key, value)
                for key, value in response_start.get("headers", [])
                if key.lower() not in (b"content-length", b"transfer-encoding")
            ]
            body = b"".join(body_parts)
            headers.append((b"content-length", str(len(body)).encode("ascii")))
            headers.append((b"x-public-mcp-framing", b"buffered-v1"))
            await send(dict(response_start, headers=headers))
            # Vercel's ASGI bridge requires an explicit terminal marker. The
            # ASGI default is false, but omitting it leaves modern JSON replies
            # advertised as chunked without a terminating chunk on Vercel.
            await send({"type": "http.response.body", "body": body, "more_body": False})
            body_parts.clear()
            response_start = None
            return
        await send(message)

    return send_buffered
