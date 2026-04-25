# Hunter V2

Documentacao tecnica interna para devs do Hunter V2.

O Hunter V2 e um sistema Django de gestao operacional para oficinas automotivas. O produto cobre o fluxo completo de atendimento e execucao: conta/oficina, clientes e veiculos, agendamento, orcamento tecnico-comercial, assinatura digital, ordem de servico, estoque, financeiro gerencial e emissao fiscal.

## Objetivo deste README

Este arquivo funciona como porta de entrada tecnica do projeto. Ele responde quatro perguntas:

1. O que o sistema faz.
2. Como subir o ambiente local.
3. Onde cada parte importante mora no codigo.
4. Em quais documentos aprofundar cada tema.

## Sumario

- [Objetivo deste README](#objetivo-deste-readme)
- [Visao geral do produto](#visao-geral-do-produto)
- [Stack principal](#stack-principal)
- [Estrutura do repositorio](#estrutura-do-repositorio)
- [Mapa rapido dos apps](#mapa-rapido-dos-apps)
- [Quick start local](#quick-start-local)
- [Comandos uteis](#comandos-uteis)
- [Fluxo funcional principal](#fluxo-funcional-principal)
- [Integracoes externas relevantes](#integracoes-externas-relevantes)
- [Ponto de entrada para leitura](#ponto-de-entrada-para-leitura)
- [Documentacao detalhada e navegavel](#documentacao-detalhada-e-navegavel)
- [Arquivos-chave para entender o sistema](#arquivos-chave-para-entender-o-sistema)
- [Notas operacionais importantes](#notas-operacionais-importantes)
- [Quando alterar documentacao](#quando-alterar-documentacao)
- [Indice da documentacao tecnica](docs/README.md)

## Visao geral do produto

Principais capacidades do sistema:

- multi-oficina por conta, com oficina ativa na sessao
- cadastro de clientes, veiculos, fornecedores e colaboradores
- fluxo de orcamento em varias etapas, com diagnostico, checklist e precificacao
- assinatura digital de orcamentos e documentos
- criacao e aprovacao de ordem de servico
- controle de estoque, movimentacoes e transferencia de itens
- financeiro com grupos, contas bancarias, meios de pagamento, fluxo de caixa e DRE
- emissao de NF-e e NFS-e com webhook e conciliacao

## Stack principal

- Backend: Django 5.2
- Linguagem: Python 3.11+
- Banco relacional: PostgreSQL
- Frontend: Django Templates + HTMX + Tailwind CSS + Crispy Forms
- Gerenciador Python: `uv`
- Gerenciador JS: `npm`
- App server: Gunicorn
- Static files: WhiteNoise
- Arquivos de oficina: Railway Storage Bucket (S3 compativel)
- PDF / automacao: `xhtml2pdf` e Playwright
- Deploy: Docker + Railway

## Estrutura do repositorio

```text
hunter_v2/
|- apps/                 # Apps de dominio e infraestrutura compartilhada
|- config/               # settings, urls, wsgi, asgi
|- templates/            # Templates globais
|- static/               # Assets fonte
|- media/                # Uploads locais e arquivos gerados
|- Dockerfile            # Build de deploy
|- docker-compose.yml    # PostgreSQL local
|- entrypoint.sh         # Startup do container
|- manage.py             # Entry point do Django
|- pyproject.toml        # Dependencias Python e config de tooling
|- package.json          # Plugins Tailwind
`- README.md             # Porta de entrada tecnica
```

## Mapa rapido dos apps

| App | Responsabilidade principal |
| --- | --- |
| `apps.accounts` | conta, usuario e relacao inicial de tenancy |
| `apps.iam` | papeis, cargos e permissoes |
| `apps.workshops` | oficinas, configuracoes operacionais, custos e arquivos |
| `apps.collaborators` | membros e vinculos de usuarios com oficinas |
| `apps.catalog` | produtos, servicos, kits e grupos de catalogo |
| `apps.suppliers` | fornecedores |
| `apps.sources` | origens/fontes de clientes e demandas |
| `apps.quote` | perguntas investigativas e apoio a triagem |
| `apps.checklist` | checklists e itens de checklist |
| `apps.customer` | clientes e veiculos |
| `apps.budget` | fluxo principal do orcamento, itens, PDFs e assinatura |
| `apps.workorder` | ordem de servico e execucao do trabalho |
| `apps.scheduling` | agendamentos |
| `apps.stock` | estoque, saldos e movimentacoes |
| `apps.finance` | financeiro, DRE, fiscal, Webmania e webhooks |
| `apps.messaging` | templates e grupos de comunicacao |
| `apps.core` | modelos base, middlewares, utilitarios, comandos e servicos compartilhados |

## Quick start local

### Pre-requisitos

- Python 3.11+
- `uv`
- Node.js 20+ e `npm`
- Docker / Docker Compose
- PostgreSQL rodando via container local

### Instalacao

```bash
uv sync
npm ci
docker compose up -d postgres
uv run python manage.py migrate
uv run python manage.py runserver
```

### Seed opcional para ambiente de desenvolvimento

Se quiser popular o banco com dados de exemplo depois das migrations:

```bash
uv run python manage.py seed_demo_data
```

### Variaveis de ambiente

Antes de rodar o projeto, garanta que as variaveis do seu `.env` estejam disponiveis na sessao atual do terminal ou configuradas pelo fluxo que sua equipe usa localmente.

## Comandos uteis

### Desenvolvimento

```bash
uv run python manage.py runserver
uv run python manage.py tailwind build
uv run python manage.py tailwind build --force
uv run python manage.py collectstatic --noinput
```

### Testes

```bash
uv run python manage.py test
uv run python manage.py test apps.finance
uv run python manage.py test apps.core.tests
uv run python manage.py test apps.core.tests.tests.TestRenderTableTag
uv run python manage.py test apps.core.tests.tests.TestRenderTableTag.test_renders_and_paginates
```

### Qualidade de codigo

```bash
uv run ruff check .
uv run ruff format .
uv run mypy .
```

### Operacao e manutencao

```bash
uv run python manage.py makemigrations
uv run python manage.py migrate
uv run python manage.py seed_demo_data
uv run python manage.py webhook
uv run python manage.py reconcile_webmania_documents
uv run playwright install --with-deps chromium
```

## Fluxo funcional principal

Em alto nivel, o sistema gira em torno deste fluxo:

1. Uma `Account` possui usuarios e uma ou mais oficinas.
2. O usuario atua dentro de uma oficina ativa na sessao.
3. O atendimento pode nascer de cliente/veiculo ja cadastrado ou de um agendamento.
4. O orcamento conduz triagem, checklist, diagnostico, itens e precificacao.
5. O fechamento pode envolver PDF, aprovacao e assinatura digital.
6. A aprovacao alimenta a ordem de servico.
7. A OS aprovada impacta estoque e pode gerar movimentos financeiros.
8. O fechamento fiscal gera NF-e/NFS-e e passa a depender da integracao com a Webmania.

Para a versao detalhada do fluxo, leia [Fluxo principal do sistema](docs/04-fluxo-principal-do-sistema.md).

## Integracoes externas relevantes

- Webmania: emissao fiscal, status, conciliacao e webhook
- SuperSign: assinatura digital e webhook de conclusao
- Railway Storage Bucket: armazenamento privado de certificado e logo de oficina
- Playwright: runtime de navegador usado no build e em geracao/automacao

Essas integracoes nao sao detalhe periferico. Elas influenciam configuracao, deploy, startup e parte importante da modelagem do dominio.

## Ponto de entrada para leitura

Se voce esta entrando no projeto agora, esta ordem funciona bem:

1. [Indice da documentacao tecnica](docs/README.md)
2. [Visao geral do produto](docs/01-visao-geral-do-produto.md)
3. [Arquitetura e apps](docs/02-arquitetura-e-apps.md)
4. [Configuracao do ambiente](docs/03-configuracao-do-ambiente.md)
5. [Fluxo principal do sistema](docs/04-fluxo-principal-do-sistema.md)
6. [Multi-oficina e permissoes](docs/05-multi-oficina-e-permissoes.md)
7. [Orcamentos, assinatura e webhooks](docs/06-orcamentos-assinatura-e-webhooks.md)
8. [Financeiro e DRE](docs/08-financeiro-e-dre.md)
9. [Fiscal, NFe/NFSe e Webmania](docs/09-fiscal-nfe-nfse-e-webmania.md)

## Documentacao detalhada e navegavel

Indice completo: [abrir documentacao tecnica](docs/README.md).

| Documento | Quando abrir |
| --- | --- |
| [Visao geral do produto](docs/01-visao-geral-do-produto.md) | para entender o dominio antes de mergulhar no codigo |
| [Arquitetura e apps](docs/02-arquitetura-e-apps.md) | para localizar responsabilidades por app e camada |
| [Configuracao do ambiente](docs/03-configuracao-do-ambiente.md) | para onboarding, `.env`, banco e comandos locais |
| [Fluxo principal do sistema](docs/04-fluxo-principal-do-sistema.md) | para entender a jornada ponta a ponta |
| [Multi-oficina e permissoes](docs/05-multi-oficina-e-permissoes.md) | para tenancy, oficina ativa e escopo de acesso |
| [Orcamentos, assinatura e webhooks](docs/06-orcamentos-assinatura-e-webhooks.md) | para o fluxo central do modulo `budget` |
| [Estoque e catalogo](docs/07-estoque-e-catalogo.md) | para produtos, servicos, kits, saldo e consumo |
| [Financeiro e DRE](docs/08-financeiro-e-dre.md) | para movimentos, caixa, classificacao e relatorios |
| [Fiscal, NFe/NFSe e Webmania](docs/09-fiscal-nfe-nfse-e-webmania.md) | para emissao, webhook, certificado e integracao fiscal |
| [Deploy, build e operacao](docs/10-deploy-build-e-operacao.md) | para Docker, Railway, startup e troubleshooting operacional |
| [Glossario](docs/11-glossario.md) | para termos do dominio e nomenclaturas internas |

## Arquivos-chave para entender o sistema

- `config/settings.py`: configuracao global, apps instalados e variaveis de ambiente
- `config/urls.py`: mapa raiz de rotas
- `apps/core/middlewares.py`: exigencia de oficina e logging de performance
- `apps/workshops/context_processors.py`: oficina ativa e contexto do usuario
- `apps/budget/urls.py`: centro do fluxo comercial
- `apps/workorder/approval.py`: aprovacao da OS com baixa de estoque
- `apps/finance/urls.py`: financeiro, DRE, fiscal e Webmania
- `apps/workshops/services/files.py`: logo/certificado via bucket S3 compativel e sincronizacao com Webmania
- `apps/core/management/commands/seed_demo_data.py`: seed de desenvolvimento

## Notas operacionais importantes

- O projeto usa PostgreSQL como banco padrao. SQLite nao faz parte do fluxo suportado.
- Em ambiente containerizado, o `entrypoint.sh` executa `manage.py webhook`, aplica migrations e sobe Gunicorn.
- A integracao de assinatura depende de `APP_BASE_URL` apontando para uma URL realmente acessivel pelo provedor externo.
- Recursos fiscais dependem de certificado da oficina, configuracao da empresa na Webmania e classes fiscais consistentes.
- O sistema assume contexto de oficina ativa para boa parte das funcionalidades. Quando isso falha, o primeiro lugar para investigar costuma ser `apps/workshops/context_processors.py` e `apps/core/middlewares.py`.

## Quando alterar documentacao

Atualize este README e os arquivos em `docs/` sempre que houver mudanca relevante em:

- setup local
- variaveis de ambiente
- integracoes externas
- fluxo do orcamento ou da OS
- regras de estoque, financeiro ou fiscal
- estrategia de deploy e build
