#!/usr/bin/env python3
"""
CDK app for LangGraph AgentCore infrastructure.

This app defines two stacks that are deployed in different phases:

Phase 1 (before agentcore deploy):
    SecretsStack - Creates the Tavily API key in Secrets Manager

Phase 2 (agentcore configure + deploy):
    Managed by agentcore CLI, not CDK

Phase 3 (after agentcore deploy):
    IamPolicyStack - Grants the execution role access to the secret

Usage:
    # Phase 1: Deploy secrets
    cdk deploy SecretsStack \\
        --context secret_name="langgraph-agent/tavily-api-key" \\
        --context tavily_api_key="your-key"

    # Phase 3: Deploy IAM policy
    cdk deploy IamPolicyStack \\
        --context execution_role_arn="arn:aws:iam::..." \\
        --context secret_arn="arn:aws:secretsmanager:..."
"""

import os

import aws_cdk as cdk
from stacks import (
    CONTEXT_EXECUTION_ROLE_ARN,
    CONTEXT_SECRET_ARN,
    CONTEXT_SECRET_NAME,
    CONTEXT_TAVILY_API_KEY,
    IAM_POLICY_STACK_NAME,
    SECRETS_STACK_NAME,
    IamPolicyStack,
    SecretsStack,
)

app = cdk.App()

# Get configuration from context (passed by deploy script via --context flags)
secret_name = app.node.try_get_context(CONTEXT_SECRET_NAME)
tavily_api_key = app.node.try_get_context(CONTEXT_TAVILY_API_KEY)
execution_role_arn = app.node.try_get_context(CONTEXT_EXECUTION_ROLE_ARN)
secret_arn = app.node.try_get_context(CONTEXT_SECRET_ARN)

# Environment configuration - uses CDK CLI's resolved account/region
env = cdk.Environment(
    account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
    region=os.environ.get("CDK_DEFAULT_REGION"),
)

# SecretsStack - deployed BEFORE agentcore (Phase 1)
# Required context: secret_name, tavily_api_key
if secret_name and tavily_api_key:
    SecretsStack(
        app,
        SECRETS_STACK_NAME,
        secret_name=secret_name,
        tavily_api_key=tavily_api_key,
        env=env,
    )

# IamPolicyStack - deployed AFTER agentcore (Phase 3)
# Required context: execution_role_arn, secret_arn
if execution_role_arn and secret_arn:
    IamPolicyStack(
        app,
        IAM_POLICY_STACK_NAME,
        execution_role_arn=execution_role_arn,
        secret_arn=secret_arn,
        env=env,
    )

app.synth()
