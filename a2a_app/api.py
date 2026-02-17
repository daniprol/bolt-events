"""A2A API endpoints with Redis-based SSE streaming."""

import json
import logging

from django.conf import settings
from django_bolt import BoltAPI, Request, CompressionConfig
from django_bolt.middleware import no_compress
from django_bolt.responses import JSON, StreamingResponse
from django_bolt.shortcuts import render
from django_bolt.exceptions import NotFound
from django_bolt.logging import LoggingConfig, create_logging_middleware
from a2a_app.events import RedisEventSubscriber
from a2a_app.handlers import (
    handle_tasks_cancel,
    handle_tasks_get,
    handle_tasks_resubscribe,
    handle_tasks_send,
    handle_tasks_send_subscribe,
)
from a2a_app.redis_client import get_redis_client
from a2a_app.schemas import (
    CreateConversationBody,
    JSONRPCError,
    JSONRPCRequest,
    JSONRPCResponse,
)
from a2a_app.services import ConversationService, TaskService

logger = logging.getLogger(__name__)

api = BoltAPI(
    compression=CompressionConfig(
        backend="brotli",      # "brotli", "gzip", or "zstd"
        minimum_size=1000,     # Minimum size to compress (bytes)
        gzip_fallback=True,    # Fall back to gzip
    )
)

# Production logging config
config = LoggingConfig(
    logger_name="a2a_app",

    # Performance: Don't log every request
    # sample_rate=0.1,          # Log 10% of successful requests
    # min_duration_ms=100,      # Only log requests > 100ms

    # Skip noisy paths
    skip_paths={"/health", "/ready", "/metrics", "/favicon.ico"},
    skip_status_codes={204, 304},

    # Request logging
    request_log_fields={"method", "path", "client_ip", "user_agent"},

    # Response logging
    response_log_fields={"status_code", "duration"},

    # Security
    obfuscate_headers={"authorization", "cookie", "x-api-key"},
    obfuscate_cookies={"sessionid", "csrftoken", "jwt"},

    # Body logging (careful in production)
    log_request_body=False,
)

middleware = create_logging_middleware(
    logger_name=config.logger_name,
    skip_paths=config.skip_paths,
    sample_rate=config.sample_rate,
)

TERMINAL_STATES = {"completed", "failed", "canceled", "rejected"}


def get_agent_card() -> dict:
    """Get the agent card configuration."""
    return settings.A2A_CONFIG.get("AGENT_CARD", {})


def format_sse_event(data: dict, event_id: str | None = None) -> str:
    """Format data as SSE event."""
    event_lines = []
    if event_id:
        event_lines.append(f"id: {event_id}")
    event_lines.append(f"data: {json.dumps(data)}")
    event_lines.append("")  # Empty line to end event
    return "\n".join(event_lines) + "\n"


# ============================================
# Home / Playground
# ============================================


@api.get("")
async def playground_home(request: Request):
    """Render the A2A Playground."""
    return render(request, "playground/index.html", {"agent": get_agent_card()})


@api.get("/playground")
async def playground(request: Request):
    """Render the A2A Playground."""
    return render(request, "playground/index.html", {"agent": get_agent_card()})


# ============================================
# Agent Card Endpoints
# ============================================


@api.get("/card")
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


@api.get("/conversations")
async def list_conversations(request: Request):
    """List all conversations."""
    return {"conversations": await ConversationService.list()}


@api.post("/conversations")
async def create_conversation(request: Request, body: CreateConversationBody):
    """Create a new conversation."""
    return await ConversationService.create(body.context_id, body.agent_id)


@api.delete("/conversations/{context_id}")
async def delete_conversation(request: Request, context_id: str):
    """Delete a conversation and its tasks."""
    deleted = await ConversationService.delete(context_id)
    if not deleted:
        raise NotFound(detail=f"Conversation {context_id} not found")
    return {"success": True}


@api.get("/conversations/{context_id}")
async def get_conversation(request: Request, context_id: str):
    """Get a conversation by ID with history and stream indicator."""
    result = await ConversationService.get_detail(context_id)
    if not result:
        raise NotFound(detail=f"Conversation {context_id} not found")
    return result


# ============================================
# JSON-RPC Endpoint
# ============================================


@api.post("/rpc")
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
# SSE Stream Endpoint
# ============================================


@api.get("/rpc/{task_id}/stream")
@no_compress
async def stream_task(request: Request, task_id: str):
    """Stream events for a task using SSE."""
    last_event_id = request.headers.get("Last-Event-ID")

    async def generate():
        # Check if task exists before starting stream
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

        redis = get_redis_client()
        subscriber = RedisEventSubscriber(redis=redis)

        # Send current state if not in terminal state
        state = task.status.state
        if state not in TERMINAL_STATES:
            yield format_sse_event(
                {
                    "type": f"task.{state}",
                    "task": task.model_dump(),
                }
            )

        # Subscribe to new events
        try:
            async for event in subscriber.subscribe(task_id, last_event_id):
                event_id = event.get("_id")
                yield format_sse_event(event, event_id)

                # Stop streaming when terminal state is reached
                if event.get("type") in [f"task.{s}" for s in TERMINAL_STATES]:
                    break
        finally:
            subscriber.stop()

    return StreamingResponse(generate(), media_type="text/event-stream")
