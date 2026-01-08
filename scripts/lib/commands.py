"""Subprocess execution for external tools (cdk)."""

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .console import print_error


class CommandError(Exception):
    """External command execution error."""

    pass


@dataclass
class CommandResult:
    """Result of a subprocess command."""

    returncode: int
    stdout: str
    stderr: str

    @property
    def success(self) -> bool:
        return self.returncode == 0


def check_command_exists(cmd: str) -> bool:
    """Check if a command is available in PATH."""
    return shutil.which(cmd) is not None


def check_required_commands() -> None:
    """Check that cdk is available."""
    if not check_command_exists("cdk"):
        print_error("AWS CDK CLI not found.")
        print_error("")
        print_error("   Install it globally with:")
        print_error("")
        print_error("      npm install -g aws-cdk")
        print_error("")
        raise CommandError("cdk not found")


def run_command(
    cmd: list[str],
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
    capture_output: bool = True,
) -> CommandResult:
    """Run a subprocess command."""
    full_env = {**os.environ, **(env or {})}

    result = subprocess.run(
        cmd,
        env=full_env,
        cwd=cwd,
        capture_output=capture_output,
        text=True,
    )

    return CommandResult(
        returncode=result.returncode,
        stdout=result.stdout if capture_output else "",
        stderr=result.stderr if capture_output else "",
    )


def run_cdk_deploy(
    stack: str,
    context: dict[str, str],
    cwd: Path,
    profile: str | None = None,
) -> CommandResult:
    """Deploy a CDK stack."""
    cmd = ["cdk", "deploy", stack, "--require-approval", "never"]

    for key, value in context.items():
        cmd.extend(["--context", f"{key}={value}"])

    env = {}
    if profile:
        env["AWS_PROFILE"] = profile

    # Run CDK deploy - don't capture output so user sees progress
    result = subprocess.run(
        cmd,
        env={**os.environ, **env},
        cwd=cwd,
        capture_output=False,
    )

    return CommandResult(
        returncode=result.returncode,
        stdout="",
        stderr="",
    )


def run_cdk_bootstrap(
    account_id: str,
    region: str,
    profile: str | None = None,
) -> CommandResult:
    """Bootstrap CDK in the account/region."""
    cmd = ["cdk", "bootstrap", f"aws://{account_id}/{region}"]

    env = {}
    if profile:
        env["AWS_PROFILE"] = profile

    result = subprocess.run(
        cmd,
        env={**os.environ, **env},
        capture_output=False,
    )

    return CommandResult(
        returncode=result.returncode,
        stdout="",
        stderr="",
    )
