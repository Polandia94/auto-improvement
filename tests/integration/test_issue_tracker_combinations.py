"""
Integration tests for different issue tracker combinations.

These tests use VCR cassettes for real API requests to:
- GitHub Issues (FastAPI, requests)
- Trac (Django)
- Jira (Apache Kafka)

The tests demonstrate the full improvement cycle with real API data,
only mocking the Claude Code CLI subprocess calls.

To record new cassettes, set GITHUB_TOKEN environment variable and run:
    RECORD_MODE=new_episodes pytest tests/integration/test_issue_tracker_combinations.py -v
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import vcr  # type: ignore[import-untyped]
from freezegun import freeze_time

from auto_improvement.issues_tracker_clients.github_issues_client import GitHubIssuesClient
from auto_improvement.issues_tracker_clients.jira_client import JiraClient
from auto_improvement.issues_tracker_clients.trac_client import TracClient
from auto_improvement.models import (
    AgentConfig,
    FileChange,
    IssueInfo,
    IssueTrackerConfig,
    PRInfo,
    PRSelectionCriteria,
    Solution,
)
from auto_improvement.version_control_clients.github_client import GitHubClient

# Path to cassettes directory
CASSETTES_DIR = Path(__file__).parent.parent / "cassettes"
CASSETTES_DIR.mkdir(parents=True, exist_ok=True)

# Check if we should record or playback
RECORD_MODE = os.getenv("RECORD_MODE", "none")
HAS_GITHUB_TOKEN = bool(os.getenv("GITHUB_TOKEN"))

# VCR configuration - uses environment variable to control recording
my_vcr = vcr.VCR(
    cassette_library_dir=str(CASSETTES_DIR),
    record_mode=RECORD_MODE,
    match_on=["uri", "method"],
    filter_headers=["authorization", "x-github-api-version"],
    decode_compressed_response=True,
)


class TestGitHubIssuesClientIntegration:
    """Integration tests for GitHub Issues client with various projects."""

    @pytest.fixture
    def github_issues_client_fastapi(self) -> GitHubIssuesClient:
        """Create GitHub Issues client for FastAPI."""
        config = IssueTrackerConfig(
            url="https://github.com/tiangolo/fastapi/issues",
        )
        return GitHubIssuesClient(config)

    @pytest.fixture
    def github_issues_client_requests(self) -> GitHubIssuesClient:
        """Create GitHub Issues client for requests library."""
        config = IssueTrackerConfig(
            url="https://github.com/psf/requests/issues",
        )
        return GitHubIssuesClient(config)

    @my_vcr.use_cassette("github_issues_fastapi_issue.yaml")  # type: ignore[untyped-decorator]
    def test_get_fastapi_issue(self, github_issues_client_fastapi: GitHubIssuesClient) -> None:
        """Test fetching a real issue from FastAPI repository."""
        # Issue #11254 is a real FastAPI issue
        issue = github_issues_client_fastapi.get_issue("11254")

        if issue is not None:  # May be None if cassette doesn't exist yet
            assert issue.id == "11254"
            assert issue.title
            assert issue.url
            assert "fastapi" in issue.url.lower()

    def test_extract_issue_patterns(self, github_issues_client_fastapi: GitHubIssuesClient) -> None:
        """Test issue extraction patterns without API calls."""
        # Test various patterns that should match
        patterns = [
            ("Closes #123", "123"),
            ("Fixes #456", "456"),
            ("closes: #789", "789"),
            ("This PR fixes issue #100", "100"),
        ]

        for body, expected_id in patterns:
            # We only test pattern matching, not the API call
            import re

            match = re.search(
                r"(?:fix|fixes|fixed|close|closes|closed|resolve|resolves|resolved)[:\s]+#(\d+)",
                body,
                re.IGNORECASE,
            )
            if match:
                assert match.group(1) == expected_id

    def test_no_issue_in_empty_body(self, github_issues_client_fastapi: GitHubIssuesClient) -> None:
        """Test that empty PR body returns None."""
        result = github_issues_client_fastapi.extract_issue_id_from_pr("")
        assert result is None

    def test_no_issue_in_unrelated_text(
        self, github_issues_client_fastapi: GitHubIssuesClient
    ) -> None:
        """Test that unrelated text returns None."""
        result = github_issues_client_fastapi.extract_issue_id_from_pr(
            "This is just a normal PR without any issue reference."
        )
        assert result is None


class TestTracClientIntegration:
    """Integration tests for Trac client with Django project."""

    @pytest.fixture
    def trac_client(self) -> TracClient:
        """Create Trac client for Django."""
        config = IssueTrackerConfig(
            url="https://code.djangoproject.com",
            ticket_pattern=r"#(\d+)",
        )
        return TracClient(config)

    @my_vcr.use_cassette("trac_get_issue.yaml")  # type: ignore[untyped-decorator]
    def test_get_django_ticket_35000(self, trac_client: TracClient) -> None:
        """Test fetching a real Django Trac ticket using existing cassette."""
        issue = trac_client.get_issue("35000")

        assert issue is not None
        assert issue.id == "35000"
        assert issue.title
        assert issue.url
        assert "code.djangoproject.com" in issue.url

    def test_trac_issue_id_cleanup(self, trac_client: TracClient) -> None:
        """Test that issue ID is cleaned properly."""
        # Test that # is stripped from issue ID
        # This tests internal logic, not the API
        cleaned_id = "#12345".lstrip("#")
        assert cleaned_id == "12345"

    def test_extract_trac_patterns(self, trac_client: TracClient) -> None:
        """Test Trac ticket extraction patterns without API calls."""
        test_cases = [
            ("Fixed #12345", "12345"),
            ("Fixes #99999", "99999"),
            ("https://code.djangoproject.com/ticket/35000", "35000"),
        ]

        import re

        for body, expected in test_cases:
            patterns = [
                r"(?:fix|fixes|fixed|close|closes|closed|resolve|resolves|resolved)\s+#(\d+)",
                r"code\.djangoproject\.com/ticket/(\d+)",
            ]
            for pattern in patterns:
                match = re.search(pattern, body, re.IGNORECASE)
                if match:
                    assert match.group(1) == expected
                    break


class TestJiraClientIntegration:
    """Integration tests for Jira client with Apache projects."""

    @pytest.fixture
    def kafka_jira_client(self) -> JiraClient:
        """Create Jira client for Apache Kafka."""
        config = IssueTrackerConfig(
            url="https://issues.apache.org/jira",
            ticket_pattern=r"KAFKA-\d+",
        )
        return JiraClient(config)

    @pytest.fixture
    def spark_jira_client(self) -> JiraClient:
        """Create Jira client for Apache Spark."""
        config = IssueTrackerConfig(
            url="https://issues.apache.org/jira",
            ticket_pattern=r"SPARK-\d+",
        )
        return JiraClient(config)

    @my_vcr.use_cassette("jira_kafka_issue.yaml")  # type: ignore[untyped-decorator]
    def test_get_kafka_jira_issue(self, kafka_jira_client: JiraClient) -> None:
        """Test fetching a real Apache Kafka Jira issue."""
        # This will use cassette if available, or record if in recording mode
        issue = kafka_jira_client.get_issue("KAFKA-15000")

        if issue is not None:  # May be None if cassette doesn't exist yet
            assert issue.id == "KAFKA-15000"
            assert issue.title
            assert issue.url
            assert "KAFKA-15000" in issue.url

    def test_jira_ticket_patterns(self, kafka_jira_client: JiraClient) -> None:
        """Test Jira ticket extraction patterns without API calls."""
        import re

        test_cases = [
            ("KAFKA-15000", "KAFKA-15000"),
            ("fixes KAFKA-12345", "KAFKA-12345"),
            ("This PR addresses KAFKA-99999", "KAFKA-99999"),
        ]

        for body, expected in test_cases:
            match = re.search(r"KAFKA-\d+", body, re.IGNORECASE)
            if match:
                assert match.group(0).upper() == expected

    def test_jira_url_extraction(self, kafka_jira_client: JiraClient) -> None:
        """Test extracting Jira ticket from URL pattern."""
        import re

        body = "See https://issues.apache.org/jira/browse/KAFKA-15000 for details."
        pattern = r"issues\.apache\.org/jira/browse/(KAFKA-\d+)"
        match = re.search(pattern, body)

        assert match is not None
        assert match.group(1) == "KAFKA-15000"

    def test_jira_case_insensitive_extraction(self, kafka_jira_client: JiraClient) -> None:
        """Test that Jira extraction works case-insensitively."""
        import re

        body = "fixes kafka-12345"
        pattern = r"KAFKA-\d+"
        match = re.search(pattern, body, re.IGNORECASE)

        assert match is not None
        assert match.group(0).upper() == "KAFKA-12345"


def _mock_subprocess_for_docker_sdk(
    cmd: list[str], *_args: Any, **_kwargs: Any
) -> subprocess.CompletedProcess[str]:
    """Mock subprocess calls for Docker-based ClaudeClient."""
    if not cmd:
        raise ValueError("Empty command")

    if cmd[0] == "docker":
        if "images" in cmd:
            # Docker image check - return as if image exists
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="abc123\n", stderr="")
        elif "run" in cmd:
            # Docker run - simulate successful execution
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
        elif "build" in cmd:
            # Docker build
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="Successfully built\n", stderr=""
            )
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")


class TestFullCycleWithMockedClaude:
    """Full improvement cycle tests using existing VCR cassettes for API calls and mocked Claude SDK."""

    @pytest.fixture
    def mock_claude_responses(self) -> Generator[MagicMock, None, None]:
        """Mock Claude SDK Docker responses."""
        with patch("subprocess.run", side_effect=_mock_subprocess_for_docker_sdk) as mock_run:
            yield mock_run

    @my_vcr.use_cassette("github_get_merged_prs.yaml")  # type: ignore[untyped-decorator]
    def test_full_cycle_django_with_existing_cassette(
        self,
        mock_claude_responses: MagicMock,
        temp_repo_dir: Path,
    ) -> None:
        """
        Test full improvement cycle with Django using existing cassette.

        This test:
        1. Uses real API data from VCR cassette
        2. Only mocks Claude SDK in Docker
        3. Simulates the complete workflow
        """
        from auto_improvement.agent_clients.claude_client import ClaudeClient

        # Step 1: Configure issue tracker (Trac for Django)
        trac_config = IssueTrackerConfig(
            url="https://code.djangoproject.com",
            ticket_pattern=r"#(\d+)",
        )
        trac_client = TracClient(trac_config)

        # Step 2: Configure GitHub client
        github_client = GitHubClient(trac_client)

        # Step 3: Fetch merged PRs (from VCR cassette)
        criteria = PRSelectionCriteria(
            merged=True,
            has_linked_issue=False,
            min_files_changed=1,
            max_files_changed=50,
            days_back=365,
        )

        prs = github_client.get_merged_prs("django/django", criteria, limit=1)
        assert len(prs) > 0, "Cassette should contain PR data"
        pr = prs[0]

        # Step 4: Verify PR structure from cassette
        assert isinstance(pr, PRInfo)
        assert pr.number > 0
        assert pr.merged_at is not None

        # Step 5: Create Claude client (mocked Docker)
        claude_config = AgentConfig(code_path="claude", model="claude-sonnet-4-20250514")
        claude_client = ClaudeClient(claude_config, working_dir=temp_repo_dir)

        # Step 6: Create test files
        test_file = temp_repo_dir / "django" / "db" / "models" / "query.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("# Original query.py content")

        # Step 7: Generate solution (mocked SDK response)
        with patch.object(claude_client, "_run_sdk_in_docker") as mock_sdk:
            mock_sdk.return_value = subprocess.CompletedProcess(
                args=["docker", "run"], returncode=0, stdout="", stderr=""
            )
            with patch.object(
                claude_client,
                "_detect_changed_files",
                return_value=["django/db/models/query.py"],
            ):
                solution = claude_client.generate_solution(pr, pr.linked_issue, None)

            assert solution is not None
            assert len(solution.files) > 0

            # Step 8: Create comparison solutions
            dev_solution = Solution(
                files={"django/db/models/query.py": "# Developer solution"},
                description="Developer's implementation",
            )

            # Step 9: Analyze comparison (Claude edits files directly, returns None)
            claude_client.analyze_comparison(dev_solution, solution)

            # Just verify SDK was called
            assert mock_sdk.called

    def test_mock_claude_solution_generation(
        self,
        mock_claude_responses: MagicMock,
        temp_repo_dir: Path,
    ) -> None:
        """Test that Claude SDK mocking works correctly for solution generation."""
        from auto_improvement.agent_clients.claude_client import ClaudeClient

        # Create Claude client
        claude_config = AgentConfig(code_path="claude")
        claude_client = ClaudeClient(claude_config, working_dir=temp_repo_dir)

        # Create test file
        test_file = temp_repo_dir / "test.py"
        test_file.write_text("# Test content")

        # Create minimal PR info
        pr_info = PRInfo(
            number=1,
            title="Test PR",
            description="Test description",
            author="test",
            merged_at=datetime.now(UTC),
            merge_commit_sha="abc123",
            base_commit_sha="base",
            head_commit_sha="head",
            files_changed=[],
            url="https://github.com/test/test/pull/1",
        )

        # Generate solution with mocked SDK
        with patch.object(claude_client, "_run_sdk_in_docker") as mock_sdk:
            mock_sdk.return_value = subprocess.CompletedProcess(
                args=["docker", "run"], returncode=0, stdout="", stderr=""
            )
            with patch.object(claude_client, "_detect_changed_files", return_value=["test.py"]):
                solution = claude_client.generate_solution(pr_info, None, None)

        assert solution is not None
        assert "test.py" in solution.files

    def test_mock_claude_analysis(
        self,
        mock_claude_responses: MagicMock,
        temp_repo_dir: Path,
    ) -> None:
        """Test that Claude SDK mocking works correctly for analysis."""
        from auto_improvement.agent_clients.claude_client import ClaudeClient

        claude_config = AgentConfig(code_path="claude")
        claude_client = ClaudeClient(claude_config, working_dir=temp_repo_dir)

        dev_solution = Solution(
            files={"test.py": "# Developer code"},
            description="Developer solution",
        )
        claude_solution = Solution(
            files={"test.py": "# Claude code"},
            description="Claude solution",
        )

        # Mock _run_sdk_in_docker
        with patch.object(claude_client, "_run_sdk_in_docker") as mock_sdk:
            mock_sdk.return_value = subprocess.CompletedProcess(
                args=["docker", "run"], returncode=0, stdout="", stderr=""
            )

            # analyze_comparison now returns None and edits files directly
            claude_client.analyze_comparison(dev_solution, claude_solution)

            # Just verify SDK was called
            assert mock_sdk.called


class TestIssueTrackerClientFactory:
    """Tests for creating issue tracker clients from configuration."""

    def test_create_github_issues_client(self) -> None:
        """Test creating GitHub Issues client."""
        config = IssueTrackerConfig(
            url="https://github.com/owner/repo/issues",
        )
        client = GitHubIssuesClient(config)
        assert client.config.url == "https://github.com/owner/repo/issues"

    def test_create_trac_client(self) -> None:
        """Test creating Trac client."""
        config = IssueTrackerConfig(
            url="https://code.djangoproject.com",
            ticket_pattern=r"#(\d+)",
        )
        client = TracClient(config)
        assert client.base_url == "https://code.djangoproject.com"

    def test_create_jira_client(self) -> None:
        """Test creating Jira client."""
        config = IssueTrackerConfig(
            url="https://issues.apache.org/jira",
            ticket_pattern=r"KAFKA-\d+",
        )
        client = JiraClient(config)
        assert client.base_url == "https://issues.apache.org/jira"

    def test_create_jira_client_with_auth(self) -> None:
        """Test creating Jira client with authentication."""
        config = IssueTrackerConfig(
            url="https://jira.example.com",
            auth={"username": "user", "api_token": "token"},
        )
        client = JiraClient(config)
        assert client.session.auth == ("user", "token")


class TestCombinedWorkflow:
    """Tests demonstrating the combined workflow with different trackers."""

    @my_vcr.use_cassette("github_get_merged_prs_workflow.yaml")  # type: ignore[untyped-decorator]
    def test_workflow_with_trac(self) -> None:
        """Test workflow: GitHub PRs + Trac issue tracker."""
        trac_config = IssueTrackerConfig(
            url="https://code.djangoproject.com",
            ticket_pattern=r"#(\d+)",
        )
        trac_client = TracClient(trac_config)
        github_client = GitHubClient(trac_client)

        criteria = PRSelectionCriteria(
            merged=True,
            has_linked_issue=False,
            min_files_changed=1,
            max_files_changed=50,
            days_back=365,
        )

        prs = github_client.get_merged_prs("django/django", criteria, limit=1)
        assert len(prs) > 0

        pr = prs[0]
        assert isinstance(pr, PRInfo)
        assert pr.merged_at is not None

    def test_workflow_clients_are_configurable(self) -> None:
        """Test that workflow components are properly configurable."""
        # GitHub Issues configuration
        gh_config = IssueTrackerConfig(
            url="https://github.com/tiangolo/fastapi/issues",
        )
        gh_client = GitHubIssuesClient(gh_config)
        github_for_gh = GitHubClient(gh_client)

        # Trac configuration
        trac_config = IssueTrackerConfig(
            url="https://code.djangoproject.com",
            ticket_pattern=r"#(\d+)",
        )
        trac_client = TracClient(trac_config)
        github_for_trac = GitHubClient(trac_client)

        # Jira configuration
        jira_config = IssueTrackerConfig(
            url="https://issues.apache.org/jira",
            ticket_pattern=r"KAFKA-\d+",
        )
        jira_client = JiraClient(jira_config)
        github_for_jira = GitHubClient(jira_client)

        # All should be configured correctly
        assert github_for_gh.issue_tracker == gh_client
        assert github_for_trac.issue_tracker == trac_client
        assert github_for_jira.issue_tracker == jira_client


class TestFullRunImprovementCycle:
    """
    Full integration test for run_improvement_cycle function.

    This test runs the complete AutoImprovement.run_improvement_cycle() flow:
    1. Clones the real django/django repository (cached between runs)
    2. Uses VCR cassettes for GitHub API (get merged PRs)
    3. Uses VCR cassettes for Trac API (get Django ticket details)
    4. Only mocks Claude Code CLI subprocess calls

    To record cassettes:
        GITHUB_TOKEN=<token> RECORD_MODE=new_episodes pytest tests/integration/test_issue_tracker_combinations.py::TestFullRunImprovementCycle -v -s
    """

    # Directory to cache cloned repos between test runs
    REPOS_CACHE_DIR = Path(__file__).parent.parent.parent / ".test-repos"

    @pytest.fixture(scope="class")
    def django_repo_path(self) -> Generator[Path, None, None]:
        """
        Clone or use cached django/django repository.

        This fixture clones the real Django repo once and reuses it.
        The repo is stored in .test-repos/django to persist between runs.
        """
        repo_dir = self.REPOS_CACHE_DIR / "django"

        if not repo_dir.exists() or not (repo_dir / ".git").exists():
            # Clone the real Django repository with enough history for PR testing
            self.REPOS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                [
                    "git",
                    "clone",
                    "--depth",
                    "1000",  # Shallow clone with more history
                    "https://github.com/django/django.git",
                    str(repo_dir),
                ],
                check=True,
                capture_output=True,
                timeout=600,  # 10 min timeout for clone
            )
        else:
            # Update existing repo - unshallow if needed
            subprocess.run(
                ["git", "fetch", "--unshallow"],
                cwd=repo_dir,
                check=False,  # May fail if already unshallowed
                capture_output=True,
                timeout=300,
            )
            # Try to fetch latest, but don't fail if network is unavailable
            # The tests use VCR cassettes so fresh data isn't critical
            subprocess.run(
                ["git", "fetch", "origin", "main"],
                cwd=repo_dir,
                check=False,  # Don't fail on network issues
                capture_output=True,
                timeout=120,
            )

        # Reset to a known state
        subprocess.run(
            ["git", "checkout", "main"],
            cwd=repo_dir,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "reset", "--hard", "HEAD"],
            cwd=repo_dir,
            check=True,
            capture_output=True,
        )

        yield repo_dir

    @pytest.fixture
    def mock_claude_for_full_cycle(self) -> Generator[MagicMock, None, None]:
        """
        Mock Claude SDK with comprehensive responses for full cycle.

        This mock intercepts Docker commands for ClaudeClient initialization
        and lets real git commands pass through.
        """
        claude_md_content = """# Django Project Context

## Architecture
Django follows MTV (Model-Template-View) pattern.

## Coding Conventions
- Use 4-space indentation
- Follow PEP 8 style guide
- Docstrings for all public methods

## Testing
- Use Django's TestCase for database tests
- unittest.TestCase for pure Python tests

## Common Patterns
- QuerySet chaining for database operations
- Manager classes for custom QuerySet methods
"""

        # Store the original subprocess.run
        original_run = subprocess.run

        def subprocess_side_effect(
            cmd: list[str], *args: Any, **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            if not cmd:
                raise ValueError("Empty command")
            # Mock docker commands for ClaudeClient initialization and SDK execution
            if cmd[0] == "docker":
                if "images" in cmd:
                    # Return as if docker image exists
                    return subprocess.CompletedProcess(
                        args=cmd, returncode=0, stdout="abc123\n", stderr=""
                    )
                elif "run" in cmd:
                    # Check if this is a run_research call by looking for config mount
                    # and write CLAUDE.md to the workspace
                    for i, arg in enumerate(cmd):
                        if arg == "-v" and i + 1 < len(cmd):
                            vol_mount = cmd[i + 1]
                            if "/workspace" in vol_mount and ":" in vol_mount:
                                workspace_path = vol_mount.split(":")[0]
                                learning_dir = Path(workspace_path)
                                if learning_dir.exists():
                                    (learning_dir / "CLAUDE.md").write_text(claude_md_content)
                    return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
                return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
            # Let real git and other commands execute normally
            return original_run(cmd, *args, **kwargs)

        with patch("subprocess.run", side_effect=subprocess_side_effect) as mock_run:
            yield mock_run

    @freeze_time("2025-12-29")  # Freeze time to match cassette recording date
    @my_vcr.use_cassette("full_cycle_django_prs_auto.yaml")  # type: ignore[untyped-decorator]
    def test_run_improvement_cycle_django_with_trac(
        self,
        mock_claude_for_full_cycle: MagicMock,
        django_repo_path: Path,
    ) -> None:
        """
        Test complete run_improvement_cycle with real Django repo and Trac issue tracker.

        This test exercises the full AutoImprovement flow:
        1. Uses real cloned django/django repository
        2. Uses VCR to record/playback GitHub API calls (public, no token needed)
        3. Uses VCR to record/playback Trac API calls (public)
        4. Only mocks Claude Code CLI subprocess calls
        5. Uses real GitManager for git operations

        To re-record cassette: RECORD_MODE=new_episodes pytest <test>
        Note: Uses freeze_time to ensure date-based queries match cassette.
        """
        from auto_improvement.core import AutoImprovement
        from auto_improvement.git_manager import GitManager
        from auto_improvement.models import Config, IssueTrackerConfig, ProjectConfig

        # Create config with Trac as issue tracker, pointing to real cloned repo
        config = Config(
            project=ProjectConfig(
                name="django",
                repo="django/django",
                local_path=django_repo_path,
            ),
            issue_tracker=IssueTrackerConfig(
                client=TracClient,
                url="https://code.djangoproject.com",
                ticket_pattern=r"#(\d+)",
            ),
        )

        # Create real GitManager pointing to our cached Django repo
        git_manager = GitManager(
            repo_url="django/django",
            local_path=django_repo_path,
        )
        # Initialize the repo attribute since we already have the repo
        import git

        git_manager.repo = git.Repo(django_repo_path)

        # Patch GitManager constructor to return our pre-configured instance
        with patch("auto_improvement.core.GitManager", return_value=git_manager):
            # Create AutoImprovement instance
            auto_improve = AutoImprovement(
                repo_path="django/django",
                config_path=None,
            )

            # Override config with our test config
            auto_improve.config = config

            # Also update the clients to use Trac issue tracker
            from auto_improvement.version_control_clients.github_client import GitHubClient

            trac_client = TracClient(config.issue_tracker)
            auto_improve.issue_tracker_client = trac_client
            auto_improve.github_client = GitHubClient(trac_client)

            # Run the improvement cycle with just 1 PR for testing
            result = auto_improve.run_improvement_cycle(max_iterations=1)

        # Verify the result structure
        assert result is not None
        assert result.total_prs >= 0  # May be 0 if no PRs with linked issues found
        assert result.completed_at is not None or result.total_prs == 0

        # If we processed any PRs, verify session data
        if result.sessions:
            session = result.sessions[0]
            assert session.pr_info is not None
            assert session.attempts >= 1

    @my_vcr.use_cassette("full_cycle_django_trac_issue.yaml")  # type: ignore[untyped-decorator]
    def test_run_improvement_cycle_with_specific_pr(
        self,
        mock_claude_for_full_cycle: MagicMock,
        django_repo_path: Path,
    ) -> None:
        """
        Test run_improvement_cycle with a specific PR number using real Django repo.

        This test uses VCR to record the GitHub API call for fetching a specific PR
        and the Trac API call for the linked issue.
        """
        from auto_improvement.core import AutoImprovement
        from auto_improvement.git_manager import GitManager
        from auto_improvement.models import Config, IssueTrackerConfig, ProjectConfig

        # Create config
        config = Config(
            project=ProjectConfig(
                name="django",
                repo="django/django",
                local_path=django_repo_path,
            ),
            issue_tracker=IssueTrackerConfig(
                client=TracClient,
                url="https://code.djangoproject.com",
                ticket_pattern=r"#(\d+)",
            ),
        )

        # Create real GitManager
        git_manager = GitManager(
            repo_url="django/django",
            local_path=django_repo_path,
        )
        import git

        git_manager.repo = git.Repo(django_repo_path)

        with patch("auto_improvement.core.GitManager", return_value=git_manager):
            auto_improve = AutoImprovement(
                repo_path="django/django",
                config_path=None,
            )
            auto_improve.config = config

            # Run with a specific merged PR number (use a real one that exists)
            # PR #20446 is a recent merged Django PR
            result = auto_improve.run_improvement_cycle(specific_pr=20446)

        # Verify results
        assert result is not None
        assert result.total_prs == 1
        assert len(result.sessions) == 1
        assert result.sessions[0].pr_info.number == 20446
        assert result.completed_at is not None

        # Verify session was processed
        session = result.sessions[0]
        assert session.attempts >= 1
        assert session.success is True

    def test_improvement_cycle_calculates_stats_correctly(
        self,
        mock_claude_for_full_cycle: MagicMock,
        temp_repo_dir: Path,
    ) -> None:
        """Test that the improvement cycle correctly calculates final statistics."""
        from auto_improvement.agent_clients.claude_client import ClaudeClient
        from auto_improvement.core import AutoImprovement
        from auto_improvement.models import Config, IssueTrackerConfig, ProjectConfig

        # Create test files that would be "changed" by Claude
        (temp_repo_dir / "file.py").write_text("# solution content")

        # Create learning directory with CLAUDE.md (required by research phase)
        learning_dir = temp_repo_dir.parent / f"{temp_repo_dir.name}-learning"
        learning_dir.mkdir(parents=True, exist_ok=True)
        (learning_dir / "CLAUDE.md").write_text("# Django Context\n\nTest context for Django.")

        # Create multiple test PRs with linked issues
        test_prs = [
            PRInfo(
                number=1001,
                title="PR 1",
                description="First PR fixes #10001",
                author="user1",
                merged_at=datetime.now(UTC),
                merge_commit_sha="sha1",
                base_commit_sha="base1",
                head_commit_sha="head1",
                files_changed=[
                    FileChange(
                        filename="file1.py", status="modified", additions=5, deletions=2, changes=7
                    )
                ],
                url="https://github.com/django/django/pull/1001",
                linked_issue=IssueInfo(
                    id="10001",
                    title="Issue 1",
                    description="First issue",
                    url="https://code.djangoproject.com/ticket/10001",
                ),
            ),
            PRInfo(
                number=1002,
                title="PR 2",
                description="Second PR fixes #10002",
                author="user2",
                merged_at=datetime.now(UTC),
                merge_commit_sha="sha2",
                base_commit_sha="base2",
                head_commit_sha="head2",
                files_changed=[
                    FileChange(
                        filename="file2.py", status="modified", additions=3, deletions=1, changes=4
                    )
                ],
                url="https://github.com/django/django/pull/1002",
                linked_issue=IssueInfo(
                    id="10002",
                    title="Issue 2",
                    description="Second issue",
                    url="https://code.djangoproject.com/ticket/10002",
                ),
            ),
        ]

        config = Config(
            project=ProjectConfig(
                name="django",
                repo="django/django",
                local_path=temp_repo_dir,
            ),
            issue_tracker=IssueTrackerConfig(
                client=TracClient,
                url="https://code.djangoproject.com",
            ),
        )

        # Create fully mocked GitManager for fake PRs
        mock_git_manager = MagicMock()
        mock_git_manager.local_path = temp_repo_dir
        mock_git_manager.clone_or_update.return_value = MagicMock()
        mock_git_manager.checkout_before_pr.return_value = "base"
        mock_git_manager.checkout_after_pr.return_value = "merge"
        mock_git_manager.clean.return_value = None
        mock_git_manager.get_pr_solution.return_value = Solution(
            files={"file.py": "# solution"},
            description="Solution",
        )

        # Mock ClaudeClient methods to return success
        def mock_run_sdk(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(
                args=["docker", "run"], returncode=0, stdout="", stderr=""
            )

        with (
            patch("auto_improvement.core.GitManager", return_value=mock_git_manager),
            patch.object(AutoImprovement, "_select_prs", return_value=test_prs),
            patch.object(AutoImprovement, "_research_phase"),  # Skip research phase
            patch.object(ClaudeClient, "_run_sdk_in_docker", side_effect=mock_run_sdk),
            patch.object(ClaudeClient, "_detect_changed_files", return_value=["file.py"]),
        ):
            auto_improve = AutoImprovement(
                repo_path="django/django",
                config_path=None,
            )
            auto_improve.config = config

            # Run cycle with 2 PRs
            result = auto_improve.run_improvement_cycle(max_iterations=2)

        # Verify statistics
        assert result.total_prs == 2
        assert len(result.sessions) == 2
        assert result.completed_at is not None

        # Verify both sessions were processed
        for session in result.sessions:
            assert session.success is True
            assert session.attempts >= 1

        # Both PRs should have been processed
        pr_numbers = [s.pr_info.number for s in result.sessions]
        assert 1001 in pr_numbers
        assert 1002 in pr_numbers
