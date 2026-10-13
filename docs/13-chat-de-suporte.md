# Chat de suporte

[Voltar ao README principal](../README.md) | [Indice da documentacao](README.md) | [Anterior: Observabilidade e telemetria](12-observabilidade-e-telemetria.md)

## Objetivo

O chat de suporte e um assistente em linguagem natural embutido em uma API externa. O usuario de oficina faz perguntas sobre os dados (DRE, clientes, orcamentos, OS, financeiro, estoque) e sobre o sistema (regras, telas, campos), e recebe respostas geradas pela API externa **Chat Hunter**, que consulta o mesmo Postgres do Hunter em modo somente leitura.

Principios do desenho:

- **Proxy backend obrigatorio:** o navegador nunca fala com a API externa nem ve a `X-API-Key`. Todo o trafego passa por endpoints internos Django.
- **Sessao local minima:** persistimos apenas `session_id` + metadados. O conteudo das mensagens nao e gravado no nosso banco (modo sem logs); o historico e lido sob demanda na API externa.
- **Identidade server-side:** `id_oficina`/`id_usuario` sao resolvidos de `request.user` + oficina ativa. Valores vindos do browser sao ignorados.
- **Controle de acesso pelo dono do sistema:** blocklist de usuarios + oficinas desabilitadas, gerenciada em Gerenciar Sistema.

## API externa (Chat Hunter)

Base: `https://chathunter.up.railway.app` (configuravel via `CHAT_HUNTER_BASE_URL`). Autenticacao: header `X-API-Key` com o valor de `CHAT_HUNTER_API_KEY` (somente servidor, nunca commitado).

| Endpoint | Uso |
| --- | --- |
| `POST /api/v1/ask` `{id_oficina, id_usuario, pergunta, session_id}` | Envia pergunta, retorna `{resposta, session_id, titulo}` |
| `GET /api/v1/history?id_oficina=&id_usuario=&session_id=` | Historico da conversa `{mensagens: [{role, content}], titulo, atualizado_em}` |
| `GET /api/v1/titles?id_oficina=&id_usuario=` | Ultimos 10 titulos `{titulos: [{session_id, titulo, atualizado_em}]}` |
| `GET /health`, `GET /docs` | Saude e Swagger |

Mapeamento de identidade (validado no banco): `id_oficina = Workshop.pk`, `id_usuario = User.pk` (`accounts.User`, nao `WorkshopMember.pk`). O `session_id` e opaco (`uuid4().hex` gerado no nosso backend); a API externa expira o contexto apos 30 dias sem uso. Uma resposta pode levar de segundos a ~1 minuto: timeout de leitura 120 s com botao Cancelar no frontend.

Erros da API externa sao traduzidos para mensagens PT-BR amigaveis. O 403 externo ("acesso recusado para este usuario/oficina") tem texto distinto do 403 local ("sem acesso nesta oficina") para facilitar o diagnostico.

## Arquitetura no Hunter v2

Novo app `apps/support_chat`, seguindo o padrao DDD do repo:

```text
apps/support_chat/
  models.py                  # ChatSession, ChatBlockedUser, ChatDisabledWorkshop
  application/
    session_resolver.py      # regra de reuso/criacao de sessao (5 min)
    access_policy.py         # can_use_chat() + cache
  infrastructure/
    chat_hunter_client.py    # gateway HTTP (ask/history/titles)
    history_parser.py        # normalizacao de history + titles
    errors.py                # ChatHunterError(status, message)
  presentation/
    urls.py                  # namespace support_chat
    views/chat_views.py      # bootstrap/ask/sessions/history/titles
  templates/support_chat/_widget.html
  context_processors.py      # flag SUPPORT_CHAT_VISIBLE
  admin.py
```

### Model `ChatSession`

Trilha de sessao por vinculo + oficina. Campos: `member` (FK `WorkshopMember`), `workshop` (FK `Workshop`), `session_id` (unico, default `uuid4().hex`), `last_interaction_at`, `message_count`, `is_active`. Constraint: 1 sessao ativa por (member, workshop). `touch()` atualiza interacao/contador apos cada `ask` 200.

### Regra de sessao (5 minutos)

`SessionResolver.resolve_active(member, workshop)` reusa a ultima sessao se `now - last_interaction_at <= SUPPORT_CHAT_SESSION_TIMEOUT_MINUTES` (padrao 5); senao desativa a anterior e cria nova. Transacao com `select_for_update` evita sessoes ativas duplicadas com 2 abas. O botao "Envie uma mensagem para nós" sempre forca sessao nova via `POST sessions/new/`.

## Endpoints internos (`/support-chat/`)

Todos exigem login, oficina ativa com vinculo (`WorkshopMember` ativo), flag `SUPPORT_CHAT_ENABLED` e politica de acesso (403 local caso contrario). CSRF obrigatorio nos POSTs. Rate-limit 30 msgs/min por vinculo (429).

| Rota                   | Metodo                         | Descricao                                                     |
|------------------------|--------------------------------|---------------------------------------------------------------|
| `bootstrap/`           | GET                            | Resolve sessao ativa + devolve historico (usado ao retomar)   |
| `ask/`                 | POST `{pergunta, session_id?}` | Chama `/api/v1/ask`, atualiza `touch()`, invalida caches      |
| `sessions/`            | GET                            | Ultimas 10 sessoes locais (so `session_id` + data + ativa)    |
| `sessions/new/`        | POST                           | Forca nova sessao                                             |
| `history/?session_id=` | GET                            | Proxy de `/api/v1/history` (valida pertencimento, cache 60 s) |
| `titles/`              | GET                            | Proxy de `/api/v1/titles` (cache 60 s por vinculo)            |

## Widget frontend

Partial `support_chat/_widget.html` incluida em `templates/base.html`, visivel apenas quando `SUPPORT_CHAT_VISIBLE` e verdadeiro. FAB circular inferior direito; modal com 3 visoes:

- **Home:** "Olá, como posso te ajudar?" + botao "Envie uma mensagem para nós" (icone `send`) — abre sessao nova.
- **Sessao:** header com back-arrow (volta a Home) + bolhas usuario/assistente, markdown via `marked` + `DOMPurify` (CDN), chips de sugestoes no estado vazio, typing indicator, botao Cancelar (`AbortController`), `Esc` fecha.
- **Mensagens:** botao fixo "Envie uma mensagem para nós" (icone `help`) + lista de titulos (titulo + data) clicaveis.
- **Footer:** `Home` (icone `home`) | `Mensagens` (icone `message`), texto azul (`text-primary`) na aba ativa/hover, altura `h-14`.

JS em `static/js/support-chat.js` (vanilla + `fetch`, sem dependencia nova alem dos CDNs de markdown).

## Controle de acesso (Gerenciar Sistema)

Area restrita a usernames em `SYSTEM_ADMIN_USERNAMES` (`/workshops/sistema/gerenciar/`). Nova pagina **Acesso ao Chat** (`sistema/gerenciar/chat/acesso/`), no mesmo padrao da pagina de broadcast (card no dashboard + `SystemManagementMixin` + `SearchableSelectInput` + POST classico):

- **Usuarios Bloqueados:** blocklist global — usuario bloqueado perde o chat em todas as oficinas.
- **Oficinas sem Chat:** oficinas desabilitadas — nenhum membro delas ve o chat.
- Semantica: acesso = usuario nao bloqueado **E** oficina habilitada. Bypass total para `SYSTEM_ADMIN_USERNAMES`. Bloqueado nao ve o widget (some por completo); chamadas diretas a API interna retornam 403.
- Persistencia: `ChatBlockedUser` / `ChatDisabledWorkshop` (+ autor e data, visiveis tambem no Django admin). `can_use_chat()` tem cache de 60 s com versionamento, invalidado a cada alteracao.

## Variaveis de ambiente

| Var | Padrao | Descricao |
| --- | --- | --- |
| `SUPPORT_CHAT_ENABLED` | `1` | Feature flag global (0 desliga widget + endpoints) |
| `CHAT_HUNTER_BASE_URL` | `https://chathunter.up.railway.app` | Base da API externa |
| `CHAT_HUNTER_API_KEY` | (vazio) | `X-API-Key` — obrigatoria em prod, nunca commitar |
| `SUPPORT_CHAT_SESSION_TIMEOUT_MINUTES` | `5` | Janela de reuso de sessao |
| `SUPPORT_CHAT_HISTORY_CACHE_SECONDS` | `60` | Cache de history/titles/politica |
| `SYSTEM_ADMIN_USERNAMES` | (vazio) | Quem acessa Gerenciar Sistema (bypass do chat) |

Sem `CHAT_HUNTER_API_KEY`, os endpoints retornam 503 com mensagem amigavel.

## Seguranca e LGPD

- Pergunta/resposta/`session_id`/ids nunca vao para logs; apenas contadores agregados anonimos.
- XSS mitigado com `DOMPurify`; nunca `|safe` sem sanitizacao.
- Spoofing mitigado: IDs do body ignorados; `session_id` de outro vinculo retorna 404.
- Rollback imediato: `SUPPORT_CHAT_ENABLED=0` (sem deploy).

## Operacao e troubleshooting

| Sintoma | Causa provavel | Acao |
| --- | --- | --- |
| "Você não tem acesso ao chat nesta oficina." | Sem vinculo ativo ou bloqueado/oficina desabilitada | Checar `WorkshopMember`, blocklists, `SYSTEM_ADMIN_USERNAMES` |
| "O assistente recusou o acesso..." | 403 da API externa (`User.pk`/`Workshop.pk` sem vinculo la) | Validar ids no banco da API |
| "O assistente está indisponível..." | 502/503/timeout externo | Checar `/health` externo, key,Splash latencia |
| Widget invisivel | Flag off, sem oficina ativa ou bloqueado | Checar env, sessao, politica |
| Titles vazio | Sem conversas ou cache | Aguardar 60 s / nova pergunta gera `titulo` |

Arquivos-chave: `apps/support_chat/**`, `apps/workshops/views/system_management.py` (`SupportChatAccessView`), `apps/workshops/forms/system_management.py` (`SupportChatAccessForm`), `templates/base.html` (include), `config/settings.py` (envs), `config/urls.py` (rotas).

[Voltar ao README principal](../README.md) | [Indice da documentacao](README.md)
