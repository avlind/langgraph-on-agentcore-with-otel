#!/usr/bin/env python3
"""CDK app for LangGraph AgentCore infrastructure."""

import os

import aws_cdk as cdk

from stacks import IamPolicyStack, SecretsStack

app = cdk.App()

# Get configuration from context (passed by deploy.sh via --context flags)
secret_name = app.node.try_get_context("secret_name")
tavily_api_key = app.node.try_get_context("tavily_api_key")
execution_role_arn = app.node.try_get_context("execution_role_arn")
secret_arn = app.node.try_get_context("secret_arn")

# Environment configuration
env = cdk.Environment(
    account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
    region=os.environ.get("CDK_DEFAULT_REGION"),
)

# SecretsStack - deployed BEFORE agentcore (Phase 1)
# Required context: secret_name, tavily_api_key
if secret_name and tavily_api_key:
    SecretsStack(
        app,
        "SecretsStack",
        secret_name=secret_name,
        tavily_api_key=tavily_api_key,
        env=env,
    )

# IamPolicyStack - deployed AFTER agentcore (Phase 3)
# Required context: execution_role_arn, secret_arn
if execution_role_arn and secret_arn:
    IamPolicyStack(
        app,
        "IamPolicyStack",
        execution_role_arn=execution_role_arn,
        secret_arn=secret_arn,
        env=env,
    )

app.synth()
