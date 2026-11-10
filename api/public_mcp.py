"""Direct HTTP handler for the stateless public MCP endpoint on Vercel."""
from __future__ import annotations

import asyncio
import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit

from mcp_public_origins import allowed_public_origins
from public_mcp import create_public_app, public_mcp

_CORS_HEADERS = [
    ("Access-Control-Allow-Methods", "POST, GET, HEAD, OPTIONS"),
    ("Access-Control-Allow-Headers", "Accept, Content-Type, MCP-Protocol-Version, Mcp-Method, Mcp-Name, Mcp-Session-Id, Last-Event-ID"),
    ("Access-Control-Expose-Headers", "MCP-Protocol-Version, Mcp-Session-Id"),
    ("Access-Control-Max-Age", "600"),
    ("Vary", "Origin"),
]


def _asgi_headers(http_headers):
    return [(name.lower().encode("latin-1"), value.encode("latin-1"))
            for name, value in http_headers.items()]


def _run_public_asgi(method, path, query, headers, body, client, server, scheme):
    scope = {
        "type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1", "method": method, "scheme": scheme,
        "path": "/mcp", "raw_path": b"/mcp", "query_string": query,
        "root_path": path, "headers": _asgi_headers(headers),
        "server": server, "client": client,
    }
    received = False
    messages = []
    request_app = create_public_app()

    async def receive():
        nonlocal received
        if received:
            return {"type": "http.disconnect"}
        received = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        messages.append(message)

    async def dispatch():
        async with request_app.router.lifespan_context(request_app):
            await request_app(scope, receive, send)

    asyncio.run(dispatch())
    start = next((m for m in messages if m["type"] == "http.response.start"), None)
    if start is None:
        raise RuntimeError("Public MCP did not start an HTTP response")
    response_body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    response_headers = [(k.decode("latin-1"), v.decode("latin-1"))
                        for k, v in start.get("headers", [])]
    return start["status"], response_body, response_headers


def _dispatch_modern_jsonrpc(request):
    """Handle bounded modern MCP calls synchronously for Vercel's HTTP runtime.

    Vercel's Python streaming adapter emits an unframed body for this POST when
    an asyncio/ASGI response is returned. This path keeps the JSON response
    wholly synchronous and gives the HTTP handler one concrete body to frame.
    """
    request_id = request.get("id")
    method = request.get("method")
    params = request.get("params") or {}
    if not isinstance(params, dict):
        return {"jsonrpc": "2.0", "id": request_id,
                "error": {"code": -32602, "message": "params must be an object"}}

    if method == "server/discover":
        result = {
            "cacheScope": "private",
            "capabilities": {"prompts": {"listChanged": True},
                             "resources": {"listChanged": True, "subscribe": True},
                             "tools": {"listChanged": True}},
            "instructions": ("Modo publico de auditoria EAP. Somente analisa dados fornecidos "
                             "na propria chamada, sem consultar, criar ou alterar projetos no banco. "
                             "Para operacoes persistentes, use o MCP privado autenticado."),
            "resultType": "complete", "supportedVersions": ["2026-07-28"], "ttlMs": 0,
            "_meta": {"io.modelcontextprotocol/serverInfo":
                      {"name": "arquimedes-eap-publico", "version": ""}},
        }
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    if method == "tools/list":
        tools = []
        for tool in public_mcp._tool_manager.list_tools():
            item = {"name": tool.name, "inputSchema": tool.parameters}
            if tool.description:
                item["description"] = tool.description
            if tool.annotations is not None:
                item["annotations"] = tool.annotations.model_dump(exclude_none=True)
            tools.append(item)
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": tools}}

    if method == "tools/call":
        name = params.get("name")
        tool = public_mcp._tool_manager.get_tool(name) if isinstance(name, str) else None
        if tool is None:
            return {"jsonrpc": "2.0", "id": request_id,
                    "error": {"code": -32602, "message": "Unknown tool"}}
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            return {"jsonrpc": "2.0", "id": request_id,
                    "error": {"code": -32602, "message": "arguments must be an object"}}
        try:
            validated = tool.fn_metadata.arg_model.model_validate(arguments)
            result = tool.fn(**validated.model_dump(exclude_none=True))
        except Exception as exc:
            result = {"erro": str(exc), "persistido": False}
            is_error = True
        else:
            is_error = False
        encoded = json.dumps(result, ensure_ascii=False, default=str)
        call_result = {"content": [{"type": "text", "text": encoded}],
                       "structuredContent": result, "isError": is_error}
        return {"jsonrpc": "2.0", "id": request_id, "result": call_result}

    return {"jsonrpc": "2.0", "id": request_id,
            "error": {"code": -32601, "message": "Method not found"}}


class handler(BaseHTTPRequestHandler):
    """Vercel's direct Python HTTP handler, avoiding ASGI/WSGI streaming framing."""
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        if "text/event-stream" in self.headers.get("Accept", ""):
            self._reply(405, b"", [("Allow", "POST, OPTIONS"), ("Cache-Control", "no-store")])
            return
        payload = {"ok": True, "transport": "streamable-http", "endpoint": "/public-mcp",
                   "auth": "none", "capabilities": "stateless-calculations-only"}
        self._reply(200, json.dumps(payload).encode(),
                    [("Content-Type", "application/json"), ("Cache-Control", "no-store")])

    def do_HEAD(self):
        self._reply(200, b"", [("Cache-Control", "no-store")])

    def do_OPTIONS(self):
        self._reply(204, b"", [("Allow", "GET, HEAD, POST, OPTIONS")])

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._reply(400, b"Invalid Content-Length", [("Content-Type", "text/plain")])
            return
        if length < 0:
            self._reply(400, b"Invalid Content-Length", [("Content-Type", "text/plain")])
            return
        body = self.rfile.read(length) if length else b""
        host = self.headers.get("Host", "localhost")
        parsed_host = urlsplit("//" + host)
        scheme = self.headers.get("X-Forwarded-Proto", "https").split(",", 1)[0].strip()
        path, _, query = self.path.partition("?")
        try:
            protocol_version = self.headers.get("MCP-Protocol-Version", "")
            if protocol_version == "2026-07-28":
                request = json.loads(body or b"{}")
                if not isinstance(request, dict):
                    raise ValueError("JSON-RPC request must be an object")
                method_header = self.headers.get("Mcp-Method")
                if method_header and method_header != request.get("method"):
                    raise ValueError("Mcp-Method does not match JSON-RPC method")
                tool_header = self.headers.get("Mcp-Name")
                if tool_header and tool_header != (request.get("params") or {}).get("name"):
                    raise ValueError("Mcp-Name does not match JSON-RPC tool name")
                response = _dispatch_modern_jsonrpc(request)
                self._reply(200, json.dumps(response, ensure_ascii=False).encode(),
                            [("Content-Type", "application/json"), ("Cache-Control", "no-store")],
                            chunked=True)
                return
            status, response_body, response_headers = _run_public_asgi(
                "POST", path, query.encode("latin-1"), self.headers, body,
                self.client_address, (parsed_host.hostname or "localhost", parsed_host.port or 443), scheme,
            )
        except Exception:
            payload = {"error": "Public MCP request failed"}
            self._reply(500, json.dumps(payload).encode(), [("Content-Type", "application/json")])
            return
        self._reply(status, response_body, response_headers)

    def _reply(self, status, body, headers=(), *, chunked=False):
        origin = self.headers.get("Origin", "")
        allowed = allowed_public_origins()
        if origin and origin.lower() not in allowed:
            status = 403
            body = json.dumps({"ok": False, "error": "Origin not allowed"}).encode()
            headers = [("Content-Type", "application/json"), ("Cache-Control", "no-store")]
        response_headers = [(key, value) for key, value in headers
                            if key.lower() not in ("content-length", "transfer-encoding", "connection")]
        if origin and origin.lower() in allowed:
            response_headers.extend(_CORS_HEADERS)
            response_headers.append(("Access-Control-Allow-Origin", origin))
        self.send_response(status)
        for key, value in response_headers:
            self.send_header(key, value)
        if chunked:
            # Vercel's current Python streaming gateway labels this POST as
            # chunked but forwards the handler's body without encoding it.
            # Encode one complete chunk here so its wire response is valid.
            self.send_header("Transfer-Encoding", "chunked")
        else:
            self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        if body and self.command != "HEAD":
            if chunked:
                self.wfile.write(f"{len(body):X}\r\n".encode("ascii") + body + b"\r\n0\r\n\r\n")
            else:
                self.wfile.write(body)
        self.close_connection = True

    def log_message(self, format, *args):
        return
