FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (Python + Node build tooling)
RUN apt-get update && apt-get install -y \
  git \
  curl \
  build-essential \
  python3-dev \
  libcairo2-dev \
  pkg-config \
  && rm -rf /var/lib/apt/lists/*

# Install Node.js (LTS) + npm
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
  && apt-get update && apt-get install -y nodejs \
  && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY pyproject.toml ./
COPY uv.lock ./

# Copy Node manifests first for better caching
COPY package.json ./
COPY package-lock.json ./

# Install uv
RUN pip install uv

# Install Python dependencies
RUN uv sync --frozen

# Install Playwright browser runtime
RUN uv run playwright install --with-deps chromium

# Install Node dependencies (needed for Tailwind plugins)
RUN npm ci

# Pre-download Tailwind CLI with retries (avoids flaky GitHub downloads during manage.py build)
ARG TAILWIND_CLI_VERSION=2.8.2
RUN set -eux; \
  url="https://github.com/dobicinaitis/tailwind-cli-extra/releases/download/v${TAILWIND_CLI_VERSION}/tailwindcss-extra-linux-x64"; \
  for attempt in 1 2 3 4 5; do \
    if curl -fsSL --retry 3 --retry-delay 2 -o /usr/local/bin/tailwindcss "$url"; then \
      chmod +x /usr/local/bin/tailwindcss; \
      break; \
    fi; \
    if [ "$attempt" -eq 5 ]; then \
      echo "Failed to download Tailwind CLI after ${attempt} attempts"; \
      exit 1; \
    fi; \
    echo "Tailwind CLI download failed (attempt ${attempt}); retrying..."; \
    sleep $((attempt * 2)); \
  done

# Copy the rest of the application
COPY . .

# Set the path to include the virtual environment
ENV PATH="/app/.venv/bin:$PATH"
ENV TAILWIND_CLI_PATH=/usr/local/bin/tailwindcss

RUN uv run python manage.py tailwind build
RUN uv run python manage.py collectstatic --noinput

RUN chmod +x /app/entrypoint.sh

CMD ["/app/entrypoint.sh"]
