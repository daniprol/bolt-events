"""Redis client configuration with connection pooling.

This module provides a singleton Redis client with connection pooling
for production use. The connection pool is shared across all requests
to minimize connection overhead.
"""

import logging

import redis.asyncio as aioredis
from django.conf import settings

logger = logging.getLogger(__name__)


def _get_redis_config() -> dict:
    """Get Redis configuration from Django settings."""
    return getattr(settings, "REDIS", {"URL": "redis://localhost:6379/1"})


class RedisClientManager:
    """Manages Redis connection pool and shared client instance.

    This is a singleton class that ensures a single connection pool
    is shared across the entire application.
    """

    _instance: "RedisClientManager | None" = None
    _pool: aioredis.ConnectionPool | None = None
    _client: aioredis.Redis | None = None

    def __new__(cls) -> "RedisClientManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def get_pool(self) -> aioredis.ConnectionPool:
        """Get or create the Redis connection pool."""
        if self._pool is None:
            config = _get_redis_config()
            self._pool = aioredis.ConnectionPool.from_url(
                config["URL"],
                max_connections=config.get("MAX_CONNECTIONS", 100),
                socket_connect_timeout=config.get("SOCKET_CONNECT_TIMEOUT", 10),
                socket_timeout=config.get("SOCKET_TIMEOUT", 10),
                retry_on_timeout=config.get("RETRY_ON_TIMEOUT", True),
                health_check_interval=config.get("HEALTH_CHECK_INTERVAL", 30),
            )
            logger.info("Redis connection pool initialized")
        return self._pool

    def get_client(self) -> aioredis.Redis:
        """Get or create the shared Redis client."""
        if self._client is None:
            self._client = aioredis.Redis(connection_pool=self.get_pool())
        return self._client

    async def close(self) -> None:
        """Close the connection pool and client."""
        if self._client is not None:
            await self._client.close()
            self._client = None
            logger.info("Redis client closed")

        if self._pool is not None:
            await self._pool.disconnect()
            self._pool = None
            logger.info("Redis connection pool disconnected")


_redis_manager = RedisClientManager()


def get_redis_client() -> aioredis.Redis:
    """Get the shared Redis client."""
    return _redis_manager.get_client()


async def close_redis() -> None:
    """Close Redis connections gracefully."""
    await _redis_manager.close()
