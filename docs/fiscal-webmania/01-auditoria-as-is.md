# Auditoria as-is fiscal

Data da auditoria: 2026-05-28.

Escopo: codigo fonte atual do repositorio. Arquivos `__pycache__` nao foram considerados evidencia valida.

## Estado Git observado

| Item                                   | Estado           |
| -------------------------------------- | ---------------- |
| `webmania_fiscal_openapi_context.json` | Nao rastreado    |
| `docs/fiscal-webmania/`                | Criado na Fase 0 |

## Inventario de codigo fiscal atual

| Tema                       | Arquivo real                                                                                | Classe/funcao real                                                                  | Evidencia                                                                            | Observacoes                                                                     |
| -------------------------- | ------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------- |
| Models fiscais             | `apps/finance/models/finance.py`                                                            | `NfeRequest`, `NfseRequest`, `NfeItem`, `NfseItem`, `NfseBatch`                     | Campos `workshop`, `workorder`, `uuid`, status, URLs XML/PDF/DANFE                   | Dominio legado centrado em OS                                                   |
| Classes fiscais            | `apps/finance/models/finance.py`                                                            | `TaxClassNfe`, cenarios ICMS/IPI/PIS/COFINS, `TaxClassNfse`, `TaxClassPreset`       | Unicidade por `workshop` e `reference`                                               | Base reutilizavel para Fase 1/2/3                                               |
| Empresa Webmania           | `apps/finance/models/finance.py`                                                            | `WebmaniaCompany`                                                                   | Credenciais, dados da empresa, series, numeros, certificado snapshot                 | `workshop` e OneToOne nullable                                                  |
| Webhook persistido         | `apps/finance/models/finance.py`                                                            | `WebmaniaWebhookEvent`                                                              | `model`, `event_uuid`, `payload`, `processed_at`, `processing_error`                 | Sem fingerprint unico                                                           |
| URLs fiscais               | `apps/finance/urls.py`                                                                      | Rotas `nfe`, `nfse`, `emissao`, `webmania/webhook`                                  | Rotas de listagem, detalhe, reconciliacao, cancelamento, download, inutilizacao NF-e | Fiscal dentro de `apps.finance`                                                 |
| Emissao unificada          | `apps/finance/views/emission.py`                                                            | `EmissionRequestCreateView`                                                         | `dynamic_steps_by_mode` inclui `nfe`, `nfse`, `both`                                 | Permite NF-e e NFS-e da mesma OS                                                |
| Emissao NF-e               | `apps/finance/services/nfe_emission.py`                                                     | `build_nfe_payload`, `emit_nfe_request`, `sync_nfe_emission_response`               | Chamada `POST /1/nfe/emissao/`, payload com produtos, cliente, pedido                | Payload enviado nao e persistido antes da chamada                               |
| Emissao NFS-e              | `apps/finance/services/emission.py`                                                         | `build_nfse_payload`, `emit_nfse_request`, `sync_emission_response`                 | Chamada `POST /2/nfse/emissao`, payload com RPS e tomador                            | Possui fallback para impostos explicitos                                        |
| Preview                    | `apps/finance/services/nfe_emission.py`, `apps/finance/services/emission.py`                | `preview_*`, `download_*_preview_document`                                          | Usa `previa_danfe=True`                                                              | Preview faz chamadas remotas                                                    |
| Cancelamento NF-e          | `apps/finance/views/nfe.py`, `services/nfe_emission.py`                                     | `NfeRequestCancelView`, `cancel_nfe_document`                                       | Status permitido `aprovado`, `contingencia`; `PUT /1/nfe/cancelar/`                  | Atualiza item local apos resposta                                               |
| Inutilizacao NF-e          | `apps/finance/views/nfe.py`, `services/nfe_emission.py`                                     | `NfeRequestInvalidateView`, `invalidate_nfe_number`                                 | `PUT /1/nfe/inutilizar/`                                                             | Permitida quando numero reservado e item reprovado/denegado ou sem item         |
| Cancelamento NFS-e         | `apps/finance/views/nfse.py`, `services/emission.py`                                        | `NfseRequestCancelView`, `cancel_nfse_document`                                     | Motivos 1, 2, 4; `PUT /2/nfse/cancelar`                                              | Atualiza item local apos resposta                                               |
| Downloads                  | `apps/finance/views/nfe.py`, `apps/finance/views/nfse.py`, `services/webmania_documents.py` | `NfeDocumentDownloadView`, `NfseDocumentDownloadView`, `download_webmania_document` | Baixa URL retornada pela Webmania usando headers da oficina                          | Autorizacao por `WorkshopScopedMixin`                                           |
| Central de emitidas        | `apps/finance/views/issued_documents.py`                                                    | `IssuedDocumentsListView`, `IssuedDocumentsArchiveDownloadView`                     | Filtros por periodo/tipo/search; zip XML/PDF                                         | Busca so NF-e/NFS-e                                                             |
| Reconciliacao              | `apps/finance/management/commands/reconcile_webmania_documents.py`                          | `Command.handle`                                                                    | Processa webhooks pendentes e reconcilia `NfeItem` em `processando/contingencia`     | Nao reconcilia NFS-e no comando atual                                           |
| Consulta NF-e              | `apps/finance/services/nfe_consulta.py`                                                     | `consult_nfe_item`, `reconcile_nfe_item`                                            | Usa UUID ou chave em `GET /1/nfe/consulta/`                                          | Salva `last_sync_error` em falha                                                |
| Consulta NFS-e             | `apps/finance/services/nfse_consulta.py`                                                    | `consult_nfse_item`, `reconcile_nfse_item`                                          | Usa endpoint configurado com `event_uuid`                                            | Diverge do guia oficial que documenta `GET /2/nfse/consulta`                    |
| Autenticacao               | `apps/finance/services/webmania_auth.py`                                                    | `build_webmania_headers`, `should_use_global_webmania_auth`                         | Homologacao usa global; producao tenta credenciais da empresa por oficina            | API v2 futura precisa bearer consistente                                        |
| Segredos                   | `apps/finance/services/webmania_secrets.py`                                                 | `encrypt_secret`, `decrypt_secret`                                                  | Usado em empresa Webmania                                                            | Manter reutilizacao                                                             |
| Certificado e logo         | `apps/workshops/services/files.py`                                                          | `save_workshop_certificate_atomic`, `save_workshop_logo_atomic`                     | Storage S3, rollback e sync Webmania                                                 | Reutilizar obrigatoriamente                                                     |
| Permissoes                 | `apps/workshops/mixin.py`                                                                   | `WorkshopScopedMixin`                                                               | Filtra queryset por `workshop`; valida `has_workshop_perm`                           | Base de tenancy fiscal                                                          |
| Permissao Webmania empresa | `apps/finance/views/common.py`                                                              | `DirectorWorkshopAccessMixin`                                                       | Diretor/gerente + permissao especifica opcional                                      | Usado para empresa Webmania                                                     |
| Testes existentes          | `apps/finance/tests.py`, `apps/finance/test_list_filters.py`                                | Testes Django                                                                       | Arquivos existem                                                                     | Fase 1 deve levantar cobertura especifica fiscal antes de alterar comportamento |

## Capacidades atuais

| Funcionalidade                | Existe hoje? | Evidencia                                             | Limitacoes                                   |
| ----------------------------- | -----------: | ----------------------------------------------------- | -------------------------------------------- |
| Emissao NF-e                  |          Sim | `emit_nfe_request`                                    | Apenas OS/produtos; sem tentativa persistida |
| Emissao NFS-e                 |          Sim | `emit_nfse_request`                                   | Apenas OS/servicos; sem tentativa persistida |
| NF-e e NFS-e na mesma OS      |          Sim | `note_mode = both`                                    | Estado controlado por sessao e cache         |
| NFC-e                         |      Parcial | `WebmaniaCompany` tem campos NFC-e                    | Sem fluxo de emissao NFC-e                   |
| CT-e/CT-e OS                  |          Nao | Sem models/views/services fonte                       | Apenas previsto em docs futuras              |
| MDF-e                         |          Nao | Sem models/views/services fonte                       | Apenas previsto em docs futuras              |
| NFCom                         |          Nao | Sem models/views/services fonte                       | Baixa prioridade                             |
| DC-e                          |          Nao | Sem feature flag atual localizada                     | Deve ser beta                                |
| Webhook NF-e/NFS-e            |          Sim | `WebhookView`, `webmania_webhooks.py`                 | Sem fingerprint unico; modelos limitados     |
| Reconciliacao NF-e            |          Sim | management command e view                             | Comando nao cobre NFS-e                      |
| Reconciliacao NFS-e           |      Parcial | `NfseRequestReconcileView`                            | Sem comando operacional atual                |
| Download individual           |          Sim | `NfeDocumentDownloadView`, `NfseDocumentDownloadView` | Depende de URLs remotas                      |
| Download em lote              |          Sim | `IssuedDocumentsArchiveDownloadView`                  | Apenas NF-e/NFS-e                            |
| Inutilizacao NF-e             |          Sim | `NfeRequestInvalidateView`                            | Somente numeracao reservada                  |
| Carta de correcao             |          Nao | Sem rota/service atual                                | Fase 2                                       |
| Devolucao/complementar/ajuste |          Nao | Sem rota/service atual                                | Fase 2                                       |
| Substituicao NFS-e            |          Nao | Sem rota/service atual                                | Fase 3                                       |

## Problemas tecnicos reais identificados

| Problema                                          | Evidencia de codigo                                                                      | Risco                                                                                            | Severidade | Solucao sugerida                                                                    | Fase |
| ------------------------------------------------- | ---------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ | ---------- | ----------------------------------------------------------------------------------- | ---- |
| Idempotencia principal usa cache                  | `EmissionRequestCreateView._acquire_submission_lock` em `apps/finance/views/emission.py` | Cache nao protege contra perda de estado, timeout pos-envio ou processos independentes           | Alta       | Criar `FiscalEmissionAttempt` persistido com lock transacional e estado `uncertain` | 1    |
| Payload enviado nao e persistido antes da chamada | `emit_nfe_request`, `emit_nfse_request` fazem `requests.post` antes de salvar tentativa  | Sem auditoria completa e risco de reenvio em estado incerto                                      | Alta       | Persistir tentativa e payload sanitizado antes de chamada remota                    | 1    |
| Reconciliacao por comando cobre so NF-e           | `reconcile_webmania_documents.py` importa apenas `NfeItem`                               | NFS-e pode ficar divergente sem rotina operacional                                               | Media      | Expandir comando para NFS-e e webhooks pendentes por modelo                         | 1    |
| Webhook sem fingerprint unico                     | `WebmaniaWebhookEvent` nao tem unique constraint                                         | Eventos duplicados geram multiplos registros e processamento repetido                            | Media      | Criar fingerprint/hash e processamento idempotente                                  | 1    |
| Webhook resolve por UUID global sem oficina       | `NfeItem.objects.filter(uuid=event_uuid).first()`                                        | Se UUID nao for globalmente unico ou houver dados legados duplicados, pode atualizar item errado | Alta       | Resolver por UUID + modelo + origem/empresa quando possivel; auditar duplicados     | 1    |
| Permissoes NF-e reaproveitam `nfserequest`        | `NfeRequestListView.workshop_permission_model = "nfserequest"`                           | Permissoes fiscais ficam imprecisas                                                              | Media      | Definir matriz fiscal e compatibilidade temporaria                                  | 1/6  |
| `print` em paths fiscais                          | `nfe_emission.py` e debug helpers em services                                            | Risco de log sensivel e ruido operacional                                                        | Media      | Substituir por logger sanitizado e toggles seguros                                  | 1    |
| Dominio atual depende de OS                       | `NfeRequest.workorder`, `NfseRequest.workorder` obrigatorios                             | Bloqueia emissao manual, por orcamento ou financeiro                                             | Alta       | Introduzir modelagem de origem fiscal e compatibilidade com legado                  | 4/8  |

## Diagrama textual dos models atuais

```text
Workshop
  -> WebmaniaCompany (OneToOne nullable)
  -> TaxClassNfe (1:N)
      -> TaxClassNfeIcmsScenario (1:N)
      -> TaxClassNfeIpiScenario (1:N)
      -> TaxClassNfePisScenario (1:N)
      -> TaxClassNfeCofinsScenario (1:N)
  -> TaxClassNfse (1:N)
  -> TaxClassPreset (1:N)
  -> NfeRequest (1:N)
      -> WorkOrder (N:1)
      -> NfeItem (1:N via request nullable)
  -> NfseRequest (1:N)
      -> WorkOrder (N:1)
      -> NfseBatch (1:N via request nullable)
      -> NfseItem (1:N via request nullable)
WebmaniaWebhookEvent
  -> payload/event_uuid sem FK direta
```

## Mapa de chamadas atual

```text
Fluxo unificado:
EmissionRequestCreateView
-> forms de wizard
-> _get_or_create_nfe_request/_get_or_create_nfse_request
-> emit_nfe_request/emit_nfse_request
-> build_webmania_headers
-> Webmania
-> sync_nfe_emission_response/sync_emission_response
-> NfeItem/NfseItem/NfseBatch
-> webhook/reconciliacao/download atualizam os mesmos itens

Webhook:
WebhookView
-> store_webhook_event
-> process_webhook_event
-> apply_nfe_item_payload/apply_nfse_item_payload/apply_nfse_batch_payload

Downloads:
NfeDocumentDownloadView/NfseDocumentDownloadView/IssuedDocumentsArchiveDownloadView
-> download_webmania_document
-> build_webmania_headers
-> URL remota retornada pela Webmania
```
