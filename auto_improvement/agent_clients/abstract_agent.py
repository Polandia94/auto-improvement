"""Agent Abstract Client."""

from __future__ import annotations

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
