"""Non-secret readiness probe for Vercel deployment diagnostics."""
import json
import os
from http.server import BaseHTTPRequestHandler

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        required = ("MCP_API_TOKEN", "TURSO_URL", "TURSO_TOKEN")
        ready = all(os.getenv(k) for k in required)
        body = json.dumps({"ok": ready, "configured": ready}).encode("utf-8")
        self.send_response(200 if ready else 503)
        self.send_header("content-type", "application/json")
        self.send_header("cache-control", "no-store")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
