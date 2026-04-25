# Deploy, build e operacao

[Voltar ao README principal](../README.md) | [Indice da documentacao](README.md) | [Anterior: Fiscal, NFe/NFSe e Webmania](09-fiscal-nfe-nfse-e-webmania.md) | [Proximo: Glossario](11-glossario.md)

## Modelo atual de deploy

O repositorio esta preparado para deploy via Docker, com indicacao explicita de uso na Railway.

Arquivos-chave:

- `Dockerfile`
- `entrypoint.sh`
- `railway.toml`

## O que o Dockerfile faz

Em alto nivel, o `Dockerfile`:

1. usa `python:3.11-slim`
2. instala dependencias de sistema
3. instala Node.js 20 e `npm`
4. copia manifests Python e Node para aproveitar cache
5. instala `uv`
6. roda `uv sync --frozen`
7. instala runtime do Playwright
8. roda `npm ci`
9. copia o restante da aplicacao
10. executa build do Tailwind
11. executa `collectstatic`
12. prepara permissao de execucao do `entrypoint.sh`

Esse pipeline deixa claro que o build de frontend e o preparo de assets fazem parte do build de imagem, nao de um passo separado de CI apenas.

## Cairo no deploy

O deploy ja instala dependencias nativas do Cairo no `Dockerfile`, o que e necessario para conversao de logomarca SVG em PNG no backend.

Trecho relevante:

- `libcairo2-dev`
- `pkg-config`

Se a aplicacao passar a falhar em conversao de SVG no ambiente remoto, revise primeiro se a imagem publicada foi rebuildada a partir do `Dockerfile` mais recente.

## Startup do container

`entrypoint.sh` executa esta sequencia:

1. sincroniza o webhook de assinatura com `manage.py webhook`
2. aplica migrations com `manage.py migrate --noinput`
3. sobe Gunicorn em `0.0.0.0:8000`

Isso tem algumas implicacoes:

- o startup depende de banco acessivel
- o startup depende das credenciais necessarias para sincronizar webhook, se o fluxo estiver habilitado
- migrations fazem parte da subida da aplicacao

## Railway

`railway.toml` informa:

- builder `DOCKERFILE`
- uso do `Dockerfile` do projeto
- politica de restart em falha
- timeout de healthcheck estendido

## Static files

O projeto usa WhiteNoise e `CompressedManifestStaticFilesStorage`. Em termos operacionais, isso significa:

- `collectstatic` e obrigatorio em build/deploy
- assets precisam estar consistentes com o hash gerado
- problemas de static em producao podem envolver cache/manifests alem de CSS em si

## Tailwind

O build de Tailwind e feito via `django-tailwind-cli` com config em `config/settings.py`.

Comandos uteis:

```bash
uv run python manage.py tailwind build
uv run python manage.py tailwind build --force
```

## Logs e observabilidade basica

O projeto possui configuracao de logging no proprio Django e middleware opcional de performance. Para investigacoes basicas, revise:

- `DJANGO_LOG_LEVEL`
- `DJANGO_ROOT_LOG_LEVEL`
- `PERF_LOGGING_ENABLED`
- `PERF_LOG_QUERIES`
- `PERF_LOG_MIN_MS`

## Checklist operacional de subida

Antes de considerar o ambiente saudavel, confira:

- banco respondeu e migrations aplicaram
- assets estaticos foram gerados
- webhook de assinatura sincronizou, se o ambiente exigir
- credenciais externas estao presentes para recursos usados naquele ambiente
- Gunicorn subiu sem erro

## Problemas comuns em deploy

### Container sobe e cai logo depois

- revise migrations
- revise conexao com banco
- revise credenciais/variaveis obrigatorias do startup

### Em producao a assinatura nao volta

- revise `APP_BASE_URL`
- revise se a URL publica e acessivel externamente
- revise sincronizacao do webhook

### Fiscal quebra so em deploy

- revise credenciais Webmania no ambiente remoto
- revise credenciais do bucket S3 compativel e certificado da oficina

### Upload de logo SVG falha

- no ambiente local Windows, confirme que `libcairo-2.dll` esta disponivel no `PATH`
- em deploy Docker, confirme que a imagem atual foi rebuildada com as dependencias nativas do Cairo
- valide com `uv run python -c "import cairosvg; print('ok')"`

### Static quebrado

- confirme `collectstatic`
- confirme build do Tailwind
- confirme se a imagem publicada e a mais recente

## Comandos relevantes para operacao

```bash
uv run python manage.py migrate
uv run python manage.py webhook
uv run python manage.py reconcile_webmania_documents
uv run python manage.py collectstatic --noinput
```

## Leitura complementar

- [Configuracao do ambiente](03-configuracao-do-ambiente.md)
- [Orcamentos, assinatura e webhooks](06-orcamentos-assinatura-e-webhooks.md)
- [Fiscal, NFe/NFSe e Webmania](09-fiscal-nfe-nfse-e-webmania.md)

[Anterior: Fiscal, NFe/NFSe e Webmania](09-fiscal-nfe-nfse-e-webmania.md) | [Indice da documentacao](README.md) | [Proximo: Glossario](11-glossario.md) | [Voltar ao README principal](../README.md)
