"""Unit tests for langgraph_agent_web_search module functions.

These tests directly import and test the functions in the agent module,
using mocks to isolate the functions from their dependencies.
"""

import logging
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError


class TestFetchTavilyApiKey:
    """Tests for the fetch_tavily_api_key function."""

    @pytest.fixture
    def mock_secrets_client(self):
        """Create a mock Secrets Manager client."""
        mock_client = MagicMock()
        return mock_client

    def test_successful_fetch(self, mock_secrets_client):
        """Test successful secret retrieval from Secrets Manager."""
        mock_secrets_client.get_secret_value.return_value = {
            "SecretString": "tavily-test-key-123"
        }

        with patch("boto3.client", return_value=mock_secrets_client):
            # Import inside patch to avoid module-level side effects
            from langgraph_agent_web_search import fetch_tavily_api_key

            result = fetch_tavily_api_key()

        assert result == "tavily-test-key-123"
        mock_secrets_client.get_secret_value.assert_called_once()

    def test_resource_not_found_returns_none(self, mock_secrets_client, caplog):
        """Test ResourceNotFoundException returns None and logs error."""
        mock_secrets_client.get_secret_value.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException", "Message": "Secret not found"}},
            "GetSecretValue",
        )

        with patch("boto3.client", return_value=mock_secrets_client):
            from langgraph_agent_web_search import fetch_tavily_api_key

            with caplog.at_level(logging.ERROR):
                result = fetch_tavily_api_key()

        assert result is None
        assert "not found" in caplog.text.lower()

    def test_access_denied_returns_none(self, mock_secrets_client, caplog):
        """Test AccessDeniedException returns None and logs error."""
        mock_secrets_client.get_secret_value.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "Access denied"}},
            "GetSecretValue",
        )

        with patch("boto3.client", return_value=mock_secrets_client):
            from langgraph_agent_web_search import fetch_tavily_api_key

            with caplog.at_level(logging.ERROR):
                result = fetch_tavily_api_key()

        assert result is None
        assert "access denied" in caplog.text.lower()

    def test_invalid_request_returns_none(self, mock_secrets_client, caplog):
        """Test InvalidRequestException returns None and logs error."""
        mock_secrets_client.get_secret_value.side_effect = ClientError(
            {"Error": {"Code": "InvalidRequestException", "Message": "Invalid request"}},
            "GetSecretValue",
        )

        with patch("boto3.client", return_value=mock_secrets_client):
            from langgraph_agent_web_search import fetch_tavily_api_key

            with caplog.at_level(logging.ERROR):
                result = fetch_tavily_api_key()

        assert result is None
        assert "invalid request" in caplog.text.lower()

    def test_unknown_client_error_returns_none(self, mock_secrets_client, caplog):
        """Test unknown ClientError returns None and logs error."""
        mock_secrets_client.get_secret_value.side_effect = ClientError(
            {"Error": {"Code": "UnknownError", "Message": "Something went wrong"}},
            "GetSecretValue",
        )

        with patch("boto3.client", return_value=mock_secrets_client):
            from langgraph_agent_web_search import fetch_tavily_api_key

            with caplog.at_level(logging.ERROR):
                result = fetch_tavily_api_key()

        assert result is None
        assert "UnknownError" in caplog.text

    def test_unexpected_exception_returns_none(self, mock_secrets_client, caplog):
        """Test unexpected non-ClientError exception returns None."""
        mock_secrets_client.get_secret_value.side_effect = RuntimeError("Network failure")

        with patch("boto3.client", return_value=mock_secrets_client):
            from langgraph_agent_web_search import fetch_tavily_api_key

            with caplog.at_level(logging.ERROR):
                result = fetch_tavily_api_key()

        assert result is None
        assert "unexpected error" in caplog.text.lower()


class TestChatbotNode:
    """Tests for the chatbot graph node function."""

    def test_chatbot_invokes_resilient_llm(self):
        """Test chatbot node invokes resilient LLM with messages."""
        mock_response = MagicMock()
        mock_response.content = "Test response"
        mock_response.tool_calls = []

        mock_invoker = MagicMock()
        mock_invoker.invoke.return_value = mock_response
        mock_invoker.using_fallback = False

        with patch("langgraph_agent_web_search.resilient_llm", mock_invoker):
            from langgraph_agent_web_search import chatbot

            state = {"messages": [{"role": "user", "content": "Hello"}]}
            result = chatbot(state)

        assert "messages" in result
        assert len(result["messages"]) == 1
        assert result["messages"][0] == mock_response
        mock_invoker.invoke.assert_called_once_with(state["messages"])

    def test_chatbot_logs_fallback_usage(self, caplog):
        """Test chatbot logs when fallback model is used."""
        mock_response = MagicMock()
        mock_response.content = "Fallback response"
        mock_response.tool_calls = []

        mock_invoker = MagicMock()
        mock_invoker.invoke.return_value = mock_response
        mock_invoker.using_fallback = True

        with patch("langgraph_agent_web_search.resilient_llm", mock_invoker):
            from langgraph_agent_web_search import chatbot

            with caplog.at_level(logging.INFO):
                state = {"messages": [{"role": "user", "content": "Test"}]}
                chatbot(state)

        assert "fallback model" in caplog.text.lower()

    def test_chatbot_logs_tool_calls(self, caplog):
        """Test chatbot logs when response has tool calls."""
        mock_response = MagicMock()
        mock_response.content = "I'll search for that"
        mock_response.tool_calls = [{"name": "tavily_search", "args": {"query": "test"}}]

        mock_invoker = MagicMock()
        mock_invoker.invoke.return_value = mock_response
        mock_invoker.using_fallback = False

        with patch("langgraph_agent_web_search.resilient_llm", mock_invoker):
            from langgraph_agent_web_search import chatbot

            with caplog.at_level(logging.INFO):
                state = {"messages": [{"role": "user", "content": "Search for news"}]}
                chatbot(state)

        assert "tool calls: True" in caplog.text


class TestAgentInvocation:
    """Tests for the agent_invocation entry point function."""

    @pytest.fixture
    def mock_graph(self):
        """Create a mock graph."""
        mock = MagicMock()
        return mock

    def test_valid_prompt_returns_result(self, mock_graph):
        """Test agent returns result for valid prompt."""
        mock_message = MagicMock()
        mock_message.content = "The weather in Seattle is rainy."
        mock_graph.invoke.return_value = {"messages": [mock_message]}

        with patch("langgraph_agent_web_search.graph", mock_graph):
            from langgraph_agent_web_search import agent_invocation

            result = agent_invocation({"prompt": "What is the weather?"}, None)

        assert result == {"result": "The weather in Seattle is rainy."}
        mock_graph.invoke.assert_called_once()

    def test_missing_prompt_uses_default(self, mock_graph, caplog):
        """Test agent uses default message when prompt is missing."""
        mock_message = MagicMock()
        mock_message.content = "No prompt response"
        mock_graph.invoke.return_value = {"messages": [mock_message]}

        with patch("langgraph_agent_web_search.graph", mock_graph):
            from langgraph_agent_web_search import agent_invocation

            with caplog.at_level(logging.WARNING):
                result = agent_invocation({}, None)

        assert "result" in result
        assert "no prompt" in caplog.text.lower()
        # Verify default prompt was used in the invoke call
        call_args = mock_graph.invoke.call_args[0][0]
        assert call_args["messages"][0]["content"] == "No prompt found in input"

    def test_empty_prompt_uses_default(self, mock_graph, caplog):
        """Test agent uses default message when prompt is empty string."""
        mock_message = MagicMock()
        mock_message.content = "Default response"
        mock_graph.invoke.return_value = {"messages": [mock_message]}

        with patch("langgraph_agent_web_search.graph", mock_graph):
            from langgraph_agent_web_search import agent_invocation

            with caplog.at_level(logging.WARNING):
                result = agent_invocation({"prompt": ""}, None)

        assert "result" in result
        # Empty string is falsy, so default should be used
        call_args = mock_graph.invoke.call_args[0][0]
        assert call_args["messages"][0]["content"] == "No prompt found in input"

    def test_graph_exception_returns_error(self, mock_graph, caplog):
        """Test agent returns error message when graph raises exception."""
        mock_graph.invoke.side_effect = RuntimeError("LLM connection failed")

        with patch("langgraph_agent_web_search.graph", mock_graph):
            from langgraph_agent_web_search import agent_invocation

            with caplog.at_level(logging.ERROR):
                result = agent_invocation({"prompt": "Test"}, None)

        assert "result" in result
        assert "Error processing request" in result["result"]
        assert "LLM connection failed" in result["result"]
        assert "failed" in caplog.text.lower()

    def test_message_without_content_attribute(self, mock_graph):
        """Test agent handles message without content attribute."""
        # Some message types might not have .content, falling back to str()
        # Create a simple class without content attribute
        class MessageWithoutContent:
            def __str__(self):
                return "String representation"

        mock_message = MessageWithoutContent()
        mock_graph.invoke.return_value = {"messages": [mock_message]}

        with patch("langgraph_agent_web_search.graph", mock_graph):
            from langgraph_agent_web_search import agent_invocation

            result = agent_invocation({"prompt": "Test"}, None)

        assert "result" in result
        # Should fall back to str() representation
        assert result["result"] == "String representation"

    def test_invocation_logs_prompt_length(self, mock_graph, caplog):
        """Test agent logs the prompt length on invocation."""
        mock_message = MagicMock()
        mock_message.content = "Response"
        mock_graph.invoke.return_value = {"messages": [mock_message]}

        with patch("langgraph_agent_web_search.graph", mock_graph):
            from langgraph_agent_web_search import agent_invocation

            with caplog.at_level(logging.INFO):
                agent_invocation({"prompt": "Hello world"}, None)

        assert "prompt length: 11" in caplog.text.lower()

    def test_invocation_logs_success(self, mock_graph, caplog):
        """Test agent logs successful completion."""
        mock_message = MagicMock()
        mock_message.content = "Success"
        mock_graph.invoke.return_value = {"messages": [mock_message]}

        with patch("langgraph_agent_web_search.graph", mock_graph):
            from langgraph_agent_web_search import agent_invocation

            with caplog.at_level(logging.INFO):
                agent_invocation({"prompt": "Test"}, None)

        assert "completed successfully" in caplog.text.lower()


class TestStateType:
    """Tests for the State TypedDict structure."""

    def test_state_accepts_message_list(self):
        """Test State type accepts list of messages."""
        from langgraph_agent_web_search import State

        # TypedDict allows any dict that matches the structure
        state: State = {"messages": []}
        assert state["messages"] == []

    def test_state_with_base_messages(self):
        """Test State works with message dictionaries."""
        from langgraph_agent_web_search import State

        state: State = {
            "messages": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
            ]
        }
        assert len(state["messages"]) == 2
