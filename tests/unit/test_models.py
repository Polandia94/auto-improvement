"""Unit tests for auto_improvement.models module."""

from __future__ import annotations

from datetime import UTC, datetime

from auto_improvement.agent_clients.claude_client import ClaudeClient
from auto_improvement.issues_tracker_clients.github_issues_client import GitHubIssuesClient
from auto_improvement.issues_tracker_clients.jira_client import JiraClient
from auto_improvement.issues_tracker_clients.trac_client import TracClient
from auto_improvement.models import (
    AgentConfig,
    Config,
    FileChange,
    ImprovementRun,
    ImprovementSession,
    IssueInfo,
    IssueTrackerConfig,
    LearningConfig,
    PRInfo,
    ProjectConfig,
    PRSelectionCriteria,
    Solution,
    VersionControlConfig,
)
from auto_improvement.version_control_clients.github_client import GitHubClient


class TestIssueTrackerConfig:
    """Tests for IssueTrackerConfig model."""

    def test_default_client_is_github_issues(self) -> None:
        """Test that default client is GitHubIssuesClient."""
        config = IssueTrackerConfig()
        assert config.client == GitHubIssuesClient

    def test_string_to_client_type_github(self) -> None:
        """Test that 'github_issues' string is converted to class."""
        config = IssueTrackerConfig.model_validate({"client": "github_issues"})
        assert config.client == GitHubIssuesClient

    def test_string_to_client_type_jira(self) -> None:
        """Test that 'jira' string is converted to class."""
        config = IssueTrackerConfig.model_validate({"client": "jira"})
        assert config.client == JiraClient

    def test_string_to_client_type_trac(self) -> None:
        """Test that 'trac' string is converted to class."""
        config = IssueTrackerConfig.model_validate({"client": "trac"})
        assert config.client == TracClient

    def test_explicit_client_class(self) -> None:
        """Test setting client as class directly."""
        config = IssueTrackerConfig(client=TracClient)
        assert config.client == TracClient

    def test_url_and_ticket_pattern(self) -> None:
        """Test URL and ticket pattern configuration."""
        config = IssueTrackerConfig(
            client=JiraClient,
            url="https://jira.example.com",
            ticket_pattern=r"PROJ-\d+",
        )
        assert config.url == "https://jira.example.com"
        assert config.ticket_pattern == r"PROJ-\d+"


class TestProjectConfig:
    """Tests for ProjectConfig model."""

    def test_defaults(self) -> None:
        """Test default values."""
        config = ProjectConfig()
        assert config.name is None
        assert config.repo is None
        assert config.local_path is None

    def test_with_values(self) -> None:
        """Test with explicit values."""
        config = ProjectConfig(
            name="My Project",
            repo="owner/repo",
        )
        assert config.name == "My Project"
        assert config.repo == "owner/repo"


class TestPRSelectionCriteria:
    """Tests for PRSelectionCriteria model."""

    def test_defaults(self) -> None:
        """Test default values."""
        criteria = PRSelectionCriteria()
        assert criteria.merged is True
        assert criteria.has_linked_issue is True
        assert criteria.min_files_changed == 1
        assert criteria.max_files_changed == 20
        assert criteria.exclude_labels == []
        assert criteria.include_labels == []
        assert criteria.days_back == 365

    def test_custom_values(self) -> None:
        """Test with custom values."""
        criteria = PRSelectionCriteria(
            min_files_changed=5,
            max_files_changed=50,
            exclude_labels=["wip", "draft"],
            include_labels=["bug", "feature"],
            days_back=30,
        )
        assert criteria.min_files_changed == 5
        assert criteria.max_files_changed == 50
        assert criteria.exclude_labels == ["wip", "draft"]
        assert criteria.include_labels == ["bug", "feature"]
        assert criteria.days_back == 30


class TestLearningConfig:
    """Tests for LearningConfig model."""

    def test_defaults(self) -> None:
        """Test default values."""
        config = LearningConfig()
        assert config.max_attempts_per_pr == 3
        assert config.success_threshold == 0.8
        assert config.min_prs_before_next == 1
        assert config.max_prs_per_session == 10


class TestAgentConfig:
    """Tests for AgentConfig model."""

    def test_defaults(self) -> None:
        """Test default values."""
        config = AgentConfig()
        assert config.client == ClaudeClient
        assert config.code_path == "claude"
        assert config.model is None
        assert config.max_tokens == 8000
        assert config.temperature == 0.7
        assert config.api_key is None

    def test_with_values(self) -> None:
        """Test with custom values."""
        config = AgentConfig(
            code_path="/usr/local/bin/claude",
            model="claude-sonnet-4-20250514",
            temperature=0.5,
        )
        assert config.code_path == "/usr/local/bin/claude"
        assert config.model == "claude-sonnet-4-20250514"
        assert config.temperature == 0.5


class TestVersionControlConfig:
    """Tests for VersionControlConfig model."""

    def test_default_client_is_github(self) -> None:
        """Test that default client is GitHubClient."""
        config = VersionControlConfig()
        assert config.client == GitHubClient


class TestConfig:
    """Tests for Config model."""

    def test_defaults(self) -> None:
        """Test default configuration."""
        config = Config()
        assert config.project.name is None
        assert config.pr_selection.merged is True
        assert config.learning.max_attempts_per_pr == 3
        assert config.agent_config.code_path == "claude"
        assert config.issue_tracker.client == GitHubIssuesClient
        assert config.version_control_config.client == GitHubClient


class TestIssueInfo:
    """Tests for IssueInfo model."""

    def test_creation(self) -> None:
        """Test creating an issue info."""
        issue = IssueInfo(
            id="123",
            title="Test Issue",
            description="Test description",
            url="https://github.com/owner/repo/issues/123",
            labels=["bug", "priority:high"],
        )
        assert issue.id == "123"
        assert issue.title == "Test Issue"
        assert issue.description == "Test description"
        assert issue.url == "https://github.com/owner/repo/issues/123"
        assert issue.labels == ["bug", "priority:high"]

    def test_default_labels(self) -> None:
        """Test default empty labels list."""
        issue = IssueInfo(
            id="123",
            title="Test Issue",
            description="Test description",
            url="https://github.com/owner/repo/issues/123",
        )
        assert issue.labels == []


class TestFileChange:
    """Tests for FileChange model."""

    def test_creation(self) -> None:
        """Test creating a file change."""
        change = FileChange(
            filename="src/main.py",
            status="modified",
            additions=10,
            deletions=5,
            changes=15,
            patch="@@ -1,5 +1,10 @@",
        )
        assert change.filename == "src/main.py"
        assert change.status == "modified"
        assert change.additions == 10
        assert change.deletions == 5
        assert change.changes == 15
        assert change.patch == "@@ -1,5 +1,10 @@"

    def test_renamed_file(self) -> None:
        """Test file change for renamed file."""
        change = FileChange(
            filename="new_name.py",
            status="renamed",
            additions=0,
            deletions=0,
            changes=0,
            previous_filename="old_name.py",
        )
        assert change.status == "renamed"
        assert change.previous_filename == "old_name.py"


class TestPRInfo:
    """Tests for PRInfo model."""

    def test_creation(self) -> None:
        """Test creating a PR info."""
        merged_at = datetime.now(UTC)
        pr = PRInfo(
            number=123,
            title="Test PR",
            description="Test PR description",
            author="testuser",
            merged_at=merged_at,
            merge_commit_sha="abc123",
            base_commit_sha="def456",
            head_commit_sha="ghi789",
            files_changed=[],
            url="https://github.com/owner/repo/pull/123",
        )
        assert pr.number == 123
        assert pr.title == "Test PR"
        assert pr.author == "testuser"
        assert pr.merged_at == merged_at
        assert pr.linked_issue is None

    def test_with_linked_issue(self) -> None:
        """Test PR with linked issue."""
        issue = IssueInfo(
            id="456",
            title="Related Issue",
            description="Issue description",
            url="https://github.com/owner/repo/issues/456",
        )
        pr = PRInfo(
            number=123,
            title="Test PR",
            description="Fixes #456",
            author="testuser",
            merged_at=datetime.now(UTC),
            merge_commit_sha="abc123",
            base_commit_sha="def456",
            head_commit_sha="ghi789",
            files_changed=[],
            linked_issue=issue,
            url="https://github.com/owner/repo/pull/123",
        )
        assert pr.linked_issue is not None
        assert pr.linked_issue.id == "456"


class TestSolution:
    """Tests for Solution model."""

    def test_creation(self) -> None:
        """Test creating a solution."""
        solution = Solution(
            files={"src/main.py": "print('hello')"},
            description="A simple solution",
            reasoning="Just print hello",
        )
        assert solution.files == {"src/main.py": "print('hello')"}
        assert solution.description == "A simple solution"
        assert solution.reasoning == "Just print hello"

    def test_without_reasoning(self) -> None:
        """Test solution without reasoning."""
        solution = Solution(
            files={"src/main.py": "print('hello')"},
            description="A simple solution",
        )
        assert solution.reasoning is None


class TestImprovementSession:
    """Tests for ImprovementSession model."""

    def test_creation(self) -> None:
        """Test creating an improvement session."""
        pr = PRInfo(
            number=123,
            title="Test PR",
            description="Test",
            author="testuser",
            merged_at=datetime.now(UTC),
            merge_commit_sha="abc123",
            base_commit_sha="def456",
            head_commit_sha="ghi789",
            files_changed=[],
            url="https://github.com/owner/repo/pull/123",
        )
        session = ImprovementSession(
            pr_info=pr,
            attempts=2,
            success=True,
            best_score=0.85,
            key_insights=["Insight 1", "Insight 2"],
        )
        assert session.attempts == 2
        assert session.success is True
        assert session.best_score == 0.85
        assert len(session.key_insights) == 2


class TestImprovementRun:
    """Tests for ImprovementRun model."""

    def test_defaults(self) -> None:
        """Test default values."""
        run = ImprovementRun()
        assert run.sessions == []
        assert run.total_prs == 0
        assert run.successful_prs == 0
        assert run.average_score == 0.0
        assert run.total_learnings == 0
        assert run.completed_at is None
