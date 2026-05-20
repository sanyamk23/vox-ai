"""Async Redis cache — thin wrapper around redis.asyncio."""
import json
from typing import Any, Optional

import redis.asyncio as aioredis

from config import settings

_redis: Optional[aioredis.Redis] = None


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


class _Cache:
    async def get(self, key: str) -> Any:
        val = await get_redis().get(key)
        if val is None:
            return None
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return val

    async def set(self, key: str, value: Any, timeout: int = 3600) -> None:
        await get_redis().setex(key, timeout, json.dumps(value, default=str))

    async def add(self, key: str, value: Any, timeout: int = 3600) -> bool:
        """SET NX — returns True if key was created."""
        result = await get_redis().set(
            key, json.dumps(value, default=str), nx=True, ex=timeout
        )
        return result is not None

    async def incr(self, key: str) -> int:
        return await get_redis().incr(key)

    async def delete(self, key: str) -> None:
        await get_redis().delete(key)


cache = _Cache()
