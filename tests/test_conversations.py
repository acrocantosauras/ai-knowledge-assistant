"""Tests for Conversation API."""

from fastapi.testclient import TestClient

from app.main import create_app


def test_create_conversation_requires_authentication() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/conversations/",
        json={"title": "Test Conversation"},
    )

    assert response.status_code in (401, 422)


def test_create_conversation() -> None:
    client = TestClient(create_app())

    # Register user
    register = client.post(
        "/api/v1/auth/register",
        json={
            "email": "conv-test@example.com",
            "password": "TestPassword123!",
            "display_name": "Conv Test",
        },
    )
    assert register.status_code == 201

    # Login
    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": "conv-test@example.com",
            "password": "TestPassword123!",
        },
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    # Create conversation
    response = client.post(
        "/api/v1/conversations/",
        json={"title": "Test Conversation"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Test Conversation"
    assert data["status"] == "active"
    assert "id" in data
    assert "created_at" in data


def test_list_conversations() -> None:
    client = TestClient(create_app())

    # Register user
    register = client.post(
        "/api/v1/auth/register",
        json={
            "email": "conv-list@example.com",
            "password": "TestPassword123!",
            "display_name": "Conv List",
        },
    )
    assert register.status_code == 201

    # Login
    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": "conv-list@example.com",
            "password": "TestPassword123!",
        },
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    # Create a few conversations
    for i in range(3):
        response = client.post(
            "/api/v1/conversations/",
            json={"title": f"Conversation {i}"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 201

    # List conversations
    response = client.get(
        "/api/v1/conversations/",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert len(data["conversations"]) == 3
    for conv in data["conversations"]:
        assert "id" in conv
        assert "title" in conv
        assert "message_count" in conv


def test_get_conversation() -> None:
    client = TestClient(create_app())

    # Register user
    register = client.post(
        "/api/v1/auth/register",
        json={
            "email": "conv-get@example.com",
            "password": "TestPassword123!",
            "display_name": "Conv Get",
        },
    )
    assert register.status_code == 201

    # Login
    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": "conv-get@example.com",
            "password": "TestPassword123!",
        },
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    # Create conversation
    create_resp = client.post(
        "/api/v1/conversations/",
        json={"title": "Test Conversation"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_resp.status_code == 201
    conv_id = create_resp.json()["id"]

    # Get conversation
    response = client.get(
        f"/api/v1/conversations/{conv_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == conv_id
    assert data["title"] == "Test Conversation"
    assert "messages" in data
    assert isinstance(data["messages"], list)


def test_get_conversation_not_found() -> None:
    client = TestClient(create_app())

    # Register user
    register = client.post(
        "/api/v1/auth/register",
        json={
            "email": "conv-notfound@example.com",
            "password": "TestPassword123!",
            "display_name": "Conv NotFound",
        },
    )
    assert register.status_code == 201

    # Login
    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": "conv-notfound@example.com",
            "password": "TestPassword123!",
        },
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    # Get non-existent conversation
    response = client.get(
        "/api/v1/conversations/00000000-0000-0000-0000-000000000000",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


def test_update_conversation() -> None:
    client = TestClient(create_app())

    # Register user
    register = client.post(
        "/api/v1/auth/register",
        json={
            "email": "conv-update@example.com",
            "password": "TestPassword123!",
            "display_name": "Conv Update",
        },
    )
    assert register.status_code == 201

    # Login
    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": "conv-update@example.com",
            "password": "TestPassword123!",
        },
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    # Create conversation
    create_resp = client.post(
        "/api/v1/conversations/",
        json={"title": "Original Title"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_resp.status_code == 201
    conv_id = create_resp.json()["id"]

    # Update conversation
    response = client.put(
        f"/api/v1/conversations/{conv_id}",
        json={"title": "Updated Title", "status": "archived"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Updated Title"
    assert data["status"] == "archived"


def test_delete_conversation() -> None:
    client = TestClient(create_app())

    # Register user
    register = client.post(
        "/api/v1/auth/register",
        json={
            "email": "conv-delete@example.com",
            "password": "TestPassword123!",
            "display_name": "Conv Delete",
        },
    )
    assert register.status_code == 201

    # Login
    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": "conv-delete@example.com",
            "password": "TestPassword123!",
        },
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    # Create conversation
    create_resp = client.post(
        "/api/v1/conversations/",
        json={"title": "To Delete"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_resp.status_code == 201
    conv_id = create_resp.json()["id"]

    # Delete conversation
    response = client.delete(
        f"/api/v1/conversations/{conv_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 204

    # Verify it's deleted
    get_resp = client.get(
        f"/api/v1/conversations/{conv_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_resp.status_code == 404


def test_cross_user_conversation_isolation() -> None:
    """Test that users cannot access each other's conversations."""
    client = TestClient(create_app())

    # User 1
    register1 = client.post(
        "/api/v1/auth/register",
        json={
            "email": "user1@example.com",
            "password": "TestPassword123!",
            "display_name": "User 1",
        },
    )
    assert register1.status_code == 201
    login1 = client.post(
        "/api/v1/auth/login",
        json={"email": "user1@example.com", "password": "TestPassword123!"},
    )
    token1 = login1.json()["access_token"]

    # User 2
    register2 = client.post(
        "/api/v1/auth/register",
        json={
            "email": "user2@example.com",
            "password": "TestPassword123!",
            "display_name": "User 2",
        },
    )
    assert register2.status_code == 201
    login2 = client.post(
        "/api/v1/auth/login",
        json={"email": "user2@example.com", "password": "TestPassword123!"},
    )
    token2 = login2.json()["access_token"]

    # User 1 creates conversation
    create_resp = client.post(
        "/api/v1/conversations/",
        json={"title": "User 1's Conversation"},
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert create_resp.status_code == 201
    conv_id = create_resp.json()["id"]

    # User 2 tries to access User 1's conversation
    response = client.get(
        f"/api/v1/conversations/{conv_id}",
        headers={"Authorization": f"Bearer {token2}"},
    )

    assert response.status_code == 404

    # User 2 lists conversations - should be empty
    response = client.get(
        "/api/v1/conversations/",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert response.status_code == 200
    assert response.json()["total"] == 0