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
