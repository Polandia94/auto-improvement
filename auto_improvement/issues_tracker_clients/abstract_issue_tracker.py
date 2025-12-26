"""Issue tracker integrations (Trac, Jira, etc.)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from auto_improvement.models import IssueInfo, IssueTrackerConfig


class AbstractIssueTrackerClient(ABC):
    """Base class for issue tracker clients."""

    @abstractmethod
    def __init__(self, config: IssueTrackerConfig) -> None:
        """Initialize the issue tracker client."""
        ...

    @abstractmethod
    def get_issue(self, issue_id: str) -> IssueInfo | None:
        """Fetch issue information."""
        raise NotImplementedError

    @abstractmethod
    def extract_issue_id_from_pr(self, pr_body: str) -> IssueInfo | None:
        """Extract issue ID from PR body and return issue info."""
        raise NotImplementedError
