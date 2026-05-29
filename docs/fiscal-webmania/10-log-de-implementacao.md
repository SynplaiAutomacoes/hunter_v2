# Log de implementacao fiscal

Este arquivo deve ser atualizado a partir da primeira fase de codigo aprovada.

## Entradas

| Data       | Fase | Objetivo                      | Arquivos alterados       | Migrations | Testes executados | Decisoes       | Pendencias     | Riscos                                          | Proxima acao       |
| ---------- | ---- | ----------------------------- | ------------------------ | ---------- | ----------------- | -------------- | -------------- | ----------------------------------------------- | ------------------ |
| 2026-05-28 | 0    | Criar PRDs e OpenAPI validado | `docs/fiscal-webmania/*` | Nenhuma    | Nao aplicavel     | ADRs propostas | Aprovada pelo usuario | Docs podem ficar desatualizados se codigo mudar | Manter docs sincronizados |
| 2026-05-28 | 0.1  | Reforcar OpenAPI, divergencias e regras beta | `docs/fiscal-webmania/*` | Nenhuma | Parse JSON e contagem OpenAPI | Consultas NFS-e/MDF-e conforme exemplo oficial; NFCom/DC-e beta com feature flag | Aprovada pelo usuario | Schemas devem ser reconferidos antes de cada fase de codigo | Revalidar antes de novas familias |
| 2026-05-28 | 1    | Estabilizar NF-e/NFS-e existentes | `apps/finance/models/finance.py`, `apps/finance/models/__init__.py`, `apps/finance/migrations/0041_fiscalemissionattempt_and_more.py`, `apps/finance/services/fiscal_attempts.py`, `apps/finance/services/nfe_emission.py`, `apps/finance/services/emission.py`, `apps/finance/services/tax_classes.py`, `apps/finance/services/webmania_webhooks.py`, `apps/finance/management/commands/reconcile_webmania_documents.py`, `apps/finance/views/nfe.py`, `apps/workshops/mixin.py`, `apps/finance/tests.py`, `docs/fiscal-webmania/*` | `finance.0041_fiscalemissionattempt_and_more` | `FiscalPhaseOneStabilizationTests` e `FiscalPhaseOneConcurrentEmissionTests` OK; `makemigrations finance --check --dry-run` OK; ruff nos arquivos tocados OK; `git diff --check` OK; falhas globais aceitas como preexistentes | Manter `NfeRequest`/`NfseRequest`; tentativa persistida por intencao; `uncertain` bloqueia reenvio; webhook por fingerprint; NF-e usa permissao propria com fallback legado | Validada tecnicamente com dividas preexistentes registradas e aceitas pelo usuario | Reconciliacao e webhook nao emitem; tentativa incerta exige consulta/reconciliacao manual antes de nova emissao | Aguardar autorizacao explicita da Fase 2 |
| 2026-05-28 | 2.0  | Planejar expansao NF-e/NFC-e | `docs/fiscal-webmania/*` | Nenhuma | Revisao documental e rechecagem oficial NF-e/NFC-e | Recomendar nucleo minimo; usuario decidiu que `FiscalDocumentLink` fica somente para 2.2; dividir Fase 2 em 2.1 CC-e, 2.2 derivados, 2.3 NFC-e, 2.4 manifestacao/IBS-CBS | Aprovada pelo usuario | Endpoints e Reforma Tributaria devem ser revalidados antes de codigo | Fase 2.1 implementada para revisao |
| 2026-05-28 | 2.1  | Implementar CC-e Webmania | `apps/finance/models/finance.py`, `apps/finance/models/__init__.py`, `apps/finance/migrations/0042_fiscalemissionattempt_operation_type_and_more.py`, `apps/finance/services/fiscal_attempts.py`, `apps/finance/services/nfe_events.py`, `apps/finance/services/webmania_webhooks.py`, `apps/finance/views/nfe.py`, `apps/finance/views/__init__.py`, `apps/finance/urls.py`, `apps/finance/templates/finance/nfe_request_detail.html`, `apps/finance/tests.py`, `docs/fiscal-webmania/*` | `finance.0042_fiscalemissionattempt_operation_type_and_more` | `makemigrations finance --check --dry-run` OK; `FiscalPhaseOne*` + `FiscalPhaseTwoCorrection*` OK com 27 testes; ruff nos arquivos Python tocados OK; `git diff --check` OK | Criar apenas `FiscalDocument`/`FiscalDocumentEvent`; `FiscalDocumentLink` fica para 2.2; CC-e e evento, nao nota comum; idempotencia por sequencia 1-20; webhook CC-e por UUID e fallback por chave+sequencia com ambiguidade rejeitada | Validada | Webmania CC-e deve ser reconferida em homologacao antes de producao; `uncertain` exige resolucao manual/reconciliacao futura | Aguardar autorizacao explicita da Fase 2.2 |
| 2026-05-28 | 2.2.0 | Revisar modelagem documental de derivados NF-e | `docs/fiscal-webmania/*` | Nenhuma | `git diff --check` documental | Devolucao/estorno e complementar exigem `FiscalDocumentLink`; ajuste usa link opcional; NF-e externa ganha projecao minima; credito/debito vao para Fase 2.5 | Documentada; sem codigo autorizado | Revalidar payloads oficiais imediatamente antes de implementar cada subfase | Recomendar iniciar por Fase 2.2A |
| 2026-05-28 | 2.2A-doc | Corrigir decisoes antes do codigo de devolucao/estorno | `docs/fiscal-webmania/*` | Nenhuma | `git diff --check` documental | NF-e externa valida formato e exige confirmacao, sem consulta padrao como garantia; idempotencia por documento derivado persistido | Documentada; Fase 2.2A autorizada apos esta correcao | Payloads oficiais ainda devem ser revalidados no gateway | Implementar somente Fase 2.2A |
| 2026-05-28 | 2.2A | Implementar e validar devolucao e estorno NF-e | `apps/finance/models/finance.py`, `apps/finance/migrations/0043_fiscaldocumentlink_alter_fiscaldocument_options_and_more.py`, `apps/finance/services/fiscal_attempts.py`, `apps/finance/services/nfe_returns.py`, `apps/finance/services/webmania_webhooks.py`, `apps/finance/management/commands/reconcile_webmania_documents.py`, `apps/finance/views/nfe.py`, `apps/finance/views/__init__.py`, `apps/finance/urls.py`, `apps/finance/templates/finance/nfe_request_detail.html`, `apps/finance/tests.py`, `docs/fiscal-webmania/*` | `finance.0043_fiscaldocumentlink_alter_fiscaldocument_options_and_more` | `makemigrations finance --check --dry-run` OK; `FiscalPhaseOne*`, `FiscalPhaseTwoCorrection*`, `FiscalPhaseTwoReturn*` OK com 45 testes; ruff nos arquivos Python tocados OK; `git diff --check` OK | Criar `FiscalDocumentLink`; persistir documento derivado antes do POST `/1/nfe/devolucao/`; idempotencia por documento derivado; parcial usa sequenciais fiscais e vetor `quantidade` alinhado; NF-e externa minima bloqueia parcial sem XML/importacao; webhook/reconciliacao atualizam somente derivado | Validada | UI local minima usa produtos JSON com sequencial fiscal; validacao externa por XML/API especifica permanece backlog | Aguardar autorizacao explicita da Fase 2.2B |
| 2026-05-28 | 2.2B.0 | Planejar Nota Fiscal Complementar | `docs/fiscal-webmania/*` | Nenhuma | `git diff --check` documental | Complementar sera `FiscalDocument(purpose="complementary")` com subtipo `price_quantity`, `tax` ou `import_addition`; `FiscalDocumentLink(role="complements")` obrigatorio; idempotencia por documento derivado; externa minima bloqueia preco/quantidade sem XML/importacao | Documentada; codigo funcional nao autorizado | Revalidar payload oficial por subtipo antes do codigo; decidir politica final para complementar tributaria externa | Recomendar iniciar por `complementary_price_quantity` local |
| 2026-05-28 | 2.2B.1 | Implementar Nota Fiscal Complementar de preco/quantidade local | `apps/finance/models/finance.py`, `apps/finance/migrations/0044_alter_fiscaldocument_options_and_more.py`, `apps/finance/services/nfe_complementary.py`, `apps/finance/services/webmania_webhooks.py`, `apps/finance/management/commands/reconcile_webmania_documents.py`, `apps/finance/views/nfe.py`, `apps/finance/views/__init__.py`, `apps/finance/urls.py`, `apps/finance/templates/finance/nfe_request_detail.html`, `apps/finance/tests.py`, `docs/fiscal-webmania/*` | `finance.0044_alter_fiscaldocument_options_and_more` | `makemigrations finance --check --dry-run` OK; Fases 1, 2.1, 2.2A e 2.2B.1 direcionadas OK com 56 testes; ruff nos arquivos Python tocados OK; `git diff --check` OK | Complementar de preco/quantidade usa documento derivado local, link `complements`, tentativa `complementary_price_quantity`, payload congelado, webhook/reconciliacao somente no derivado; objetos tributarios e IBS/CBS fora do escopo | Implementada para revisao; Fase 2.2B.2 nao iniciada | UI minima usa itens JSON; complemento externo preco/quantidade permanece bloqueado sem importacao/XML validada | Aguardar revisao e aprovacao da Fase 2.2B.1 |

## Detalhes da Fase 1 - 2026-05-28

### Implementado

- Criado `FiscalEmissionAttempt` como idempotencia persistida por `workshop`, tipo documental e chave de intencao.
- Criados estados de tentativa: `created`, `sent`, `succeeded`, `failed`, `uncertain`.
- NF-e e NFS-e criam e bloqueiam tentativa antes da chamada HTTP remota.
- Timeout ou resposta remota invalida apos envio marcam tentativa como `uncertain`.
- Tentativa `uncertain` bloqueia reenvio automatico da mesma intencao.
- Payload de tentativa e respostas sao persistidos de forma sanitizada, sem headers ou credenciais.
- Webhook Webmania recebeu fingerprint persistido, constraint unica compatível e processamento idempotente.
- Webhook duplicado nao duplica efeitos; evento fora de ordem nao regride status.
- Webhook com UUID ambiguo entre oficinas fica pendente sem atualizar documento de outra oficina.
- Reconciliação operacional consulta NF-e, NFS-e e tentativas `uncertain`, sem emitir.
- Prints/debugs fiscais foram substituidos por logging sanitizado.
- NF-e passou a usar permissao `nferequest` com fallback temporario para `nfserequest`.

### Evidencias fiscais

| Risco | Evidencia |
| ----- | --------- |
| Concorrencia/duplicidade | `FiscalPhaseOneConcurrentEmissionTests.test_concurrent_nfe_emission_intention_calls_remote_once` passou e valida duas threads simultaneas com uma chamada remota. O teste sequencial `FiscalPhaseOneStabilizationTests.test_duplicate_nfe_intention_calls_remote_once_and_sanitizes_payload` tambem passou. |
| Timeout uncertain | `FiscalPhaseOneStabilizationTests.test_nfe_timeout_marks_uncertain_and_blocks_resend` passou e valida status `uncertain`. |
| `uncertain` bloqueia reenvio | Mesmo teste valida que a segunda chamada nao chama `requests.post`. |
| Webhook duplicado | `FiscalPhaseOneStabilizationTests.test_webhook_duplicate_is_idempotent_and_out_of_order_status_does_not_regress` passou. |
| Webhook fora de ordem | Mesmo teste valida que status aprovado nao regride para processando. |
| Reconciliação NFS-e sem emissão | `FiscalPhaseOneStabilizationTests.test_reconciliation_command_consults_nfse_without_emitting` passou. |
| Isolamento entre oficinas | `FiscalPhaseOneStabilizationTests.test_webhook_ambiguous_uuid_is_deferred_without_cross_workshop_update` passou. |
| Permissao legada preservada | `FiscalPhaseOneStabilizationTests.test_workshop_permission_fallback_preserves_legacy_nfe_permission` passou. |
| Ausencia de credenciais em logs/payload | Teste de duplicidade valida sanitizacao de `token`, `secret` e `headers`. |

### Comandos obrigatorios executados

| Comando | Resultado |
| ------- | --------- |
| `uv run python manage.py makemigrations --check --dry-run` | Falhou por migrations pendentes nao fiscais em `customer`, `scheduling`, `suppliers`. |
| `uv run python manage.py migrate --plan` | OK; planeja `finance.0041_fiscalemissionattempt_and_more`. |
| `uv run python manage.py test apps.finance --keepdb` | Falhou em `DreReportViewTests.test_dre_workorder_cost_total_includes_kit_service_cost`; o mesmo teste isolado falha no baseline anterior a Fase 1 com `Money('90.00') != Money('145.00')`. |
| `uv run python manage.py test apps.workshops --keepdb` | Falhou em testes de arquivo/logo/certificado Webmania, fora do escopo da Fase 1. |
| `uv run python manage.py test apps.workorder --keepdb` | Falhou em testes de OS/reabertura/assinatura/filtros, fora do escopo da Fase 1. |
| `uv run ruff check .` | Falhou por imports F401 preexistentes em `movement_group.py`, `workorder/reopening.py`, `workorder/views.py`. |
| `uv run mypy .` | Falhou com erros amplos preexistentes de stubs/tipos; branch atual mediu 2755 erros em 216 arquivos contra baseline medido de 2756 erros em 216 arquivos. |
