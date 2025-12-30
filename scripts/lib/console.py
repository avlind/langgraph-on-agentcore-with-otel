"""Colored console output utilities using Rich."""

from rich.console import Console

console = Console()


def print_step(step: str, message: str) -> None:
    """Print a step indicator: [1/5] Deploying..."""
    console.print(f"\n[blue][{step}][/blue] {message}")


def print_success(message: str) -> None:
    """Print success message with green checkmark."""
    console.print(f"   [green]✓[/green] {message}")


def print_warning(message: str) -> None:
    """Print warning message with yellow indicator."""
    console.print(f"   [yellow]![/yellow] {message}")


def print_error(message: str) -> None:
    """Print error message with red X."""
    console.print(f"   [red]✗[/red] {message}")


def print_header(title: str, emoji: str = "🚀") -> None:
    """Print deployment header."""
    console.print(f"[blue]{emoji} {title}[/blue]")
    console.print("=" * 30)


def print_config(
    region: str,
    agent_name: str,
    model_id: str | None = None,
    secret_name: str | None = None,
    profile: str | None = None,
    delete_secret: bool = False,
    delete_ecr: bool = False,
) -> None:
    """Print configuration summary."""
    console.print("[blue]📋 Configuration:[/blue]")
    console.print(f"   Region: {region}")
    console.print(f"   Agent:  {agent_name}")
    if model_id:
        console.print(f"   Model:  {model_id}")
    if secret_name:
        if delete_secret:
            console.print(f"   Secret: {secret_name} (will be deleted)")
        else:
            console.print(f"   Secret: {secret_name}")
    if delete_ecr:
        console.print(f"   ECR:    bedrock-agentcore-{agent_name} (will be deleted)")
    if profile:
        console.print(f"   Profile: {profile}")


def print_final_success(message: str = "Deployment successful!") -> None:
    """Print final success message."""
    console.print()
    console.print(f"[green]✅ {message}[/green]")


def print_next_steps(profile: str | None = None) -> None:
    """Print next steps after deployment."""
    console.print()
    console.print("Next steps:")
    prefix = f"AWS_PROFILE={profile} " if profile else ""
    console.print(f'   Test: {prefix}agentcore invoke \'{{"prompt": "Search for AWS news"}}\'')
    console.print(f"   Logs: {prefix}agentcore logs --follow")
    console.print(f"   Traces: {prefix}agentcore obs list")
