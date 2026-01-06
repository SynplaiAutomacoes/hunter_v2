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

# Install dependencies using uv
RUN uv sync --frozen

# Copy the rest of the application
COPY . .

# Set the path to include the virtual environment
ENV PATH="/app/.venv/bin:$PATH"

RUN chmod +x /app/entrypoint.sh

CMD ["/app/entrypoint.sh"]