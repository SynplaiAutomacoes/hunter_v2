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

Fase atual: Fase 2.3.3 - Inutilizacao de numeracao NFC-e validada.

Status geral: Fase 0 e Fase 0.1 aprovadas; Fase 1 validada tecnicamente em 2026-05-28 com aceite explicito das dividas preexistentes comprovadas no baseline anterior. A Fase 2.0 foi aprovada documentalmente, a Fase 2.1 foi validada somente para CC-e, a Fase 2.2.0 revisou documentalmente derivados NF-e, a Fase 2.2A foi validada para devolucao/estorno, a Fase 2.2B.0 planejou Nota Fiscal Complementar, a Fase 2.2B.1 foi validada somente para complementar de preco/quantidade de NF-e original local no checkpoint `5faacd9c05960c153eaf69d239bf885da9985df7`, e a Fase 2.2C foi validada no checkpoint `1910a0678754d3c6b44f2bdd22c65492a8e8b803` somente para Nota Fiscal de Ajuste. A Fase 2.3.0 foi aprovada documentalmente e a Fase 2.3.1 foi implementada no checkpoint `8d5832fdf8cd0e4f3ad18d4a92123c7596e6391b`, corrigida e validada no checkpoint `0f5c4abd0c62af6835465674b5b1004f2e4eeab9` para emissao manual simples de NFC-e. A Fase 2.3.2 foi validada somente para cancelamento padrao de NFC-e no checkpoint `a4ae87f7e3f4748369d0d68a90d30e21a0a3d71b`. A Fase 2.3.3 esta autorizada e em implementacao somente para inutilizacao de numeracao NFC-e.

A Fase 1 alterou somente os fluxos existentes de NF-e/NFS-e para estabilizacao, seguranca, idempotencia persistida, webhook, reconciliacao e permissoes conforme escopo aprovado. A revisao comprovou cobertura fiscal critica, incluindo teste transacional concorrente real. As falhas globais remanescentes em DRE, workshops, workorder, ruff/mypy e migrations nao fiscais foram aceitas como dividas preexistentes registradas em `11-backlog-e-pendencias.md`.

A Fase 2.1 criou `FiscalDocument`, `FiscalDocumentEvent` e extensoes minimas de `FiscalEmissionAttempt` para CC-e. A Fase 2.2A introduziu e validou `FiscalDocumentLink` e documentos derivados para devolucao/estorno. A Fase 2.2B.1 adicionou complementar local de preco/quantidade com `FiscalDocument(purpose="complementary", complementary_type="price_quantity")`, link `complements`, tentativa idempotente e UI minima no detalhe da NF-e. A Fase 2.2C adicionou ajuste com `FiscalDocument(purpose="adjustment", origin="manual")`, link `adjusts` opcional, tentativa `adjustment`, validacao de regime tributario por `WebmaniaCompany.regime_tributario` e UI minima no detalhe da NF-e. A Fase 2.3.1 adicionou NFC-e manual simples direto em `FiscalDocument(document_type="nfce", purpose="normal", origin="manual")`, sem `NfceRequest`, com configuracao por oficina em `WebmaniaCompany`, protecao de CSC, tentativa `nfce_emission`, webhook/reconciliacao, downloads e UI minima. A Fase 2.3.2 adicionou cancelamento padrao de NFC-e como `FiscalDocumentEvent(event_type="cancellation")`, tentativa `nfce_cancellation`, `PUT /1/nfe/cancelar/` sem `nfce_referenciada`, webhook/reconciliacao sem reenvio e XML de cancelamento protegido. Permanecem fora de escopo ate nova autorizacao: complementar tributaria, complementar de adicao/importacao, contingencia/offline NFC-e, cancelamento por substituicao, inutilizacao NFC-e, PDV/TEF/SAT/MFE, manifestacao, IBS/CBS, credito/debito e demais familias fiscais.

Depois da Fase 2.3.2, permanecem fora de escopo funcional: contingencia/offline, cancelamento por substituicao, PDV completo, TEF/SAT/MFE, complementar tributaria, IBS/CBS, adicao/importacao, manifestacao, credito/debito e demais familias fiscais. Durante a Fase 2.3.3, a unica expansao autorizada e inutilizacao de numeracao NFC-e; ela nao e cancelamento, nao se vincula a uma NFC-e emitida e nao implementa inutilizacao funcional de NF-e. A implementacao usa `FiscalNumberInutilization` e `FiscalEmissionAttempt(operation_type="nfce_inutilization")`.

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
| 2.2A - Devolucao/estorno      | validada | `07-plano-de-fases-e-criterios-de-aceite.md`                         | 2026-05-28      | 2026-05-28  | 2.2B nao iniciada |
| 2.2B - Complementar           | 2.2B.1 validada | `07-plano-de-fases-e-criterios-de-aceite.md`                         | 2026-05-28      | 2026-05-28  | 2.2B.2 tributaria e 2.2B.3 importacao nao iniciadas |
| 2.2C - Ajuste                 | validada | `07-plano-de-fases-e-criterios-de-aceite.md`                         | 2026-05-28      | 2026-05-28  | Complementar tributaria, NFC-e, manifestacao, IBS/CBS e credito/debito nao iniciados |
| 2.3.0 - Planejamento NFC-e   | aprovada documentalmente | `07-plano-de-fases-e-criterios-de-aceite.md`                         | N/A             | 2026-05-29  | Manter exclusoes da fase |
| 2.3.1 - NFC-e manual simples | validada             | `07-plano-de-fases-e-criterios-de-aceite.md`                         | 2026-05-29      | 2026-05-29  | Sem contingencia/offline, cancelamento por substituicao ou PDV |
| 2.3.2 - Cancelamento NFC-e   | validada             | `07-plano-de-fases-e-criterios-de-aceite.md`                         | 2026-05-29      | 2026-05-29  | Somente cancelamento padrao; sem substituicao, contingencia ou inutilizacao |
| 2.3.3 - Inutilizacao NFC-e   | validada              | `07-plano-de-fases-e-criterios-de-aceite.md`                         | 2026-05-29      | 2026-05-29  | Somente `modelo=2`; sem NF-e, substituicao ou contingencia/offline |
| 2.3 - NFC-e                  | parcialmente validada | `07-plano-de-fases-e-criterios-de-aceite.md`                         | 2026-05-29      | 2026-05-29  | 2.3.1, 2.3.2 e 2.3.3 validadas; substituicao e contingencia/offline nao iniciadas |
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
