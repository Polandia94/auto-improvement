"""Claude client supporting both Claude Code CLI and Claude API."""

from __future__ import annotations

import os
import subprocess
import typing
from pathlib import Path

from auto_improvement.agent_clients.abstract_agent import AbstractAgentClient
from auto_improvement.models import Solution

if typing.TYPE_CHECKING:
    from auto_improvement.models import AgentConfig, IssueInfo, PRInfo


class ClaudeClient(AbstractAgentClient):
    """Client for interacting with Claude code"""

    def __init__(self, config: AgentConfig, working_dir: Path | None = None):
        self.config = config
        self.working_dir = working_dir or Path.cwd()
        self.agent_file = "CLAUDE.md"
        self.agent_name = "Claude"
        self.code_path = "claude"

        self._ensure_docker_image()
        self._ensure_docker_auth()
        self._verify_claude_code()

    def _ensure_docker_image(self) -> None:
        """Ensure the Docker sandbox image exists, build if needed."""
        # Check if image exists
        result = subprocess.run(
            ["docker", "images", "-q", self.config.docker_image],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

        if result.stdout.strip():
            return  # Image exists

        # Image doesn't exist, build it
        print(f"Building Docker sandbox image '{self.config.docker_image}'...")

        # Get Dockerfile from package resources
        dockerfile_content = self._get_dockerfile_content()

        # Build image using stdin
        result = subprocess.run(
            ["docker", "build", "-t", self.config.docker_image, "-"],
            input=dockerfile_content,
            capture_output=True,
            text=True,
            timeout=600,  # 10 minutes for build
            check=False,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to build Docker image: {result.stderr}\n"
                "You can manually build: docker build -t auto-improve-sandbox ."
            )

        print(f"Docker image '{self.config.docker_image}' built successfully.")

    def _get_dockerfile_content(self) -> str:
        """Get Dockerfile content from package resources."""
        return """# Docker image for running Claude Code in isolation
FROM node:20-slim

# Install dependencies
RUN apt-get update && apt-get install -y \\
    git \\
    python3 \\
    python3-pip \\
    python3-venv \\
    make \\
    curl \\
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code CLI
RUN npm install -g @anthropic-ai/claude-code

# Create non-root user (required for --dangerously-skip-permissions)
RUN useradd -m -s /bin/bash claude && \\
    mkdir -p /workspace && \\
    chown -R claude:claude /workspace

# Switch to non-root user
USER claude

# Create workspace directory
WORKDIR /workspace

# Default command
ENTRYPOINT ["claude"]
"""

    def _get_claude_config_dir(self) -> Path:
        """Get the persistent Claude config directory for Docker."""
        config_dir = Path.home() / ".auto-improve" / "claude-config"
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir

    def _ensure_docker_auth(self) -> None:
        """Ensure Claude is authenticated in Docker, run setup-token if needed."""
        claude_config = self._get_claude_config_dir()

        # Check if already authenticated (credentials file exists)
        if (claude_config / ".credentials.json").exists():
            return  # Already configured

        print("Claude Code authentication required in Docker container.")
        print("Running 'claude setup-token' - please follow the prompts...")

        # Run setup-token interactively
        result = subprocess.run(
            [
                "docker",
                "run",
                "-it",
                "--rm",
                "-v",
                f"{claude_config}:/home/claude/.claude",
                self.config.docker_image,
                "setup-token",
            ],
            timeout=300,  # 5 minutes for auth
            check=False,
        )

        if result.returncode != 0:
            raise RuntimeError(
                "Failed to authenticate Claude Code. Please run:\n"
                f"docker run -it --rm -v {claude_config}:/home/claude/.claude "
                f"{self.config.docker_image} setup-token"
            )

        print("Claude Code authenticated successfully.")

    def _build_docker_cmd(self, claude_args: list[str], workspace_dir: Path) -> list[str]:
        """Build Docker command to run Claude in isolation."""
        claude_config = self._get_claude_config_dir()
        return [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{workspace_dir}:/workspace",
            "-v",
            f"{claude_config}:/home/claude/.claude",  # Persistent auth
            "-w",
            "/workspace",
            "-e",
            f"ANTHROPIC_API_KEY={os.environ.get('ANTHROPIC_API_KEY', '')}",
            self.config.docker_image,
            *claude_args,
        ]

    def _verify_claude_code(self) -> None:
        """Verify Claude Code CLI is available."""
        try:
            result = subprocess.run(
                [self.config.code_path, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError(f"Claude Code CLI not working: {result.stderr}")
        except FileNotFoundError as err:
            raise RuntimeError(
                f"Claude Code CLI not found at '{self.config.code_path}'. "
                "Install it from: https://github.com/anthropics/claude-code"
            ) from err
        except subprocess.TimeoutExpired as err:
            raise RuntimeError("Claude Code CLI timed out") from err

    @typing.override
    def generate_solution(
        self,
        pr_info: PRInfo,
        issue_info: IssueInfo | None,
        context: dict[str, str],
        agent_md_path: Path | None = None,
    ) -> Solution:
        """Generate solution using Claude Code CLI."""
        # Build the prompt
        prompt = self._build_implementation_prompt(pr_info, issue_info, context)

        # Add critical instruction to prevent looking at future git history
        full_prompt = f"""{prompt}

CRITICAL RULES:
1. DO NOT use git log, git show, git diff, or any git commands that reveal commit history
2. DO NOT look at .git/ directory contents
3. Solve the issue based ONLY on the issue description and current code state
4. The repository has been checked out to a specific point in time - treat it as the current state

Implement the solution by editing the necessary files directly."""

        # Build command - either Docker or local
        extra_args = [
            "--disallowedTools",
            "Bash(git log:*)",
            "Bash(git show:*)",
        ]

        # Write prompt to temp file in working directory (accessible in Docker)
        prompt_file = self.working_dir / ".claude-prompt.txt"
        prompt_file.write_text(full_prompt)

        try:
            # Docker mode: full isolation with dangerously-skip-permissions
            claude_args = [
                self.config.code_path,
                "--print",
                "--dangerously-skip-permissions",
                "--system-prompt-file",
                "/workspace/.claude-prompt.txt",
                "Execute the task described in the system prompt.",
            ]
            if self.config.model:
                claude_args.extend(["--model", self.config.model])
            claude_args.extend(extra_args)
            cmd = self._build_docker_cmd(claude_args, self.working_dir)

            # Run Claude Code in Docker - exits automatically after completion
            result = subprocess.run(
                cmd,
                text=True,
                timeout=3000,  # 50 minute timeout
                check=False,
            )
        finally:
            # Clean up prompt file
            prompt_file.unlink(missing_ok=True)

        if result.returncode != 0:
            raise RuntimeError(f"Claude Code failed with return code {result.returncode}")

        # Detect files that Claude modified in the working directory
        changed_files = self._detect_changed_files()

        files = {}
        for file_path in changed_files:
            full_path = self.working_dir / file_path
            if full_path.exists():
                files[file_path] = full_path.read_text()

        return Solution(
            files=files,
            description=f"Solution generated by Claude Code for PR #{pr_info.number}",
        )

    def analyze_comparison(
        self,
        developer_solution: Solution,
        agent_solution: Solution,
        agent_md_content: str | None = None,
    ) -> None:
        """Use Claude to analyze the comparison and update CLAUDE.md directly."""
        prompt = self._create_comparation_prompt(developer_solution, agent_solution)

        # If agent_md_content is provided, include it in the prompt
        if agent_md_content:
            prompt = f"## Current Context\n\n{agent_md_content}\n\n{prompt}"

        # Write prompt to temp file in working directory (accessible in Docker)
        prompt_file = self.working_dir / ".claude-prompt.txt"
        prompt_file.write_text(prompt)

        try:
            # Build Claude command - runs in Docker for isolation
            claude_args = [
                self.config.code_path,
                "--print",  # Print response and exit automatically
                "--dangerously-skip-permissions",  # Safe because running in Docker
                "--system-prompt-file",
                "/workspace/.claude-prompt.txt",
                "Execute the analysis described in the system prompt.",
            ]

            if self.config.model:
                claude_args.extend(["--model", self.config.model])

            # Wrap in Docker for isolation
            cmd = self._build_docker_cmd(claude_args, self.working_dir)

            result = subprocess.run(
                cmd,
                text=True,
                timeout=300,  # 5 minute timeout
                check=False,
            )
        finally:
            # Clean up prompt file
            prompt_file.unlink(missing_ok=True)

        if result.returncode != 0:
            raise RuntimeError(f"Code analysis failed with return code {result.returncode}")

    @typing.override
    def run_analysis(self, prompt: str, workspace_dir: Path) -> None:
        """Run analysis with a prompt in Docker for isolation."""
        # Write prompt to temp file in workspace directory (accessible in Docker)
        prompt_file = workspace_dir / ".claude-prompt.txt"
        prompt_file.write_text(prompt)

        try:
            # Build Claude command - runs in Docker for isolation
            claude_args = [
                self.config.code_path,
                "--print",  # Print response and exit automatically
                "--dangerously-skip-permissions",  # Safe because running in Docker
                "--system-prompt-file",
                "/workspace/.claude-prompt.txt",
                "Execute the analysis described in the system prompt.",
            ]

            if self.config.model:
                claude_args.extend(["--model", self.config.model])

            # Wrap in Docker for isolation
            cmd = self._build_docker_cmd(claude_args, workspace_dir)

            result = subprocess.run(
                cmd,
                text=True,
                timeout=3000,  # 50 minute timeout
                check=False,
            )

            if result.returncode != 0:
                raise RuntimeError(
                    f"{self.agent_name} analysis failed with return code {result.returncode}"
                )

        except subprocess.TimeoutExpired as err:
            raise RuntimeError(f"{self.agent_name} analysis timed out") from err
        except RuntimeError:
            raise
        except Exception as err:
            raise RuntimeError(f"Failed to run {self.agent_name}: {err}") from err
        finally:
            # Clean up prompt file
            prompt_file.unlink(missing_ok=True)
