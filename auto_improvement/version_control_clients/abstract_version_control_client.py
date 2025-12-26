"""Abstract API client for fetching PRs and repository information."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from auto_improvement.issues_tracker_clients.abstract_issue_tracker import (
        AbstractIssueTrackerClient,
    )
    from auto_improvement.models import PRInfo, PRSelectionCriteria


class AbstractVersionControlClient(ABC):
    """Abstract client for interacting with version control systems."""

    @abstractmethod
    def __init__(self, issue_tracker: AbstractIssueTrackerClient) -> None: ...

    @abstractmethod
    def get_merged_prs(
        self, repo: str, criteria: PRSelectionCriteria, limit: int = 100
    ) -> list[PRInfo]: ...

    @abstractmethod
    def get_pr(self, repo: str, pr_number: int) -> PRInfo: ...

    @abstractmethod
    def get_readme(self, repo: str) -> str | None: ...
