# Builder container — runs Claude Code CLI against the mounted /project workspace.
# The host project directory is bind-mounted at runtime; nothing is baked in.

FROM node:20-slim

# System deps: git (required by claude-code) + ca-certificates
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code CLI globally
RUN npm install -g @anthropic-ai/claude-code

# Workspace — host project folder is mounted here at runtime
WORKDIR /project

# Default: keep the container alive so `docker exec` calls work
CMD ["tail", "-f", "/dev/null"]
