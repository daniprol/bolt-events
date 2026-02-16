"""E2E tests for SSE streaming - critical for testing event streaming."""

import pytest
import asyncio


@pytest.mark.django_db
class TestSSEStream:
    """E2E tests for SSE event streaming."""

    async def test_stream_nonexistent_task(self, client):
        """Test streaming from non-existent task returns error event."""
        response = await client.get("/agent/rpc/nonexistent/stream/")
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

        content = b""
        async for chunk in response.streaming_content:
            content += chunk
            if b"TASK_NOT_FOUND" in content:
                break

        assert b"TASK_NOT_FOUND" in content

    async def test_stream_completes_after_task_done(self, client):
        """Test stream completes after task finishes."""
        send_resp = await client.post(
            "/agent/rpc/",
            json={
                "jsonrpc": "2.0",
                "method": "tasks/send",
                "params": {
                    "message": {"role": "user", "parts": [{"type": "text", "text": "Quick"}]}
                },
                "id": 1,
            },
        )
        task_id = send_resp.json()["result"]["id"]

        response = await client.get(f"/agent/rpc/{task_id}/stream/")
        assert response.status_code == 200

        content = b""
        async for chunk in response.streaming_content:
            content += chunk
            if b"task.completed" in content:
                break

        assert b"task.completed" in content

    async def test_resubscribe_with_last_event_id(self, client):
        """Test resubscription with Last-Event-ID header."""
        send_resp = await client.post(
            "/agent/rpc/",
            json={
                "jsonrpc": "2.0",
                "method": "tasks/send",
                "params": {
                    "message": {"role": "user", "parts": [{"type": "text", "text": "Test"}]}
                },
                "id": 1,
            },
        )
        task_id = send_resp.json()["result"]["id"]

        response1 = await client.get(f"/agent/rpc/{task_id}/stream/")
        content1 = b""
        async for chunk in response1.streaming_content:
            content1 += chunk
            if b"task.message" in content1:
                break

        response2 = await client.get(
            f"/agent/rpc/{task_id}/stream/",
            headers={"Last-Event-ID": "0"},
        )
        assert response2.status_code == 200


@pytest.mark.django_db
class TestSSEEventTypes:
    """Test different event types in SSE stream."""

    async def test_task_working_event(self, client):
        """Test task.working event is emitted."""
        send_resp = await client.post(
            "/agent/rpc/",
            json={
                "jsonrpc": "2.0",
                "method": "tasks/send",
                "params": {"message": {"role": "user", "parts": [{"type": "text", "text": "Hi"}]}},
                "id": 1,
            },
        )
        task_id = send_resp.json()["result"]["id"]

        response = await client.get(f"/agent/rpc/{task_id}/stream/")

        content = b""
        async for chunk in response.streaming_content:
            content += chunk
            if b"task.working" in content:
                break

        assert b"task.working" in content

    async def test_task_message_events(self, client):
        """Test task.message events are emitted."""
        send_resp = await client.post(
            "/agent/rpc/",
            json={
                "jsonrpc": "2.0",
                "method": "tasks/send",
                "params": {
                    "message": {"role": "user", "parts": [{"type": "text", "text": "Hello"}]}
                },
                "id": 1,
            },
        )
        task_id = send_resp.json()["result"]["id"]

        response = await client.get(f"/agent/rpc/{task_id}/stream/")

        content = b""
        async for chunk in response.streaming_content:
            content += chunk
            if b"task.message" in content:
                break

        assert b"task.message" in content

    async def test_task_artifact_event(self, client):
        """Test task.artifact event is emitted."""
        send_resp = await client.post(
            "/agent/rpc/",
            json={
                "jsonrpc": "2.0",
                "method": "tasks/send",
                "params": {
                    "message": {"role": "user", "parts": [{"type": "text", "text": "Generate"}]}
                },
                "id": 1,
            },
        )
        task_id = send_resp.json()["result"]["id"]

        response = await client.get(f"/agent/rpc/{task_id}/stream/")

        content = b""
        async for chunk in response.streaming_content:
            content += chunk
            if b"task.artifact" in content:
                break

        assert b"task.artifact" in content

    async def test_task_completed_event(self, client):
        """Test task.completed event is emitted."""
        send_resp = await client.post(
            "/agent/rpc/",
            json={
                "jsonrpc": "2.0",
                "method": "tasks/send",
                "params": {
                    "message": {"role": "user", "parts": [{"type": "text", "text": "Done"}]}
                },
                "id": 1,
            },
        )
        task_id = send_resp.json()["result"]["id"]

        response = await client.get(f"/agent/rpc/{task_id}/stream/")

        content = b""
        async for chunk in response.streaming_content:
            content += chunk
            if b"task.completed" in content:
                break

        assert b"task.completed" in content


@pytest.mark.django_db
class TestSSEEdgeCases:
    """Edge case tests for SSE streaming."""

    async def test_multiple_rapid_connections(self, client):
        """Test multiple rapid stream connections to same task."""
        send_resp = await client.post(
            "/agent/rpc/",
            json={
                "jsonrpc": "2.0",
                "method": "tasks/send",
                "params": {
                    "message": {"role": "user", "parts": [{"type": "text", "text": "Test"}]}
                },
                "id": 1,
            },
        )
        task_id = send_resp.json()["result"]["id"]

        streams = []
        for _ in range(5):
            response = await client.get(f"/agent/rpc/{task_id}/stream/")
            streams.append(response)

        assert all(s.status_code == 200 for s in streams)

    async def test_stream_content_type(self, client):
        """Test SSE stream returns correct content type."""
        send_resp = await client.post(
            "/agent/rpc/",
            json={
                "jsonrpc": "2.0",
                "method": "tasks/send",
                "params": {
                    "message": {"role": "user", "parts": [{"type": "text", "text": "Test"}]}
                },
                "id": 1,
            },
        )
        task_id = send_resp.json()["result"]["id"]

        response = await client.get(f"/agent/rpc/{task_id}/stream/")

        assert response.headers["content-type"] == "text/event-stream; charset=utf-8"

    async def test_sse_event_format(self, client):
        """Test SSE events are properly formatted."""
        send_resp = await client.post(
            "/agent/rpc/",
            json={
                "jsonrpc": "2.0",
                "method": "tasks/send",
                "params": {
                    "message": {"role": "user", "parts": [{"type": "text", "text": "Test"}]}
                },
                "id": 1,
            },
        )
        task_id = send_resp.json()["result"]["id"]

        response = await client.get(f"/agent/rpc/{task_id}/stream/")

        content = b""
        async for chunk in response.streaming_content:
            content += chunk
            if b"event:" in content:
                break

        assert b"event:" in content
        assert b"data:" in content


@pytest.mark.django_db
class TestConversationStreamingStatus:
    """Test conversation streaming status changes."""

    async def test_conversation_not_streaming_after_send(self, client):
        """Test conversation is not marked as streaming after tasks/send."""
        create_resp = await client.post("/agent/conversations/", json={})
        ctx_id = create_resp.json()["context_id"]

        await client.post(
            "/agent/rpc/",
            json={
                "jsonrpc": "2.0",
                "method": "tasks/send",
                "params": {
                    "message": {"role": "user", "parts": [{"type": "text", "text": "Test"}]},
                    "contextId": ctx_id,
                },
                "id": 1,
            },
        )

        conv_resp = await client.get(f"/agent/conversations/{ctx_id}/")
        conv = conv_resp.json()

        assert conv["is_streaming"] is False

    async def test_conversation_streaming_after_sendSubscribe(self, client):
        """Test conversation is marked as streaming after tasks/sendSubscribe."""
        create_resp = await client.post("/agent/conversations/", json={})
        ctx_id = create_resp.json()["context_id"]

        await client.post(
            "/agent/rpc/",
            json={
                "jsonrpc": "2.0",
                "method": "tasks/sendSubscribe",
                "params": {
                    "message": {"role": "user", "parts": [{"type": "text", "text": "Test"}]},
                    "contextId": ctx_id,
                },
                "id": 1,
            },
        )

        conv_resp = await client.get(f"/agent/conversations/{ctx_id}/")
        conv = conv_resp.json()

        assert conv["is_streaming"] is True
