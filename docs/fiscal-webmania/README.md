# Fiscal Webmania - PRDs vivos

## INSTRUÇÕES PARA QUALQUER AGENTE OU SESSÃO FUTURA

1. Leia este indice antes de modificar o fiscal.
2. Leia `00-regras-de-execucao.md`.
3. Leia o PRD da fase atualmente marcada como ativa.
4. Leia `09-decisoes-arquiteturais.md`.
5. Leia `10-log-de-implementacao.md`.
6. Verifique `git status` e alteracoes existentes.
7. Nunca presuma que uma fase foi implementada apenas porque ela foi planejada.
8. Atualize o status e o log ao concluir qualquer mudanca.
9. Nao implemente uma fase posterior enquanto criterios da anterior nao estiverem atendidos.
10. Em caso de conflito entre plano e codigo atual, registre a divergencia e solicite decisao antes de alterar comportamento fiscal critico.

Regra permanente: antes de implementar qualquer fase, leia este arquivo e os PRDs associados.

## Objetivo

Transformar a camada fiscal do Hunter V2 em um modulo completo, seguro e extensivel sobre a Webmania, preservando os fluxos atuais de NF-e e NFS-e enquanto o dominio evolui para NF-e, NFC-e, NFS-e, CT-e, CT-e OS, MDF-e, NFCom e DC-e.

## Status atual

Fase atual: Fase 2.2A - Devolucao e estorno NF-e implementada para revisao.

Status geral: Fase 0 e Fase 0.1 aprovadas; Fase 1 validada tecnicamente em 2026-05-28 com aceite explicito das dividas preexistentes comprovadas no baseline anterior. A Fase 2.0 foi aprovada documentalmente, a Fase 2.1 foi validada somente para CC-e, a Fase 2.2.0 revisou documentalmente derivados NF-e, e a Fase 2.2A foi implementada para devolucao/estorno sem iniciar complementar, ajuste, NFC-e ou eventos avancados.

A Fase 1 alterou somente os fluxos existentes de NF-e/NFS-e para estabilizacao, seguranca, idempotencia persistida, webhook, reconciliacao e permissoes conforme escopo aprovado. A revisao comprovou cobertura fiscal critica, incluindo teste transacional concorrente real. As falhas globais remanescentes em DRE, workshops, workorder, ruff/mypy e migrations nao fiscais foram aceitas como dividas preexistentes registradas em `11-backlog-e-pendencias.md`.

A Fase 2.1 criou apenas `FiscalDocument`, `FiscalDocumentEvent` e extensoes minimas de `FiscalEmissionAttempt` para CC-e. A validacao cobriu webhook por UUID e por chave+sequencia, ambiguidade, sequencia/idempotencia, permissao, tenancy, downloads e sanitizacao. `FiscalDocumentLink`, documentos derivados, NFC-e, manifestacao e IBS/CBS permanecem fora de escopo e dependem de nova aprovacao.

## Documentos

1. `00-regras-de-execucao.md`
2. `01-auditoria-as-is.md`
3. `02-prd-produto-e-escopo.md`
4. `03-prd-matriz-api-webmania.md`
5. `04-prd-dominio-e-modelagem.md`
6. `05-prd-seguranca-idempotencia-webhooks.md`
7. `06-prd-ux-permissoes-e-workflows.md`
8. `07-plano-de-fases-e-criterios-de-aceite.md`
9. `08-plano-de-testes-e-operacao.md`
10. `09-decisoes-arquiteturais.md`
11. `10-log-de-implementacao.md`
12. `11-backlog-e-pendencias.md`
13. `api/webmania_fiscal_openapi_validated.json`

## Sequencia obrigatoria de leitura

1. `README.md`
2. `00-regras-de-execucao.md`
3. `01-auditoria-as-is.md`
4. `03-prd-matriz-api-webmania.md`
5. `04-prd-dominio-e-modelagem.md`
6. `05-prd-seguranca-idempotencia-webhooks.md`
7. PRD da fase ativa em `07-plano-de-fases-e-criterios-de-aceite.md`
8. `09-decisoes-arquiteturais.md`
9. `10-log-de-implementacao.md`

## Tabela de fases

| Fase                         | Status               | Documento guia                                                        | Implementada em | Validada em | Pendencias               |
| ---------------------------- | -------------------- | --------------------------------------------------------------------- | --------------- | ----------- | ------------------------ |
| 0 - Auditoria e PRDs         | validada             | `01-auditoria-as-is.md`, `07-plano-de-fases-e-criterios-de-aceite.md` | N/A             | 2026-05-28  | Manter docs atualizados  |
| 0.1 - OpenAPI validado       | validada             | `03-prd-matriz-api-webmania.md`, `api/webmania_fiscal_openapi_validated.json` | N/A       | 2026-05-28  | Revalidar antes de novas familias |
| 1 - Estabilizacao NF-e/NFS-e | validada com dividas preexistentes registradas | `05-prd-seguranca-idempotencia-webhooks.md`                           | 2026-05-28      | 2026-05-28  | Falhas globais preexistentes aceitas e documentadas |
| 2.0 - Planejamento NF-e/NFC-e | aprovada documentalmente | `02-prd-produto-e-escopo.md`, `04-prd-dominio-e-modelagem.md`, `07-plano-de-fases-e-criterios-de-aceite.md` | N/A | 2026-05-28 | Manter decisao 2.1 sem `FiscalDocumentLink` |
| 2.1 - CC-e                   | validada             | `07-plano-de-fases-e-criterios-de-aceite.md`                         | 2026-05-28      | 2026-05-28  | Nao iniciar 2.2 sem aprovacao |
| 2.2.0 - Revisao derivados NF-e | documentada | `04-prd-dominio-e-modelagem.md`, `07-plano-de-fases-e-criterios-de-aceite.md` | N/A | 2026-05-28 | Nenhum codigo autorizado |
| 2.2A - Devolucao/estorno      | implementada para revisao | `07-plano-de-fases-e-criterios-de-aceite.md`                         | 2026-05-28      | N/A         | Aguardar validacao; 2.2B nao iniciada |
| 2.2B - Complementar           | nao iniciada | `07-plano-de-fases-e-criterios-de-aceite.md`                         | N/A             | N/A         | Requer autorizacao explicita |
| 2.2C - Ajuste                 | nao iniciada | `07-plano-de-fases-e-criterios-de-aceite.md`                         | N/A             | N/A         | Link ao original opcional |
| 2.3 - NFC-e                  | nao iniciada         | `07-plano-de-fases-e-criterios-de-aceite.md`                         | N/A             | N/A         | Requer decisao de configuracao NFC-e |
| 2.4 - Manifestacao e IBS/CBS | nao iniciada         | `07-plano-de-fases-e-criterios-de-aceite.md`                         | N/A             | N/A         | Revalidar Reforma Tributaria |
| 2.5 - Credito/debito NF-e     | nao iniciada         | `07-plano-de-fases-e-criterios-de-aceite.md`                         | N/A             | N/A         | Revalidar finalidades 5/6 |
| 3 - Completar NFS-e          | nao iniciada         | `03-prd-matriz-api-webmania.md`                                       | N/A             | N/A         | Fase 1 validada          |
| 4 - CT-e e CT-e OS           | nao iniciada         | `03-prd-matriz-api-webmania.md`                                       | N/A             | N/A         | Fases prioritarias       |
| 5 - MDF-e                    | nao iniciada         | `03-prd-matriz-api-webmania.md`                                       | N/A             | N/A         | CT-e/MDF-e modelados     |
| 6 - NFCom                    | nao iniciada         | `03-prd-matriz-api-webmania.md`                                       | N/A             | N/A         | Confirmar relevancia     |
| 7 - DC-e beta                | nao iniciada         | `03-prd-matriz-api-webmania.md`                                       | N/A             | N/A         | Feature flag obrigatoria |
| 8 - Consolidacao e legado    | nao iniciada         | `04-prd-dominio-e-modelagem.md`                                       | N/A             | N/A         | Backfill aprovado        |

## Checklist de retomada

- Rodar `git status --short`.
- Confirmar se ha alteracoes nao relacionadas.
- Ler `01-auditoria-as-is.md` e validar se o codigo ainda corresponde.
- Ler `10-log-de-implementacao.md` para saber o que foi feito.
- Confirmar fase aprovada pelo usuario antes de editar codigo.
- Reconsultar documentacao oficial Webmania se endpoint, autenticacao ou payload tiver risco de mudanca.
