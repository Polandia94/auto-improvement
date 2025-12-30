"""
Integration tests for the auto-improvement cycle.

These tests use VCR cassettes for GitHub API requests and mock subprocess
calls for Claude Code CLI interactions.
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

from auto_improvement.agent_clients.claude_client import ClaudeClient
from auto_improvement.issues_tracker_clients.github_issues_client import GitHubIssuesClient
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

# Ensure cassettes directory exists
CASSETTES_DIR.mkdir(parents=True, exist_ok=True)

# Use RECORD_MODE env var: "none" for playback, "new_episodes" to record new cassettes
RECORD_MODE = os.getenv("RECORD_MODE", "none")

# VCR configuration
my_vcr = vcr.VCR(
    cassette_library_dir=str(CASSETTES_DIR),
    record_mode=RECORD_MODE,
    match_on=["uri", "method"],
    filter_headers=["authorization", "x-github-api-version"],
    decode_compressed_response=True,
)


class TestGitHubClientWithVCR:
    """Test GitHub client using VCR cassettes for HTTP mocking."""

    @pytest.fixture
    def github_client(self) -> GitHubClient:
        """Create GitHub client with mock issue tracker."""
        issue_tracker = GitHubIssuesClient(IssueTrackerConfig())
        return GitHubClient(issue_tracker)

    @my_vcr.use_cassette("github_get_merged_prs.yaml")  # type: ignore[untyped-decorator]
    def test_get_merged_prs(self, github_client: GitHubClient) -> None:
        """Test fetching merged PRs - gets real merged PRs from Django repo."""
        criteria = PRSelectionCriteria(
            merged=True,
            has_linked_issue=False,  # Don't require linked issue for flexibility
            min_files_changed=1,
            max_files_changed=50,
            days_back=365,  # Look back far enough to find PRs
        )

        prs = github_client.get_merged_prs("django/django", criteria, limit=3)

        # Verify we got some merged PRs
        assert len(prs) > 0, "Should find at least one merged PR"

        # Verify each PR has the expected structure
        for pr in prs:
            assert isinstance(pr, PRInfo)
            assert pr.number > 0
            assert pr.title
            assert pr.author
            assert pr.merged_at is not None
            assert pr.merge_commit_sha
            assert pr.url.startswith("https://github.com/")

    @my_vcr.use_cassette("github_get_repo_info.yaml")  # type: ignore[untyped-decorator]
    def test_get_repo_info(self, github_client: GitHubClient) -> None:
        """Test fetching repository info using VCR cassette."""
        info = github_client.get_repo_info("django/django")

        # Check structure, not specific values (values may change over time)
        assert info["name"] == "django"
        assert "language" in info
        assert "description" in info
        assert info["full_name"] == "django/django"

    @my_vcr.use_cassette("github_get_readme.yaml")  # type: ignore[untyped-decorator]
    def test_get_readme(self, github_client: GitHubClient) -> None:
        """Test fetching README using VCR cassette."""
        readme = github_client.get_readme("django/django")

        assert readme is not None
        assert len(readme) > 0
        # Django's README should mention Django
        assert "Django" in readme or "django" in readme.lower()


class TestTracClientWithVCR:
    """Test Trac client using VCR cassettes."""

    @pytest.fixture
    def trac_client(self) -> TracClient:
        """Create Trac client."""
        config = IssueTrackerConfig(
            url="https://code.djangoproject.com",
            ticket_pattern=r"#(\d+)",
        )
        return TracClient(config)

    @my_vcr.use_cassette("trac_get_issue.yaml")  # type: ignore[untyped-decorator]
    def test_get_issue(self, trac_client: TracClient) -> None:
        """Test fetching a real Trac issue using VCR cassette."""
        # Use a real Django ticket number - ticket #35000 is a real one
        issue = trac_client.get_issue("35000")

        assert issue is not None
        assert issue.id == "35000"
        assert issue.title  # Should have a title
        assert issue.url  # Should have URL


def _mock_subprocess_for_docker(
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


class TestClaudeClientMocked:
    """Test Claude client with mocked subprocess calls."""

    @pytest.fixture
    def claude_client(self, temp_repo_dir: Path) -> Generator[ClaudeClient, None, None]:
        """Create Claude client with mocked Docker calls."""
        with patch("subprocess.run", side_effect=_mock_subprocess_for_docker):
            config = AgentConfig(code_path="claude", model="claude-sonnet-4-20250514")
            client = ClaudeClient(config, working_dir=temp_repo_dir)
            yield client

    def test_verify_claude_code(self, temp_repo_dir: Path) -> None:
        """Test ClaudeClient initialization with Docker."""
        with patch("subprocess.run", side_effect=_mock_subprocess_for_docker) as mock_run:
            config = AgentConfig(code_path="claude")
            ClaudeClient(config, working_dir=temp_repo_dir)

            # Verify subprocess was called for Docker image check
            assert mock_run.call_count >= 1
            # Verify docker images was called
            docker_calls = [
                call
                for call in mock_run.call_args_list
                if "docker" in str(call) and "images" in str(call)
            ]
            assert len(docker_calls) >= 1

    def test_generate_solution(
        self,
        claude_client: ClaudeClient,
        sample_pr_info: PRInfo,
        sample_issue_info: IssueInfo,
        temp_repo_dir: Path,
    ) -> None:
        """Test solution generation with mocked Claude SDK."""
        # Create a test file that Claude would "modify"
        test_file = temp_repo_dir / "django" / "db" / "models"
        test_file.mkdir(parents=True)
        (test_file / "query.py").write_text("# Original content")

        with patch.object(claude_client, "_run_sdk_in_docker") as mock_sdk:
            mock_sdk.return_value = subprocess.CompletedProcess(
                args=["docker", "run"],
                returncode=0,
                stdout="",
                stderr="",
            )

            # Mock _detect_changed_files to return our test file
            with patch.object(
                claude_client, "_detect_changed_files", return_value=["django/db/models/query.py"]
            ):
                solution = claude_client.generate_solution(
                    sample_pr_info,
                    sample_issue_info,
                    None,
                )

                assert solution is not None
                assert "query.py" in str(solution.files) or solution.description


class TestFullIntegrationCycle:
    """Integration tests for the complete improvement cycle."""

    @pytest.fixture
    def mock_all_external_calls(
        self,
        temp_repo_dir: Path,
        sample_pr_info: PRInfo,
        sample_developer_solution: Solution,
    ) -> Generator[dict[str, MagicMock], None, None]:
        """Mock all external calls for full integration test."""
        mocks: dict[str, MagicMock] = {}

        with patch("subprocess.run", side_effect=_mock_subprocess_for_docker) as mock_subprocess:
            mocks["subprocess"] = mock_subprocess
            yield mocks

    def test_github_client_integration(
        self,
    ) -> None:
        """Test GitHub client can fetch and parse PR data correctly."""
        issue_tracker = GitHubIssuesClient(IssueTrackerConfig())
        client = GitHubClient(issue_tracker)

        with my_vcr.use_cassette("github_get_merged_prs_integration.yaml"):
            criteria = PRSelectionCriteria(
                merged=True,
                has_linked_issue=False,
                min_files_changed=1,
                max_files_changed=50,
                days_back=365,
            )

            prs = client.get_merged_prs("django/django", criteria, limit=1)

            # We should get at least one PR
            assert len(prs) > 0
            pr = prs[0]

            # Verify PR structure
            assert isinstance(pr, PRInfo)
            assert pr.number > 0
            assert pr.merged_at is not None

            # Verify file changes structure (if any)
            for file_change in pr.files_changed:
                assert isinstance(file_change, FileChange)
                assert file_change.filename
                assert file_change.status in ["added", "modified", "removed", "renamed"]

    def test_trac_integration_with_real_ticket(
        self,
    ) -> None:
        """Test Trac issue tracker integration with a real ticket."""
        trac_config = IssueTrackerConfig(
            url="https://code.djangoproject.com",
            ticket_pattern=r"#(\d+)",
        )
        trac_client = TracClient(trac_config)

        with my_vcr.use_cassette("trac_get_issue_integration.yaml"):
            # Use a real ticket - #35000 exists in Django Trac
            issue = trac_client.get_issue("35000")

            assert issue is not None
            assert issue.id == "35000"
            assert issue.title

    def test_solution_comparison(
        self,
        sample_developer_solution: Solution,
        sample_claude_solution: Solution,
    ) -> None:
        """Test that solutions can be compared correctly."""
        # Verify solutions have expected structure
        assert sample_developer_solution.files
        assert sample_claude_solution.files

        # Check file overlap
        dev_files = set(sample_developer_solution.files.keys())
        claude_files = set(sample_claude_solution.files.keys())

        # There should be at least one common file
        common_files = dev_files & claude_files
        assert len(common_files) >= 1, "Solutions should have at least one common file"

        # Verify content differences exist (for testing comparison logic)
        for filename in common_files:
            dev_content = sample_developer_solution.files[filename]
            claude_content = sample_claude_solution.files[filename]
            # Content should be different (Claude's solution is simpler in our fixture)
            assert dev_content != claude_content


class TestVCRRecordingMode:
    """
    Tests that demonstrate VCR recording capabilities.

    These tests can be used to record new cassettes by changing
    record_mode to 'new_episodes' or 'all'.
    """

    @pytest.fixture
    def recording_vcr(self) -> vcr.VCR:
        """Create VCR instance configured for recording."""
        return vcr.VCR(
            cassette_library_dir=str(CASSETTES_DIR),
            record_mode="new_episodes",  # Will record if cassette doesn't exist
            match_on=["uri", "method"],
            filter_headers=["authorization"],
        )

    def test_vcr_cassette_playback(self, recording_vcr: vcr.VCR) -> None:
        """Verify VCR cassette playback works correctly."""
        with recording_vcr.use_cassette("github_get_repo_info_recording.yaml"):
            issue_tracker = GitHubIssuesClient(IssueTrackerConfig())
            client = GitHubClient(issue_tracker)
            info = client.get_repo_info("django/django")

            assert info["name"] == "django"
            assert info["full_name"] == "django/django"


class TestClaudeCodeMocking:
    """Tests demonstrating different Claude Code mocking strategies."""

    def test_mock_successful_solution_generation(self, temp_repo_dir: Path) -> None:
        """Test mocking a successful solution generation."""
        with patch("subprocess.run", side_effect=_mock_subprocess_for_docker):
            config = AgentConfig(code_path="claude")
            client = ClaudeClient(config, working_dir=temp_repo_dir)

            # Create test files
            (temp_repo_dir / "test.py").write_text("# Test file")

            # Mock _run_sdk_in_docker for solution generation
            with patch.object(client, "_run_sdk_in_docker") as mock_sdk:
                mock_sdk.return_value = subprocess.CompletedProcess(
                    args=["docker", "run"],
                    returncode=0,
                    stdout="",
                    stderr="",
                )

                with patch.object(client, "_detect_changed_files", return_value=["test.py"]):
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

                    solution = client.generate_solution(pr_info, None, None)

                    assert solution is not None
                    assert "test.py" in solution.files

    def test_mock_failed_solution_generation(self, temp_repo_dir: Path) -> None:
        """Test handling of failed Claude SDK execution."""
        with patch("subprocess.run", side_effect=_mock_subprocess_for_docker):
            config = AgentConfig(code_path="claude")
            client = ClaudeClient(config, working_dir=temp_repo_dir)

            # Mock _run_sdk_in_docker to fail
            with patch.object(client, "_run_sdk_in_docker") as mock_sdk:
                mock_sdk.return_value = subprocess.CompletedProcess(
                    args=["docker", "run"],
                    returncode=1,
                    stdout="",
                    stderr="Error: SDK execution failed",
                )

                pr_info = PRInfo(
                    number=1,
                    title="Test PR",
                    description="Test",
                    author="test",
                    merged_at=datetime.now(UTC),
                    merge_commit_sha="abc",
                    base_commit_sha="base",
                    head_commit_sha="head",
                    files_changed=[],
                    url="https://github.com/test/test/pull/1",
                )

                with pytest.raises(RuntimeError, match="Claude SDK failed"):
                    client.generate_solution(pr_info, None, None)


class TestEndToEndWithMocks:
    """End-to-end tests using both VCR and subprocess mocks."""

    def test_fetch_pr_and_generate_solution(
        self,
        temp_repo_dir: Path,
    ) -> None:
        """Test fetching a PR and generating a solution end-to-end."""
        issue_tracker = GitHubIssuesClient(IssueTrackerConfig())
        github_client = GitHubClient(issue_tracker)

        # Fetch merged PRs using VCR
        with my_vcr.use_cassette("github_e2e_get_merged_prs.yaml"):
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
        assert pr.merged_at is not None

        # Generate solution with mocked SDK
        with patch("subprocess.run", side_effect=_mock_subprocess_for_docker):
            config = AgentConfig(code_path="claude")
            client = ClaudeClient(config, working_dir=temp_repo_dir)

            # Create expected files
            query_file = temp_repo_dir / "django" / "db" / "models" / "query.py"
            query_file.parent.mkdir(parents=True, exist_ok=True)
            query_file.write_text("# Modified query.py")

            with patch.object(client, "_run_sdk_in_docker") as mock_sdk:
                mock_sdk.return_value = subprocess.CompletedProcess(
                    args=["docker", "run"],
                    returncode=0,
                    stdout="",
                    stderr="",
                )

                with patch.object(
                    client, "_detect_changed_files", return_value=["django/db/models/query.py"]
                ):
                    solution = client.generate_solution(pr, pr.linked_issue, None)

                    assert solution is not None
                    assert len(solution.files) > 0

    def test_complete_analysis_flow(
        self,
        temp_repo_dir: Path,
        sample_developer_solution: Solution,
    ) -> None:
        """Test complete flow: fetch PR -> generate solution -> analyze."""
        issue_tracker = GitHubIssuesClient(IssueTrackerConfig())
        github_client = GitHubClient(issue_tracker)

        # Step 1: Fetch merged PRs with VCR
        with my_vcr.use_cassette("github_e2e_complete_flow.yaml"):
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

        # Step 2: Mock Claude SDK for solution generation and analysis
        with patch("subprocess.run", side_effect=_mock_subprocess_for_docker):
            config = AgentConfig(code_path="claude")
            client = ClaudeClient(config, working_dir=temp_repo_dir)

            # Create test file
            test_file = temp_repo_dir / "query.py"
            test_file.write_text("# Claude's solution")

            with patch.object(client, "_run_sdk_in_docker") as mock_sdk:
                mock_sdk.return_value = subprocess.CompletedProcess(
                    args=["docker", "run"],
                    returncode=0,
                    stdout="",
                    stderr="",
                )

                with patch.object(client, "_detect_changed_files", return_value=["query.py"]):
                    claude_solution = client.generate_solution(pr, pr.linked_issue, None)

                # Verify SDK was called and solution was generated
                assert mock_sdk.called
                assert claude_solution is not None
