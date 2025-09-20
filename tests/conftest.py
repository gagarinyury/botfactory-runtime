import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient
from runtime.main import app

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

# Ensure asyncio mode for async tests
pytest.register_assert_rewrite("tests.utils")