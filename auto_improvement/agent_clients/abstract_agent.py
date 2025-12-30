"""Agent Abstract Client."""

from __future__ import annotations

import difflib
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from auto_improvement.models import AgentConfig, IssueInfo, PRInfo, Solution


class AbstractAgentClient(ABC):
    """Abstract client for interacting with Agents."""

    agent_name: str
    agent_file: str
    working_dir: Path
    code_path: str
    config: AgentConfig

    @abstractmethod
    def __init__(self, config: AgentConfig, working_dir: Path | None = None): ...

    @abstractmethod
    def generate_solution(
        self,
        pr_info: PRInfo,
        issue_info: IssueInfo | None,
        agent_md_path: Path | None = None,
    ) -> Solution: ...

    def _build_implementation_prompt(
        self,
        pr_info: PRInfo,
        issue_info: IssueInfo | None,
    ) -> str:
        """Build prompt for implementation."""
        prompt_parts = []

        # Add issue information
        if issue_info:
            prompt_parts.append(f"# Issue: {issue_info.title}\n")
            prompt_parts.append(f"{issue_info.description}\n")
            prompt_parts.append(f"Issue URL: {issue_info.url}\n")
        else:
            prompt_parts.append(f"# Task: {pr_info.title}\n")
            prompt_parts.append(f"{pr_info.description}\n")

        prompt_parts.append("\n## Task\n")
        prompt_parts.append(
            "Implement a solution to address the issue above. "
            "Follow the project's existing patterns and conventions. "
            "Make the minimum necessary changes to fix the issue.\n"
        )

        # List files that need to be modified

        return "".join(prompt_parts)

    def _detect_changed_files(self) -> list[str]:
        """Detect files that have been changed in the working directory."""
        # Use git to detect changes if available
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                cwd=str(self.working_dir),
                timeout=5,
                check=False,
            )

            if result.returncode == 0:
                changed_files = []
                for line in result.stdout.split("\n"):
                    if line.strip():
                        # Parse git status format: "XY filename"
                        parts = line.strip().split(maxsplit=1)
                        if len(parts) == 2:
                            changed_files.append(parts[1])
                return changed_files
        except Exception:
            pass

        return []

    def _extract_files_from_response(self, response: str, pr_info: PRInfo) -> dict[str, str]:
        """Extract file contents from Agent's response."""
        files = {}

        # Look for code blocks with filenames
        import re

        # Pattern: ```python\n# filename.py\n<code>```
        # or ```\nfilename.py\n<code>```
        # This is a simple heuristic - in practice Agent might format differently

        # Try to find file sections
        for file_change in pr_info.files_changed:
            if file_change.status not in ["added", "modified"]:
                continue

            filename = file_change.filename

            # Look for the filename in the response
            # and extract code after it
            patterns = [
                # ```python\n# path/to/file.py\n<code>```
                rf"```\w*\n#\s*{re.escape(filename)}\n(.*?)```",
                # ```python\npath/to/file.py\n<code>```
                rf"```\w*\n{re.escape(filename)}\n(.*?)```",
                # Just the filename followed by a code block
                rf"{re.escape(filename)}.*?```\w*\n(.*?)```",
            ]

            for pattern in patterns:
                match = re.search(pattern, response, re.DOTALL)
                if match:
                    files[filename] = match.group(1).strip()
                    break

        return files

    @abstractmethod
    def run_analysis(self, prompt: str, workspace_dir: Path) -> None:
        """
        Run an analysis task with the given prompt in the specified workspace.

        The agent should execute the prompt and make any necessary file changes
        in the workspace directory. This runs in Docker for isolation.

        Args:
            prompt: The analysis prompt to execute
            workspace_dir: Directory to use as workspace (mounted in Docker)

        Raises:
            RuntimeError: If the analysis fails or times out

        """
        ...

    @abstractmethod
    def run_research(self, prompt: str, workspace_dir: Path) -> None:
        """
        Run a research task with the given prompt in the specified workspace.

        The agent should analyze the codebase and create initial context files
        (like CLAUDE.md) in the workspace directory. This runs in Docker for isolation.

        Args:
            prompt: The research prompt to execute
            workspace_dir: Directory to use as workspace (mounted in Docker)

        Raises:
            RuntimeError: If the research fails or times out

        """
        ...

    def _create_comparation_prompt(
        self, developer_solution: Solution, agent_solution: Solution
    ) -> str:
        """Create comparison prompt showing diffs between solutions."""
        diff_output = self._create_solution_diff(developer_solution, agent_solution)

        return f"""Compare these two solutions and provide detailed analysis.

## Developer's Solution Description
{developer_solution.description}

## {self.agent_name}'s Solution Description
{agent_solution.description}

## File Differences (Developer vs {self.agent_name})
{diff_output}

Analyze:
1. What patterns or approaches did the developer use that {self.agent_name} missed?
2. What are the key differences in implementation?
3. What conventions or project-specific patterns should be learned?
4. Are there any MCP servers or tools that would help?
5. What specific guidance should be added to {self.agent_file}?
Provide specific, actionable learnings.
"""

    def _create_solution_diff(
        self, developer_solution: Solution, agent_solution: Solution, context_lines: int = 5
    ) -> str:
        """Create unified diff between two solutions."""
        parts = []

        # Get all files from both solutions
        all_files = set(developer_solution.files.keys()) | set(agent_solution.files.keys())

        for filename in sorted(all_files):
            dev_content = developer_solution.files.get(filename, "")
            agent_content = agent_solution.files.get(filename, "")

            if dev_content == agent_content:
                parts.append(f"\n### {filename}\n(identical in both solutions)\n")
                continue

            # Create unified diff
            dev_lines = dev_content.splitlines(keepends=True)
            agent_lines = agent_content.splitlines(keepends=True)

            diff = difflib.unified_diff(
                agent_lines,
                dev_lines,
                fromfile=f"{self.agent_name}: {filename}",
                tofile=f"Developer: {filename}",
                n=context_lines,
            )

            diff_text = "".join(diff)
            if diff_text:
                parts.append(f"\n### {filename}\n```diff\n{diff_text}```\n")
            else:
                # Files differ but diff is empty (e.g., whitespace only)
                parts.append(f"\n### {filename}\n(minor differences, possibly whitespace)\n")

        return "".join(parts) if parts else "(no file differences found)"
