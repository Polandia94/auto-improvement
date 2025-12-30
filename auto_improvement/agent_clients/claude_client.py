"""Claude client using the Claude Agent SDK inside Docker for isolation."""

from __future__ import annotations

import json
import os
import subprocess
import typing
from pathlib import Path

from auto_improvement.agent_clients.abstract_agent import AbstractAgentClient
from auto_improvement.models import Solution

if typing.TYPE_CHECKING:
    from auto_improvement.models import AgentConfig, IssueInfo, PRInfo


# SDK runner script that will be embedded in the Docker image
SDK_RUNNER_SCRIPT = '''#!/usr/bin/env python3
"""SDK runner script for executing Claude Agent SDK inside Docker."""

import argparse
import asyncio
import json
import os
import sys

from claude_agent_sdk import ClaudeAgentOptions, query
from claude_agent_sdk.types import AssistantMessage, TextBlock


async def run_query(
    prompt: str,
    system_prompt: str | None = None,
    model: str | None = None,
    allowed_tools: list[str] | None = None,
    disallowed_tools: list[str] | None = None,
    print_output: bool = True,
    cwd: str = "/workspace",
) -> str:
    """Run a query using the Claude Agent SDK."""
    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        allowed_tools=allowed_tools or ["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
        disallowed_tools=disallowed_tools,
        permission_mode="acceptEdits",
        cwd=cwd,
    )

    if model:
        options.model = model

    output_parts = []

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    if print_output:
                        print(block.text)
                    output_parts.append(block.text)

    return "\\n".join(output_parts)


def main() -> None:
    """Main entry point for the SDK runner."""
    parser = argparse.ArgumentParser(description="Run Claude Agent SDK")
    parser.add_argument("--config", required=True, help="JSON config file path")
    args = parser.parse_args()

    # Read config from file
    with open(args.config) as f:
        config = json.load(f)

    prompt = config.get("prompt", "")
    system_prompt = config.get("system_prompt")
    model = config.get("model")
    allowed_tools = config.get("allowed_tools")
    disallowed_tools = config.get("disallowed_tools")
    print_output = config.get("print_output", True)
    cwd = config.get("cwd", "/workspace")

    try:
        asyncio.run(run_query(
            prompt=prompt,
            system_prompt=system_prompt,
            model=model,
            allowed_tools=allowed_tools,
            disallowed_tools=disallowed_tools,
            print_output=print_output,
            cwd=cwd,
        ))
    except Exception as e:
        print(f"Error running SDK: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
'''


class ClaudeClient(AbstractAgentClient):
    """Client for interacting with Claude using the Agent SDK inside Docker."""

    def __init__(self, config: AgentConfig, working_dir: Path | None = None):
        self.config = config
        self.working_dir = working_dir or Path.cwd()
        self.agent_file = "CLAUDE.md"
        self.agent_name = "Claude"
        self.code_path = "claude"

        self._ensure_docker_image()
        self._ensure_docker_auth()

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
        """Get Dockerfile content with Python, uv, and Claude Agent SDK."""
        return f"""# Docker image for running Claude Agent SDK in isolation
FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \\
    git \\
    make \\
    curl \\
    nodejs \\
    npm \\
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code CLI
RUN npm install -g @anthropic-ai/claude-code

# Install uv for fast Python package management
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Install claude-agent-sdk as root (before creating non-root user)
RUN uv pip install --system claude-agent-sdk anyio

# Create non-root user
RUN useradd -m -s /bin/bash claude && \\
    mkdir -p /workspace /app && \\
    chown -R claude:claude /workspace /app

# Switch to non-root user
USER claude
ENV PATH="/home/claude/.local/bin:$PATH"

WORKDIR /app

# Create the SDK runner script
COPY --chown=claude:claude <<'RUNNER_EOF' /app/sdk_runner.py
{SDK_RUNNER_SCRIPT}
RUNNER_EOF

RUN chmod +x /app/sdk_runner.py

# Set workspace as default working directory
WORKDIR /workspace

# Default command
ENTRYPOINT ["python", "/app/sdk_runner.py"]
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
                "--help",  # Override entrypoint temporarily
            ],
            timeout=10,
            check=False,
        )

        # Now run the actual setup-token with claude CLI
        result = subprocess.run(
            [
                "docker",
                "run",
                "-it",
                "--rm",
                "--entrypoint",
                "claude",
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
                f"docker run -it --rm --entrypoint claude "
                f"-v {claude_config}:/home/claude/.claude "
                f"{self.config.docker_image} setup-token"
            )

        print("Claude Code authenticated successfully.")

    def _build_docker_cmd(
        self,
        config_file: Path,
        workspace_dir: Path,
    ) -> list[str]:
        """Build Docker command to run the SDK runner in isolation."""
        claude_config = self._get_claude_config_dir()
        return [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{workspace_dir}:/workspace",
            "-v",
            f"{claude_config}:/home/claude/.claude",  # Persistent auth
            "-v",
            f"{config_file}:/app/config.json:ro",  # Mount config file
            "-w",
            "/workspace",
            "-e",
            f"ANTHROPIC_API_KEY={os.environ.get('ANTHROPIC_API_KEY', '')}",
            self.config.docker_image,
            "--config",
            "/app/config.json",
        ]

    def _run_sdk_in_docker(
        self,
        prompt: str,
        workspace_dir: Path,
        system_prompt: str | None = None,
        disallowed_tools: list[str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run the SDK inside Docker with the given configuration."""
        # Build SDK config
        sdk_config = {
            "prompt": prompt,
            "system_prompt": system_prompt,
            "model": self.config.model,
            "disallowed_tools": disallowed_tools,
            "print_output": True,
            "cwd": "/workspace",
        }

        # Write config to temp file in workspace (accessible in Docker)
        config_file = workspace_dir / ".sdk-config.json"
        config_file.write_text(json.dumps(sdk_config, indent=2))

        try:
            cmd = self._build_docker_cmd(config_file, workspace_dir)

            result = subprocess.run(
                cmd,
                text=True,
                timeout=3000,  # 50 minute timeout
                check=False,
            )

            return result
        finally:
            # Clean up config file
            config_file.unlink(missing_ok=True)

    @typing.override
    def generate_solution(
        self,
        pr_info: PRInfo,
        issue_info: IssueInfo | None,
        agent_md_path: Path | None = None,
    ) -> Solution:
        """Generate solution using Claude Agent SDK in Docker."""
        # Build the prompt
        prompt = self._build_implementation_prompt(pr_info, issue_info)

        # Add critical instruction to prevent looking at future git history
        system_prompt = f"""{prompt}

CRITICAL RULES:
1. DO NOT use git log, git show, git diff, or any git commands that reveal commit history
2. DO NOT look at .git/ directory contents
3. Solve the issue based ONLY on the issue description and current code state
4. The repository has been checked out to a specific point in time - treat it as the current state

Implement the solution by editing the necessary files directly."""

        # Copy agent MD file to workspace so Claude auto-reads it
        workspace_agent_md = None
        if agent_md_path and agent_md_path.exists():
            workspace_agent_md = self.working_dir / self.agent_file
            import shutil

            shutil.copy(agent_md_path, workspace_agent_md)

        try:
            # Run SDK in Docker with disallowed git history tools
            result = self._run_sdk_in_docker(
                prompt="Execute the task described in the system prompt.",
                workspace_dir=self.working_dir,
                system_prompt=system_prompt,
                disallowed_tools=["Bash(git log:*)", "Bash(git show:*)"],
            )
        finally:
            # Move agent MD back to learning dir (in case it was modified)
            if workspace_agent_md and workspace_agent_md.exists() and agent_md_path:
                import shutil

                shutil.move(workspace_agent_md, agent_md_path)

        if result.returncode != 0:
            raise RuntimeError(f"Claude SDK failed with return code {result.returncode}")

        # Detect files that Claude modified in the working directory
        changed_files = self._detect_changed_files()

        files = {}
        for file_path in changed_files:
            full_path = self.working_dir / file_path
            if full_path.exists():
                files[file_path] = full_path.read_text()

        return Solution(
            files=files,
            description=f"Solution generated by Claude SDK for PR #{pr_info.number}",
        )

    @typing.override
    def run_analysis(self, prompt: str, workspace_dir: Path) -> None:
        """Run analysis with Claude SDK in Docker for isolation."""
        try:
            result = self._run_sdk_in_docker(
                prompt="Execute the analysis described in the system prompt.",
                workspace_dir=workspace_dir,
                system_prompt=prompt,
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

    @typing.override
    def run_research(self, prompt: str, workspace_dir: Path) -> None:
        """Run research phase with Claude SDK in Docker."""
        result = self._run_sdk_in_docker(
            prompt=prompt,
            workspace_dir=workspace_dir,
            system_prompt=None,  # Prompt is self-contained for research
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"{self.agent_name} research session failed with return code {result.returncode}"
            )

    def analyze_comparison(
        self,
        developer_solution: Solution,
        claude_solution: Solution,
    ) -> None:
        """Analyze and compare two solutions, updating learning files directly."""
        prompt = self._create_comparation_prompt(developer_solution, claude_solution)
        self.run_analysis(prompt, self.working_dir)
