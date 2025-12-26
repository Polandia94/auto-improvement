"""GitHub API client for fetching PRs and repository information."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, override

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from auto_improvement.version_control_clients.abstract_version_control_client import (
    AbstractVersionControlClient,
)

if TYPE_CHECKING:
    from auto_improvement.issues_tracker_clients.abstract_issue_tracker import (
        AbstractIssueTrackerClient,
    )
    from auto_improvement.models import PRInfo, PRSelectionCriteria

logger = logging.getLogger(__name__)


class GitHubClient(AbstractVersionControlClient):
    """Client for interacting with GitHub API."""

    @override
    def __init__(self, issue_tracker: AbstractIssueTrackerClient):
        self.issue_tracker = issue_tracker
        token = os.getenv("GITHUB_TOKEN")
        self.base_url = "https://api.github.com"
        self.session = requests.Session()

        # Configure retry strategy with exponential backoff
        retry_strategy = Retry(
            total=5,  # Total number of retries
            backoff_factor=2,  # Wait 2, 4, 8, 16, 32 seconds between retries
            status_forcelist=[429, 500, 502, 503, 504],  # Retry on these HTTP status codes
            allowed_methods=["GET"],  # Only retry GET requests
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        if token:
            self.session.headers.update({"Authorization": f"token {token}"})
        self.session.headers.update({"Accept": "application/vnd.github.v3+json"})

    @override
    def get_merged_prs(
        self, repo: str, criteria: PRSelectionCriteria, limit: int = 100
    ) -> list[PRInfo]:
        """Fetch merged PRs matching criteria using GitHub Search API."""
        # Use Search API to filter merged PRs directly (more efficient)
        url = f"{self.base_url}/search/issues"

        since = datetime.now(UTC) - timedelta(days=criteria.days_back)
        since_str = since.strftime("%Y-%m-%d")

        # Build search query: merged PRs in repo, merged after date
        query = f"repo:{repo} is:pr is:merged merged:>={since_str}"

        params: dict[str, str | int] = {
            "q": query,
            "sort": "updated",
            "order": "desc",
            "per_page": 100,
        }

        all_prs: list[PRInfo] = []
        page = 1

        while len(all_prs) < limit:
            print(f"Fetching merged PRs page {page}...")
            params_with_page: dict[str, str | int] = {**params, "page": page}
            try:
                response = self.session.get(url, params=params_with_page, timeout=30)
                response.raise_for_status()
                data = response.json()
                items = data.get("items", [])
            except requests.exceptions.RequestException as e:
                logger.error(f"Failed to fetch PRs page {page}: {e}")
                break

            if not items:
                break

            for item in items:
                pr_number = item["number"]
                logger.debug(f"Evaluating PR #{pr_number}")

                # Fetch full PR details (search API returns limited data)
                try:
                    pr_info = self.get_pr(repo, pr_number)
                except requests.exceptions.RequestException as e:
                    logger.warning(f"Failed to fetch PR #{pr_number}: {e}")
                    continue

                # Apply additional criteria
                if not self._matches_criteria(pr_info, criteria):
                    print(f"  PR #{pr_number} does not match criteria, skipping...")
                    continue

                all_prs.append(pr_info)

                if len(all_prs) >= limit:
                    break

            page += 1

        return all_prs

    @override
    def get_pr(self, repo: str, pr_number: int) -> PRInfo:
        """Fetch a specific PR."""
        owner, repo_name = repo.split("/")
        url = f"{self.base_url}/repos/{owner}/{repo_name}/pulls/{pr_number}"

        response = self.session.get(url, timeout=30)
        response.raise_for_status()
        pr_data = response.json()

        return self._parse_pr(pr_data)

    def _parse_pr(self, pr_data: dict[str, Any]) -> PRInfo:
        """Parse PR data from GitHub API."""
        from auto_improvement.models import FileChange, PRInfo

        # Get files changed with retry and error handling
        files_url = pr_data["url"] + "/files"
        try:
            logger.debug(f"Fetching files for PR #{pr_data['number']}: {files_url}")
            files_response = self.session.get(files_url, timeout=30)
            files_response.raise_for_status()
            files_data = files_response.json()
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to fetch files for PR #{pr_data['number']}: {e}")
            # Return PR info with empty file list if files fetch fails
            files_data = []

        file_changes = []
        for file_data in files_data:
            file_changes.append(
                FileChange(
                    filename=file_data["filename"],
                    status=file_data["status"],
                    additions=file_data["additions"],
                    deletions=file_data["deletions"],
                    changes=file_data["changes"],
                    patch=file_data.get("patch"),
                    previous_filename=file_data.get("previous_filename"),
                )
            )

        # Extract linked issue from title and body (Django often puts refs in title)
        pr_title = pr_data.get("title", "") or ""
        pr_body = pr_data.get("body", "") or ""
        combined_text = f"{pr_title}\n{pr_body}"
        linked_issue = self.issue_tracker.extract_issue_id_from_pr(combined_text)

        # Get labels
        labels = [label["name"] for label in pr_data.get("labels", [])]

        return PRInfo(
            number=pr_data["number"],
            title=pr_data["title"],
            description=pr_data.get("body") or "",
            author=pr_data["user"]["login"],
            merged_at=datetime.fromisoformat(pr_data["merged_at"].replace("Z", "+00:00")),
            merge_commit_sha=pr_data["merge_commit_sha"],
            base_commit_sha=pr_data["base"]["sha"],
            head_commit_sha=pr_data["head"]["sha"],
            files_changed=file_changes,
            labels=labels,
            linked_issue=linked_issue,
            url=pr_data["html_url"],
        )

    def _matches_criteria(self, pr_info: PRInfo, criteria: PRSelectionCriteria) -> bool:
        """Check if PR matches selection criteria."""
        # Check linked issue
        if criteria.has_linked_issue and not pr_info.linked_issue:
            print(f"PR #{pr_info.number}: no linked issue found")
            return False

        # Check files changed
        num_files = len(pr_info.files_changed)
        if num_files < criteria.min_files_changed or num_files > criteria.max_files_changed:
            print(f"PR #{pr_info.number}: file count {num_files} out of range")
            return False

        # Check labels
        pr_labels = set(pr_info.labels)

        if criteria.exclude_labels and any(label in pr_labels for label in criteria.exclude_labels):
            print(f"PR #{pr_info.number}: excluded label found")
            return False

        if criteria.include_labels and not any(
            label in pr_labels for label in criteria.include_labels
        ):
            print(f"PR #{pr_info.number}: required label not found")
            return False

        return True

    def get_repo_info(self, repo: str) -> dict[str, Any]:
        """Fetch repository information."""
        owner, repo_name = repo.split("/")
        url = f"{self.base_url}/repos/{owner}/{repo_name}"

        response = self.session.get(url, timeout=30)
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return data

    @override
    def get_readme(self, repo: str) -> str | None:
        """Fetch repository README."""
        owner, repo_name = repo.split("/")
        url = f"{self.base_url}/repos/{owner}/{repo_name}/readme"

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            readme_data = response.json()

            # Decode base64 content
            import base64

            content = base64.b64decode(readme_data["content"]).decode("utf-8")
            return content
        except Exception:
            return None
