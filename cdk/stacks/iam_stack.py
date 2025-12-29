"""
CDK stack for IAM policies attached to the AgentCore execution role.

This stack grants the AgentCore execution role permission to read secrets
from AWS Secrets Manager. It uses the principle of least privilege by
granting access only to the specific secret ARN.

Usage:
    cdk deploy IamPolicyStack \\
        --context execution_role_arn="arn:aws:iam::123456789012:role/..." \\
        --context secret_arn="arn:aws:secretsmanager:region:account:secret:name"
"""

import re

from aws_cdk import CfnOutput, Stack
from aws_cdk import aws_iam as iam
from constructs import Construct

from .constants import SECRETS_MANAGER_POLICY_NAME

# Regex pattern for validating IAM role ARNs
IAM_ROLE_ARN_PATTERN = re.compile(r"^arn:aws:iam::\d{12}:role/[\w+=,.@-]+$")

# Regex pattern for validating Secrets Manager ARNs
SECRETS_MANAGER_ARN_PATTERN = re.compile(
    r"^arn:aws:secretsmanager:[a-z0-9-]+:\d{12}:secret:[\w/+=,.@-]+"
)


class IamPolicyStack(Stack):
    """
    Stack that adds Secrets Manager access policy to AgentCore execution role.

    This stack is deployed in Phase 3 of the deployment process, after the
    AgentCore agent and its execution role have been created. It imports
    the existing role and attaches an inline policy for secret access.

    The policy grants only secretsmanager:GetSecretValue on the specific
    secret ARN (no wildcards) following the principle of least privilege.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        execution_role_arn: str,
        secret_arn: str,
        **kwargs,
    ) -> None:
        """
        Initialize the IamPolicyStack.

        Args:
            scope: CDK app or stage scope.
            construct_id: Unique identifier for this stack.
            execution_role_arn: ARN of the AgentCore execution role to modify.
            secret_arn: ARN of the secret to grant access to.
            **kwargs: Additional stack properties (env, etc.).

        Raises:
            ValueError: If ARNs are empty or malformed.
        """
        super().__init__(scope, construct_id, **kwargs)

        # Validate inputs
        if not execution_role_arn:
            raise ValueError("execution_role_arn cannot be empty")
        if not IAM_ROLE_ARN_PATTERN.match(execution_role_arn):
            raise ValueError(f"Invalid IAM role ARN format: {execution_role_arn}")

        if not secret_arn:
            raise ValueError("secret_arn cannot be empty")
        if not SECRETS_MANAGER_ARN_PATTERN.match(secret_arn):
            raise ValueError(f"Invalid Secrets Manager ARN format: {secret_arn}")

        # Import the existing execution role created by agentcore
        execution_role = iam.Role.from_role_arn(
            self,
            "ExecutionRole",
            role_arn=execution_role_arn,
            mutable=True,  # Required to attach policies
        )

        # Create inline policy for Secrets Manager access
        # Use exact secret ARN (no wildcard) for least privilege
        secrets_policy = iam.Policy(
            self,
            "SecretsManagerAccess",
            policy_name=SECRETS_MANAGER_POLICY_NAME,
            statements=[
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["secretsmanager:GetSecretValue"],
                    resources=[secret_arn],
                )
            ],
        )

        # Attach to the imported role
        execution_role.attach_inline_policy(secrets_policy)

        CfnOutput(
            self,
            "PolicyName",
            value=secrets_policy.policy_name,
            description="Name of the Secrets Manager access policy",
        )
