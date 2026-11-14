"""Persistent single-service request quotas; never trust caller-supplied IP headers."""
import hashlib
import os
from pathlib import Path
import sqlite3
import time
from contextlib import closing

from starlette.responses import JSONResponse


def take_slot(database, identity, category, limit, seconds, now=None):
    now = int(time.time() if now is None else now)
    window = now // seconds
    key = hashlib.sha256(identity.encode()).hexdigest()
    with closing(sqlite3.connect(str(database), timeout=5)) as connection, connection:
        connection.execute("CREATE TABLE IF NOT EXISTS quotas (identity TEXT, category TEXT, window INTEGER, count INTEGER, PRIMARY KEY(identity,category,window))")
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("DELETE FROM quotas WHERE window < ? AND category = ?", (window - 1, category))
        row = connection.execute("SELECT count FROM quotas WHERE identity=? AND category=? AND window=?", (key, category, window)).fetchone()
        if row and row[0] >= limit:
            return max(1, seconds - now % seconds)
        connection.execute("INSERT INTO quotas VALUES (?,?,?,1) ON CONFLICT(identity,category,window) DO UPDATE SET count=count+1", (key, category, window))
    return 0


def install_request_limits(app):
    database = Path(os.getenv("PAPERPILOT_RATE_DB", "/data/request-limits.sqlite3"))
    database.parent.mkdir(parents=True, exist_ok=True)

    @app.middleware("http")
    async def limit_requests(request, call_next):
        path = request.url.path
        if request.method in ("POST", "PUT", "PATCH"):
            if path.startswith("/auth/"):
                category, limit, seconds = "auth", 10, 600
            elif path in ("/uploadfile/", "/import-url/") or path.endswith("/retry"):
                category, limit, seconds = "upload", 5, 3600
            elif path.endswith("/ask"):
                category, limit, seconds = "question", 20, 3600
            else:
                category, limit, seconds = "write", 60, 60
            # Socket peer is trustworthy; X-Forwarded-For from callers is not.
            # Configure Uvicorn trusted proxy IPs explicitly for per-client quotas.
            identity = request.client.host if request.client else "unknown"
            from starlette.concurrency import run_in_threadpool
            retry = await run_in_threadpool(take_slot, database, identity, category, limit, seconds)
            if retry:
                return JSONResponse({"detail": "Too many requests. Please wait before trying again."}, status_code=429, headers={"Retry-After": str(retry)})
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        if path.startswith("/auth/"):
            response.headers["Cache-Control"] = "no-store"
        return response
