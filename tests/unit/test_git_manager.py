"""Unit tests for auto_improvement.git_manager module."""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from auto_improvement.git_manager import GitManager
from auto_improvement.models import FileChange, PRInfo, Solution


class TestGitManagerInit:
    """Tests for GitManager initialization."""

    def test_init_with_short_repo_url(self) -> None:
        """Test initialization with owner/repo format."""
        manager = GitManager("django/django")
        assert manager.repo_url == "django/django"
        assert "django" in str(manager.local_path)

    def test_init_with_full_url(self) -> None:
        """Test initialization with full GitHub URL."""
        manager = GitManager("https://github.com/django/django")
        assert manager.repo_url == "https://github.com/django/django"
        assert "django" in str(manager.local_path)

    def test_init_with_custom_local_path(self, tmp_path: Path) -> None:
        """Test initialization with custom local path."""
        local_path = tmp_path / "my-repo"
        manager = GitManager("owner/repo", local_path=local_path)
        assert manager.local_path == local_path

    def test_get_repo_name_from_short_url(self) -> None:
        """Test extracting repo name from short URL."""
        manager = GitManager("owner/my-project")
        assert manager._get_repo_name() == "my-project"

    def test_get_repo_name_removes_git_suffix(self) -> None:
        """Test that .git suffix is removed from repo name."""
        manager = GitManager("https://github.com/owner/repo.git")
        assert manager._get_repo_name() == "repo"


class TestGitManagerOperations:
    """Tests for GitManager operations."""

    @pytest.fixture
    def temp_repo(self, tmp_path: Path) -> tuple[GitManager, Path]:
        """Create a temporary git repository."""
        repo_path = tmp_path / "test-repo"
        repo_path.mkdir()

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        # Create initial commit
        readme = repo_path / "README.md"
        readme.write_text("# Test Repository\n")
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        manager = GitManager("test/repo", local_path=repo_path)
        # Directly initialize the repo attribute (skip clone_or_update which needs remote)
        import git

        manager.repo = git.Repo(repo_path)

        return manager, repo_path

    def test_repo_initialized(self, temp_repo: tuple[GitManager, Path]) -> None:
        """Test that repo is properly initialized."""
        manager, repo_path = temp_repo

        # Repo should be initialized from fixture
        assert manager.repo is not None
        assert manager.local_path == repo_path

    def test_get_file_content(self, temp_repo: tuple[GitManager, Path]) -> None:
        """Test getting file content."""
        manager, repo_path = temp_repo

        content = manager.get_file_content("README.md")
        assert content is not None
        assert "Test Repository" in content

    def test_get_file_content_nonexistent(self, temp_repo: tuple[GitManager, Path]) -> None:
        """Test getting content of nonexistent file."""
        manager, _ = temp_repo

        content = manager.get_file_content("nonexistent.txt")
        assert content is None

    def test_apply_solution(self, temp_repo: tuple[GitManager, Path]) -> None:
        """Test applying a solution to the repository."""
        manager, repo_path = temp_repo

        solution = Solution(
            files={
                "new_file.py": "print('Hello, World!')\n",
                "subdir/nested.py": "# Nested file\n",
            },
            description="Test solution",
        )

        manager.apply_solution(solution)

        # Check files were created
        assert (repo_path / "new_file.py").exists()
        assert (repo_path / "subdir" / "nested.py").exists()
        assert (repo_path / "new_file.py").read_text() == "print('Hello, World!')\n"

    def test_get_changed_files(self, temp_repo: tuple[GitManager, Path]) -> None:
        """Test detecting changed files."""
        manager, repo_path = temp_repo

        # Create a new untracked file
        (repo_path / "new_file.txt").write_text("New content")

        changed = manager.get_changed_files()
        assert "new_file.txt" in changed

    def test_clean_removes_untracked_files(self, temp_repo: tuple[GitManager, Path]) -> None:
        """Test that clean removes untracked files."""
        manager, repo_path = temp_repo

        # Create untracked files
        (repo_path / "untracked.txt").write_text("Should be removed")

        manager.clean()

        assert not (repo_path / "untracked.txt").exists()

    def test_create_branch(self, temp_repo: tuple[GitManager, Path]) -> None:
        """Test creating a new branch."""
        manager, _ = temp_repo

        manager.create_branch("test-branch")

        # Verify branch was created and checked out
        assert manager.repo is not None
        assert manager.repo.active_branch.name == "test-branch"

    def test_reset_hard(self, temp_repo: tuple[GitManager, Path]) -> None:
        """Test hard reset."""
        manager, repo_path = temp_repo

        # Modify a file
        (repo_path / "README.md").write_text("Modified content")

        manager.reset_hard()

        # Verify file was reset
        assert (repo_path / "README.md").read_text() == "# Test Repository\n"

    def test_get_context_files(self, temp_repo: tuple[GitManager, Path]) -> None:
        """Test getting context files for a PR."""
        manager, repo_path = temp_repo

        # Create some files
        (repo_path / "file1.py").write_text("print('file1')")
        (repo_path / "file2.py").write_text("print('file2')")

        pr_info = PRInfo(
            number=1,
            title="Test PR",
            description="Test",
            author="user",
            merged_at=datetime.now(UTC),
            merge_commit_sha="abc",
            base_commit_sha="def",
            head_commit_sha="ghi",
            files_changed=[
                FileChange(
                    filename="file1.py",
                    status="added",
                    additions=1,
                    deletions=0,
                    changes=1,
                ),
                FileChange(
                    filename="file2.py",
                    status="added",
                    additions=1,
                    deletions=0,
                    changes=1,
                ),
            ],
            url="https://github.com/test/repo/pull/1",
        )

        context = manager.get_context_files(pr_info)
        assert "file1.py" in context
        assert "file2.py" in context

    def test_cleanup_removes_directory(self, tmp_path: Path) -> None:
        """Test that cleanup removes the repository directory."""
        repo_path = tmp_path / "to-be-deleted"
        repo_path.mkdir()
        (repo_path / "file.txt").write_text("content")

        manager = GitManager("test/repo", local_path=repo_path)
        manager.cleanup()

        assert not repo_path.exists()


class TestGitManagerErrorHandling:
    """Tests for GitManager error handling."""

    def test_checkout_without_init_raises_error(self) -> None:
        """Test that checkout operations raise error without initialization."""
        manager = GitManager("test/repo")

        pr_info = PRInfo(
            number=1,
            title="Test",
            description="Test",
            author="user",
            merged_at=datetime.now(UTC),
            merge_commit_sha="abc",
            base_commit_sha="def",
            head_commit_sha="ghi",
            files_changed=[],
            url="https://github.com/test/repo/pull/1",
        )

        with pytest.raises(ValueError, match="Repository not initialized"):
            manager.checkout_before_pr(pr_info)

    def test_get_file_content_without_init_raises_error(self) -> None:
        """Test that get_file_content raises error without initialization."""
        manager = GitManager("test/repo")

        with pytest.raises(ValueError, match="Repository not initialized"):
            manager.get_file_content("file.txt")

    def test_clean_without_init_raises_error(self) -> None:
        """Test that clean raises error without initialization."""
        manager = GitManager("test/repo")

        with pytest.raises(ValueError, match="Repository not initialized"):
            manager.clean()
