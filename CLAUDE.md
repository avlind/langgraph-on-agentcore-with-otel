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

# View traces (default: last 1 hour)
make traces PROFILE=YourProfileName
make traces PROFILE=YourProfileName HOURS=2

# Tail runtime logs
make logs PROFILE=YourProfileName
```

## Architecture

```text
CDK manages all infrastructure:
├── SecretsStack           → Secrets Manager (Tavily API key)
├── AgentInfraStack        → ECR, CodeBuild, IAM role, VPC, Security Group
└── RuntimeStack           → AgentCore Runtime (PRIVATE network mode)

User Request → Bedrock AgentCore → VPC (private subnet + NAT) → LangGraph Agent → Claude Haiku (Bedrock)
                                                                                 ↘ Tavily Search API
```

The agent is a ReAct-style graph in `langgraph_agent_web_search.py`:

1. **chatbot node** - Invokes Claude Haiku with tools bound
2. **tools_condition** - Routes to tools node if LLM requests tool call
3. **tools node** - Executes Tavily search
4. Loop back to chatbot until complete

## Key Implementation Details

- **Dependency management**: Uses uv with `pyproject.toml` and `uv.lock`
- **Infrastructure as Code**: AWS CDK (Python) manages all infrastructure in `cdk/` directory
- **Secrets handling**: TAVILY_API_KEY stored in AWS Secrets Manager via CDK SecretsStack
- **Network mode**: PRIVATE with NAT gateway — agent runs in a private subnet with outbound internet via NAT (no public IP)
- **IAM policies**: AgentInfraStack creates execution role with Secrets Manager, Bedrock, ECR, CloudWatch, and ENI permissions
- **Environment variables**: RuntimeStack passes `AWS_REGION`, `SECRET_NAME`, `MODEL_ID`, `FALLBACK_MODEL_ID` to the container
- **Deployment scripts**: Python scripts in `scripts/` directory using Typer CLI framework
- **Container deployment**: Required for OpenTelemetry instrumentation - the Dockerfile uses `opentelemetry-instrument` wrapper
- **3-phase deployment**: (1) CDK SecretsStack + AgentInfraStack, (2) CodeBuild, (3) CDK RuntimeStack
- **Linting/Formatting**: Uses ruff for both linting and formatting

## CDK Stacks

| Stack | Resources | When Deployed |
|-------|-----------|---------------|
| `SecretsStack` | Secrets Manager secret | Phase 1 (parallel with AgentInfraStack) |
| `AgentInfraStack` | ECR, CodeBuild, IAM role, VPC, Security Group | Phase 1 (parallel with SecretsStack) |
| `RuntimeStack` | AgentCore Runtime | Phase 3 (after CodeBuild) |

## Git Commit Guidelines

- Do NOT add "Generated with Claude Code" or similar signatures to commit messages
- Do NOT add "Co-Authored-By" lines to commits

## Configuration

Configuration is split between two files:

**`.env`** - Non-sensitive deployment configuration:

- `AWS_REGION` - Deployment region
- `AGENT_NAME` - Agent name in AgentCore
- `MODEL_ID` - Primary Bedrock model ID
- `FALLBACK_MODEL_ID` - Fallback model for resilience
- `SECRET_NAME` - Secrets Manager secret name

**`.secrets`** - Sensitive values (gitignored):

- `TAVILY_API_KEY` - Tavily API key (stored in Secrets Manager on deploy)
