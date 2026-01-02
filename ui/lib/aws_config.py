"""Parse AWS config file for available profiles."""

import configparser
import os
from pathlib import Path


def get_aws_profiles() -> list[str]:
    """
    Parse ~/.aws/config to extract available profile names.

    Returns a list of profile names sorted alphabetically.
    The 'default' profile is always first if it exists.
    """
    config_path = Path.home() / ".aws" / "config"

    if not config_path.exists():
        # Fall back to checking credentials file
        credentials_path = Path.home() / ".aws" / "credentials"
        if credentials_path.exists():
            return _parse_credentials_file(credentials_path)
        return ["default"]

    profiles = _parse_config_file(config_path)

    # Also check credentials file for additional profiles
    credentials_path = Path.home() / ".aws" / "credentials"
    if credentials_path.exists():
        cred_profiles = _parse_credentials_file(credentials_path)
        profiles = list(set(profiles) | set(cred_profiles))

    # Sort profiles with 'default' first
    profiles = sorted(profiles, key=lambda p: (p != "default", p.lower()))

    return profiles if profiles else ["default"]


def _parse_config_file(path: Path) -> list[str]:
    """Parse AWS config file format (sections are [profile name] or [default])."""
    config = configparser.ConfigParser()
    try:
        config.read(path)
    except configparser.Error:
        return []

    profiles = []
    for section in config.sections():
        if section == "default":
            profiles.append("default")
        elif section.startswith("profile "):
            profile_name = section[8:]  # Remove "profile " prefix
            profiles.append(profile_name)

    # Check if [default] exists
    if config.has_section("default") and "default" not in profiles:
        profiles.append("default")

    return profiles


def _parse_credentials_file(path: Path) -> list[str]:
    """Parse AWS credentials file format (sections are [profile_name])."""
    config = configparser.ConfigParser()
    try:
        config.read(path)
    except configparser.Error:
        return []

    return list(config.sections())


def get_current_profile() -> str:
    """Get the currently active AWS profile from environment."""
    return os.environ.get("AWS_PROFILE", "default")


def get_agentcore_region() -> str:
    """
    Get AWS region from agentcore config file.

    Reads from .bedrock_agentcore.yaml in the project root.
    Falls back to us-east-1 if not found.
    """
    config = get_agentcore_config()
    return config.get("region", os.environ.get("AWS_REGION", "us-east-1"))


def get_agentcore_config() -> dict:
    """
    Get agentcore configuration from .bedrock_agentcore.yaml.

    Returns dict with keys: region, account, agent_name, agent_id, endpoint_name
    """
    import yaml

    default_config = {
        "region": os.environ.get("AWS_REGION", "us-east-1"),
        "account": "",
        "agent_name": "",
        "agent_id": "",
        "endpoint_name": "DEFAULT",
    }

    config_path = Path.cwd() / ".bedrock_agentcore.yaml"
    if not config_path.exists():
        return default_config

    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)

        default_agent = config.get("default_agent")
        if not default_agent or "agents" not in config:
            return default_config

        agent_config = config["agents"].get(default_agent, {})
        aws_config = agent_config.get("aws", {})
        bedrock_config = agent_config.get("bedrock_agentcore", {})

        return {
            "region": aws_config.get("region", default_config["region"]),
            "account": aws_config.get("account", ""),
            "agent_name": agent_config.get("name", default_agent),
            "agent_id": bedrock_config.get("agent_id", ""),
            "endpoint_name": "DEFAULT",
        }
    except Exception:
        return default_config


def build_cloudwatch_session_url(session_id: str) -> str | None:
    """
    Build CloudWatch GenAI Observability URL for a specific session.

    Returns the full deep link URL, or None if config is incomplete.
    """
    from urllib.parse import quote

    config = get_agentcore_config()

    # Require all fields for deep link
    if not all([config["region"], config["account"], config["agent_name"], config["agent_id"]]):
        return None

    region = config["region"]
    account = config["account"]
    agent_name = config["agent_name"]
    agent_id = config["agent_id"]
    endpoint = config["endpoint_name"]

    # Build resource ARN (URL encoded)
    resource_arn = (
        f"arn:aws:bedrock-agentcore:{region}:{account}:"
        f"runtime/{agent_id}/runtime-endpoint/{endpoint}:{endpoint}"
    )
    encoded_arn = quote(resource_arn, safe="")

    # Build service name
    service_name = f"{agent_name}.{endpoint}"

    # Build full URL
    url = (
        f"https://{region}.console.aws.amazon.com/cloudwatch/home?region={region}"
        f"#gen-ai-observability/agent-core/agent-alias/{agent_id}/endpoint/{endpoint}"
        f"/agent/{agent_name}/session/{session_id}"
        f"?resourceId={encoded_arn}&serviceName={service_name}"
    )

    return url
