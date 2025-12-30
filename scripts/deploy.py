"""Deploy LangGraph agent to AWS Bedrock AgentCore."""

import sys
from pathlib import Path
from typing import Annotated

import typer

from .lib.aws import (
    check_cdk_bootstrap,
    get_account_id,
    get_session,
    get_stack_output,
    stack_exists,
)
from .lib.commands import (
    CommandError,
    check_required_commands,
    run_agentcore_configure,
    run_agentcore_deploy,
    run_cdk_bootstrap,
    run_cdk_deploy,
)
from .lib.config import ConfigurationError, DeployConfig, get_deploy_config
from .lib.console import (
    console,
    print_config,
    print_error,
    print_final_success,
    print_header,
    print_next_steps,
    print_step,
    print_success,
    print_warning,
)
from .lib.yaml_parser import extract_execution_role_arn

app = typer.Typer(help="Deploy LangGraph agent to AWS Bedrock AgentCore")


def step_1_deploy_secrets(config: DeployConfig) -> None:
    """Deploy Secrets Manager secret via CDK."""
    print_step("1/6", "Deploying Secrets Manager secret (CDK)...")

    cdk_dir = Path("cdk")
    result = run_cdk_deploy(
        stack="SecretsStack",
        context={
            "secret_name": config.secret_name,
            "tavily_api_key": config.tavily_api_key,
        },
        cwd=cdk_dir,
        profile=config.aws_profile,
    )

    if not result.success:
        print_error("SecretsStack deployment failed")
        raise typer.Exit(1)

    # Verify stack exists
    session = get_session(config.aws_profile)
    if not stack_exists(session, "SecretsStack", config.aws_region):
        print_error("SecretsStack deployment failed")
        raise typer.Exit(1)

    print_success("Secret deployed via CDK")


def step_2_configure_agent(config: DeployConfig) -> None:
    """Configure agent for container deployment."""
    print_step("2/6", "Configuring agent...")

    result = run_agentcore_configure(
        entrypoint="langgraph_agent_web_search.py",
        agent_name=config.agent_name,
        region=config.aws_region,
        profile=config.aws_profile,
    )

    if not result.success:
        print_error("Agent configuration failed")
        if result.stderr:
            console.print(result.stderr)
        raise typer.Exit(1)

    print_success("Agent configured for container deployment")


def step_3_deploy_agent(config: DeployConfig) -> None:
    """Deploy agent to AgentCore."""
    print_step("3/6", "Deploying to AgentCore (this may take several minutes)...")

    result = run_agentcore_deploy(
        env_vars={
            "AWS_REGION": config.aws_region,
            "SECRET_NAME": config.secret_name,
            "MODEL_ID": config.model_id,
            "FALLBACK_MODEL_ID": config.fallback_model_id,
        },
        profile=config.aws_profile,
    )

    if not result.success:
        print_error("Agent deployment failed")
        raise typer.Exit(1)

    print_success("Deployment complete")


def step_4_extract_role_arn(config: DeployConfig) -> tuple[str, str]:
    """Extract execution role ARN and secret ARN."""
    print_step("4/6", "Extracting execution role ARN...")

    config_path = Path(".bedrock_agentcore.yaml")
    if not config_path.exists():
        print_error(".bedrock_agentcore.yaml not found after deployment")
        raise typer.Exit(1)

    role_arn = extract_execution_role_arn(config_path, config.agent_name)
    if not role_arn:
        print_error("Could not extract execution role ARN from .bedrock_agentcore.yaml")
        console.print(f"   Check that agent '{config.agent_name}' exists in the config file")
        raise typer.Exit(1)

    print_success(f"Found role: {role_arn}")

    # Get secret ARN from CDK outputs
    session = get_session(config.aws_profile)
    secret_arn = get_stack_output(session, "SecretsStack", "SecretArn", config.aws_region)

    if not secret_arn:
        print_error("Could not retrieve Secret ARN from CloudFormation outputs")
        raise typer.Exit(1)

    print_success(f"Found secret: {secret_arn}")

    return role_arn, secret_arn


def step_5_grant_permissions(
    config: DeployConfig, role_arn: str, secret_arn: str
) -> None:
    """Grant IAM permissions via CDK."""
    print_step("5/6", "Granting IAM permissions (CDK)...")

    cdk_dir = Path("cdk")
    result = run_cdk_deploy(
        stack="IamPolicyStack",
        context={
            "execution_role_arn": role_arn,
            "secret_arn": secret_arn,
        },
        cwd=cdk_dir,
        profile=config.aws_profile,
    )

    if not result.success:
        print_error("IamPolicyStack deployment failed")
        raise typer.Exit(1)

    # Verify stack exists
    session = get_session(config.aws_profile)
    if not stack_exists(session, "IamPolicyStack", config.aws_region):
        print_error("IamPolicyStack deployment failed")
        raise typer.Exit(1)

    print_success("IAM policy attached via CDK")


def step_6_restart_containers(config: DeployConfig) -> None:
    """Restart containers to pick up IAM permissions."""
    print_step("6/6", "Restarting containers to apply IAM permissions...")

    # Run agentcore deploy again - this triggers an update and restarts containers
    result = run_agentcore_deploy(
        env_vars={
            "AWS_REGION": config.aws_region,
            "SECRET_NAME": config.secret_name,
            "MODEL_ID": config.model_id,
            "FALLBACK_MODEL_ID": config.fallback_model_id,
        },
        profile=config.aws_profile,
    )

    if not result.success:
        print_warning("Container restart may have failed, but IAM permissions are in place")
        print_warning("Try invoking the agent - new containers will have correct permissions")
    else:
        print_success("Containers restarted with IAM permissions")


@app.command()
def deploy(
    profile: Annotated[
        str | None,
        typer.Option("--profile", help="AWS CLI profile name (for SSO users)"),
    ] = None,
) -> None:
    """
    Deploy the LangGraph agent to AWS Bedrock AgentCore.

    This command performs a 6-step deployment:

    1. Deploy Secrets Manager secret via CDK

    2. Configure agent for container deployment

    3. Deploy to AgentCore

    4. Extract execution role ARN

    5. Grant IAM permissions via CDK

    6. Restart containers to apply IAM permissions
    """
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
        print_header("LangGraph Agent Deployment")
        print_config(
            region=config.aws_region,
            agent_name=config.agent_name,
            model_id=config.model_id,
            secret_name=config.secret_name,
            profile=config.aws_profile,
        )

        # Execute deployment steps
        step_1_deploy_secrets(config)
        step_2_configure_agent(config)
        step_3_deploy_agent(config)
        role_arn, secret_arn = step_4_extract_role_arn(config)
        step_5_grant_permissions(config, role_arn, secret_arn)
        step_6_restart_containers(config)

        # Success message
        print_final_success("Deployment successful!")
        print_next_steps(config.aws_profile)

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
