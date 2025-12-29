"""Pytest fixtures for agent and CDK tests."""

import os
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def mock_env_vars(monkeypatch):
    """Set required environment variables for all tests."""
    monkeypatch.setenv("AWS_REGION", "us-east-2")
    monkeypatch.setenv("SECRET_NAME", "test-secret")
    monkeypatch.setenv("MODEL_ID", "test-model")
    monkeypatch.setenv("FALLBACK_MODEL_ID", "test-fallback-model")
    monkeypatch.setenv("TAVILY_API_KEY", "test-tavily-key")


@pytest.fixture
def mock_boto_client():
    """Mock boto3 secretsmanager client."""
    with patch("boto3.client") as mock_client:
        mock_sm = MagicMock()
        mock_sm.get_secret_value.return_value = {"SecretString": "test-api-key"}
        mock_client.return_value = mock_sm
        yield mock_client


@pytest.fixture
def mock_llm_response():
    """Mock LLM response object."""
    mock_response = MagicMock()
    mock_response.content = "This is a test response"
    mock_response.tool_calls = []
    return mock_response
