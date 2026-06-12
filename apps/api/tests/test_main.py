"""Unit tests for the FastAPI main application.

This module contains tests to verify API endpoints like the health check.
"""

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_check():
    """Verify that the health check endpoint returns 200 OK and healthy status."""
    response = client.get("/health/live")
    expected_status_code = 200
    assert response.status_code == expected_status_code
    assert response.json()["status"] == "alive"
