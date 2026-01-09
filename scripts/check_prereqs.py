#!/usr/bin/env python3
"""Check that all prerequisites are installed for the project.

This script verifies that required tools are available on the system
before running setup or other commands.
"""

import shutil
import subprocess
import sys


def check_command(name: str, install_hint: str, version_flag: str = "--version") -> bool:
    """Check if a command is available and print its version."""
    path = shutil.which(name)
    if not path:
        print(f"  ✗ {name} - NOT FOUND")
        print(f"    Install: {install_hint}")
        return False

    # Try to get version
    try:
        result = subprocess.run(
            [name, version_flag],
            capture_output=True,
            text=True,
            timeout=5,
        )
        version = result.stdout.strip().split("\n")[0] or result.stderr.strip().split("\n")[0]
        # Truncate long version strings
        if len(version) > 60:
            version = version[:60] + "..."
        print(f"  ✓ {name} - {version}")
    except (subprocess.TimeoutExpired, FileNotFoundError, IndexError):
        print(f"  ✓ {name} - found at {path}")

    return True


def main() -> int:
    """Check all prerequisites and return exit code."""
    print("Checking prerequisites...")
    print()

    all_found = True

    # Required tools
    checks = [
        ("uv", "curl -LsSf https://astral.sh/uv/install.sh | sh"),
        ("aws", "https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"),
        ("cdk", "npm install -g aws-cdk"),
        ("node", "https://nodejs.org/en/download/"),
    ]

    for name, install_hint in checks:
        if not check_command(name, install_hint):
            all_found = False

    print()

    if all_found:
        print("All prerequisites found!")
        return 0
    else:
        print("Some prerequisites are missing. Please install them and try again.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
