# PRD dominio e modelagem fiscal

## Modelo conceitual recomendado

Entidades propostas:

- `FiscalDocument`: documento fiscal unificado.
- `FiscalDocumentEvent`: eventos de webhook, eventos fiscais e transicoes locais.
- `FiscalEmissionAttempt`: tentativa persistida de emissao.
- `FiscalDocumentLink`: vinculos entre documento fiscal, origem e documentos derivados.
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
FiscalDocument N:N origem via FiscalDocumentLink
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

- `FiscalDocument`, `FiscalDocumentEvent`, `FiscalDocumentLink`.
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
