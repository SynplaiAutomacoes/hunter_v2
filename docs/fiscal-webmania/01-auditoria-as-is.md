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

### Auditoria tecnica Fase 2.4C.0 - Documentos derivados com IBS/CBS

Escopo: leitura de codigo em modo somente leitura dos services ja implementados de documentos derivados NF-e para planejar IBS/CBS sem alterar comportamento funcional.

| Fluxo atual | Service auditado | Monta IBS/CBS hoje? | Fonte dos dados fiscais atual | Risco atual | Correcao planejada |
| ----------- | ---------------- | ------------------: | ----------------------------- | ----------- | ------------------ |
| Devolucao parcial/total | `apps/finance/services/nfe_returns.py` | Nao | Documento original por `FiscalDocument`/`NfeItem`; parcial envia sequenciais fiscais em `produtos` e quantidades alinhadas; total nao envia selecao parcial | Alto: se a Webmania exigir IBS/CBS no derivado, a classe atual pode ter mudado desde a NF-e original e a NF-e externa minima nao possui itens/importos | Fase 2.4C.1 deve usar snapshot tributario original local quando disponivel, bloquear quando ausente e manter NF-e externa minima sem parcial ate importacao/XML validado |
| Estorno pelo endpoint de devolucao | `apps/finance/services/nfe_returns.py` | Nao | Chave original, natureza, ambiente, CFOP e marcador operacional interno de estorno | Alto: estorno nao pode ser tratado como devolucao parcial comum; eventual IBS/CBS deve seguir regra propria ou bloquear por falta de evidencia | Fase 2.4C.1 deve validar payload proprio de estorno, sem copiar itens/tributos cegamente, e preservar regra SC/ES ja documentada |
| Complementar preco/quantidade | `apps/finance/services/nfe_complementary.py` | Nao; remove explicitamente `impostos`, `ibs`, `cbs` e grupos tributarios fora de escopo | Produto complementar deriva do item original conhecido, substituindo apenas acrescimo de quantidade/valor, CFOP e situacao tributaria ICMS | Alto: complemento de produto pode exigir IBS/CBS, mas copiar o produto original pode repetir valores integrais ou misturar complemento tributario | Fase 2.4C.2 deve reintroduzir somente IBS/CBS aplicavel ao acrescimo, com snapshot do item original e sem abrir complementar tributaria geral |
| Ajuste | `apps/finance/services/nfe_adjustment.py` | Nao; remove `produtos`, `impostos`, `ibs`, `cbs` | Payload avulso de ajuste com ICMS/ICMS-ST, cliente, CFOP e regime tributario permitido | Medio/alto: `/1/nfe/ajuste/` e ICMS/ICMS-ST oriented no codigo atual; a aplicabilidade IBS/CBS deve ser confirmada antes de qualquer ampliacao | Fase 2.4C.3 deve manter ajuste separado, bloquear ou exigir decisao fiscal quando a operacao depender de Reforma Tributaria, e nao inserir `produtos[].impostos.ibs_cbs` sem contrato oficial |

### Auditoria tecnica Fase 2.4C.3 - Nota Fiscal de Ajuste

| Item auditado | Evidencia atual | Decisao da fase |
| ------------- | --------------- | --------------- |
| Payload | `apps/finance/services/nfe_adjustment.py` monta `operacao`, `natureza_operacao`, `codigo_cfop`, `valor_icms`, `valor_icms_st`, `ambiente`, `cliente`, `situacao_tributaria`, informacoes textuais e `url_notificacao` | Manter somente campos documentados; bloquear chaves de produto, IBS/CBS, eventos e credito/debito antes do gateway |
| Regime tributario | `validate_adjustment_tax_regime()` permite `lucro_real`, `lucro_normal`, `lucro_presumido` e bloqueia Simples/MEI/desconhecido | Preservar regra validada; nao liberar por ausencia de configuracao |
| Permissoes | `NfeAdjustmentIssueView` exige `issue_nfe_adjustment`; downloads usam `download_nfe_adjustment` | Preservar permissoes existentes; nenhuma permissao IBS/CBS ou credito/debito e reutilizada |
| Idempotencia | `FiscalEmissionAttempt(operation_type=adjustment)` e criado antes da chamada remota; `uncertain` bloqueia reenvio | Preservar sem migration |
| Webhook/reconciliacao | Resolver ajuste por UUID/chave/tentativa e atualizar somente `FiscalDocument(purpose=adjustment)` | Preservar; nao criar evento IBS/CBS nem alterar documento vinculado |
| Risco de campos indevidos | Antes da 2.4C.3, o payload normal era estreito, mas campos extra nao tinham bloqueio explicito de contrato no service | Adicionar rejeicao explicita para `produtos`, `impostos`, `ibs_cbs`, `evento_ibs_cbs`, `tipo_credito`, `tipo_debito`, `finalidade=5/6` e correlatos |

Decisao tecnica da auditoria: documentos derivados nao devem usar automaticamente a classe fiscal atual do produto como verdade historica. Para NF-e local, a fonte preferencial futura deve ser o snapshot fiscal usado na nota original; a classe atual serve apenas como apoio/validacao quando houver confirmacao fiscal explicita. Para NF-e externa minima, IBS/CBS derivado deve ficar bloqueado ate XML/importacao validada preservar itens, sequenciais e tributacao original.

### Auditoria tecnica Fase 2.4D.3 - Evento IBS/CBS 112150

| Item auditado | Estado real apos implementacao | Decisao da fase |
| ------------- | ------------------------------ | --------------- |
| Payload | `apps/finance/services/nfe_ibs_cbs_events.py` monta `chave`, `ambiente`, `cod_evento=112150`, `evento` numerico, `data_previsao_entrega` e `url_notificacao` opcional | Seguir exemplo oficial com `data_previsao_entrega` no topo; nao enviar `ibs_cbs`, `itens`, `produtos`, credito/debito ou cancelamento |
| Elegibilidade | `is_document_eligible_for_ibs_cbs_event_112150()` aceita somente NF-e normal local autorizada com chave | Bloquear NFC-e, documentos derivados, ajuste, credito/debito, documentos externos e estados nao autorizados nesta subfase |
| Modelagem | Reutiliza `FiscalDocumentEvent(event_type=ibs_cbs, event_code=112150, event_payload_type=delivery_forecast)` e `FiscalEmissionAttempt(operation_type=nfe_ibs_cbs_event)` | Nao criar `FiscalDocument`, `FiscalDocumentLink` ou migration nova |
| Idempotencia | A mesma data de previsao de entrega com evento ativo/aprovado/incerto bloqueia nova transmissao; datas diferentes reservam nova sequencia ate 20 | Preservar sequencia e payload em `uncertain`; nao reenviar automaticamente |
| Webhook | Reutiliza resolucao IBS/CBS por UUID remoto/tentativa ou fallback chave+sequencia, rejeitando ambiguidade | Atualizar somente `FiscalDocumentEvent`; nao alterar documento base nem `NfeItem` |

### Auditoria tecnica Fase 2.4D.4 - Cancelamento do Evento IBS/CBS 112150

| Item auditado | Estado real apos implementacao | Decisao da fase |
| ------------- | ------------------------------ | --------------- |
| Payload | `apps/finance/services/nfe_ibs_cbs_events.py` monta cancelamento com `uuid`, `ambiente` e `url_notificacao` opcional | Seguir contrato oficial por UUID; nao enviar `chave`, `cod_evento`, `evento`, `data_previsao_entrega`, `ibs_cbs`, produtos ou payload fiscal |
| Elegibilidade | Cancelamento 112150 exige evento original `event_type=ibs_cbs`, `event_code=112150`, status aprovado/succeeded e UUID remoto | Bloquear sem UUID, falho/rejeitado, incerto, ja cancelado, outro codigo e documento base em estado final invalido |
| Modelagem | Cria `FiscalDocumentEvent(event_type=ibs_cbs_cancellation, event_code=112150, related_event=<112150>)` e tentativa `nfe_ibs_cbs_event_cancellation` | Nao criar `FiscalDocument`, nao usar `FiscalDocumentLink`, preservar trilha auditavel separada |
| Idempotencia | Constraint ativa de `related_event + event_type` e tentativa persistida bloqueiam duplicidade/concorrencia | Timeout deixa cancelamento `uncertain` e impede novo cancelamento automatico |
| Webhook | Reutiliza resolucao de cancelamento IBS/CBS por UUID remoto/tentativa, rejeitando ambiguidade | Atualizar somente evento de cancelamento e marcar evento original como cancelado em retorno positivo; nao alterar documento base nem `NfeItem` |

### Auditoria tecnica Fase 2.4D.5.0 - Eventos IBS/CBS 112120/112130/112140

Escopo: leitura de codigo em modo somente leitura para planejar eventos IBS/CBS de emitente que exigem itens, valores e controle operacional.

| Item auditado | Estado real atual | Impacto para 112120/112130/112140 |
| ------------- | ----------------- | ---------------------------------- |
| Service de eventos | `apps/finance/services/nfe_ibs_cbs_events.py` possui builders/transmissao para `112110`, `112150` e seus cancelamentos; constantes atuais cobrem apenas esses codigos | Reaproveitar transmissao, sanitizacao, sequencia e tentativa; criar builders por codigo para eventos com itens |
| Modelagem | `FiscalDocumentEvent` ja possui `event_code`, `event_sequence`, `event_payload_type`, payload/resposta, UUID remoto e `related_event` para cancelamento | Nao exige nova entidade para os tres eventos; exige `event_payload_type` especifico por codigo |
| Idempotencia | `FiscalEmissionAttempt(operation_type=nfe_ibs_cbs_event)` ja protege evento emitido; `uncertain` bloqueia reenvio | Reutilizar; chave deve incluir documento, codigo, sequencia e geracao |
| Webhook | Resolve evento IBS/CBS por UUID remoto, tentativa e fallback chave+sequencia, rejeitando ambiguidade | Reutilizar, mas garantir filtro por `event_code` e candidato unico para eventos com itens |
| Views/templates | Detalhe de NF-e expõe apenas acoes de `112110`, `112150` e cancelamentos validados | UI futura deve ser por codigo, sem formulario generico JSON |
| Testes | `apps/finance/tests.py` cobre 112110/112150, idempotencia, concorrencia, webhook, permissao, downloads e cancelamentos | Novos testes devem reaproveitar base e adicionar validacao de itens, valores IBS/CBS e controle operacional |
| Fonte fiscal de itens | Derivados 2.4C usam snapshot original em `FiscalDocument.request_payload`, `response_payload`, `NfeItem.raw_payload` e `log_payload`; NF-e/NFC-e normal usa `classe_imposto` | Eventos com itens devem usar snapshot fiscal do documento emitido; `TaxClassNfe` atual nao e fallback automatico |
| Documentos externos | NF-e externa minima por chave nao contem itens ou sequenciais fiscais | Bloquear eventos com itens para documento externo sem XML/importacao validada |

Conclusao: a infraestrutura tecnica de evento esta pronta para ser reutilizada, mas os tres codigos exigem regras de negocio distintas. O risco principal nao e HTTP/Webmania; e a fonte local confiavel para sequencial fiscal, valores IBS/CBS, quantidade/unidade e contexto operacional.

### Auditoria tecnica Fase 2.4D.6.0 - Eventos IBS/CBS 112120 e 112140

Escopo: leitura de codigo em modo somente leitura para decidir se os eventos restantes do grupo `112xxx` podem ser implementados com seguranca agora.

| Fonte exigida | Evidencia no codigo atual | Existe fonte confiavel para 112120/112140? | Impacto |
| ------------- | ------------------------- | ------------------------------------------ | ------- |
| XML/importacao validada de NF-e externa | `apps/stock/forms.py` e `apps/stock/utils.py` possuem importacao/parser XML para estoque, mas isso nao projeta automaticamente `FiscalDocument` externo com itens fiscais, sequenciais, IBS/CBS e origem validada para eventos Webmania | Parcial e fora do dominio fiscal de eventos | Exige fase preparatoria para transformar XML/importacao em snapshot fiscal auditavel antes de permitir eventos com itens em documentos externos |
| Snapshot fiscal por item | `FiscalDocument.request_payload`, `FiscalDocument.response_payload`, `NfeItem.raw_payload` e `NfeItem.log_payload` sao usados por devolucao/complementar/evento `112130` | Parcial para NF-e local ja emitida/projetada; nao garante importacao ALC/ZFM nem nota de debito antecipado | Pode apoiar validacao de item/sequencial, mas nao basta para `112120` ou `112140` sem contexto de negocio especifico |
| Controle de estoque com perda/perecimento | `112130` aceita input fiscal confirmado para perecimento/perda/roubo/furto; app `stock` controla importacoes/produtos, mas nao ha evento operacional fiscal de conversao em isencao ALC/ZFM ou nao fornecimento antecipado | Nao para `112120`/`112140` | Criar evento agora exigiria input manual sem origem operacional suficiente |
| Controle de transporte | `112130` foi implementado com confirmacao fiscal manual; nao ha fluxo de transporte fiscal para ALC/ZFM ou pagamento antecipado | Nao aplicavel/suficiente | Nao desbloqueia `112120`/`112140` |
| Pagamento antecipado | `FinancialMovement`, `PaymentMethod` e `WorkOrderPaymentMethod` existem, mas representam financeiro operacional/OS; nao ha modelagem fiscal de pagamento antecipado vinculado a nota de debito e item fiscal | Nao | `112140` deve ficar bloqueado ate modelagem de pagamento antecipado fiscal e/ou nota de debito |
| Nota de debito/credito | Fase 2.5.0 decidiu adiar credito/debito porque finalidades 5/6 dependem de IBS/CBS e regras exclusivas | Nao | `112140` referencia item da nota de debito de pagamento antecipado; bloquear ate credito/debito ou fluxo equivalente ser validado |
| Vinculo financeiro -> item fiscal | O financeiro registra movimentos e pagamentos por OS, mas nao ha vinculo auditavel entre pagamento antecipado, item fiscal e sequencial de nota de debito | Nao | Sem esse vinculo, `quantidade_nao_fornecida` seria input manual de alto risco |
| Quantidade/unidade nao fornecida | Nao ha entidade operacional de nao fornecimento associada a nota de debito/pagamento antecipado | Nao | Exige fase propria de regra financeira/operacional antes de `112140` |

## Auditoria Fase 2.5.1.0 - fontes locais para credito/debito

| Hipotese oficial | Fonte atual encontrada | Suficiente? | Lacuna impeditiva |
| --- | --- | ---: | --- |
| Multa/juros | `FinancialMovement`, `PaymentMethod` e parcelas de OS possuem valores/taxas operacionais | Nao | Nao ha classificacao fiscal de multa/juros IBS/CBS nem vinculo por item ao DF-e regularizado. Taxa de meio de pagamento nao equivale a multa/juros fiscal. |
| Credito presumido IBS ZFM | Classe fiscal suporta grupos IBS/CBS; nao ha saldo ZFM/apuracao | Nao | Falta fonte de apuracao, elegibilidade ZFM e saldo de credito presumido. |
| Recusa total/nao localizacao | Existem rejeicoes operacionais de OS, nao evento logistico fiscal de entrega | Nao | Falta prova de entrega/recusa vinculada a NF-e e aos itens fiscais. |
| Reducao de valores | Documentos e movimentos guardam valores | Nao | Falta causa fiscal, base anterior, itens afetados e regra de calculo auditavel. |
| Sucessao/transferencia | Nao localizado dominio de sucessao empresarial | Nao | Falta entidade sucessora, saldo transferido e fundamento fiscal. |
| Cooperativas | Nao localizado dominio fiscal de cooperativas | Nao | Falta classificacao do participante e credito transferido. |
| Saidas imunes/isentas | Classe fiscal possui configuracao tributaria, mas nao apuracao consolidada | Nao | Falta apuracao e rastreio das saidas que originaram a anulacao. |
| NFs nao processadas na apuracao | Documentos fiscais existem; nao ha livro/apuracao IBS/CBS local | Nao | Falta periodo de apuracao, motivo de nao processamento e `dfe_referenciado` por item. |
| Pagamento antecipado | Pagamentos de OS e movimentos financeiros existem | Nao | Falta conceito fiscal de adiantamento e vinculo pagamento -> item fiscal -> nota de debito. |
| Perda em estoque | `StockMovement` registra entrada/saida/status | Nao | Falta motivo fiscal de perda, snapshot IBS/CBS e vinculo ao item/documento que originou o credito. |
| Desenquadramento do SN | `WebmaniaCompany.regime_tributario` guarda regime atual | Nao | Falta historico de transicao, data de efeito e apuracao do debito. |
| Documento original local | `FiscalDocument` guarda payload/resposta e links | Parcial | Pode fornecer chave/snapshot, mas nao prova a hipotese legal nem a apuracao de cada tipo. |
| Documento externo | `StockImport`/XML e documento externo minimo existem em fluxos distintos | Nao | Nao ha projecao fiscal externa validada e vinculada ao item para credito/debito. |

Conclusao: nenhum tipo possui hoje fonte local completa e confiavel. A infraestrutura fiscal e reutilizavel, mas nao substitui a modelagem das hipoteses legais. A Fase 2.5.1 funcional deve permanecer bloqueada.

### Resultado tecnico da Fase 2.5.1P

- `FiscalDocument`, `NfeItem.raw_payload/log_payload` e os payloads do documento fornecem o snapshot historico por item.
- `TaxClassNfe` continua sendo configuracao atual e nao e fallback para documento ja emitido.
- `FinancialMovement` e `StockMovement` agora podem ser referenciados opcionalmente por uma base, sem serem reinterpretados automaticamente como fato fiscal.
- `FiscalReferencedBasis` prepara e aprova dados locais; nao cria `FiscalDocument`, `FiscalEmissionAttempt` nem chama Webmania.
- Documento externo permanece bloqueado sem projecao externa e XML/importacao realmente validada.

## Auditoria Fase 2.5.2.0 - capacidade real da base preparada

`FiscalReferencedBasis` congela chave, sequencial e snapshot `ibs_cbs`, mas nao congela ainda o snapshot comercial completo exigido em `produtos[]` (`nome`, NCM, quantidade, unidade, subtotal, total e CFOP) nem valores tipados de principal, multa e juros por item. `FinancialMovement.amount` e agregado e nao identifica parcela fiscal, item ou composicao multa/juros. As evidencias em `notes` sao auditaveis, mas nao substituem fonte monetaria estruturada.

Conclusao: a 2.5.1P resolve identidade, tenancy, snapshot tributario e aprovacao, mas ainda nao fornece base quantitativa suficiente para transmitir qualquer tipo com seguranca.

Conclusao 2.4D.6.0: o codigo ja possui infraestrutura tecnica reutilizavel para `FiscalDocumentEvent`, idempotencia, webhook e cancelamento por UUID, mas nao possui fontes de dominio suficientemente confiaveis para liberar `112120` ou `112140` agora. A decisao recomendada e adiar ambos e planejar uma fase preparatoria antes de qualquer implementacao funcional.
## Auditoria Fase 2.5.2P - fonte monetaria e comercial

- `FiscalReferencedBasis` ja e escopada por oficina, documento e sequencial fiscal, mas a 2.5.1P congelava somente identidade e `ibs_cbs_snapshot`.
- `FiscalDocument.request_payload/response_payload` e `NfeItem.raw_payload/log_payload` sao as fontes historicas permitidas para descricao, codigo, NCM, CFOP, quantidade, unidade, valor unitario e total.
- `FinancialMovement.amount` usa Decimal/Money, mas e agregado: nao separa principal, multa e juros por item e permanece apenas como evidencia vinculada.
- O padrao de arredondamento fiscal existente usa `Decimal`, duas casas para dinheiro, seis para quantidade e `ROUND_HALF_UP`.
- Cadastro atual de produto e `TaxClassNfe` nao sao fontes historicas validas e nao sao usados como fallback.
## Auditoria Fase 2.5.3.0 - credito tipo 1

- A Fase 2.5.2P foi validada no checkpoint `638d4c12`; `FiscalReferencedBasisItem` fornece item, CFOP historico, quantidade, unitario, total original e composicao explicita `multa + juros`.
- A base local resolve rastreabilidade e imutabilidade, mas nao define a semantica fiscal do novo produto de credito.
- A documentacao oficial confirma `POST /1/nfe/emissao/`, `finalidade=5`, `tipo_credito=1`, `nfe_referenciada[]`, `codigo_cfop` na raiz e somente `impostos.ibs_cbs`.
- `dfe_referenciado` e documentado apenas para debito tipos 3/4; nao deve ser enviado no credito tipo 1.
- Lacuna bloqueante: nao ha regra oficial consultada para converter multa/juros em `quantidade`, `subtotal`, `total` ou para derivar/proporcionar os valores IBS/CBS. Copiar o item ou imposto original seria inferencia insegura.
## Resultado tecnico Fase 2.5.3P

- `FiscalCreditProductPreview` foi criado como entidade local versionada por base/revisao.
- Reutiliza somente `FiscalReferencedBasis` aprovada, `FiscalReferencedBasisItem` congelado e `ibs_cbs_snapshot`; nao consulta cadastro atual nem `TaxClassNfe`.
- Form/view atuais da base foram reutilizados apenas para navegacao; a previa possui quatro permissoes proprias e tenancy por oficina.
- Nao foram adicionados purpose `credit`, operation type remoto, gateway, webhook ou reconciliacao.

## Resultado tecnico Fase 2.5.4

A emissao de credito tipo 1 reutiliza os helpers da NF-e normal para `cliente` e `pedido`, mas consome `produtos[]` exclusivamente da `FiscalCreditProductPreview` aprovada. O novo service transmite somente `modelo=1`, `finalidade=5`, `tipo_credito=1` e `impostos.ibs_cbs`; nenhum dado fiscal e recalculado a partir de `TaxClassNfe` ou cadastro atual.

## Resultado tecnico Fase 2.5.5

O cancelamento do credito reutiliza a estrutura `FiscalDocumentEvent`/`FiscalEmissionAttempt` do cancelamento NFC-e, com service separado e filtros estritos de NF-e, `purpose=credit` e tipo `1`. O cancelamento legado de `NfeItem` nao foi alterado. Webhook e reconciliacao atuam somente no evento/documento de credito.

## Auditoria incremental - Fase 2.5.6.0

Estado comprovado em 2026-06-22, sem alteracao funcional:

- o checkpoint `5d612544` encerrou o ciclo do credito tipo 1: `FiscalReferencedBasis`, `FiscalReferencedBasisItem`, snapshots comerciais/monetarios, `FiscalCreditProductPreview`, emissao e cancelamento;
- a base referenciada preserva chave da NF-e, sequencial fiscal, CFOP, snapshot IBS/CBS e composicao multa + juros por item;
- `FiscalCreditProductPreview` e semanticamente restrita a credito tipo 1 e nao deve ser reutilizada diretamente para debito;
- nao existe preview, documento, tentativa, permissao ou UI funcional de debito;
- `112120` continua sem fonte local ALC/ZFM validada; `112140` continua sem fonte de pagamento antecipado/nao fornecimento;
- eventos `211xxx` continuam dependentes de papel de destinatario, entrada/importacao fiscal, estoque ou apuracao externa;
- NFS-e existente e legado operacional que exige auditoria IBS/CBS propria antes de expansao; CT-e ainda nao possui dominio operacional local.

### Auditoria tecnica inicial da Fase 2.5.6P

- `FiscalReferencedBasis` concentra chave, hipotese fiscal, snapshot IBS/CBS, origem financeira e aprovacao congelada.
- `FiscalReferencedBasisItem` concentra identidade fiscal sequencial, snapshot comercial e base monetaria imutavel, incluindo multa, juros e soma.
- `FiscalCreditProductPreview` possui model, service, forms, views, templates e testes proprios; sua semantica e imutavel para `finalidade=5`/`tipo_credito=1` e nao sera convertida.
- `fiscal_credit_product_preview.py` valida quantidade, unitario, total, CFOP, IBS/CBS exclusivo, feature flag e ausencia de fallback atual.
- `WebmaniaCompany.credit_debit_basis_enabled` e flag preparatoria geral ja existente; sera reutilizada, mas nao concede permissao nem abre emissao de debito.
- permissoes de credito sao especificas e nao concedem acesso a preview de debito.
- emissao/cancelamento de credito usam services e tentativas remotas proprios; a preview de debito nao os importara nem chamara.

## Auditoria incremental - Fase 2.5.7.0

## Auditoria implementada - Fase 2.5.7

- A emissao usa exclusivamente `FiscalDebitProductPreview` aprovada, base aprovada e NF-e original local autorizada.
- O produto preserva CFOP, valores e `dfe_referenciado` congelados; `impostos` aceita somente `ibs_cbs` do snapshot aprovado.
- `FiscalDocument(purpose="debit", fiscal_purpose_type="4")`, link `debits` e tentativa `nfe_debit_emission` existem antes do gateway.
- Webhook resolve UUID/chave globalmente sem associacao ambigua; reconciliacao usa somente consulta remota.
- Nenhum cancelamento ou outro tipo de debito foi aberto.
- checkpoint `189bf973` validou `FiscalDebitProductPreview`, migration `0057`, permissao, tenancy, imutabilidade e ausencia de gateway remoto;
- a preview aprovada contem chave/item em `dfe_referenciado`, produto comercial, quantidade, unitario, total, CFOP e snapshot IBS/CBS exclusivo;
- `FiscalDocument` ainda nao possui `purpose="debit"`, campo `debit_product_preview` ou constraint de documento de debito;
- `FiscalDocumentLinkRole` ainda nao possui `debits`;
- `FiscalEmissionOperationType` ainda nao possui `nfe_debit_emission`;
- nao existem service, view, URL, webhook/reconciliacao ou permissoes de emissao/download de debito;
- o fluxo de credito tipo 1 comprova a infraestrutura reutilizavel de auth, cliente, pedido, idempotencia, status, webhook, reconciliacao e downloads;
- a primeira emissao de debito deve ficar restrita a origem local, pois cliente/pedido sao derivados da NF-e operacional local; origem externa exige fase propria.
