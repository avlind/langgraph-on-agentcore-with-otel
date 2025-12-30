"""Destroy LangGraph agent and clean up AWS resources."""

from pathlib import Path
from typing import Annotated

import typer

from .lib.aws import (
    delete_ecr_repository,
    delete_secret,
    delete_stack_and_wait,
    get_session,
)
from .lib.commands import CommandError, check_command_exists, run_agentcore_destroy
from .lib.config import ConfigurationError, get_destroy_config
from .lib.console import (
    console,
    print_config,
    print_error,
    print_final_success,
    print_header,
    print_step,
    print_success,
    print_warning,
)

app = typer.Typer(help="Destroy LangGraph agent and clean up AWS resources")


@app.command()
def destroy(
    profile: Annotated[
        str | None,
        typer.Option("--profile", help="AWS CLI profile name (for SSO users)"),
    ] = None,
    delete_secret_flag: Annotated[
        bool,
        typer.Option("--delete-secret", help="Also delete the Secrets Manager secret"),
    ] = False,
    delete_ecr: Annotated[
        bool,
        typer.Option("--delete-ecr", help="Also delete the ECR repository"),
    ] = False,
    all_resources: Annotated[
        bool,
        typer.Option("--all", help="Delete everything (agent + secret + ECR)"),
    ] = False,
) -> None:
    """
    Destroy the LangGraph agent and optionally clean up resources.

    By default, only the AgentCore agent and IAM policy stack are destroyed.
    The secret and ECR repo are preserved for faster redeployment.

    Use --all to delete everything, or use individual flags:

    --delete-secret: Delete the Secrets Manager secret

    --delete-ecr: Delete the ECR repository
    """
    try:
        # Check agentcore is available
        if not check_command_exists("agentcore"):
            print_error("agentcore command not found.")
            console.print()
            console.print("   Run this script via uv or make:")
            console.print()
            console.print("      uv run python -m scripts.destroy --profile YourProfile")
            console.print("      # or")
            console.print("      make destroy PROFILE=YourProfile")
            console.print()
            raise typer.Exit(1)

        # Load configuration
        config = get_destroy_config(profile)

        # Handle --all flag
        if all_resources:
            delete_secret_flag = True
            delete_ecr = True

        # Calculate total steps
        total_steps = 2  # IAM policy stack + AgentCore agent
        if delete_secret_flag:
            total_steps += 1
        if delete_ecr:
            total_steps += 1

        current_step = 0

        # Print header
        print_header("LangGraph Agent Cleanup", emoji="🗑️")
        print_config(
            region=config.aws_region,
            agent_name=config.agent_name,
            secret_name=config.secret_name if delete_secret_flag else None,
            profile=config.aws_profile,
            delete_secret=delete_secret_flag,
            delete_ecr=delete_ecr,
        )

        session = get_session(profile)

        # Step 1: Destroy IAM Policy Stack
        current_step += 1
        print_step(f"{current_step}/{total_steps}", "Destroying IAM policy stack...")
        delete_stack_and_wait(session, "IamPolicyStack", config.aws_region)

        # Step 2: Destroy AgentCore agent
        current_step += 1
        print_step(f"{current_step}/{total_steps}", "Destroying AgentCore agent...")

        config_path = Path(".bedrock_agentcore.yaml")
        if config_path.exists():
            result = run_agentcore_destroy(config.agent_name, profile)
            if result.success:
                print_success("Agent destroyed")
            else:
                print_warning("Agent destruction may have failed, continuing...")
        else:
            print_warning("No .bedrock_agentcore.yaml found, agent may already be destroyed")

        # Step 3: Delete Secrets Stack (if requested)
        if delete_secret_flag:
            current_step += 1
            print_step(f"{current_step}/{total_steps}", "Destroying Secrets Manager stack...")

            delete_stack_and_wait(session, "SecretsStack", config.aws_region)

            # Also delete the actual secret (has RETAIN policy)
            delete_secret(session, config.secret_name, config.aws_region)

        # Step 4: Delete ECR repository (if requested)
        if delete_ecr:
            current_step += 1
            print_step(f"{current_step}/{total_steps}", "Deleting ECR repository...")

            ecr_repo = f"bedrock-agentcore-{config.agent_name}"
            delete_ecr_repository(session, ecr_repo, config.aws_region)

        # Success message
        print_final_success("Cleanup complete!")

        # Show preserved resources
        if not delete_secret_flag or not delete_ecr:
            console.print()
            console.print("Resources preserved (use flags to delete):")
            if not delete_secret_flag:
                console.print("   • Secrets Manager secret (--delete-secret)")
            if not delete_ecr:
                console.print("   • ECR repository (--delete-ecr)")
            console.print()
            console.print("To delete everything: python -m scripts.destroy --all")

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
