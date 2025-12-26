"""Trac issue tracker client."""

from __future__ import annotations

import logging
import re
import typing
from typing import TYPE_CHECKING

import requests
from bs4 import BeautifulSoup, Tag

from auto_improvement.issues_tracker_clients.abstract_issue_tracker import (
    AbstractIssueTrackerClient,
)
from auto_improvement.models import IssueInfo

if TYPE_CHECKING:
    from auto_improvement.models import IssueTrackerConfig

logger = logging.getLogger(__name__)


class TracClient(AbstractIssueTrackerClient):
    """Client for Trac issue tracker (used by Django)."""

    def __init__(self, config: IssueTrackerConfig):
        self.config = config
        self.base_url = config.url.rstrip("/") if config.url else ""
        self.session = requests.Session()

    @typing.override
    def get_issue(self, issue_id: str) -> IssueInfo | None:
        """Fetch issue from Trac."""
        # Clean issue ID (remove # if present)
        issue_id = issue_id.lstrip("#")

        url = f"{self.base_url}/ticket/{issue_id}"

        try:
            response = self.session.get(url)
            response.raise_for_status()

            # Parse HTML to extract issue information
            soup = BeautifulSoup(response.text, "html.parser")

            # Get title
            title_elem = soup.find("h1", class_="searchable") or soup.find("h1")
            title = title_elem.get_text(strip=True) if title_elem else f"Ticket #{issue_id}"

            # Remove ticket number from title if present
            title = re.sub(r"^#?\d+:\s*", "", title)

            # Get description - the actual text is in div.searchable inside div.description
            description_elem = soup.find("div", class_="description")
            description = ""
            if isinstance(description_elem, Tag):
                # Find the searchable div inside description which contains the actual text
                searchable_div = description_elem.find("div", class_="searchable")
                if isinstance(searchable_div, Tag):
                    description = searchable_div.get_text(separator="\n", strip=True)
                else:
                    description = description_elem.get_text(separator="\n", strip=True)

            # Get labels/keywords
            labels: list[str] = []
            keywords_elem = soup.find("td", headers="h_keywords")
            if isinstance(keywords_elem, Tag):
                keywords_text = keywords_elem.get_text(strip=True)
                if keywords_text:
                    labels = [k.strip() for k in keywords_text.split(",")]

            return IssueInfo(
                id=issue_id,
                title=title,
                description=description,
                url=url,
                labels=labels,
            )
        except Exception as e:
            logger.warning(f"Error fetching Trac issue {issue_id}: {e}")
            return None

    @typing.override
    def extract_issue_id_from_pr(self, pr_body: str) -> IssueInfo | None:
        """Extract Trac issue ID from PR body and fetch issue details."""
        if not pr_body:
            print("No PR body provided.")
            return None

        # Look for patterns like "Fixed #12345", "Refs #12345", "ticket #12345" or Trac URLs
        patterns = [
            r"(?:fix|fixes|fixed|close|closes|closed|resolve|resolves|resolved|ref|refs)\s+#(\d+)",
            r"ticket[\s-]+#?(\d+)",  # Matches "ticket #12345", "ticket-12345", "ticket12345"
            r"code\.djangoproject\.com/ticket/(\d+)",
        ]

        issue_id = None
        for pattern in patterns:
            match = re.search(pattern, pr_body, re.IGNORECASE)
            if match:
                issue_id = match.group(1)
                break

        if not issue_id:
            return None

        # Fetch issue details using get_issue
        return self.get_issue(issue_id)
