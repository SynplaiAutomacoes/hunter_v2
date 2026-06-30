# PRD seguranca, idempotencia, webhooks e reconciliacao

## Seguranca

- Credenciais Webmania devem continuar em settings ou `WebmaniaCompany` criptografada.
- Certificado e logo devem reutilizar `apps/workshops/services/files.py`.
- Downloads devem passar por view autenticada, oficina ativa e permissao.
- Payloads e logs devem ser sanitizados.
- Headers secretos nunca devem ser persistidos.
- Payload bruto de webhook pode ser persistido, mas deve ser protegido por permissao.
- Acesso a payload/log fiscal deve ser mais restrito que acesso a listagem.

## Isolamento por oficina

Toda action deve validar:

- usuario autenticado;
- oficina ativa;
- membership;
- permissao;
- ownership do documento;
- ownership do download;
- permissao para payload/log.

## Idempotencia

Regras nao negociaveis:

- Uma intencao fiscal nao pode causar duas chamadas de emissao remota.
- A idempotencia deve ser persistida no banco.
- Cache nao pode ser protecao principal.
- Chave principal de idempotencia nao pode depender so de campos mutaveis de UI.
- Estado `uncertain` deve existir.
- Tentativa `uncertain` nunca deve ser reenviada automaticamente.
- Antes de nova emissao, consultar ou reconciliar estado remoto.

Fluxo:

```text
intencao criada
-> tentativa persistida e bloqueada
-> chamada remota unica
-> resposta persistida
-> documento local atualizado
-> webhook/reconciliacao atualizam o mesmo documento
```

## FiscalEmissionAttempt implementado na Fase 1

Na Fase 1 foi implementada a estrutura minima persistida para estabilizar os models legados de NF-e/NFS-e, sem criar ainda o dominio unificado `FiscalDocument`.

Campos implementados:

- `workshop`
- `document_kind`: `nfe`, `nfse`
- `request_model`, `request_id`
- `idempotency_key`
- `status`: `created`, `sent`, `succeeded`, `failed`, `uncertain`
- `remote_model`
- `remote_uuid`, `remote_key`
- `request_payload`
- `response_payload`
- `error_message`
- `sent_at`, `completed_at`, timestamps herdados.

Indice unico:

- `workshop`, `document_kind`, `idempotency_key`.

Decisao de compatibilidade:

- `account`, `origin_type` e `origin_id` ficam para o dominio unificado futuro. Na Fase 1, a oficina e o par `request_model`/`request_id` preservam compatibilidade com `NfeRequest` e `NfseRequest`.
- Payloads sao sanitizados antes de persistir. Headers e credenciais nao sao persistidos.
- Timeout ou resposta invalida apos envio remoto entram em `uncertain`.
- Tentativa `uncertain`, `sent` ou `succeeded` bloqueia reenvio automatico da mesma intencao.

## Webhook

Deve definir:

- autenticacao por token/header configurado;
- persistencia do payload bruto antes do processamento;
- fingerprint idempotente por modelo, uuid e hash canonico do payload;
- resolucao prioritaria por UUID;
- comportamento para chave alterada em contingencia;
- eventos fora de ordem;
- webhook duplicado;
- webhook antes da projecao local;
- payload desconhecido;
- reprocessamento seguro;
- auditoria de erro.

Implementado na Fase 1:

- `WebmaniaWebhookEvent.fingerprint` com constraint unica condicional.
- `store_webhook_event` usa `get_or_create` por fingerprint para deduplicar payload identico.
- `process_webhook_event` nao reprocessa evento ja marcado como processado.
- Eventos fora de ordem nao regridem status de maior prioridade.
- UUID ambiguo entre oficinas fica pendente e nao atualiza documentos de outra oficina.

## Reconciliacao

Reconciliar:

- documentos `processing`;
- documentos `contingency`;
- tentativas `uncertain`;
- documentos aprovados sem downloads;
- webhooks pendentes.

Regras:

- Nunca emitir durante reconciliacao.
- `uncertain` exige consulta remota antes de liberar nova tentativa.
- `processing` deve permanecer aguardando se remoto ainda processa.
- `contingency` deve atualizar chave/URLs quando autorizada.
- Downloads ausentes devem ser recuperados por URLs remotas quando disponiveis.

Management command futuro:

- `--model`
- `--workshop`
- `--status`
- `--limit`
- `--dry-run`
- `--include-uncertain`
- relatorio de processados, atualizados, ignorados e falhas.

Implementado na Fase 1:

- O comando existente processa webhooks pendentes, NF-e em `processando`/`contingencia`, NFS-e em `processando`/`contingencia`/`agendado` e tentativas `uncertain`.
- Tentativas `uncertain` sao reconciliadas por consulta do item local quando ja existe `NfeItem` ou `NfseItem`.
- Nenhum caminho de reconciliacao chama emissao remota.

## Fase 2.0 - Idempotencia por operacao NF-e/NFC-e

Todas as operacoes novas da Fase 2 devem reutilizar ou evoluir `FiscalEmissionAttempt` para representar tentativas por operacao, nao apenas por emissao inicial.

Chave recomendada:

```text
{document_kind}:{operation}:{workshop_id}:{subject_identifier}:{operation_fingerprint}
```

Onde:

- `document_kind`: `nfe` ou `nfce`.
- `operation`: `cce`, `return`, `reversal`, `complementary`, `complementary_tax`, `adjustment`, `nfe_credit_emission`, `nfe_debit_emission`, `nfce_emission`, `manifestation`, `ibs_cbs_event`, `ibs_cbs_cancel`, `nfce_replacement_cancel`, `nfce_inutilization`.
- `subject_identifier`: UUID/chave/documento original/evento original quando existir; para ajuste sem original, usar identificador deterministico da intencao manual, nunca texto livre mutavel isolado da UI.
- `operation_fingerprint`: hash canonico dos campos fiscais essenciais, sanitizado e estavel.

| Operacao | Chave de idempotencia | Estado `uncertain` | Bloqueio de reenvio |
| -------- | --------------------- | ------------------ | ------------------- |
| CC-e | `nfe:cce:{workshop}:{original_uuid_or_key}:{hash_correcao}` | Timeout apos envio ou resposta sem identificador/evento | Bloquear mesma correcao para mesma nota ate reconciliar. |
| Devolucao | `hash(workshop_id, derived_document_id, operation_type, request_generation)` | Timeout/resposta incompleta apos envio | Bloquear documento derivado e saldo reservado ate consulta/reconciliacao; nao reenviar automaticamente. |
| Estorno via devolucao | `hash(workshop_id, derived_document_id, operation_type, request_generation)` | Timeout/resposta incompleta | Bloquear estorno derivado ate consulta/reconciliacao. |
| Complementar | `hash(workshop_id, complementary_document_id, operation_type, request_generation)` | Timeout/resposta incompleta | Bloquear o documento complementar derivado em `uncertain`; nao reenviar automaticamente. |
| Ajuste | `hash(workshop_id, adjustment_document_id, operation_type, request_generation)` | Timeout/resposta incompleta | Bloquear o documento de ajuste derivado/avulso em `uncertain`; nao exigir documento original. |
| Nota Fiscal de Credito | `hash(workshop_id, credit_document_id, "nfe_credit_emission", request_generation)` | Timeout/resposta incompleta | Bloquear a intencao persistida ate consulta/reconciliacao; nao usar somente payload como identidade. |
| Nota Fiscal de Debito | `hash(workshop_id, debit_document_id, "nfe_debit_emission", request_generation)` | Timeout/resposta incompleta | Bloquear a intencao persistida ate consulta/reconciliacao; nao usar somente payload como identidade. |
| NFC-e | `nfce:emission:{workshop}:{origin_type}:{origin_id}:{hash_itens_pagamento}` | Timeout/resposta incompleta | Bloquear emissao da mesma origem/intencao. |
| Manifestacao | `nfe:manifestation:{workshop}:{chave}:{evento}` | Timeout/resposta sem protocolo/status | Bloquear mesma manifestacao ate consulta. |
| IBS/CBS | `nfe:ibs_cbs_event:{workshop}:{original_key}:{event_code}:{hash_payload}` | Timeout/resposta sem evento | Bloquear evento identico. |
| Cancelamento IBS/CBS | `nfe:ibs_cbs_cancel:{workshop}:{event_identifier}:{hash_motivo}` | Timeout/resposta sem status | Bloquear cancelamento do mesmo evento. |
| Cancelamento/substituicao NFC-e | `nfce:replacement_cancel:{workshop}:{original_key}:{replacement_key_or_hash}` | Timeout/resposta incompleta | Bloquear ate consulta do status da NFC-e/evento. |

Estados:

- `started`: tentativa persistida antes da chamada remota.
- `sent`: chamada remota iniciada.
- `succeeded`: Webmania retornou evento/documento aceito ou status final conhecido.
- `failed`: erro remoto claro sem efeito fiscal.
- `uncertain`: chamada pode ter chegado na Webmania, mas o retorno local nao confirmou o resultado.

Regras adicionais:

- Nenhuma subfase pode usar apenas cache para idempotencia.
- Fase 2.2A nao pode usar apenas `original + itens + quantidades + CFOP` como identidade definitiva, pois devolucoes parciais legitimas podem ter payload equivalente. A tentativa deve estar ligada a uma intencao derivada persistida ou ao proprio `FiscalDocument` derivado criado antes da chamada remota.
- Payload sanitizado de devolucao/estorno deve ser congelado apos o envio; nova tentativa para o mesmo derivado com payload diferente e conflito.
- Devolucao parcial usa sequenciais fiscais da NF-e original em `produtos` e vetor `quantidade` alinhado por indice; IDs internos de catalogo/banco nao podem compor o contrato remoto.
- NF-e externa minima por chave manual nao permite devolucao parcial enquanto a ordem fiscal dos itens nao for importada/validada por XML ou fonte fiscal especifica.

### Idempotencia Fase 2.2B - Nota complementar

Regra: a identidade operacional da complementar e o `FiscalDocument` complementar derivado, nao apenas o payload fiscal. Isso permite complementares legitimas distintas com payload parecido em momentos diferentes e evita retry duplicado em timeout.

Fluxo obrigatorio:

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

Estados:

- `started`: documento complementar criado e tentativa aberta.
- `sent`: chamada remota iniciada.
- `succeeded`: resposta remota clara e persistida.
- `failed`: erro antes de envio efetivo ou rejeicao clara.
- `uncertain`: timeout/resposta invalida apos possivel envio; bloqueia reenvio e exige consulta/reconciliacao.

Payload:

- Congelar `request_payload` sanitizado apos envio.
- Nao persistir headers ou credenciais.
- Separar `complementary_price_quantity`, `complementary_tax` e `complementary_import_addition` para idempotencia, auditoria e UI.
- Fase 2.2B.1 implementa somente `complementary_price_quantity`; `complementary_tax`, IBS/CBS e `complementary_import_addition` permanecem sem codigo.

Webhook complementar:

- Resolver primeiro por `remote_uuid` do derivado.
- Fallback por tentativa associada (`FiscalEmissionAttempt.remote_uuid`).
- Fallback por chave somente se resolver um unico documento complementar derivado na oficina.
- Rejeitar associacao ambigua.
- Atualizar XML/DANFE/status/log somente no derivado.
- Nunca alterar status da NF-e original.
- Eventos devem ter tentativa propria e registro em `FiscalDocumentEvent`.
- Documentos derivados devem ter tentativa propria e registro em `FiscalDocument`.
- Webhook/reconciliacao devem atualizar a tentativa/evento/documento correspondente e nunca chamar endpoint de emissao/evento.
- Payloads persistidos devem remover headers, tokens, certificados, secrets e dados sensiveis nao essenciais.

### Idempotencia Fase 2.2C - Nota de ajuste

Regra: a identidade operacional do ajuste e o `FiscalDocument` de ajuste criado antes do envio, nao o payload fiscal livre. Isso permite dois ajustes legitimos com valores semelhantes e impede que retry, concorrencia ou timeout transmitam a mesma intencao duas vezes.

Fluxo validado:

```text
criar FiscalDocument de ajuste em estado inicial
-> criar/bloquear FiscalEmissionAttempt associado ao ajuste
-> executar uma unica chamada POST /1/nfe/ajuste/
-> persistir retorno no ajuste
-> webhook/reconciliacao atualizam apenas o ajuste
```

Chave:

```text
hash(workshop_id, adjustment_document_id, operation_type, request_generation)
```

Regras:

- `uncertain` bloqueia reenvio automatico.
- Payload sanitizado fica congelado apos envio.
- Regime tributario deve ser validado antes do gateway.
- Webhook resolve primeiro por UUID do ajuste e usa tentativa associada como fallback seguro.
- Fallback ambiguo nao atualiza documento.
- NF-e relacionada opcional nao pode ter status alterado por resposta, webhook ou reconciliacao do ajuste.
- Cenarios de estorno SC/ES cobertos por devolucao devem ser direcionados/bloqueados antes de `/1/nfe/ajuste/`.

## Fase 2.0 - Webhooks e reconciliacao NF-e/NFC-e

- Webhook deve resolver por `uuid` primeiro e por `chave` somente quando nao houver ambiguidade dentro da oficina.
- Evento CC-e deve ser associado ao documento original e nao criar uma nota comum.
- Webhook de documento derivado deve atualizar o `FiscalDocument` derivado e manter link com o original.
- Evento IBS/CBS fora de ordem nao pode regredir estado de evento ja autorizado/cancelado.
- Reconciliacao Fase 2 deve consultar status por `GET /1/nfe/consulta/` e downloads por URLs retornadas, sem reenviar operacao.

### Fase 2.3.0 - Idempotencia e webhook NFC-e

Padrao recomendado:

```text
criar FiscalDocument NFC-e em estado inicial
-> criar/bloquear FiscalEmissionAttempt(operation_type="nfce_emission")
-> congelar payload sanitizado
-> executar uma unica chamada POST /1/nfe/emissao/ com modelo=2
-> persistir retorno no documento NFC-e
-> webhook/reconciliacao atualizam somente o documento NFC-e
```

Chave recomendada:

```text
hash(workshop_id, nfce_document_id, operation_type, request_generation)
```

Regras:

- Nao usar apenas itens/pagamento como identidade, porque duas vendas consumidor legitimas podem ter payload equivalente.
- Documento `uncertain` bloqueia reenvio automatico e exige consulta/reconciliacao.
- Webhook deve resolver primeiro por UUID; fallback por tentativa/chave somente se houver candidato unico na oficina.
- `modelo=nfce` deve atualizar somente `FiscalDocument(document_type="nfce")`; nao atualizar `NfeItem` legado por engano.
- Chave pode mudar em contingencia; UUID deve ser preferencial.
- Downloads XML/DANFE NFC-e devem passar por view autorizada e nao expor URL remota sem permissao.
- Credenciais CSC e headers Webmania nunca devem ser persistidos em payload/log.
## Atualizacao Fase 2.3.2 - Idempotencia E Webhook NFC-e Cancelamento

- Chave de idempotencia: `hash(workshop_id, nfce_document_id, nfce_cancellation, cancellation_event_id, request_generation)`.
- Fluxo: validar documento elegivel, criar evento, criar tentativa, congelar payload sanitizado, chamar `PUT /1/nfe/cancelar/` uma unica vez, persistir retorno no evento e atualizar documento apenas quando cancelamento for confirmado.
- Timeout marca evento e tentativa como `uncertain`; novo cancelamento automatico fica bloqueado ate reconciliacao.
- Webhook `modelo=nfce` com status de cancelamento tenta resolver evento de cancelamento antes de atualizar a NFC-e normal.
- Associacao ambigua e rejeitada; webhook duplicado e idempotente por fingerprint.
- CSC, tokens e credenciais continuam fora de payloads/logs persistidos.

## Atualizacao Fase 2.3.3 - Inutilizacao NFC-e

- A inutilizacao NFC-e nao usa `FiscalDocumentEvent`, pois nao existe NFC-e emitida a cancelar.
- A intencao persistente e `FiscalNumberInutilization`, escopada por oficina, ambiente, serie e faixa.
- A tentativa usa `FiscalEmissionAttempt(operation_type="nfce_inutilization")` associada a `FiscalNumberInutilization`.
- Chave idempotente: `hash(workshop_id, inutilization_id, operation_type, request_generation)`.
- Faixas com status `started`, `sent`, `succeeded` ou `uncertain` bloqueiam sobreposicao local; `failed` libera a faixa para nova decisao operacional.
- Timeout apos possivel envio remoto marca tentativa e faixa como `uncertain` e bloqueia reenvio automatico.
- A documentacao oficial consultada nao confirmou `url_notificacao` nem endpoint especifico de consulta para inutilizacao; portanto, a Fase 2.3.3 nao inventa webhook/reconciliacao remota para essa operacao.
- A validacao local impede conflito apenas com documentos/faixas conhecidos pelo Hunter; a UI exige confirmacao de que numeros usados fora do Hunter dependem da aceitacao remota/SEFAZ.

## Fase 2.5.0 - Idempotencia, Webhook e Seguranca para Credito/Debito

Credito/debito devem seguir o padrao das fases 2.2A, 2.2B.1, 2.2C e 2.3: a identidade de transmissao nasce de um documento local persistido, nao do payload fiscal.

Fluxo recomendado:

```text
criar FiscalDocument(document_type=nfe, purpose=credit|debit)
-> criar/bloquear FiscalEmissionAttempt(operation_type=nfe_credit_emission|nfe_debit_emission)
-> congelar payload sanitizado
-> executar uma unica chamada POST /1/nfe/emissao/
-> persistir resposta no FiscalDocument
-> webhook/reconciliacao atualizam somente esse FiscalDocument
```

Regras:

- `operation_type="nfe_credit_emission"` para `finalidade=5`.
- `operation_type="nfe_debit_emission"` para `finalidade=6`.
- `uncertain` bloqueia reenvio automatico e exige consulta/reconciliacao.
- Duas notas legitimas com payloads iguais devem poder coexistir quando forem intencoes/documentos locais distintos.
- Webhook resolve primeiro por UUID remoto. Fallback por tentativa/chave so pode ocorrer quando houver candidato unico da oficina, documento e finalidade esperada.
- Resposta de credito/debito nao pode atualizar NF-e normal, CC-e, devolucao, estorno, complementar, ajuste, NFC-e ou inutilizacao por engano.
- Payload/log nao devem persistir headers Webmania, segredos, certificado, CSC ou tokens.
- Como finalidade 5/6 e ligada a IBS/CBS pela documentacao Webmania, a emissao funcional deve permanecer bloqueada por feature flag e habilitacao administrativa ate subfase tributaria aprovada.

## Fase 2.4.0 - Bloqueio seguro IBS/CBS

Regra principal: enquanto IBS/CBS nao estiver configurado localmente de forma auditavel para o fluxo afetado, o Hunter deve bloquear transmissao em producao antes do gateway. Falhar cedo e melhor do que transmitir payload sabidamente incompleto ou incompatível com a regra oficial.

Politica recomendada:

- NF-e/NFC-e em producao com data de emissao >= `05/01/2026`: bloquear se qualquer produto/classe fiscal exigir IBS/CBS e nao houver `situacao_tributaria` e `classificacao_tributaria` minimas, alem dos grupos condicionais aplicaveis.
- Homologacao: permitir somente com configuracao IBS/CBS valida ou com modo controlado explicitamente habilitado por administracao fiscal; esse modo nao pode ser confundido com conformidade de producao.
- Credito/debito: manter bloqueado ate que `produtos[].impostos.ibs_cbs` seja suportado e os tributos antigos sejam removidos preventivamente dessas finalidades.
- Eventos IBS/CBS: manter bloqueados ate que a emissao base esteja conformada, para evitar historico de eventos sobre documentos com payload base incorreto.
- Complementar tributaria: manter bloqueada ate haver modelagem tributaria separada e validada.

Seguranca e auditoria:

- Nao calcular situacao/classificacao tributaria automaticamente sem fonte fiscal confiavel.
- Configuracao IBS/CBS deve exigir permissao fiscal administrativa e registrar usuario, oficina e timestamp.
- Payloads persistidos devem conter somente dados fiscais necessarios e sanitizados; nunca headers, tokens, CSC, certificado ou credenciais Webmania.
- Logs de bloqueio devem indicar documento/oficina/classe ausente sem imprimir payload completo sensivel.

Idempotencia:

- O bloqueio por configuracao ausente ocorre antes da criacao de tentativa remota.
- Quando a tentativa ja estiver `sent` ou `uncertain`, a falta posterior de configuracao nao autoriza reenvio automatico; reconciliacao continua consultando sem emitir.

Webhook/reconciliacao:

- A adequacao IBS/CBS nao muda a regra permanente: webhook e reconciliacao nunca emitem.
- Para documentos ja emitidos antes da conformidade, reconciliacao deve preservar o payload/resposta historicos e registrar lacuna apenas como pendencia operacional, sem tentar corrigir por nova emissao.

## Fase 2.4C.0 - Seguranca e idempotencia dos derivados com IBS/CBS

Regra principal: IBS/CBS em documentos derivados nao cria uma nova identidade de retry. A identidade continua sendo o documento derivado local ja validado nas fases anteriores.

Fluxo recomendado por derivado:

```text
validar original/snapshot IBS-CBS
-> validar permissoes e oficina
-> criar ou bloquear FiscalDocument derivado existente
-> criar/bloquear FiscalEmissionAttempt da operacao
-> congelar payload sanitizado com IBS/CBS efetivo
-> transmitir uma unica vez
-> webhook/reconciliacao atualizam somente o derivado
```

Regras:

- Falta de snapshot IBS/CBS bloqueia antes do gateway e antes de tentativa remota nova.
- Payload congelado nao pode ser reconstruido com classe fiscal atual apos timeout; `uncertain` preserva o snapshot/payload enviado.
- Webhook de devolucao, estorno, complementar ou ajuste deve resolver o `FiscalDocument` derivado por UUID/tentativa e nunca atualizar a NF-e original por chave.
- Reconciliacao continua consultando sem emitir. Ela pode preencher XML/DANFE/status do derivado, mas nao recalcular IBS/CBS nem substituir payload historico.
- Logs de bloqueio podem citar oficina, documento, sequencial fiscal e classe pendente, mas nao devem imprimir payload completo, credenciais, headers, CSC, certificado ou tokens.

Bloqueios seguros:

- NF-e externa minima sem XML/importacao validada nao pode gerar devolucao parcial nem complementar preco/quantidade com IBS/CBS.
- Classe fiscal atual divergente do snapshot original deve exigir confirmacao fiscal explicita ou bloquear.
- Ajuste nao deve receber `produtos[].impostos.ibs_cbs` por inferencia; se a operacao depender de Reforma Tributaria, bloquear ate contrato oficial aprovado.

Resultado 2.4C.3 para ajuste:

- `FiscalEmissionAttempt(operation_type=adjustment)` permanece a fonte de idempotencia.
- `uncertain` continua bloqueando reenvio automatico.
- Payload persistido e transmitido e revalidado contra campos fora do contrato antes do gateway.
- Campos de credito/debito, eventos IBS/CBS, produtos e IBS/CBS sao bloqueados antes de qualquer chamada remota.
- Webhook e reconciliacao continuam atualizando somente o `FiscalDocument(purpose=adjustment)` correspondente.

## Fase 2.4D.0 - Idempotencia e seguranca de Eventos IBS/CBS

Fluxo planejado:

```text
validar documento base NF-e/NFC-e elegivel
-> reservar event_sequence por documento e tipo de evento IBS/CBS
-> criar FiscalDocumentEvent(event_type=ibs_cbs)
-> criar/bloquear FiscalEmissionAttempt(operation_type=nfe_ibs_cbs_event)
-> congelar payload sanitizado
-> executar uma unica chamada POST /1/nfe/evento-ibs-cbs/
-> persistir resposta somente no evento
-> webhook/reconciliacao atualizam somente o evento
```

Chave idempotente:

```text
hash(workshop_id, fiscal_document_id, event_type, cod_evento, event_sequence, request_generation)
```

Regras:

- Retry da mesma intencao nao pode chamar a Webmania novamente.
- Concorrencia na mesma combinacao documento/codigo/sequencia deve resultar em uma unica chamada remota.
- `uncertain` preserva sequencia e payload, bloqueia reenvio automatico e exige reconciliacao/decisao administrativa.
- Payload nao pode ser reconstruido a partir de classe fiscal atual apos envio.
- Eventos com itens devem validar sequencial fiscal e oficina antes do gateway.
- Eventos de destinatario devem exigir habilitacao/permissao propria; nao usar fallback de NF-e emitente.

Webhook:

- `url_notificacao` e documentada para atualizacoes de status de evento; quando usada, o webhook deve resolver primeiro por UUID remoto do evento.
- Fallback por tentativa so pode atualizar candidato unico da mesma oficina, documento, `cod_evento` e sequencia.
- Associacao ambigua deve ficar pendente e nao atualizar evento/documento.
- Webhook de evento IBS/CBS nao altera status da NF-e/NFC-e base, devolucao, estorno, complementar ou ajuste.
- XML/log retornados devem ficar no `FiscalDocumentEvent`.

Cancelamento:

- Cancelamento de evento IBS/CBS usa endpoint proprio por UUID do evento autorizado e deve ser planejado em subfase separada.
- Nao cancelar documento fiscal base.
- Nao permitir cancelamento se evento original estiver `uncertain`, sem UUID remoto ou fora da oficina ativa.

Sanitizacao:

- Persistir payload fiscal, `cod_evento`, sequencia, `itens`, `dfe_referenciado` e valores IBS/CBS quando necessarios.
- Nunca persistir headers Webmania, consumer key/secret, access token, certificado, CSC ou tokens.

Resultado da Fase 2.4D.1:

- Evento `112110` usa `FiscalEmissionAttempt(operation_type="nfe_ibs_cbs_event")`.
- A chave idempotente inclui oficina, documento, tipo de evento, `cod_evento`, sequencia e geracao da requisicao.
- A sequencia `event_sequence` e congelada mesmo em `uncertain`; tentativa incerta bloqueia reenvio automatico.
- O webhook reconhece payloads de evento IBS/CBS por modelo ou `cod_evento`, resolve por UUID remoto do evento ou fallback por chave+sequencia, rejeita ambiguidade e atualiza somente `FiscalDocumentEvent`.
- Payload persistido e sanitizado remove token da URL de notificacao; headers e credenciais Webmania nao sao persistidos.

Resultado da Fase 2.4D.2:

- Cancelamento do evento `112110` usa `FiscalEmissionAttempt(operation_type="nfe_ibs_cbs_event_cancellation")`.
- A chave idempotente inclui oficina, evento original, evento de cancelamento e hash do payload sanitizado.
- O payload congelado contem somente `uuid`, `ambiente` e `url_notificacao` quando aplicavel; headers/credenciais nao sao persistidos.
- Timeout marca tentativa e evento de cancelamento como `uncertain`; o evento original permanece autorizado e novo cancelamento automatico fica bloqueado.
- Webhook de cancelamento resolve primeiro o evento de cancelamento por UUID remoto/tentativa, rejeita ambiguidade e atualiza somente `FiscalDocumentEvent(event_type="ibs_cbs_cancellation")` e o status do evento IBS/CBS original, nunca o documento base.

## Fase 2.4D.3.0 - Idempotencia dos demais Eventos IBS/CBS

Regra comum: eventos restantes devem reutilizar `FiscalEmissionAttempt(operation_type="nfe_ibs_cbs_event")`, com chave idempotente baseada em oficina, documento, `cod_evento`, `event_sequence` reservado e hash do payload sanitizado. `event_sequence` continua de 1 a 20 por documento e codigo, reservado transacionalmente.

Por grupo:

- Grupo A (`112150`): mesma infraestrutura de `112110`, mas o hash do payload deve incluir `data_previsao_entrega`. Timeout preserva sequencia e data enviada.
- Grupo B (`112120`, `112130`, `112140`): duplicidade deve considerar documento, codigo, sequencia e payload congelado de itens/valores/controle. O saldo/estoque operacional nao pode ser recalculado apos envio `sent` ou `uncertain`.

Implementacao 2.4D.5.1: para `112130`, o Hunter cria `FiscalDocumentEvent` e `FiscalEmissionAttempt(operation_type="nfe_ibs_cbs_event")` antes do POST remoto. A chave idempotente inclui oficina, documento, codigo do evento e sequencia reservada. O payload sanitizado fica congelado com `itens[]`; uma tentativa `uncertain` bloqueia reenvio automatico do mesmo payload. Webhook atualiza somente o evento resolvido por UUID remoto ou fallback seguro de chave + sequencia + `cod_evento`; ambiguidade nao altera nenhum registro.
- Grupo C (`211128`): idempotencia deve incluir documento relacionado a credito/debito e `indicador_aceitacao`; bloquear ate credito/debito funcional.
- Grupo D (`211110`, `211120`, `211124`, `211130`, `211140`, `211150`): idempotencia exige fonte externa auditavel do documento de aquisicao e itens; bloquear ate existir essa fonte.

Cancelamento: manter `FiscalEmissionAttempt(operation_type="nfe_ibs_cbs_event_cancellation")` apenas para `112110` validado. Generalizacao para `112150` ou outros codigos exige decisao explicita e testes proprios.

Resultado 2.4D.3: `112150` reutiliza a tentativa persistida `FiscalEmissionAttempt(operation_type="nfe_ibs_cbs_event")`, com idempotencia por oficina, documento, tipo, codigo, sequencia e geracao. A mesma data de previsao de entrega fica bloqueada enquanto houver evento `112150` ativo, aprovado ou incerto; datas diferentes podem gerar nova sequencia, respeitando o limite de 20 eventos por documento/tipo. Timeout marca evento e tentativa como `uncertain`, preserva a sequencia e bloqueia reenvio automatico da mesma data. Webhook segue a resolucao validada por UUID remoto/tentativa ou fallback chave+sequencia, rejeitando ambiguidade e atualizando somente `FiscalDocumentEvent`.

Resultado 2.4D.4: cancelamento do `112150` reutiliza `FiscalEmissionAttempt(operation_type="nfe_ibs_cbs_event_cancellation")`, com chave por oficina, evento original, evento de cancelamento e geracao. A presenca de cancelamento `started`, `sent`, aprovado/cancelado ou `uncertain` bloqueia nova tentativa. Timeout marca o cancelamento como `uncertain` e preserva o payload por UUID. Webhook de cancelamento resolve por UUID remoto/tentativa, rejeita ambiguidade, atualiza somente o evento de cancelamento e marca o evento original como cancelado apenas em retorno remoto positivo, sem alterar o `FiscalDocument` base.

## Fase 2.4D.5.0 - Idempotencia e bloqueios para 112120/112130/112140

Eventos `112120`, `112130` e `112140` devem reutilizar `FiscalDocumentEvent(event_type="ibs_cbs")` e `FiscalEmissionAttempt(operation_type="nfe_ibs_cbs_event")`, mas nao devem compartilhar um builder generico sem validadores por codigo.

Chave planejada:

```text
hash(workshop_id, fiscal_document_id, "ibs_cbs", cod_evento, event_sequence, request_generation)
```

Regras por codigo:

- `112120`: permitir somente quando houver NF-e de importacao local ou importada por XML, item fiscal confiavel e contexto ALC/ZFM confirmado. Bloquear documento externo minimo.
- `112130`: permitir somente quando houver snapshot fiscal do item e evento operacional de perecimento/perda/roubo/furto em transporte contratado pelo fornecedor, com valores de estorno IBS/CBS informados e confirmados.
- `112140`: permitir somente quando houver documento/pagamento antecipado modelado e itens de nota de debito com quantidade nao fornecida. Bloquear ate existir essa origem.

Estados `started`, `sent`, `processing`, `approved/succeeded` e `uncertain` devem bloquear repeticao do mesmo evento/codigo/sequencia. `uncertain` preserva itens, valores e `controle_estoque`, e nao pode ser recalculado por saldo/estoque posterior.

Webhook futuro deve resolver primeiro por UUID remoto do evento; fallback por tentativa ou chave+sequencia so pode atualizar um candidato unico da mesma oficina, documento, `cod_evento` e sequencia. Ambiguidade deve deixar o webhook pendente. O status da NF-e/NFC-e base nao deve ser alterado.

Resultado 2.4D.5.2: o cancelamento do `112130` reutiliza `FiscalEmissionAttempt(operation_type="nfe_ibs_cbs_event_cancellation")`, com chave idempotente por oficina, evento original, evento de cancelamento e geracao. O payload congelado contem somente `uuid`, `ambiente` e `url_notificacao` quando aplicavel. Tentativa `uncertain` bloqueia novo cancelamento automatico do mesmo evento. Webhook de cancelamento resolve por UUID remoto/tentativa, rejeita ambiguidade, atualiza somente o evento de cancelamento e marca o evento `112130` original como cancelado apenas em retorno remoto positivo, sem alterar o `FiscalDocument` base.

## Fase 2.4D.6.0 - Bloqueios seguros para 112120 e 112140

Decisao: manter `112120` e `112140` bloqueados ate haver fonte local confiavel. A idempotencia tecnica de `nfe_ibs_cbs_event` esta pronta, mas nao substitui validacao fiscal/operacional dos dados de origem.

Bloqueios obrigatorios para futura implementacao:

- `112120`: bloquear documento externo minimo, documento sem XML/importacao validada, ausencia de contexto ALC/ZFM, item sem sequencial fiscal, falta de snapshot IBS/CBS original e quantidade/unidade sem regra de isencao comprovada.
- `112140`: bloquear enquanto nao houver nota de debito/pagamento antecipado funcional, vinculo financeiro-item fiscal, snapshot IBS/CBS da nota de debito e quantidade/unidade nao fornecida auditavel.
- Ambos: bloquear reenvio se houver evento ativo, aprovado, `processing` ou `uncertain` com mesma intencao; preservar payload congelado; webhook deve resolver por UUID remoto ou fallback candidato unico da mesma oficina/documento/codigo/sequencia.

Cancelamento futuro: somente apos emissao correspondente validada, usando `FiscalEmissionAttempt(operation_type="nfe_ibs_cbs_event_cancellation")` por codigo. Nao generalizar cancelamento por endpoint sem testes por codigo.
## Fase 2.5.1.0 - Seguranca e idempotencia planejadas

- Operacoes futuras: `nfe_credit_emission` e `nfe_debit_emission`.
- Fluxo: criar documento local, validar tipo/fontes/referencias/IBS-CBS, criar e bloquear tentativa, congelar payload sanitizado, transmitir uma vez, persistir resposta e permitir somente consulta na reconciliacao `uncertain`.
- Chave: hash de oficina, documento local, operacao e geracao da requisicao; payload fiscal nao e identidade suficiente para distinguir duas intencoes legitimas.
- Bloquear: tipo sem fonte local; referencia obrigatoria ausente; documento externo sem XML/importacao validada; falta de snapshot IBS/CBS; qualquer tributo fora de `ibs_cbs`; ausencia de vinculo financeiro/item quando a hipotese exigir; uso de nota como substituto de evento ou vice-versa.
- Webhook deve resolver por UUID remoto e tentativa associada, restringir oficina/tipo/finalidade e jamais atualizar documento/evento IBS/CBS diferente.
- Feature flag global e habilitacao administrativa por oficina devem ser cumulativas; nenhuma permissao legada concede emissao.

### Protecoes implementadas na Fase 2.5.1P

- `transaction.atomic()` e lock no documento/base durante criacao/aprovacao.
- Snapshot vem somente de payload historico do documento/NfeItem e e sanitizado.
- Aprovacao bloqueia origem externa sem XML validado, snapshot incompleto, hipotese desconhecida, referencia obrigatoria ausente e cross-workshop.
- Nenhum `FiscalEmissionAttempt` ou webhook novo foi criado, pois nao existe operacao remota nesta fase.
- A flag por oficina nao adiciona `nfe_credit_emission` ou `nfe_debit_emission` aos choices existentes.

## Fase 2.5.2.0 - Bloqueio mantido

Mesmo uma `FiscalReferencedBasis` aprovada nao autoriza emissao enquanto nao houver valor fiscal tipado por item e snapshot comercial congelado. A futura idempotencia deve nascer apenas com o `FiscalDocument` de credito, usando tentativa `nfe_credit_emission`; nenhuma tentativa deve ser criada durante a preparacao 2.5.2P.
## Protecao da base monetaria 2.5.2P

A preparacao permanece fora do dominio de transmissao: nao cria `FiscalDocument` de credito/debito, `FiscalEmissionAttempt`, webhook ou reconciliacao. A feature flag controla apenas preparacao. Snapshots aprovados sao imutaveis; payload exposto usa sanitizacao fiscal e as consultas permanecem escopadas por oficina/permissao.
## Seguranca planejada - credito tipo 1

A futura intencao deve criar `FiscalDocument` e `FiscalEmissionAttempt` antes do gateway, congelar o payload e usar `uncertain` sem retry automatico. Base e item aprovados devem ser bloqueados para uso concorrente pela mesma intencao. Webhook resolve primeiro por UUID do credito e depois por tentativa nao ambigua; nunca atualiza a NF-e original ou evento IBS/CBS.

Bloqueios pre-gateway: base/item incompletos, valor `multa + juros <= 0`, chave/CFOP ausentes, qualquer tributo tradicional, `tipo_debito`, evento IBS/CBS, documento externo sem XML validado, oficina divergente, `credit_debit_basis_enabled` inativa, habilitacao administrativa de emissao ausente, permissao ausente e tentativa `uncertain`.
## Seguranca implementada na 2.5.3P

Nao existe idempotencia remota porque nao existe operacao remota. A transacao bloqueia base e item, gera revisao unica e congela payload aprovado. A flag `credit_debit_basis_enabled` controla somente preparacao. Payload e IBS/CBS exigem permissao propria e passam por sanitizacao antes da resposta JSON.

## Seguranca Fase 2.5.4

A autorizacao explicita desta fase amplia `credit_debit_basis_enabled` para habilitar tambem o credito tipo 1. A preview e bloqueada por `select_for_update(of=("self",))`; documento, link e `FiscalEmissionAttempt(operation_type="nfe_credit_emission")` sao persistidos antes do HTTP. Timeout/resposta nao interpretavel gera `uncertain`, que bloqueia nova intencao. Webhook resolve somente documentos `purpose=credit`/tipo `1`, rejeita ambiguidade e nao altera origem, base ou preview. Reconciliacao usa apenas consulta remota.

## Seguranca Fase 2.5.5

O documento e bloqueado transacionalmente; evento e tentativa sao persistidos antes do `PUT`. A chave idempotente inclui oficina, documento, operacao, evento e geracao. Cancelamento ativo ou `uncertain` impede nova tentativa; timeout preserva o evento incerto sem mudar o documento. Webhook resolve primeiro o evento de cancelamento por UUID/chave/tentativa, rejeita ambiguidade e somente entao marca o credito cancelado. Reconciliacao usa `GET /1/nfe/consulta/` e nunca reenvia o cancelamento.

## Seguranca planejada - debito tipo 4

### Seguranca implementada na Fase 2.5.7

A preview e bloqueada transacionalmente, o documento/link/tentativa sao persistidos antes do POST e a unicidade da preview impede segunda intencao. Timeout marca documento e tentativa como `uncertain`; retry nao reenvia. O webhook rejeita UUID/chave ambiguos em qualquer oficina ou proposito fiscal, e a reconciliacao executa apenas `GET /1/nfe/consulta/`.

## Seguranca implementada - Fase 2.5.8

O documento e bloqueado com `select_for_update`; cancelamento ativo ou `uncertain` impede nova transmissao. Timeout marca evento e tentativa como incertos. Resposta intermediaria nao cancela o documento e permanece bloqueada para consulta. A resolucao do webhook considera todos os cancelamentos NF-e para rejeitar colisao entre credito/debito e oficinas. Reconciliacao nunca executa `PUT`.
A Fase 2.5.6.0 nao abre gateway remoto. A fase preparatoria recomendada deve:

- impedir que uma preview de credito seja promovida ou convertida em debito;
- exigir base/item aprovados, mesma oficina, feature flag e permissoes proprias;
- congelar payload de produto e `dfe_referenciado` depois da aprovacao;
- bloquear tributos tradicionais e qualquer fallback para cadastro fiscal atual;
- registrar validacoes sem criar `FiscalDocument` ou `FiscalEmissionAttempt`.

Somente uma fase funcional posterior podera usar `FiscalEmissionAttempt(operation_type="nfe_debit_emission")`. Essa emissao devera manter uma chamada por intencao, `uncertain` bloqueante, webhook por UUID e reconciliacao sem reenvio. Cancelamento devera ser subfase separada pelo fluxo padrao NF-e.

Resultado 2.5.6P: nenhuma operacao remota, idempotencia de emissao, webhook ou reconciliacao foi criada. A seguranca desta fase e local: transacao, lock da base, revisao unica, snapshots aprovados, imutabilidade, sanitizacao, permissao e tenancy.

## Seguranca planejada - Fase posterior a 2.5.7.0

Idempotencia: `hash(workshop_id, debit_document_id, "nfe_debit_emission", request_generation)`. Criar documento e tentativa dentro da mesma transacao antes do POST. A preview aprovada so pode possuir um documento. `sent`/`succeeded`/`uncertain` bloqueiam reenvio; timeout ou resposta indeterminada deixam documento e tentativa `uncertain`.

Webhook resolve primeiro por UUID do documento de debito, depois por tentativa inequivoca; ambiguidade nao atualiza nada. Reconciliacao usa somente consulta NF-e e nunca reenvia. NF-e original, base, item e preview permanecem imutaveis.

## Seguranca planejada apos a Fase 2.6.0

A Fase 3.0 deve auditar o fluxo NFS-e existente antes de ampliar operacoes. O plano deve preservar idempotencia persistida antes do POST, estado `uncertain` bloqueante, webhook duplicado/fora de ordem e reconciliacao exclusivamente consultiva.

Substituicao e manifestacao precisam de chaves idempotentes e resolucao de tenancy proprias. Capacidades municipais devem bloquear operacoes nao suportadas antes do gateway. Nenhum fallback por permissao NF-e/NFC-e deve conceder operacoes NFS-e, e nenhuma reconciliacao pode emitir, substituir, manifestar ou cancelar documento.

### Operation types e estados planejados

- `nfse_emission`: preservar uma chamada por `NfseRequest`/documento e migrar o operation type generico sem duplicar tentativas existentes.
- `nfse_query`: trilha opcional de consulta, sem semantica de emissao e sem bloquear consulta operacional.
- `nfse_cancellation`, `nfse_substitution`, `nfse_manifestation`: tentativa persistida antes do HTTP, payload congelado e `uncertain` sem retry automatico.

Estados de documento: `draft`, `processing`, `authorized`, `rejected`, `cancelled`, `substituted`, `uncertain`, `failed`; estados de tentativa permanecem `started`, `sent`, `succeeded`, `failed`, `uncertain`. `scheduled` e `contingency` sao estados remotos preservados, nao sinonimos de sucesso.

Webhook: fingerprint continua obrigatorio, mas cada item/lote deve persistir o ultimo `atualizado_em`. UUID e oficina devem resultar em candidato unico; fallback por tentativa so e aceito quando inequivoco. Payload antigo deve ser marcado processado sem regredir estado. Payload ambiguo permanece pendente.

Reconciliacao: GET por UUID para item/lote e operacoes incertas quando o contrato permitir. Nunca chamar emissao, cancelamento, substituicao ou manifestacao. Cancelamento atual e prioridade alta da 3.3 porque nao possui essa protecao.

### Garantias validadas na Fase 3.1

- payload e fingerprint do webhook sao calculados sobre estrutura sanitizada;
- `atualizado_em` remoto prevalece quando presente, com fallback seguro para o rank legado quando ausente;
- timestamp anterior ou rank regressivo nao altera item, lote ou request;
- ambiguidade continua impedindo associacao automatica;
- reconciliacao NFS-e executa somente consulta por UUID e preserva erro/estado sem operacao mutavel.

## Garantias da Fase 3.2

- consulta valida UUID e `modelo` antes de qualquer escrita;
- UUID duplicado entre oficinas ou registros bloqueia atualizacao automatica;
- lote e itens sao aplicados na mesma transacao, com rollback integral em ambiguidade;
- webhook e query reutilizam `apply_nfse_*_payload`, rank e `atualizado_em`;
- GET nao cria `FiscalEmissionAttempt`: retry manual e seguro, enquanto horario/origem/payload/erro formam a trilha local;
- timeout de consulta registra erro, mas nao transforma o status fiscal em `uncertain` sem evidencia remota;
- comando de reconciliacao nao executa POST, PUT, cancelamento, substituicao ou manifestacao.
## Fase 3.3 - cancelamento NFS-e

Fluxo: bloquear item e validar oficina/capacidade/status -> criar `NfseCancellation` -> criar tentativa `nfse_cancellation` -> congelar `{uuid, motivo}` -> executar um unico PUT. Timeout ou resposta inconclusiva marca ambos como `uncertain` e impede reenvio. Webhook pode confirmar pelo UUID unico; `atualizado_em` e rank impedem reabertura por retorno antigo. A reconciliacao de `uncertain` executa somente GET de consulta e nunca repete o cancelamento.

## Fase 3.4.0 - seguranca planejada da substituicao

Fluxo futuro: validar preview/base/original/capability/flag -> criar `NfseSubstitution` -> reservar tentativa `nfse_substitution` -> congelar payload -> executar um POST -> atualizar somente original e substituta confirmadas. Timeout gera `uncertain`; nunca repetir POST automaticamente. Enquanto o UUID substituto for desconhecido, consultar a original e registrar pendencia administrativa, sem presumir que ela foi substituida. Quando o retorno/webhook trouxer `nfse_substituida`, validar o UUID original antes de aplicar.

Webhook: resolver primeiro UUID da substituta; fallback por tentativa e `nfse_substituida.uuid`; rejeitar multiplas correspondencias; usar `atualizado_em`; preservar XML original e armazenar XML substituto separadamente. Reconciliacao consulta UUID conhecido e jamais substitui novamente.

Na Fase 3.4P nao existe idempotencia remota, webhook ou reconciliacao. A transacao bloqueia o `NfseItem` original durante a criacao, sanitiza e congela o pre-payload; a aprovacao bloqueia a preview e impede mutacao ou reversao direta do estado aprovado. Tenancy, feature flag, capability e permissoes sao verificadas antes da preparacao/aprovacao.

Na Fase 3.4.1, `FiscalEmissionAttempt(operation_type="nfse_substitution")` nasce antes do POST e usa chave por oficina/preview/substituicao. Retry e concorrencia encontram a intencao existente; timeout marca operacao/tentativa `uncertain` e nunca repete POST. Webhook resolve primeiro UUID substituto e, quando necessario, usa `nfse_substituida.uuid` contra uma unica intencao sent/uncertain. Ambiguidade bloqueia. Reconciliacao executa somente GET por UUID substituto; timeout sem UUID permanece pendencia administrativa.

## Fase 3.6.0 - seguranca planejada da manifestacao NFS-e

Operacao futura: `FiscalEmissionAttempt(operation_type="nfse_manifestation")`.

Chave idempotente planejada: oficina, NFS-e local, papel do manifestador, tipo/codigo da manifestacao e geracao da intencao. O payload deve ser congelado antes do `POST /2/nfse/manifestar`; retry nao reenvia; concorrencia deve resultar em uma unica chamada remota. Timeout ou resposta sem confirmacao suficiente marca manifestacao e tentativa como `uncertain` e bloqueia reenvio automatico.

Webhook planejado: resolver por UUID remoto da manifestacao, se existir; fallback por tentativa somente quando houver uma unica tentativa `sent`/`uncertain` compativel no mesmo escopo. Webhook sem identificador suficiente deve ficar pendente, nao inferir sucesso. A atualizacao deve afetar somente `NfseManifestation`, nunca cancelar, substituir ou reabrir a `NfseItem` original.

Reconciliacao planejada: somente consulta segura por GET quando houver identificador remoto suficiente. Nenhum comando de reconciliacao pode repetir `POST /2/nfse/manifestar`. Ambiguidade entre oficinas, NFS-e original/substituta ou manifestacoes do mesmo papel/tipo deve bloquear aplicacao automatica.

### Resultado 3.6.1

`NfseManifestation` e `FiscalEmissionAttempt(operation_type="nfse_manifestation")` sao persistidos antes do POST. O payload contem somente `ambiente`, `uuid`, `manifestador`, `evento` e campos condicionais de rejeicao. Timeout marca manifestacao e tentativa como `uncertain` e bloqueia nova tentativa da mesma intencao. Webhook `modelo=manifestacao_nfse` resolve somente por UUID remoto unico da manifestacao; payload sem identificador suficiente fica pendente. Reconciliacao usa apenas consulta por UUID remoto da manifestacao e nunca repete POST.

## Seguranca recomendada pela Fase 3.7.0

A proxima fase recomendada e preparatoria, portanto nao deve criar idempotencia remota, webhook ou reconciliacao. A seguranca deve ser local:

- transacao e lock ao criar/aprovar preview;
- payload planejado sanitizado e hash persistido;
- imutabilidade apos aprovacao;
- capability municipal, feature flag, permissao e oficina ativa antes de preparar/aprovar;
- nenhum `FiscalEmissionAttempt`, `NfseItem` remoto, POST, webhook ou download fiscal.

A fase funcional posterior de emissao manual nova devera criar tentativa antes de `POST /2/nfse/emissao`, com chave por oficina, preview aprovada e geracao da intencao. Timeout ou resposta inconclusiva deve marcar tentativa/documento como `uncertain` e bloquear retry automatico. Webhook NFS-e deve resolver por UUID unico do item emitido ou tentativa inequivoca; reconciliacao deve usar somente GET.

## Fase 3.7.1 - emissao manual NFS-e

A emissao manual cria `NfseManualEmission` e `FiscalEmissionAttempt(operation_type="nfse_manual_emission")` antes do HTTP. A chave de idempotencia inclui oficina, preview, operacao, intencao e geracao fixa; retries da mesma preview nao reenviam e estados `sent`, `succeeded` ou `uncertain` bloqueiam nova transmissao.

Timeout marca tentativa e emissao como `uncertain`. Reconciliacao usa somente `GET /2/nfse/consulta/{uuid}` quando ha UUID remoto seguro; se a intencao incerta nao possui UUID, nenhum POST e repetido. Webhook `modelo=nfse` resolve primeiro substituicao, depois emissao manual por `remote_uuid` unico, e so entao cai no fluxo generico de `NfseItem`. Webhook ambiguo fica pendente.
## Fase 3.8.0 - seguranca, idempotencia e webhooks da NFS-e manual

A Fase 3.7.1 validada no checkpoint `2cb35206` ja garante emissao manual por preview aprovada, tentativa `nfse_manual_emission`, `NfseItem` somente apos confirmacao valida e reconciliacao sem repetir `POST /2/nfse/emissao`.

Para o ciclo seguinte, o menor risco e cancelar a NFS-e manual usando a mesma trilha de cancelamento NFS-e ja validada:

- idempotencia por `FiscalEmissionAttempt(operation_type="nfse_cancellation")`;
- payload congelado `{uuid, motivo}`;
- timeout em `uncertain` bloqueando reenvio automatico;
- webhook por UUID atualizando somente o cancelamento/NFS-e correspondente;
- reconciliacao exclusivamente consultiva por `GET /2/nfse/consulta/{identifier}`;
- XML de cancelamento separado do XML original;
- preview e emissao manual imutaveis.

Risco principal: resolver por UUID um `NfseItem` manual que tambem possa ser visto por fluxos legados. A fase funcional deve exigir unicidade local, oficina ativa, permissao `cancel_nfse` e bloqueio de ambiguidade. Permissao de emitir NFS-e manual, aprovar preview, substituir ou manifestar nao autoriza cancelamento.

Resultado da Fase 3.8.1:

- `FiscalEmissionAttempt(operation_type="nfse_cancellation")` foi reutilizado.
- O payload do cancelamento manual fica congelado como `{uuid, motivo}`.
- Timeout permanece `uncertain` e bloqueia retry automatico.
- Webhook `modelo=nfse/status=cancelado` confirma o cancelamento manual quando ha intencao de cancelamento segura; caso contrario nao reinterpreta como nova emissao.
- Reconciliacao usa somente `GET /2/nfse/consulta/{identifier}` e nao repete `PUT`.
- XML original da NFS-e manual e preservado; XML de cancelamento fica em `NfseCancellation.xml_url`.

## Fase 3.9.0 - seguranca recomendada apos ciclo minimo manual

A Fase 3.8.1 foi validada no checkpoint `29f3f3a9`. O proximo bloco recomendado e substituicao da NFS-e manual por extensao segura do fluxo atual.

Garantias a preservar:

- `NfseManualEmissionPreview`, `NfseManualEmission.request_payload` e XML original da NFS-e manual permanecem imutaveis.
- A tentativa deve continuar sendo criada antes do `POST /2/nfse/substituir`, com `FiscalEmissionAttempt(operation_type="nfse_substitution")`.
- A chave idempotente deve ser por oficina, preview/substituicao e geracao da intencao; retry de preview aprovada nao reenvia se ja houver `sent`, `succeeded` ou `uncertain`.
- Webhook deve resolver primeiro a substituta por UUID; fallback por `nfse_substituida` so e aceitavel quando a original manual e a intencao forem inequivocas.
- Reconciliacao continua somente GET e nunca repete `POST /2/nfse/substituir`.
- Ambiguidade entre original manual, original legada, substituta ou outra oficina deve deixar o evento pendente.

Risco principal: adaptar elegibilidade sem abrir substituicao para NFS-e manual incompleta. Bloqueios obrigatorios: sem UUID, sem `codigo_verificacao`, status nao autorizado, cancelada, substituida, incerta, cancelamento ativo/incerto, substituicao ativa/incerta, capability/flag desligada, permissao ausente ou cross-workshop.

## Fase 3.9.1 - seguranca implementada na substituicao manual

A Fase 3.9.1 reutiliza `FiscalEmissionAttempt(operation_type="nfse_substitution")` e a chave idempotente existente por oficina, preview/substituicao e geracao da intencao. A chamada remota e unica por preview aprovada; estados `sent`, `succeeded` e `uncertain` bloqueiam reenvio automatico.

Bloqueios implementados para a original manual:

- sem `NfseManualEmission` vinculada quando nao ha `NfseRequest`;
- status diferente de autorizada;
- status cancelada, substituida ou `uncertain`;
- ausencia de UUID, codigo de verificacao ou XML original;
- emissao manual `uncertain`;
- cancelamento ativo/autorizado/incerto;
- substituicao ativa/autorizada/incerta;
- capability de substituicao desligada;
- feature flag de preview desligada;
- cross-workshop.

Webhook e reconciliacao permanecem os do fluxo de substituicao: resolver por UUID da substituta ou por `nfse_substituida` deterministico, pendenciar ambiguidade e usar somente GET na reconciliacao. Nenhum caminho repete `POST /2/nfse/substituir`.

## Fase 3.10.0 - seguranca da manifestacao manual reavaliada

`NfseManifestation`, `FiscalEmissionAttempt(operation_type="nfse_manifestation")`, webhook e reconciliacao consultiva ja existem para manifestacao NFS-e Padrao Nacional. A seguranca tecnica de idempotencia e retry e reaproveitavel; o bloqueio remanescente e fiscal: nao ha papel de manifestador seguro para NFS-e manual emitida pela propria oficina.

Bloqueios que permanecem obrigatorios para qualquer fase futura:

- `national_standard_enabled=False`;
- `manifestation_enabled=False`;
- usuario sem `issue_nfse_manifestation`;
- NFS-e manual cancelada, substituida ou `uncertain`;
- NFS-e manual sem UUID seguro;
- NFS-e manual substituta sem confirmacao remota valida;
- NFS-e recebida/importada sem dominio de importacao e tenancy;
- NFS-e municipal legada;
- ausencia de papel fiscal da oficina como tomadora ou intermediaria.

Webhook/reconciliacao: nenhum webhook deve inferir sucesso de manifestacao manual por UUID da NFS-e original. A confirmacao deve depender do UUID remoto da manifestacao ou identificador equivalente seguro. Reconciliacao segue exclusivamente consultiva e nunca repete `POST /2/nfse/manifestar`.

## Fase 3.11.0 - seguranca planejada para NFS-e recebida/importada

O registro de NFS-e recebida deve ser local e validativo. Nenhuma importacao pode emitir, cancelar, substituir ou manifestar documento. O XML validado e o hash devem ser a primeira fronteira de confianca; consulta Webmania e webhook servem como enriquecimento/reconciliacao, nunca como prova unica inicial de papel fiscal.

Bloqueios planejados:

- XML ausente quando a origem exigir XML;
- XML invalido ou nao parseavel;
- hash duplicado;
- UUID duplicado;
- chave/identificador duplicado;
- CNPJ da oficina ausente no XML;
- CNPJ da oficina com papel desconhecido;
- CNPJ divergente entre XML, empresa Webmania e oficina ativa;
- municipio incompatível;
- ambiente incompatível;
- documento cancelado, substituido ou `uncertain`;
- documento de outra oficina;
- documento emitido pelo proprio Hunter importado como recebido;
- tentativa de manifestar antes de `validation_status=validated`.

Webhook recebido sem documento local deve ficar pendente. Reconciliacao futura de documento recebido deve ser somente GET/consulta e nao deve repetir `POST /2/nfse/manifestar`.

## Fase 3.11.1 - seguranca implementada para importacao recebida

`NfseReceivedDocument` foi implementado como fronteira local de confianca. A importacao exige flag `nfse_received_import_enabled`, XML parseavel, bloqueio de DTD/entidade, hash SHA-256 do XML normalizado, unicidade por oficina para hash/UUID/identificador, papel fiscal seguro e colisao negativa contra NFS-e emitida localmente.

O fluxo nao possui gateway remoto: nenhuma chamada Webmania, nenhum webhook, nenhuma reconciliacao e nenhum `FiscalEmissionAttempt`. Payload/XML sao protegidos por permissoes especificas de recebidas.

## Fase 3.12.0 - seguranca planejada para manifestacao recebida

A futura manifestacao de NFS-e recebida deve reutilizar a seguranca de `NfseManifestation`: tentativa persistida antes do POST, payload congelado, idempotencia por intencao, timeout `uncertain`, webhook por UUID remoto unico da manifestacao e reconciliacao somente GET.

Chave idempotente planejada: oficina, tipo de origem (`received_document`), id do `NfseReceivedDocument`, evento, manifestador, operation type `nfse_manifestation`, id da intencao e geracao fixa. A chave nao deve usar somente UUID da NFS-e recebida, porque o mesmo documento pode ter eventos/manifestadores distintos.

Bloqueios obrigatorios antes de criar a intencao:

- `validation_status` diferente de `validated`;
- role diferente de `taker` ou `intermediary`;
- role `provider`, `unknown` ou `multiple`;
- XML ausente/invalido ou hash ausente;
- UUID/identificador remoto inseguro;
- `remote_status` cancelado/substituido/anulado ou estado local `uncertain`;
- documento duplicado ou cross-workshop;
- `national_standard_enabled=False`;
- `manifestation_enabled=False`;
- usuario sem `issue_nfse_manifestation`;
- tentativa ativa/concluida/incerta para o mesmo documento, evento e manifestador.

Webhook `modelo=manifestacao_nfse` deve continuar resolvendo por UUID remoto unico da manifestacao. Se houver colisao entre manifestacao local e recebida, o evento fica pendente; nao deve cair para UUID da NFS-e original. Reconciliacao de manifestacao recebida deve exigir UUID remoto da manifestacao e nunca repetir `POST /2/nfse/manifestar`.

## Fase 3.13.1 - seguranca da consulta auxiliar de recebida

A consulta auxiliar e GET-only e nao usa `FiscalEmissionAttempt`, porque timeout/falha de leitura nao prova alteracao fiscal remota nem deve reservar intencao.

Bloqueios antes da consulta:

- documento nao pertence a oficina ativa;
- origem diferente de XML;
- `validation_status` diferente de `validated`;
- `xml_snapshot` ausente;
- `xml_hash` ausente;
- UUID e identificador seguro ausentes;
- flag `nfse_received_consultation_enabled=False`;
- usuario sem `consult_nfse_received`.

Garantias apos a consulta:

- resposta remota e sanitizada;
- divergencias sao registradas em `NfseReceivedDocumentConsultation.divergences`;
- XML, hash, CNPJs, municipio, ambiente, valor, role fiscal e payload parseado nao sao sobrescritos;
- retorno cancelado/substituido/anulado e consultivo, nao cria cancelamento/substituicao local;
- consulta nao cria `NfseManifestation`, nao chama `POST /2/nfse/manifestar`, nao cria `NfseItem`, nao cria `FiscalDocument(nfse)` e nao cria documento recebido sem XML.

Webhook sem documento recebido previamente validado continua pendente/fora do escopo desta fase.

## Fase 3.14.0 - seguranca recomendada para lote XML de recebidas

Status: em planejamento documental em 2026-06-29. A Fase 3.13.1 foi validada no checkpoint `01f0924d`.

Regras de seguranca para a proxima fase recomendada:

- A importacao em lote deve aceitar somente XMLs; nao deve criar documento recebido por consulta Webmania, digitacao de UUID ou webhook sem documento previo.
- Cada arquivo deve ser validado isoladamente contra oficina/empresa, hash, UUID, identificador, papel fiscal, XML malformado e status extraido.
- Duplicidades por hash, UUID e identificador devem ser bloqueadas sem sobrescrever o documento existente.
- Falha de um arquivo nao deve apagar documentos validos ja importados no mesmo lote; o comportamento esperado e importacao parcial com relatorio auditavel.
- XML e payloads derivados devem manter as mesmas protecoes de permissao/download do upload unitario.
- Nao ha webhook nem reconciliacao automatica no lote; consulta Webmania permanece acao consultiva separada.
- Nenhum lote deve criar manifestacao automatica, `NfseItem`, `FiscalDocument(nfse)` ou `FiscalEmissionAttempt`.

Riscos principais: lote grande consumindo memoria, arquivo de outra oficina, duplicidade parcial, relatorio incompleto e expectativa de rollback total. A mitigacao documental recomendada e limite de tamanho/quantidade, validacao por arquivo, resultado persistido ou exibido por arquivo e bloqueios cross-workshop determinísticos.

## Fase 3.14.1 - seguranca implementada para lote XML

O lote implementado e XML-only, local e sem gateway remoto. Cada arquivo e validado isoladamente por extensao, tamanho, conteudo XML, parser existente, papel fiscal, duplicidade e colisao com documentos emitidos localmente.

Duplicidades sao bloqueadas dentro do lote e contra a base existente por hash, UUID e identificador. O comportamento e importacao parcial: arquivos validos sao persistidos e arquivos invalidos geram itens de erro no relatorio.

Nao ha consulta Webmania automatica, webhook, manifestacao automatica, `NfseItem`, `FiscalDocument(nfse)` ou `FiscalEmissionAttempt` no fluxo de lote.

## Fase 3.15.0 - seguranca recomendada para integracao e-mail/ERP

Status: validada documentalmente em 2026-06-29 no checkpoint `4815728b`. A Fase 3.14.1 foi validada no checkpoint `b53e862b`.

Riscos a tratar antes de qualquer implementacao:

- autenticacao e armazenamento de credenciais externas;
- anexos adulterados ou com conteudo nao XML;
- e-mails/ERP com documentos de outra oficina;
- reprocessamento de anexos duplicados;
- processamento silencioso sem revisao;
- exposicao de dados fiscais sensiveis;
- necessidade de fila/job e observabilidade.

Regras recomendadas: e-mail/ERP deve apenas fornecer XMLs para um pipeline controlado que reutilize o lote local. Nao pode consultar Webmania automaticamente, manifestar automaticamente, criar documento sem XML, criar `NfseItem`, criar `FiscalDocument(nfse)` ou criar `FiscalEmissionAttempt`.

## Fase 3.15.1 - seguranca planejada para caixa externa de XML

Status: em planejamento documental em 2026-06-29. A Fase 3.15.0 foi validada documentalmente no checkpoint `4815728b`.

Controles obrigatorios planejados:

- validar extensao, MIME declarado e conteudo XML antes de aceitar item candidato;
- bloquear ZIP inseguro, arquivo executavel, path traversal, arquivo vazio e arquivo acima do limite;
- calcular `xml_hash` canonico e bloquear duplicidade por hash, UUID, identificador, origem externa e mensagem/anexo quando aplicavel;
- validar CNPJ, papel fiscal e oficina/empresa antes de enviar item para lote;
- manter cross-workshop bloqueado em todas as telas, jobs e downloads;
- exigir revisao humana antes de transformar item pendente em lote fiscal;
- auditar fonte, data/hora, usuario ou job, remetente/sistema externo, hash, descarte, erro e reprocessamento;
- proteger payload/XML por permissao propria e evitar exposicao de XML fiscal em logs;
- manter itens rejeitados e descartados com retencao definida, sem apagar historico.

Autenticacao planejada: OAuth para Gmail/Microsoft quando aplicavel, credenciais por oficina ou empresa, conta dedicada, escopos minimos, revogacao, rotacao, auditoria de acesso e segregacao por oficina. Nenhuma autenticacao externa sera implementada nesta fase documental.

Idempotencia planejada: hash XML, identificador fiscal, identificador externo da fonte, id da mensagem de e-mail quando houver, fingerprint de anexo e `source_identifier`. Reprocessamento deve ser seguro, nao duplicar documento, nao sobrescrever XML validado e nao apagar historico.

Nao ha webhook fiscal nesta fase. Um eventual webhook externo operacional, se existir em fase futura, deve apenas criar item candidato autenticado na caixa de entrada e nunca chamar Webmania, manifestar ou criar documento recebido diretamente.

## Fase 3.15.2 - seguranca implementada na inbox externa

Status: em implementacao controlada em 2026-06-30. A Fase 3.15.1 foi validada documentalmente no checkpoint `5882cd4e`.

Controles implementados: flag propria por empresa/oficina, upload manual apenas, nome seguro por arquivo, limite de quantidade/tamanho herdado do lote XML, rejeicao de arquivo vazio, extensao nao XML, conteudo sem aparencia XML, XML malformado, DTD/entidade externa, XML duplicado no envio, XML duplicado contra inbox ativa, XML duplicado contra `NfseReceivedDocument`, papel fiscal inseguro e CNPJ/oficina divergente quando parseavel.

Processamento: somente item aprovado por usuario e ainda nao vinculado a lote e enviado ao `NfseReceivedImportBatch`. Item descartado, invalido, duplicado ou ja processado nao e processado. Reprocessamento de item ja processado e bloqueado por ausencia de itens aprovados sem lote.

Nao ha webhook externo real, job agendado, consulta Webmania automatica, manifestacao automatica ou exposicao de path local.

## Fase 3.16.0 - seguranca apos inbox externa local

Status: em planejamento documental em 2026-06-30. A Fase 3.15.2 foi validada no checkpoint `517d25b8`.

Conectores reais de e-mail, ERP, pasta monitorada e webhook externo continuam com risco alto por credenciais, spoofing/origem falsa, segregacao por oficina, anexos adulterados, idempotencia por mensagem e observabilidade. A inbox local reduziu o risco de origem operacional, mas nao resolveu autenticacao externa.

Recomendacao de seguranca: priorizar melhorias locais e auditaveis da inbox antes de conectores reais. Qualquer conector futuro deve criar apenas item de inbox pendente, com revisao humana obrigatoria, sem consulta Webmania automatica e sem manifestacao automatica.

## Fase 3.16.1 - seguranca operacional da inbox XML

Status: em implementacao tecnica em 2026-06-30. A Fase 3.16.0 foi validada documentalmente no checkpoint `267fc601`.

Controles implementados: filtros e busca sempre partem de `workshop` ativo; exportacao CSV exige `export_nfse_external_xml_inbox` e nao inclui XML bruto, credenciais ou path local; acoes em massa exigem `bulk_manage_nfse_external_xml_inbox`; descarte em massa exige motivo; processamento em massa aceita somente itens aprovados, sem vinculo previo e com XML/hash.

Auditoria permanece persistida nos campos existentes de usuario/data de aprovacao, descarte e processamento, no motivo de descarte e nos vinculos com lote/documento. Falhas em item individual nao derrubam a acao inteira.

Nao foram implementados conector real, webhook externo, job agendado, consulta Webmania automatica, manifestacao automatica, reprocessamento de erro ou limpeza fisica de XML fiscal.
