FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (Python + Node build tooling)
RUN apt-get update && apt-get install -y \
    git \
    curl \
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

# Install Node dependencies (needed for Tailwind plugins)
RUN npm ci

# Copy the rest of the application
COPY . .

# Set the path to include the virtual environment
ENV PATH="/app/.venv/bin:$PATH"

RUN uv run python manage.py tailwind build

RUN chmod +x /app/entrypoint.sh

CMD ["/app/entrypoint.sh"]