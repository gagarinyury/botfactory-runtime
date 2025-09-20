import os
import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient
from runtime.main import app

# Global anyio marker for all tests
pytestmark = pytest.mark.anyio

# Skip if not running inside Docker container
if os.environ.get("INSIDE_CONTAINER") != "1":
    pytest.skip("run inside docker", allow_module_level=True)

@pytest.fixture
def client():
    """FastAPI TestClient fixture"""
    return TestClient(app)

@pytest.fixture
async def async_client():
    """Async HTTP client fixture"""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

@pytest.fixture(scope="function")
def anyio_backend():
    return "asyncio"

@pytest.fixture
def demo_bot_id():
    """Known bot ID from seed data"""
    return "c3b88b65-623c-41b5-a3c9-8d56fcbc4413"

@pytest.fixture
def tg_update():
    """Minimal valid Telegram update"""
    return {
        "update_id": 123,
        "message": {
            "message_id": 456,
            "date": 1640995200,
            "text": "/start",
            "from": {"id": 789, "is_bot": False, "first_name": "Test"},
            "chat": {"id": 789, "type": "private"}
        }
    }

# Ensure asyncio mode for async tests
pytest.register_assert_rewrite("tests.utils")