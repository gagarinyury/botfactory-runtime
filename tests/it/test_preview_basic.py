"""Test preview endpoint basic functionality"""
import pytest
from fastapi.testclient import TestClient
from runtime.main import app

client = TestClient(app)

def test_preview_send_start_command():
    """Test /preview/send with /start command returns greeting"""
    response = client.post(
        "/preview/send",
        json={
            "bot_id": "c3b88b65-623c-41b5-a3c9-8d56fcbc4413",
            "text": "/start"
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert "bot_reply" in data
    assert "Привет" in data["bot_reply"]

def test_preview_send_help_command():
    """Test /preview/send with /help command"""
    response = client.post(
        "/preview/send",
        json={
            "bot_id": "c3b88b65-623c-41b5-a3c9-8d56fcbc4413",
            "text": "/help"
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert "bot_reply" in data
    assert "команд" in data["bot_reply"]

def test_preview_send_unknown_command():
    """Test /preview/send with unknown command returns fallback"""
    response = client.post(
        "/preview/send",
        json={
            "bot_id": "c3b88b65-623c-41b5-a3c9-8d56fcbc4413",
            "text": "/unknown_command"
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert "bot_reply" in data
    assert data["bot_reply"] == "Не знаю эту команду"

def test_preview_send_missing_bot_id():
    """Test /preview/send with missing bot_id"""
    response = client.post(
        "/preview/send",
        json={"text": "/start"}
    )

    # Should return 422 for validation error
    assert response.status_code == 422

def test_preview_send_missing_text():
    """Test /preview/send with missing text"""
    response = client.post(
        "/preview/send",
        json={"bot_id": "c3b88b65-623c-41b5-a3c9-8d56fcbc4413"}
    )

    # Should return 422 for validation error
    assert response.status_code == 422

def test_preview_send_invalid_json():
    """Test /preview/send with invalid JSON"""
    response = client.post(
        "/preview/send",
        data="invalid json",
        headers={"Content-Type": "application/json"}
    )

    assert response.status_code == 422

def test_preview_send_non_existent_bot():
    """Test /preview/send with non-existent bot ID"""
    response = client.post(
        "/preview/send",
        json={
            "bot_id": "00000000-0000-0000-0000-000000000000",
            "text": "/start"
        }
    )

    # Should still return 200 but with fallback response
    assert response.status_code == 200
    data = response.json()
    assert "bot_reply" in data

def test_preview_send_empty_text():
    """Test /preview/send with empty text"""
    response = client.post(
        "/preview/send",
        json={
            "bot_id": "c3b88b65-623c-41b5-a3c9-8d56fcbc4413",
            "text": ""
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert "bot_reply" in data
    # Empty text should trigger fallback
    assert data["bot_reply"] == "Не знаю эту команду"

def test_preview_send_special_characters():
    """Test /preview/send with special characters"""
    response = client.post(
        "/preview/send",
        json={
            "bot_id": "c3b88b65-623c-41b5-a3c9-8d56fcbc4413",
            "text": "🤖 /start 🚀"
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert "bot_reply" in data

def test_preview_send_long_text():
    """Test /preview/send with very long text"""
    long_text = "a" * 1000
    response = client.post(
        "/preview/send",
        json={
            "bot_id": "c3b88b65-623c-41b5-a3c9-8d56fcbc4413",
            "text": long_text
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert "bot_reply" in data


def test_unknown_command(demo_bot_id):
    """Test preview with unknown command returns fallback"""
    response = client.post(
        "/preview/send",
        json={"bot_id": demo_bot_id, "text": "/unknown"}
    )

    assert response.status_code == 200
    data = response.json()
    assert "bot_reply" in data
    assert data["bot_reply"].startswith("Не знаю")