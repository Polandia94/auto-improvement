# Auto-Improvement

A meta-learning system that improves AI coding assistants by learning from real-world Pull Requests.

## How It Works

1. **Research Phase**: Analyzes repository README, issues, and PRs to build initial context
2. **Time Travel**: Checks out code before a merged PR
3. **Challenge**: Asks the AI agent to implement the solution
4. **Compare**: Compares AI solution with actual developer solution
5. **Learn**: Updates context file with learnings and patterns
6. **Iterate**: Repeats with more PRs until performance improves

## Key Features

### 🔧 Fully Configurable

This are the current capabilities.

**PR Source** (where code is hosted):
- ✅ GitHub (tested)

**Issue Tracker** (where issues are tracked):
- ✅ GitHub Issues (not tested)
- ✅ Trac (e.g., Django, Python) (tested)
- ✅ Jira (Not tested)

**AI Agent** (which LLM to use):
- ✅ Claude Code (Tested)

### 🤖 Intelligent Comparison & Learning

Uses the AI itself to:
- Compare solutions intelligently
- Extract meaningful patterns
- Organize learnings naturally
- Suggest tools and improvements

## Installation


### Manual Install

```bash
# Install UV
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install package
uv pip install -e .

# Verify
auto-improve version
```

See [INSTALL.md](INSTALL.md) for detailed installation instructions.

## Quick Start

### Command Line

```bash
# Initialize configuration for any project
auto-improve init \
  --repo owner/repo \
  --name "Project Name" \
  --tracker github

# Run improvement cycle
auto-improve run \
  --repo owner/repo \
  --config config.yaml \
  --max-prs 5

# Process specific PR
auto-improve run-pr \
  --repo owner/repo \
  --pr 12345 \
  --config config.yaml
```

### Python API

```python
from auto_improvement import AutoImprovement

# Initialize
improver = AutoImprovement(
    repo_path="owner/repo",
    config_path="config.yaml"
)

# Run improvement cycle
results = improver.run_improvement_cycle(max_iterations=5)

# Check results
print(f"Success rate: {results.successful_prs}/{results.total_prs}")
print(f"Average score: {results.average_score:.1%}")
```

## Configuration

Create a YAML configuration file:

```yaml
# Project configuration
project:
  name: "Your Project"
  repo: "owner/repo"  # GitHub repository

# Issue tracker configuration (top-level, not nested under project)
issue_tracker:
  url: "https://github.com/owner/repo/issues"

# PR Selection Criteria
pr_selection:
  merged: true
  has_linked_issue: true
  min_files_changed: 1
  max_files_changed: 20
  days_back: 90
  exclude_labels:
    - "dependencies"
    - "automated"

# Learning Configuration
learning:
  max_attempts_per_pr: 3
  success_threshold: 0.8
  max_prs_per_session: 10

# AI Agent Configuration
agent_config:
  code_path: "claude"  # Path to Claude Code CLI

# Optional: Custom prompts
prompts:
  analysis: null  # Use intelligent default unified analysis prompt
```

## Examples

### Example 1: GitHub Project with GitHub Issues

```bash
auto-improve init \
  --repo rails/rails \
  --name Rails \
  --tracker github

auto-improve run --repo rails/rails --config auto-improve-config.yaml
```

### Example 2: GitHub Project with Trac Issues

See [examples/django_config.yaml](examples/django_config.yaml) for Django configuration.

```bash
auto-improve run \
  --repo django/django \
  --config examples/django_config.yaml \
  --max-prs 5
```

### Example 3: Using API Mode

Configure API mode in your config.yaml:

```yaml
agent_config:
  model: "claude-sonnet-4-5-20250929"
  api_key: "sk-ant-..."  # Or set ANTHROPIC_API_KEY env var
```

Then run normally:

```bash
export ANTHROPIC_API_KEY=sk-ant-your-key

auto-improve run \
  --repo owner/repo \
  --config config.yaml
```

## Architecture

### Extensibility Points

The system is designed to be easily extended:

#### 1. **PR Source** ([version_control_clients/github_client.py](auto_improvement/version_control_clients/github_client.py))
```python
# Add new PR source (GitLab, Bitbucket, etc.)
class GitLabClient:
    def get_merged_prs(self, repo, criteria) -> list[PRInfo]:
        # Fetch from GitLab API
        ...
```

#### 2. **Issue Tracker** ([issues_tracker_clients/](auto_improvement/issues_tracker_clients/))
```python
# Add new issue tracker (Linear, Azure DevOps, etc.)
class LinearClient(AbstractIssueTrackerClient):
    def get_issue(self, issue_id: str) -> IssueInfo | None:
        # Fetch from Linear API
        ...
```

#### 3. **AI Agent** ([agent_clients/claude_client.py](auto_improvement/agent_clients/claude_client.py))
```python
# Add new LLM provider (GPT-4, Gemini, etc.)
class GPT4Client(AbstractAgentClient):
    def generate_solution(self, pr_info, issue_info, context) -> Solution:
        # Use OpenAI API
        ...
```

### Component Overview

```
┌─────────────────┐
│   CLI / API     │  Entry point
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│ AutoImprovement │  Main orchestrator
└────────┬────────┘
         │
         ├──→ GitHubClient      (PR source - extensible)
         ├──→ IssueTracker      (Issue source - extensible)
         ├──→ GitManager        (Git operations)
         ├──→ ClaudeClient      (AI agent - extensible)
         └──→ UnifiedAnalyzer   (Uses AI to compare & learn)
```

## Supported Configurations

| Component | Supported | Notes |
|-----------|-----------|-------|
| **PR Source** | GitHub | Extensible to GitLab, Bitbucket |
| **Issue Tracker** | GitHub, Trac, Jira | Extensible to Linear, Azure DevOps |
| **AI Agent** | Claude Code, Claude API | Extensible to GPT-4, Gemini, etc. |
| **VCS** | Git | Core requirement |

## Use Cases

### 1. Learning from Open Source Projects
```bash
# Learn from any GitHub project
auto-improve init --repo facebook/react --name React --tracker github
auto-improve run --repo facebook/react --config react-config.yaml
```

### 2. Enterprise Projects with Jira
```yaml
project:
  issue_tracker:
    type: "jira"
    url: "https://company.atlassian.net"
    auth:
      email: "you@company.com"
      api_token: "your-token"
```

### 3. Python Projects with Trac
```yaml
project:
  issue_tracker:
    type: "trac"
    url: "https://bugs.python.org"
```

## Environment Variables

```bash
# For Claude API mode
export ANTHROPIC_API_KEY=sk-ant-your-key

# For GitHub (optional, increases rate limits)
export GITHUB_TOKEN=ghp_your-token

# For Jira (alternative to config)
export JIRA_EMAIL=you@company.com
export JIRA_API_TOKEN=your-token
```

## Documentation

- [INSTALL.md](INSTALL.md) - Installation guide

## Examples Directory

- [examples/django_config.yaml](examples/django_config.yaml) - Django with Trac
- [examples/django_github_issues.yaml](examples/django_github_issues.yaml) - Django with GitHub
- [examples/example_usage.py](examples/example_usage.py) - Python API examples

## Development

```bash
# Install with dev dependencies
uv pip install -e ".[dev]"

# Format code
make format

# Run linting
make lint

# Run type checking
make typecheck

# Run all checks
make check
```

## Roadmap


## Contributing

Contributions welcome! Priority areas:
1. New PR sources (GitLab, Bitbucket)
2. New issue trackers (Linear, Azure DevOps)
3. New AI agents (GPT-4, Gemini)
4. Better comparison metrics
5. Documentation improvements

## License

MIT - See [LICENSE](LICENSE)

## Credits

Built with:
- [UV](https://github.com/astral-sh/uv) - Fast Python package installer
- [Ruff](https://github.com/astral-sh/ruff) - Fast Python linter
- [Claude](https://anthropic.com/claude) - AI coding assistant
- [Pydantic](https://pydantic.dev/) - Data validation
- [Rich](https://github.com/Textualize/rich) - Terminal formatting
- [Typer](https://typer.tiangolo.com/) - CLI framework
