FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY pyproject.toml ./
COPY uv.lock ./

# Install uv
RUN pip install uv

# Args for GitHub authentication
ARG GITHUB_TOKEN

# Configure git to use the GitHub token
RUN if [ -n "$GITHUB_TOKEN" ]; then \
    git config --global url."https://${GITHUB_TOKEN}@github.com/".insteadOf "https://github.com/"; \
    fi

# Install dependencies using uv
RUN uv sync --frozen

# Copy the rest of the application
COPY . .

# Set the path to include the virtual environment
ENV PATH="/app/.venv/bin:$PATH"

# Comando padrão (pode ser sobrescrito no docker-compose)
CMD ["uv", "run", "gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]