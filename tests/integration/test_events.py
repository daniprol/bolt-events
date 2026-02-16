"""Integration tests for Redis events - requires real Redis."""

import pytest
import asyncio
import redis.asyncio as aioredis

from a2a_app.events import RedisEventPublisher, RedisEventSubscriber
from a2a_app.redis_client import RedisClientManager


pytestmark = pytest.mark.redis


@pytest.fixture
def redis_client_manager(test_redis_url):
    """Create a Redis client manager for tests."""
    # Create a fresh manager for each test to avoid connection pool conflicts
    manager = RedisClientManager()
    # Override the pool with test-specific URL
    import redis.asyncio as aioredis

    pool = aioredis.ConnectionPool.from_url(
        test_redis_url,
        max_connections=10,
    )
    manager._pool = pool
    manager._client = aioredis.Redis(connection_pool=pool)

    yield manager

    # Cleanup
    async def cleanup():
        await manager.close()

    import asyncio

    asyncio.run(cleanup())


@pytest.mark.asyncio
async def test_publish_and_subscribe(test_redis_url):
    """Test basic publish and subscribe functionality."""
    # Create Redis client for this test
    pool = aioredis.ConnectionPool.from_url(test_redis_url, max_connections=10)
    redis = aioredis.Redis(connection_pool=pool)

    try:
        publisher = RedisEventPublisher(redis=redis)
        subscriber = RedisEventSubscriber(redis=redis)

        event_id = await publisher.publish("task-test-1", {"type": "test.event", "data": "hello"})
        assert event_id is not None

        events = []
        async for event in subscriber.subscribe("task-test-1"):
            events.append(event)
            if len(events) >= 1:
                break

        assert len(events) == 1
        assert events[0]["type"] == "test.event"
        assert events[0]["data"] == "hello"
    finally:
        await redis.close()
        await pool.disconnect()


@pytest.mark.asyncio
async def test_publish_multiple_events(test_redis_url):
    """Test publishing multiple events to the same task."""
    pool = aioredis.ConnectionPool.from_url(test_redis_url, max_connections=10)
    redis = aioredis.Redis(connection_pool=pool)

    try:
        publisher = RedisEventPublisher(redis=redis)

        for i in range(5):
            event_id = await publisher.publish("task-multi", {"type": "event", "index": i})
            assert event_id is not None
    finally:
        await redis.close()
        await pool.disconnect()


@pytest.mark.asyncio
async def test_subscribe_with_last_event_id(test_redis_url):
    """Test subscribing with Last-Event-ID to skip already received events."""
    pool = aioredis.ConnectionPool.from_url(test_redis_url, max_connections=10)
    redis = aioredis.Redis(connection_pool=pool)

    try:
        publisher = RedisEventPublisher(redis=redis)

        event_id_1 = await publisher.publish("task-resume", {"type": "event-1", "index": 1})
        event_id_2 = await publisher.publish("task-resume", {"type": "event-2", "index": 2})
        event_id_3 = await publisher.publish("task-resume", {"type": "event-3", "index": 3})

        subscriber = RedisEventSubscriber(redis=redis)

        events = []
        async for event in subscriber.subscribe("task-resume", last_event_id=event_id_1):
            events.append(event)
            if len(events) >= 2:
                break

        assert len(events) == 2
        assert events[0]["index"] == 2
        assert events[1]["index"] == 3
    finally:
        await redis.close()
        await pool.disconnect()


@pytest.mark.asyncio
async def test_subscribe_from_beginning(test_redis_url):
    """Test subscribing from the beginning (no last_event_id)."""
    pool = aioredis.ConnectionPool.from_url(test_redis_url, max_connections=10)
    redis = aioredis.Redis(connection_pool=pool)

    try:
        publisher = RedisEventPublisher(redis=redis)

        await publisher.publish("task-begin", {"type": "event-1"})
        await publisher.publish("task-begin", {"type": "event-2"})

        subscriber = RedisEventSubscriber(redis=redis)

        events = []
        async for event in subscriber.subscribe("task-begin"):
            events.append(event)
            if len(events) >= 2:
                break

        assert len(events) == 2
    finally:
        await redis.close()
        await pool.disconnect()


@pytest.mark.asyncio
async def test_high_throughput_events(test_redis_url):
    """Test handling high volume of events."""
    pool = aioredis.ConnectionPool.from_url(test_redis_url, max_connections=10)
    redis = aioredis.Redis(connection_pool=pool)

    try:
        publisher = RedisEventPublisher(redis=redis)
        task_id = "task-throughput"

        for i in range(100):
            await publisher.publish(task_id, {"type": "event", "index": i, "data": f"data-{i}"})

        subscriber = RedisEventSubscriber(redis=redis)

        events = []
        async for event in subscriber.subscribe(task_id):
            events.append(event)
            if len(events) >= 100:
                break

        assert len(events) == 100
    finally:
        await redis.close()
        await pool.disconnect()


@pytest.mark.asyncio
async def test_get_events_since(test_redis_url):
    """Test getting events since a specific event ID."""
    pool = aioredis.ConnectionPool.from_url(test_redis_url, max_connections=10)
    redis = aioredis.Redis(connection_pool=pool)

    try:
        publisher = RedisEventPublisher(redis=redis)

        event_id_1 = await publisher.publish("task-since", {"type": "event-1"})
        event_id_2 = await publisher.publish("task-since", {"type": "event-2"})
        event_id_3 = await publisher.publish("task-since", {"type": "event-3"})

        subscriber = RedisEventSubscriber(redis=redis)

        events = []
        async for event in subscriber.get_events_since("task-since", event_id_2, limit=10):
            events.append(event)

        assert len(events) == 1
        assert events[0]["type"] == "event-3"
    finally:
        await redis.close()
        await pool.disconnect()


@pytest.mark.asyncio
async def test_concurrent_publish_subscribe(test_redis_url):
    """Test concurrent publishing and subscribing."""
    pool = aioredis.ConnectionPool.from_url(test_redis_url, max_connections=10)
    redis = aioredis.Redis(connection_pool=pool)

    try:
        publisher = RedisEventPublisher(redis=redis)
        subscriber = RedisEventSubscriber(redis=redis)

        async def publish_events():
            for i in range(10):
                await publisher.publish("task-concurrent", {"type": "event", "index": i})
                await asyncio.sleep(0.01)

        async def consume_events():
            events = []
            async for event in subscriber.subscribe("task-concurrent"):
                events.append(event)
                if len(events) >= 10:
                    break
            return events

        await asyncio.gather(publish_events(), consume_events())
    finally:
        await redis.close()
        await pool.disconnect()


@pytest.mark.asyncio
async def test_get_all_events(test_redis_url):
    """Test getting all events from a stream."""
    pool = aioredis.ConnectionPool.from_url(test_redis_url, max_connections=10)
    redis = aioredis.Redis(connection_pool=pool)

    try:
        publisher = RedisEventPublisher(redis=redis)

        # Publish events
        for i in range(5):
            await publisher.publish("task-all", {"type": f"event-{i}"})

        subscriber = RedisEventSubscriber(redis=redis)

        # Get all events
        events = []
        async for event in subscriber.get_all_events("task-all"):
            events.append(event)

        assert len(events) == 5
        assert events[0]["type"] == "event-0"
        assert events[4]["type"] == "event-4"
    finally:
        await redis.close()
        await pool.disconnect()
