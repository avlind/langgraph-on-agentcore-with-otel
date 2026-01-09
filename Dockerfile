# LangGraph Agent Dockerfile for AWS Bedrock AgentCore
# ARM64 architecture required by AgentCore Runtime

FROM --platform=linux/arm64 ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

# Environment variables for uv and Python
ENV UV_SYSTEM_PYTHON=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_NO_PROGRESS=1 \
    PYTHONUNBUFFERED=1 \
    DOCKER_CONTAINER=1

# Copy dependency files first for better caching
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv pip install .

# Copy application code
COPY langgraph_agent_web_search.py ./

# Create non-root user for security
RUN useradd -m -u 1000 bedrock_agentcore
USER bedrock_agentcore

# AgentCore Runtime expects port 8080
EXPOSE 8080

# Run the agent with OpenTelemetry auto-instrumentation for CloudWatch logs
CMD ["opentelemetry-instrument", "python", "-m", "langgraph_agent_web_search"]
