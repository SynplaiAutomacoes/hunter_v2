# Resumo

Plano de implementação do **Chat de Suporte Hunter v2** — widget flutuante (canto inferior direito) integrado à API externa **Chat Hunter** (`https://chathunter.up.railway.app/api/v1/ask`), com gerenciamento de sessão próprio no Postgres do Hunter v2.

Decisões validadas com o solicitante (rodada 1 + rodada 2):
- **Persistência local mínima:** salvar apenas `session_id` + metadados (usuário, oficina, timestamps). Conteúdo pergunta/resposta **não** é persistido localmente; histórico é lido sob demanda via `GET /api/v1/history?id_oficina=&id_usuario=&session_id=` com o mesmo `X-API-Key` do `ask`.
- **Identidade externa (corrigido após validação no banco):** `id_oficina = Workshop.pk` (oficina ativa) e `id_usuario = User.pk` (`accounts.User`) — **não** `WorkshopMember.pk`. Validado: user pk=20 (`Lucas.Moreira`) com vínculo ativo (member 35) na oficina 19 (`Hunter Jeep Vila Sonia`); `admin` é user pk=9 (member 25). O `WorkshopMember` serve só para guarda de acesso local + escopo das `ChatSession`/cache/rate-limit. Backend resolve o membership e nunca confia em IDs do browser.
- **Mensagens 403 diferenciadas:** guarda local → "Você não tem acesso ao chat nesta oficina."; recusa da API externa → "O assistente recusou o acesso para este usuário/oficina. Fale com o administrador."
- **Contrato `history` confirmado:** resposta `{id_oficina, id_usuario, session_id, mensagens: [{role, content}], atualizado_em}`. Parser deve ser tolerante a `role/content` com nomes alternativos e a lista vazia.
- **Sessão:** `session_id` opaco gerado no backend (`uuid4().hex`); regra de 5 min conta desde a **última mensagem** (`last_interaction_at`), escopo por par (usuário, oficina).
- **Proxy backend obrigatório:** `X-API-Key` vive só no servidor (env). Frontend nunca chama a API externa diretamente.
- **Escopo global:** widget em `templates/base.html`, visível para todo usuário autenticado com oficina ativa.
- **Histórico local:** aba **Mensagens** (footer) lista conversas via `GET /support-chat/titles/` (proxy de `GET /api/v1/titles`, payload `{titulos: [{session_id, titulo, atualizado_em}]}`), exibindo título + data; clica para retomar via `history`. Botão fixo "Envie uma mensagem para nós" no topo da aba Mensagens e na Home sempre abre **nova sessão** (`POST sessions/new/`).
- **Navegação do modal:** Home (`"Olá, como posso te ajudar?"` + botão) | Sessão (header com back-arrow ← à esquerda + close; sem botões ☰/＋) | Mensagens. Footer fixo com `Home` e `Mensagens`.
- **Frontend MVP rico:** markdown renderizado com `marked` + sanitização `DOMPurify` (via CDN pinado) + chips de perguntas-sugestão no estado vazio.
- **Limites operacionais:** rate-limit 30 msgs/min por usuário (429 além disso); timeout de leitura 120s com botão Cancelar (`AbortController`); trocar de página aborta a requisição.
- **Logs:** **sem logs de conversa** (nem pergunta/resposta, nem metadados de sessão em log de aplicação); apenas erros técnicos agregados sem PII para diagnóstico de indisponibilidade.

# Objetivo

## Objetivo

Oferecer um chat de suporte/assistente de dados em todas as telas autenticadas do Hunter v2, permitindo ao usuário de oficina fazer perguntas em linguagem natural (DRE, OS, estoque, regras do sistema) com contexto conversacional mantido pela API externa, sem expor credenciais no browser e sem acoplar o frontend ao provedor de LLM.

Objetivos de negócio:
1. Reduzir fricção de suporte e descoberta de dados ("quantos clientes tenho?", "qual a OS de cortesia?").
2. Manter isolamento por oficina/usuário já garantido pela API externa.
3. Não criar novo passivo de LGPD: não duplicar conteúdo conversacional no nosso banco.

## Requisitos

### Funcionais

- **RF01 — Widget global:** botão circular (FAB) inferior direito em todas as páginas autenticadas; abre/fecha painel de chat (~380px, responsivo mobile).
- **RF02 — Resolução de sessão ao abrir:** `GET` inicial resolve o `WorkshopMember` do par (usuário, oficina ativa) e retorna sessão ativa: se `last_interaction_at` da última sessão < 5 min, reabre; senão cria nova (`uuid4().hex`, gerado no backend). Sem membership ativo → 403 amigável sem criar sessão.
- **RF03 — Envio de pergunta:** `POST` interno `{pergunta}` → backend resolve `WorkshopMember.pk` como `id_usuario` + `Workshop.pk` como `id_oficina`, chama `POST /api/v1/ask` com `X-API-Key`, retorna `{resposta, session_id}`. Timeout de leitura 120s com suporte a cancelamento. Atualiza `last_interaction_at/message_count` **após** resposta bem-sucedida.
- **RF04 — Nova conversa manual:** botão "Nova conversa" cria nova sessão local + novo `session_id`, sem apagar anteriores.
- **RF05 — Histórico de sessões:** aba "Conversas" lista as **últimas 10 sessões** do `WorkshopMember` na oficina ativa (ordenadas por `last_interaction_at desc`, exibindo só data/hora + indicador de ativa), permite clicar e retomar qualquer sessão (carrega via `GET /api/v1/history` cujo payload é `{mensagens: [{role, content}], atualizado_em}`).
- **RF06 — Renderização de mensagens:** bolhas usuário/assistente, indicador de digitação/loading + botão Cancelar, markdown rico via `marked` + `DOMPurify`, chips de sugestão no estado vazio (ex.: "Quantos clientes eu tenho?", "Qual foi meu faturamento este mês?"), timestamps locais.
- **RF07 — Tratamento de erros amigável:** mapear 401/403/404/422/502/503 da API externa para mensagens PT-BR não técnicas; botão "tentar novamente".
- **RF08 — Identidade correta:** backend usa `WorkshopMember` resolvido de `request.user + oficina ativa` (`id_usuario = member.pk`, `id_oficina = workshop.pk`); nunca valores vindos do browser.
- **RF09 — Limite de entrada:** `pergunta` 1..2000 caracteres, validada no frontend e no backend. Rate-limit 30 msgs/min por member (429 + mensagem amigável).

### Não Funcionais

- **RNF01 — Segurança:** `CHAT_HUNTER_API_KEY` só em env/servidor; CSRF em todos os POSTs internos; `login_required`; checagem de `WorkshopMember.is_active` antes de chamar API; **sem logs de conversa** por decisão do solicitante; rate-limit 30/min por member via cache.
- **RNF02 — Performance:** chamada externa com `connect_timeout=5s, read_timeout=120s` + `AbortController` no frontend (botão Cancelar; navegação aborta); histórico com cache curto 60s por `session_id`; índices em `(member, workshop, last_interaction)`; lista de sessões limitada a 10.
- **RNF03 — Resiliência:** retry 1x apenas em erro de rede/timeout transitório (não em 4xx); circuit-breaker simples via contagem de 502/503 + mensagem de indisponibilidade; nunca vazar `X-API-Key` em logs/tracebacks.
- **RNF04 — Escalabilidade:** stateless (sessão em banco, não em memória); pronto para Gunicorn multi-worker; sem Channels/WebSocket no MVP (polling HTTP puro).
- **RNF05 — Manutenibilidade:** novo app `apps.support_chat` seguindo padrão DDD do repo (`domain/`, `application/`, `infrastructure/`, `presentation/`), SOLID, Object Calisthenics (métodos curtos, sem else encadeado, uma responsabilidade por classe); `mypy` + `ruff` limpos.
- **RNF06 — Acessibilidade/UX:** foco no input ao abrir, `Esc` fecha, aria-labels, contraste Tailwind/DaisyUI, funciona com HTMX/Alpine já presentes em `base.html`.
- **RNF07 — Observabilidade (modo sem logs de conversa):** por decisão do solicitante, **nenhum log de pergunta/resposta/session_id/user/workshop**. Apenas contadores agregados anônimos (ex.: total 200/4xx/5xx por minuto, latência p50/p95 sem identificadores) + log de erro técnico sem PII quando a API externa cai. Health interno verifica presença da env sem imprimi-la.

## Premissas

1. API externa já está em produção e estável em `https://chathunter.up.railway.app` (`POST /api/v1/ask` + `GET /api/v1/history` com mesmo `X-API-Key`, `/health`, `/docs`).
2. `id_usuario` = `collaborators.WorkshopMember.pk` (vínculo usuário×oficina) e `id_oficina` = `workshops.Workshop.pk`. Usuário sem `WorkshopMember` ativo recebe 403 amigável (caso: owner sem membership, membro inativo).
3. `session_id` é opaco (`uuid4().hex`); expira após 30 dias sem uso no Mongo deles. Formato de `history`: `{id_oficina, id_usuario, session_id, mensagens: [{role, content}], atualizado_em}`.
4. Stack mantida: Django 5.2 server-side + HTMX + Alpine.js + Tailwind/DaisyUI; sem SPA/React no MVP.
5. Postgres é o único banco de escrita local; não usaremos Mongo local.
6. `active_workshop_id` da sessão (`apps.workshops.context_processors.active_workshops`) é fonte da verdade para `id_oficina`.
7. Variáveis `CHAT_HUNTER_BASE_URL` e `CHAT_HUNTER_API_KEY` serão configuradas em `.env` local e Railway; valor de exemplo do solicitante **não** será commitado.

## Dependências

- **Externas:** disponibilidade/latência da Chat Hunter API; `OPENAI_API_KEY` deles; Mongo de conversas deles.
- **Internas:** `apps.accounts.User`, `apps.workshops` (oficina ativa), `apps.collaborators.WorkshopMember` (vínculo), `templates/base.html`, `config/settings.py`, `config/urls.py`, `static/js/`.
- **Infra:** `requests` (já no `pyproject.toml`) ou `httpx`; migrations Postgres; envs no Railway (`CHAT_HUNTER_BASE_URL`, `CHAT_HUNTER_API_KEY`, `SUPPORT_CHAT_SESSION_TIMEOUT_MINUTES=5`, `SUPPORT_CHAT_ENABLED=1`).
- **Documentação:** Swagger da API externa (`/docs`) para confirmar contrato de `/api/v1/history` (hoje só conhecido por informe verbal: `GET /api/v1/history?id_oficina=19&id_usuario=20&session_id=A1`).

## Riscos

| # | Risco | Impacto | Mitigação |
|---|-------|---------|-----------|
| 1 | Contrato de `GET /api/v1/history` não documentado/muda | Histórico quebra | Etapa 0 valida contrato com teste manual + fallback "histórico indisponível"; isolar parsing em `ChatHistoryParser` |
| 2 | Latência 10–60s da API (várias consultas SQL) gera timeout/UX ruim | Abandono | Timeout 120s, typing indicator, resposta assíncrona via fetch + AbortController, desabilitar botão durante envio |
| 3 | Vazamento de `X-API-Key` se chamada for feita no browser | Crítico | Proxy backend obrigatório; teste automatizado garante que key nunca vai ao template/JS; `git-secrets`/review |
| 4 | Spoofing de `id_oficina`/`id_usuario` via DevTools | Vazamento entre oficinas | Backend ignora IDs do body e usa `request.user` + oficina ativa; teste de isolamento |
| 5 | Sessões órfãs / condição de corrida ao abrir 2 abas | Duas sessões ativas | `get_or_create` + `select_for_update` no resolver; uma sessão "ativa" por (user, workshop), demais inativas mas listáveis |
| 6 | 401/403 por usuário sem vínculo | Chat parece quebrado | Mensagem específica "sem acesso nesta oficina" + log warn; não criar sessão nesses casos |
| 7 | Custo/latência OpenAI deles em pico | 502/503 frequentes | Retry limitado, mensagem de fallback, feature flag `SUPPORT_CHAT_ENABLED` para desligar sem deploy |
| 8 | XSS via markdown da resposta do LLM | Médio | Sanitizar HTML (bleach ou markdown seguro + escape); nunca `|safe` sem sanitização |

# Plano de Implementação

## Etapa 0 — Validação de contrato da API externa
### Objetivo
Confirmar na prática os contratos de `/api/v1/ask` e `/api/v1/history` antes de codar.
### Alterações
- Teste manual com `curl`/PowerShell + Swagger (`/docs`) registrando exemplos reais de request/response/erro de ambos endpoints.
- Definir timeout real p50/p95 e formato exato do histórico (lista de `{role, content, timestamp}`? paginação?).
- Congelar `CHAT_HUNTER_BASE_URL`, header `X-API-Key`, limites (2000 chars pergunta).
### Arquivos Impactados
- Nenhum código; artefato em `docs/support-chat-api-contrato.md` (nota de descoberta) + coleção de exemplos em `scratch/`.
### Critérios de Aceite
- [ ] Exemplo 200 de `ask` com e sem `session_id` documentado.
- [ ] Exemplo 200 de `history` com sessão existente e inexistente documentado.
- [ ] Tabela de erros 401/403/404/422/502/503 com corpos reais.

## Etapa 1 — Fundação: app `support_chat` + modelo de sessão
### Objetivo
Criar o bounded context do chat sem nenhuma integração externa ainda.
### Alterações
- `python manage.py startapp` adaptado para estrutura DDD: `apps/support_chat/{domain,application,infrastructure,presentation,templates,migrations,tests}` + `apps.py` (`SupportChatConfig`, `verbose_name="Chat de Suporte"`).
- Entidade `ChatSession` (domain) + model Django (infrastructure): `member FK collaborators.WorkshopMember`, `workshop FK workshops.Workshop` (desnormalizado para query rápida + integridade), `session_id CharField(unique, db_index, default=uuid4hex)`, `last_interaction_at DateTime`, `message_count Int`, `is_active Bool`, `TimeStampedModel` base. Constraint: 1 sessão ativa por (member, workshop) — reforçada em código + `UniqueConstraint(condition=is_active=True)`.
- `SessionResolver` (application service, SRP): `resolve_active(member, workshop)` — retorna última sessão se `now - last_interaction <= 5min`, senão desativa anterior e cria nova. Usa `transaction.atomic + select_for_update`. Chave de unicidade é o `member`, não o `User` (mesmo user em 2 oficinas tem 2 trilhas independentes).
- Registrar em `INSTALLED_APPS`, `admin.py` (list/filter por workshop/user), migration inicial, `factory`/seed para dev.
- Settings: `SUPPORT_CHAT_ENABLED`, `CHAT_HUNTER_BASE_URL`, `CHAT_HUNTER_API_KEY`, `SUPPORT_CHAT_SESSION_TIMEOUT_MINUTES=5`, `SUPPORT_CHAT_HISTORY_CACHE_SECONDS=60`.
### Arquivos Impactados
- `apps/support_chat/**` (novo), `config/settings.py`, `apps/support_chat/admin.py`, `.env.example`/docs de env.
### Critérios de Aceite
- [ ] `makemigrations` + `migrate` ok; `ruff` + `mypy` limpos.
- [ ] Teste unitário: sem sessão → cria; com sessão de 2 min → reusa; com 6 min → cria nova e desativa antiga; 2 abas concorrentes → 1 ativa.
- [ ] Admin lista sessões por oficina/usuário.

## Etapa 2 — Cliente HTTP da Chat Hunter API (infraestrutura)
### Objetivo
Isolar toda comunicação externa em um gateway testável, sem vazar segredos.
### Alterações
- `infrastructure/chat_hunter_client.py`: classe `ChatHunterClient` (injeção de `base_url`, `api_key`, `timeout=(5,120)` via construtor — DIP). Métodos `ask(id_oficina, id_usuario, pergunta, session_id)` e `get_history(id_oficina, id_usuario, session_id)` (mesmo `X-API-Key`). Usa `requests.Session` com retry 1x só em erro de rede (não 4xx). Mapeia exceções para `ChatHunterError(status, message)` tipado.
- `infrastructure/history_parser.py`: normaliza `{mensagens: [{role, content}], atualizado_em}` para `[{role: user|assistant, text, created_at}]` tolerante a `role` variations (`user/human/pergunta` → user; `assistant/ai/resposta` → assistant) e lista vazia. `atualizado_em` parsing ISO tolerante.
- **Sem logs de conversa:** nunca logar `api_key`, `pergunta`, `resposta`, `session_id`, `member/workshop ids` em qualquer nível. Apenas contadores agregados.
- Testes com `responses`/`unittest.mock` cobrindo 200/401/403/422/502/timeout.
### Arquivos Impactados
- `apps/support_chat/infrastructure/chat_hunter_client.py`, `history_parser.py`, `apps/support_chat/tests/test_client*.py`.
### Critérios de Aceite
- [ ] 200 de `ask` retorna `resposta` + ecoa `session_id`.
- [ ] 401/403/502 viram exceções tipadas com mensagens PT-BR mapeadas na camada presentation.
- [ ] Nenhum teste faz chamada real (mock) + nenhum log contém a key.

## Etapa 3 — Endpoints internos (proxy backend)
### Objetivo
Expor API interna segura que o widget JS consome; frontend nunca vê a key nem escolhe IDs.
### Alterações
- `presentation/urls.py` (namespace `support_chat`): `GET /support-chat/bootstrap/` (resolve `WorkshopMember` + sessão + retorna `session_id` + histórico via history API), `POST /support-chat/ask/` (`{pergunta}` → chama client, atualiza `last_interaction_at/message_count` só em 200), `GET /support-chat/sessions/` (últimas 10 do member na oficina ativa, só `session_id + last_interaction_at + is_active`), `POST /support-chat/sessions/new/` (força nova sessão), `GET /support-chat/history/?session_id=` (proxy do history externo com cache 60s; valida que a sessão pertence ao member).
- Todas as views: `LoginRequiredMixin`, `require_POST` onde couber, validação `pergunta 1..2000`, resolução de `workshop` via `get_active_workshop_or_404` + `WorkshopMember(user, workshop, is_active=True)` (403 se ausente/inativo, sem chamar API externa), throttle 30/min por member (cache → 429).
- Incluir `config/urls.py`: `path("support-chat/", include("apps.support_chat.presentation.urls"))`.
- Feature flag `SUPPORT_CHAT_ENABLED=0` → endpoints retornam 503 com mensagem amigável.
### Arquivos Impactados
- `apps/support_chat/presentation/views/*.py`, `urls.py`, `config/urls.py`, `apps/support_chat/tests/test_views*.py`.
### Critérios de Aceite
- [ ] `bootstrap` sem sessão recente cria `session_id` novo; com sessão de 3 min retorna a mesma.
- [ ] `ask` com oficina ativa válida retorna resposta; sem vínculo retorna 403 amigável sem chamar API externa.
- [ ] `ask` ignora `id_oficina`/`id_usuario` enviados pelo browser (teste de spoofing).
- [ ] CSRF exigido; 429 após burst.

## Etapa 4 — Widget frontend (FAB + painel)
### Objetivo
Experiência "padrão de mercado": FAB redondo, painel, bolhas, histórico, nova conversa.
### Alterações
- Parcial `apps/support_chat/templates/support_chat/_widget.html` + `static/js/support-chat.js` (vanilla + `fetch` + `AbortController`, compatível com Alpine/HTMX já em `base.html`).
- Comportamento: FAB fixo `bottom-6 right-6`; painel 380×560 (mobile full-width); ao abrir chama `bootstrap/`; envia com Enter; desabilita input durante espera + typing indicator + botão Cancelar; erro com retry; aba "Conversas" lista últimas 10 (`sessions/`, só data/hora) e carrega `history/`; botão "＋ Nova conversa"; estado vazio exibe chips de sugestão que preenchem o input.
- Markdown rico: `marked` (parse) + `DOMPurify` (sanitize) via CDN pinado com SRI; fallback para escape simples se CDN falhar. CSP deve permitir o CDN (validar `config/settings.py`).
- Acessibilidade: `aria-label`, `Esc` fecha, foco automático, `role=log` nas mensagens.
### Arquivos Impactados
- `apps/support_chat/templates/support_chat/_widget.html`, `static/js/support-chat.js`, `templates/base.html` (include condicional).
### Critérios de Aceite
- [ ] Abrir pela 1ª vez cria sessão; fechar/reabrir em <5min mantém contexto; após 6min cria nova (teste manual + E2E com relógio mockado no backend).
- [ ] Histórico mostra sessões antigas e retoma ao clicar.
- [ ] "Nova conversa" limpa painel e gera novo `session_id`.
- [ ] Sem `X-API-Key`, `id_oficina` ou `id_usuario` visíveis no JS/HTML/rede do browser.

## Etapa 5 — Integração global + permissões + flags
### Objetivo
Ligar o widget em todas as telas sem quebrar fluxos sem oficina (login, onboarding).
### Alterações
- `templates/base.html`: `{% if request.user.is_authenticated and active_workshop_id and SUPPORT_CHAT_ENABLED %}{% include "support_chat/_widget.html" %}{% endif %}` via context processor (`apps/support_chat/context_processors.py` ou reuso de `active_workshops` + setting).
- Middleware existente `RequireFirstWorkshopMiddleware` já garante oficina; widget não aparece em telas públicas/`403/404`.
- Todos os perfis veem por padrão (decisão validada); restrição futura por papel seria só um `if` no context processor.
### Arquivos Impactados
- `templates/base.html`, `apps/support_chat/context_processors.py` (novo), `config/settings.py` (TEMPLATES context_processors), `apps/core/presentation/middlewares.py` (sem mudança, só verificação).
### Critérios de Aceite
- [ ] Logado com oficina → FAB visível em budget/OS/finance/estoque; logado sem oficina → invisível sem erro; deslogado → invisível.
- [ ] `SUPPORT_CHAT_ENABLED=0` esconde widget e desliga endpoints.

## Etapa 6 — Endurecimento: segurança, performance, observabilidade
### Objetivo
Deixar o MVP pronto para produção.
### Alterações
- Rate-limit com cache `LocMemCache` (evoluir para Redis se já houver), validação de tamanho e `strip()`, `X-Request-ID` propagado ao client externo.
- Logs JSON com `latency_ms`, contadores de erro por status; alerta se p95 > 60s ou 5xx > 5%.
- `docs/10-deploy-build-e-operacao.md` + README de env: `CHAT_HUNTER_BASE_URL`, `CHAT_HUNTER_API_KEY` (Railway, sem default), rotação de key sem deploy (restart).
- Revisão LGPD: confirmar que não persistimos conteúdo; sessões listam só metadados + `session_id`.
### Arquivos Impactados
- `apps/support_chat/infrastructure/rate_limit.py` (ou middleware), `apps/core/observability.py` (hook), `docs/*`, `railway.toml`/variables.
### Critérios de Aceite
- [ ] Teste de penetração leve: spoofing, XSS (`<script>` na resposta vira texto), CSRF sem token → 403.
- [ ] p95 local do `bootstrap` (cache) < 300ms; `ask` limitado pelo provedor mas com feedback em <500ms (typing).
- [ ] Key ausente em prod → falha explícita no boot/health, não silenciosa.

## Etapa 7 — Testes, QA e rollout
### Objetivo
Garantir regressão zero e rollout controlado.
### Alterações
- Pirâmide: unitários (resolver, parser, client), integração (views com mock do client), E2E manual (roteiro: abrir, perguntar, esperar 6min, nova conversa, histórico, erro 503 simulado, mobile).
- `uv run python manage.py test apps.support_chat` + `ruff check` + `mypy` no CI.
- Rollout: flag off em prod → smoke em staging com key real → on para 1 oficina piloto → on global. Plano de rollback: `SUPPORT_CHAT_ENABLED=0`.
### Arquivos Impactados
- `apps/support_chat/tests/**`, `scripts/` de smoke (opcional), `docs/support-chat-qa.md`.
### Critérios de Aceite
- [ ] Cobertura ≥80% no novo app; todos os testes verdes.
- [ ] Roteiro QA assinado em staging; sem regressão em `base.html` (toasts, Alpine, HTMX intactos).
- [ ] Runbook de incidentes (key inválida, API fora, lentidão) publicado.

# Pontos de Atenção / Dúvidas Residuais (baixo risco, não bloqueiam MVP)

1. **Owner sem membership:** `Account.owner` / superuser sem `WorkshopMember` receberá 403 do nosso proxy. Confirmar se devemos auto-criar membership ou manter 403 com mensagem "sem acesso nesta oficina".
2. **`role`/`content` exatos do history:** confirmado o envelope `{mensagens: [{role, content}]}`, mas valores de `role` (`user` vs `human`, `assistant` vs `ai`) e formato de `atualizado_em` serão tolerados pelo parser; congelar exemplos reais na Etapa 0.
3. **CDN `marked`/`DOMPurify` + CSP:** confirmar que a política de segurança permite CDN pinado com SRI; senão, vendorizar em `static/js/vendor/`.
4. **Cache com múltiplos workers:** `LocMemCache` não compartilha throttle entre workers Gunicorn; se o rate-limit furar em prod, evoluir para cache Redis/DB.
5. **Chips de sugestão:** textos iniciais propostos no RF06; confirmar lista final com produto antes da Etapa 4.
6. **Key por oficina:** hoje global via env; se um dia cada oficina tiver sua key, será preciso campo em `Workshop` + rotação — endpoint interno já isola essa mudança.

# Checklist Final

- [ ] Etapa 0: contratos `ask` + `history` (`{mensagens: [{role, content}]}`) validados e documentados
- [ ] Etapa 1: app + `ChatSession(member, workshop)` + `SessionResolver` por member + migration + admin
- [ ] Etapa 2: `ChatHunterClient` + parser tolerante isolados e testados (sem key/logs de conversa no repo)
- [ ] Etapa 3: endpoints proxy (`bootstrap`, `ask`, `sessions` últimas 10, `history`) com auth/CSRF/throttle 30/min e 403 sem membership
- [ ] Etapa 4: widget FAB + painel + histórico (só data/hora) + nova conversa + markdown `marked`/`DOMPurify` + chips + Cancelar, sem segredos no browser
- [ ] Etapa 5: inclusão global em `base.html` com flag e oficina ativa
- [ ] Etapa 6: segurança (spoofing/XSS/CSRF), modo sem logs, docs de deploy, envs Railway
- [ ] Etapa 7: testes verdes, QA staging, rollout piloto, runbook
- [ ] Critério geral: `id_usuario=WorkshopMember.pk`; abrir <5min desde última mensagem reusa sessão (por member+oficina); >5min cria nova; histórico últimas 10 navegável; nova conversa manual funciona
