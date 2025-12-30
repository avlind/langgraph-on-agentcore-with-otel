"""YAML parsing for .bedrock_agentcore.yaml."""

from pathlib import Path

import yaml


def extract_execution_role_arn(config_path: Path, agent_name: str) -> str | None:
    """
    Extract execution role ARN from .bedrock_agentcore.yaml.

    Looks for the execution_role containing 'Runtime' under the
    specified agent name.

    Args:
        config_path: Path to .bedrock_agentcore.yaml
        agent_name: Name of the agent to look for

    Returns:
        The execution role ARN if found, None otherwise.
    """
    if not config_path.exists():
        return None

    with open(config_path) as f:
        config = yaml.safe_load(f)

    if not config:
        return None

    # Navigate to agents section
    agents = config.get("agents", {})
    agent_config = agents.get(agent_name, {})

    if not agent_config:
        return None

    # The execution_role is nested under 'aws' in the config
    aws_config = agent_config.get("aws", {})
    execution_role = aws_config.get("execution_role", "")

    if execution_role and "Runtime" in execution_role:
        return execution_role

    return None
