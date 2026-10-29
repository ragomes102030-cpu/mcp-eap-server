"""Vercel ASGI entrypoint. Keep the original server.py for Render."""
from api.index import app
