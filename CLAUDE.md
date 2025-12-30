# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

LangGraph agent with Tavily web search deployed to AWS Bedrock AgentCore. Uses Claude Haiku via Bedrock with OpenTelemetry instrumentation for full observability. Infrastructure is managed with AWS CDK. Dependencies are managed with uv.

## Common Commands

```bash
# Install dependencies (creates .venv automatically)
uv sync

# Run tests
make test

# Lint and format code
make lint
make format

# Deploy agent to AWS (includes CDK infrastructure)
make deploy PROFILE=YourProfileName

# Destroy agent and cleanup AWS resources
make destroy-all PROFILE=YourProfileName

# Test the deployed agent
make invoke PROFILE=YourProfileName
make invoke PROFILE=YourProfileName PROMPT="Search for AWS news"

# View agent status
make status PROFILE=YourProfileName

# View traces
make traces PROFILE=YourProfileName

# Tail runtime logs
make logs PROFILE=YourProfileName
```

## Architecture

```
CDK manages:                    agentcore CLI manages:
├── SecretsStack               ├── Agent runtime
│   └── Secrets Manager        ├── Execution role
└── IamPolicyStack             ├── ECR repository
    └── IAM policy             ├── CodeBuild
                               └── S3 artifacts

User Request → Bedrock AgentCore → LangGraph Agent → Claude Haiku (Bedrock)
                                                   ↘ Tavily Search API
```

The agent is a ReAct-style graph in `langgraph_agent_web_search.py`:
1. **chatbot node** - Invokes Claude Haiku with tools bound
2. **tools_condition** - Routes to tools node if LLM requests tool call
3. **tools node** - Executes Tavily search
4. Loop back to chatbot until complete

## Key Implementation Details

- **Dependency management**: Uses uv with `pyproject.toml` and `uv.lock`
- **Infrastructure as Code**: AWS CDK (Python) manages Secrets Manager and IAM policies in `cdk/` directory
- **Secrets handling**: TAVILY_API_KEY is stored in AWS Secrets Manager via CDK SecretsStack
- **IAM policies**: CDK IamPolicyStack grants `secretsmanager:GetSecretValue` to execution role
- **Environment variables**: `scripts/deploy.py` passes `AWS_REGION`, `SECRET_NAME`, `MODEL_ID` to the container runtime via `agentcore deploy --env` flags
- **Deployment scripts**: Python scripts in `scripts/` directory using Typer CLI framework (replaced shell scripts)
- **Container deployment**: Required for OpenTelemetry instrumentation - the Dockerfile uses `opentelemetry-instrument` wrapper
- **6-step deployment**: (1) CDK SecretsStack, (2) agentcore configure, (3) agentcore deploy, (4) extract role ARN, (5) CDK IamPolicyStack, (6) restart containers to apply IAM permissions
- **Linting/Formatting**: Uses ruff for both linting and formatting

## CDK Stacks

| Stack | Resources | When Deployed |
|-------|-----------|---------------|
| `SecretsStack` | Secrets Manager secret | Before agentcore configure |
| `IamPolicyStack` | IAM inline policy | After agentcore deploy |

## Git Commit Guidelines

- Do NOT add "Generated with Claude Code" or similar signatures to commit messages
- Do NOT add "Co-Authored-By" lines to commits

## Configuration

All configuration is in `.env`:
- `TAVILY_API_KEY` - Tavily API key (stored in Secrets Manager on deploy)
- `AWS_REGION` - Deployment region
- `AGENT_NAME` - Agent name in AgentCore
- `MODEL_ID` - Bedrock model ID
- `SECRET_NAME` - Secrets Manager secret name
