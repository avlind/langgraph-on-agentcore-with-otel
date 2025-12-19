# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

LangGraph agent with Tavily web search deployed to AWS Bedrock AgentCore. Uses Claude Haiku via Bedrock with OpenTelemetry instrumentation for full observability.

## Common Commands

```bash
# Activate virtual environment (REQUIRED before any commands)
source .venv/bin/activate

# Deploy agent to AWS
./deploy.sh --profile YourProfileName

# Destroy agent and cleanup AWS resources
./destroy.sh --profile YourProfileName --all

# Test the deployed agent
AWS_PROFILE=YourProfileName agentcore invoke '{"prompt": "Search for AWS news"}'

# View agent status
AWS_PROFILE=YourProfileName agentcore status

# View traces with timing breakdown
AWS_PROFILE=YourProfileName agentcore obs show --last 1 --verbose

# Tail runtime logs
AWS_PROFILE=YourProfileName agentcore logs --follow
```

## Architecture

```
User Request → Bedrock AgentCore → LangGraph Agent → Claude Haiku (Bedrock)
                                                   ↘ Tavily Search API
```

The agent is a ReAct-style graph in `langgraph_agent_web_search.py`:
1. **chatbot node** - Invokes Claude Haiku with tools bound
2. **tools_condition** - Routes to tools node if LLM requests tool call
3. **tools node** - Executes Tavily search
4. Loop back to chatbot until complete

## Key Implementation Details

- **Secrets handling**: TAVILY_API_KEY is stored in AWS Secrets Manager and fetched at runtime via boto3
- **ENV injection**: `deploy.sh` injects `AWS_REGION`, `SECRET_NAME`, `MODEL_ID` into the generated Dockerfile since agentcore has no built-in way to pass env vars to the container runtime
- **Container deployment**: Required for OpenTelemetry instrumentation - the Dockerfile uses `opentelemetry-instrument` wrapper
- **IAM role extraction**: `deploy.sh` uses awk to find the correct execution role for the specific agent name in `.bedrock_agentcore.yaml` (multi-agent support)

## Configuration

All configuration is in `.env`:
- `TAVILY_API_KEY` - Tavily API key (stored in Secrets Manager on deploy)
- `AWS_REGION` - Deployment region
- `AGENT_NAME` - Agent name in AgentCore
- `MODEL_ID` - Bedrock model ID
- `SECRET_NAME` - Secrets Manager secret name
