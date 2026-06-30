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
## Atualizacao Fase 2.3.2 - Evento De Cancelamento NFC-e

- Cancelamento padrao NFC-e nao cria novo `FiscalDocument`.
- O evento e representado em `FiscalDocumentEvent(event_type="cancellation")`, associado ao `FiscalDocument(document_type="nfce", purpose="normal", origin="manual")`.
- `FiscalEmissionAttempt(operation_type="nfce_cancellation")` referencia documento e evento.
- `FiscalDocumentLink` nao e usado para cancelamento padrao.
- A NFC-e original so altera `status` para `cancelado` apos resposta remota, webhook ou reconciliacao valida.
- A migration da fase altera somente choices/permissoes; nao ha backfill nem alteracao destrutiva do legado.

## Atualizacao Fase 2.3.3 - Modelagem da Inutilizacao NFC-e

- Inutilizacao nao e evento de documento emitido; representa numero ou intervalo que nao deve existir como NFC-e.
- Entidade criada: `FiscalNumberInutilization`.
- Campos principais: oficina, conta, `document_type="nfce"`, ambiente, serie, sequencia inicial/final, motivo, status local, status remoto, payload enviado sanitizado, resposta sanitizada, UUID/protocolo/XML quando retornados, solicitante e timestamps.
- `FiscalEmissionAttempt` foi estendido com FK opcional para `FiscalNumberInutilization` e `operation_type="nfce_inutilization"`.
- Constraints/indices: check `sequence_start <= sequence_end`, indice de escopo/status por oficina-modelo-ambiente-serie e indice de faixa por oficina-modelo-ambiente-serie-inicio-fim.
- Sobreposicao de faixas e bloqueio contra NFC-e local conhecida sao garantidos por service transacional com lock da configuracao `WebmaniaCompany` da oficina.
- `FiscalDocument`, `FiscalDocumentEvent`, `FiscalDocumentLink` e `NfeItem` nao sao criados nem alterados pela inutilizacao NFC-e.

## Fase 2.5.0 - Modelagem planejada para Nota Fiscal de Credito e Debito

Decisao recomendada:

- Credito fiscal: `FiscalDocument(document_type="nfe", purpose="credit", origin="manual")`.
- Debito fiscal: `FiscalDocument(document_type="nfe", purpose="debit", origin="manual")`.
- Nao criar models legados paralelos (`NfeCreditRequest`, `NfeDebitRequest`) e nao reutilizar `NfeItem` como fonte operacional.
- Adicionar campo futuro `fiscal_purpose_type` ou equivalente em `FiscalDocument` para preservar `tipo_credito` ou `tipo_debito` remoto. O valor deve ser armazenado como codigo bruto validado, com label interno versionado no codigo/documentacao.
- Preservar payload sanitizado enviado e resposta sanitizada recebida, pois a semantica desses documentos pode mudar com IBS/CBS/Reforma Tributaria.

Vinculo com documentos anteriores:

- `FiscalDocumentLink(role="credits")` para nota de credito sera opcional/condicional.
- `FiscalDocumentLink(role="debits")` para nota de debito sera opcional/condicional.
- O link so deve ser obrigatorio quando o tipo remoto ou regra de negocio aprovada exigir referencia a documento anterior.
- Sem evidencia oficial por tipo, uma nota de credito/debito manual administrativa nao deve ser bloqueada apenas por ausencia de documento original, mas tambem nao deve ser liberada sem a fase IBS/CBS quando o payload tributario for obrigatorio.

Cardinalidade planejada:

```text
Workshop 1:N FiscalDocument(document_type=nfe, purpose=credit|debit)
FiscalDocument(credit|debit) 1:N FiscalEmissionAttempt(operation_type=nfe_credit_emission|nfe_debit_emission)
FiscalDocument(credit|debit) 0:N FiscalDocumentLink(role=credits|debits)
```

Idempotencia planejada:

```text
criar FiscalDocument local
-> criar/bloquear FiscalEmissionAttempt
-> congelar payload sanitizado
-> executar uma unica chamada POST /1/nfe/emissao/
-> persistir retorno no documento
-> webhook/reconciliacao atualizam somente o documento emitido
```

Chaves:

- Credito: `hash(workshop_id, credit_document_id, "nfe_credit_emission", request_generation)`.
- Debito: `hash(workshop_id, debit_document_id, "nfe_debit_emission", request_generation)`.

Dependencia IBS/CBS:

- A fase funcional deve permanecer bloqueada ate haver suporte aprovado para IBS/CBS ou uma decisao tributaria documentada que identifique tipos seguros sem esses campos.
- Como a documentacao/ajuda Webmania associa finalidade 5/6 a IBS/CBS, a modelagem deve prever campos tributarios sem implementa-los nesta fase documental.

## Fase 2.4.0 - Modelagem recomendada IBS/CBS NF-e/NFC-e

Problema de dominio: os fluxos atuais NF-e/NFC-e dependem de `classe_imposto` e classes fiscais NF-e locais sem campos IBS/CBS. A Webmania permite IBS/CBS no payload do produto e nas classes de imposto. Como classificacao tributaria nao deve ser inferida automaticamente, o Hunter precisa de fonte local administravel antes de enviar ou bloquear emissao.

Decisao implementada para a Fase 2.4A+B:

- Evoluir `TaxClassNfe` com suporte IBS/CBS, mantendo compatibilidade com ICMS/IPI/PIS/COFINS atuais.
- Usar modelagem hibrida no proprio `TaxClassNfe`: campos normalizados para `ibs_cbs_enabled`, situacao/classificacao tributaria e campos de regime regular; `ibs_cbs_details` JSON validado para preservar grupos condicionais oficiais; usuario/data de configuracao; indice por oficina/habilitacao.
- Nao criar `TaxClassNfeIbsCbsScenario` nesta fase. Se fases futuras exigirem multiplos cenarios IBS/CBS por classe, esse model deve ser planejado separadamente.
- Manter `WebmaniaCompany.regime_tributario` como dado auxiliar de validacao, nao como fonte unica de classificacao IBS/CBS.
- Permitir payload inline `produtos[].impostos.ibs_cbs` apenas quando a fase aprovada exigir; a primeira preferencia operacional deve ser classe fiscal configurada e validada.

Relação com produtos:

- Produto/servico de catalogo deve continuar podendo apontar para classe fiscal.
- A classe fiscal deve indicar se esta apta para NF-e, NFC-e ou ambos.
- A ausencia de IBS/CBS configurado deve ser detectavel antes do gateway para cada produto e ambiente.

Estados e auditoria:

- Alteracoes de configuracao IBS/CBS devem ser auditaveis por oficina e usuario.
- Payload enviado para Webmania deve preservar o `ibs_cbs` efetivo na sincronizacao da classe fiscal. Como NF-e/NFC-e normal usam `classe_imposto`, o gate local exige classe IBS/CBS-ready antes do gateway.
- Nao guardar headers, credenciais, CSC ou certificado junto aos payloads tributarios.

Compatibilidade:

- Nao remover `TaxClassNfeIcmsScenario`, `TaxClassNfeIpiScenario`, `TaxClassNfePisScenario` ou `TaxClassNfeCofinsScenario`.
- Durante a transicao, NF-e/NFC-e normal pode precisar coexistir com tributos antigos e `ibs_cbs`; credito/debito e excecoes oficiais devem impedir tributos antigos quando a finalidade exigir somente IBS/CBS.
- `TaxClassNfse` ja possui campos IBS/CBS, mas isso nao resolve NF-e/NFC-e; usar apenas como referencia de padrao, nao como substituto.

Subfases de dominio:

| Subfase | Modelagem minima | Observacao |
| ------- | ---------------- | ---------- |
| 2.4A | Classe fiscal/produto com IBS/CBS local e bloqueio seguro | Primeira subfase funcional recomendada. |
| 2.4B | Emissao normal NF-e/NFC-e com snapshot do IBS/CBS usado | Deve proteger producao >= `05/01/2026`. |
| 2.4C | Regras por documento derivado | Devolucao, complementar e ajuste nao devem reutilizar cegamente o payload normal. |
| 2.4D | `FiscalDocumentEvent` para eventos IBS/CBS | Somente apos emissao base conformada. |
| 2.4E | `FiscalDocument(purpose=credit|debit)` com `fiscal_purpose_type` | Somente apos base IBS/CBS validada. |

## Fase 2.4C.0 - Modelagem planejada para derivados com IBS/CBS

Problema de dominio: documentos derivados nao sao uma reemissao da nota normal. Devolucao, estorno, complementar e ajuste possuem semanticas fiscais distintas e nao podem reutilizar automaticamente o payload normal nem a classe fiscal atual do produto.

### Decisao recomendada

- Manter `FiscalDocument` e `FiscalDocumentLink` ja validados nas Fases 2.2A, 2.2B.1 e 2.2C.
- Preservar a idempotencia por documento derivado local e `FiscalEmissionAttempt`, sem usar hash de payload como identidade final.
- Para devolucao/estorno e complementar preco/quantidade, usar snapshot fiscal da NF-e original local como primeira fonte.
- Para ajuste, manter documento avulso `FiscalDocument(purpose="adjustment", origin="manual")` e link opcional `adjusts`; nao exigir documento original nem produtos.
- Bloquear derivados quando a fonte fiscal IBS/CBS nao for auditavel.

### Snapshot tributario

Fonte preferencial futura:

```text
FiscalDocument original
-> request_payload_sanitized/response_payload_sanitized
-> NfeItem.raw_payload/log_payload legado quando aplicavel
-> item fiscal original por sequencial
-> classe TaxClassNfe atual apenas como validacao auxiliar confirmada
```

Regras:

- O snapshot deve preservar `classe_imposto`, `impostos.ibs_cbs`, situacao/classificacao e grupos condicionais usados na nota original quando disponiveis.
- A classe fiscal atual pode ter mudado depois da NF-e original; por isso ela nao pode substituir automaticamente o snapshot.
- Quando o snapshot nao tiver IBS/CBS e a operacao exigir IBS/CBS, bloquear antes do gateway ou exigir fluxo aprovado de reconstrucao fiscal com confirmacao.

### NF-e externa

Para `FiscalDocument(origin="external")` criado somente por chave:

- nao ha itens, sequenciais, quantidades nem snapshot tributario confiavel;
- devolucao parcial e complementar preco/quantidade devem permanecer bloqueadas;
- estorno/devolucao total so devem ser liberados em fase funcional se o contrato oficial e a regra fiscal permitirem sem detalhe de itens, com confirmacao forte e permissao restrita;
- backlog obrigatorio: importacao/validacao por XML ou API fiscal especifica para criar snapshot externo minimo.

### Subfases de modelagem

| Subfase | Modelagem | Dependencia | Risco principal |
| ------- | --------- | ----------- | --------------- |
| 2.4C.1 | Reusar `FiscalDocument(purpose=return|reversal)`, `FiscalDocumentLink(role=returns|reverses)` e tentativa existente; adicionar validadores IBS/CBS por item/snapshot | 2.4A+B validada | Copiar tributacao atual em vez da original |
| 2.4C.2 | Reusar `FiscalDocument(purpose=complementary, complementary_type=price_quantity)` e link `complements`; permitir IBS/CBS somente para o acrescimo | 2.4C.1 preferencialmente validada | Misturar complemento de produto com complementar tributaria |
| 2.4C.3 | Reusar `FiscalDocument(purpose=adjustment)` e link opcional `adjusts`; decidir se ha bloqueio por operacao/CFOP/regime | 2.4A+B validada e revalidacao oficial do ajuste | Inserir produtos/IBS-CBS sem contrato oficial |

Resultado da Fase 2.4C.3: nenhuma nova entidade ou migration e necessaria. O ajuste permanece `FiscalDocument(document_type=nfe, purpose=adjustment, origin=manual)`, com `FiscalDocumentLink(role=adjusts)` opcional e `FiscalEmissionAttempt(operation_type=adjustment)`. Campos de credito/debito, produtos, eventos IBS/CBS e `produtos[].impostos.ibs_cbs` sao rejeitados antes do gateway porque pertencem a contratos fiscais proprios ou nao estao documentados em `/1/nfe/ajuste/`.

## Fase 2.4D.0 - Modelagem planejada para Eventos IBS/CBS

Decisao principal: evento IBS/CBS nao e documento fiscal novo. Deve ser representado por `FiscalDocumentEvent(event_type="ibs_cbs")` vinculado ao `FiscalDocument` base (`document_type="nfe"` ou `"nfce"`), preservando a NF-e/NFC-e original sem alterar seu status fiscal indevidamente.

Campos planejados em `FiscalDocumentEvent`:

- `document`: documento NF-e/NFC-e base.
- `event_type="ibs_cbs"`.
- `event_code`: `cod_evento` remoto.
- `event_sequence`: valor de `evento`, reservado de 1 a 20 por documento e codigo.
- `event_payload_type`: agrupamento interno para orientar UI/validacao, por exemplo `no_specific_fields`, `items_stock_control`, `delivery_forecast`, `acceptance`, `credit_request`.
- `remote_uuid`: UUID retornado pela Webmania para o evento.
- `remote_event_id` ou `protocol`: protocolo/identificador remoto quando retornado.
- `remote_model`: `modelo` retornado.
- `status` e `remote_status`.
- `request_payload_sanitized` e `response_payload_sanitized`.
- `xml_url` quando retornado.
- `requested_by`, `requested_at`, `completed_at`, `created_at`, `updated_at`.

Campos planejados em `FiscalEmissionAttempt`:

- `operation_type="nfe_ibs_cbs_event"` para registro.
- `operation_type="nfe_ibs_cbs_event_cancellation"` para cancelamento futuro, se aprovado.

Resultado da Fase 2.4D.1:

- `FiscalDocumentEvent` recebeu campos `event_code`, `event_payload_type` e `remote_event_id`.
- `event_type="ibs_cbs"` representa o evento IBS/CBS, nao um novo documento fiscal.
- `event_code="112110"` e `event_payload_type="no_specific_fields"` registram a subfase implementada.
- A sequencia e reservada transacionalmente por documento e tipo de evento IBS/CBS, respeitando a constraint existente de unicidade `(document, event_type, event_sequence)`.
- `FiscalEmissionAttempt(operation_type="nfe_ibs_cbs_event")` fica associado ao documento base e ao evento.
- O status, XML e payload de retorno sao persistidos somente no evento; a NF-e/NFC-e base nao tem status alterado pelo evento.
- associacao obrigatoria ao `FiscalDocument` base e ao `FiscalDocumentEvent`.
- `idempotency_key`, `payload_hash`, status `started|sent|succeeded|failed|uncertain`, payload/resposta sanitizados e UUID remoto.

Resultado da Fase 2.4D.2:

- `FiscalDocumentEvent(event_type="ibs_cbs_cancellation")` representa o cancelamento do evento `112110`.
- `related_event` vincula o cancelamento ao evento IBS/CBS original; `FiscalDocumentLink` nao e usado.
- A constraint condicional impede dois cancelamentos ativos/incertos/aprovados para o mesmo evento original.
- `FiscalEmissionAttempt(operation_type="nfe_ibs_cbs_event_cancellation")` e associado ao evento de cancelamento e ao documento base apenas para escopo/tenancy.
- Sucesso remoto marca o evento de cancelamento como autorizado/cancelado conforme retorno e marca o evento original como `cancelado`; o `FiscalDocument` base permanece inalterado.
- Timeout deixa tentativa e evento de cancelamento como `uncertain`, preservando o bloqueio contra novo cancelamento automatico.

Cancelamento de evento:

- Nao deve criar `FiscalDocument`.
- Deve ser modelado como evento filho ou relacao explicita com o evento IBS/CBS original, em subfase propria.
- Deve usar `PUT /1/nfe/evento-ibs-cbs/cancelar/` por UUID do evento autorizado.
- A ausencia de UUID remoto do evento original bloqueia cancelamento antes do gateway.

Constraints recomendadas:

- Unicidade de `(document, event_type, event_code, event_sequence)` para impedir duplicidade local.
- Unicidade condicional de `remote_uuid` por oficina/documento quando preenchido.
- Bloqueio transacional ao reservar proxima sequencia por documento e codigo.
- Nenhum evento IBS/CBS pode ser associado a documento de outra oficina.

Compatibilidade:

- NF-e/NFC-e normal e derivados continuam sendo `FiscalDocument`.
- CC-e e cancelamento NFC-e ja usam `FiscalDocumentEvent`; a fase deve reutilizar esse padrao, sem criar app fiscal paralelo.
- Ajuste permanece `FiscalDocument(purpose="adjustment")` e nao recebe eventos IBS/CBS por inferencia.

## Fase 2.4D.3.0 - Modelagem planejada para demais Eventos IBS/CBS

Decisao: todos os eventos IBS/CBS restantes continuam sendo `FiscalDocumentEvent(event_type="ibs_cbs")` associados a `FiscalDocument` base. Nao criar `FiscalDocument` novo para evento e nao usar `FiscalDocumentLink`.

Agrupamento de modelagem:

- Grupo A (`112150`): reutiliza campos existentes de `FiscalDocumentEvent`, com `event_payload_type="delivery_forecast"` e payload contendo `data_previsao_entrega`.
- Grupo B (`112120`, `112130`, `112140`): exige payload com `itens[]`, sequencial fiscal, valores IBS/CBS e `controle_estoque`; deve validar snapshot de item e origem operacional antes de qualquer chamada remota.
- Grupo C (`211128`): exige `indicador_aceitacao` e contexto de nota de credito/debito/apuracao assistida; permanece bloqueado ate `FiscalDocument(purpose=credit|debit)` estar implementado.
- Grupo D (`211110`, `211120`, `211124`, `211130`, `211140`, `211150`): exige papel de destinatario, documento de aquisicao, apuracao fiscal/contabil ou controle de estoque externo; manter em backlog ate existir modelagem de entrada/monitor fiscal/importacao XML.

Proxima subfase recomendada: `2.4D.3 - Evento IBS/CBS 112150`. O documento elegivel deve ser NF-e/NFC-e normal local autorizada, com chave valida e oficina ativa. Derivados, ajuste, credito/debito e documentos externos continuam bloqueados para esse evento ate nova decisao.

Cancelamento: nao generalizar o cancelamento validado em 2.4D.2 para todos os codigos. Para `112150`, planejar cancelamento em subfase posterior ou no fechamento da subfase apenas se a implementacao comprovar que o retorno remoto e o ciclo de vida seguem exatamente o mesmo padrao, com testes especificos.

Resultado 2.4D.3: `112150` foi modelado sem migration nova, reutilizando `FiscalDocumentEvent` existente com `event_type="ibs_cbs"`, `event_code="112150"`, `event_payload_type="delivery_forecast"` e `FiscalEmissionAttempt(operation_type="nfe_ibs_cbs_event")`. A elegibilidade final ficou conservadora: somente `FiscalDocument(document_type="nfe", purpose="normal", origin="local", status="aprovado")` com chave de acesso. NFC-e foi bloqueada nesta subfase ate confirmacao operacional especifica, e documentos derivados/ajuste permanecem bloqueados. O evento nao cria `FiscalDocument`, nao usa `FiscalDocumentLink` e nao altera o status fiscal do documento base.

Resultado 2.4D.4: o cancelamento do `112150` reutiliza `FiscalDocumentEvent` existente sem migration, com `event_type="ibs_cbs_cancellation"`, `event_code="112150"`, `related_event` apontando para o evento `112150` original e `event_payload_type="cancellation"`. A tentativa usa `FiscalEmissionAttempt(operation_type="nfe_ibs_cbs_event_cancellation")`. O cancelamento nao cria `FiscalDocument`, nao usa `FiscalDocumentLink` e nao altera o status fiscal da NF-e base; apenas marca o evento original como cancelado quando o retorno remoto do cancelamento e positivo.

## Fase 2.4D.5.0 - Modelagem planejada para eventos IBS/CBS com itens

Eventos `112120`, `112130` e `112140` continuam sendo `FiscalDocumentEvent(event_type="ibs_cbs")` associados ao `FiscalDocument` base. Nenhum deles deve criar `FiscalDocument`, `FiscalDocumentLink` ou alterar status fiscal da NF-e/NFC-e base.

| Codigo | `event_payload_type` recomendado | Dados especificos |
| ------ | -------------------------------- | ----------------- |
| `112120` | `import_alc_zfm_not_exempted` | Itens com sequencial fiscal, `valor_ibs`, `valor_cbs` e `controle_estoque.quantidade/unidade`. |
| `112130` | `supplier_transport_loss` | Itens com sequencial fiscal, `valor_ibs`, `valor_cbs`, `quantidade_perecimento`, `unidade_perecimento`, `valor_ibs_estorno` e `valor_cbs_estorno`. |
| `112140` | `advance_payment_not_supplied` | Itens da nota de debito/pagamento antecipado, `valor_ibs`, `valor_cbs`, `quantidade_nao_fornecida` e `unidade_nao_fornecida`. |

Fonte de dados recomendada:

- Snapshot fiscal do documento original em `FiscalDocument.request_payload`, `FiscalDocument.response_payload`, `NfeItem.raw_payload` ou `NfeItem.log_payload`, desde que contenha produtos, sequencial fiscal e IBS/CBS suficiente.
- Dados de estoque/transporte/financeiro apenas como complemento auditavel para os fatos do evento.
- Input manual somente com confirmacao fiscal explicita e sem recompor tributacao por inferencia.

Bloqueio permanente: `TaxClassNfe` atual nao pode ser fallback automatico para eventos de documento ja emitido, porque a classe pode ter sido alterada depois da autorizacao da NF-e/NFC-e base.
### Resultado Fase 2.4D.5.1 - Evento IBS/CBS 112130

O evento `112130` foi modelado como `FiscalDocumentEvent(event_type="ibs_cbs", event_code="112130", event_payload_type="supplier_transport_loss")` associado ao `FiscalDocument` original. Nenhum `FiscalDocument` novo e nenhum `FiscalDocumentLink` sao criados. A elegibilidade exige NF-e normal local autorizada, chave de acesso valida e snapshot fiscal original com item sequencial e bloco IBS/CBS. O snapshot da classe fiscal atual nao substitui o snapshot da nota ja emitida.

O payload persistido e transmitido segue o contrato oficial com `itens[]`; o bloco top-level `ibs_cbs` nao e usado. A sequencia do evento continua compartilhando a constraint existente `(document, event_type, event_sequence)`, preservando limite de 20 eventos IBS/CBS por documento.

### Resultado Fase 2.4D.5.2 - Cancelamento do Evento IBS/CBS 112130

O cancelamento do evento `112130` foi modelado como `FiscalDocumentEvent(event_type="ibs_cbs_cancellation", event_code="112130", event_payload_type="cancellation", related_event=<evento 112130>)`, associado ao mesmo `FiscalDocument` base apenas para escopo e historico. Nenhum `FiscalDocument` novo e nenhum `FiscalDocumentLink` sao criados.

A tentativa usa `FiscalEmissionAttempt(operation_type="nfe_ibs_cbs_event_cancellation")`. Retorno remoto positivo atualiza o evento de cancelamento e marca somente o evento `112130` original como `cancelado`; o status, chave, XML e DANFE da NF-e base permanecem inalterados. Eventos sem UUID remoto, em estado incerto/falho/rejeitado ou ja cancelados bloqueiam antes do gateway.

## Fase 2.4D.6.0 - Modelagem recomendada para 112120 e 112140

Decisao: nao criar model novo nem implementar emission builders nesta fase. Quando autorizados futuramente, `112120` e `112140` devem continuar como `FiscalDocumentEvent(event_type="ibs_cbs")`, associados ao `FiscalDocument` base, sem criar `FiscalDocument` ou `FiscalDocumentLink`.

Modelagem futura por codigo:

- `112120`: `event_payload_type="import_alc_zfm_not_exempted"`, exigindo documento de importacao local/importado por XML validado, snapshot fiscal por item, contexto ALC/ZFM e `controle_estoque.quantidade/unidade`.
- `112140`: `event_payload_type="advance_payment_not_supplied"`, exigindo documento de debito/pagamento antecipado, snapshot fiscal por item da nota de debito, vinculo financeiro auditavel e `controle_estoque.quantidade_nao_fornecida/unidade_nao_fornecida`.

Ambos devem reutilizar `FiscalEmissionAttempt(operation_type="nfe_ibs_cbs_event")`, sequencia transacional por documento/codigo e payload congelado. `TaxClassNfe` atual nao pode ser fallback para recompor evento de documento ja emitido.

Fase preparatoria recomendada antes de codigo funcional:

1. projetar/importar NF-e externa/XML em `FiscalDocument` com itens, sequenciais fiscais e IBS/CBS auditaveis;
2. modelar contexto ALC/ZFM/importacao para `112120`;
3. modelar nota de debito/pagamento antecipado e vinculo item fiscal-financeiro para `112140`;
4. definir saldos/quantidades afetadas e bloqueios de concorrencia antes de transmitir eventos.
## Fase 2.5.1.0 - Modelagem final recomendada para credito/debito

Reutilizar o nucleo, sem models legados paralelos:

- `FiscalDocument(document_type="nfe", purpose="credit"|"debit", origin="manual"|origem futura aprovada)`.
- Novo campo futuro `fiscal_purpose_type` como string curta, contendo o valor remoto de `tipo_credito` ou `tipo_debito`; a descricao deve vir de enum de aplicacao versionado, sem perder o valor bruto.
- `FiscalDocumentLink(role="credits"|"debits")` apenas quando houver documento local/importado realmente referenciado. Para credito, `nfe_referenciada` pode representar uma ou mais NF-e e pode exigir tabela associativa/metadata de referencias; nao limitar a um unico link. Para debito `3`/`4`, o vinculo deve chegar ao item fiscal referenciado, nao apenas ao documento.
- Snapshot imutavel por item: CFOP na raiz, dados comerciais, `impostos.ibs_cbs` exclusivo e `dfe_referenciado` quando aplicavel.
- Fonte/justificativa fiscal persistida por tipo, com usuario, oficina, evidencia e periodo de apuracao quando aplicavel.

Obrigatoriedade do link:

| Caso | Link local | Referencia remota |
| --- | --- | --- |
| Credito com NF-e Hunter/importada | Obrigatorio para cada referencia conhecida | `nfe_referenciada[]` |
| Credito cuja hipotese nao tenha documento comprovado | Bloquear ate regra oficial/negocio aprovada | Nao inventar chave |
| Debito tipos 3/4 | Obrigatorio por documento e item | `produtos[].dfe_referenciado` obrigatorio |
| Debito demais tipos | Opcional somente quando relacao real existir | Nao enviar `dfe_referenciado` sem fundamento |

Nao criar os novos choices/campos antes da aprovacao funcional. A fase preparatoria deve primeiro modelar fontes e referencias por item.

### Modelagem implementada na Fase 2.5.1P

`FiscalReferencedBasis` contem oficina, documento e `NfeItem` de origem, chave, sequencial fiscal, tipo da base, hipotese, snapshot IBS/CBS, referencias opcionais financeira/estoque, marcadores de origem/XML externo, status, criador/aprovador, timestamps e evidencias. Constraints impedem duplicidade local por documento/item/hipotese e externa por chave/item/hipotese.

Status: `draft`, `ready`, `approved`, `rejected`, `invalid`, `archived`. O snapshot de registro ja aprovado e imutavel no model. Aprovacao exige snapshot com situacao/classificacao, evidencia textual, referencias requeridas pela hipotese, oficina coerente e XML validado para origem externa.

`WebmaniaCompany` recebeu `credit_debit_basis_enabled`, ator e timestamp de habilitacao. A flag nao cria novos purposes nem operation types de emissao.

## Fase 2.5.2.0 - Lacuna de modelagem antes da emissao

A futura fase preparatoria 2.5.2P deve ampliar a base, nao criar documento emitido, com snapshot comercial imutavel por item e valores `principal`, `multa`, `juros`, `total_fiscal`, unidade/quantidade e CFOP. Deve preservar origem e moeda com `Decimal`, validar soma e impedir alteracao apos aprovacao.

Somente uma fase funcional posterior podera adicionar `FiscalDocumentPurpose.CREDIT`, `fiscal_purpose_type`, links `credits`, tentativa `nfe_credit_emission` e documento derivado. Nada disso e autorizado na 2.5.2.0.
## FiscalReferencedBasisItem - Fase 2.5.2P

Entidade one-to-one de `FiscalReferencedBasis`, criada porque a base principal ja identifica exatamente um item fiscal, enquanto o snapshot monetario/comercial possui regras proprias de completude e imutabilidade. Armazena sequencial, descricao, codigo, NCM, CFOP, quantidade, unidade, valor unitario, total original, principal, multa, juros, outros, base credito/debito e snapshots JSON sanitizados.

Dinheiro usa `DecimalField(18,2)` e quantidade `DecimalField(18,6)`. Para `credit_fine_interest`/`debit_fine_interest`, `credit_debit_base_amount = fine_amount + interest_amount`; nas demais hipoteses, a composicao e principal + multa + juros + outros. Movimentacao financeira nao preenche valores automaticamente. Aprovacao congela item, CFOP, snapshots e todos os valores.
## Modelagem futura - credito tipo 1

- `FiscalDocument(document_type="nfe", purpose="credit", origin="derived", fiscal_purpose_type="1")`, criado antes do gateway em estado inicial/processing.
- `FiscalDocumentLink(document=credito, related_document=original, role="credits")` obrigatorio para cada NF-e referenciada conhecida localmente. A primeira implementacao deve limitar-se a uma base/uma NF-e original; multiplas referencias exigem decisao posterior.
- Relacao obrigatoria e imutavel do documento de credito com `FiscalReferencedBasis`; o `FiscalReferencedBasisItem` e alcancado pela one-to-one e deve estar congelado pela aprovacao da base.
- `FiscalEmissionAttempt(operation_type="nfe_credit_emission")`, chaveada por oficina, documento de credito, operacao e geracao da requisicao.
- Payload sanitizado congelado antes de `POST /1/nfe/emissao/`; timeout produz `uncertain` e bloqueia reenvio.
- Webhook/reconciliacao atualizam somente o documento de credito por UUID/tentativa segura; XML/DANFE permanecem no derivado.
- Cancelamento nao integra a primeira emissao: sera fase posterior pelo fluxo padrao de cancelamento NF-e, nunca pelo cancelamento de evento IBS/CBS.

Nenhum desses campos/choices/models foi criado na Fase 2.5.3.0.
## FiscalCreditProductPreview - Fase 2.5.3P

Entidade local com oficina, base, item, revisao, operacao `credit`, tipo fiscal `1`, chave/sequencial, CFOP, quantidade, unitario, total, produto, IBS/CBS, pre-payload, grupos proibidos, erros, status, confirmacao e atores/timestamps. Constraints garantem revisao unica por base e valores positivos; indices cobrem oficina/status e chave/item.

Cada revisao e imutavel apos aprovacao. A criacao bloqueia a base para reservar revisao e bloqueia o item separadamente. Nao ha FK para `FiscalDocument` derivado ou `FiscalEmissionAttempt`, porque essas entidades permanecem proibidas nesta fase.

## Documento de credito tipo 1 - Fase 2.5.4

`FiscalDocument(document_type="nfe", purpose="credit", fiscal_purpose_type="1", origin="derived")` referencia obrigatoriamente `FiscalReferencedBasis` e uma unica `FiscalCreditProductPreview`. A constraint `fiscal_credit_document_requires_basis_preview` protege a estrutura e a relacao one-to-one da preview impede duas intencoes para o mesmo pre-payload. `FiscalDocumentLink(role="credits")` liga o credito a NF-e original local sem altera-la.

## Cancelamento do credito tipo 1 - Fase 2.5.5

O cancelamento cria `FiscalDocumentEvent(event_type="cancellation", event_payload_type="nfe_credit_cancellation")` associado ao documento de credito e tentativa `nfe_credit_cancellation`. Nao cria `FiscalDocument` nem link. `xml_url` do evento guarda prioritariamente `xml_cancelamento`; a resposta integral sanitizada preserva tambem o XML original quando retornado.

## Modelagem recomendada apos a Fase 2.5.6.0

Proxima fase recomendada: `2.5.6P - Preview fiscal de debito tipo 4`, sem `FiscalDocument`, `FiscalEmissionAttempt` ou gateway remoto.

Criar uma modelagem irma da preview de credito, preferencialmente `FiscalDebitProductPreview`, associada obrigatoriamente a `FiscalReferencedBasis` e `FiscalReferencedBasisItem`. Ela deve congelar:

- `operation_type="debit"` e `fiscal_purpose_type="4"`;
- `dfe_referenciado.chave` e `dfe_referenciado.item` vindos da base aprovada;
- produto comercial/monetario explicitamente aprovado para debito;
- `codigo_cfop` de debito, sem copiar automaticamente o CFOP do credito ou do documento original;
- `impostos.ibs_cbs` do snapshot aprovado, sem recalcule ou fallback para `TaxClassNfe` atual;
- ausencia comprovada de ICMS, IPI, PIS, COFINS, ISSQN, II e demais grupos proibidos.

Nao reutilizar `FiscalCreditProductPreview` diretamente: a imutabilidade e a semantica aprovada daquela entidade pertencem a `finalidade=5`, `tipo_credito=1`. Uma futura emissao, somente apos nova aprovacao, usara `FiscalDocument(purpose="debit", fiscal_purpose_type="4")`, link `debits` e tentativa `nfe_debit_emission`.

### Implementacao validada da Fase 2.5.6P

`FiscalDebitProductPreview` foi criada como entidade independente com base/item, revisao, operacao `debit`, tipo fiscal `4`, chave/item referenciados, `dfe_referenciado`, valores explicitos, produto, IBS/CBS, pre-payload, validacoes, autores e timestamps. Constraints garantem revisao unica por base e valores positivos. Payloads, referencias e valores tornam-se imutaveis apos aprovacao.

Nao foram adicionados `FiscalDocument(purpose="debit")`, `FiscalEmissionAttempt(operation_type="nfe_debit_emission")` nem vinculo de documento remoto.

## Modelagem futura - Emissao de debito tipo 4

### Modelagem implementada na Fase 2.5.7

- `FiscalDocument(document_type="nfe", purpose="debit", fiscal_purpose_type="4")` ligado de forma exclusiva a uma preview.
- `FiscalDocumentLink(role="debits")` para a NF-e original local.
- `FiscalEmissionAttempt(operation_type="nfe_debit_emission")` associado ao documento derivado.
- Flag auditavel `WebmaniaCompany.nfe_debit_emission_enabled` separada da preparacao.
- Constraint exige base e preview para documentos de debito.

### Cancelamento implementado na Fase 2.5.8

O cancelamento reutiliza o `FiscalDocument` de debito e cria `FiscalDocumentEvent(event_type="cancellation", event_payload_type="nfe_debit_cancellation")`. Nao cria documento ou link novo. `FiscalEmissionAttempt(operation_type="nfe_debit_cancellation")` referencia documento e evento; o XML de cancelamento fica em `event.xml_url`.
Adicionar somente na fase funcional aprovada:

- `FiscalDocumentPurpose.DEBIT`;
- `FiscalDocumentLinkRole.DEBITS`;
- `FiscalDocument.debit_product_preview` como `OneToOneField(PROTECT)`;
- constraint: documento `purpose="debit"` exige origem derivada, tipo fiscal `4`, base e preview de debito;
- `FiscalEmissionOperationType.NFE_DEBIT_EMISSION`;
- permissoes de emitir, visualizar, baixar e visualizar payload.

Fluxo: preview aprovada -> criar `FiscalDocument(document_type="nfe", origin="derived", purpose="debit", fiscal_purpose_type="4")` -> vincular `referenced_basis` e `debit_product_preview` -> criar `FiscalDocumentLink(role="debits")` para a NF-e original local -> criar tentativa -> transmitir.

A relacao com `FiscalReferencedBasisItem` permanece transitiva e imutavel por `debit_product_preview.basis_item`; nao duplicar FK no documento sem necessidade. Uma preview pode produzir no maximo um documento devido ao `OneToOneField`.

## Direcao de dominio apos a Fase 2.6.0

A proxima etapa recomendada e `Fase 3.0 - Auditoria e Planejamento Tecnico da NFS-e Expandida`, exclusivamente documental. O fluxo NFS-e existente deve ser auditado antes de qualquer nova modelagem para decidir a evolucao de `NfseRequest`, `NfseItem` e `NfseBatch`, a projecao em `FiscalDocument` e a compatibilidade com RPS/lotes e capacidades municipais.

Nenhum novo model e autorizado na Fase 3.0. O planejamento deve definir, com evidencia do codigo e do contrato municipal/Webmania:

- identidade do documento e do RPS, incluindo municipio, provedor e ambiente;
- representacao de ISS e IBS/CBS durante a transicao;
- vinculos de substituicao e manifestacao sem alterar indevidamente o documento original;
- estrategia de convivencia/backfill para o legado;
- capacidades municipais como dado configuravel e auditavel, sem inferencia automatica.

## Decisao de modelagem NFS-e - Fase 3.0

Adotar convivencia gradual:

1. `NfseRequest`, `NfseBatch` e `NfseItem` permanecem fonte operacional do fluxo por OS nas subfases iniciais.
2. `FiscalDocument(document_type="nfse")` sera projecao sob demanda de `NfseItem` quando uma nova operacao exigir evento/link, sem backfill em massa.
3. Emissao manual futura nascera diretamente em `FiscalDocument`; nao criar um segundo request legado.
4. `FiscalDocumentEvent` representara cancelamento e manifestacao; substituicao criara novo `FiscalDocument` e `FiscalDocumentLink(role="substitutes")` para a nota anterior.
5. `FiscalEmissionAttempt` sera estendido com operation types NFS-e especificos e associado ao legado/projecao durante a convivencia.

### Capacidade municipal planejada

Recomenda-se `NfseMunicipalCapability` separado, versionado por oficina, codigo IBGE/municipio, provedor/modelo, versao e ambiente. O snapshot deve armazenar `status`, ambientes, autenticacoes, modelos de emissao, funcoes, codigos de servico, parametros disponiveis, `fetched_at`, payload sanitizado e erro de sincronizacao.

Campos derivados pesquisaveis: Padrao Nacional, emissao sincrona/assincrona, `nfse`/`lote_rps`, consulta, cancelamento, substituicao, manifestacao, homologacao, XML/PDF/RPS e requisitos de IM/CNAE/codigo de servico. Prazo de cancelamento nao deve ser inferido quando `/status` nao o informar; permanecer como regra administrativa confirmada por municipio.

`WebmaniaCompany` deve manter credenciais e defaults da oficina, nao absorver matriz municipal dinamica. Nenhuma capacidade pode ser considerada valida indefinidamente; definir TTL e bloqueio seguro na Fase 3.1.

### Compatibilidade legada

- manter URLs, wizard, templates e permissoes atuais durante 3.1-3.3;
- adicionar flags por oficina para cada comportamento novo, com fallback exclusivo para o fluxo legado ja validado;
- fazer a tentativa existente por `NfseRequest` ser a autoridade de idempotencia da emissao durante a convivencia;
- impedir que uma projecao `FiscalDocument` crie segunda tentativa para a mesma request/UUID;
- criar projecao transacional e idempotente somente quando necessaria, sem alterar ownership do legado;
- medir requests sem item/lote, UUID ambiguo, webhook pendente e status divergente antes de aprovar qualquer backfill;
- rollback desliga flags novas e mantem leitura dos dados adicionados, sem apagar request/item/lote.

### Modelagem implementada na Fase 3.1

`NfseMunicipalCapability` possui unicidade por `(workshop, company, city_code)`, indices por oficina/municipio/atividade e empresa/UF/municipio, flags de operacao e requisitos municipais. `WebmaniaCompany.nfse_legacy_compatibility_enabled` controla explicitamente a ausencia de cadastro. `NfseBatch` e `NfseItem` receberam `remote_updated_at`; nenhum dado legado foi transformado ou preenchido em massa.

### Extensao minima da Fase 3.2

- `NfseBatch`: `last_reconciled_at` e `last_update_source`.
- `NfseItem`: `last_update_source`, reutilizando `last_reconciled_at` existente.
- `NfseMunicipalCapability`: `remote_status` e `last_status_error`, reutilizando `remote_payload`/`last_synced_at`.
- Nenhum `FiscalDocument(nfse)`, backfill ou modelo de cancelamento/substituicao/manifestacao foi criado.
## `NfseCancellation`

Trilha propria ligada a um `NfseItem`, `NfseRequest` e oficina. Persiste motivo, payload congelado, resposta sanitizada, XML, solicitante e timestamps. Uma constraint parcial permite no maximo um cancelamento reservante (`started`, `sent`, `uncertain` ou `succeeded`) por item; falha remota conclusiva pode originar nova intencao. Nao existe vinculo com `FiscalDocument` e o lote nao e atualizado pelo cancelamento individual.

## Modelagem planejada para substituicao NFS-e

### Fase preparatoria 3.4P

`NfseSubstitutionPreview`: oficina, requisicao/item original, UUID e codigo de verificacao originais, ambiente, motivo, `rps_payload` sanitizado, snapshot do XML original/URL e hash, erros/status de validacao, criador/aprovador e timestamps. A aprovacao congela o payload. Nao cria `FiscalEmissionAttempt`, NFS-e substituta nem chamada remota.

### Fase funcional posterior

`NfseSubstitution`: oficina, preview aprovada, item original, item substituto anulavel ate retorno, UUIDs original/substituto, payload/response, XML original snapshot, XML substituto, status e solicitante. A tentativa usa `operation_type="nfse_substitution"`. Nao modelar como mero evento: o endpoint cria uma nova NFS-e, enquanto a original deve permanecer auditavel e passar a `substituido` somente por confirmacao remota valida. Nao criar `FiscalDocument(nfse)` generalizado nesta etapa.

Uma preview aprovada pode originar no maximo uma substituicao ativa, incerta ou concluida. O item substituto pertence a mesma oficina/requisicao operacional, mas possui UUID, numero, verificacao, XML/PDF e status proprios.

### Modelagem implementada na Fase 3.4P

`NfseSubstitutionPreview` referencia `NfseItem` original e congela UUID, codigo de verificacao, snapshot auditavel do XML/retorno original, ambiente, motivo, novo RPS e request planejado. Status, erros, campos proibidos, criador e aprovador formam a trilha local. Constraint permite somente uma preview aprovada por original. Payload, referencia, motivo, ambiente e snapshot tornam-se imutaveis apos aprovacao. `WebmaniaCompany.nfse_substitution_preview_enabled` e a flag preparatoria; `NfseMunicipalCapability.substitution_enabled` continua sendo o controle municipal.

### Modelagem implementada na Fase 3.4.1

## Modelagem planejada para manifestacao NFS-e Padrao Nacional

Fase: 3.6.0 documental.

Decisao planejada: criar model proprio `NfseManifestation` vinculado a `NfseItem`, `workshop` e tentativa futura `FiscalEmissionAttempt(operation_type="nfse_manifestation")`. Nao criar `FiscalDocument(nfse)` nesta fase nem exigir backfill. Manifestacao nao e substituicao nem cancelamento: e uma trilha/evento fiscal sobre NFS-e existente, com payload proprio e resposta remota propria.

Campos candidatos: `workshop`, `nfse_item`, `manifestation_type`, `manifestation_code`, `manifestation_role`, `request_payload`, `response_payload`, `remote_uuid`, `remote_status`, `xml_manifestation`, `status`, `is_uncertain`, `created_by`, `created_at` e `updated_at`. A implementacao futura pode usar enums para papel (`taker`, `intermediary`), tipo (`confirmation`, `rejection`) e status (`started`, `sent`, `succeeded`, `failed`, `uncertain`).

Constraints planejadas: no maximo uma manifestacao ativa, incerta ou concluida por `workshop`, `nfse_item`, `manifestation_code` e `manifestation_role`; falha conclusiva pode permitir nova tentativa da mesma intencao. NFS-e cancelada, substituida ou incerta deve ser bloqueada antes de criar a intencao.

Capability planejada: reutilizar/confirmar `NfseMunicipalCapability.manifestation_enabled` como gate municipal e adicionar/usar flag administrativa de oficina `nfse_manifestation_enabled` se a fase funcional exigir separacao entre capacidade remota e rollout interno. Se Padrao Nacional nao estiver confirmado, a operacao deve bloquear mesmo com permissao de usuario.

### Modelagem implementada na Fase 3.6.1

Criado `NfseManifestation` vinculado obrigatoriamente a `NfseItem` e `workshop`, sem `FiscalDocument(nfse)` e sem backfill. A entidade registra tipo, codigo de evento, papel do manifestador, motivo/justificativa de rejeicao, payload congelado, resposta remota, UUID/status remoto, XML/artefato de manifestacao, status local e usuario criador.

Constraint condicional impede mais de uma manifestacao ativa, incerta ou concluida para a mesma NFS-e, evento e manifestador. A operation type e `nfse_manifestation`. A capability usada e `NfseMunicipalCapability.national_standard_enabled=True` + `manifestation_enabled=True`; nenhuma flag de emissao manual foi criada.

`NfseSubstitution` possui preview one-to-one, original, substituta opcional, UUIDs, codigo original, motivo, payload/response, snapshots XML separados, status, `is_uncertain`, solicitante e timestamps. Constraint impede duas operacoes ativas para a mesma original. `NfseItemStatus.substituido` protege anti-regressao. Nao existe `FiscalDocument(nfse)`.

## Modelagem recomendada pela Fase 3.7.0

Proxima fase recomendada: `3.7P - Preview de emissao manual nova de NFS-e`, sem `FiscalEmissionAttempt`, sem `NfseItem` emitido e sem chamada Webmania.

Entidade candidata: preview/snapshot de NFS-e manual nova, escopada por oficina, empresa/capability municipal e usuario. A preview deve congelar:

- tomador e endereco;
- servico, codigo municipal, discriminacao, CNAE/atividade quando aplicavel;
- valores, descontos, retencoes, ISS e IBS/CBS;
- ambiente, municipio, provedor/capability, serie/numero/RPS ou regra de numeracao;
- payload planejado sanitizado, hash, status, criador/aprovador e timestamps.

Status candidatos: `draft`, `ready`, `approved`, `rejected`, `archived`. Aprovacao torna payload, tomador, servico, valores, impostos, ambiente e municipio imutaveis.

Uma fase funcional posterior podera consumir somente preview aprovada para criar a intencao remota. Essa decisao futura deve escolher explicitamente se reutiliza `NfseRequest`/`NfseItem` ou se cria uma projecao fiscal nova para emissao manual; a fase preparatoria nao decide ownership definitivo nem executa backfill.

## Fase 3.7.1 - NfseManualEmission

Foi criada a entidade `NfseManualEmission` como intencao remota da emissao manual nova. Ela referencia obrigatoriamente `NfseManualEmissionPreview` aprovada, preserva `company`, `environment`, `rps_number`, `rps_series`, `request_payload`, `response_payload`, `remote_uuid`, `codigo_verificacao`, XML/PDF e status. O payload e imutavel apos persistido.

`NfseItem.workorder` passa a aceitar nulo para permitir NFS-e manual sem OS legada. O `NfseItem` so e criado quando o retorno remoto aprovado confirma `modelo=nfse` e `uuid`; nao ha `FiscalDocument(nfse)` nesta fase. A tentativa remota usa `FiscalEmissionAttempt(operation_type="nfse_manual_emission")`.
## Fase 3.8.0 - impacto de dominio pos-emissao manual NFS-e

A Fase 3.7.1 foi validada no checkpoint `2cb35206` e introduziu `NfseManualEmission` como origem imutavel de uma `NfseItem` manual autorizada. A emissao manual nao cria `FiscalDocument(nfse)` e nao deve passar a criar apenas para cancelar, substituir ou manifestar.

Para o proximo ciclo, a fonte local mais segura e `NfseManualEmission.nfse_item`: quando presente e autorizado, o `NfseItem` possui UUID/codigo/artefatos suficientes para reutilizar operacoes NFS-e ja existentes.

Decisao de modelagem para a proxima fase: **estender com seguranca o cancelamento NFS-e existente**. `NfseCancellation` deve continuar sendo a trilha de cancelamento vinculada ao `NfseItem`; se houver dependencia legada em `NfseRequest`/OS, ela deve ser relaxada de modo compatível para aceitar `NfseItem` manual, sem alterar `NfseManualEmissionPreview`, sem alterar `NfseManualEmission.request_payload` e sem criar `FiscalDocument(nfse)`.

Substituicao da NFS-e manual pode reutilizar `NfseSubstitutionPreview` e `NfseSubstitution`, mas exige fase propria porque cria nova NFS-e substituta e precisa adaptar a elegibilidade para origem manual. Manifestacao da NFS-e manual tambem exige fase separada condicionada a Padrao Nacional/capability.

Resultado da Fase 3.8.1: `NfseCancellation` foi reutilizado. A unica alteracao de modelagem foi permitir `request=null` para cancelamentos vinculados a `NfseItem` manual, sem criar modelo novo e sem introduzir `FiscalDocument(nfse)`. Quando existe `NfseRequest`, o fluxo legado permanece com a mesma relacao e validacao. Quando a origem e manual, a relacao segura e `NfseCancellation.item -> NfseItem -> NfseManualEmission`.

`NfseManualEmissionPreview` e `NfseManualEmission.request_payload` permanecem imutaveis; o cancelamento nao altera o payload aprovado nem cria nova NFS-e.

## Fase 3.9.0 - decisao de dominio apos ciclo minimo manual

O ciclo manual minimo validado (`preview -> emissao -> cancelamento`) confirma que a origem manual pode conviver com as entidades NFS-e existentes sem criar `FiscalDocument(nfse)` generalizado. A alteracao `NfseCancellation.request` opcional mostrou que operacoes sobre `NfseItem` manual devem depender da relacao segura `NfseManualEmission.nfse_item`, nao de `NfseRequest`/OS.

Para a proxima fase recomendada, a modelagem deve reutilizar `NfseSubstitutionPreview` e `NfseSubstitution` com elegibilidade ampliada para `NfseItem` manual. A original manual continua sendo a `NfseItem` vinculada a `NfseManualEmission`; a substituta deve ser uma nova `NfseItem`, com UUID, numero, codigo de verificacao, XML/PDF e status proprios. A preview aprovada deve congelar o novo RPS e o snapshot da original, sem recalcular a partir da emissao manual, de OS, de cliente ou de classe fiscal atual.

Nao criar fluxo paralelo especifico para `NfseManualEmission` se a extensao segura do fluxo atual bastar. Nao criar `FiscalDocument(nfse)`, backfill ou dominio de NFS-e recebida/importada nesta fase.

## Fase 3.9.1 - modelagem implementada para substituicao manual

A Fase 3.9.1 nao criou novo modelo. `NfseSubstitutionPreview` e `NfseSubstitution` foram mantidos como trilhas unicas de substituicao NFS-e.

Extensao implementada:

- a elegibilidade de `NfseSubstitutionPreview` passa a aceitar `NfseItem` originado por `NfseManualEmission`;
- quando a original tem `request_id=None`, a relacao segura exigida e `NfseItem -> NfseManualEmission`;
- a capability de substituicao para origem manual vem de `NfseManualEmission.preview.municipal_capability`;
- a substituta e criada como nova `NfseItem` somente apos confirmacao remota valida;
- se a original manual nao tem `NfseRequest`/OS, a substituta tambem permanece sem `request`/`workorder`;
- `FiscalDocument(nfse)` nao foi criado.

Dados preservados: `NfseManualEmissionPreview`, `NfseManualEmission.request_payload`, XML original da NFS-e manual e snapshot do XML original. XML/PDF da substituta ficam em `NfseSubstitution`.

## Fase 3.10.0 - modelagem reavaliada para manifestacao manual

A modelagem existente de `NfseManifestation` continua adequada para NFS-e local Padrao Nacional quando o papel fiscal do manifestador e seguro. Para a NFS-e manual emitida pelo proprio Hunter, a entidade local confiavel e `NfseManualEmission -> NfseItem`, mas ela representa documento emitido pela oficina. A modelagem nao contem, nesta data, uma prova de que a oficina atua como tomadora ou intermediaria da propria NFS-e manual.

Conclusao de dominio: nao criar modelo paralelo de manifestacao manual e nao ampliar `NfseManifestation` nesta fase. A decisao correta e manter manifestacao manual pendente ate existir criterio explicito de papel fiscal. Se uma fase futura for aprovada, a preferencia segue sendo extensao segura de `NfseManifestation`, nao fluxo separado, com bloqueio para manual cancelada, substituida, uncertain, sem UUID ou sem Padrao Nacional confirmado.

NFS-e recebida/importada de terceiros permanece fora do dominio atual. Ela deve ter fase propria antes de ser usada como base de manifestacao, porque exige XML recebido, identificadores remotos, papel da oficina, associacao segura a cliente/oficina e protecao cross-workshop.

## Fase 3.11.0 - modelagem planejada para NFS-e recebida/importada

Entidade planejada: `NfseReceivedDocument`.

Responsabilidade: representar NFS-e emitida por terceiro e recebida pela oficina em papel fiscal validado. Nao substitui `NfseItem` emitido pelo Hunter, nao nasce de `NfseManualEmission`, nao e `NfseSubstitution`, nao e `NfseCancellation` e nao executa `NfseManifestation`.

Campos minimos planejados, ajustados ao estilo do projeto:

- `workshop`;
- `company`;
- `source` (`xml_upload`, `webmania_query`, `webhook_pending`, `manual_identifier`, `batch_import`, `external_integration`);
- `xml_snapshot`;
- `xml_hash`;
- `uuid`;
- `access_key_or_identifier`;
- `verification_code`;
- `provider_tax_id`;
- `taker_tax_id`;
- `intermediary_tax_id`;
- `municipality_code`;
- `environment`;
- `issue_date`;
- `service_amount`;
- `status`;
- `remote_status`;
- `role` (`taker`, `intermediary`, `provider`, `unknown`, `multiple`, `divergent`);
- `validation_status`;
- `validation_errors`;
- `raw_payload`;
- `created_by`;
- timestamps herdados de `TimeStampedModel`.

Constraints planejadas: unicidade por oficina para `xml_hash`, UUID e chave/identificador quando preenchidos; bloqueio de documento emitido pelo proprio Hunter como recebido; bloqueio cross-workshop; falhas de validacao preservadas em `validation_errors` sem criar `NfseItem` ou `FiscalDocument(nfse)`.

Manifestacao futura deve depender de `NfseReceivedDocument` validado, papel `taker` ou `intermediary`, Padrao Nacional confirmado, UUID/chave segura e capability `manifestation_enabled`. Papel `provider`, `unknown`, `multiple` ou `divergent` bloqueia manifestacao.

## Fase 3.11.1 - modelagem implementada para NFS-e recebida

Foi criado `NfseReceivedDocument` como entidade propria de NFS-e recebida por XML. A entidade guarda `workshop`, `company`, origem `xml_upload`, `xml_snapshot`, `xml_hash`, UUID, identificador/chave, codigo de verificacao, CNPJs de prestador/tomador/intermediario, municipio, ambiente, data, valor, status local/remoto, role fiscal, status de validacao, erros, payload parseado e usuario criador.

Tambem foi criada a flag `WebmaniaCompany.nfse_received_import_enabled`. A importacao local valida XML, hash, duplicidade, papel fiscal e colisao com documentos emitidos pelo Hunter. Nao cria `NfseItem`, nao cria `FiscalDocument(nfse)`, nao cria `FiscalEmissionAttempt` e nao cria `NfseManifestation`.

## Fase 3.12.0 - modelagem recomendada para manifestacao de NFS-e recebida

Decisao de dominio: **extensao segura de `NfseManifestation` existente**, nao fluxo paralelo especifico.

A modelagem atual de `NfseManifestation` e adequada para payload, status, tentativa, retorno remoto, UUID da manifestacao, webhook e reconciliacao, mas hoje exige `nfse_item` obrigatorio. A fase funcional futura deve introduzir um vinculo alternativo a `NfseReceivedDocument` (`received_document` ou nome equivalente), mantendo `nfse_item` para manifestacoes de NFS-e local existentes.

Regra estrutural planejada: exatamente uma origem por manifestacao. Uma instancia deve ter `nfse_item` XOR `received_document`; instancias sem origem ou com duas origens devem ser invalidas. A constraint/idempotencia deve mudar de `nfse_item + event + manifestor` para origem normalizada (`nfse_item` ou `received_document`) + `manifestation_code` + `manifestor`, sempre escopada por oficina.

Elegibilidade de recebido: `validation_status=validated`, role `taker` ou `intermediary`, UUID seguro, XML snapshot/hash preservados, mesma oficina/empresa, status nao cancelado/substituido/uncertain, Padrao Nacional e `manifestation_enabled` confirmados por capability segura. `provider`, `unknown`, `multiple`, divergente, duplicado ou cross-workshop bloqueiam.

Dados preservados: a manifestacao nao altera `xml_snapshot`, `xml_hash`, CNPJs, municipio, ambiente, valor, status remoto extraido ou payload parseado do recebido. XML/artefato de manifestacao, se retornado, permanece separado em `NfseManifestation`.

## Fase 3.13.1 - modelagem da consulta auxiliar de NFS-e recebida

Decisao de dominio: criar `NfseReceivedDocumentConsultation` como snapshot consultivo separado de `NfseReceivedDocument`.

Responsabilidade: guardar cada retorno de consulta Webmania para uma NFS-e recebida ja validada por XML. A entidade nao e fonte primaria fiscal; apenas registra metadados de consulta, resposta sanitizada, status remoto consultivo, UUID remoto consultivo, confirmacao consultiva de Padrao Nacional, divergencias e erros.

Campos implementados:

- `workshop`;
- `received_document`;
- `identifier`;
- `identifier_source`;
- `request_metadata`;
- `response_payload`;
- `remote_status`;
- `remote_uuid`;
- `remote_updated_at`;
- `national_standard_confirmed`;
- `divergences`;
- `validation_errors`;
- `consulted_by`.

Tambem foi criada a flag `WebmaniaCompany.nfse_received_consultation_enabled`, separada de `nfse_received_import_enabled`, para permitir desligar a consulta remota sem impedir o registro local por XML.

Dados preservados em `NfseReceivedDocument`: `xml_snapshot`, `xml_hash`, UUID, identificador, codigo de verificacao, CNPJs, municipio, ambiente, data, valor, status remoto extraido do XML, role fiscal e payload parseado. Divergencias da consulta nunca sobrescrevem esses campos.

Nao foram criados `NfseItem`, `FiscalDocument(nfse)`, `NfseManifestation` ou `FiscalEmissionAttempt` para consulta.

## Fase 3.14.0 - modelagem recomendada para o proximo bloco

Status: em planejamento documental em 2026-06-29. A Fase 3.13.1 foi validada no checkpoint `01f0924d`, com `NfseReceivedDocumentConsultation`, migration `0071`, flag `nfse_received_consultation_enabled` e consulta GET-only implementados.

Decisao de dominio recomendada: a proxima fase deve implementar importacao em lote de XML de NFS-e recebida, reaproveitando `NfseReceivedDocument` como entidade primaria. A criacao de recebida continua exigindo XML; consulta Webmania nao vira fonte primaria.

Modelagem esperada para 3.14.1:

- `NfseReceivedDocument` permanece o registro fiscal individual e imutavel quanto a XML/hash/dados extraidos.
- O lote pode ser representado por entidade leve de auditoria, por exemplo `NfseReceivedDocumentImportBatch`, e resultados por arquivo, se isso for necessario para relatorio persistido.
- Duplicidade deve considerar hash, UUID e identificador dentro da oficina/empresa.
- Arquivos validos podem ser persistidos mesmo quando outros arquivos do lote falham, desde que o relatorio por arquivo seja completo.
- Nenhum lote pode substituir XML validado de documento existente.
- Nenhum lote pode criar `NfseItem`, `FiscalDocument(nfse)` ou `NfseManifestation`.

Integracao e-mail/ERP, CT-e/MDF-e/NFCom/DC-e, eventos IBS/CBS pendentes, creditos/debitos restantes e complementar tributaria exigem modelagens de dominio proprias e permanecem fora do escopo imediato.

## Fase 3.14.1 - modelagem implementada para lote XML de recebidas

Foram criados `NfseReceivedImportBatch` e `NfseReceivedImportBatchItem` pela migration `0072`.

`NfseReceivedImportBatch` representa a execucao auditavel do lote, com oficina, empresa, origem `xml_upload`, status, totais, contadores e usuario criador.

`NfseReceivedImportBatchItem` representa o resultado por arquivo, com nome sanitizado, hash XML, status, documento recebido importado quando houver, codigo/mensagem de erro, erros de validacao e resumo parseado.

O documento fiscal individual continua sendo `NfseReceivedDocument`. O lote nao cria nova fonte fiscal, nao cria documento sem XML e nao altera XML/hash/dados extraidos de documentos existentes.

## Fase 3.15.0 - modelagem recomendada apos consolidacao recebida

Status: validada documentalmente em 2026-06-29 no checkpoint `4815728b`. A Fase 3.14.1 foi validada no checkpoint `b53e862b`.

Decisao de dominio: a proxima fase deve ser preparatoria/documental para integracao e-mail/ERP como fonte externa de XMLs, sem implementar pipeline real ainda.

Modelagem a avaliar na fase futura:

- fonte externa por oficina/empresa, com credenciais e escopo;
- caixa/fila de anexos antes de qualquer importacao fiscal;
- fingerprint por origem/anexo/hash para idempotencia;
- vinculo posterior com `NfseReceivedImportBatch`;
- trilha de auditoria de quem configurou, quando processou e por qual regra;
- isolamento estrito por oficina e empresa.

`NfseReceivedDocument` e `NfseReceivedImportBatch` continuam sendo a fronteira fiscal. E-mail/ERP nao deve criar documento sem XML nem substituir XML validado.

## Fase 3.15.1 - modelagem planejada da caixa de entrada externa de XML

Status: em planejamento documental em 2026-06-29. A Fase 3.15.0 foi validada documentalmente no checkpoint `4815728b`.

Decisao de dominio: escolher **Opcao A - Implementar caixa de entrada externa de XML** em fase funcional futura, como dominio local intermediario. A fase atual apenas planeja essa modelagem; nao cria models, migrations ou services.

Modelo conceitual recomendado:

- `NfseExternalXmlInbox`: configuracao/logica de uma origem externa por oficina/empresa, com tipo de fonte, identificador, estado, flags e metadados de auditoria.
- `NfseExternalXmlInboxItem`: XML candidato recebido da origem externa, ainda pendente de revisao humana e antes de qualquer importacao fiscal.

Campos planejados para o item: `workshop`, `company`, `source_type`, `source_identifier`, `original_filename`, `content_type`, `xml_snapshot`, `xml_hash`, `received_at`, `status`, `validation_errors`, `linked_batch`, `linked_received_document`, `created_at` e `updated_at`.

Estados planejados: `pending_review`, `approved_for_batch`, `imported`, `discarded`, `rejected`, `duplicate` e `error`. Um item pendente nao e documento fiscal; somente o lote XML validado pode criar `NfseReceivedDocument`.

Relacao com lote XML: a recomendacao e **B - caixa de entrada pendente para usuario revisar e acionar lote**. A criacao automatica de lote a partir de XML coletado deve ficar adiada, porque aumenta risco de importacao silenciosa e documento de oficina errada.

Fronteira fiscal permanente: origem externa entrega XML candidato; `NfseReceivedImportBatch` e `NfseReceivedDocument` continuam sendo o nucleo fiscal. A futura implementacao nao deve criar documento recebido sem XML, nao deve substituir XML validado, nao deve criar `NfseItem`, `FiscalDocument(nfse)` ou `FiscalEmissionAttempt` e nao deve manifestar automaticamente.

## Fase 3.15.2 - modelagem implementada da inbox externa

Status: em implementacao controlada em 2026-06-30. A Fase 3.15.1 foi validada documentalmente no checkpoint `5882cd4e`.

Modelagem criada: `WebmaniaCompany.nfse_external_xml_inbox_enabled`, `NfseExternalXmlInbox` e `NfseExternalXmlInboxItem`.

`NfseExternalXmlInbox` representa a operacao local/manual de entrada de XML candidato por oficina/empresa, com origem `manual_upload`, status, contadores, usuario criador e auditoria de processamento.

`NfseExternalXmlInboxItem` representa o XML candidato com nome original/seguro, XML snapshot, hash, tamanho, metadados de origem, status, erros, resumo parseado, aprovacao, descarte, processamento e vinculos com `NfseReceivedImportBatch`, `NfseReceivedImportBatchItem` e `NfseReceivedDocument`.

O item da inbox nao e documento fiscal. Documento recebido continua nascendo somente pelo lote/importador XML validado. A inbox nao cria `NfseItem`, `FiscalDocument(nfse)`, `FiscalEmissionAttempt` ou `NfseManifestation`.

## Fase 3.16.0 - dominio apos inbox externa local

Status: em planejamento documental em 2026-06-30. A Fase 3.15.2 foi validada no checkpoint `517d25b8`.

O bloco NFS-e recebida agora possui registro unitario por XML, manifestacao de recebida, consulta auxiliar GET-only, lote XML e inbox externa local/manual/assistida. A fonte fiscal continua sendo `NfseReceivedDocument` criado pelo pipeline XML/lote.

A proxima evolucao de menor risco no dominio e ampliar a propria inbox local: filtros, busca, relatorio/exportacao, acoes em massa controladas, retencao, reprocessamento explicito e painel de auditoria. Conectores reais de e-mail/ERP/pasta/webhook devem continuar fora do dominio funcional enquanto autenticacao, segregacao por oficina e contratos externos nao estiverem definidos.

## Fase 3.16.1 - dominio operacional da inbox XML

Status: em implementacao tecnica em 2026-06-30. A Fase 3.16.0 foi validada documentalmente no checkpoint `267fc601`.

`NfseExternalXmlInbox` e `NfseExternalXmlInboxItem` foram mantidos como dominio unico da inbox local. A fase nao criou nova entidade fiscal, nao criou documento recebido diretamente e nao alterou `NfseReceivedDocument`.

Foram adicionadas operacoes de leitura/gestao local: filtros, busca, exportacao CSV sem XML bruto e acoes em massa. O processamento em massa continua selecionando itens aprovados e delegando a criacao fiscal exclusivamente ao `NfseReceivedImportBatch`.

Retencao e reprocessamento foram mantidos como pendencias futuras, porque exigem politica fiscal explicita e regras adicionais para nao duplicar lote/documento.
