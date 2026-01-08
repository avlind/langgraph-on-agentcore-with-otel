"""Destroy LangGraph agent and clean up AWS resources using CDK.

Since all resources (including AgentCore Runtime) are managed by CDK,
this script simply runs `cdk destroy --all`.
"""

import time
from pathlib import Path
from typing import Annotated

import typer

from .lib.commands import CommandError, check_command_exists
from .lib.config import ConfigurationError, get_destroy_config
from .lib.console import (
    console,
    print_config,
    print_error,
    print_final_success,
    print_header,
    print_step,
    print_success,
)

app = typer.Typer(help="Destroy LangGraph agent and clean up AWS resources")


def run_cdk_destroy(
    config,
    profile: str | None = None,
    force: bool = False,
) -> bool:
    """Run CDK destroy --all to remove all stacks."""
    import subprocess

    cdk_dir = Path("cdk")

    # Get absolute path to project root
    source_path = str(Path.cwd().absolute())

    cmd = [
        "cdk",
        "destroy",
        "--all",
        "--context",
        f"secret_name={config.secret_name}",
        "--context",
        "tavily_api_key=dummy",  # Not needed for destroy but required for CDK synth
        "--context",
        f"agent_name={config.agent_name}",
        "--context",
        f"model_id={config.model_id}",
        "--context",
        f"fallback_model_id={config.fallback_model_id}",
        "--context",
        f"source_path={source_path}",
    ]

    if force:
        cmd.append("--force")

    if profile:
        cmd.extend(["--profile", profile])

    console.print("   Running: cdk destroy --all ...")

    result = subprocess.run(
        cmd,
        cwd=cdk_dir,
        capture_output=False,  # Stream output to console
    )

    return result.returncode == 0


@app.command()
def destroy(
    profile: Annotated[
        str | None,
        typer.Option("--profile", help="AWS CLI profile name (for SSO users)"),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Skip confirmation prompts"),
    ] = False,
    all_resources: Annotated[
        bool,
        typer.Option("--all", help="Destroy all resources (same as default behavior)"),
    ] = False,
) -> None:
    """
    Destroy the LangGraph agent and all AWS resources.

    This command runs `cdk destroy --all` to remove:
    - RuntimeStack (AgentCore Runtime)
    - AgentInfraStack (ECR, CodeBuild, IAM, Memory)
    - SecretsStack (Secrets Manager secret)
    """
    start_time = time.time()

    try:
        # Check cdk is available
        if not check_command_exists("cdk"):
            print_error("AWS CDK CLI not found.")
            console.print()
            console.print("   Install it globally with:")
            console.print()
            console.print("      npm install -g aws-cdk")
            console.print()
            raise typer.Exit(1)

        # Load configuration
        config = get_destroy_config(profile)

        # Print header
        print_header("LangGraph Agent Cleanup (CDK)")
        print_config(
            region=config.aws_region,
            agent_name=config.agent_name,
            secret_name=config.secret_name,
            profile=config.aws_profile,
        )

        # Step 1: Destroy all CDK stacks
        print_step("1/1", "Destroying all CDK stacks...")

        if not run_cdk_destroy(config, profile, force):
            print_error("CDK destroy failed")
            raise typer.Exit(1)

        print_success("All CDK stacks destroyed")

        # Success message with elapsed time
        elapsed = time.time() - start_time
        minutes, seconds = divmod(int(elapsed), 60)
        time_str = f"{minutes}m {seconds}s" if minutes else f"{seconds}s"

        print_final_success(f"Cleanup complete! (Total time: {time_str})")
        console.print()
        console.print("[bold]To redeploy:[/bold]")
        console.print("  make deploy PROFILE=<profile>")

    except ConfigurationError:
        raise typer.Exit(1)
    except CommandError:
        raise typer.Exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Cleanup cancelled.[/yellow]")
        raise typer.Exit(130)


def main() -> None:
    """Entry point for the destroy script."""
    app()


if __name__ == "__main__":
    main()
