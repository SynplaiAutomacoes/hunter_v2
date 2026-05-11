# Configuracao do ambiente

[Voltar ao README principal](../README.md) | [Indice da documentacao](README.md) | [Anterior: Arquitetura e apps](02-arquitetura-e-apps.md) | [Proximo: Fluxo principal do sistema](04-fluxo-principal-do-sistema.md)

## Objetivo

Este documento descreve como preparar o ambiente local de desenvolvimento, quais variaveis de ambiente o projeto espera e quais comandos usar no dia a dia.

## Pre-requisitos

Instale antes de qualquer coisa:

- Python 3.11+
- `uv`
- Node.js 20+
- `npm`
- Docker / Docker Compose

### Dependencia nativa para conversao de logo SVG

O fluxo de logomarca usa `CairoSVG` para converter SVG em PNG antes de salvar no bucket e sincronizar com a Webmania. No Windows, isso exige o runtime nativo do Cairo.

Opcao recomendada no Windows:

1. instale o GTK3 Runtime ou outro pacote que forneca `libcairo-2.dll`
2. adicione a pasta `bin` desse runtime ao `PATH`
3. feche e abra o terminal novamente
4. rode `uv sync`

Exemplo comum de pasta esperada no `PATH`:

- `C:\Program Files\GTK3-Runtime Win64\bin`

Validacao rapida:

```bash
uv run python -c "import cairosvg; print('ok')"
```

Se esse comando falhar com erro sobre `libcairo-2.dll`, o runtime do Cairo ainda nao esta disponivel para o Python.

## Setup local minimo

No root do projeto:

```bash
uv sync
npm ci
docker compose up -d postgres
uv run python manage.py migrate
uv run python manage.py runserver
```

Se voce pretende subir logomarca em SVG no ambiente local, valide tambem:

```bash
uv run python -c "import cairosvg; print('cairosvg pronto')"
```

Se quiser base inicial com dados de demonstracao:

```bash
uv run python manage.py seed_demo_data
```

## Banco de dados local

O projeto usa PostgreSQL por padrao. O `docker-compose.yml` do repositorio sobe um servico `postgres` com estes defaults:

- database: `meu_crm`
- usuario: `usuario_crm`
- senha: `senha_secreta`
- porta: `5432`

Os mesmos valores aparecem como fallback em `config/settings.py`.

## Variaveis de ambiente

O projeto usa `os.getenv(...)` diretamente em `config/settings.py` e em alguns pontos pontuais do codigo. Abaixo esta o conjunto relevante para desenvolvimento e operacao.

### Django e app base

| Variavel | Uso |
| --- | --- |
| `DJANGO_SECRET_KEY` | secret key do Django |
| `DJANGO_DEBUG` | ativa/desativa modo debug |
| `DJANGO_ALLOWED_HOSTS` | hosts permitidos, separados por virgula |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | origens confiaveis para CSRF |
| `APP_BASE_URL` | URL publica usada por integracoes como webhook/assinatura |

### Banco de dados

| Variavel | Uso |
| --- | --- |
| `DB_NAME` | nome do banco |
| `DB_USER` | usuario do banco |
| `DB_PASSWORD` | senha do banco |
| `DB_HOST` | host do banco |
| `DB_PORT` | porta do banco |

### Eventos de orcamento e performance

| Variavel | Uso |
| --- | --- |
| `BUDGET_EVENTS_ENABLED` | liga eventos em tempo real do orcamento |
| `BUDGET_POLL_INTERVAL_SECONDS` | polling do budget event stream |
| `BUDGET_SSE_CHECK_INTERVAL_SECONDS` | intervalo de verificacao SSE |
| `PERF_LOGGING_ENABLED` | habilita middleware de performance |
| `PERF_LOG_QUERIES` | registra queries no log de performance |
| `PERF_LOG_MIN_MS` | threshold minimo para logar request lenta |
| `FIPE_SYNC_EVERY_ACCESS` | sincroniza catalogo FIPE em todo acesso relevante de cadastro de veiculo |
| `FIPE_SYNC_ACCESS_INTERVAL` | sincroniza catalogo FIPE a cada N acessos relevantes quando o modo sempre ativo estiver desligado |
| `FIPE_FUEL_CACHE_TTL_HOURS` | validade do cache local de combustiveis por modelo |
| `FIPE_DEV_MODE` | em ambiente local/desenvolvimento evita sync completo e atualiza apenas a marca selecionada sob demanda |
| `FIPE_API_TOKEN` | token dedicado para chamadas da API FIPE |

### Webmania

| Variavel | Uso |
| --- | --- |
| `WEBMANIA_AMBIENT` | ambiente da Webmania (`1` prod, `2` homolog) |
| `WEBMANIA_API_KEY` | credencial principal |
| `WEBMANIA_CONSUMER_KEY` | credencial principal |
| `WEBMANIA_CONSUMER_SECRET` | credencial principal |
| `WEBMANIA_ACCESS_TOKEN` | credencial principal |
| `WEBMANIA_ACCESS_TOKEN_SECRET` | credencial principal |
| `WEBMANIA_B2B_CONSUMER_KEY` | credencial B2B |
| `WEBMANIA_B2B_CONSUMER_SECRET` | credencial B2B |
| `WEBMANIA_B2B_ACCESS_TOKEN` | credencial B2B |
| `WEBMANIA_B2B_ACCESS_TOKEN_SECRET` | credencial B2B |
| `WEBMANIA_WEBHOOK_TOKEN` | token base para autenticacao de webhook |

### SuperSign

| Variavel | Uso |
| --- | --- |
| `SUPERSIGN_BASE_URL` | URL base da API |
| `SUPERSIGN_ACCOUNT_ID` | conta do provedor |
| `SUPERSIGN_API_KEY` | chave de integracao |
| `SUPERSIGN_FOLDER_ID` | pasta/container de documentos |

### Storage Bucket S3 compativel

| Variavel | Uso |
| --- | --- |
| `ACCESS_KEY_ID` | chave de acesso do bucket |
| `SECRET_ACCESS_KEY` | segredo do bucket |
| `BUCKET` | nome do bucket |
| `ENDPOINT` | endpoint S3 compativel |
| `REGION` | regiao do bucket, normalmente `auto` |

### Seguranca e log em producao

| Variavel | Uso |
| --- | --- |
| `DJANGO_SECURE_SSL_REDIRECT` | redirect HTTPS em producao |
| `DJANGO_SECURE_HSTS_SECONDS` | HSTS |
| `DJANGO_LOG_LEVEL` | nivel de log de loggers especificos |
| `DJANGO_ROOT_LOG_LEVEL` | nivel do root logger |

### Variavel extra fora de `settings.py`

| Variavel | Uso |
| --- | --- |
| `token_vehicle_api` | token usado no fluxo legado de consulta por placa em `apps/customer/util.py` |

## Exemplo de `.env`

Use os valores reais do seu ambiente. O bloco abaixo e apenas um esqueleto seguro para onboarding:

```dotenv
DJANGO_SECRET_KEY=dev-only-secret
DJANGO_DEBUG=1
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:8000
APP_BASE_URL=http://localhost:8000

DB_NAME=meu_crm
DB_USER=usuario_crm
DB_PASSWORD=senha_secreta
DB_HOST=localhost
DB_PORT=5432

BUDGET_EVENTS_ENABLED=0
BUDGET_POLL_INTERVAL_SECONDS=20
BUDGET_SSE_CHECK_INTERVAL_SECONDS=3

PERF_LOGGING_ENABLED=0
PERF_LOG_QUERIES=0
PERF_LOG_MIN_MS=300

FIPE_SYNC_EVERY_ACCESS=0
FIPE_SYNC_ACCESS_INTERVAL=500
FIPE_FUEL_CACHE_TTL_HOURS=168
FIPE_DEV_MODE=0
FIPE_API_TOKEN=

WEBMANIA_AMBIENT=2
WEBMANIA_API_KEY=
WEBMANIA_CONSUMER_KEY=
WEBMANIA_CONSUMER_SECRET=
WEBMANIA_ACCESS_TOKEN=
WEBMANIA_ACCESS_TOKEN_SECRET=
WEBMANIA_B2B_CONSUMER_KEY=
WEBMANIA_B2B_CONSUMER_SECRET=
WEBMANIA_B2B_ACCESS_TOKEN=
WEBMANIA_B2B_ACCESS_TOKEN_SECRET=
WEBMANIA_WEBHOOK_TOKEN=

SUPERSIGN_BASE_URL=https://api.sign.supersign.com.br
SUPERSIGN_ACCOUNT_ID=
SUPERSIGN_API_KEY=
SUPERSIGN_FOLDER_ID=

ACCESS_KEY_ID=
SECRET_ACCESS_KEY=
BUCKET=
ENDPOINT=https://storage.railway.app
REGION=auto

DJANGO_LOG_LEVEL=DEBUG
DJANGO_ROOT_LOG_LEVEL=DEBUG

token_vehicle_api=
```

## Carregando o `.env`

Antes de subir a aplicacao, garanta que as variaveis definidas no seu `.env` estejam exportadas na sessao atual do terminal ou carregadas pelo fluxo padrao adotado pela equipe no ambiente local.

## Build de assets

Para gerar Tailwind localmente:

```bash
uv run python manage.py tailwind build
```

Se precisar forcar rebuild:

```bash
uv run python manage.py tailwind build --force
```

## Testes e qualidade

### Testes

```bash
uv run python manage.py test
uv run python manage.py test apps.finance
uv run python manage.py test apps.core.tests
```

### Lint, format e tipos

```bash
uv run ruff check .
uv run ruff format .
uv run mypy .
```

## Problemas comuns

### Nao conecta no PostgreSQL

- confirme que o container `postgres` esta rodando
- confira `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER` e `DB_PASSWORD`
- lembre que o fallback do projeto assume `localhost:5432`

### Webhook/assinatura nao funciona localmente

- `APP_BASE_URL` precisa apontar para uma URL acessivel pelo provedor externo
- em desenvolvimento local, normalmente isso exige um tunel publico como ngrok
- o comando `manage.py webhook` sincroniza o endpoint da SuperSign

### Funcionalidade fiscal nao sobe

- confirme credenciais Webmania
- confirme certificado e senha da oficina
- confirme `ACCESS_KEY_ID`, `SECRET_ACCESS_KEY`, `BUCKET` e `ENDPOINT`

### CSS nao reflete mudancas

- rode `uv run python manage.py tailwind build`
- se necessario use `--force`

## Sequencia recomendada para um novo dev

1. Subir PostgreSQL local.
2. Configurar `.env` com o minimo necessario.
3. Rodar `uv sync` e `npm ci`.
4. Aplicar migrations.
5. Rodar `seed_demo_data` se precisar navegar em fluxo real.
6. Subir `runserver`.
7. Ler [Fluxo principal do sistema](04-fluxo-principal-do-sistema.md) para nao entrar no dominio sem contexto.

[Anterior: Arquitetura e apps](02-arquitetura-e-apps.md) | [Indice da documentacao](README.md) | [Proximo: Fluxo principal do sistema](04-fluxo-principal-do-sistema.md) | [Voltar ao README principal](../README.md)
