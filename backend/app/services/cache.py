from __future__ import annotations

import threading
import time
from typing import Generic, TypeVar, Callable, Optional


T = TypeVar("T")


class TimedCache(Generic[T]):
    """Simple thread-safe TTL cache for expensive operations."""

    def __init__(self, ttl_seconds: int = 15):
        self.ttl_seconds = ttl_seconds
        self._value: Optional[T] = None
        self._timestamp: float = 0.0
        self._lock = threading.Lock()

    def get(self, builder: Callable[[], T], force_refresh: bool = False) -> T:
        with self._lock:
            now = time.time()
            if force_refresh or self._value is None or (now - self._timestamp) > self.ttl_seconds:
                self._value = builder()
                self._timestamp = now
        return self._value

    def invalidate(self):
        with self._lock:
            self._value = None
            self._timestamp = 0.0
