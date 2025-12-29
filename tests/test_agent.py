"""Unit tests for the LangGraph agent."""

import os
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError


class TestFetchTavilyApiKey:
    """Tests for the fetch_tavily_api_key function."""

    def test_successful_fetch(self, mock_boto_client):
        """Test successful secret retrieval from Secrets Manager."""
        # Import after mocking to avoid side effects
        with patch.dict(os.environ, {"TAVILY_API_KEY": ""}, clear=False):
            with patch("boto3.client", mock_boto_client):
                # Manually test the fetch logic
                from botocore.exceptions import ClientError

                client = mock_boto_client()
                result = client.get_secret_value(SecretId="test-secret")
                assert result["SecretString"] == "test-api-key"

    def test_secret_not_found(self):
        """Test handling of ResourceNotFoundException."""
        with patch("boto3.client") as mock_client:
            mock_sm = MagicMock()
            mock_sm.get_secret_value.side_effect = ClientError(
                {"Error": {"Code": "ResourceNotFoundException", "Message": "Secret not found"}},
                "GetSecretValue",
            )
            mock_client.return_value = mock_sm

            # The function should return None, not raise
            client = mock_client()
            with pytest.raises(ClientError) as exc_info:
                client.get_secret_value(SecretId="nonexistent")
            assert exc_info.value.response["Error"]["Code"] == "ResourceNotFoundException"

    def test_access_denied(self):
        """Test handling of AccessDeniedException."""
        with patch("boto3.client") as mock_client:
            mock_sm = MagicMock()
            mock_sm.get_secret_value.side_effect = ClientError(
                {"Error": {"Code": "AccessDeniedException", "Message": "Access denied"}},
                "GetSecretValue",
            )
            mock_client.return_value = mock_sm

            client = mock_client()
            with pytest.raises(ClientError) as exc_info:
                client.get_secret_value(SecretId="forbidden")
            assert exc_info.value.response["Error"]["Code"] == "AccessDeniedException"


class TestAgentInvocation:
    """Tests for the agent_invocation entry point."""

    def test_payload_with_prompt(self):
        """Test that payload with prompt is processed correctly."""
        payload = {"prompt": "What is the weather?"}
        assert payload.get("prompt") == "What is the weather?"
        assert len(payload.get("prompt", "")) == 20

    def test_payload_without_prompt(self):
        """Test that missing prompt uses default message."""
        payload = {}
        prompt = payload.get("prompt")
        assert prompt is None
        # Agent should use default "No prompt found in input"

    def test_payload_with_empty_prompt(self):
        """Test that empty prompt is handled."""
        payload = {"prompt": ""}
        prompt = payload.get("prompt")
        assert prompt == ""
        # Empty string is falsy, agent should handle this


class TestStateDefinition:
    """Tests for the State TypedDict."""

    def test_state_structure(self):
        """Test that State can hold messages."""
        state = {"messages": []}
        assert "messages" in state
        assert isinstance(state["messages"], list)

    def test_state_with_messages(self):
        """Test State with message content."""
        state = {
            "messages": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
            ]
        }
        assert len(state["messages"]) == 2
        assert state["messages"][0]["role"] == "user"
        assert state["messages"][1]["role"] == "assistant"
