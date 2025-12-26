"""CLI interface for auto-improvement system."""

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from auto_improvement.config import save_config
from auto_improvement.core import AutoImprovement
from auto_improvement.models import (
    AgentConfig,
    Config,
    IssueTrackerConfig,
    ProjectConfig,
)

app = typer.Typer(
    name="auto-improve",
    help="Auto-improvement system for AI coding assistants",
    add_completion=False,
)

console = Console()


@app.command()
def run(
    repo: Annotated[str, typer.Option("--repo", "-r", help="GitHub repository (owner/repo)")],
    config: Annotated[
        Path | None, typer.Option("--config", "-c", help="Configuration YAML file")
    ] = None,
    agent_md: Annotated[
        Path | None, typer.Option("--agent-md", help="Path to CLAUDE.md or similar file")
    ] = None,
    max_prs: Annotated[
        int | None, typer.Option("--max-prs", "-n", help="Maximum PRs to process")
    ] = None,
) -> None:
    """Run auto-improvement cycle on a repository."""
    try:
        # Create improver
        improver = AutoImprovement(
            repo_path=repo,
            config_path=config,
            agent_config_path=agent_md,
        )

        # Run improvement cycle
        result = improver.run_improvement_cycle(max_iterations=max_prs)

        # Success
        if result.successful_prs > 0:
            console.print("\n[bold green]✓ Completed successfully![/bold green]")
            console.print(f"Processed {result.total_prs} PRs, {result.successful_prs} successful")
        else:
            console.print("\n[yellow]⚠ Completed with issues[/yellow]")
            console.print(f"Processed {result.total_prs} PRs, but none reached success threshold")

    except Exception as e:
        console.print(f"[bold red]Error: {e}[/bold red]")
        raise typer.Exit(1) from e


@app.command()
def run_pr(
    repo: Annotated[str, typer.Option("--repo", "-r", help="GitHub repository (owner/repo)")],
    pr_number: Annotated[int, typer.Option("--pr", "-p", help="PR number to process")],
    config: Annotated[
        Path | None, typer.Option("--config", "-c", help="Configuration YAML file")
    ] = None,
    agent_md: Annotated[
        Path | None, typer.Option("--agent-md", help="Path to CLAUDE.md or similar file")
    ] = None,
) -> None:
    """Process a specific PR."""
    try:
        # Create improver
        improver = AutoImprovement(
            repo_path=repo,
            config_path=config,
            agent_config_path=agent_md,
        )

        # Run on specific PR
        result = improver.run_improvement_cycle(specific_pr=pr_number)

        # Print results
        if result.sessions:
            session = result.sessions[0]
            console.print(f"\n[bold]Results for PR #{pr_number}:[/bold]")
            console.print(f"Score: {session.best_score:.1%}")
            console.print(f"Attempts: {session.attempts}")
            console.print(f"Success: {'✓' if session.success else '✗'}")

    except Exception as e:
        console.print(f"[bold red]Error: {e}[/bold red]")
        raise typer.Exit(1) from e


@app.command()
def init(
    repo: Annotated[str, typer.Option("--repo", "-r", help="GitHub repository (owner/repo)")],
    output: Annotated[Path, typer.Option("--output", "-o", help="Output config file")] = Path(
        "auto-improve-config.yaml"
    ),
    project_name: Annotated[str, typer.Option("--name", "-n", help="Project name")] = "",
    issue_tracker: Annotated[
        str, typer.Option("--tracker", "-t", help="Issue tracker: github, trac, jira")
    ] = "github",
    tracker_url: Annotated[
        str | None, typer.Option("--tracker-url", help="Issue tracker URL")
    ] = None,
) -> None:
    """Initialize a configuration file."""
    try:
        # Use repo name as project name if not provided
        if not project_name:
            project_name = repo.split("/")[-1].title()

        # Create default config
        if issue_tracker == "github":
            from auto_improvement.issues_tracker_clients.github_issues_client import (
                GitHubIssuesClient,
            )

            tracker_config = IssueTrackerConfig(
                client=GitHubIssuesClient,
                url=tracker_url or f"https://github.com/{repo}/issues",
            )
        elif issue_tracker == "trac":
            from auto_improvement.issues_tracker_clients.trac_client import TracClient

            if not tracker_url:
                console.print("[red]Error: --tracker-url required for Trac[/red]")
                raise typer.Exit(1) from None
            tracker_config = IssueTrackerConfig(
                client=TracClient,
                url=tracker_url,
            )
        elif issue_tracker == "jira":
            from auto_improvement.issues_tracker_clients.trac_client import TracClient

            if not tracker_url:
                console.print("[red]Error: --tracker-url required for Jira[/red]")
                raise typer.Exit(1) from None
            tracker_config = IssueTrackerConfig(
                client=TracClient,
                url=tracker_url,
            )
        else:
            console.print(f"[red]Error: Unknown tracker type: {issue_tracker}[/red]")
            raise typer.Exit(1) from None

        project_config = ProjectConfig(
            name=project_name,
            repo=repo,
        )

        agent_config = AgentConfig()

        config = Config(
            project=project_config,
            agent_config=agent_config,
            issue_tracker=tracker_config,
        )

        # Save config
        save_config(config, output)

        console.print(f"[green]✓ Configuration saved to {output}[/green]")
        console.print("\nEdit the file to customize prompts and criteria.")
        console.print(f"\nRun with: auto-improve run --repo {repo} --config {output}")

    except Exception as e:
        console.print(f"[bold red]Error: {e}[/bold red]")
        raise typer.Exit(1) from e


@app.command()
def version() -> None:
    """Show version information."""
    from auto_improvement import __version__

    console.print(f"auto-improvement version {__version__}")


if __name__ == "__main__":
    app()
