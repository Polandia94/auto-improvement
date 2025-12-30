"""Core auto-improvement orchestrator."""

import json
import random
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from auto_improvement.analyzer import UnifiedAnalyzer
from auto_improvement.git_manager import GitManager
from auto_improvement.models import (
    Config,
    ImprovementRun,
    ImprovementSession,
    IssueInfo,
    PRInfo,
    Solution,
)


def load_config(config_path: Path | None = None) -> Config:
    """Load configuration from YAML file or use defaults."""
    if config_path and config_path.exists():
        with open(config_path) as f:
            config_data = yaml.safe_load(f)
        return Config(**config_data)
    return Config()


class AutoImprovement:
    """Main orchestrator for the auto-improvement system."""

    def __init__(
        self,
        repo_path: str,
        config_path: Path | None = None,
        agent_config_path: Path | None = None,
    ):
        """
        Initialize the auto-improvement system.

        Args:
            repo_path: GitHub repo in format "owner/repo"
            config_path: Path to configuration YAML file
            agent_config_path: Path to agent config file (e.g., CLAUDE.md)

        """
        self.console = Console()

        # Load configuration
        self.config = load_config(config_path)
        self.config.project.repo = repo_path

        # Set up paths
        self.agent_md_path = agent_config_path
        self.repo_path = repo_path

        # Initialize clients - the validators ensure these are never None after config load
        issue_tracker_client_class = self.config.issue_tracker.client
        if issue_tracker_client_class is None:
            raise ValueError("Issue tracker client not configured")
        self.issue_tracker_client = issue_tracker_client_class(self.config.issue_tracker)

        version_control_client_class = self.config.version_control_config.client
        if version_control_client_class is None:
            raise ValueError("Version control client not configured")
        self.github_client = version_control_client_class(self.issue_tracker_client)

        self.git_manager = GitManager(
            repo_url=repo_path,
            local_path=self.config.project.local_path,
        )

        # Learning directory is a sibling to the repo, not inside it
        # e.g., .auto-improve-repos/django -> .auto-improve-repos/django-learning
        self.learning_dir = self.git_manager.local_path.parent / (
            self.git_manager.local_path.name + "-learning"
        )
        self.learning_dir.mkdir(parents=True, exist_ok=True)

        agent_client_class = self.config.agent_config.client
        if agent_client_class is None:
            raise ValueError("Agent client not configured")
        self.agent_client = agent_client_class(
            config=self.config.agent_config,
            working_dir=self.git_manager.local_path,
        )

        # Initialize unified analyzer with learning directory separate from repo
        analysis_prompt = self.config.prompts.analysis
        self.analyzer = UnifiedAnalyzer(
            agent_client=self.agent_client,
            local_path=self.learning_dir,
            analysis_prompt=analysis_prompt,
        )

        # State
        self.current_run: ImprovementRun | None = None

        # Tracking file for analyzed PRs (in learning dir, not repo)
        self.analyzed_prs_file = self.learning_dir / ".analyzed_prs.json"

    def run_improvement_cycle(
        self,
        max_iterations: int | None = None,
        specific_pr: int | None = None,
    ) -> ImprovementRun:
        """
        Run a complete improvement cycle.

        Args:
            max_iterations: Maximum number of PRs to process (default: from config)
            specific_pr: Process a specific PR number instead of auto-selecting

        Returns:
            ImprovementRun with results

        """
        max_iterations = max_iterations or self.config.learning.max_prs_per_session

        # Initialize run
        self.current_run = ImprovementRun()

        self.console.print("\n[bold cyan]🚀 Starting Auto-Improvement Cycle[/bold cyan]\n")

        # Step 1: Clone/update repository
        self._setup_repository()

        # Step 2: Research
        self._research_phase()

        # Step 3: Select PRs
        if specific_pr:
            prs = [self.github_client.get_pr(self.repo_path, specific_pr)]
        else:
            prs = self._select_prs(max_iterations)

        self.console.print(f"\n[bold]Selected {len(prs)} PRs for learning[/bold]\n")

        # Step 4: Process each PR
        for pr in prs:
            session = self._process_pr(pr)
            self.current_run.sessions.append(session)

            # Update stats
            self.current_run.total_prs += 1
            if session.success:
                self.current_run.successful_prs += 1

        # Step 5: Calculate final stats
        self._finalize_run()

        return self.current_run

    def _research_phase(self) -> None:
        """Initial research phase using Agent to analyze the project."""
        # Check if agent md already exists
        if self.analyzer.agent_md_path.exists():
            self.console.print(
                f"[cyan]ℹ[/cyan] Found existing {self.analyzer.agent_md_path.name}, "
                "skipping research phase\n"
            )
            return

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console,
        ) as progress:
            task = progress.add_task(
                f"🔍 Researching project with {self.agent_client.agent_name}...", total=None
            )

            repo_info = self._fetch_repo_info()

            progress.update(task, description="🧠 Building research prompt...")

            # Build research prompt
            research_prompt = self._build_research_prompt(repo_info, self.analyzer.agent_md_path)

            progress.update(task, description="🤖 Performing research with AI agent...")
            # Use CAgentlaude to analyze and create initial file
            self._perform_research(research_prompt)

            progress.update(task, completed=True)

        self.console.print(
            f"[green]✓[/green] Research completed and {self.agent_client.agent_file} created\n"
        )

    def _fetch_repo_info(self) -> dict[str, Any]:
        """Fetch repository information."""
        try:
            # Check if the client has get_repo_info method (GitHubClient does)
            if hasattr(self.github_client, "get_repo_info"):
                info: dict[str, Any] = self.github_client.get_repo_info(self.repo_path)
                return info
            return {}
        except Exception as e:
            self.console.print(f"[yellow]⚠[/yellow] Could not fetch repo info: {e}")
            return {}

    def _build_research_prompt(self, repo_info: dict[str, Any], agent_md_path: Path) -> str:
        """Build the research prompt."""
        repo_name = repo_info.get("name", self.repo_path)
        description = repo_info.get("description", "No description available")
        language = repo_info.get("language", "Unknown")

        prompt = f"""You are researching the {repo_name} project to create initial context documentation.

# Repository Information
- **Name**: {repo_name}
- **Description**: {description}
- **Primary Language**: {language}
- **URL**: https://github.com/{self.repo_path}

# README Content

# Your Task

Based on the above information, please:

1. **Research the project** to understand:
   - What problem this project solves
   - Key architectural patterns and design decisions
   - Common use cases and best practices
   - Community conventions and standards

2. **Analyze the provided files** to understand:
   - Project structure and organization
   - Technology stack and dependencies
   - Coding patterns and conventions
   - Testing approaches

3. **Create a comprehensive {self.agent_client.agent_file} file on '{agent_md_path}' that includes:
```

Please provide the complete {self.agent_client.agent_name} content that will help me (an AI assistant) understand this project better for future PR implementations.
"""

        return prompt

    def _perform_research(self, prompt: str) -> None:
        """Use Agent SDK to perform research and create initial file."""
        # Access config dynamically
        agent_client = self.agent_client
        if not agent_client:
            raise RuntimeError("Agent client not properly configured")

        self.console.print("\n[bold cyan]Starting Claude research session...[/bold cyan]")
        self.console.print(
            "[dim]Claude SDK is running in Docker with auto-approval enabled.[/dim]\n"
        )

        # Use the agent client's run_research method which uses the SDK in Docker
        agent_client.run_research(prompt, self.learning_dir)

        # After interactive session, verify the CLAUDE.md file was created
        if not self.analyzer.agent_md_path.exists():
            raise RuntimeError(
                f"Claude did not create {self.agent_client.agent_file}. "
                "Please ensure Claude generated the learning context during the research session."
            )

    def _extract_claude_md_from_response(self, response: str) -> str:
        """Extract CLAUDE.md content from Claude's response."""
        import re

        # Try to find markdown code block
        pattern = r"```markdown\n(.*?)```"
        match = re.search(pattern, response, re.DOTALL)

        if match:
            return match.group(1).strip()

        # Try to find content between # Project Context markers
        pattern = r"(# Project Context.*)"
        match = re.search(pattern, response, re.DOTALL)

        if match:
            return match.group(1).strip()

        # If no structured content found, return the whole response
        return response.strip()

    def _setup_repository(self) -> None:
        """Clone or update repository."""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console,
        ) as progress:
            task = progress.add_task("📦 Setting up repository...", total=None)

            self.git_manager.clone_or_update()
            self.analyzer._initialize_files()

            progress.update(task, completed=True)

        self.console.print("[green]✓[/green] Repository ready\n")

    def _select_prs(self, limit: int) -> list[PRInfo]:
        """Select PRs for learning."""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console,
        ) as progress:
            task = progress.add_task("🎯 Finding suitable PRs...", total=None)

            # Load already analyzed PRs to skip them
            analyzed_prs = self._load_analyzed_prs()
            if analyzed_prs:
                self.console.print(f"[dim]Skipping {len(analyzed_prs)} already analyzed PRs[/dim]")

            # Fetch more PRs than needed to account for skipping analyzed ones
            enriched_prs = self.search_prs(limit, analyzed_prs)

            # Shuffle and take limit
            random.shuffle(enriched_prs)
            selected = enriched_prs[:limit]

            progress.update(task, completed=True)

        return selected

    def search_prs(self, limit: int, analyzed_prs: set[int], offset: int = 0) -> list[PRInfo]:
        fetch_limit = limit + len(analyzed_prs) + 10 + offset
        prs = self.github_client.get_merged_prs(
            self.repo_path,
            self.config.pr_selection,
            limit=fetch_limit,
        )

        # Enrich with issue information, skipping already analyzed PRs
        enriched_prs = []
        for pr in prs:
            # Skip already analyzed PRs
            if pr.number in analyzed_prs:
                print(f"Skipping PR #{pr.number}: already analyzed")
                continue

            print(f"Processing PR #{pr.number}: {pr.title}")
            if pr.linked_issue:
                enriched_prs.append(pr)
            else:
                # Try to fetch from issue tracker
                print("  No linked issue, trying to extract from PR description...")
                print(self.issue_tracker_client)
                issue_info = self._extract_issue_id_from_pr(pr)
                if issue_info:
                    pr.linked_issue = issue_info
                    enriched_prs.append(pr)
        return enriched_prs

    def _extract_issue_id_from_pr(self, pr: PRInfo) -> IssueInfo | None:
        """Extract issue ID from PR title and description and fetch issue info."""
        # Try description first, then title (Django often puts ticket refs in title)
        combined_text = f"{pr.title}\n{pr.description or ''}"
        return self.issue_tracker_client.extract_issue_id_from_pr(combined_text)

    def _process_pr(self, pr: PRInfo) -> ImprovementSession:
        """Process a single PR."""
        self.console.print(f"\n[bold blue]━━━ PR #{pr.number}: {pr.title} ━━━[/bold blue]")

        if pr.linked_issue:
            self.console.print(f"📋 Issue: {pr.linked_issue.title}")
            self.console.print(f"🔗 {pr.linked_issue.url}\n")

        session = ImprovementSession(
            pr_info=pr,
            attempts=0,
            success=False,
            best_score=0.0,
        )

        # Try multiple attempts
        for attempt in range(1, self.config.learning.max_attempts_per_pr + 1):
            self.console.print(
                f"\n[yellow]⚙️  Attempt {attempt}/{self.config.learning.max_attempts_per_pr}[/yellow]"
            )

            session.attempts = attempt

            # Time travel to before PR
            self._time_travel_before_pr(pr)

            # Generate solution
            claude_solution = self._generate_solution(pr)
            session.claude_solution = claude_solution

            # Get developer solution
            developer_solution = self.git_manager.get_pr_solution(pr)
            session.developer_solution = developer_solution

            # Unified analysis: compare solutions and update all learning files
            # Claude runs interactively and edits learning files directly
            self._analyze_and_learn(developer_solution, claude_solution, pr)

            session.success = True
            self.console.print("[bold green]✅ Analysis complete![/bold green]")

            # Save PR as analyzed so it won't be processed again
            self._save_analyzed_pr(pr.number)
            break

        return session

    def _time_travel_before_pr(self, pr: PRInfo) -> None:
        """Checkout code before PR."""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console,
        ) as progress:
            task = progress.add_task("⏮️  Time traveling to before PR...", total=None)

            self.git_manager.checkout_before_pr(pr)
            self.git_manager.clean()  # Clean working directory

            progress.update(task, completed=True)

    def _generate_solution(self, pr: PRInfo) -> Solution:
        """Generate solution using Claude."""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console,
        ) as progress:
            task = progress.add_task("🤖 Generating solution with Claude...", total=None)

            # Generate solution
            solution = self.agent_client.generate_solution(
                pr, pr.linked_issue, self.analyzer.agent_md_path
            )

            progress.update(task, completed=True)

        return solution

    def _analyze_and_learn(
        self,
        developer_solution: Solution,
        claude_solution: Solution,
        pr: PRInfo,
    ) -> None:
        """Analyze solutions and update all learning files (unified approach)."""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console,
        ) as progress:
            task = progress.add_task(
                "🔄 Analyzing solutions and updating learning files...", total=None
            )

            # Claude runs interactively and edits learning files directly
            self.analyzer.analyze_and_learn(developer_solution, claude_solution, pr)

            progress.update(task, completed=True)

    def _finalize_run(self) -> None:
        """Finalize the improvement run."""
        if not self.current_run:
            return

        self.current_run.completed_at = datetime.now(UTC)

        # Calculate average score
        if self.current_run.sessions:
            total_score = sum(s.best_score for s in self.current_run.sessions)
            self.current_run.average_score = total_score / len(self.current_run.sessions)

        # Count total insights across all sessions
        self.current_run.total_learnings = sum(
            len(s.key_insights) for s in self.current_run.sessions
        )

        # Print summary
        self.console.print("\n[bold cyan]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold cyan]")
        self.console.print("[bold]📊 Improvement Run Summary[/bold]\n")
        self.console.print(f"Total PRs processed: {self.current_run.total_prs}")
        self.console.print(f"Successful PRs: {self.current_run.successful_prs}")
        self.console.print(f"Average score: {self.current_run.average_score:.1%}")
        self.console.print(f"Total learnings: {self.current_run.total_learnings}")
        self.console.print(
            f"\n[green]✓ CLAUDE.md has been updated with {self.current_run.total_learnings} new learnings[/green]"
        )
        self.console.print("[bold cyan]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold cyan]\n")

    def _load_analyzed_prs(self) -> set[int]:
        """Load the set of already analyzed PR numbers."""
        if not self.analyzed_prs_file.exists():
            return set()

        try:
            data = json.loads(self.analyzed_prs_file.read_text())
            return set(data.get("analyzed_prs", []))
        except (json.JSONDecodeError, KeyError):
            return set()

    def _save_analyzed_pr(self, pr_number: int) -> None:
        """Save a PR number to the analyzed PRs tracking file."""
        analyzed = self._load_analyzed_prs()
        analyzed.add(pr_number)

        data: dict[str, list[int] | str] = {
            "analyzed_prs": sorted(analyzed),
            "last_updated": datetime.now(UTC).isoformat(),
        }
        self.analyzed_prs_file.write_text(json.dumps(data, indent=2))
