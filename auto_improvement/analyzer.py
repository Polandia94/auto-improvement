"""Unified analyzer that compares solutions and updates all learning files."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from auto_improvement.agent_clients.abstract_agent import AbstractAgentClient
    from auto_improvement.models import PRInfo, Solution


class UnifiedAnalyzer:
    """
    Analyzes solutions and updates all learning files in one pass.

    Runs Claude interactively to:
    1. Compare developer vs AI solution
    2. Extract learnings and patterns
    3. Update learning files directly:
       - CLAUDE.md: Context and patterns
       - skills/: Techniques learned
       - mcp_suggestions.md: MCP servers to add
       - suggestions.md: Insights for developer
    """

    def __init__(
        self,
        agent_client: AbstractAgentClient,
        local_path: Path,
        analysis_prompt: str | None = None,
    ) -> None:
        """
        Initialize the analyzer.

        Args:
            agent_client: AI agent client for analysis
            local_path: Directory containing all learning files
            analysis_prompt: Optional custom prompt for analysis

        """
        self.agent_client = agent_client
        self.learning_dir = local_path
        self.learning_dir.mkdir(parents=True, exist_ok=True)

        # Initialize learning files - use agent_file from client
        self.agent_md_path = local_path / agent_client.agent_file
        self.skills_dir = local_path / "skills"
        self.mcp_suggestions_path = local_path / "mcp_suggestions.md"
        self.suggestions_path = local_path / "suggestions.md"

        self.analysis_prompt = analysis_prompt or self._default_analysis_prompt()

    def _initialize_files(self) -> None:
        """Initialize learning files if they don't exist."""
        self.skills_dir.mkdir(parents=True, exist_ok=True)

        if not self.mcp_suggestions_path.exists():
            self.mcp_suggestions_path.write_text(self._initial_mcp_suggestions())

        if not self.suggestions_path.exists():
            self.suggestions_path.write_text(self._initial_suggestions())

    def analyze_and_learn(
        self,
        developer_solution: Solution,
        agent_solution: Solution,
        pr_info: PRInfo,
    ) -> None:
        """
        Analyze solutions and update all learning files.

        Claude runs interactively and edits the learning files directly.

        Args:
            developer_solution: The actual developer's solution
            agent_solution: AI agent's attempted solution
            pr_info: PR information

        """
        # Read current state of files for context
        current_agent_md = self.agent_md_path.read_text() if self.agent_md_path.exists() else ""
        current_skills = self._get_current_skills_summary()
        current_mcp = self.mcp_suggestions_path.read_text()

        # Format solutions for comparison
        dev_solution_text = self._format_solution(developer_solution, "Developer")
        agent_solution_text = self._format_solution(agent_solution, self.agent_client.agent_name)

        # Build prompt
        prompt = self.analysis_prompt.format(
            pr_number=pr_info.number,
            pr_title=pr_info.title,
            pr_description=pr_info.description or "No description",
            issue_description=(
                pr_info.linked_issue.description if pr_info.linked_issue else "No linked issue"
            ),
            developer_solution=dev_solution_text,
            agent_solution=agent_solution_text,
            current_agent_md=current_agent_md,
            current_skills=current_skills,
            current_mcp=current_mcp,
            agent_name=self.agent_client.agent_name,
            agent_file=self.agent_client.agent_file,
        )

        # Run the agent interactively - it will edit files directly
        self.agent_client.run_analysis(prompt, self.learning_dir)

    def _format_solution(self, solution: Solution, label: str) -> str:
        """Format a solution for display in prompt."""
        lines = [f"## {label} Solution\n"]
        lines.append(f"**Description:** {solution.description}\n")

        if solution.reasoning:
            lines.append(f"**Reasoning:** {solution.reasoning}\n")

        lines.append("\n**Files Changed:**\n")
        for filename, content in solution.files.items():
            lines.append(f"\n### {filename}\n```\n{content}\n```\n")

        return "\n".join(lines)

    def _default_analysis_prompt(self) -> str:
        """Default prompt for analysis."""
        return """You are analyzing an AI coding assistant's attempt to solve a real-world PR.

# Context

**PR #{pr_number}:** {pr_title}

{pr_description}

**Linked Issue:**
{issue_description}

# Solutions to Compare

{developer_solution}

{agent_solution}

# Current Learning State

## Current {agent_file}
{current_agent_md}

## Current Skills
{current_skills}

## Current MCP Suggestions
{current_mcp}

# Your Task

Analyze the differences between the developer's solution and {agent_name}'s attempt.
Update the learning files to capture what {agent_name} can learn:

### {agent_file}
- Update with project patterns, conventions, and architectural decisions that help YOU ({agent_name}) generate better code
- Include coding style, naming conventions, common patterns, test approaches
- Keep it concise
- Only update if you learned something new

### skills/<skill-name>/SKILL.md
- Create new skills for significant techniques learned
- Use Anthropic Skills format with YAML frontmatter

### mcp_suggestions.md
- Suggest MCP servers/tools that would help
- Only update if you have new suggestions

### suggestions.md
- ONLY for ACTIONABLE insights that benefit the HUMAN DEVELOPER, NOT lessons for {agent_name}
- Examples of what TO add: refactoring opportunities, tech debt to address, potential bugs found, security concerns, performance improvements the developer could make
- Examples of what NOT to add: patterns you learned, conventions you noticed, architectural decisions (those go in {agent_file})
- APPEND only (never replace existing content)
- Skip entirely if you have no actionable developer-focused insights

Focus on patterns, not just differences. Learn from what the developer did that {agent_name} missed.
"""

    def _get_current_skills_summary(self) -> str:
        """Get summary of all current skills."""
        if not self.skills_dir.exists() or not list(self.skills_dir.iterdir()):
            return "(No skills learned yet)"

        skills_summary = []
        for skill_folder in sorted(self.skills_dir.iterdir()):
            if skill_folder.is_dir():
                skill_file = skill_folder / "SKILL.md"
                if skill_file.exists():
                    content = skill_file.read_text()
                    skills_summary.append(f"### {skill_folder.name}\n{content[:500]}...\n")

        return "\n".join(skills_summary) if skills_summary else "(No skills learned yet)"

    def _initial_mcp_suggestions(self) -> str:
        """Initial mcp_suggestions.md content."""
        return """# MCP Server Suggestions

This file tracks suggestions for MCP servers that would improve the AI's capabilities.

## Suggested MCP Servers

(To be identified)

## Reasons

(To be documented)
"""

    def _initial_suggestions(self) -> str:
        """Initial suggestions.md content."""
        return """# Developer Suggestions

Actionable insights for human developers discovered during AI code analysis.
Contains: refactoring opportunities, tech debt, potential bugs, security concerns, performance improvements.

NOT for: AI learning notes, patterns, or conventions (those go in CLAUDE.md).

---
"""
