FROM python:3.11-slim

WORKDIR /app

# Force Python to flush stdout/stderr immediately (fixes log visibility in Docker)
ENV PYTHONUNBUFFERED=1

# Install system dependencies for PDF parsing, gosu for privilege dropping, and curl for Node.js
RUN apt-get update && apt-get install -y gcc gosu curl && rm -rf /var/lib/apt/lists/*

# Install Node.js 20 for Claude Code CLI
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

# Install Claude Code CLI globally
RUN npm install -g @anthropic-ai/claude-code

# Create user matching the host user (UID 1002 = homelab)
RUN groupadd -g 1002 appuser && useradd -u 1002 -g appuser -m appuser

# Copy requirements first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Copy and set up entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Expose Flask port
EXPOSE 5000

# Run entrypoint as root (it will drop to appuser after fixing permissions)
ENTRYPOINT ["/entrypoint.sh"]
