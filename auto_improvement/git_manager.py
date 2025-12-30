"""Git operations manager for time travel and repo management."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, cast

import git

from auto_improvement.models import Solution

if TYPE_CHECKING:
    from auto_improvement.models import PRInfo

logger = logging.getLogger(__name__)


class GitManager:
    """Manages git operations for the improvement process."""

    def __init__(self, repo_url: str, local_path: Path | None = None):
        self.repo_url = repo_url
        self.local_path = local_path or Path.cwd() / ".auto-improve-repos" / self._get_repo_name()
        self.repo: git.Repo | None = None

    def _get_repo_name(self) -> str:
        """Extract repo name from URL."""
        # Handle both https://github.com/owner/repo and owner/repo formats
        if "/" in self.repo_url:
            return self.repo_url.split("/")[-1].replace(".git", "")
        return self.repo_url

    def clone_or_update(self) -> git.Repo:
        """Clone repository if it doesn't exist, otherwise update it."""
        if self.local_path.exists() and (self.local_path / ".git").exists():
            logger.info(f"Repository already exists at {self.local_path}, updating...")
            self.repo = git.Repo(self.local_path)
            # Try to fetch latest changes, but don't fail if network is unavailable
            try:
                self.repo.remotes.origin.fetch()
            except git.exc.GitCommandError as e:
                logger.warning(f"Could not fetch updates (network may be unavailable): {e}")
        else:
            logger.info(f"Cloning repository to {self.local_path}...")
            self.local_path.mkdir(parents=True, exist_ok=True)

            # Convert owner/repo to full URL if needed
            if not self.repo_url.startswith("http"):
                full_url = f"https://github.com/{self.repo_url}.git"
            else:
                full_url = self.repo_url

            # Try a shallow clone first to avoid long stalls for large repos.
            # Disable git terminal prompts so clone fails fast on auth issues.
            env = os.environ.copy()
            env.setdefault("GIT_TERMINAL_PROMPT", "0")

            try:
                self.repo = git.Repo.clone_from(full_url, self.local_path)
            except subprocess.TimeoutExpired as e:
                raise RuntimeError("git clone timed out") from e

        return self.repo

    def checkout_before_pr(self, pr_info: PRInfo) -> str:
        """Checkout the commit just before the PR was merged."""
        if not self.repo:
            raise ValueError("Repository not initialized. Call clone_or_update() first.")

        # Checkout the base commit (the commit the PR was based on)
        base_commit = pr_info.base_commit_sha
        logger.debug(f"Checking out commit before PR: {base_commit[:8]}")

        self.repo.git.checkout(base_commit, force=True)
        return base_commit

    def checkout_after_pr(self, pr_info: PRInfo) -> str:
        """Checkout the merge commit to see the final state after PR."""
        if not self.repo:
            raise ValueError("Repository not initialized. Call clone_or_update() first.")

        merge_commit = pr_info.merge_commit_sha
        logger.debug(f"Checking out merge commit: {merge_commit[:8]}")

        self.repo.git.checkout(merge_commit, force=True)
        return merge_commit

    def get_file_content(self, file_path: str, commit: str | None = None) -> str | None:
        """Get content of a file at a specific commit or current HEAD."""
        if not self.repo:
            raise ValueError("Repository not initialized. Call clone_or_update() first.")

        try:
            if commit:
                # Get file content at specific commit
                return cast(str, self.repo.git.show(f"{commit}:{file_path}"))
            else:
                # Get current file content
                full_path = self.local_path / file_path
                if full_path.exists():
                    return full_path.read_text()
                return None
        except git.GitCommandError:
            return None

    def get_pr_solution(self, pr_info: PRInfo) -> Solution:
        """Extract the developer's solution from a PR."""
        # Checkout after PR to get the final state
        self.checkout_after_pr(pr_info)

        files = {}
        for file_change in pr_info.files_changed:
            if file_change.status in ["added", "modified"]:
                content = self.get_file_content(file_change.filename)
                if content:
                    files[file_change.filename] = content

        return Solution(
            files=files,
            description=pr_info.description,
            reasoning=f"Developer solution from PR #{pr_info.number}",
        )

    def apply_solution(self, solution: Solution) -> None:
        """Apply a solution to the current checkout."""
        if not self.repo:
            raise ValueError("Repository not initialized. Call clone_or_update() first.")

        for filename, content in solution.files.items():
            file_path = self.local_path / filename

            # Create parent directories if needed
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Write the file
            file_path.write_text(content)

    def get_changed_files(self) -> list[str]:
        """Get list of files changed in working directory."""
        if not self.repo:
            raise ValueError("Repository not initialized. Call clone_or_update() first.")

        # Get both staged and unstaged changes
        changed_files: list[str] = []

        # Unstaged changes
        for item in self.repo.index.diff(None):
            if item.a_path is not None:
                changed_files.append(item.a_path)

        # Untracked files
        changed_files.extend(self.repo.untracked_files)

        return changed_files

    def create_branch(self, branch_name: str) -> None:
        """Create a new branch for testing."""
        if not self.repo:
            raise ValueError("Repository not initialized. Call clone_or_update() first.")

        # Create and checkout new branch
        self.repo.git.checkout("-b", branch_name)

    def reset_hard(self, commit: str = "HEAD") -> None:
        """Reset repository to a specific commit."""
        if not self.repo:
            raise ValueError("Repository not initialized. Call clone_or_update() first.")

        self.repo.git.reset("--hard", commit)

    def clean(self, exclude_patterns: list[str] | None = None) -> None:
        """
        Remove untracked files and directories, excluding specified patterns.

        Args:
            exclude_patterns: List of patterns to exclude from cleaning.

        """
        if not self.repo:
            raise ValueError("Repository not initialized. Call clone_or_update() first.")

        # Build git clean command with excludes
        args = ["-fd"]  # Don't use -x to respect .gitignore
        if exclude_patterns:
            for pattern in exclude_patterns:
                args.extend(["--exclude", pattern])

        self.repo.git.clean(*args)

    def cleanup(self) -> None:
        """Clean up the local repository."""
        if self.local_path.exists():
            shutil.rmtree(self.local_path)
