import os
import boto3
from typing import Annotated
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

# Load environment variables from .env file (for local dev)
load_dotenv()

# If TAVILY_API_KEY not in env, try to fetch from Secrets Manager
if not os.environ.get("TAVILY_API_KEY"):
    try:
        client = boto3.client("secretsmanager", region_name="us-east-2")
        secret = client.get_secret_value(SecretId="langgraph-agent/tavily-api-key")
        os.environ["TAVILY_API_KEY"] = secret["SecretString"]
    except Exception:
        pass  # Will fail later if key is truly missing
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

# Initialize the LLM with Bedrock
llm = init_chat_model(
    "global.anthropic.claude-haiku-4-5-20251001-v1:0",
    model_provider="bedrock_converse",
)

# Define search tool
from langchain_community.tools.tavily_search import TavilySearchResults
search = TavilySearchResults(max_results=3)
tools = [search]
llm_with_tools = llm.bind_tools(tools)

# Define state
class State(TypedDict):
    messages: Annotated[list, add_messages]

# Build the graph
graph_builder = StateGraph(State)

def chatbot(state: State):
    return {"messages": [llm_with_tools.invoke(state["messages"])]}

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
def agent_invocation(payload, context):
    tmp_msg = {"messages": [{"role": "user", "content": payload.get("prompt", "No prompt found in input")}]}
    tmp_output = graph.invoke(tmp_msg)
    return {"result": tmp_output['messages'][-1].content}

if __name__ == "__main__":
    app.run()