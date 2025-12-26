"""Unit tests for issue tracker clients."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from auto_improvement.issues_tracker_clients.github_issues_client import GitHubIssuesClient
from auto_improvement.issues_tracker_clients.jira_client import JiraClient
from auto_improvement.issues_tracker_clients.trac_client import TracClient
from auto_improvement.models import IssueTrackerConfig


class TestGitHubIssuesClient:
    """Tests for GitHubIssuesClient."""

    @pytest.fixture
    def client(self) -> GitHubIssuesClient:
        """Create a GitHub Issues client."""
        config = IssueTrackerConfig(
            url="https://github.com/django/django/issues",
        )
        return GitHubIssuesClient(config)

    def test_init(self, client: GitHubIssuesClient) -> None:
        """Test client initialization."""
        assert client.config.url == "https://github.com/django/django/issues"

    def test_extract_issue_id_from_pr_fixes_pattern(self, client: GitHubIssuesClient) -> None:
        """Test extracting issue ID from PR body with 'fixes' pattern."""
        with patch.object(client.session, "get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "number": 123,
                "title": "Test Issue",
                "body": "Issue description",
                "html_url": "https://github.com/django/django/issues/123",
                "labels": [{"name": "bug"}],
            }
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            result = client.extract_issue_id_from_pr("This PR fixes #123")
            assert result is not None
            assert result.id == "123"
            assert result.title == "Test Issue"

    def test_extract_issue_id_from_pr_closes_pattern(self, client: GitHubIssuesClient) -> None:
        """Test extracting issue ID from PR body with 'closes' pattern."""
        with patch.object(client.session, "get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "number": 456,
                "title": "Another Issue",
                "body": "Description",
                "html_url": "https://github.com/django/django/issues/456",
                "labels": [],
            }
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            result = client.extract_issue_id_from_pr("Closes #456\n\nMore description")
            assert result is not None
            assert result.id == "456"

    def test_extract_issue_id_from_pr_no_match(self, client: GitHubIssuesClient) -> None:
        """Test extracting issue ID when no issue is referenced."""
        result = client.extract_issue_id_from_pr("This PR has no issue reference")
        assert result is None

    def test_extract_issue_id_from_pr_empty_body(self, client: GitHubIssuesClient) -> None:
        """Test extracting issue ID from empty PR body."""
        result = client.extract_issue_id_from_pr("")
        assert result is None

    def test_get_issue_success(self, client: GitHubIssuesClient) -> None:
        """Test getting issue by ID."""
        with patch.object(client.session, "get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "number": 789,
                "title": "Test Issue",
                "body": "Issue description",
                "html_url": "https://github.com/django/django/issues/789",
                "labels": [{"name": "enhancement"}],
            }
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            result = client.get_issue("789")
            assert result is not None
            assert result.id == "789"
            assert result.title == "Test Issue"
            assert "enhancement" in result.labels

    def test_get_issue_no_url(self) -> None:
        """Test get_issue when no URL is configured."""
        config = IssueTrackerConfig(url=None)
        client = GitHubIssuesClient(config)
        result = client.get_issue("123")
        assert result is None

    def test_get_issue_api_error(self, client: GitHubIssuesClient) -> None:
        """Test get_issue when API returns error."""
        with patch.object(client.session, "get") as mock_get:
            mock_get.side_effect = requests.exceptions.RequestException("API Error")

            result = client.get_issue("123")
            assert result is None


class TestTracClient:
    """Tests for TracClient."""

    @pytest.fixture
    def client(self) -> TracClient:
        """Create a Trac client."""
        config = IssueTrackerConfig(
            url="https://code.djangoproject.com",
            ticket_pattern=r"#(\d+)",
        )
        return TracClient(config)

    def test_init(self, client: TracClient) -> None:
        """Test client initialization."""
        assert client.base_url == "https://code.djangoproject.com"

    def test_extract_issue_id_from_pr_fixed_pattern(self, client: TracClient) -> None:
        """Test extracting Trac ticket from PR body with 'Fixed' pattern."""
        with patch.object(client, "get_issue") as mock_get_issue:
            mock_get_issue.return_value = MagicMock(id="12345")

            result = client.extract_issue_id_from_pr("Fixed #12345 - Some change")
            assert result is not None
            mock_get_issue.assert_called_once_with("12345")

    def test_extract_issue_id_from_pr_url_pattern(self, client: TracClient) -> None:
        """Test extracting Trac ticket from Django Trac URL."""
        with patch.object(client, "get_issue") as mock_get_issue:
            mock_get_issue.return_value = MagicMock(id="54321")

            result = client.extract_issue_id_from_pr(
                "This addresses https://code.djangoproject.com/ticket/54321"
            )
            assert result is not None
            mock_get_issue.assert_called_once_with("54321")

    def test_extract_issue_id_from_pr_no_match(self, client: TracClient) -> None:
        """Test extracting issue ID when no ticket is referenced."""
        result = client.extract_issue_id_from_pr("This PR has no ticket reference")
        assert result is None

    def test_get_issue_strips_hash(self, client: TracClient) -> None:
        """Test that get_issue strips # from issue ID."""
        with patch.object(client.session, "get") as mock_get:
            mock_response = MagicMock()
            mock_response.text = """
            <html>
                <h1 class="searchable">#123: Test Ticket</h1>
                <div class="description">
                    <div class="searchable">Ticket description</div>
                </div>
            </html>
            """
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            result = client.get_issue("#123")
            assert result is not None
            assert result.id == "123"

    def test_get_issue_network_error(self, client: TracClient) -> None:
        """Test get_issue when network error occurs."""
        with patch.object(client.session, "get") as mock_get:
            mock_get.side_effect = requests.exceptions.RequestException("Network Error")

            result = client.get_issue("123")
            assert result is None


class TestJiraClient:
    """Tests for JiraClient."""

    @pytest.fixture
    def client(self) -> JiraClient:
        """Create a Jira client."""
        config = IssueTrackerConfig(
            url="https://jira.example.com",
            ticket_pattern=r"PROJ-\d+",
        )
        return JiraClient(config)

    def test_init(self, client: JiraClient) -> None:
        """Test client initialization."""
        assert client.base_url == "https://jira.example.com"

    def test_init_with_auth(self) -> None:
        """Test client initialization with authentication."""
        config = IssueTrackerConfig(
            url="https://jira.example.com",
            auth={"username": "user", "api_token": "token"},
        )
        client = JiraClient(config)
        assert client.session.auth == ("user", "token")

    def test_extract_issue_id_from_pr_simple_pattern(self, client: JiraClient) -> None:
        """Test extracting Jira ticket from PR body."""
        with patch.object(client, "get_issue") as mock_get_issue:
            mock_get_issue.return_value = MagicMock(id="PROJ-123")

            result = client.extract_issue_id_from_pr("Fixes PROJ-123: Some change")
            assert result is not None
            mock_get_issue.assert_called_once_with("PROJ-123")

    def test_extract_issue_id_from_pr_url_pattern(self, client: JiraClient) -> None:
        """Test extracting Jira ticket from Jira URL."""
        with patch.object(client, "get_issue") as mock_get_issue:
            mock_get_issue.return_value = MagicMock(id="PROJ-456")

            result = client.extract_issue_id_from_pr("See https://jira.example.com/browse/PROJ-456")
            assert result is not None
            mock_get_issue.assert_called_once_with("PROJ-456")

    def test_extract_issue_id_from_pr_lowercase(self, client: JiraClient) -> None:
        """Test that issue ID is uppercased."""
        with patch.object(client, "get_issue") as mock_get_issue:
            mock_get_issue.return_value = MagicMock(id="PROJ-789")

            client.extract_issue_id_from_pr("fixes proj-789")
            # Issue ID should be uppercased
            mock_get_issue.assert_called_once_with("PROJ-789")

    def test_get_issue_success(self, client: JiraClient) -> None:
        """Test getting Jira issue by ID."""
        with patch.object(client.session, "get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "key": "PROJ-123",
                "fields": {
                    "summary": "Test Issue",
                    "description": "Issue description",
                    "labels": ["bug"],
                    "components": [{"name": "backend"}],
                },
            }
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            result = client.get_issue("PROJ-123")
            assert result is not None
            assert result.id == "PROJ-123"
            assert result.title == "Test Issue"
            assert "bug" in result.labels
            assert "backend" in result.labels

    def test_get_issue_api_error(self, client: JiraClient) -> None:
        """Test get_issue when API returns error."""
        with patch.object(client.session, "get") as mock_get:
            mock_get.side_effect = requests.exceptions.RequestException("API Error")

            result = client.get_issue("PROJ-123")
            assert result is None
