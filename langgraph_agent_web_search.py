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
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.messages import BaseMessage
from langgraph.graph import START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from typing_extensions import TypedDict

from resilience import ResilientLLMInvoker

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

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
search = TavilySearchResults(max_results=3)
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
