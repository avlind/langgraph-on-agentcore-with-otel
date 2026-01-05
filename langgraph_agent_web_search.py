"""
LangGraph agent with Tavily web search deployed to AWS Bedrock AgentCore.

This agent uses a ReAct-style graph:
1. chatbot node - Invokes Claude Haiku with tools bound
2. tools_condition - Routes to tools node if LLM requests tool call
3. tools node - Executes Tavily search
4. Loop back to chatbot until complete
"""

import logging
import os
from typing import Annotated, Any

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.messages import BaseMessage
from langchain_tavily import TavilySearch
from langgraph.graph import START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)
from typing_extensions import TypedDict

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# =============================================================================
# Resilience utilities for LLM invocations with retry and fallback logic
# =============================================================================

# Error codes that should trigger retry on primary model
RETRYABLE_ERROR_CODES = {
    "ThrottlingException",
    "ServiceUnavailable",
    "InternalFailure",
    "ServiceException",
    "RequestTimeout",
}

# Error codes that should trigger immediate fallback (no retry)
FALLBACK_ERROR_CODES = {
    "ModelNotReadyException",
    "ModelStreamErrorException",
    "ModelTimeoutException",
    "ModelErrorException",
    "ServiceQuotaExceededException",  # Quota exhausted, fallback immediately
}


def is_retryable_error(exception: Exception) -> bool:
    """Check if exception should trigger a retry on the same model."""
    if isinstance(exception, ClientError):
        error_code = exception.response.get("Error", {}).get("Code", "")
        return error_code in RETRYABLE_ERROR_CODES
    return False


def should_fallback(exception: Exception) -> bool:
    """Check if exception should trigger fallback to secondary model."""
    if isinstance(exception, ClientError):
        error_code = exception.response.get("Error", {}).get("Code", "")
        return error_code in FALLBACK_ERROR_CODES
    return False


class ResilientLLMInvoker:
    """Wrapper that provides retry and fallback logic for LLM invocations."""

    def __init__(
        self,
        primary_llm_with_tools,
        fallback_llm_with_tools,
        max_retries: int = 3,
        min_wait_seconds: float = 1.0,
        max_wait_seconds: float = 10.0,
    ):
        self.primary_llm = primary_llm_with_tools
        self.fallback_llm = fallback_llm_with_tools
        self.max_retries = max_retries
        self.min_wait = min_wait_seconds
        self.max_wait = max_wait_seconds
        self._using_fallback = False

    def invoke(self, messages: list[BaseMessage]) -> BaseMessage:
        """
        Invoke LLM with retry and fallback logic.

        Flow:
        1. Try primary model
        2. On retryable error, retry up to max_retries times with exponential backoff
        3. After retries exhausted or on fallback-triggering error, use fallback model
        """
        self._using_fallback = False

        try:
            return self._invoke_with_retry(messages)
        except Exception as primary_error:
            logger.warning(
                "Primary model failed after retries: %s. Falling back to secondary model.",
                str(primary_error),
            )
            return self._invoke_fallback(messages, primary_error)

    def _invoke_with_retry(self, messages: list[BaseMessage]) -> BaseMessage:
        """Invoke primary model with retry logic."""

        @retry(
            retry=retry_if_exception(is_retryable_error),
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=1, min=self.min_wait, max=self.max_wait),
            reraise=True,
        )
        def _invoke():
            return self.primary_llm.invoke(messages)

        return _invoke()

    def _invoke_fallback(
        self, messages: list[BaseMessage], original_error: Exception
    ) -> BaseMessage:
        """Invoke fallback model."""
        self._using_fallback = True
        logger.info(
            "Using fallback model due to primary model failure: %s",
            str(original_error),
        )

        try:
            response = self.fallback_llm.invoke(messages)
            logger.info("Fallback model invocation successful")
            return response
        except Exception as fallback_error:
            logger.error(
                "Fallback model also failed: %s. Original error: %s",
                str(fallback_error),
                str(original_error),
            )
            raise RuntimeError(
                f"Both primary and fallback models failed. "
                f"Primary error: {original_error}. "
                f"Fallback error: {fallback_error}"
            ) from fallback_error

    @property
    def using_fallback(self) -> bool:
        """Returns True if the last invocation used the fallback model."""
        return self._using_fallback


# =============================================================================
# Agent Configuration
# =============================================================================

# Load environment variables from .env file (for local dev)
load_dotenv()

# Configuration from environment variables (with defaults)
AWS_REGION = os.environ.get("AWS_REGION", "us-east-2")
SECRET_NAME = os.environ.get("SECRET_NAME", "langgraph-agent/tavily-api-key")
MODEL_ID = os.environ.get("MODEL_ID", "global.anthropic.claude-haiku-4-5-20251001-v1:0")
FALLBACK_MODEL_ID = os.environ.get(
    "FALLBACK_MODEL_ID", "global.anthropic.claude-sonnet-4-5-20250929-v1:0"
)


def fetch_tavily_api_key() -> str | None:
    """
    Fetch Tavily API key from AWS Secrets Manager.

    Returns:
        The API key string if successful, None otherwise.

    Raises:
        Logs specific errors but does not raise - returns None on failure.
    """
    try:
        logger.info("Fetching Tavily API key from Secrets Manager: %s", SECRET_NAME)
        client = boto3.client("secretsmanager", region_name=AWS_REGION)
        secret = client.get_secret_value(SecretId=SECRET_NAME)
        logger.info("Successfully retrieved Tavily API key from Secrets Manager")
        return secret["SecretString"]
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        if error_code == "ResourceNotFoundException":
            logger.error("Secret '%s' not found in Secrets Manager", SECRET_NAME)
        elif error_code == "AccessDeniedException":
            logger.error("Access denied to secret '%s'. Check IAM permissions.", SECRET_NAME)
        elif error_code == "InvalidRequestException":
            logger.error("Invalid request for secret '%s': %s", SECRET_NAME, e)
        else:
            logger.error("Failed to fetch secret '%s': %s - %s", SECRET_NAME, error_code, e)
        return None
    except Exception as e:
        logger.error("Unexpected error fetching secret '%s': %s", SECRET_NAME, e)
        return None


# Fetch Tavily API key: prefer env var, fallback to Secrets Manager
if not os.environ.get("TAVILY_API_KEY"):
    tavily_key = fetch_tavily_api_key()
    if tavily_key:
        os.environ["TAVILY_API_KEY"] = tavily_key
    else:
        logger.warning(
            "TAVILY_API_KEY not found in environment or Secrets Manager. "
            "Web search will fail at runtime."
        )
else:
    logger.info("Using TAVILY_API_KEY from environment variable")

# Initialize the primary LLM with Bedrock
logger.info("Initializing primary LLM with model: %s", MODEL_ID)
llm_primary = init_chat_model(
    MODEL_ID,
    model_provider="bedrock_converse",
)

# Initialize the fallback LLM with Bedrock
logger.info("Initializing fallback LLM with model: %s", FALLBACK_MODEL_ID)
llm_fallback = init_chat_model(
    FALLBACK_MODEL_ID,
    model_provider="bedrock_converse",
)

# Define search tool
search = TavilySearch(max_results=3)
tools = [search]

# Bind tools to both models
llm_primary_with_tools = llm_primary.bind_tools(tools)
llm_fallback_with_tools = llm_fallback.bind_tools(tools)

# Create resilient invoker with retry and fallback
resilient_llm = ResilientLLMInvoker(
    primary_llm_with_tools=llm_primary_with_tools,
    fallback_llm_with_tools=llm_fallback_with_tools,
    max_retries=3,
    min_wait_seconds=1.0,
    max_wait_seconds=10.0,
)


# Define state
class State(TypedDict):
    """State for the agent graph containing the message history."""

    messages: Annotated[list[BaseMessage], add_messages]


def chatbot(state: State) -> dict[str, list[BaseMessage]]:
    """
    Chatbot node that invokes the LLM with tools.

    Uses ResilientLLMInvoker for automatic retry with exponential backoff
    and fallback to secondary model on failure.

    Args:
        state: Current state containing message history.

    Returns:
        Dictionary with updated messages list.
    """
    logger.info("Chatbot node invoked with %d messages", len(state["messages"]))
    response = resilient_llm.invoke(state["messages"])
    if resilient_llm.using_fallback:
        logger.info("Response generated using fallback model")
    logger.info("LLM response received, has tool calls: %s", bool(response.tool_calls))
    return {"messages": [response]}


# Build the graph
# Flow: START -> chatbot -> tools_condition -> tools -> chatbot (loop until done)
graph_builder = StateGraph(State)
graph_builder.add_node("chatbot", chatbot)
tool_node = ToolNode(tools=tools)
graph_builder.add_node("tools", tool_node)
graph_builder.add_conditional_edges("chatbot", tools_condition)
graph_builder.add_edge("tools", "chatbot")
graph_builder.add_edge(START, "chatbot")
graph = graph_builder.compile()

# Integrate with Bedrock AgentCore
from bedrock_agentcore.runtime import BedrockAgentCoreApp

app = BedrockAgentCoreApp()


@app.entrypoint
def agent_invocation(payload: dict[str, Any], context: Any) -> dict[str, str]:
    """
    Entry point for Bedrock AgentCore invocations.

    Args:
        payload: Input payload containing 'prompt' key with user message.
        context: AgentCore context (contains request metadata).

    Returns:
        Dictionary with 'result' key containing the agent's response.
    """
    prompt = payload.get("prompt")
    if not prompt:
        logger.warning("No prompt found in payload, using default message")
        prompt = "No prompt found in input"

    logger.info("Agent invocation started with prompt length: %d", len(prompt))

    input_state: State = {"messages": [{"role": "user", "content": prompt}]}

    try:
        output = graph.invoke(input_state)
        final_message = output["messages"][-1]
        result = getattr(final_message, "content", str(final_message))
        logger.info("Agent invocation completed successfully")
        return {"result": result}
    except Exception as e:
        logger.error("Agent invocation failed: %s", e, exc_info=True)
        return {"result": f"Error processing request: {e}"}


if __name__ == "__main__":
    app.run()
