# Usa Python 3.12 (leve)
FROM python:3.12-slim

# Instala o uv dentro do container
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Define diretório de trabalho
WORKDIR /app

# Variáveis de ambiente para Python não criar arquivos .pyc e logs serem imediatos
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Instala dependências do sistema necessárias para compilar certas libs (opcional, mas bom ter)
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copia arquivos de dependência primeiro (para cache do Docker)
COPY pyproject.toml uv.lock ./

# Instala dependências do projeto no sistema do container
RUN uv sync --frozen

# Copia o resto do código
COPY . .

# Comando padrão (pode ser sobrescrito no docker-compose)
CMD ["uv", "run", "gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]