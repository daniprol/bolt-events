"""Integration tests for services."""

import pytest
from a2a_app.services import TaskService, ConversationService
from a2a_app.schemas import Message, TextPart


@pytest.mark.django_db
class TestTaskService:
    """Tests for TaskService."""

    async def test_create_task(self):
        msg = Message(role="user", parts=[TextPart(text="Hello")])
        task = await TaskService.create(msg)

        assert task.id.startswith("task-")
        assert task.contextId == task.id
        assert task.status.state == "submitted"
        assert len(task.history) == 1

    async def test_create_task_with_context(self):
        msg = Message(role="user", parts=[TextPart(text="Hello")])
        task = await TaskService.create(msg, context_id="ctx-123")

        assert task.contextId == "ctx-123"

    async def test_get_task(self):
        msg = Message(role="user", parts=[TextPart(text="Hi")])
        task = await TaskService.create(msg)

        retrieved = await TaskService.get(task.id)
        assert retrieved is not None
        assert retrieved.id == task.id

    async def test_get_nonexistent_task(self):
        result = await TaskService.get("nonexistent")
        assert result is None

    async def test_update_status(self):
        msg = Message(role="user", parts=[TextPart(text="Hi")])
        task = await TaskService.create(msg)

        await TaskService.update_status(task.id, "working")

        updated = await TaskService.get(task.id)
        assert updated.status.state == "working"

    async def test_append_message(self):
        msg = Message(role="user", parts=[TextPart(text="Hi")])
        task = await TaskService.create(msg)

        await TaskService.append_message(
            task.id, {"role": "agent", "parts": [{"type": "text", "text": "Hello"}]}
        )

        updated = await TaskService.get(task.id)
        assert len(updated.history) == 2

    async def test_add_artifact(self):
        msg = Message(role="user", parts=[TextPart(text="Hi")])
        task = await TaskService.create(msg)

        await TaskService.add_artifact(task.id, {"name": "test", "parts": []})

        updated = await TaskService.get(task.id)
        assert len(updated.artifacts) == 1

    async def test_get_by_context(self):
        msg1 = Message(role="user", parts=[TextPart(text="First")])
        task1 = await TaskService.create(msg1, context_id="ctx-shared")

        msg2 = Message(role="user", parts=[TextPart(text="Second")])
        await TaskService.create(msg2, context_id="ctx-shared")

        tasks = await TaskService.get_by_context("ctx-shared")
        assert len(tasks) == 2


@pytest.mark.django_db
class TestConversationService:
    """Tests for ConversationService."""

    async def test_create_conversation(self):
        conv = await ConversationService.create()

        assert conv.context_id.startswith("ctx-")
        assert conv.agent_id == "default"

    async def test_create_conversation_with_id(self):
        conv = await ConversationService.create(context_id="my-conv")
        assert conv.context_id == "my-conv"

    async def test_list_conversations_empty(self):
        convs = await ConversationService.list()
        assert convs == []

    async def test_list_conversations(self):
        await ConversationService.create(context_id="ctx-1")
        await ConversationService.create(context_id="ctx-2")

        convs = await ConversationService.list()
        assert len(convs) == 2

    async def test_get_conversation(self):
        created = await ConversationService.create(context_id="ctx-test")

        retrieved = await ConversationService.get("ctx-test")
        assert retrieved is not None
        assert retrieved.context_id == "ctx-test"

    async def test_delete_conversation(self):
        await ConversationService.create(context_id="ctx-delete")

        result = await ConversationService.delete("ctx-delete")
        assert result is True

        conv = await ConversationService.get("ctx-delete")
        assert conv is None

    async def test_get_detail(self):
        await ConversationService.create(context_id="ctx-detail")
        msg = Message(role="user", parts=[TextPart(text="Hello")])
        await TaskService.create(msg, context_id="ctx-detail")

        detail = await ConversationService.get_detail("ctx-detail")
        assert detail is not None
        assert detail.context_id == "ctx-detail"
        assert len(detail.tasks) == 1
        assert len(detail.messages) > 0
