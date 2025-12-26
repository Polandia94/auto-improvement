"""GitHub Issues tracker client."""

from __future__ import annotations

import logging
import os
import re
import typing

import requests

from auto_improvement.issues_tracker_clients.abstract_issue_tracker import (
    AbstractIssueTrackerClient,
)
from auto_improvement.models import IssueInfo

if typing.TYPE_CHECKING:
    from auto_improvement.models import IssueTrackerConfig

logger = logging.getLogger(__name__)


class GitHubIssuesClient(AbstractIssueTrackerClient):
    """Client for GitHub Issues."""

    def __init__(self, config: IssueTrackerConfig):
        self.config = config
        self.session = requests.Session()
        github_token = os.getenv("GITHUB_TOKEN")
        if github_token:
            self.session.headers.update({"Authorization": f"token {github_token}"})
        self.session.headers.update({"Accept": "application/vnd.github.v3+json"})

    @typing.override
    def get_issue(self, issue_id: str) -> IssueInfo | None:
        """Fetch issue from GitHub Issues."""
        # Parse repo from config URL
        # Expected format: https://github.com/owner/repo/issues
        if not self.config.url:
            return None
        match = re.search(r"github\.com/([^/]+)/([^/]+)", self.config.url)
        if not match:
            return None

        owner, repo = match.groups()
        url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_id}"

        try:
            response = self.session.get(url)
            response.raise_for_status()
            issue_data = response.json()

            return IssueInfo(
                id=str(issue_data["number"]),
                title=issue_data["title"],
                description=issue_data.get("body", ""),
                url=issue_data["html_url"],
                labels=[label["name"] for label in issue_data.get("labels", [])],
            )
        except Exception as e:
            logger.warning(f"Error fetching GitHub issue {issue_id}: {e}")
            return None

    @typing.override
    def extract_issue_id_from_pr(self, pr_body: str) -> IssueInfo | None:
        """Extract linked issue ID from PR body and fetch issue details."""
        if not pr_body:
            return None

        # Parse repo from config URL
        if not self.config.url:
            return None
        match = re.search(r"github\.com/([^/]+)/([^/]+)", self.config.url)
        if not match:
            return None

        owner, repo = match.groups()

        # Look for common issue reference patterns
        patterns = [
            r"(?:fixes|closes|resolves|fix|close|resolve)\s+#(\d+)",
            r"(?:fixes|closes|resolves|fix|close|resolve)\s+https?://github\.com/[^/]+/[^/]+/issues/(\d+)",
        ]

        issue_number = None
        for pattern in patterns:
            match = re.search(pattern, pr_body, re.IGNORECASE)
            if match:
                issue_number = match.group(1)
                break

        if not issue_number:
            return None

        # Fetch issue details
        issue_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}"
        try:
            response = self.session.get(issue_url, timeout=30)
            response.raise_for_status()
            issue_data = response.json()

            return IssueInfo(
                id=str(issue_data["number"]),
                title=issue_data["title"],
                description=issue_data.get("body", ""),
                url=issue_data["html_url"],
                labels=[label["name"] for label in issue_data.get("labels", [])],
            )
        except Exception:
            return None
