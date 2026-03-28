"""
Redis connection pool and helper client.

Provides both caching helpers (get/set with TTL) and Pub/Sub wrappers that
play well with ``asyncio``.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import redis.asyncio as aioredis
from loguru import logger

from app.core.config import settings


class RedisClient:
    """Thin async wrapper around ``redis.asyncio`` with convenience methods."""

    def __init__(self) -> None:
        self._pool: aioredis.ConnectionPool | None = None
        self._client: aioredis.Redis | None = None
        self._pubsub: aioredis.client.PubSub | None = None
        self._subscriber_tasks: dict[str, asyncio.Task[None]] = {}

    # -- lifecycle -----------------------------------------------------------

    async def connect(self) -> None:
        self._pool = aioredis.ConnectionPool.from_url(
            settings.redis.url,
            max_connections=settings.redis.max_connections,
            decode_responses=settings.redis.decode_responses,
            socket_timeout=settings.redis.socket_timeout,
            socket_connect_timeout=settings.redis.socket_connect_timeout,
        )
        self._client = aioredis.Redis(connection_pool=self._pool)
        # Verify connectivity.
        await self._client.ping()
        logger.info("Redis connected (pool_size={ps})", ps=settings.redis.max_connections)

    async def disconnect(self) -> None:
        # Cancel any subscriber listeners.
        for task in self._subscriber_tasks.values():
            task.cancel()
        self._subscriber_tasks.clear()

        if self._pubsub:
            await self._pubsub.close()
            self._pubsub = None

        if self._client:
            await self._client.aclose()
            self._client = None

        if self._pool:
            await self._pool.disconnect()
            self._pool = None

        logger.info("Redis disconnected")

    @property
    def client(self) -> aioredis.Redis:
        if self._client is None:
            raise RuntimeError("RedisClient is not connected. Call connect() first.")
        return self._client

    # -- cache helpers -------------------------------------------------------

    async def get(self, key: str) -> str | None:
        return await self.client.get(key)

    async def get_json(self, key: str) -> Any | None:
        raw = await self.client.get(key)
        if raw is None:
            return None
        return json.loads(raw)

    async def set(
        self,
        key: str,
        value: str | bytes,
        ttl_s: int | None = None,
    ) -> None:
        if ttl_s:
            await self.client.setex(key, ttl_s, value)
        else:
            await self.client.set(key, value)

    async def set_json(
        self,
        key: str,
        value: Any,
        ttl_s: int | None = None,
    ) -> None:
        serialized = json.dumps(value, default=str)
        await self.set(key, serialized, ttl_s=ttl_s)

    async def delete(self, *keys: str) -> int:
        if not keys:
            return 0
        return await self.client.delete(*keys)

    async def exists(self, key: str) -> bool:
        return bool(await self.client.exists(key))

    async def incr(self, key: str, amount: int = 1) -> int:
        return await self.client.incrby(key, amount)

    async def expire(self, key: str, ttl_s: int) -> None:
        await self.client.expire(key, ttl_s)

    async def keys(self, pattern: str = "*") -> list[str]:
        return await self.client.keys(pattern)

    # -- pub/sub helpers -----------------------------------------------------

    async def publish(self, channel: str, message: Any) -> int:
        """Publish a JSON-serialisable *message* to *channel*.
        Returns the number of subscribers that received the message."""
        payload = json.dumps(message, default=str) if not isinstance(message, (str, bytes)) else message
        return await self.client.publish(channel, payload)

    async def subscribe(
        self,
        channel: str,
        callback: Any,
    ) -> None:
        """Subscribe to *channel* and invoke *callback(channel, data)* for
        each message.  The listener runs in a background ``asyncio.Task``."""
        if self._pubsub is None:
            self._pubsub = self.client.pubsub()

        await self._pubsub.subscribe(channel)

        async def _listen() -> None:
            try:
                async for raw_msg in self._pubsub.listen():
                    if raw_msg["type"] != "message":
                        continue
                    data = raw_msg["data"]
                    try:
                        data = json.loads(data)
                    except (json.JSONDecodeError, TypeError):
                        pass
                    try:
                        await callback(raw_msg["channel"], data)
                    except Exception:
                        logger.opt(exception=True).error(
                            "Redis subscriber callback error on channel={ch}",
                            ch=channel,
                        )
            except asyncio.CancelledError:
                return

        task = asyncio.create_task(_listen(), name=f"redis-sub-{channel}")
        self._subscriber_tasks[channel] = task

    async def unsubscribe(self, channel: str) -> None:
        if self._pubsub:
            await self._pubsub.unsubscribe(channel)
        task = self._subscriber_tasks.pop(channel, None)
        if task:
            task.cancel()

    # -- hash helpers (useful for orderbook snapshots) -----------------------

    async def hset(self, name: str, key: str, value: str) -> None:
        await self.client.hset(name, key, value)

    async def hget(self, name: str, key: str) -> str | None:
        return await self.client.hget(name, key)

    async def hgetall(self, name: str) -> dict[str, str]:
        return await self.client.hgetall(name)

    async def hdel(self, name: str, *keys: str) -> int:
        return await self.client.hdel(name, *keys)

    # -- sorted set helpers (useful for leaderboards / rankings) -------------

    async def zadd(self, name: str, mapping: dict[str, float]) -> int:
        return await self.client.zadd(name, mapping)

    async def zrange_with_scores(
        self,
        name: str,
        start: int = 0,
        end: int = -1,
        desc: bool = False,
    ) -> list[tuple[str, float]]:
        if desc:
            return await self.client.zrevrange(name, start, end, withscores=True)
        return await self.client.zrange(name, start, end, withscores=True)
