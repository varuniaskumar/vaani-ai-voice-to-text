"""Root Vercel entrypoint for the combined frontend and API deployment."""

from backend.app.main import app

__all__ = ["app"]
