"""Deploy LangGraph agent to AWS Bedrock AgentCore using CDK.

This deployment script uses CDK to deploy all infrastructure in phases:
1. SecretsStack + AgentInfraStack: Secrets, ECR, CodeBuild, IAM
2. CodeBuild + MemoryStack: Build Docker image AND create Memory (parallel)
3. RuntimeStack: Create the AgentCore Runtime (needs image to exist)
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Annotated

import typer

from .lib.aws import check_cdk_bootstrap, get_account_id, get_session
from .lib.commands import CommandError, check_required_commands, run_cdk_bootstrap
from .lib.config import ConfigurationError, get_deploy_config
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

app = typer.Typer(help="Deploy LangGraph agent to AWS Bedrock AgentCore")


def run_cdk_deploy(
    config,
    source_path: str,
    stacks: list[str],
    profile: str | None = None,
) -> bool:
    """Run CDK deploy for specific stacks with all required context values."""
    import subprocess

    cdk_dir = Path("cdk")

    cmd = [
        "cdk",
        "deploy",
        *stacks,
        "--require-approval",
        "never",
        "--context",
        f"secret_name={config.secret_name}",
        "--context",
        f"tavily_api_key={config.tavily_api_key}",
        "--context",
        f"agent_name={config.agent_name}",
        "--context",
        f"model_id={config.model_id}",
        "--context",
        f"fallback_model_id={config.fallback_model_id}",
        "--context",
        f"source_path={source_path}",
    ]

    if profile:
        cmd.extend(["--profile", profile])

    stack_names = " ".join(stacks)
    console.print(f"   Running: cdk deploy {stack_names} ...")

    result = subprocess.run(
        cmd,
        cwd=cdk_dir,
        capture_output=False,  # Stream output to console
    )

    return result.returncode == 0


def trigger_codebuild(config, profile: str | None = None) -> bool:
    """Trigger CodeBuild to build the Docker image."""
    import time

    session = get_session(profile)
    codebuild = session.client("codebuild", region_name=config.aws_region)

    project_name = f"{config.agent_name}-builder"

    try:
        console.print(f"   Triggering CodeBuild project: {project_name}")
        response = codebuild.start_build(projectName=project_name)
        build_id = response["build"]["id"]
        console.print(f"   Build started: {build_id}")

        # Poll for build completion (CodeBuild doesn't have a waiter)
        console.print("   Waiting for build to complete...")
        max_attempts = 60
        delay = 10

        while max_attempts > 0:
            build_response = codebuild.batch_get_builds(ids=[build_id])
            build = build_response["builds"][0]
            build_status = build.get("buildStatus")
            build_complete = build.get("buildComplete", False)

            if build_complete:
                if build_status == "SUCCEEDED":
                    return True
                else:
                    console.print(f"   [red]Build failed with status: {build_status}[/red]")
                    return False

            console.print(f"   Status: {build_status}...")
            time.sleep(delay)
            max_attempts -= 1

        console.print("   [red]Timeout waiting for build[/red]")
        return False

    except Exception as e:
        console.print(f"   [red]CodeBuild error: {e}[/red]")
        return False


@app.command()
def deploy(
    profile: Annotated[
        str | None,
        typer.Option("--profile", help="AWS CLI profile name (for SSO users)"),
    ] = None,
) -> None:
    """
    Deploy the LangGraph agent to AWS Bedrock AgentCore.

    This command:
    1. Deploys CDK infrastructure (SecretsStack + AgentInfraStack)
    2. Triggers CodeBuild to build the agent container
    3. Deploys the RuntimeStack (AgentCore Runtime via CDK)
    """
    start_time = time.time()

    try:
        # Check required commands
        check_required_commands()

        # Load and validate configuration
        config = get_deploy_config(profile)

        # Check CDK bootstrap
        session = get_session(profile)
        if not check_cdk_bootstrap(session, config.aws_region):
            print_warning("CDK not bootstrapped in this account/region.")
            console.print()
            console.print("   Bootstrapping CDK (one-time setup)...")
            account_id = get_account_id(session)
            result = run_cdk_bootstrap(account_id, config.aws_region, profile)
            if not result.success:
                print_error("CDK bootstrap failed")
                raise typer.Exit(1)
            print_success("CDK bootstrapped successfully")

        # Print header
        print_header("LangGraph Agent Deployment (CDK)")
        print_config(
            region=config.aws_region,
            agent_name=config.agent_name,
            model_id=config.model_id,
            secret_name=config.secret_name,
            profile=config.aws_profile,
        )

        # Get absolute path to project root
        source_path = str(Path.cwd().absolute())

        # Step 1: Deploy infrastructure stacks (SecretsStack + AgentInfraStack)
        print_step("1/3", "Deploying infrastructure (SecretsStack + AgentInfraStack)...")

        if not run_cdk_deploy(config, source_path, ["SecretsStack", "AgentInfraStack"], profile):
            print_error("CDK infrastructure deployment failed")
            raise typer.Exit(1)

        print_success("Infrastructure stacks deployed successfully")

        # Step 2: Run CodeBuild + MemoryStack in parallel
        print_step("2/3", "Building container + deploying Memory (parallel)...")

        codebuild_success = False
        memory_success = False

        with ThreadPoolExecutor(max_workers=2) as executor:
            # Submit both tasks
            codebuild_future = executor.submit(trigger_codebuild, config, profile)
            memory_future = executor.submit(
                run_cdk_deploy, config, source_path, ["MemoryStack"], profile
            )

            # Wait for both to complete and collect results
            for future in as_completed([codebuild_future, memory_future]):
                if future == codebuild_future:
                    codebuild_success = future.result()
                    if codebuild_success:
                        console.print("   [green]✓[/green] CodeBuild completed")
                    else:
                        console.print("   [red]✗[/red] CodeBuild failed")
                else:
                    memory_success = future.result()
                    if memory_success:
                        console.print("   [green]✓[/green] MemoryStack deployed")
                    else:
                        console.print("   [red]✗[/red] MemoryStack deployment failed")

        if not codebuild_success:
            print_error("CodeBuild failed - check AWS Console for details")
            raise typer.Exit(1)

        if not memory_success:
            print_error("MemoryStack deployment failed")
            raise typer.Exit(1)

        print_success("Container built and Memory deployed successfully")

        # Step 3: Deploy RuntimeStack (AgentCore Runtime)
        print_step("3/3", "Deploying RuntimeStack (AgentCore Runtime)...")

        if not run_cdk_deploy(config, source_path, ["RuntimeStack"], profile):
            print_error("Runtime deployment failed")
            raise typer.Exit(1)

        print_success("RuntimeStack deployed successfully")

        # Success message with elapsed time
        elapsed = time.time() - start_time
        minutes, seconds = divmod(int(elapsed), 60)
        time_str = f"{minutes}m {seconds}s" if minutes else f"{seconds}s"

        print_final_success(f"Deployment successful! (Total time: {time_str})")
        console.print()
        console.print("[bold]Next steps:[/bold]")
        console.print("  - Test: make invoke PROFILE=<profile>")
        console.print("  - Destroy: make destroy-all PROFILE=<profile>")

    except ConfigurationError:
        raise typer.Exit(1)
    except CommandError:
        raise typer.Exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Deployment cancelled.[/yellow]")
        raise typer.Exit(130)


def main() -> None:
    """Entry point for the deploy script."""
    app()


if __name__ == "__main__":
    main()
