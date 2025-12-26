"""Example usage of the auto-improvement system."""

from pathlib import Path

from auto_improvement import AutoImprovement


# Example 1: Basic usage with Django
def example_django_basic() -> None:
    """Run auto-improvement on Django with default settings."""
    improver = AutoImprovement(
        repo_path="django/django",
        config_path=Path("examples/django_config.yaml"),
    )

    results = improver.run_improvement_cycle(max_iterations=3)

    print(f"Processed {results.total_prs} PRs")
    print(f"Success rate: {results.successful_prs}/{results.total_prs}")
    print(f"Average score: {results.average_score:.1%}")
    print(f"Total learnings: {results.total_learnings}")


# Example 2: Process a specific Django PR
def example_specific_pr() -> None:
    """Process a specific PR."""
    improver = AutoImprovement(
        repo_path="django/django",
        config_path=Path("examples/django_config.yaml"),
    )

    # Process PR #18000 (or any other PR number)
    results = improver.run_improvement_cycle(specific_pr=18000)

    if results.sessions:
        session = results.sessions[0]
        print(f"PR #{session.pr_info.number}: {session.pr_info.title}")
        print(f"Score: {session.best_score:.1%}")
        print(f"Key insights: {len(session.key_insights)}")


# Example 3: Using API mode instead of Claude Code
def example_api_mode() -> None:
    """Run with Claude API instead of Claude Code CLI."""
    improver = AutoImprovement(
        repo_path="django/django",
        config_path=Path("examples/django_config.yaml"),
    )

    # Override to use API mode by setting the API key
    improver.config.agent_config.api_key = "your-api-key-here"  # Or set ANTHROPIC_API_KEY env var

    results = improver.run_improvement_cycle(max_iterations=2)
    print(f"Completed with {results.total_learnings} learnings")


# Example 4: Custom project configuration
def example_custom_project() -> None:
    """Run on a custom project."""
    from auto_improvement.issues_tracker_clients.github_issues_client import (
        GitHubIssuesClient,
    )
    from auto_improvement.models import (
        AgentConfig,
        Config,
        IssueTrackerConfig,
        ProjectConfig,
    )

    # Create custom config
    config = Config(
        project=ProjectConfig(
            name="My Project",
            repo="myorg/myproject",
        ),
        issue_tracker=IssueTrackerConfig(
            client=GitHubIssuesClient,
            url="https://github.com/myorg/myproject/issues",
        ),
        agent_config=AgentConfig(
            code_path="claude",
            model="claude-sonnet-4-20250514",
        ),
    )

    # Save config
    from auto_improvement.config import save_config

    config_path = Path("my-project-config.yaml")
    save_config(config, config_path)

    # Run improvement
    improver = AutoImprovement(
        repo_path="myorg/myproject",
        config_path=config_path,
    )

    improver.run_improvement_cycle(max_iterations=5)


if __name__ == "__main__":
    # Run examples
    print("Example 1: Django basic")
    # example_django_basic()

    print("\nExample 2: Specific PR")
    # example_specific_pr()

    print("\nExample 3: API mode")
    # example_api_mode()

    print("\nExample 4: Custom project")
    # example_custom_project()

    print("\nUncomment the example you want to run!")
