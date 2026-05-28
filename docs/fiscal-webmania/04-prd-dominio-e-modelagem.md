# PRD dominio e modelagem fiscal

## Modelo conceitual recomendado

Entidades propostas:

- `FiscalDocument`: documento fiscal unificado.
- `FiscalDocumentEvent`: eventos de webhook, eventos fiscais e transicoes locais.
- `FiscalEmissionAttempt`: tentativa persistida de emissao.
- `FiscalDocumentLink`: vinculos entre documento fiscal, origem e documentos derivados. Nao foi criado na Fase 2.1; fica reservado para a Fase 2.2.
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
- `FiscalDocumentLink`: vinculos entre documento original, documento derivado e origem operacional, somente a partir da Fase 2.2.

Decisao aplicada na Fase 2.1: criar apenas `FiscalDocument`, `FiscalDocumentEvent` e extensoes minimas de `FiscalEmissionAttempt`. `FiscalDocument` e uma projecao sob demanda de `NfeItem` quando CC-e e solicitada; `FiscalDocumentLink` nao existe nessa fase.

Essa abordagem evita tratar eventos como notas comuns e permite que documentos derivados tenham vinculo auditavel com a nota original.

### Representacao por operacao

| Operacao | Representacao local | Vinculo obrigatorio |
| -------- | ------------------- | ------------------- |
| CC-e | `FiscalDocumentEvent(kind="cce")` | `FiscalDocument` original NF-e aprovada ou espelho de `NfeItem`. |
| Manifestacao | `FiscalDocumentEvent(kind="recipient_manifestation")` | Documento/chave manifestada; pode existir sem nota emitida pelo Hunter, mas sempre com oficina. |
| IBS/CBS | `FiscalDocumentEvent(kind="ibs_cbs")` | NF-e/NFC-e original. |
| Cancelamento IBS/CBS | `FiscalDocumentEvent(kind="ibs_cbs_cancel")` | Evento IBS/CBS original e documento original. |
| Devolucao/estorno | `FiscalDocument(kind="nfe", purpose="return")` | Documento original por `FiscalDocumentLink(role="returns")`. |
| Complementar | `FiscalDocument(kind="nfe", purpose="complementary")` | Documento original por `FiscalDocumentLink(role="complements")`. |
| Ajuste | `FiscalDocument(kind="nfe", purpose="adjustment")` | Documento original por `FiscalDocumentLink(role="adjusts")`. |
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
- Na Fase 2.1, a relacao de espelho e o `OneToOne`/referencia segura com `NfeItem`; `FiscalDocumentLink` sera usado somente quando existirem documentos derivados reais na Fase 2.2.
- Operacoes derivadas devem usar a chave/UUID do documento original e chave idempotente propria por operacao.
- Documento derivado nao substitui documento original; ele aponta para ele.

### Arquivos previstos para Fase 2.1

- Models/migrations: `apps/finance/models/finance.py`, nova migration para `FiscalDocument`, `FiscalDocumentEvent` e extensoes minimas de `FiscalEmissionAttempt`; sem `FiscalDocumentLink`.
- Services/gateways: `apps/finance/services/nfe_events.py`, extensao de `apps/finance/services/fiscal_attempts.py`.
- Views: `apps/finance/views/nfe.py`.
- Forms: formulario minimo integrado ao fluxo de detalhe NF-e ou arquivo dedicado futuro, sem criar central fiscal.
- URLs: `apps/finance/urls.py`.
- Templates: modal/form de CC-e em `apps/finance/templates/finance/`.
- Testes: `apps/finance/tests.py` ou pacote futuro de testes finance para CC-e, idempotencia, permissao, tenancy e webhook.
- Docs: atualizar `docs/fiscal-webmania/*` e log.
