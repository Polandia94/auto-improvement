# Docker image for running Claude Code in isolation
FROM node:20-slim

# Install dependencies
RUN apt-get update && apt-get install -y \
    git \
    python3 \
    python3-pip \
    python3-venv \
    make \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code CLI
RUN npm install -g @anthropic-ai/claude-code

# Create non-root user (required for --dangerously-skip-permissions)
RUN useradd -m -s /bin/bash claude && \
    mkdir -p /workspace && \
    chown -R claude:claude /workspace

# Switch to non-root user
USER claude

# Create workspace directory
WORKDIR /workspace

# Default command
ENTRYPOINT ["claude"]
