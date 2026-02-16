"""E2E tests for API endpoints."""

import pytest


@pytest.mark.django_db
class TestConversationAPI:
    """E2E tests for conversation endpoints."""

    async def test_list_conversations_empty(self, client):
        """Test listing conversations when none exist."""
        response = await client.get("/agent/conversations/")
        assert response.status_code == 200
        data = response.json()
        assert "conversations" in data

    async def test_create_conversation(self, client):
        """Test creating a new conversation."""
        response = await client.post(
            "/agent/conversations/",
            json={"agent_id": "test-agent"},
        )
        assert response.status_code == 201
        data = response.json()
        assert "context_id" in data

    async def test_create_conversation_with_id(self, client):
        """Test creating a conversation with custom ID."""
        response = await client.post(
            "/agent/conversations/",
            json={"context_id": "my-custom-id"},
        )
        assert response.status_code == 201
        assert response.json()["context_id"] == "my-custom-id"

    async def test_get_conversation(self, client):
        """Test getting a conversation by ID."""
        create_resp = await client.post("/agent/conversations/", json={})
        ctx_id = create_resp.json()["context_id"]

        response = await client.get(f"/agent/conversations/{ctx_id}/")
        assert response.status_code == 200
        data = response.json()
        assert data["context_id"] == ctx_id

    async def test_get_nonexistent_conversation(self, client):
        """Test getting a non-existent conversation."""
        response = await client.get("/agent/conversations/nonexistent/")
        assert response.status_code == 404

    async def test_delete_conversation(self, client):
        """Test deleting a conversation."""
        create_resp = await client.post("/agent/conversations/", json={})
        ctx_id = create_resp.json()["context_id"]

        response = await client.delete(f"/agent/conversations/{ctx_id}/")
        assert response.status_code == 200

        get_resp = await client.get(f"/agent/conversations/{ctx_id}/")
        assert get_resp.status_code == 404


@pytest.mark.django_db
class TestJSONRPCAPI:
    """E2E tests for JSON-RPC endpoint."""

    async def test_tasks_send(self, client):
        """Test tasks/send method."""
        response = await client.post(
            "/agent/rpc/",
            json={
                "jsonrpc": "2.0",
                "method": "tasks/send",
                "params": {
                    "message": {
                        "role": "user",
                        "parts": [{"type": "text", "text": "Hello"}],
                    }
                },
                "id": 1,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "result" in data
        assert data["result"]["id"].startswith("task-")

    async def test_tasks_send_with_id(self, client):
        """Test tasks/send with custom task ID."""
        response = await client.post(
            "/agent/rpc/",
            json={
                "jsonrpc": "2.0",
                "method": "tasks/send",
                "params": {
                    "id": "my-custom-task",
                    "message": {"role": "user", "parts": [{"type": "text", "text": "Hi"}]},
                },
                "id": 1,
            },
        )
        assert response.json()["result"]["id"] == "my-custom-task"

    async def test_tasks_get(self, client):
        """Test tasks/get method."""
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

        response = await client.post(
            "/agent/rpc/",
            json={
                "jsonrpc": "2.0",
                "method": "tasks/get",
                "params": {"id": task_id},
                "id": 2,
            },
        )
        data = response.json()
        assert data["result"]["id"] == task_id

    async def test_tasks_get_nonexistent(self, client):
        """Test getting a non-existent task."""
        response = await client.post(
            "/agent/rpc/",
            json={
                "jsonrpc": "2.0",
                "method": "tasks/get",
                "params": {"id": "nonexistent"},
                "id": 1,
            },
        )
        assert response.status_code == 200
        assert "error" in response.json()

    async def test_method_not_found(self, client):
        """Test calling a non-existent method."""
        response = await client.post(
            "/agent/rpc/",
            json={
                "jsonrpc": "2.0",
                "method": "tasks/invalid",
                "params": {},
                "id": 1,
            },
        )
        data = response.json()
        assert data["error"]["code"] == -32601

    async def test_tasks_send_subscribe(self, client):
        """Test tasks/sendSubscribe method."""
        response = await client.post(
            "/agent/rpc/",
            json={
                "jsonrpc": "2.0",
                "method": "tasks/sendSubscribe",
                "params": {"message": {"role": "user", "parts": [{"type": "text", "text": "Hi"}]}},
                "id": 1,
            },
        )
        data = response.json()
        assert "streamUrl" in data["result"]
        assert data["result"]["streamUrl"].endswith("/stream/")

    async def test_tasks_cancel(self, client):
        """Test tasks/cancel method."""
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

        response = await client.post(
            "/agent/rpc/",
            json={
                "jsonrpc": "2.0",
                "method": "tasks/cancel",
                "params": {"id": task_id},
                "id": 2,
            },
        )
        assert response.status_code in [200, 400]

    async def test_tasks_resubscribe(self, client):
        """Test tasks/resubscribe method."""
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

        response = await client.post(
            "/agent/rpc/",
            json={
                "jsonrpc": "2.0",
                "method": "tasks/resubscribe",
                "params": {"id": task_id},
                "id": 2,
            },
        )
        data = response.json()
        assert "streamUrl" in data["result"]


@pytest.mark.django_db
class TestAgentCard:
    """E2E tests for agent card endpoints."""

    async def test_get_agent_card(self, client):
        """Test getting the agent card."""
        response = await client.get("/agent/card/")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "capabilities" in data

    async def test_get_agent_card_well_known(self, client):
        """Test getting the agent card from well-known location."""
        response = await client.get("/agent/.well-known/agent-card.json")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
