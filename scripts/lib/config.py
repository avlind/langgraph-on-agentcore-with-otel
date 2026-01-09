"""Configuration loading and validation for deployment scripts."""

import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

from .console import print_error


class ConfigurationError(Exception):
    """Configuration validation error."""

    pass


@dataclass
class DeployConfig:
    """Validated deployment configuration."""

    aws_region: str
    agent_name: str
    model_id: str
    fallback_model_id: str
    secret_name: str
    tavily_api_key: str
    aws_profile: str | None = None


@dataclass
class DestroyConfig:
    """Configuration for destroy operation."""

    aws_region: str
    agent_name: str
    secret_name: str
    model_id: str
    fallback_model_id: str
    aws_profile: str | None = None


def load_env_file(env_path: Path = Path(".env")) -> dict[str, str]:
    """Load configuration from .env file using python-dotenv."""
    if not env_path.exists():
        raise ConfigurationError(
            f".env file not found at {env_path}. Copy .env.sample to .env and configure it."
        )
    return dict(dotenv_values(env_path))


def load_secrets_file(secrets_path: Path = Path(".secrets")) -> dict[str, str]:
    """Load secrets from .secrets file using python-dotenv."""
    if not secrets_path.exists():
        raise ConfigurationError(
            f".secrets file not found at {secrets_path}. "
            "Copy .secrets.sample to .secrets and add your API keys."
        )
    return dict(dotenv_values(secrets_path))


def validate_aws_region(region: str) -> None:
    """Validate AWS region format (e.g., us-east-2)."""
    pattern = r"^[a-z]{2}-[a-z]+-[0-9]+$"
    if not re.match(pattern, region):
        raise ConfigurationError(
            f"Invalid AWS_REGION format: {region} (expected format: us-east-2)"
        )


def validate_agent_name(name: str) -> None:
    """Validate agent name (alphanumeric and underscores only)."""
    pattern = r"^[a-zA-Z0-9_]+$"
    if not re.match(pattern, name):
        raise ConfigurationError(
            f"Invalid AGENT_NAME: {name} (use only alphanumeric and underscores)"
        )


def get_deploy_config(aws_profile: str | None = None) -> DeployConfig:
    """Load and validate complete deployment configuration."""
    # Load configuration from .env
    env = load_env_file()

    # Load secrets from .secrets
    secrets = load_secrets_file()

    # Get config values with defaults
    aws_region = env.get("AWS_REGION", "us-east-2")
    agent_name = env.get("AGENT_NAME", "langgraph_agent_web_search")
    model_id = env.get("MODEL_ID", "global.anthropic.claude-haiku-4-5-20251001-v1:0")
    fallback_model_id = env.get(
        "FALLBACK_MODEL_ID", "global.anthropic.claude-sonnet-4-5-20250929-v1:0"
    )
    secret_name = env.get("SECRET_NAME", "langgraph-agent/tavily-api-key")

    # Get secrets
    tavily_api_key = secrets.get("TAVILY_API_KEY", "")

    # Validate required values
    errors = []

    if not tavily_api_key:
        errors.append("TAVILY_API_KEY is not set in .secrets file")

    try:
        validate_aws_region(aws_region)
    except ConfigurationError as e:
        errors.append(str(e))

    try:
        validate_agent_name(agent_name)
    except ConfigurationError as e:
        errors.append(str(e))

    if errors:
        for error in errors:
            print_error(error)
        raise ConfigurationError("Configuration validation failed")

    # Set AWS_PROFILE environment variable if provided
    if aws_profile:
        os.environ["AWS_PROFILE"] = aws_profile

    return DeployConfig(
        aws_region=aws_region,
        agent_name=agent_name,
        model_id=model_id,
        fallback_model_id=fallback_model_id,
        secret_name=secret_name,
        tavily_api_key=tavily_api_key,
        aws_profile=aws_profile,
    )


def get_destroy_config(aws_profile: str | None = None) -> DestroyConfig:
    """Load configuration for destroy operation."""
    env = load_env_file()

    # Get values with defaults
    aws_region = env.get("AWS_REGION", "us-east-2")
    agent_name = env.get("AGENT_NAME", "langgraph_agent_web_search")
    secret_name = env.get("SECRET_NAME", "langgraph-agent/tavily-api-key")
    model_id = env.get("MODEL_ID", "global.anthropic.claude-haiku-4-5-20251001-v1:0")
    fallback_model_id = env.get(
        "FALLBACK_MODEL_ID", "global.anthropic.claude-sonnet-4-5-20250929-v1:0"
    )

    # Set AWS_PROFILE environment variable if provided
    if aws_profile:
        os.environ["AWS_PROFILE"] = aws_profile

    return DestroyConfig(
        aws_region=aws_region,
        agent_name=agent_name,
        secret_name=secret_name,
        model_id=model_id,
        fallback_model_id=fallback_model_id,
        aws_profile=aws_profile,
    )
