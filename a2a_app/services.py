"""A2A Services - Business logic layer."""

import logging
import uuid

from a2a_app.models import A2ATask, Conversation
from a2a_app.schemas import (
    Conversation as ConversationSchema,
)
from a2a_app.schemas import (
    ConversationDetail,
    Message,
    Task,
    conversation_from_orm,
    task_from_orm,
)

logger = logging.getLogger(__name__)

TERMINAL_STATES = {"completed", "failed", "canceled", "rejected"}


class TaskService:
    """Service for task operations."""

    @staticmethod
    async def get(task_id: str) -> Task | None:
        """Get a task by ID."""
        try:
            task = await A2ATask.objects.aget(task_id=task_id)
            return task_from_orm(task)
        except A2ATask.DoesNotExist:
            return None

    @staticmethod
    async def get_by_context(context_id: str, limit: int = 100) -> list[Task]:
        """Get tasks by context ID."""
        tasks = []
        async for task in A2ATask.objects.filter(context_id=context_id).order_by("-created_at")[
            :limit
        ]:
            tasks.append(task_from_orm(task))
        return tasks

    @staticmethod
    async def create(message: Message, context_id: str | None = None) -> Task:
        """Create a new task."""
        task_id = f"task-{uuid.uuid4().hex[:8]}"
        ctx_id = context_id or task_id

        message_data = {
            "messageId": message.messageId or f"msg-{uuid.uuid4().hex[:8]}",
            "role": message.role,
            "parts": [{"type": p.type, "text": p.text} for p in message.parts],
        }

        task = await A2ATask.objects.acreate(
            task_id=task_id,
            context_id=ctx_id,
            status_state="submitted",
            history=[message_data],
            artifacts=[],
            metadata={},
        )

        return task_from_orm(task)

    @staticmethod
    async def update_status(task_id: str, state: str, message: dict | None = None) -> bool:
        """Update task status."""
        rows = await A2ATask.objects.filter(task_id=task_id).aupdate(
            status_state=state,
            status_message=message,
        )
        return rows > 0

    @staticmethod
    async def append_message(task_id: str, message: dict) -> bool:
        """Append a message to task history."""
        try:
            task = await A2ATask.objects.aget(task_id=task_id)
            history = task.history or []
            history.append(message)
            await A2ATask.objects.filter(task_id=task_id).aupdate(history=history)
            return True
        except A2ATask.DoesNotExist:
            return False

    @staticmethod
    async def add_artifact(task_id: str, artifact: dict) -> bool:
        """Add an artifact to a task."""
        try:
            task = await A2ATask.objects.aget(task_id=task_id)
            artifacts = task.artifacts or []
            artifacts.append(artifact)
            await A2ATask.objects.filter(task_id=task_id).aupdate(artifacts=artifacts)
            return True
        except A2ATask.DoesNotExist:
            return False


class ConversationService:
    """Service for conversation operations."""

    @staticmethod
    async def list() -> list[ConversationSchema]:
        """List all conversations with metadata."""
        conversations = []
        async for conv in Conversation.objects.order_by("-updated_at"):
            first_task = (
                await A2ATask.objects.filter(context_id=conv.context_id)
                .order_by("created_at")
                .afirst()
            )

            title = "New Conversation"
            if first_task and first_task.history:
                first_msg = first_task.history[0]
                parts = first_msg.get("parts", [])
                if parts:
                    text = parts[0].get("text", "")
                    title = text[:50] if text else "New Conversation"

            task_count = await A2ATask.objects.filter(context_id=conv.context_id).acount()

            conversations.append(conversation_from_orm(conv, task_count, title))

        return conversations

    @staticmethod
    async def get(context_id: str) -> ConversationSchema | None:
        """Get a conversation by ID."""
        try:
            conv = await Conversation.objects.aget(context_id=context_id)
            task_count = await A2ATask.objects.filter(context_id=context_id).acount()
            return conversation_from_orm(conv, task_count)
        except Conversation.DoesNotExist:
            return None

    @staticmethod
    async def get_detail(context_id: str) -> ConversationDetail | None:
        """Get conversation with tasks and messages."""
        try:
            conv = await Conversation.objects.aget(context_id=context_id)
        except Conversation.DoesNotExist:
            return None

        tasks = []
        async for task in A2ATask.objects.filter(context_id=context_id).order_by("-created_at"):
            tasks.append(task_from_orm(task))

        messages = []
        for task in reversed(tasks):
            for msg in task.history:
                messages.append(
                    {
                        "task_id": task.id,
                        "role": msg.get("role"),
                        "parts": msg.get("parts", []),
                    }
                )

        return ConversationDetail(
            context_id=conv.context_id,
            agent_id=conv.agent_id,
            is_streaming=conv.is_streaming,
            stream_url=conv.stream_url,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
            tasks=tasks,
            messages=messages,
        )

    @staticmethod
    async def create(
        context_id: str | None = None, agent_id: str = "default"
    ) -> ConversationSchema:
        """Create a new conversation."""
        ctx_id = context_id or f"ctx-{uuid.uuid4().hex[:8]}"
        conv, _ = await Conversation.objects.aget_or_create(
            context_id=ctx_id,
            defaults={"agent_id": agent_id, "is_streaming": False},
        )
        return conversation_from_orm(conv)

    @staticmethod
    async def delete(context_id: str) -> bool:
        """Delete a conversation and its tasks."""
        await A2ATask.objects.filter(context_id=context_id).adelete()
        rows, _ = await Conversation.objects.filter(context_id=context_id).adelete()
        return rows > 0
