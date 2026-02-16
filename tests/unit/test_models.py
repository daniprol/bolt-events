"""Unit tests for Django models."""

import pytest
from django.db import IntegrityError
from a2a_app.models import A2ATask, Conversation


@pytest.mark.django_db
class TestA2ATaskModel:
    """Tests for A2ATask model."""

    async def test_create_task(self):
        task = await A2ATask.objects.acreate(
            task_id="task-1",
            context_id="ctx-1",
            status_state="submitted",
        )
        assert task.task_id == "task-1"
        assert task.status_state == "submitted"

    async def test_task_timestamps(self):
        task = await A2ATask.objects.acreate(
            task_id="task-2",
            context_id="ctx-1",
        )
        assert task.created_at is not None
        assert task.updated_at is not None

    async def test_task_with_history(self):
        history = [
            {"role": "user", "parts": [{"type": "text", "text": "Hi"}]},
            {"role": "agent", "parts": [{"type": "text", "text": "Hello"}]},
        ]
        task = await A2ATask.objects.acreate(
            task_id="task-3",
            history=history,
        )
        assert len(task.history) == 2

    async def test_task_with_artifacts(self):
        artifacts = [
            {"name": "result", "parts": [{"type": "data", "data": {"key": "value"}}]},
        ]
        task = await A2ATask.objects.acreate(
            task_id="task-4",
            artifacts=artifacts,
        )
        assert len(task.artifacts) == 1

    async def test_to_dict(self):
        task = await A2ATask.objects.acreate(
            task_id="task-5",
            context_id="ctx-1",
            status_state="completed",
        )
        d = task.to_dict()
        assert d["id"] == "task-5"
        assert d["status"]["state"] == "completed"

    async def test_unique_task_id(self):
        await A2ATask.objects.acreate(task_id="task-unique", context_id="ctx-1")
        with pytest.raises(IntegrityError):
            await A2ATask.objects.acreate(task_id="task-unique", context_id="ctx-1")


@pytest.mark.django_db
class TestConversationModel:
    """Tests for Conversation model."""

    async def test_create_conversation(self):
        conv = await Conversation.objects.acreate(
            context_id="ctx-1",
            agent_id="default",
        )
        assert conv.context_id == "ctx-1"
        assert conv.is_streaming is False

    async def test_unique_context_id(self):
        await Conversation.objects.acreate(context_id="ctx-2", agent_id="default")
        with pytest.raises(IntegrityError):
            await Conversation.objects.acreate(context_id="ctx-2", agent_id="default")

    async def test_is_streaming_default(self):
        conv = await Conversation.objects.acreate(
            context_id="ctx-3",
            agent_id="default",
        )
        assert conv.is_streaming is False

    async def test_is_streaming_set_true(self):
        conv = await Conversation.objects.acreate(
            context_id="ctx-4",
            agent_id="default",
            is_streaming=True,
        )
        assert conv.is_streaming is True

    async def test_with_metadata(self):
        conv = await Conversation.objects.acreate(
            context_id="ctx-5",
            agent_id="default",
            metadata={"key": "value"},
        )
        assert conv.metadata["key"] == "value"
