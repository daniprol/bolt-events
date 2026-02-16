"""Shared pytest fixtures for A2A tests."""

import asyncio
import os
import pytest

pytest_plugins = ["pytest_django"]


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def cleanup_db():
    """Clean database before each test."""
    from django.db import connection
    from a2a_app.models import A2ATask, Conversation

    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM a2a_tasks")
        cursor.execute("DELETE FROM a2a_conversations")

    yield


@pytest.fixture
def task_factory():
    """Factory for creating tasks."""
    from tests.factories import TaskFactory

    return TaskFactory


@pytest.fixture
def conversation_factory():
    """Factory for creating conversations."""
    from tests.factories import ConversationFactory

    return ConversationFactory


@pytest.fixture
async def redis_client():
    """Redis client for tests."""
    import redis.asyncio as aioredis

    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/15")
    client = aioredis.from_url(redis_url)
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.close()


@pytest.fixture
async def fakeredis_client():
    """Fake Redis client for tests without real Redis."""
    import fakeredis.aioredis

    client = fakeredis.aioredis.FakeRedis()
    yield client
    await client.flushall()
    await client.close()


@pytest.fixture
def test_redis_url():
    """Get Redis URL for tests."""
    return os.environ.get("REDIS_URL", "redis://localhost:6379/15")


@pytest.fixture
def mark_redis(request, test_redis_url):
    """Skip test if Redis is not available."""
    import redis

    try:
        r = redis.Redis.from_url(test_redis_url)
        r.ping()
    except Exception:
        pytest.skip("Redis not available")
