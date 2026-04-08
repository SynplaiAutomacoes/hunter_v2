# Multi-oficina e permissoes

[Voltar ao README principal](../README.md) | [Indice da documentacao](README.md) | [Anterior: Fluxo principal do sistema](04-fluxo-principal-do-sistema.md) | [Proximo: Orcamentos, assinatura e webhooks](06-orcamentos-assinatura-e-webhooks.md)

## Por que este tema importa

O Hunter V2 foi desenhado para operar com conta, usuarios e oficinas em paralelo. Isso significa que boa parte das regras de acesso, consulta e persistencia depende de escopo correto de conta e oficina.

Se um bug parece "aleatorio" em tela, permissao ou dados faltando, este e um dos primeiros temas para investigar.

## Entidades principais

### `Account`

Unidade raiz de tenancy. Usuarios e oficinas pertencem a uma conta.

### `User`

Usuario autenticado do sistema. Um usuario pode estar ligado a uma conta e atuar em oficinas por meio do vinculo operacional.

### `Workshop`

Unidade operacional central. A maior parte das funcionalidades do produto assume que existe uma oficina valida e ativa no contexto da sessao.

### Membership de oficina

O projeto usa relacao explicita entre usuario e oficina. Isso aparece em partes como:

- `User.workshops`
- validacoes no middleware
- filtros no context processor

## Oficina ativa na sessao

`apps/workshops/context_processors.py` resolve estas informacoes para o request:

- oficinas ativas disponiveis para o usuario
- `active_workshop_id`
- flags de diretor e gerente da oficina ativa

Quando a sessao nao tem `active_workshop_id` valido, o context processor tenta escolher uma oficina disponivel e persistir esse valor na sessao.

## Middleware de exigencia de oficina

`apps/core/middlewares.py` implementa `RequireFirstWorkshopMiddleware`, que faz validacoes importantes:

- se o usuario autenticado nao tem conta valida, faz logout
- se o owner da conta nao tem oficina ativa/cadastrada, redireciona para criacao de oficina
- se o colaborador nao possui membership ativo em oficina valida da conta, faz logout

Tambem existe uma whitelist de rotas permitidas antes da existencia da oficina.

## Papel do account owner

O owner da conta tem tratamento especial em alguns pontos. Na pratica:

- ele pode ser responsavel pelo bootstrap da conta
- ele costuma ser quem cria a primeira oficina
- sem oficina valida, certas rotas ficam bloqueadas por middleware

## Papel de colaboradores, gestores e diretores

O contexto de oficina ativa nao basta sozinho. O projeto tambem expande papel local por oficina, como diretor e gerente, a partir de helpers usados no context processor.

Isso significa que, para certas features, voce precisa considerar ao mesmo tempo:

- autenticacao
- conta
- membership em oficina
- papel local na oficina ativa

## Regras praticas para desenvolvimento

### Ao criar listagens

Sempre pergunte:

- essa consulta precisa ser filtrada por `account_id`?
- essa consulta precisa ser filtrada por `workshop` ou oficina ativa?
- o usuario pode enxergar dados de mais de uma oficina ao mesmo tempo?

### Ao criar forms e actions

Valide se a entidade alterada pertence a oficina/conta esperada. Nao assuma que o ID vindo da URL e suficiente.

### Ao criar templates e navegacao

Se a tela depende de oficina ativa, confira se ela usa corretamente o contexto injetado pelo context processor.

### Ao criar servicos

Nao esconda escopo de tenancy. Prefira receber oficina/conta explicitamente quando a operacao for sensivel a contexto.

## Sinais de problema de escopo

- dados de outra oficina aparecendo em lista
- usuario autenticado sendo deslogado sem motivo aparente
- pagina funcionando para owner e quebrando para colaborador
- acao funcionando em admin mas falhando em fluxo normal
- consulta retornando vazio mesmo com dados existentes

## Checklist antes de subir uma mudanca

- a consulta esta filtrada pela oficina/conta correta?
- a view lida com usuario sem oficina valida?
- o template depende de `active_workshop_id`?
- o comportamento muda entre owner, diretor, gerente e colaborador?
- existe risco de vazar dados entre oficinas?

## Arquivos para abrir quando houver duvida

- `apps/accounts/models.py`
- `apps/core/middlewares.py`
- `apps/workshops/context_processors.py`
- `apps/iam/`
- `apps/collaborators/`

## Relacao com o resto do sistema

Este tema impacta diretamente:

- navegacao e autorizacao
- listagens e filtros
- criacao e aprovacao de orcamento
- execucao de OS
- estoque, financeiro e fiscal

Em outras palavras: multi-oficina nao e detalhe de acesso. E uma regra estrutural do produto.

[Anterior: Fluxo principal do sistema](04-fluxo-principal-do-sistema.md) | [Indice da documentacao](README.md) | [Proximo: Orcamentos, assinatura e webhooks](06-orcamentos-assinatura-e-webhooks.md) | [Voltar ao README principal](../README.md)
