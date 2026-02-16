"""Unit tests for A2A schemas."""

import pytest
from a2a_app.schemas import (
    Message,
    Task,
    TaskStatus,
    Conversation,
    JSONRPCRequest,
    JSONRPCResponse,
    JSONRPCError,
    TaskSendParams,
    TextPart,
)


class TestTextPartSchema:
    """Tests for TextPart serializer."""

    def test_valid_text_part(self):
        part = TextPart(type="text", text="Hello")
        assert part.text == "Hello"
        assert part.type == "text"

    def test_text_part_defaults(self):
        part = TextPart(text="Hello")
        assert part.type == "text"


class TestMessageSchema:
    """Tests for Message serializer."""

    def test_valid_message(self):
        msg = Message(role="user", parts=[TextPart(text="Hello")])
        assert msg.role == "user"
        assert len(msg.parts) == 1

    def test_message_without_messageId(self):
        msg = Message(role="user", parts=[TextPart(text="Hi")])
        assert msg.messageId is None

    def test_valid_agent_role(self):
        msg = Message(role="agent", parts=[TextPart(text="Test")])
        assert msg.role == "agent"


class TestJSONRPCSchemas:
    """Tests for JSON-RPC request/response schemas."""

    def test_valid_request(self):
        req = JSONRPCRequest(
            method="tasks/send",
            params={"message": {"role": "user", "parts": [{"type": "text", "text": "Hi"}]}},
            id=1,
        )
        assert req.jsonrpc == "2.0"
        assert req.method == "tasks/send"

    def test_request_without_id(self):
        req = JSONRPCRequest(method="tasks/get", params={"id": "task-1"})
        assert req.id is None

    def test_response_with_error(self):
        resp = JSONRPCResponse(
            jsonrpc="2.0",
            error=JSONRPCError(code=-32601, message="Method not found"),
            id=1,
        )
        assert resp.error.code == -32601

    def test_response_with_result(self):
        resp = JSONRPCResponse(
            jsonrpc="2.0",
            result={"id": "task-1", "status": {"state": "submitted"}},
            id=1,
        )
        assert resp.result["id"] == "task-1"


class TestTaskSendParamsSchema:
    """Tests for TaskSendParams validation."""

    def test_valid_params(self):
        params = TaskSendParams.model_validate(
            {
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": "Hello"}],
                }
            }
        )
        assert params.message.role == "user"

    def test_with_custom_task_id(self):
        params = TaskSendParams.model_validate(
            {
                "id": "custom-task-id",
                "message": {"role": "user", "parts": [{"type": "text", "text": "Hi"}]},
            }
        )
        assert params.id == "custom-task-id"

    def test_with_context_id(self):
        params = TaskSendParams.model_validate(
            {
                "contextId": "ctx-123",
                "message": {"role": "user", "parts": [{"type": "text", "text": "Hi"}]},
            }
        )
        assert params.contextId == "ctx-123"

    def test_with_metadata(self):
        params = TaskSendParams.model_validate(
            {
                "message": {"role": "user", "parts": [{"type": "text", "text": "Hi"}]},
                "metadata": {"source": "test"},
            }
        )
        assert params.metadata["source"] == "test"


class TestTaskSchema:
    """Tests for Task serializer."""

    def test_valid_task(self):
        task = Task(
            id="task-1",
            contextId="ctx-1",
            status=TaskStatus(state="submitted"),
            history=[],
            artifacts=[],
        )
        assert task.id == "task-1"
        assert task.status.state == "submitted"

    def test_task_with_history(self):
        task = Task(
            id="task-1",
            status=TaskStatus(state="working"),
            history=[Message(role="user", parts=[TextPart(text="Hello")])],
        )
        assert len(task.history) == 1

    def test_task_with_artifacts(self):
        task = Task(
            id="task-1",
            status=TaskStatus(state="completed"),
            artifacts=[{"name": "result", "parts": []}],
        )
        assert len(task.artifacts) == 1


class TestConversationSchema:
    """Tests for Conversation serializer."""

    def test_valid_conversation(self):
        conv = Conversation(
            context_id="ctx-1",
            agent_id="default",
            is_streaming=False,
        )
        assert conv.context_id == "ctx-1"
        assert conv.is_streaming is False

    def test_conversation_with_task_count(self):
        conv = Conversation(
            context_id="ctx-1",
            agent_id="default",
            task_count=5,
        )
        assert conv.task_count == 5
