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

## Auditoria IBS/CBS - Fase 2.4.0

Escopo desta auditoria: leitura de codigo em modo somente leitura para verificar se os fluxos NF-e/NFC-e ja implementados montam ou persistem dados IBS/CBS conforme a documentacao oficial Webmania para Reforma Tributaria.

| Fluxo atual | Monta IBS/CBS hoje? | Fonte dos dados | Risco atual | Correcao necessaria | Prioridade |
| ----------- | ------------------: | --------------- | ----------- | ------------------- | ---------- |
| NF-e legada | Nao diretamente | `apps/finance/services/nfe_emission.py` monta produtos com `classe_imposto`; `TaxClassNfe` nao possui campos IBS/CBS locais | Critico para producao >= `05/01/2026` se a classe remota nao estiver conforme ou se for necessario payload inline | Fase 2.4A para modelar IBS/CBS em classes fiscais/produtos; Fase 2.4B para bloquear/emitir NF-e normal conforme regra | Critica |
| NFC-e manual simples | Nao | `apps/finance/services/nfce_emission.py` monta `modelo=2` com produtos e `classe_imposto`; filtros removem `ibs`, `cbs` e `impostos` fora do escopo anterior | Critico para producao >= `05/01/2026`; NFC-e manual pode ser rejeitada sem IBS/CBS quando obrigatorio | Fase 2.4A/2.4B para configurar IBS/CBS e permitir payload conforme contrato | Critica |
| Devolucao/estorno | Nao explicitamente | `apps/finance/services/nfe_returns.py` envia chave original, CFOP, natureza, sequenciais e quantidades | Alto; pode depender de tributacao da nota original/remota, mas o Hunter nao documenta nem valida IBS/CBS derivado | Fase 2.4C deve definir se reutiliza dados originais, classe fiscal ou payload IBS/CBS especifico por devolucao/estorno | Alta |
| Complementar preco/quantidade | Nao; remove explicitamente | `apps/finance/services/nfe_complementary.py` remove `impostos`, `ibs`, `cbs` e tributos fora do escopo 2.2B.1 | Alto; complemento de produto pode exigir IBS/CBS na transicao e hoje o payload bloqueia esses campos | Fase 2.4C deve revalidar complementar de preco/quantidade com IBS/CBS sem misturar com complementar tributaria | Alta |
| Ajuste | Nao; remove explicitamente | `apps/finance/services/nfe_adjustment.py` envia ICMS/ICMS-ST de ajuste e remove `produtos`, `impostos`, `ibs`, `cbs` | Medio/alto; ajuste pode continuar sem produto, mas precisa decisao fiscal sobre aplicabilidade IBS/CBS e coexistencia | Fase 2.4C deve confirmar se ajuste exige campos IBS/CBS ou se permanece separado por finalidade/endpoint | Alta |
| Classes de imposto NF-e | Nao localmente | `TaxClassNfe`, `NfeTaxClassForm`, `_serialize_nfe_tax_class` e `_upsert_local_nfe_tax_class` cobrem ICMS/IPI/PIS/COFINS; nao guardam `ibs_cbs` | Critico; `classe_imposto` e a fonte atual dos produtos NF-e/NFC-e | Fase 2.4A deve adicionar modelagem/serializacao/localizacao dos campos IBS/CBS para classes NF-e | Critica |
| Classes de imposto NFS-e | Parcial, fora da familia NF-e/NFC-e | `TaxClassNfse` e `NfseTaxClassForm` ja possuem campos `ibs_cbs` | Nao resolve NF-e/NFC-e; indica padrao reutilizavel para NFS-e futura | Auditar NFS-e em fase propria antes de expandir NFS-e | Media |
| Credito/debito futuro | Nao implementado | Planejado na Fase 2.5.0 | Critico se implementado antes de IBS/CBS; finalidades 5/6 exigem somente IBS/CBS | Bloquear codigo funcional ate base IBS/CBS validada na Fase 2.4E | Critica |

Campos pesquisados no codigo atual: `ibs_cbs`, `situacao_tributaria`, `classificacao_tributaria`, `situacao_tributaria_regular`, `classificacao_tributaria_regular`, `ibs_estadual`, `ibs_municipal`, `cbs`, `credito_presumido`, `transferencia_credito`, `ajuste_competencia` e `estorno_credito`.

Achado principal: existe suporte local parcial a IBS/CBS apenas no lado NFS-e (`TaxClassNfse`). Para NF-e/NFC-e, a camada operacional atual depende de `classe_imposto` e de classes NF-e sem persistencia local IBS/CBS. Portanto, a conformidade NF-e/NFC-e nao pode ser presumida a partir do codigo atual.

### Auditoria tecnica inicial Fase 2.4A+B

| Item auditado | Estado real antes da implementacao | Decisao para 2.4A+B |
| ------------- | ---------------------------------- | ------------------- |
| Classe fiscal NF-e | `TaxClassNfe` guarda referencia, descricao, status, datas, informacoes e cenarios ICMS/IPI/PIS/COFINS; nao possui campos IBS/CBS | Evoluir `TaxClassNfe` existente, sem criar model paralelo |
| Sincronizacao Webmania | `save_tax_class` envia `POST /1/nfe/classe-imposto/`; `_serialize_nfe_tax_class` monta payload da classe; `_upsert_local_nfe_tax_class` persiste retorno | Incluir `ibs_cbs` na criacao/edicao quando configurado e persistir retorno sanitizado |
| NF-e normal | `_build_nfe_products_payload` envia `classe_imposto` por item; `_validate_nfe_tax_class` consulta/lista classes remotas | Manter caminho por classe fiscal e validar prontidao IBS/CBS local antes do gateway |
| NFC-e manual | `_build_product_payload` envia `classe_imposto` por produto selecionado | Manter caminho por classe fiscal e validar prontidao IBS/CBS local antes de criar/enviar documento |
| `impostos` inline | Nao e usado por NF-e normal/NFC-e manual atuais | Nao criar segundo caminho inline nesta fase |
| Ambiente | NF-e usa `settings.WEBMANIA_AMBIENT`; NFC-e recebe `environment` no fluxo manual | Aplicar bloqueio em producao e homologacao por padrao |
| Regime tributario | `WebmaniaCompany.regime_tributario` existe e ja e usado por ajuste | Usar apenas como dado auxiliar/contexto; nao inferir classificacao IBS/CBS |
