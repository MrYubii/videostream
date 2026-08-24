import threading
import time


class TTLCache:
    def __init__(self) -> None:
        self._store: dict[str, tuple[float, object]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> object | None:
        with self._lock:
            item = self._store.get(key)
            if item is None:
                return None
            expires_at, value = item
            if time.monotonic() > expires_at:
                self._store.pop(key, None)
                return None
            return value

    def set(self, key: str, value: object, ttl: float) -> None:
        with self._lock:
            self._store[key] = (time.monotonic() + ttl, value)

    def invalidate_prefix(self, prefix: str) -> None:
        with self._lock:
            for key in [k for k in self._store if k.startswith(prefix)]:
                self._store.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


cache = TTLCache()
