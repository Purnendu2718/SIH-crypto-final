"""Test health check endpoint."""

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_check_returns_200():
    """Confirm GET /api/health returns 200 and expected payload."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["app"] == "CryptoTrace Sentinel"
    assert "version" in data
    assert "environment" in data
