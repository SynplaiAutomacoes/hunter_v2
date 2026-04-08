# Arquitetura e apps

[Voltar ao README principal](../README.md) | [Indice da documentacao](README.md) | [Anterior: Visao geral do produto](01-visao-geral-do-produto.md) | [Proximo: Configuracao do ambiente](03-configuracao-do-ambiente.md)

## Visao arquitetural

O projeto segue uma arquitetura Django tradicional, com renderizacao server-side e reforco de interatividade pontual com HTMX. A maior parte da inteligencia de negocio esta distribuida por apps de dominio, forms, services, modelos e views baseadas em classe.

Em termos simples:

- Django entrega autenticacao, ORM, templates, middlewares e roteamento
- Tailwind cuida da camada visual
- HTMX adiciona interacoes incrementais sem transformar o produto em SPA
- PostgreSQL guarda o estado principal do sistema
- MongoDB/GridFS armazena alguns arquivos de oficina
- integracoes externas se conectam a partir de services, webhooks e comandos

## Estrutura principal de pastas

| Caminho | Papel |
| --- | --- |
| `config/` | settings, urls, ASGI/WSGI |
| `apps/` | dominio e infraestrutura de aplicacao |
| `templates/` | templates globais |
| `static/` | CSS, JS e assets fonte |
| `media/` | uploads locais e arquivos gerados |
| `certificados/` | arquivos locais legados ou auxiliares relacionados a certificados |

## Apps do projeto

### `apps.core`

Base compartilhada do projeto. Concentra modelos abstratos, middlewares, utilitarios, documentos, comandos e outras pecas reaproveitadas em varios dominios.

### `apps.accounts`

Controla `Account`, `User` e o ponto inicial da tenancy. E um dos primeiros lugares para entender relacionamento entre usuario e conta.

### `apps.iam`

Regras de papeis, cargos e permissao. Sempre que houver duvida sobre capacidade de acesso por perfil, o caminho passa por aqui.

### `apps.workshops`

Cadastro e configuracao da oficina. Tambem concentra custos, logo, certificado, integracao operacional com emissao fiscal e suporte a arquivos no MongoDB.

### `apps.collaborators`

Vinculo entre usuario e oficina. Importante para entender membership, papeis locais e acesso operacional.

### `apps.customer`

Clientes e veiculos. Alimenta o fluxo de atendimento e reaparece em agendamento, orcamento e OS.

### `apps.scheduling`

Agendamentos. Pode ser porta de entrada do atendimento antes do orcamento.

### `apps.quote`

Perguntas investigativas usadas na triagem. Apoia a captura de contexto tecnico antes da proposta.

### `apps.checklist`

Modela checklists e itens usados no atendimento tecnico.

### `apps.catalog`

Catalogo de produtos, servicos, kits e grupos. E a base para composicao de orcamentos e parte do comportamento de estoque e fiscal.

### `apps.suppliers`

Fornecedores usados no ecossistema operacional e financeiro.

### `apps.sources`

Origem de leads, clientes ou demandas. Serve como apoio de contexto comercial/operacional.

### `apps.budget`

Nucleo funcional do sistema. Aqui mora o fluxo principal de orcamento, os itens, as etapas, PDFs, eventos e assinatura digital.

### `apps.workorder`

Representa a execucao. Aprovacao de OS conversa com estoque e influencia financeiro/fiscal.

### `apps.stock`

Controle de saldos e movimentacoes. Tambem abriga regras de importacao, transferencia e impacto operacional dos itens fisicos.

### `apps.finance`

Maior concentracao de regras transversais depois de `apps.budget`. Cobre financeiro, DRE, classes fiscais, emissao, webhook e integracao com Webmania.

### `apps.messaging`

Templates e agrupamentos de mensagens. Hoje parece cumprir papel de comunicacao operacional e CRM leve.

## Pecas arquiteturais que merecem atencao

### Middlewares

`apps/core/middlewares.py` tem pelo menos dois comportamentos importantes:

- logging de performance por request, controlado por env vars
- exigencia de oficina valida para usuarios autenticados

### Context processor de oficina ativa

`apps/workshops/context_processors.py` injeta no request/contexto a lista de oficinas disponiveis, a oficina ativa e flags de papel local. Isso afeta navegacao, filtros e comportamento de views.

### Services

O projeto usa services em varios pontos para encapsular integracoes e regras mais carregadas. Exemplos relevantes:

- `apps/workshops/services/files.py`
- `apps/finance/services/*`

### Management commands

Comandos administrativos ajudam no bootstrap e na operacao:

- `apps/core/management/commands/seed_demo_data.py`
- `apps/budget/management/commands/webhook.py`
- `apps/finance/management/commands/reconcile_webmania_documents.py`

## Integracoes e infraestrutura transversal

### Webmania

Usada para emissao e tratamento de documentos fiscais, com suporte a webhook e conciliacao.

### SuperSign

Usada para assinatura digital. O sistema possui sincronizacao de webhook e endpoint dedicado para receber eventos de conclusao.

### MongoDB/GridFS

Usado para guardar arquivos da oficina, em especial certificado e logo, com servico dedicado para leitura, escrita, limpeza e sincronizacao.

### WhiteNoise e Gunicorn

Formam a base de entrega da aplicacao em producao no modelo atual de deploy em container.

## Onde adicionar codigo novo

Use estas regras praticas:

- se a regra e compartilhada e nao pertence claramente a um dominio, comece investigando `apps.core`
- se a regra e sobre fluxo comercial/tatico do atendimento, quase sempre passa por `apps.budget`
- se a regra nasce da aprovacao/execucao, avalie `apps.workorder` e `apps.stock`
- se a mudanca mexe com dinheiro, impostos, conta bancaria, formas de pagamento, DRE ou emissao, o ponto de partida tende a ser `apps.finance`
- se a mudanca depende de oficina ativa ou membership, revise tambem `apps.workshops`, `apps.collaborators` e `apps.iam`

## Arquivos bons para abrir cedo

- `config/settings.py`
- `config/urls.py`
- `apps/core/middlewares.py`
- `apps/workshops/context_processors.py`
- `apps/budget/urls.py`
- `apps/finance/urls.py`
- `apps/workorder/approval.py`

## Proxima leitura recomendada

- [Configuracao do ambiente](03-configuracao-do-ambiente.md)
- [Fluxo principal do sistema](04-fluxo-principal-do-sistema.md)
- [Multi-oficina e permissoes](05-multi-oficina-e-permissoes.md)

[Anterior: Visao geral do produto](01-visao-geral-do-produto.md) | [Indice da documentacao](README.md) | [Proximo: Configuracao do ambiente](03-configuracao-do-ambiente.md) | [Voltar ao README principal](../README.md)
