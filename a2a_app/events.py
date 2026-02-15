"""Redis event publisher and subscriber for SSE."""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import redis.asyncio as aioredis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


class RedisEventPublisher:
    """Redis-based event publisher for SSE.

    Publishes events to Redis streams for real-time streaming.
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        stream_prefix: str = "a2a:events",
    ) -> None:
        """Initialize the publisher.

        Args:
            redis_url: Redis connection URL.
            stream_prefix: Prefix for stream keys.
        """
        self._redis_url = redis_url
        self._stream_prefix = stream_prefix
        self._redis: aioredis.Redis | None = None

    async def _get_redis(self) -> aioredis.Redis:
        """Get or create Redis connection."""
        if self._redis is None:
            self._redis = aioredis.from_url(self._redis_url)
        return self._redis

    def _get_stream_key(self, task_id: str) -> str:
        """Get the Redis stream key for a task."""
        return f"{self._stream_prefix}:{task_id}"

    async def publish(
        self,
        task_id: str,
        event: dict[str, Any],
    ) -> str:
        """Publish an event to the task's stream.

        Args:
            task_id: The task ID.
            event: The event data to publish.

        Returns:
            The event ID in the stream.
        """
        redis = await self._get_redis()
        stream_key = self._get_stream_key(task_id)

        try:
            event_id = await redis.xadd(
                stream_key,
                {"data": json.dumps(event, default=str)},
                maxlen=1000,
                approximate=True,
            )
            logger.debug(f"Published event to {stream_key}: {event_id}")
            return event_id.decode() if isinstance(event_id, bytes) else event_id
        except RedisError as e:
            logger.error(f"Failed to publish event: {e}")
            raise

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None


class RedisEventSubscriber:
    """Redis-based event subscriber for SSE.

    Subscribes to Redis streams for real-time event streaming.
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        stream_prefix: str = "a2a:events",
    ) -> None:
        """Initialize the subscriber.

        Args:
            redis_url: Redis connection URL.
            stream_prefix: Prefix for stream keys.
        """
        self._redis_url = redis_url
        self._stream_prefix = stream_prefix
        self._redis: aioredis.Redis | None = None
        self._running = False

    async def _get_redis(self) -> aioredis.Redis:
        """Get or create Redis connection."""
        if self._redis is None:
            self._redis = aioredis.from_url(self._redis_url)
        return self._redis

    def _get_stream_key(self, task_id: str) -> str:
        """Get the Redis stream key for a task."""
        return f"{self._stream_prefix}:{task_id}"

    async def subscribe(
        self,
        task_id: str,
        last_event_id: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Subscribe to events for a task.

        Args:
            task_id: The task ID to subscribe to.
            last_event_id: The last event ID received (for resumption).

        Yields:
            Event dictionaries.
        """
        redis = await self._get_redis()
        stream_key = self._get_stream_key(task_id)
        self._running = True

        try:
            if last_event_id:
                start_id = f"({last_event_id}"
            else:
                start_id = "0"

            while self._running:
                try:
                    messages = await redis.xread(
                        {stream_key: start_id},
                        count=100,
                        block=1000,
                    )

                    if messages:
                        for stream_name, events in messages:
                            for msg_id, fields in events:
                                event_data = json.loads(fields[b"data"].decode())
                                event_data["_id"] = msg_id.decode()
                                yield event_data

                    await asyncio.sleep(0.01)

                except RedisError as e:
                    logger.error(f"Error reading from stream: {e}")
                    await asyncio.sleep(1)

        finally:
            self._running = False

    async def get_events_since(
        self,
        task_id: str,
        after_event_id: str,
        limit: int = 1000,
    ) -> AsyncIterator[dict[str, Any]]:
        """Get all events since a specific event ID.

        Args:
            task_id: The task ID.
            after_event_id: Get events after this ID.
            limit: Maximum number of events to retrieve.

        Yields:
            Event dictionaries.
        """
        redis = await self._get_redis()
        stream_key = self._get_stream_key(task_id)

        try:
            messages = await redis.xrange(
                stream_key,
                min=f"({after_event_id}",
                max="+",
                count=limit,
            )

            for msg_id, fields in messages:
                event_data = json.loads(fields[b"data"].decode())
                event_data["_id"] = msg_id.decode()
                yield event_data

        except RedisError as e:
            logger.error(f"Error reading from stream: {e}")
            raise

    async def close(self) -> None:
        """Close the Redis connection."""
        self._running = False
        if self._redis:
            await self._redis.close()
            self._redis = None
