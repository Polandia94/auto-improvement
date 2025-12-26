# Installation Guide

## Prerequisites

- Python 3.12 or higher
- Git

## Install Auto-Improvement

### Install with UV (Recommended)

```bash
# Install UV if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and install
git clone https://github.com/polandia94/auto-improvement.git
cd auto-improvement
uv pip install -e .

# Verify installation
auto-improve version
```

### Install with pip

```bash
# Clone the repository
git clone https://github.com/polandia94/auto-improvement.git
cd auto-improvement

pip install -e .

# Verify installation
auto-improve version
```

### Development Install

To install with development dependencies:

```bash
# Install with dev extras
uv pip install -e ".[dev]"

# Now you can run tests, linting, etc.
make test     # Run tests
make format   # Format code with ruff
make check    # Run linting and type checking
```

## Optional: Claude Code CLI

For the best experience, install Claude Code CLI:

```bash
# Install Claude Code
npm install -g @anthropic-ai/claude-code

# Verify
claude --version

# Authenticate (follow the prompts)
claude
```

## Environment Variables

Set up your environment:

```bash

# For GitHub (optional, but recommended)
export GITHUB_TOKEN=ghp_your-token-here
```

Add to your shell profile (~/.bashrc, ~/.zshrc, etc.):

```bash
echo 'export GITHUB_TOKEN=ghp_your-token' >> ~/.zshrc
```

## Verify Installation

```bash
# Check version
auto-improve version

# Try help
auto-improve --help

# Run a test
auto-improve init --repo django/django --name Django --tracker trac
```

## Update

To update to the latest version:

```bash
cd auto-improvement
git pull
uv pip install -e . --upgrade
```

## Uninstall

```bash
uv pip uninstall auto-improvement
```

## Troubleshooting

### UV Not Found

If `uv` command is not found after installation:

```bash
# Add to PATH
export PATH="$HOME/.cargo/bin:$PATH"

# Or source your shell config
source ~/.zshrc  # or ~/.bashrc
```

### Permission Errors

If you get permission errors:

```bash
# Use --user flag
uv pip install -e . --user
```

### Import Errors

If imports fail:

```bash
# Reinstall dependencies
uv pip install -e . --force-reinstall
```

### Claude Code Not Found

```bash
# Check if installed
which claude

# If not found, install
npm install -g @anthropic-ai/claude-code
```


## Next Steps

After installation:

1. Read the [README.md](README.md) for quick start guide
2. Try the Django example in [examples/](examples/)
3. Configure for your project
