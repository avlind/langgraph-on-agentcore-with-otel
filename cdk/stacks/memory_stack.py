"""
CDK stack for AgentCore Memory.

This stack creates the AgentCore Memory resource separately from AgentInfraStack,
allowing it to be deployed in parallel with CodeBuild for faster deployment times.

Usage:
    cdk deploy MemoryStack \\
        --context agent_name="langgraph-search-agent"
"""

from aws_cdk import CfnOutput, Stack
from aws_cdk import aws_bedrockagentcore as agentcore
from constructs import Construct


class MemoryStack(Stack):
    """
    Stack for creating the AgentCore Memory resource.

    This stack is separate from AgentInfraStack to allow parallel deployment
    with CodeBuild, reducing overall deployment time.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        agent_name: str,
        **kwargs,
    ) -> None:
        """
        Initialize the MemoryStack.

        Args:
            scope: CDK app or stage scope.
            construct_id: Unique identifier for this stack.
            agent_name: Name for the agent (used in memory name).
            **kwargs: Additional stack properties.
        """
        super().__init__(scope, construct_id, **kwargs)

        # Validate input
        if not agent_name or not agent_name.strip():
            raise ValueError("agent_name cannot be empty")

        # AgentCore Memory
        # Name must match pattern ^[a-zA-Z][a-zA-Z0-9_]{0,47}$
        memory_name = f"{agent_name}_memory".replace("-", "_")
        memory = agentcore.CfnMemory(
            self,
            "AgentMemory",
            name=memory_name,
            event_expiry_duration=30,  # Days to retain events
            description=f"Memory store for {agent_name} agent",
        )

        # Output
        CfnOutput(
            self,
            "MemoryArn",
            value=memory.attr_memory_arn,
            description="AgentCore Memory ARN",
        )

        CfnOutput(
            self,
            "MemoryName",
            value=memory_name,
            description="AgentCore Memory name",
        )

        # Store reference for cross-stack usage
        self.memory = memory
