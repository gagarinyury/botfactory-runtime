import pytest
from fastapi.testclient import TestClient
from runtime.main import app

@pytest.fixture
def client():
    """FastAPI TestClient fixture"""
    return TestClient(app)