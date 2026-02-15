"""A2A API Routes - Django-Bolt."""

import json
import logging
import uuid

from django.conf import settings
from django.shortcuts import render
from django_bolt import BoltAPI, Request
from django_bolt.middleware import no_compress
from django_bolt.responses import StreamingResponse, JSON

from a2a_app.events import RedisEventPublisher, RedisEventSubscriber
from a2a_app.schemas import (
    TaskSendParams,
    TaskIdParams,
    TaskGetParams,
    CreateConversationBody,
    JSONRPCRequest,
    JSONRPCResponse,
    JSONRPCError,
)
from a2a_app.services import TaskService, ConversationService
from a2a_app.executors import execute_fake_agent

logger = logging.getLogger(__name__)

api = BoltAPI()

TERMINAL_STATES = {"completed", "failed", "canceled", "rejected"}


def get_agent_card() -> dict:
    """Get the agent card configuration."""
    return settings.A2A_CONFIG.get("AGENT_CARD", {})


def format_sse_event(data: dict, event_id: str | None = None) -> str:
    """Format data as SSE event."""
    lines = []
    if event_id:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {data.get('type', 'message')}")
    json_data = json.dumps(data, default=str)
    for line in json_data.split("\n"):
        lines.append(f"data: {line}")
    lines.append("")
    return "\n".join(lines) + "\n"


# ============================================
# Home / Playground
# ============================================


@api.get("/")
async def playground_home(request: Request):
    """Render the A2A Playground."""
    return render(request, "playground/index.html", {"agent": get_agent_card()})


@api.get("/playground/")
async def playground(request: Request):
    """Render the A2A Playground."""
    return render(request, "playground/index.html", {"agent": get_agent_card()})


# ============================================
# Agent Card Endpoints
# ============================================


@api.get("/card/")
async def get_card(request: Request):
    """Return the agent card."""
    return get_agent_card()


@api.get("/.well-known/agent-card.json")
async def get_agent_card_well_known(request: Request):
    """Return the agent card at the standard A2A well-known location."""
    return get_agent_card()


# ============================================
# Conversation Endpoints
# ============================================


@api.get("/conversations/")
async def list_conversations(request: Request):
    """List all conversations."""
    return await ConversationService.list()


@api.post("/conversations/")
async def create_conversation(request: Request, body: CreateConversationBody):
    """Create a new conversation."""
    return await ConversationService.create(body.context_id, body.agent_id)


@api.delete("/conversations/{context_id}/")
async def delete_conversation(request: Request, context_id: str):
    """Delete a conversation and its tasks."""
    deleted = await ConversationService.delete(context_id)
    if not deleted:
        return JSON({"error": "Conversation not found"}, status=404)
    return {"success": True}


@api.get("/conversations/{context_id}/")
async def get_conversation(request: Request, context_id: str):
    """Get a conversation by ID with history and stream indicator."""
    result = await ConversationService.get_detail(context_id)
    if not result:
        return JSON({"error": "Conversation not found"}, status=404)
    return result


# ============================================
# JSON-RPC Endpoint
# ============================================


@api.post("/rpc/")
async def handle_rpc(request: Request, payload: JSONRPCRequest) -> JSONRPCResponse:
    """Handle A2A JSON-RPC requests."""
    method = payload.method
    params = payload.params or {}
    request_id = payload.id

    handlers = {
        "tasks/send": handle_tasks_send,
        "message/send": handle_tasks_send,
        "tasks/sendSubscribe": handle_tasks_send_subscribe,
        "message/stream": handle_tasks_send_subscribe,
        "tasks/resubscribe": handle_tasks_resubscribe,
        "tasks/get": handle_tasks_get,
        "tasks/cancel": handle_tasks_cancel,
    }

    handler = handlers.get(method)
    if not handler:
        return JSONRPCResponse(
            jsonrpc="2.0",
            error=JSONRPCError(code=-32601, message=f"Method not found: {method}"),
            id=request_id,
        )

    try:
        result = await handler(params)
        return JSONRPCResponse(jsonrpc="2.0", result=result, id=request_id)
    except ValueError as e:
        return JSONRPCResponse(
            jsonrpc="2.0",
            error=JSONRPCError(code=-32602, message=str(e)),
            id=request_id,
        )
    except LookupError as e:
        return JSONRPCResponse(
            jsonrpc="2.0",
            error=JSONRPCError(code=-32601, message=str(e)),
            id=request_id,
        )
    except Exception as e:
        logger.exception(f"Error handling {method}: {e}")
        return JSONRPCResponse(
            jsonrpc="2.0",
            error=JSONRPCError(code=-32603, message=str(e)),
            id=request_id,
        )


# ============================================
# RPC Handlers
# ============================================


async def handle_tasks_send(params: dict) -> dict:
    """Handle tasks/send and message/send."""
    validated = TaskSendParams.model_validate(params)

    task = await TaskService.create(validated.message, validated.contextId)
    task_id = task.id

    publisher = RedisEventPublisher(
        redis_url=settings.REDIS_URL,
        stream_prefix="a2a:events",
    )

    try:
        message_data = {
            "messageId": validated.message.messageId or f"msg-{uuid.uuid4().hex[:8]}",
            "role": validated.message.role,
            "parts": [{"type": p.type, "text": p.text} for p in validated.message.parts],
        }

        async def on_event(event: dict):
            event_type = event.get("type", "")
            event["taskId"] = task_id
            await publisher.publish(task_id, event)

            if event_type == "task.message":
                msg = event.get("message", {})
                if msg:
                    await TaskService.append_message(task_id, msg)
            elif event_type == "task.artifact":
                artifact = event.get("artifact")
                if artifact:
                    await TaskService.add_artifact(task_id, artifact)
            elif event_type in TERMINAL_STATES:
                state = (
                    "completed"
                    if event_type == "task.completed"
                    else event_type.replace("task.", "")
                )
                msg = event.get("message")
                await TaskService.update_status(task_id, state, msg)

        await execute_fake_agent(message_data, on_event)

    finally:
        await publisher.close()

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
        raise ValueError(f"Task {validated.id} is in terminal state: {task.status.state}")

    await TaskService.update_status(validated.id, "canceled")

    result_task = await TaskService.get(validated.id)
    return result_task.model_dump()


# ============================================
# SSE Stream Endpoint
# ============================================


@api.get("/rpc/{task_id}/stream/")
@no_compress
async def stream_task(request: Request, task_id: str):
    """Stream events for a task using SSE."""
    last_event_id = request.headers.get("Last-Event-ID")

    async def generate():
        task = await TaskService.get(task_id)
        if not task:
            yield format_sse_event(
                {
                    "type": "error",
                    "code": "TASK_NOT_FOUND",
                    "message": f"Task {task_id} not found",
                }
            )
            return

        subscriber = RedisEventSubscriber(
            redis_url=settings.REDIS_URL,
            stream_prefix="a2a:events",
        )

        try:
            state = task.status.state
            if state not in TERMINAL_STATES:
                yield format_sse_event(
                    {
                        "type": f"task.{state}",
                        "task": task.model_dump(),
                    }
                )

            async for event in subscriber.subscribe(task_id, last_event_id):
                event_id = event.get("_id")
                yield format_sse_event(event, event_id)

                if event.get("type") in [f"task.{s}" for s in TERMINAL_STATES]:
                    break

        finally:
            await subscriber.close()

    return StreamingResponse(generate(), media_type="text/event-stream")
