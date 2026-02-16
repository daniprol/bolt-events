"""Fake agent executor for testing and benchmarking.

This module provides a fake A2A agent that simulates various event types
for testing the streaming and SSE functionality.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)
Event = dict[str, Any]
EventCallback = Callable[[Event], Awaitable[None]]


class FakeAgentExecutor:
    """A fake A2A agent that emits simulated events.

    This agent generates various types of events for testing and benchmarking:
    - Text responses (chunked)
    - Tool calls (mock)
    - Artifacts
    - Status updates
    """

    def __init__(
        self,
        text_delay: float = 0.1,
        num_chunks: int = 5,
        include_tools: bool = True,
        include_artifacts: bool = True,
    ) -> None:
        """Initialize the fake agent.

        Args:
            text_delay: Delay between text chunks in seconds.
            num_chunks: Number of text chunks to generate.
            include_tools: Whether to include tool call events.
            include_artifacts: Whether to include artifact events.
        """
        self._text_delay = text_delay
        self._num_chunks = num_chunks
        self._include_tools = include_tools
        self._include_artifacts = include_artifacts

    async def execute(
        self,
        message: dict[str, Any],
        on_event: EventCallback | None = None,
    ) -> None:
        """Execute the fake agent and emit events through callback.

        Args:
            message: The input message from the A2A protocol.
            on_event: Optional callback for handling emitted events.
        """
        task_id = message.get("taskId", "unknown")
        user_message = self._extract_text(message)

        logger.info(f"FakeAgentExecutor processing task {task_id}: {user_message}")

        await self._emit(
            on_event,
            {
                "type": "task.working",
                "taskId": task_id,
            },
        )

        if self._include_tools:
            await self._emit(
                on_event,
                {
                    "type": "tool-call",
                    "taskId": task_id,
                    "toolCallId": f"tool-{task_id}-1",
                    "toolName": "fake_search",
                    "input": {"query": user_message},
                },
            )

            await asyncio.sleep(self._text_delay)

            await self._emit(
                on_event,
                {
                    "type": "tool-call-result",
                    "taskId": task_id,
                    "toolCallId": f"tool-{task_id}-1",
                    "result": {"results": ["fake result 1", "fake result 2"]},
                },
            )

        for i in range(self._num_chunks):
            text = f"Response chunk {i + 1}/ {self._num_chunks}. "
            text += f"Your message was: '{user_message}'. "
            text += "This is a simulated response for testing purposes. "
            text += f"Processing step {i + 1} of {self._num_chunks} complete."

            await self._emit(
                on_event,
                {
                    "type": "task.message",
                    "taskId": task_id,
                    "message": {
                        "role": "agent",
                        "parts": [{"type": "text", "text": text}],
                    },
                },
            )

            await asyncio.sleep(self._text_delay)

        if self._include_artifacts:
            await self._emit(
                on_event,
                {
                    "type": "task.artifact",
                    "taskId": task_id,
                    "artifact": {
                        "name": "analysis_result",
                        "parts": [
                            {
                                "type": "data",
                                "data": {
                                    "summary": "This is a simulated artifact for testing",
                                    "items": ["item1", "item2", "item3"],
                                    "metadata": {
                                        "generated_at": "2024-01-01T00:00:00Z",
                                        "version": "1.0",
                                    },
                                },
                            }
                        ],
                    },
                },
            )

        await self._emit(
            on_event,
            {
                "type": "task.completed",
                "taskId": task_id,
                "message": {
                    "role": "agent",
                    "parts": [{"type": "text", "text": "Task completed successfully!"}],
                },
            },
        )

        logger.info(f"FakeAgentExecutor completed task {task_id}")

    async def _emit(self, callback: EventCallback | None, event: Event) -> None:
        """Emit a single event if a callback is configured."""
        if callback is not None:
            await callback(event)

    def _extract_text(self, message: dict[str, Any]) -> str:
        """Extract text from the message."""
        parts = message.get("parts", [])
        for part in parts:
            if part.get("type") == "text":
                return part.get("text", "")
        return "Hello"


async def execute_fake_agent(
    message: dict[str, Any],
    on_event: EventCallback | None = None,
) -> None:
    """Execute a fake agent and emit events through callback.

    This is a convenience function that creates a FakeAgentExecutor
    and executes it.

    Args:
        message: The input message from the A2A protocol.
        on_event: Optional callback for handling emitted events.
    """
    agent = FakeAgentExecutor()
    await agent.execute(message, on_event)
