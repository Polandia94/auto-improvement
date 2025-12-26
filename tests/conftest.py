"""Shared test fixtures for auto-improvement tests."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from auto_improvement.models import (
    AgentConfig,
    Config,
    FileChange,
    IssueInfo,
    IssueTrackerConfig,
    LearningConfig,
    PRInfo,
    ProjectConfig,
    PromptsConfig,
    PRSelectionCriteria,
    Solution,
    VersionControlConfig,
)


# VCR configuration for recording/replaying HTTP requests
@pytest.fixture(scope="module")
def vcr_config() -> dict[str, Any]:
    """VCR configuration for recording HTTP requests."""
    return {
        "cassette_library_dir": str(Path(__file__).parent / "cassettes"),
        "record_mode": "none",  # Use 'new_episodes' to record new requests
        "match_on": ["uri", "method"],
        "filter_headers": ["authorization", "x-github-api-version"],
        "decode_compressed_response": True,
    }


@pytest.fixture
def vcr_cassette_dir() -> str:
    """Return the cassette directory."""
    return str(Path(__file__).parent / "cassettes")


# Sample PR data fixtures
@pytest.fixture
def sample_file_changes() -> list[FileChange]:
    """Sample file changes for testing."""
    return [
        FileChange(
            filename="django/db/models/query.py",
            status="modified",
            additions=15,
            deletions=5,
            changes=20,
            patch="@@ -100,5 +100,15 @@ def filter(self):\n+    # New filtering logic",
        ),
        FileChange(
            filename="tests/queryset/test_filtering.py",
            status="added",
            additions=50,
            deletions=0,
            changes=50,
            patch="@@ -0,0 +1,50 @@\n+class TestFiltering:",
        ),
    ]


@pytest.fixture
def sample_issue_info() -> IssueInfo:
    """Sample issue information for testing."""
    return IssueInfo(
        id="12345",
        title="QuerySet filter performance issue with large datasets",
        description="""When filtering QuerySets with many conditions, performance degrades significantly.

## Steps to reproduce:
1. Create a model with many fields
2. Apply multiple filter conditions
3. Observe slow query times

## Expected behavior:
Filtering should be optimized for large datasets.

## Actual behavior:
Query times increase exponentially with filter count.""",
        url="https://code.djangoproject.com/ticket/12345",
        labels=["Performance", "ORM"],
    )


@pytest.fixture
def sample_pr_info(sample_file_changes: list[FileChange], sample_issue_info: IssueInfo) -> PRInfo:
    """Sample PR information for testing."""
    return PRInfo(
        number=18234,
        title="Fixed #12345 -- Optimized QuerySet filter for large datasets",
        description="""This PR addresses the performance issue reported in ticket #12345.

## Changes:
- Optimized the filter chain building
- Added caching for repeated filter conditions
- Updated tests for the new behavior

Refs #12345""",
        author="testuser",
        merged_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
        merge_commit_sha="abc123def456",
        base_commit_sha="base123",
        head_commit_sha="head456",
        files_changed=sample_file_changes,
        labels=["Performance"],
        linked_issue=sample_issue_info,
        url="https://github.com/django/django/pull/18234",
    )


@pytest.fixture
def sample_developer_solution() -> Solution:
    """Sample developer solution for comparison."""
    return Solution(
        files={
            "django/db/models/query.py": '''class QuerySet:
    def filter(self, *args, **kwargs):
        """Optimized filter method with caching."""
        cache_key = self._build_cache_key(args, kwargs)
        if cache_key in self._filter_cache:
            return self._filter_cache[cache_key]

        result = self._apply_filters(*args, **kwargs)
        self._filter_cache[cache_key] = result
        return result

    def _build_cache_key(self, args, kwargs):
        return hash((args, tuple(sorted(kwargs.items()))))
''',
            "tests/queryset/test_filtering.py": '''import unittest
from django.test import TestCase
from django.db.models import QuerySet

class TestFiltering(TestCase):
    def test_filter_caching(self):
        """Test that repeated filters use cache."""
        qs = QuerySet()
        result1 = qs.filter(active=True)
        result2 = qs.filter(active=True)
        self.assertEqual(result1, result2)
''',
        },
        description="Developer implementation of QuerySet filter optimization",
        reasoning="Used caching strategy to avoid repeated filter computations",
    )


@pytest.fixture
def sample_claude_solution() -> Solution:
    """Sample Claude-generated solution for comparison."""
    return Solution(
        files={
            "django/db/models/query.py": '''class QuerySet:
    def filter(self, *args, **kwargs):
        """Filter method with basic optimization."""
        return self._apply_filters(*args, **kwargs)
''',
        },
        description="Claude's implementation attempt",
        reasoning="Implemented basic filter without caching optimization",
    )


@pytest.fixture
def sample_config() -> Config:
    """Sample configuration for testing."""
    return Config(
        project=ProjectConfig(
            name="django",
            repo="django/django",
            local_path=None,
        ),
        pr_selection=PRSelectionCriteria(
            merged=True,
            has_linked_issue=True,
            min_files_changed=1,
            max_files_changed=10,
            days_back=30,
        ),
        learning=LearningConfig(
            max_attempts_per_pr=2,
            success_threshold=0.7,
        ),
        prompts=PromptsConfig(),
        agent_config=AgentConfig(
            code_path="claude",
            model="claude-sonnet-4-20250514",
        ),
        issue_tracker=IssueTrackerConfig(
            url="https://code.djangoproject.com",
            ticket_pattern=r"#(\d+)",
        ),
        version_control_config=VersionControlConfig(),
    )


# Mock responses for Claude Code CLI
@pytest.fixture
def mock_claude_version_response() -> subprocess.CompletedProcess[str]:
    """Mock response for claude --version."""
    return subprocess.CompletedProcess(
        args=["claude", "--version"],
        returncode=0,
        stdout="claude-code 1.0.0\n",
        stderr="",
    )


@pytest.fixture
def mock_claude_solution_response() -> subprocess.CompletedProcess[str]:
    """Mock response for claude solution generation."""
    return subprocess.CompletedProcess(
        args=["claude", "--print"],
        returncode=0,
        stdout="""I've analyzed the issue and implemented a solution.

## Changes Made:
1. Modified `django/db/models/query.py` to optimize filter operations
2. Added caching mechanism for repeated filter conditions

The implementation follows Django's coding conventions and includes appropriate tests.""",
        stderr="",
    )


@pytest.fixture
def mock_claude_analysis_response() -> subprocess.CompletedProcess[str]:
    """Mock response for claude analysis."""
    return subprocess.CompletedProcess(
        args=["claude", "--print"],
        returncode=0,
        stdout="""<analysis>
{
    "overall_score": 0.75,
    "strengths": [
        "Correctly identified the core issue",
        "Applied appropriate filtering logic"
    ],
    "weaknesses": [
        "Missed caching optimization",
        "Did not include comprehensive tests"
    ],
    "key_insights": [
        "Django QuerySet optimizations often involve caching",
        "Performance PRs typically include benchmark tests"
    ]
}
</analysis>

I've updated the CLAUDE.md file with these learnings.""",
        stderr="",
    )


@pytest.fixture
def temp_repo_dir(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a temporary git repository for testing."""
    repo_dir = tmp_path / "test-repo"
    repo_dir.mkdir()

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )

    # Create initial commit
    readme = repo_dir / "README.md"
    readme.write_text("# Test Repository\n")
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )

    yield repo_dir


@pytest.fixture
def mock_subprocess_run(
    mock_claude_version_response: subprocess.CompletedProcess[str],
    mock_claude_solution_response: subprocess.CompletedProcess[str],
    mock_claude_analysis_response: subprocess.CompletedProcess[str],
) -> Generator[MagicMock, None, None]:
    """Mock subprocess.run for Claude Code CLI calls."""

    def subprocess_side_effect(
        cmd: list[str], *args: Any, **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        """Return appropriate mock response based on command."""
        if not cmd:
            raise ValueError("Empty command")

        # Handle claude commands
        if cmd[0] == "claude":
            if "--version" in cmd:
                return mock_claude_version_response
            elif "--print" in cmd:
                # Check if it's an analysis prompt (contains "analysis" or comparison-related terms)
                prompt = cmd[-1] if len(cmd) > 1 else ""
                if "analysis" in prompt.lower() or "compare" in prompt.lower():
                    return mock_claude_analysis_response
                return mock_claude_solution_response
            else:
                # Interactive mode - return success
                return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

        # Handle git commands - let them through or mock as needed
        if cmd[0] == "git":
            # For git commands, we might want to actually run them or mock
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

        # Default: return success
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    with patch("subprocess.run", side_effect=subprocess_side_effect) as mock_run:
        yield mock_run


@pytest.fixture
def no_github_token() -> Generator[None, None, None]:
    """Remove GitHub token for testing unauthenticated requests."""
    old_token = os.environ.get("GITHUB_TOKEN")
    os.environ.pop("GITHUB_TOKEN", None)
    yield
    if old_token:
        os.environ["GITHUB_TOKEN"] = old_token
