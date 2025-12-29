"""CDK stack for IAM policies attached to the AgentCore execution role."""

from aws_cdk import CfnOutput, Stack
from aws_cdk import aws_iam as iam
from constructs import Construct


class IamPolicyStack(Stack):
    """Stack that adds Secrets Manager access policy to AgentCore execution role."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        execution_role_arn: str,
        secret_arn: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Import the existing execution role created by agentcore
        execution_role = iam.Role.from_role_arn(
            self,
            "ExecutionRole",
            role_arn=execution_role_arn,
            mutable=True,
        )

        # Create inline policy for Secrets Manager access
        secrets_policy = iam.Policy(
            self,
            "SecretsManagerAccess",
            policy_name="SecretsManagerAccess",
            statements=[
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["secretsmanager:GetSecretValue"],
                    resources=[f"{secret_arn}*"],
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
