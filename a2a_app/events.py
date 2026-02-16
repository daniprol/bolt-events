"""Redis event publisher and subscriber for SSE.

This module provides production-ready Redis event streaming with:
- Shared connection pool for efficient resource usage
- Support for event replay via Redis Streams
- Consumer groups for horizontal scaling
- Automatic reconnection and error handling
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import redis.asyncio as aioredis
from redis.exceptions import RedisError, ResponseError

logger = logging.getLogger(__name__)

STREAM_PREFIX = "a2a:events"


class RedisEventPublisher:
    """Redis-based event publisher for SSE.

    Publishes events to Redis streams for real-time streaming.
    Uses a shared Redis client for connection pooling.

    Example:
        >>> from a2a_app.redis_client import get_redis_client
        >>> redis = get_redis_client()
        >>> publisher = RedisEventPublisher(redis)
        >>> event_id = await publisher.publish("task-123", {"type": "update"})
    """

    def __init__(
        self,
        redis: aioredis.Redis,
        stream_prefix: str = STREAM_PREFIX,
    ) -> None:
        """Initialize the publisher.

        Args:
            redis: Shared Redis client instance.
            stream_prefix: Prefix for stream keys.
        """
        self._redis = redis
        self._stream_prefix = stream_prefix

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

        Raises:
            RedisError: If the publish operation fails.
        """
        stream_key = self._get_stream_key(task_id)

        try:
            event_id = await self._redis.xadd(
                stream_key,
                {"data": json.dumps(event, default=str)},
                maxlen=1000,
                approximate=True,
            )
            logger.debug(f"Published event to {stream_key}: {event_id}")
            return event_id.decode() if isinstance(event_id, bytes) else event_id
        except RedisError as e:
            logger.error(f"Failed to publish event to {stream_key}: {e}")
            raise


class RedisEventSubscriber:
    """Redis-based event subscriber for SSE.

    Subscribes to Redis streams for real-time event streaming with support
    for resumable subscriptions and event replay.

    Example:
        >>> from a2a_app.redis_client import get_redis_client
        >>> redis = get_redis_client()
        >>> subscriber = RedisEventSubscriber(redis)
        >>> async for event in subscriber.subscribe("task-123"):
        ...     print(event)
    """

    def __init__(
        self,
        redis: aioredis.Redis,
        stream_prefix: str = STREAM_PREFIX,
    ) -> None:
        """Initialize the subscriber.

        Args:
            redis: Shared Redis client instance.
            stream_prefix: Prefix for stream keys.
        """
        self._redis = redis
        self._stream_prefix = stream_prefix
        self._running = False

    def _get_stream_key(self, task_id: str) -> str:
        """Get the Redis stream key for a task."""
        return f"{self._stream_prefix}:{task_id}"

    async def subscribe(
        self,
        task_id: str,
        last_event_id: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Subscribe to events for a task.

        Uses blocking reads for efficient event streaming. Supports resumption
        via last_event_id parameter.

        Args:
            task_id: The task ID to subscribe to.
            last_event_id: The last event ID received (for resumption).

        Yields:
            Event dictionaries with _id field containing the event ID.
        """
        stream_key = self._get_stream_key(task_id)
        self._running = True

        try:
            # Determine starting point
            if last_event_id:
                start_id = f"({last_event_id}"
            else:
                start_id = "0"

            while self._running:
                try:
                    # Use blocking read with timeout for efficient waiting
                    # BLOCK 1000 = wait up to 1 second for new messages
                    messages = await self._redis.xread(
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
                                start_id = f"({msg_id.decode()}"

                    # Brief yield to allow other tasks to run
                    await asyncio.sleep(0.001)

                except RedisError as e:
                    logger.error(f"Error reading from stream {stream_key}: {e}")
                    # Exponential backoff for reconnection
                    await asyncio.sleep(1)

        finally:
            self._running = False

    def stop(self) -> None:
        """Stop the subscription gracefully."""
        self._running = False

    async def get_events_since(
        self,
        task_id: str,
        after_event_id: str,
        limit: int = 1000,
    ) -> AsyncIterator[dict[str, Any]]:
        """Get all events since a specific event ID.

        This is useful for replaying events after a disconnection.

        Args:
            task_id: The task ID.
            after_event_id: Get events after this ID (exclusive).
            limit: Maximum number of events to retrieve.

        Yields:
            Event dictionaries with _id field.

        Raises:
            RedisError: If the read operation fails.
        """
        stream_key = self._get_stream_key(task_id)

        try:
            messages = await self._redis.xrange(
                stream_key,
                min=f"({after_event_id}",  # Exclusive of the given ID
                max="+",  # Up to latest
                count=limit,
            )

            for msg_id, fields in messages:
                event_data = json.loads(fields[b"data"].decode())
                event_data["_id"] = msg_id.decode()
                yield event_data

        except RedisError as e:
            logger.error(f"Error reading events from {stream_key}: {e}")
            raise

    async def get_all_events(
        self,
        task_id: str,
        limit: int = 1000,
    ) -> AsyncIterator[dict[str, Any]]:
        """Get all events from the beginning of the stream.

        Args:
            task_id: The task ID.
            limit: Maximum number of events to retrieve.

        Yields:
            Event dictionaries with _id field.
        """
        stream_key = self._get_stream_key(task_id)

        try:
            messages = await self._redis.xrange(
                stream_key,
                min="-",  # From beginning
                max="+",  # To end
                count=limit,
            )

            for msg_id, fields in messages:
                event_data = json.loads(fields[b"data"].decode())
                event_data["_id"] = msg_id.decode()
                yield event_data

        except RedisError as e:
            logger.error(f"Error reading events from {stream_key}: {e}")
            raise


class RedisConsumerGroup:
    """Redis consumer group for distributed event processing.

    This provides load balancing across multiple consumers and ensures
    each event is processed exactly once.

    Example:
        >>> from a2a_app.redis_client import get_redis_client
        >>> redis = get_redis_client()
        >>> consumer = RedisConsumerGroup(redis, "my-group")
        >>> async for event in consumer.consume("task-123", "worker-1"):
        ...     await process_event(event)
    """

    def __init__(
        self,
        redis: aioredis.Redis,
        group_name: str,
        stream_prefix: str = STREAM_PREFIX,
    ) -> None:
        """Initialize the consumer group.

        Args:
            redis: Shared Redis client instance.
            group_name: Name of the consumer group.
            stream_prefix: Prefix for stream keys.
        """
        self._redis = redis
        self._group_name = group_name
        self._stream_prefix = stream_prefix
        self._running = False

    def _get_stream_key(self, task_id: str) -> str:
        """Get the Redis stream key for a task."""
        return f"{self._stream_prefix}:{task_id}"

    async def _ensure_group(self, stream_key: str) -> None:
        """Create consumer group if it doesn't exist."""
        try:
            await self._redis.xgroup_create(
                stream_key,
                self._group_name,
                id="0",  # Start from beginning
                mkstream=True,
            )
            logger.debug(f"Created consumer group {self._group_name} for {stream_key}")
        except ResponseError:
            # Group already exists
            pass

    async def consume(
        self,
        task_id: str,
        consumer_name: str,
    ) -> AsyncIterator[dict[str, Any]]:
        """Consume events from the stream using consumer groups.

        This ensures each event is delivered to only one consumer in the group.

        Args:
            task_id: The task ID.
            consumer_name: Unique name for this consumer instance.

        Yields:
            Event dictionaries with _id field.
        """
        stream_key = self._get_stream_key(task_id)
        await self._ensure_group(stream_key)

        self._running = True

        try:
            while self._running:
                try:
                    # Read new messages (">" means only undelivered messages)
                    messages = await self._redis.xreadgroup(
                        groupname=self._group_name,
                        consumername=consumer_name,
                        streams={stream_key: ">"},
                        count=10,
                        block=5000,  # Wait up to 5 seconds
                    )

                    if messages:
                        for _, events in messages:
                            for msg_id, fields in events:
                                event_data = json.loads(fields[b"data"].decode())
                                event_data["_id"] = msg_id.decode()
                                yield event_data

                                # Acknowledge after successful processing
                                await self._redis.xack(
                                    stream_key,
                                    self._group_name,
                                    msg_id,
                                )

                except RedisError as e:
                    logger.error(f"Error in consumer group {self._group_name}: {e}")
                    await asyncio.sleep(1)

        finally:
            self._running = False

    def stop(self) -> None:
        """Stop consuming gracefully."""
        self._running = False

    async def get_pending_events(
        self,
        task_id: str,
        count: int = 10,
    ) -> list[dict[str, Any]]:
        """Get pending events (messages delivered but not acknowledged).

        Useful for monitoring and debugging.

        Args:
            task_id: The task ID.
            count: Maximum number of pending events to retrieve.

        Returns:
            List of pending event dictionaries.
        """
        stream_key = self._get_stream_key(task_id)

        try:
            pending = await self._redis.xpending_range(
                stream_key,
                self._group_name,
                min="-",
                max="+",
                count=count,
            )

            result = []
            for item in pending:
                result.append(
                    {
                        "message_id": item["message_id"].decode(),
                        "consumer": item["consumer"].decode(),
                        "time_since_delivered": item["time_since_delivered"],
                        "delivery_count": item["delivery_count"],
                    }
                )
            return result

        except RedisError as e:
            logger.error(f"Error getting pending events: {e}")
            return []
