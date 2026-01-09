"""Invoke the deployed LangGraph agent via HTTP API."""

import json
from typing import Annotated

import typer

from .lib.aws import get_session
from .lib.config import ConfigurationError, get_deploy_config
from .lib.console import console, print_error, print_header

app = typer.Typer(help="Invoke the deployed LangGraph agent")


def get_runtime_arn(session, agent_name: str, region: str) -> str | None:
    """Get the runtime ARN for the agent."""
    client = session.client("bedrock-agentcore-control", region_name=region)

    try:
        response = client.list_agent_runtimes()
        for runtime in response.get("agentRuntimes", []):
            if runtime.get("agentRuntimeName") == agent_name:
                return runtime.get("agentRuntimeArn")
        return None
    except Exception as e:
        print_error(f"Failed to list runtimes: {e}")
        return None


def invoke_agent_http(
    session,
    runtime_arn: str,
    prompt: str,
    region: str,
) -> None:
    """Invoke the agent via HTTP API."""
    client = session.client("bedrock-agentcore", region_name=region)

    console.print("[dim]Invoking agent...[/dim]")

    try:
        # Prepare payload
        payload = json.dumps({"prompt": prompt}).encode("utf-8")

        # Invoke the agent runtime
        response = client.invoke_agent_runtime(
            agentRuntimeArn=runtime_arn,
            payload=payload,
        )

        console.print(f"[bold]Prompt:[/bold] {prompt}")
        console.print()
        console.print("[bold]Response:[/bold]")

        # Read the streaming response body
        streaming_body = response.get("response")
        if streaming_body:
            # Read the streaming body
            response_data = streaming_body.read()

            # Parse the response
            try:
                data = json.loads(response_data.decode("utf-8"))
                if "result" in data:
                    console.print(data["result"])
                elif "error" in data:
                    print_error(f"Agent error: {data['error']}")
                else:
                    console.print(response_data.decode("utf-8"))
            except json.JSONDecodeError:
                console.print(response_data.decode("utf-8"))
        else:
            print_error("No response body received")

    except Exception as e:
        print_error(f"Invocation error: {e}")
        raise typer.Exit(1)


@app.command()
def invoke(
    profile: Annotated[
        str | None,
        typer.Option("--profile", help="AWS CLI profile name (for SSO users)"),
    ] = None,
    prompt: Annotated[
        str,
        typer.Option("--prompt", "-p", help="Prompt to send to the agent"),
    ] = "What is the weather in Seattle?",
) -> None:
    """
    Invoke the deployed LangGraph agent with a prompt.

    Uses the HTTP API via boto3 SDK.
    """
    try:
        # Load configuration
        config = get_deploy_config(profile)

        print_header("Agent Invocation")
        console.print(f"   Agent: {config.agent_name}")
        console.print(f"   Region: {config.aws_region}")
        console.print()

        session = get_session(profile)

        # Get runtime ARN
        runtime_arn = get_runtime_arn(session, config.agent_name, config.aws_region)
        if not runtime_arn:
            print_error(f"Agent '{config.agent_name}' not found.")
            console.print()
            console.print("   Deploy the agent first:")
            console.print("      make deploy PROFILE=<profile>")
            raise typer.Exit(1)

        # Invoke via HTTP API
        invoke_agent_http(session, runtime_arn, prompt, config.aws_region)

    except ConfigurationError:
        raise typer.Exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Invocation cancelled.[/yellow]")
        raise typer.Exit(130)


def main() -> None:
    """Entry point for the invoke script."""
    app()


if __name__ == "__main__":
    main()
