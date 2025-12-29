"""CDK stack for Secrets Manager resources."""

from aws_cdk import CfnOutput, RemovalPolicy, SecretValue, Stack
from aws_cdk import aws_secretsmanager as secretsmanager
from constructs import Construct


class SecretsStack(Stack):
    """Stack managing the Tavily API key secret in Secrets Manager."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        secret_name: str,
        tavily_api_key: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create the secret with explicit name
        self.secret = secretsmanager.Secret(
            self,
            "TavilyApiKey",
            secret_name=secret_name,
            secret_string_value=SecretValue.unsafe_plain_text(tavily_api_key),
            removal_policy=RemovalPolicy.RETAIN,
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
