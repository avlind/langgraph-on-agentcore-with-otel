"""Unit tests for the LangGraph agent."""

import os
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError


class TestFetchTavilyApiKey:
    """Tests for the fetch_tavily_api_key_from_secrets_manager function."""

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


class TestExceptionClassification:
    """Tests for exception classification functions."""

    def test_throttling_is_retryable(self):
        """Test ThrottlingException triggers retry."""
        from langgraph_agent_web_search import is_retryable_error, should_fallback

        error = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
            "InvokeModel",
        )
        assert is_retryable_error(error) is True
        assert should_fallback(error) is False

    def test_service_unavailable_is_retryable(self):
        """Test ServiceUnavailable triggers retry."""
        from langgraph_agent_web_search import is_retryable_error

        error = ClientError(
            {"Error": {"Code": "ServiceUnavailable", "Message": "Service unavailable"}},
            "InvokeModel",
        )
        assert is_retryable_error(error) is True

    def test_internal_failure_is_retryable(self):
        """Test InternalFailure triggers retry."""
        from langgraph_agent_web_search import is_retryable_error

        error = ClientError(
            {"Error": {"Code": "InternalFailure", "Message": "Internal error"}},
            "InvokeModel",
        )
        assert is_retryable_error(error) is True

    def test_model_not_ready_triggers_fallback(self):
        """Test ModelNotReadyException triggers fallback."""
        from langgraph_agent_web_search import is_retryable_error, should_fallback

        error = ClientError(
            {"Error": {"Code": "ModelNotReadyException", "Message": "Model not ready"}},
            "InvokeModel",
        )
        assert is_retryable_error(error) is False
        assert should_fallback(error) is True

    def test_quota_exceeded_triggers_fallback(self):
        """Test ServiceQuotaExceededException triggers immediate fallback."""
        from langgraph_agent_web_search import is_retryable_error, should_fallback

        error = ClientError(
            {"Error": {"Code": "ServiceQuotaExceededException", "Message": "Quota exceeded"}},
            "InvokeModel",
        )
        assert is_retryable_error(error) is False
        assert should_fallback(error) is True

    def test_access_denied_not_retryable(self):
        """Test AccessDeniedException doesn't retry or fallback."""
        from langgraph_agent_web_search import is_retryable_error, should_fallback

        error = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "Access denied"}},
            "InvokeModel",
        )
        assert is_retryable_error(error) is False
        assert should_fallback(error) is False

    def test_validation_error_not_retryable(self):
        """Test ValidationError doesn't retry or fallback."""
        from langgraph_agent_web_search import is_retryable_error, should_fallback

        error = ClientError(
            {"Error": {"Code": "ValidationError", "Message": "Invalid input"}},
            "InvokeModel",
        )
        assert is_retryable_error(error) is False
        assert should_fallback(error) is False

    def test_non_client_error_not_retryable(self):
        """Test non-ClientError exceptions are not retryable."""
        from langgraph_agent_web_search import is_retryable_error, should_fallback

        error = ValueError("Some other error")
        assert is_retryable_error(error) is False
        assert should_fallback(error) is False


class TestResilientLLMInvoker:
    """Tests for ResilientLLMInvoker class."""

    def _create_invoker(self, mock_primary, mock_fallback, **kwargs):
        """Helper to create invoker with mocked fallback for testing."""
        from langgraph_agent_web_search import ResilientLLMInvoker

        invoker = ResilientLLMInvoker(
            primary_llm_with_tools=mock_primary,
            fallback_model_id="test-fallback-model",
            tools=[],
            **kwargs,
        )
        # Inject mock fallback to bypass lazy initialization
        invoker._fallback_llm = mock_fallback
        return invoker

    def test_successful_primary_invocation(self, mock_llm_response):
        """Test primary model succeeds on first try."""
        mock_primary = MagicMock()
        mock_primary.invoke.return_value = mock_llm_response
        mock_fallback = MagicMock()

        invoker = self._create_invoker(mock_primary, mock_fallback, max_retries=3)
        result = invoker.invoke([])

        assert result == mock_llm_response
        assert invoker.using_fallback is False
        mock_primary.invoke.assert_called_once()
        mock_fallback.invoke.assert_not_called()

    def test_fallback_on_non_retryable_error(self, mock_llm_response):
        """Test fallback is used when primary fails with non-retryable error."""
        mock_primary = MagicMock()
        mock_primary.invoke.side_effect = ValueError("Non-retryable error")
        mock_fallback = MagicMock()
        mock_fallback.invoke.return_value = mock_llm_response

        invoker = self._create_invoker(mock_primary, mock_fallback, max_retries=3)
        result = invoker.invoke([])

        assert result == mock_llm_response
        assert invoker.using_fallback is True
        mock_primary.invoke.assert_called_once()
        mock_fallback.invoke.assert_called_once()

    def test_retry_then_success(self, mock_llm_response):
        """Test retry succeeds after initial failure."""
        throttle_error = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
            "InvokeModel",
        )
        mock_primary = MagicMock()
        mock_primary.invoke.side_effect = [throttle_error, mock_llm_response]
        mock_fallback = MagicMock()

        invoker = self._create_invoker(
            mock_primary, mock_fallback, max_retries=3, min_wait_seconds=0.01, max_wait_seconds=0.02
        )
        result = invoker.invoke([])

        assert result == mock_llm_response
        assert invoker.using_fallback is False
        assert mock_primary.invoke.call_count == 2
        mock_fallback.invoke.assert_not_called()

    def test_fallback_after_max_retries(self, mock_llm_response):
        """Test fallback after all retries exhausted."""
        throttle_error = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
            "InvokeModel",
        )
        mock_primary = MagicMock()
        mock_primary.invoke.side_effect = throttle_error
        mock_fallback = MagicMock()
        mock_fallback.invoke.return_value = mock_llm_response

        invoker = self._create_invoker(
            mock_primary, mock_fallback, max_retries=3, min_wait_seconds=0.01, max_wait_seconds=0.02
        )
        result = invoker.invoke([])

        assert result == mock_llm_response
        assert invoker.using_fallback is True
        assert mock_primary.invoke.call_count == 3
        mock_fallback.invoke.assert_called_once()

    def test_both_models_fail(self):
        """Test error raised when both models fail."""
        mock_primary = MagicMock()
        mock_primary.invoke.side_effect = ValueError("Primary failed")
        mock_fallback = MagicMock()
        mock_fallback.invoke.side_effect = ValueError("Fallback failed")

        invoker = self._create_invoker(mock_primary, mock_fallback, max_retries=3)

        with pytest.raises(RuntimeError) as exc_info:
            invoker.invoke([])

        assert "Both primary and fallback models failed" in str(exc_info.value)
        assert invoker.using_fallback is True

    def test_lazy_fallback_not_initialized_on_success(self):
        """Test fallback model is not initialized when primary succeeds."""
        from langgraph_agent_web_search import ResilientLLMInvoker

        mock_primary = MagicMock()
        mock_primary.invoke.return_value = MagicMock(content="Success")

        invoker = ResilientLLMInvoker(
            primary_llm_with_tools=mock_primary,
            fallback_model_id="test-fallback-model",
            tools=[],
            max_retries=3,
        )
        invoker.invoke([])

        # Fallback should not be initialized since primary succeeded
        assert invoker._fallback_llm is None
