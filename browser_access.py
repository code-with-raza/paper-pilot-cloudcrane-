"""Explicit browser origins for web and CloudCrane clients."""
import os
from urllib.parse import urlsplit

from fastapi.middleware.cors import CORSMiddleware


def configure_cors(app):
    origins = []
    for value in os.getenv("PAPERPILOT_ALLOWED_ORIGINS", "").split(","):
        origin = value.strip()
        if not origin:
            continue
        parsed = urlsplit(origin)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username or parsed.password
            or parsed.path or parsed.query or parsed.fragment
            or "*" in origin
        ):
            raise ValueError("PAPERPILOT_ALLOWED_ORIGINS must contain exact origins without paths or wildcards.")
        if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("Remote browser origins must use HTTPS.")
        # Accessing port validates malformed port numbers too.
        parsed.port
        origins.append(origin)
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["Authorization", "Content-Type"],
        )
