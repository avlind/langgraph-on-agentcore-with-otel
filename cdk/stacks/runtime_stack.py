"""
CDK stack for AgentCore Runtime.

This stack creates ONLY the AgentCore Runtime resource.
It must be deployed AFTER the AgentInfraStack and CodeBuild have run,
because the Runtime validation requires the ECR image to exist.

Usage:
    # Deploy after CodeBuild has pushed the image
    cdk deploy RuntimeStack \\
        --context agent_name="langgraph-search-agent" \\
        --context model_id="..." \\
        --context fallback_model_id="..." \\
        --context secret_name="..."
"""

from aws_cdk import CfnOutput, Stack
from aws_cdk import aws_bedrockagentcore as agentcore
from constructs import Construct


class RuntimeStack(Stack):
    """
    Stack for creating the AgentCore Runtime.

    This stack is separate from AgentInfraStack because the Runtime
    requires the ECR image to exist before it can be created.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        agent_name: str,
        model_id: str,
        fallback_model_id: str,
        secret_name: str,
        ecr_repository_uri: str,
        execution_role_arn: str,
        subnet_ids: list[str],
        security_group_ids: list[str],
        **kwargs,
    ) -> None:
        """
        Initialize the RuntimeStack.

        Args:
            scope: CDK app or stage scope.
            construct_id: Unique identifier for this stack.
            agent_name: Name for the AgentCore runtime.
            model_id: Primary Bedrock model ID.
            fallback_model_id: Fallback Bedrock model ID.
            secret_name: Name of the secret containing API keys.
            ecr_repository_uri: URI of the ECR repository (from AgentInfraStack).
            execution_role_arn: ARN of the execution role (from AgentInfraStack).
            subnet_ids: Private subnet IDs for VPC networking.
            security_group_ids: Security group IDs for VPC networking.
            **kwargs: Additional stack properties.
        """
        super().__init__(scope, construct_id, **kwargs)

        # AgentCore Runtime
        runtime = agentcore.CfnRuntime(
            self,
            "AgentRuntime",
            agent_runtime_name=agent_name,
            agent_runtime_artifact={
                "containerConfiguration": {"containerUri": f"{ecr_repository_uri}:latest"}
            },
            role_arn=execution_role_arn,
            network_configuration=agentcore.CfnRuntime.NetworkConfigurationProperty(
                network_mode="PRIVATE",
                network_mode_config=agentcore.CfnRuntime.VpcConfigProperty(
                    subnets=subnet_ids,
                    security_groups=security_group_ids,
                ),
            ),
            environment_variables={
                "AWS_REGION": self.region,
                "SECRET_NAME": secret_name,
                "MODEL_ID": model_id,
                "FALLBACK_MODEL_ID": fallback_model_id,
            },
            protocol_configuration="HTTP",
            description=f"LangGraph agent runtime for {agent_name}",
        )

        # Outputs
        CfnOutput(
            self,
            "RuntimeArn",
            value=runtime.attr_agent_runtime_arn,
            description="AgentCore Runtime ARN",
        )

        CfnOutput(
            self,
            "RuntimeId",
            value=runtime.attr_agent_runtime_id,
            description="AgentCore Runtime ID",
        )

        # Store reference
        self.runtime = runtime
