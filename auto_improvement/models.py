"""Data models for auto-improvement system."""

from __future__ import annotations

import importlib
from datetime import datetime
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field, model_validator

from auto_improvement.agent_clients.abstract_agent import AbstractAgentClient
from auto_improvement.issues_tracker_clients.abstract_issue_tracker import (
    AbstractIssueTrackerClient,
)
from auto_improvement.version_control_clients.abstract_version_control_client import (
    AbstractVersionControlClient,
)


def _convert_issue_tracker_client(
    v: type[AbstractIssueTrackerClient] | str | None,
) -> type[AbstractIssueTrackerClient] | None:
    """Convert string to issue tracker client class."""
    if v is None:
        return None
    if isinstance(v, str):
        mapping = {
            "github_issues": "auto_improvement.issues_tracker_clients.github_issues_client.GitHubIssuesClient",
            "jira": "auto_improvement.issues_tracker_clients.jira_client.JiraClient",
            "trac": "auto_improvement.issues_tracker_clients.trac_client.TracClient",
        }
        client_path = mapping.get(v.lower())
        if client_path:
            module_name, class_name = client_path.rsplit(".", 1)
            module = importlib.import_module(module_name)
            cls: type[AbstractIssueTrackerClient] = getattr(module, class_name)
            return cls
        return None  # Unknown string returns None
    return v


IssueTrackerClientType = Annotated[
    type[AbstractIssueTrackerClient] | None,
    BeforeValidator(_convert_issue_tracker_client),
]


class IssueTrackerConfig(BaseModel):
    """Configuration for issue tracker."""

    client: IssueTrackerClientType = None
    url: str | None = None
    ticket_pattern: str | None = None
    auth: dict[str, str] | None = None

    @model_validator(mode="after")
    def set_default_client(self) -> IssueTrackerConfig:
        """Set default client if not provided."""
        if self.client is None:
            from auto_improvement.issues_tracker_clients.github_issues_client import (
                GitHubIssuesClient,
            )

            self.client = GitHubIssuesClient
        return self


class ProjectConfig(BaseModel):
    """Project configuration."""

    name: str | None = None
    repo: str | None = None
    local_path: Path | None = None


class PRSelectionCriteria(BaseModel):
    """Criteria for selecting PRs to learn from."""

    merged: bool = True
    has_linked_issue: bool = True
    min_files_changed: int = 1
    max_files_changed: int = 20
    exclude_labels: list[str] = Field(default_factory=list)
    include_labels: list[str] = Field(default_factory=list)
    days_back: int = 365


class LearningConfig(BaseModel):
    """Learning configuration."""

    max_attempts_per_pr: int = 3
    success_threshold: float = 0.8
    min_prs_before_next: int = 1
    max_prs_per_session: int = 10


class AgentConfig(BaseModel):
    """AI Agent configuration."""

    client: type[AbstractAgentClient] | None = None

    # For Code mode (CLI-based agents)
    code_path: str = Field(default="claude")

    # Docker isolation (always enabled for security)
    docker_image: str = Field(default="auto-improve-sandbox", description="Docker image name")

    # For API mode
    model: str | None = None
    max_tokens: int = 8000
    temperature: float = 0.7
    api_key: str | None = None

    @model_validator(mode="after")
    def set_default_client(self) -> AgentConfig:
        """Set default client if not provided."""
        if self.client is None:
            from auto_improvement.agent_clients.claude_client import ClaudeClient

            self.client = ClaudeClient
        return self


class PromptsConfig(BaseModel):
    """Custom prompts configuration."""

    # Optional: Override default unified analysis prompt
    analysis: str | None = None


class VersionControlConfig(BaseModel):
    """Version control system configuration."""

    client: type[AbstractVersionControlClient] | None = None

    @model_validator(mode="after")
    def set_default_client(self) -> VersionControlConfig:
        """Set default client if not provided."""
        if self.client is None:
            from auto_improvement.version_control_clients.github_client import (
                GitHubClient,
            )

            self.client = GitHubClient
        return self


class Config(BaseModel):
    """Main configuration."""

    project: ProjectConfig = Field(default_factory=ProjectConfig)
    pr_selection: PRSelectionCriteria = Field(default_factory=PRSelectionCriteria)
    learning: LearningConfig = Field(default_factory=LearningConfig)
    prompts: PromptsConfig = Field(default_factory=PromptsConfig)
    agent_config: AgentConfig = Field(default_factory=AgentConfig)
    issue_tracker: IssueTrackerConfig = Field(default_factory=IssueTrackerConfig)
    version_control_config: VersionControlConfig = Field(default_factory=VersionControlConfig)


class IssueInfo(BaseModel):
    """Information about a linked issue."""

    id: str
    title: str
    description: str
    url: str
    labels: list[str] = Field(default_factory=list)


class FileChange(BaseModel):
    """Information about a changed file in a PR."""

    filename: str
    status: str  # added, modified, removed, renamed
    additions: int
    deletions: int
    changes: int
    patch: str | None = None
    previous_filename: str | None = None


class PRInfo(BaseModel):
    """Information about a pull request."""

    number: int
    title: str
    description: str
    author: str
    merged_at: datetime
    merge_commit_sha: str
    base_commit_sha: str
    head_commit_sha: str
    files_changed: list[FileChange]
    labels: list[str] = Field(default_factory=list)
    linked_issue: IssueInfo | None = None
    url: str


class Solution(BaseModel):
    """A solution to a problem."""

    files: dict[str, str]  # filename -> content
    description: str
    reasoning: str | None = None


class ImprovementSession(BaseModel):
    """A single improvement session (one PR)."""

    pr_info: PRInfo
    attempts: int
    success: bool
    best_score: float
    key_insights: list[str] = Field(default_factory=list)
    files_updated: list[str] = Field(default_factory=list)
    claude_solution: Solution | None = None
    developer_solution: Solution | None = None
    timestamp: datetime = Field(default_factory=datetime.now)


class ImprovementRun(BaseModel):
    """A complete improvement run across multiple PRs."""

    sessions: list[ImprovementSession] = Field(default_factory=list)
    total_prs: int = 0
    successful_prs: int = 0
    average_score: float = 0.0
    total_learnings: int = 0
    started_at: datetime = Field(default_factory=datetime.now)
    completed_at: datetime | None = None
