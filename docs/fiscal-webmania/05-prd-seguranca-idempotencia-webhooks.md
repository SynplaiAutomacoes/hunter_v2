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
