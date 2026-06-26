"""Simple TTL cache for frequently accessed data (e.g. apartment lists)."""
from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class TTLCache(Generic[K, V]):
    """A simple async-safe TTL cache.

    Entries expire after ``ttl_seconds``.  Use ``get_or_load`` to fetch
    from the cache or compute and store the value.
    """

    def __init__(self, ttl_seconds: float = 60.0) -> None:
        self._ttl = ttl_seconds
        self._store: dict[K, tuple[V, float]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: K) -> V | None:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if time.monotonic() > expires_at:
                del self._store[key]
                return None
            return value

    async def set(self, key: K, value: V) -> None:
        async with self._lock:
            self._store[key] = (value, time.monotonic() + self._ttl)

    async def invalidate(self, key: K) -> None:
        async with self._lock:
            self._store.pop(key, None)

    async def clear(self) -> None:
        async with self._lock:
            self._store.clear()

    async def get_or_load(
        self,
        key: K,
        loader: Callable[[], Awaitable[V]],
    ) -> V:
        cached = await self.get(key)
        if cached is not None:
            return cached
        value = await loader()
        await self.set(key, value)
        return value


# Global cache instances — keyed by string identifiers.
# Apartment list caches expire quickly (30s) since data changes with scrapes.
apartment_list_cache: TTLCache[str, list] = TTLCache(ttl_seconds=30.0)
# Complex list cache — longer TTL since complexes rarely change.
complex_cache: TTLCache[str, list] = TTLCache(ttl_seconds=300.0)
