# PRD dominio e modelagem fiscal

## Modelo conceitual recomendado

Entidades propostas:

- `FiscalDocument`: documento fiscal unificado.
- `FiscalDocumentEvent`: eventos de webhook, eventos fiscais e transicoes locais.
- `FiscalEmissionAttempt`: tentativa persistida de emissao.
- `FiscalDocumentLink`: vinculos entre documento fiscal, origem e documentos derivados. Foi introduzido e validado na Fase 2.2A para devolucao/estorno; sera reaproveitado na Fase 2.2B com `role="complements"`.
- `NfseProviderCapabilitySnapshot`: snapshot de capacidades municipais/provedor.
- `WorkshopFiscalModelConfig`: habilitacoes por oficina/modelo.

## Compatibilidade com legado

Fase 1 deve preservar:

- `NfeRequest`, `NfseRequest`, `NfeItem`, `NfseItem`, `NfseBatch`.
- URLs e templates atuais.
- Fluxo unificado por OS.

Evolucao recomendada:

- Introduzir tentativas persistidas primeiro.
- Mapear itens legados para `FiscalDocument` apenas quando backfill for aprovado.
- Manter leitura compatível ate a Fase 8.

## Relacionamentos e cardinalidades

```text
Account 1:N Workshop
Workshop 1:N FiscalDocument
FiscalDocument 1:N FiscalEmissionAttempt
FiscalDocument 1:N FiscalDocumentEvent
FiscalDocument N:N origem via FiscalDocumentLink (a partir da Fase 2.2)
FiscalDocument N:1 customer opcional
FiscalDocument N:1 budget opcional
FiscalDocument N:1 workorder opcional
FiscalDocument N:1 financial_movement opcional
FiscalDocument N:1 original_document opcional
WorkOrder 1:N FiscalDocument
```

## Regras obrigatorias

- `WorkOrder` deve poder se relacionar com multiplos documentos fiscais.
- NF-e e NFS-e da mesma OS nao podem conflitar.
- Emissao parcial deve ser prevista.
- Documento derivado deve poder referenciar documento original.
- Status remoto bruto deve ser preservado.
- Payload enviado e resposta recebida devem ser auditaveis e sanitizados.
- Oficina e conta devem estar explicitamente associadas.

## Status internos

Proposta inicial:

- `draft`
- `ready`
- `emitting`
- `processing`
- `approved`
- `reproved`
- `canceled`
- `denied`
- `contingency`
- `invalidated`
- `closed`
- `uncertain`
- `failed`

Status remoto bruto deve permanecer em campo separado, sem normalizacao destrutiva.

## Payloads e downloads

- `FiscalEmissionAttempt.request_payload_sanitized`
- `FiscalEmissionAttempt.response_payload_sanitized`
- `FiscalDocument.remote_raw_payload`
- `FiscalDocument.downloads` ou tabela propria se houver necessidade de auditoria por arquivo
- Nenhum payload deve guardar headers secretos.

## Migrations previstas

Fase 1:

- `FiscalEmissionAttempt` ou equivalente minimo.
- Indices unicos para idempotencia.
- Campos de auditoria necessarios sem backfill destrutivo.

Fases posteriores:

- `FiscalDocument` e `FiscalDocumentEvent` na Fase 2.1; `FiscalDocumentLink` somente a partir da Fase 2.2.
- Backfill de `NfeItem`/`NfseItem`.
- Configuracoes por modelo/oficina.

## Backfill

Estratégia proposta:

- Criar backfill idempotente.
- Ler itens legados por `workshop`.
- Gerar documentos unificados por UUID/chave/status.
- Registrar divergencias sem apagar legado.
- Rodar em dry-run antes de aplicar.

## Rollback

- Fases iniciais devem manter legado como fonte operacional.
- Novas tabelas podem ser ignoradas se rollout falhar.
- Nenhuma remocao de campo legado antes da Fase 8.

## Fase 2.0 - Modelagem recomendada para NF-e/NFC-e

### Alternativas avaliadas

| Alternativa | Vantagens | Problemas | Decisao |
| ----------- | --------- | --------- | ------- |
| Criar `FiscalDocument`/`FiscalDocumentEvent` agora | Resolve documentos derivados e eventos com modelo correto e extensivel | Exige migrations e adaptacao parcial do legado antes da central fiscal | Recomendada, em versao minima e compatível, a partir da Fase 2.1. |
| Criar models legados especificos somente para NF-e | Menor impacto inicial para CC-e/NF-e | Duplica dominio e aumenta custo de migracao para Fase 8 | Rejeitada como estrategia principal. |
| Evoluir apenas `NfeItem` com campos/eventos | Rapido para CC-e | Mistura nota, evento e documento derivado; dificulta auditoria e NFC-e | Rejeitada para Fase 2. |
| Guardar eventos apenas em `WebmaniaWebhookEvent` | Sem migrations adicionais | Webhook nao representa intencao local, permissao, status de evento ou idempotencia | Rejeitada. |

### Decisao recomendada

Introduzir um nucleo unificado minimo em `apps.finance` para a Fase 2, sem backfill obrigatorio e sem substituir o legado:

- `FiscalDocument`: projecao local para documentos NF-e/NFC-e novos da Fase 2 e, opcionalmente, espelho criado no momento em que uma acao Fase 2 parte de `NfeItem` legado.
- `FiscalDocumentEvent`: eventos fiscais e operacionais vinculados a um documento, incluindo CC-e, manifestacao, IBS/CBS, cancelamento de IBS/CBS e cancelamento de NFC-e.
- `FiscalDocumentLink`: vinculos entre documento original, documento derivado e origem operacional, introduzido na Fase 2.2A.

Decisao aplicada na Fase 2.1: criar apenas `FiscalDocument`, `FiscalDocumentEvent` e extensoes minimas de `FiscalEmissionAttempt`. `FiscalDocument` e uma projecao sob demanda de `NfeItem` quando CC-e e solicitada; `FiscalDocumentLink` nao existe nessa fase. Decisao aplicada na Fase 2.2A: criar `FiscalDocumentLink` para documentos derivados de devolucao/estorno.

Essa abordagem evita tratar eventos como notas comuns e permite que documentos derivados tenham vinculo auditavel com a nota original.

### Representacao por operacao

| Operacao | Representacao local | Vinculo obrigatorio |
| -------- | ------------------- | ------------------- |
| CC-e | `FiscalDocumentEvent(kind="cce")` | `FiscalDocument` original NF-e aprovada ou espelho de `NfeItem`. |
| Manifestacao | `FiscalDocumentEvent(kind="recipient_manifestation")` | Documento/chave manifestada; pode existir sem nota emitida pelo Hunter, mas sempre com oficina. |
| IBS/CBS | `FiscalDocumentEvent(kind="ibs_cbs")` | NF-e/NFC-e original. |
| Cancelamento IBS/CBS | `FiscalDocumentEvent(kind="ibs_cbs_cancel")` | Evento IBS/CBS original e documento original. |
| Devolucao/estorno | `FiscalDocument(kind="nfe", purpose="return" ou "reversal")` | Obrigatorio: documento original por `FiscalDocumentLink(role="returns" ou "reverses")`; original pode ser local ou externo minimo. |
| Complementar | `FiscalDocument(kind="nfe", purpose="complementary")` | Obrigatorio: documento original por `FiscalDocumentLink(role="complements")`; original pode ser local ou externo minimo. |
| Ajuste | `FiscalDocument(kind="nfe", purpose="adjustment")` | Opcional: `FiscalDocumentLink(role="adjusts")` somente quando houver relacao de negocio real ou exigencia futura confirmada. |
| Nota Fiscal de Credito | `FiscalDocument(kind="nfe", purpose="credit")` | Opcional conforme tipo de credito; usar `finalidade=5` e `tipo_credito` na Fase 2.5. |
| Nota Fiscal de Debito | `FiscalDocument(kind="nfe", purpose="debit")` | Opcional/condicional conforme tipo de debito; usar `finalidade=6` e `tipo_debito` na Fase 2.5. |
| NFC-e normal | `FiscalDocument(kind="nfce", purpose="normal")` | Origem operacional ou emissao manual. |
| Cancelamento/substituicao NFC-e | `FiscalDocumentEvent(kind="cancel" ou "replacement_cancel")` | NFC-e original; substituicao somente se suporte oficial/configuracao confirmar. |

### Compatibilidade com legado

- `NfeRequest` e `NfeItem` continuam como fonte operacional das emissões atuais da Fase 1.
- A Fase 2.1 pode criar um `FiscalDocument` espelho sob demanda quando uma CC-e for emitida para `NfeItem` legado.
- O espelho deve guardar referencia segura ao `NfeItem`, alem de `workshop`, `account`, `uuid`, `chave`, `numero`, `serie`, `ambiente`, `status` e status remoto.
- Nao ha backfill em massa na Fase 2.1; backfill completo permanece Fase 8.
- Telas legadas de NF-e continuam lendo `NfeRequest`/`NfeItem`; telas novas podem consultar o nucleo fiscal minimo para eventos e historico.
- Dual-write so e permitido para a acao nova: ao emitir evento/documento derivado, atualizar o nucleo fiscal e manter campos legados existentes sem apagar nada.

### Anti-duplicidade

- Documento original legado e espelho unificado nao podem virar duas fontes independentes de emissao.
- Na Fase 2.1, a relacao de espelho e o `OneToOne`/referencia segura com `NfeItem`; a Fase 2.2A ja usa `FiscalDocumentLink` para documentos derivados reais.
- Devolucao/estorno e complementar devem usar a chave/UUID do documento original e chave idempotente propria por operacao. Ajuste nao deve ser bloqueado por ausencia de original.
- Documento derivado nao substitui documento original; ele aponta para ele.

### Fase 2.2.0 - Decisao sobre derivados e NF-e externa

| Operacao | Endpoint | Modelo local | `FiscalDocumentLink` | Origem permitida | Idempotencia | UI minima | Rollback |
| -------- | -------- | ------------ | -------------------- | ---------------- | ------------ | --------- | -------- |
| Devolucao parcial/total | `POST /1/nfe/devolucao/` | `FiscalDocument(kind="nfe", purpose="return")` | Obrigatorio para NF-e original local ou externa | NF-e emitida pelo Hunter ou NF-e externa por chave | `hash(workshop_id, derived_document_id, operation_type, request_generation)` | Wizard por nota original, selecao de produtos/quantidades, validacao de formato da chave | Desabilitar action; documentos ja emitidos ficam consultaveis |
| Estorno via devolucao | `POST /1/nfe/devolucao/` | `FiscalDocument(kind="nfe", purpose="reversal")` | Obrigatorio para NF-e original local ou externa | NF-e emitida pelo Hunter ou NF-e externa por chave | `hash(workshop_id, derived_document_id, operation_type, request_generation)` | Acao separada "Estornar por devolucao" com alerta operacional | Desabilitar action; nao reemitir automaticamente |
| Complementar preco/quantidade | `POST /1/nfe/complementar/` | `FiscalDocument(kind="nfe", purpose="complementary")` | Obrigatorio | NF-e local ou externa por chave/UUID | `nfe:complementary:{workshop}:{original_identifier}:{hash_tipo_itens_valores}` | Form de tipo de complemento e itens/valores | Desabilitar action |
| Complementar impostos | `POST /1/nfe/complementar/` | `FiscalDocument(kind="nfe", purpose="complementary_tax")` ou `purpose="complementary"` com subtipo | Obrigatorio | NF-e local ou externa por chave/UUID | `nfe:complementary_tax:{workshop}:{original_identifier}:{hash_impostos}` | Form fiscal restrito a usuarios autorizados | Desabilitar action |
| Complementar adicao/importacao | `POST /1/nfe/complementar/` | `FiscalDocument(kind="nfe", purpose="complementary_import")` ou subtipo | Obrigatorio quando houver nota original | NF-e local ou externa por chave/UUID | `nfe:complementary_import:{workshop}:{original_identifier}:{hash_adicao}` | Form especifico, inicialmente atras de confirmacao administrativa se aplicavel | Desabilitar action |
| Ajuste | `POST /1/nfe/ajuste/` | `FiscalDocument(kind="nfe", purpose="adjustment", origin="manual")` | Opcional | Emissao manual avulsa ou vinculada a NF-e local quando houver relacao | `hash(workshop_id, adjustment_document_id, operation_type, request_generation)` | Form manual com `operacao`, natureza, CFOP, ICMS, cliente e ambiente; regime tributario obrigatorio | Desabilitar action sem afetar devolucao/complementar |

NF-e externa: permitir informar chave manual de 44 digitos para devolucao e complemento. Validar apenas o formato da chave nesta fase, criar `FiscalDocument` externo minimo com `document_type="nfe"`, `origin="external"`, `access_key`, `workshop`, `account` e flag textual de que nao foi emitida localmente. Exigir confirmacao explicita do usuario autorizado antes da emissao derivada. Nao usar `/1/nfe/consulta/` como garantia de validacao de NF-e de outro emissor; importacao/validacao por XML ou API fiscal especifica fica fora da Fase 2.2A.

Idempotencia da Fase 2.2A: a identidade da transmissao deve ser o documento derivado persistido, nao apenas `original + itens + quantidades + CFOP`, porque duas devolucoes parciais legitimas podem ter payload equivalente em momentos distintos. Fluxo obrigatorio: criar documento derivado local em estado inicial; criar/bloquear `FiscalEmissionAttempt` associado ao derivado; executar uma unica chamada `POST /1/nfe/devolucao/`; atualizar somente o derivado; webhook/reconciliacao atualizam o derivado. O payload sanitizado fica congelado apos o envio.

### Fase 2.2B.0 - Planejamento da Nota Fiscal Complementar

Endpoint alvo: `POST /1/nfe/complementar/`.

Modelo recomendado para implementacao futura:

- Documento derivado: `FiscalDocument(document_type="nfe", purpose="complementary")`.
- Subtipo: novo campo ou estrutura equivalente `complementary_type` com valores `price_quantity`, `tax` e `import_addition`. Se a implementacao optar por campo persistente, usar `CharField` indexado; se usar payload inicialmente, documentar migracao futura antes de ampliar UI.
- Vinculo obrigatorio: `FiscalDocumentLink(role="complements")` do documento complementar para a NF-e original local ou externa.
- Tentativa: `FiscalEmissionAttempt(operation_type="complementary")`, associado ao `FiscalDocument` complementar derivado.
- Status/downloads: o derivado guarda `remote_uuid`, `access_key`, `series`, `number`, `receipt`, `status`, `remote_status`, `xml_url`, `danfe_url`, `request_payload` e `response_payload`. A NF-e original nao muda status por emissao, webhook ou reconciliacao da complementar.

Subtipos:

| Subtipo | Objetivo | Modelo local | Link | NF-e local | NF-e externa minima | Prioridade |
| ------- | -------- | ------------ | ---- | ---------- | ------------------- | ---------- |
| `complementary_price_quantity` | Complementar preco e/ou quantidade de itens da NF-e original | `FiscalDocument(purpose="complementary", complementary_type="price_quantity")` | Obrigatorio `complements` | Permitido com pre-preenchimento por itens fiscais originais e validacao de sequenciais/valores/quantidades | Bloqueado sem XML/importacao validada dos itens e ordem fiscal original | Alta dentro da 2.2B |
| `complementary_tax` | Complementar impostos nao destacados ou destacados a menor | `FiscalDocument(purpose="complementary", complementary_type="tax")` | Obrigatorio `complements` | Permitido com formulario tributario separado por imposto | Pode ser permitido somente com confirmacao forte, payload totalmente auditavel e permissao restrita; nao assumir validacao remota | Media/alta |
| `complementary_import_addition` | Complementar documento de adicao/importacao | `FiscalDocument(purpose="complementary", complementary_type="import_addition")` | Obrigatorio quando houver nota original | Planejado, mas baixa relevancia para oficina | Adiado ate existir fluxo de importacao/validacao adequado | Baixa; adiar por padrao |

Implementacao Fase 2.2B.1: somente `complementary_price_quantity` local foi materializado. O derivado nasce antes da chamada remota com `origin="local"`, `purpose="complementary"`, `complementary_type="price_quantity"` e link obrigatorio `FiscalDocumentLink(role="complements")`. A NF-e original nao tem status, chave, XML ou DANFE alterados pela complementar.

Complemento tributario deve separar explicitamente:

- ICMS.
- ICMS-ST.
- IPI.
- ISSQN.
- IBS/CBS.

Nao misturar complemento tributario com complemento de produto na mesma intencao inicial. Caso a Webmania aceite payloads combinados, o Hunter V2 ainda deve usar uma intencao e idempotencia por subtipo para reduzir risco operacional.

NF-e original local:

- Reutilizar `FiscalDocument` local existente ou projetar sob demanda a partir de `NfeItem` elegivel.
- Exigir oficina ativa e ownership do documento.
- Usar chave ou UUID local conforme payload validado.
- Preencher formularios com dados originais quando existirem itens fiscais, sequenciais e impostos salvos.

NF-e original externa minima:

- Permitir chave manual de 44 digitos e criar `FiscalDocument(origin="external")` minimo.
- Exigir confirmacao explicita: "Esta NF-e nao foi emitida pelo Hunter e nao foi validada remotamente pela consulta padrao".
- Bloquear `complementary_price_quantity` sem XML/importacao validada.
- Permitir `complementary_tax` externa apenas se a fase aprovada aceitar entrada manual auditada, confirmacao forte e permissao restrita.
- Adiar `complementary_import_addition` externa ate existir importacao/validacao adequada.

Idempotencia da complementar:

```text
criar FiscalDocument complementar em estado inicial
-> criar/bloquear FiscalEmissionAttempt associado ao derivado
-> executar uma unica chamada POST /1/nfe/complementar/
-> persistir retorno no derivado
-> webhook/reconciliacao atualizam apenas o derivado
```

Chave recomendada:

```text
hash(workshop_id, complementary_document_id, operation_type, request_generation)
```

O payload sanitizado deve ser congelado apos envio. Tentativa `uncertain` bloqueia reenvio automatico e exige consulta/reconciliacao.

### Fase 2.2C - Nota Fiscal de Ajuste validada

Implementacao validada somente para `POST /1/nfe/ajuste/`.

Modelo aplicado:

- Documento: `FiscalDocument(document_type="nfe", purpose="adjustment", origin="manual")`.
- Link: `FiscalDocumentLink(role="adjusts")` opcional, criado apenas quando a acao parte do detalhe de uma NF-e local existente ou quando o usuario relacionar explicitamente um documento fiscal.
- Tentativa: `FiscalEmissionAttempt(operation_type="adjustment")`, associada ao documento de ajuste criado antes do gateway.
- Regime tributario: validado por `WebmaniaCompany.regime_tributario`; permitidos `lucro_real`, `lucro_normal` e `lucro_presumido`; bloqueados Simples Nacional, MEI e regime ausente/desconhecido.
- Payload remoto: somente `operacao`, `natureza_operacao`, `codigo_cfop`, `valor_icms`, `valor_icms_st` quando preenchido, `ambiente`, `cliente`, `situacao_tributaria`, `informacoes_fisco`, `informacoes_complementares` e `url_notificacao` quando aplicavel.
- Campos proibidos nesta fase: `produtos`, `pedido`, `impostos`, IBS, CBS, `agropecuario`, importacao e adicao.
- Webhook e reconciliacao atualizam somente o documento de ajuste e nunca alteram a NF-e relacionada opcional.

Idempotencia aplicada:

```text
criar FiscalDocument de ajuste
-> criar/bloquear FiscalEmissionAttempt associado ao documento
-> congelar payload sanitizado
-> executar uma unica chamada POST /1/nfe/ajuste/
-> persistir retorno no documento de ajuste
-> webhook/reconciliacao atualizam somente o documento de ajuste
```

Chave usada:

```text
hash(workshop_id, adjustment_document_id, operation_type, request_generation)
```

### Fase 2.3.0 - Modelagem NFC-e

Decisao recomendada:

- Usar `FiscalDocument(document_type="nfce", purpose="normal", origin="manual" ou origem operacional aprovada)`.
- Criar o documento local antes do gateway, com `workshop`, `account`, ambiente, origem, payload sanitizado, status local/remoto, UUID/chave/XML/DANFE e usuario solicitante.
- Reutilizar `FiscalEmissionAttempt` com `operation_type="nfce_emission"` associado ao documento NFC-e.
- Para cancelamento simples, usar status cancelado no documento e, se necessario para auditoria granular, `FiscalDocumentEvent(event_type="cancel")`.
- Para cancelamento por substituicao, manter planejado como `FiscalDocumentEvent(event_type="replacement_cancel")`, mas nao implementar sem confirmacao oficial e nova aprovacao.
- Para inutilizacao, preferir evento fiscal operacional proprio ou `FiscalDocumentEvent(event_type="invalidation")` vinculado a oficina/modelo/serie; definir na subfase de codigo se entrara no mesmo PR ou em subfase separada.

Compatibilidade:

- `NfeRequest`/`NfeItem` continuam fonte operacional da NF-e legada.
- NFC-e deve nascer diretamente em `FiscalDocument`; nao criar `NfceRequest` legado salvo decisao futura muito justificada.
- `WebmaniaCompany` ja possui campos NFC-e e deve ser fonte local de configuracao, evitando novo model paralelo.
- NF-e e NFC-e devem ter chaves de idempotencia, filtros, permissoes e UI separados.

Cardinalidade:

```text
Workshop 1:N FiscalDocument(document_type=nfce)
FiscalDocument(nfce) 1:N FiscalEmissionAttempt(operation_type=nfce_emission)
FiscalDocument(nfce) 1:N FiscalDocumentEvent(cancel/invalidation/replacement_cancel)
Origem operacional 1:N FiscalDocument(nfce)
```

### Arquivos previstos para Fase 2.1

- Models/migrations: `apps/finance/models/finance.py`, nova migration para `FiscalDocument`, `FiscalDocumentEvent` e extensoes minimas de `FiscalEmissionAttempt`; sem `FiscalDocumentLink`.
- Services/gateways: `apps/finance/services/nfe_events.py`, extensao de `apps/finance/services/fiscal_attempts.py`.
- Views: `apps/finance/views/nfe.py`.
- Forms: formulario minimo integrado ao fluxo de detalhe NF-e ou arquivo dedicado futuro, sem criar central fiscal.
- URLs: `apps/finance/urls.py`.
- Templates: modal/form de CC-e em `apps/finance/templates/finance/`.
- Testes: `apps/finance/tests.py` ou pacote futuro de testes finance para CC-e, idempotencia, permissao, tenancy e webhook.
- Docs: atualizar `docs/fiscal-webmania/*` e log.
