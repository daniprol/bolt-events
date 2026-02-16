"""Unit tests for FakeAgentExecutor."""

import pytest
import asyncio
from a2a_app.executors import FakeAgentExecutor


class TestFakeAgentExecutor:
    """Tests for FakeAgentExecutor."""

    @pytest.mark.asyncio
    async def test_basic_execution(self):
        """Test basic agent execution."""
        executor = FakeAgentExecutor(text_delay=0.01, num_chunks=2)
        events = []

        async def capture(event):
            events.append(event)

        message = {"role": "user", "parts": [{"type": "text", "text": "Hello"}]}
        await executor.execute(message, capture)

        assert len(events) > 0
        assert any(e["type"] == "task.working" for e in events)
        assert any(e["type"] == "task.completed" for e in events)

    @pytest.mark.asyncio
    async def test_with_tool_calls(self):
        """Test execution with tool calls."""
        executor = FakeAgentExecutor(include_tools=True, num_chunks=1)
        events = []

        async def capture(event):
            events.append(event)

        await executor.execute({"parts": [{"type": "text", "text": "test"}]}, capture)

        assert any(e["type"] == "tool-call" for e in events)
        assert any(e["type"] == "tool-call-result" for e in events)

    @pytest.mark.asyncio
    async def test_without_tools(self):
        """Test execution without tools."""
        executor = FakeAgentExecutor(include_tools=False, num_chunks=1)
        events = []

        async def capture(event):
            events.append(event)

        await executor.execute({"parts": [{"type": "text", "text": "test"}]}, capture)

        assert not any(e["type"] == "tool-call" for e in events)

    @pytest.mark.asyncio
    async def test_with_artifacts(self):
        """Test execution with artifacts."""
        executor = FakeAgentExecutor(include_artifacts=True, num_chunks=1)
        events = []

        async def capture(event):
            events.append(event)

        await executor.execute({"parts": [{"type": "text", "text": "test"}]}, capture)

        assert any(e["type"] == "task.artifact" for e in events)

    @pytest.mark.asyncio
    async def test_without_artifacts(self):
        """Test execution without artifacts."""
        executor = FakeAgentExecutor(include_artifacts=False, num_chunks=1)
        events = []

        async def capture(event):
            events.append(event)

        await executor.execute({"parts": [{"type": "text", "text": "test"}]}, capture)

        assert not any(e["type"] == "task.artifact" for e in events)

    @pytest.mark.asyncio
    async def test_multiple_chunks(self):
        """Test multiple response chunks."""
        executor = FakeAgentExecutor(num_chunks=5, text_delay=0.001)
        events = []

        async def capture(event):
            events.append(event)

        await executor.execute({"parts": [{"type": "text", "text": "test"}]}, capture)

        message_events = [e for e in events if e["type"] == "task.message"]
        assert len(message_events) == 5

    @pytest.mark.asyncio
    async def test_extract_text(self):
        """Test message text extraction."""
        executor = FakeAgentExecutor()

        msg = {"parts": [{"type": "text", "text": "Hello World"}]}
        assert executor._extract_text(msg) == "Hello World"

        msg = {"parts": [{"type": "data", "data": {}}]}
        assert executor._extract_text(msg) == "Hello"

    @pytest.mark.asyncio
    async def test_event_ordering(self):
        """Test that events are emitted in correct order."""
        executor = FakeAgentExecutor(num_chunks=1, text_delay=0.001)
        events = []

        async def capture(event):
            events.append(event["type"])

        await executor.execute({"parts": [{"type": "text", "text": "test"}]}, capture)

        assert events[0] == "task.working"
        assert events[-1] == "task.completed"

    @pytest.mark.asyncio
    async def test_empty_message(self):
        """Test handling empty message."""
        executor = FakeAgentExecutor(num_chunks=1)
        events = []

        async def capture(event):
            events.append(event)

        await executor.execute({}, capture)

        assert len(events) > 0
