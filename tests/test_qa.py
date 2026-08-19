"""Tests for QA API endpoints."""

from fastapi.testclient import TestClient

from app.main import create_app


def test_ask_question_requires_authentication() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/qa/ask",
        json={"question": "What is the capital of France?"},
    )

    assert response.status_code in (401, 422)


def test_ask_question_creates_conversation() -> None:
    client = TestClient(create_app())

    # Register user
    register = client.post(
        "/api/v1/auth/register",
        json={
            "email": "qa-test@example.com",
            "password": "TestPassword123!",
            "display_name": "QA Test",
        },
    )
    assert register.status_code == 201

    # Login
    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": "qa-test@example.com",
            "password": "TestPassword123!",
        },
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    # Ask a question (no conversation_id provided - should create new conversation)
    response = client.post(
        "/api/v1/qa/ask",
        json={"question": "What is the capital of France?"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "answer" in data
    assert "conversation_id" in data
    assert "question_message_id" in data
    assert "answer_message_id" in data
    assert "sources" in data
    assert "provider" in data
    assert "model" in data


def test_ask_question_with_existing_conversation() -> None:
    client = TestClient(create_app())

    # Register user
    register = client.post(
        "/api/v1/auth/register",
        json={
            "email": "qa-conv@example.com",
            "password": "TestPassword123!",
            "display_name": "QA Conv",
        },
    )
    assert register.status_code == 201

    # Login
    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": "qa-conv@example.com",
            "password": "TestPassword123!",
        },
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    # Create a conversation first
    conv_response = client.post(
        "/api/v1/conversations/",
        json={"title": "Test Conversation"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert conv_response.status_code == 201
    conversation_id = conv_response.json()["id"]

    # Ask a question with existing conversation_id
    response = client.post(
        "/api/v1/qa/ask",
        json={
            "question": "What is the capital of France?",
            "conversation_id": conversation_id,
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["conversation_id"] == conversation_id


def test_ask_question_invalid_conversation() -> None:
    client = TestClient(create_app())

    # Register user
    register = client.post(
        "/api/v1/auth/register",
        json={
            "email": "qa-invalid@example.com",
            "password": "TestPassword123!",
            "display_name": "QA Invalid",
        },
    )
    assert register.status_code == 201

    # Login
    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": "qa-invalid@example.com",
            "password": "TestPassword123!",
        },
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    # Ask a question with non-existent conversation_id
    response = client.post(
        "/api/v1/qa/ask",
        json={
            "question": "What is the capital of France?",
            "conversation_id": "00000000-0000-0000-0000-000000000000",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404
    assert "Conversation not found" in response.json()["detail"]


def test_ask_question_cross_user_isolation() -> None:
    """Test that users cannot use each other's conversations in QA."""
    client = TestClient(create_app())

    # User 1
    register1 = client.post(
        "/api/v1/auth/register",
        json={
            "email": "qa-user1@example.com",
            "password": "TestPassword123!",
            "display_name": "QA User 1",
        },
    )
    assert register1.status_code == 201
    login1 = client.post(
        "/api/v1/auth/login",
        json={"email": "qa-user1@example.com", "password": "TestPassword123!"},
    )
    token1 = login1.json()["access_token"]

    # User 2
    register2 = client.post(
        "/api/v1/auth/register",
        json={
            "email": "qa-user2@example.com",
            "password": "TestPassword123!",
            "display_name": "QA User 2",
        },
    )
    assert register2.status_code == 201
    login2 = client.post(
        "/api/v1/auth/login",
        json={"email": "qa-user2@example.com", "password": "TestPassword123!"},
    )
    token2 = login2.json()["access_token"]

    # User 1 creates conversation
    conv_response = client.post(
        "/api/v1/conversations/",
        json={"title": "User 1's Conversation"},
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert conv_response.status_code == 201
    conv_id = conv_response.json()["id"]

    # User 2 tries to use User 1's conversation
    response = client.post(
        "/api/v1/qa/ask",
        json={
            "question": "What is the capital of France?",
            "conversation_id": conv_id,
        },
        headers={"Authorization": f"Bearer {token2}"},
    )

    assert response.status_code == 404