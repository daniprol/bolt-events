"""A2A protocol task handlers with Redis event streaming."""

import uuid
from typing import Any

from a2a_app.events import RedisEventPublisher
from a2a_app.executors import execute_fake_agent
from a2a_app.redis_client import get_redis_client
from a2a_app.schemas import TaskGetParams, TaskIdParams, TaskSendParams
from a2a_app.services import TaskService

TERMINAL_STATES = {"completed", "failed", "canceled", "rejected"}


def _get_terminal_state(event_type: str) -> str | None:
    """Convert task.* event type to terminal task state when applicable."""
    if not event_type.startswith("task."):
        return None
    state = event_type.removeprefix("task.")
    return state if state in TERMINAL_STATES else None


async def _process_task_event(
    *,
    task_id: str,
    publisher: RedisEventPublisher,
    event: dict[str, Any],
) -> None:
    """Persist and publish a single task event."""
    event_type = event.get("type", "")
    event["taskId"] = task_id
    await publisher.publish(task_id, event)

    if event_type == "task.message":
        msg = event.get("message")
        if msg:
            await TaskService.append_message(task_id, msg)
        return

    if event_type == "task.artifact":
        artifact = event.get("artifact")
        if artifact:
            await TaskService.add_artifact(task_id, artifact)
        return

    terminal_state = _get_terminal_state(event_type)
    if terminal_state:
        await TaskService.update_status(task_id, terminal_state, event.get("message"))


async def handle_tasks_send(params: dict) -> dict:
    """Handle tasks/send and message/send."""
    validated = TaskSendParams.model_validate(params)

    task = await TaskService.create(validated.message, validated.contextId)
    task_id = task.id

    # Use shared Redis client for efficient connection pooling
    redis = get_redis_client()
    publisher = RedisEventPublisher(redis)

    message_data = {
        "messageId": validated.message.messageId or f"msg-{uuid.uuid4().hex[:8]}",
        "role": validated.message.role,
        "parts": [{"type": p.type, "text": p.text} for p in validated.message.parts],
    }

    async def on_event(event: dict[str, Any]) -> None:
        await _process_task_event(task_id=task_id, publisher=publisher, event=event)

    await execute_fake_agent(message_data, on_event)

    fresh_task = await TaskService.get(task_id)
    if fresh_task:
        return {
            "id": fresh_task.id,
            "contextId": fresh_task.contextId,
            "status": {"state": fresh_task.status.state},
            "history": fresh_task.history,
        }
    return {
        "id": task_id,
        "contextId": task.contextId,
        "status": {"state": "submitted"},
        "history": [],
    }


async def handle_tasks_send_subscribe(params: dict) -> dict:
    """Handle tasks/sendSubscribe and message/stream."""
    result = await handle_tasks_send(params)
    task_id = result["id"]

    return {
        "task": result,
        "streamUrl": f"/agent/rpc/{task_id}/stream/",
    }


async def handle_tasks_resubscribe(params: dict) -> dict:
    """Handle tasks/resubscribe."""
    validated = TaskIdParams.model_validate(params)

    task = await TaskService.get(validated.id)
    if not task:
        raise LookupError(f"Task {validated.id} not found")

    return {
        "task": task.model_dump(),
        "streamUrl": f"/agent/rpc/{validated.id}/stream/",
    }


async def handle_tasks_get(params: dict) -> dict:
    """Handle tasks/get."""
    validated = TaskGetParams.model_validate(params)

    task = await TaskService.get(validated.id)
    if not task:
        raise LookupError(f"Task {validated.id} not found")

    result = task.model_dump()
    if validated.historyLength is not None:
        result["history"] = result["history"][-validated.historyLength :]

    return result


async def handle_tasks_cancel(params: dict) -> dict:
    """Handle tasks/cancel."""
    validated = TaskIdParams.model_validate(params)

    task = await TaskService.get(validated.id)
    if not task:
        raise LookupError(f"Task {validated.id} not found")

    if task.status.state in TERMINAL_STATES:
        raise ValueError(f"Task {validated.id} is already in terminal state: {task.status.state}")

    # TODO: update_status should return the updated task to avoid this extra get
    await TaskService.update_status(validated.id, "canceled")

    result_task = await TaskService.get(validated.id)
    return result_task.model_dump()
