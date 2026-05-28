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
