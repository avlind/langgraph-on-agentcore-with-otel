"""
CDK stack for Secrets Manager resources.

This stack creates an AWS Secrets Manager secret to store the Tavily API key.
The secret is created with RETAIN removal policy to preserve it across stack
deletions (useful for iterative development).

Usage:
    cdk deploy SecretsStack \\
        --context secret_name="langgraph-agent/tavily-api-key" \\
        --context tavily_api_key="your-api-key"
"""

from aws_cdk import CfnOutput, RemovalPolicy, SecretValue, Stack
from aws_cdk import aws_secretsmanager as secretsmanager
from constructs import Construct


class SecretsStack(Stack):
    """
    Stack managing the Tavily API key secret in Secrets Manager.

    This stack is deployed in Phase 1 of the deployment process, before
    the AgentCore agent is created. The secret ARN is exported for use
    by the IamPolicyStack.

    Attributes:
        secret: The Secrets Manager secret resource.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        secret_name: str,
        tavily_api_key: str,
        **kwargs,
    ) -> None:
        """
        Initialize the SecretsStack.

        Args:
            scope: CDK app or stage scope.
            construct_id: Unique identifier for this stack.
            secret_name: Name for the secret in Secrets Manager.
            tavily_api_key: The Tavily API key value to store.
            **kwargs: Additional stack properties (env, etc.).

        Raises:
            ValueError: If secret_name or tavily_api_key is empty.
        """
        super().__init__(scope, construct_id, **kwargs)

        # Validate inputs
        if not secret_name or not secret_name.strip():
            raise ValueError("secret_name cannot be empty")
        if not tavily_api_key or not tavily_api_key.strip():
            raise ValueError("tavily_api_key cannot be empty")

        # Create the secret with explicit name
        # Note: unsafe_plain_text is used because the key is passed via CDK context
        # from deploy.sh. The secret value is not logged by CDK.
        self.secret = secretsmanager.Secret(
            self,
            "TavilyApiKey",
            secret_name=secret_name,
            secret_string_value=SecretValue.unsafe_plain_text(tavily_api_key),
            removal_policy=RemovalPolicy.RETAIN,
            description="Tavily API key for LangGraph agent web search",
        )

        # Export ARN for use by deploy script and IamPolicyStack
        CfnOutput(
            self,
            "SecretArn",
            value=self.secret.secret_arn,
            description="ARN of the Tavily API key secret",
            export_name=f"{construct_id}-SecretArn",
        )

        CfnOutput(
            self,
            "SecretName",
            value=secret_name,
            description="Name of the Tavily API key secret",
            export_name=f"{construct_id}-SecretName",
        )
