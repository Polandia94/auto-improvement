"""Jira issue tracker client."""

from __future__ import annotations

import logging
import os
import re
import typing
from typing import TYPE_CHECKING

import requests

from auto_improvement.issues_tracker_clients.abstract_issue_tracker import (
    AbstractIssueTrackerClient,
)
from auto_improvement.models import IssueInfo

if TYPE_CHECKING:
    from auto_improvement.models import IssueTrackerConfig

logger = logging.getLogger(__name__)


class JiraClient(AbstractIssueTrackerClient):
    """Client for Jira issue tracker."""

    def __init__(self, config: IssueTrackerConfig):
        self.config = config
        self.base_url = config.url.rstrip("/") if config.url else ""
        self.session = requests.Session()

        # Set up authentication if provided
        if config.auth:
            username = config.auth.get("username") or os.getenv("JIRA_USERNAME")
            api_token = config.auth.get("api_token") or os.getenv("JIRA_API_TOKEN")
            if username and api_token:
                self.session.auth = (username, api_token)

        self.session.headers.update({"Accept": "application/json"})

    @typing.override
    def get_issue(self, issue_id: str) -> IssueInfo | None:
        """Fetch issue from Jira."""
        url = f"{self.base_url}/rest/api/2/issue/{issue_id}"

        try:
            response = self.session.get(url)
            response.raise_for_status()
            issue_data = response.json()

            fields = issue_data.get("fields", {})

            # Get labels
            labels = fields.get("labels", [])

            # Also include component names as labels
            components = fields.get("components", [])
            for component in components:
                if component.get("name"):
                    labels.append(component["name"])

            return IssueInfo(
                id=issue_data["key"],
                title=fields.get("summary", ""),
                description=fields.get("description", "") or "",
                url=f"{self.base_url}/browse/{issue_data['key']}",
                labels=labels,
            )
        except Exception as e:
            logger.warning(f"Error fetching Jira issue {issue_id}: {e}")
            return None

    @typing.override
    def extract_issue_id_from_pr(self, pr_body: str) -> IssueInfo | None:
        """Extract Jira issue ID from PR body and fetch issue details."""
        if not pr_body:
            return None

        # Get ticket pattern from config or use default Jira pattern
        ticket_pattern = self.config.ticket_pattern or r"[A-Z][A-Z0-9]+-\d+"

        # Look for patterns like "PROJ-123" or Jira URLs
        patterns = [
            rf"(?:fix|fixes|fixed|close|closes|closed|resolve|resolves|resolved)\s+({ticket_pattern})",
            rf"({ticket_pattern})",  # Simple ticket reference
        ]

        # Also look for Jira URLs if base_url is configured
        if self.base_url:
            escaped_url = re.escape(self.base_url)
            patterns.insert(0, rf"{escaped_url}/browse/({ticket_pattern})")

        issue_id = None
        for pattern in patterns:
            match = re.search(pattern, pr_body, re.IGNORECASE)
            if match:
                issue_id = match.group(1).upper()
                break

        if not issue_id:
            return None

        # Fetch issue details using get_issue
        return self.get_issue(issue_id)
