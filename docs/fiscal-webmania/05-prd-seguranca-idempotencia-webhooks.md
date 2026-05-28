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
- `operation`: `cce`, `return`, `reversal`, `complementary`, `complementary_tax`, `adjustment`, `credit_note`, `debit_note`, `nfce_emission`, `manifestation`, `ibs_cbs_event`, `ibs_cbs_cancel`, `nfce_replacement_cancel`.
- `subject_identifier`: UUID/chave/documento original/evento original quando existir; para ajuste sem original, usar identificador deterministico da intencao manual, nunca texto livre mutavel isolado da UI.
- `operation_fingerprint`: hash canonico dos campos fiscais essenciais, sanitizado e estavel.

| Operacao | Chave de idempotencia | Estado `uncertain` | Bloqueio de reenvio |
| -------- | --------------------- | ------------------ | ------------------- |
| CC-e | `nfe:cce:{workshop}:{original_uuid_or_key}:{hash_correcao}` | Timeout apos envio ou resposta sem identificador/evento | Bloquear mesma correcao para mesma nota ate reconciliar. |
| Devolucao | `hash(workshop_id, derived_document_id, operation_type, request_generation)` | Timeout/resposta incompleta apos envio | Bloquear documento derivado e saldo reservado ate consulta/reconciliacao; nao reenviar automaticamente. |
| Estorno via devolucao | `hash(workshop_id, derived_document_id, operation_type, request_generation)` | Timeout/resposta incompleta | Bloquear estorno derivado ate consulta/reconciliacao. |
| Complementar | `nfe:complementary:{workshop}:{original_identifier}:{hash_tipo_itens_valores_impostos}` | Timeout/resposta incompleta | Bloquear complemento identico; permitir complemento distinto somente apos status claro. |
| Ajuste | `nfe:adjustment:{workshop}:{operacao}:{codigo_cfop}:{valor_icms}:{hash_cliente_payload}` | Timeout/resposta incompleta | Bloquear ajuste identico; nao exigir documento original. |
| Nota Fiscal de Credito | `nfe:credit_note:{workshop}:{tipo_credito}:{hash_payload}` | Timeout/resposta incompleta | Bloquear nota de credito identica ate consulta. |
| Nota Fiscal de Debito | `nfe:debit_note:{workshop}:{tipo_debito}:{hash_payload}` | Timeout/resposta incompleta | Bloquear nota de debito identica ate consulta. |
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
- Eventos devem ter tentativa propria e registro em `FiscalDocumentEvent`.
- Documentos derivados devem ter tentativa propria e registro em `FiscalDocument`.
- Webhook/reconciliacao devem atualizar a tentativa/evento/documento correspondente e nunca chamar endpoint de emissao/evento.
- Payloads persistidos devem remover headers, tokens, certificados, secrets e dados sensiveis nao essenciais.

## Fase 2.0 - Webhooks e reconciliacao NF-e/NFC-e

- Webhook deve resolver por `uuid` primeiro e por `chave` somente quando nao houver ambiguidade dentro da oficina.
- Evento CC-e deve ser associado ao documento original e nao criar uma nota comum.
- Webhook de documento derivado deve atualizar o `FiscalDocument` derivado e manter link com o original.
- Evento IBS/CBS fora de ordem nao pode regredir estado de evento ja autorizado/cancelado.
- Reconciliacao Fase 2 deve consultar status por `GET /1/nfe/consulta/` e downloads por URLs retornadas, sem reenviar operacao.
