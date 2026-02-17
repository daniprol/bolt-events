"""A2A Schemas - msgspec Serializers for domain and API."""

from datetime import datetime
from typing import TYPE_CHECKING

from django_bolt.serializers import Serializer, field

if TYPE_CHECKING:
    from a2a_app.models import Conversation as ConversationModel
    from a2a_app.models import Task as TaskModel

# ============================================
# Domain Models (used for API responses)
# ============================================


class TextPart(Serializer):
    type: str = "text"
    text: str


class Message(Serializer):
    messageId: str | None = None
    role: str
    parts: list[TextPart]


class TaskStatus(Serializer):
    state: str
    message: Message | None = None


class Task(Serializer):
    id: str
    contextId: str | None = None
    status: TaskStatus
    history: list[Message] = field(default_factory=list)
    artifacts: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    createdAt: datetime | None = None
    updatedAt: datetime | None = None


class Conversation(Serializer):
    context_id: str
    agent_id: str
    title: str = ""
    is_streaming: bool = False
    task_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ConversationDetail(Serializer):
    context_id: str
    agent_id: str
    is_streaming: bool = False
    stream_url: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    tasks: list[Task] = field(default_factory=list)
    messages: list[dict] = field(default_factory=list)


# ============================================
# API Request/Response Schemas
# ============================================


class JSONRPCError(Serializer):
    code: int
    message: str
    data: dict | None = None


class JSONRPCRequest(Serializer):
    jsonrpc: str = "2.0"
    method: str
    params: dict | None = None
    id: str | int | None = None


class JSONRPCResponse(Serializer):
    jsonrpc: str = "2.0"
    result: dict | None = None
    error: JSONRPCError | None = None
    id: str | int | None = None


class TaskSendParams(Serializer):
    id: str | None = None
    contextId: str | None = None
    message: Message
    metadata: dict = field(default_factory=dict)


class TaskIdParams(Serializer):
    id: str


class TaskGetParams(Serializer):
    id: str
    historyLength: int | None = None


class TaskSendResponse(Serializer):
    id: str
    contextId: str
    status: TaskStatus
    history: list[Message]


class TaskSubscribeResponse(Serializer):
    task: TaskSendResponse
    streamUrl: str


# ============================================
# API Input Schemas (for type hints in endpoints)
# ============================================


class CreateConversationBody(Serializer):
    context_id: str | None = None
    agent_id: str = "default"


# ============================================
# Helper to convert ORM to Schema
# ============================================


def task_from_orm(task: "TaskModel") -> Task:
    """Convert A2ATask ORM model to Task schema."""
    return Task(
        id=task.task_id,
        contextId=task.context_id,
        status=TaskStatus(
            state=task.status_state,
            message=None,
        ),
        history=task.history or [],
        artifacts=task.artifacts or [],
        metadata=task.metadata or {},
        createdAt=task.created_at,
        updatedAt=task.updated_at,
    )


def conversation_from_orm(conv: "ConversationModel", task_count: int = 0, title: str = "") -> Conversation:
    """Convert Conversation ORM model to Conversation schema."""
    return Conversation(
        context_id=conv.context_id,
        agent_id=conv.agent_id,
        title=title,
        is_streaming=conv.is_streaming,
        task_count=task_count,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )
