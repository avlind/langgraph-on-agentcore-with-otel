#!/usr/bin/env python3
"""
CDK app for LangGraph AgentCore infrastructure.

This app defines stacks for deploying a LangGraph agent to AWS Bedrock AgentCore:

    SecretsStack - Creates the Tavily API key in Secrets Manager
    AgentInfraStack - Creates ECR, CodeBuild, IAM role
    MemoryStack - Creates AgentCore Memory (deployed in parallel with CodeBuild)
    RuntimeStack - Creates the AgentCore Runtime (deployed after CodeBuild)

Deployment order:
    1. cdk deploy SecretsStack AgentInfraStack  (infrastructure)
    2. Run CodeBuild + cdk deploy MemoryStack   (parallel)
    3. cdk deploy RuntimeStack  (runtime needs image to exist)

Usage:
    cdk deploy --all \\
        --context secret_name="langgraph-agent/tavily-api-key" \\
        --context tavily_api_key="your-key" \\
        --context agent_name="langgraph-search-agent" \\
        --context model_id="..." \\
        --context fallback_model_id="..." \\
        --context source_path="/path/to/project"
"""

import os
from pathlib import Path

import aws_cdk as cdk
from stacks import (
    AGENT_INFRA_STACK_NAME,
    CONTEXT_AGENT_NAME,
    CONTEXT_FALLBACK_MODEL_ID,
    CONTEXT_MODEL_ID,
    CONTEXT_SECRET_NAME,
    CONTEXT_SOURCE_PATH,
    CONTEXT_TAVILY_API_KEY,
    MEMORY_STACK_NAME,
    RUNTIME_STACK_NAME,
    SECRETS_STACK_NAME,
    AgentInfraStack,
    MemoryStack,
    RuntimeStack,
    SecretsStack,
)

app = cdk.App()

# Get configuration from context (passed by deploy script via --context flags)
secret_name = app.node.try_get_context(CONTEXT_SECRET_NAME)
tavily_api_key = app.node.try_get_context(CONTEXT_TAVILY_API_KEY)
agent_name = app.node.try_get_context(CONTEXT_AGENT_NAME)
model_id = app.node.try_get_context(CONTEXT_MODEL_ID)
fallback_model_id = app.node.try_get_context(CONTEXT_FALLBACK_MODEL_ID)
source_path = app.node.try_get_context(CONTEXT_SOURCE_PATH)

# Environment configuration - uses CDK CLI's resolved account/region
env = cdk.Environment(
    account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
    region=os.environ.get("CDK_DEFAULT_REGION"),
)

# SecretsStack - Creates Tavily API key secret
# Required context: secret_name, tavily_api_key
secrets_stack = None
if secret_name and tavily_api_key:
    secrets_stack = SecretsStack(
        app,
        SECRETS_STACK_NAME,
        secret_name=secret_name,
        tavily_api_key=tavily_api_key,
        env=env,
    )

# AgentInfraStack - Creates ECR, CodeBuild, IAM role
# Required context: secret_name, agent_name, model_id, fallback_model_id, source_path
# Deploys in parallel with SecretsStack (uses wildcard for secret ARN in IAM policy)
infra_stack = None
if agent_name and model_id and source_path and secret_name:
    # Resolve source path relative to cdk directory
    resolved_source_path = source_path
    if not Path(source_path).is_absolute():
        # If relative, resolve from cdk directory's parent (project root)
        resolved_source_path = str(Path(__file__).parent.parent / source_path)

    infra_stack = AgentInfraStack(
        app,
        AGENT_INFRA_STACK_NAME,
        secret_name=secret_name,
        agent_name=agent_name,
        model_id=model_id,
        fallback_model_id=fallback_model_id or model_id,
        source_path=resolved_source_path,
        env=env,
    )

# MemoryStack - Creates AgentCore Memory
# Deployed in parallel with CodeBuild for faster deployment
memory_stack = None
if agent_name:
    memory_stack = MemoryStack(
        app,
        MEMORY_STACK_NAME,
        agent_name=agent_name,
        env=env,
    )

# RuntimeStack - Creates the AgentCore Runtime
# This stack must be deployed AFTER CodeBuild has pushed the Docker image
# It uses cross-stack references from AgentInfraStack
if infra_stack:
    runtime_stack = RuntimeStack(
        app,
        RUNTIME_STACK_NAME,
        agent_name=agent_name,
        model_id=model_id,
        fallback_model_id=fallback_model_id or model_id,
        secret_name=secret_name,
        ecr_repository_uri=infra_stack.ecr_repo.repository_uri,
        execution_role_arn=infra_stack.execution_role.role_arn,
        env=env,
    )
    runtime_stack.add_dependency(infra_stack)

app.synth()
