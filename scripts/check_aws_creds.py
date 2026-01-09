#!/usr/bin/env python3
"""Check AWS credentials and provide helpful feedback."""

import argparse
import os
import subprocess
import sys


def check_aws_credentials(interactive: bool = False) -> bool:
    """
    Check if AWS credentials are valid and print status.

    Args:
        interactive: If True, offer to run SSO login when expired.

    Returns:
        True if credentials are valid, False otherwise.
    """
    profile = os.environ.get("AWS_PROFILE", "")

    # Build the command
    cmd = ["aws", "sts", "get-caller-identity", "--output", "json"]
    if profile:
        cmd.extend(["--profile", profile])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

        if result.returncode == 0:
            # Credentials are valid
            if profile:
                print(f"✓ Using AWS SSO Profile: {profile}")
            elif os.environ.get("AWS_ACCESS_KEY_ID"):
                print("✓ Using AWS credentials from environment variables")
            else:
                print("✓ Using AWS default credentials")
            return True

        # Credentials failed - check error type
        error_output = result.stderr.lower()

        if "token has expired" in error_output or is_sso_error(error_output):
            return handle_sso_expired(profile, interactive)
        elif "could not be found" in error_output and "profile" in error_output:
            print_profile_not_found_help(profile)
        elif "could not find credentials" in error_output or "unable to locate" in error_output:
            print_no_credentials_help(profile)
        else:
            print_generic_error(profile, result.stderr)

        return False

    except subprocess.TimeoutExpired:
        print("✗ AWS credential check timed out")
        print_no_credentials_help(profile)
        return False
    except FileNotFoundError:
        print("✗ AWS CLI not found. Please install the AWS CLI:")
        print("  https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html")
        return False


def is_sso_error(error_output: str) -> bool:
    """Check if error is SSO-related."""
    sso_indicators = ["sso", "token", "refresh", "expired", "authorization"]
    return any(indicator in error_output for indicator in sso_indicators)


def handle_sso_expired(profile: str, interactive: bool) -> bool:
    """Handle expired SSO session, optionally offering interactive login."""
    print("✗ AWS SSO session has expired")
    print("")

    if not profile:
        print("To refresh your SSO session, run:")
        print("  aws sso login")
        print("")
        return False

    if not interactive:
        print("To refresh your SSO session, run:")
        print(f"  aws sso login --profile {profile}")
        print("")
        return False

    # Interactive mode - offer to login
    print("Would you like to login now? This will run:")
    print(f"  aws sso login --profile {profile}")
    print("")

    try:
        response = input("Run SSO login? [Y/n]: ").strip().lower()
        if response in ("", "y", "yes"):
            return run_sso_login(profile)
        else:
            print("")
            print("Skipped. To login manually, run:")
            print(f"  aws sso login --profile {profile}")
            print("")
            return False
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.")
        return False


def run_sso_login(profile: str) -> bool:
    """Run AWS SSO login and return success status."""
    print("")
    print(f"Starting SSO login for profile '{profile}'...")
    print("(This will open your browser)")
    print("")

    try:
        # Run SSO login interactively (not capturing output so user sees it)
        result = subprocess.run(
            ["aws", "sso", "login", "--profile", profile],
            timeout=300,  # 5 minute timeout for browser auth
        )

        if result.returncode == 0:
            print("")
            print(f"✓ SSO login successful for profile: {profile}")
            return True
        else:
            print("")
            print("✗ SSO login failed")
            return False

    except subprocess.TimeoutExpired:
        print("")
        print("✗ SSO login timed out (5 minute limit)")
        return False
    except KeyboardInterrupt:
        print("")
        print("✗ SSO login cancelled")
        return False


def print_profile_not_found_help(profile: str) -> None:
    """Print help when profile doesn't exist."""
    print(f"✗ AWS profile '{profile}' not found")
    print("")
    print("To fix this, choose one of these options:")
    print("")
    print("Option 1: Configure SSO with this profile name")
    print(f"  aws configure sso --profile {profile}")
    print("")
    print("Option 2: Use a different profile")
    print("  make set-profile PROFILE=YourExistingProfile")
    print("")
    print("Option 3: List available profiles")
    print("  aws configure list-profiles")
    print("")


def print_no_credentials_help(profile: str) -> None:
    """Print help when no credentials are found."""
    print("✗ No AWS credentials found")
    print("")
    print("To configure AWS credentials, choose one of these options:")
    print("")
    print("Option 1: SSO Login (recommended for organizations)")
    if profile:
        print(f"  aws sso login --profile {profile}")
    else:
        print("  aws configure sso                          # First-time setup")
        print("  aws sso login --profile YourProfile        # Login to SSO")
        print("  make set-profile PROFILE=YourProfile       # Save for make commands")
    print("")
    print("Option 2: Configure default credentials (access keys)")
    print("  aws configure                              # Prompts for access key/secret")
    print("  # Then run make commands without PROFILE")
    print("")
    print("Option 3: Set environment variables")
    print("  export AWS_ACCESS_KEY_ID=your-key-id")
    print("  export AWS_SECRET_ACCESS_KEY=your-secret-key")
    print("  export AWS_REGION=us-east-1")
    print("")


def print_generic_error(profile: str, error: str) -> None:
    """Print generic error with help."""
    print("✗ AWS credentials are invalid or expired")
    print("")
    print(f"Error: {error.strip()}")
    print("")
    if profile:
        print("Try refreshing your SSO session:")
        print(f"  aws sso login --profile {profile}")
    else:
        print("Try running:")
        print("  aws configure")
    print("")


def main() -> int:
    """Main entry point with argument parsing."""
    parser = argparse.ArgumentParser(description="Check AWS credentials")
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Offer to run SSO login if session is expired",
    )
    args = parser.parse_args()

    success = check_aws_credentials(interactive=args.interactive)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
