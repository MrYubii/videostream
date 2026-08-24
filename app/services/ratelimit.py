import threading
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, window_seconds: int) -> bool:
        now = time.monotonic()
        with self._lock:
            if len(self._hits) > 5000:
                stale = [
                    k for k, q in self._hits.items()
                    if not q or now - q[-1] > window_seconds * 2
                ]
                for k in stale:
                    self._hits.pop(k, None)
            queue = self._hits[key]
            while queue and now - queue[0] > window_seconds:
                queue.popleft()
            if len(queue) >= limit:
                return False
            queue.append(now)
            return True


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, limit: int, window_seconds: int) -> None:
        super().__init__(app)
        self._limiter = InMemoryRateLimiter()
        self._limit = limit
        self._window = window_seconds

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not path.startswith("/api") or path.endswith("/stream"):
            return await call_next(request)
        client = request.client.host if request.client else "unknown"
        key = f"{client}:{path}"
        if not self._limiter.allow(key, self._limit, self._window):
            return JSONResponse(status_code=429, content={"detail": "Too many requests, slow down"})
        return await call_next(request)
