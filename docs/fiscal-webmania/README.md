# Fiscal Webmania - PRDs vivos

## Atualizacao Fase 4.1.2 - Finalizacao operacional da NF-e de devolucao

- O fluxo produtivo existente foi preservado: NF-e original projetada em `FiscalDocument`, documento derivado separado, `FiscalDocumentLink`, tentativa fiscal, `POST /1/nfe/devolucao/`, webhook, consulta, historico e downloads.
- A selecao parcial passa a bloquear item repetido, item ausente no snapshot e quantidade superior ao saldo; snapshots duplicados entre request/response/legado nao multiplicam a quantidade original.
- Devolucao total e estorno continuam sem selecao parcial no payload de homologacao, mas agora reservam internamente todo o saldo e nao podem coexistir com devolucao parcial ativa/concluida.
- Timeout e resposta sem UUID/chave conclusivos permanecem `uncertain` e nao geram novo POST. Webhook e reconciliacao GET-only passam a sincronizar tambem a tentativa existente.
- Nenhum model, migration, endpoint remoto, payload Webmania, OpenAPI, NF-e normal, CC-e ou outro dominio fiscal foi alterado.

## Atualizacao Fase 4.1.1 - Finalizacao da Carta de Correcao NF-e

- O fluxo produtivo existente de CC-e permanece como fonte da verdade: UI no detalhe da NF-e, `FiscalDocumentEvent`, `FiscalEmissionAttempt`, Webmania, webhook, historico, payload protegido e downloads XML/DACCE.
- A finalizacao adiciona reconciliacao segura por `GET /1/nfe/consulta/` somente quando o UUID remoto da propria CC-e e conhecido; modelo, UUID, sequencia e chave retornados sao conferidos antes de atualizar o evento.
- Timeout continua em `uncertain` e nunca dispara novo `POST`. Sem UUID remoto seguro, a operacao aguarda webhook e a consulta e bloqueada.
- Webhook confirmado passa a sincronizar tambem a tentativa idempotente associada, sem alterar a NF-e nem seu XML original.
- Nenhum model, migration, payload Webmania, contrato remoto, OpenAPI, fluxo de emissao/cancelamento/inutilizacao NF-e ou dominio fiscal adicional foi alterado.

## Atualizacao Fase 4.0.5

- A Fase 4.0.4 foi validada e encerrada no checkpoint `9486f8ca`.
- A Fase 4.0.5 e exclusivamente documental/operacional e transforma o plano de migracao em roteiro de homologacao das permissoes dedicadas NF-e.
- Decisao: Opcao B, homologar grupos e preparar fase futura de remocao do fallback somente com evidencias reais e aceite operacional.
- O fallback legado permanece ativo; nao ha alteracao de codigo, migration, model, service, view, template, teste, OpenAPI, endpoint remoto, payload fiscal ou regra fiscal.
- CT-e, MDF-e, NFCom, DC-e, IBS/CBS pendente, credito/debito pendente e complementar tributaria continuam nao iniciados.

## Atualizacao Fase 4.0.4

- A Fase 4.0.3 foi validada e encerrada no checkpoint `9f888ced`.
- A Fase 4.0.4 e exclusivamente documental e planeja a migracao operacional das permissoes dedicadas da NF-e normal para grupos reais.
- Decisao: Opcao B, planejar remocao futura do fallback em fase propria somente apos mapeamento, atribuicao e homologacao operacional dos grupos.
- O fallback legado permanece ativo agora; nao ha alteracao de codigo, migration, model, service, view, template, teste, OpenAPI, endpoint remoto, payload fiscal ou regra fiscal.
- CT-e, MDF-e, NFCom, DC-e, IBS/CBS pendente, credito/debito pendente e complementar tributaria continuam nao iniciados.

## Atualizacao Fase 4.0.3

- A Fase 4.0.2 foi validada e encerrada no checkpoint `43a597e0dbce3ece5cfcb05d7eae278f2522e8f6`.
- A branch `feat/notas-fiscais` ja integrou `origin/main`; validacao pos-merge concluida no HEAD `0caf7ca5`.
- A Fase 4.0.3 implementa a Opcao A: permissoes dedicadas para NF-e normal com fallback legado temporario.
- Escopo: cancelamento, inutilizacao e downloads XML/DANFE existentes; permissoes de payload/resposta remota ficam criadas para uso futuro sem view nova.
- Nao ha endpoint remoto novo, payload fiscal novo, regra fiscal nova, modernizacao de cancelamento/inutilizacao, CT-e, MDF-e, NFCom, DC-e, IBS/CBS pendente, credito/debito pendente ou complementar tributaria.

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

Fase atual: Fase 4.2.0 - Finalizacao Prioritaria da Carta de Correcao NF-e, em implementacao em 2026-07-02. A Fase 4.1.0 foi validada e encerrada no checkpoint `af76387f`, endurecendo devolucao/estorno NF-e sem reabrir outros dominios. A Fase 4.0.2 de permissoes dedicadas genericas da NF-e normal permanece pausada por mudanca de prioridade e nao deve ser continuada nesta execucao.

Marco consolidado: NF-e/NFC-e existentes preservadas, NFS-e legada preservada, NFS-e manual com preview, emissao, cancelamento e substituicao, manifestacao NFS-e Padrao Nacional, NFS-e recebida por XML unitario, consulta/reconciliacao GET-only, manifestacao de recebida, lote XML, inbox externa local/manual/assistida, ampliacao operacional da inbox, auditoria tecnica/fiscal geral e saneamento tecnico pos-auditoria. Permanecem confirmadas as ausencias de conectores reais de e-mail/ERP, consulta Webmania automatica, manifestacao automatica, criacao direta de `NfseReceivedDocument` pela inbox, criacao de documento recebido sem XML, `NfseItem`, `FiscalDocument(nfse)`, `FiscalEmissionAttempt`, CT-e, MDF-e, NFCom, DC-e, eventos IBS/CBS pendentes, creditos/debitos pendentes e complementar tributaria.

Status geral: Fase 0 e Fase 0.1 aprovadas; Fase 1 validada tecnicamente em 2026-05-28 com aceite explicito das dividas preexistentes comprovadas no baseline anterior. A Fase 2.0 foi aprovada documentalmente, a Fase 2.1 foi validada somente para CC-e, a Fase 2.2.0 revisou documentalmente derivados NF-e, a Fase 2.2A foi validada para devolucao/estorno, a Fase 2.2B.0 planejou Nota Fiscal Complementar, a Fase 2.2B.1 foi validada somente para complementar de preco/quantidade de NF-e original local no checkpoint `5faacd9c05960c153eaf69d239bf885da9985df7`, e a Fase 2.2C foi validada no checkpoint `1910a0678754d3c6b44f2bdd22c65492a8e8b803` somente para Nota Fiscal de Ajuste. A Fase 2.3.0 foi aprovada documentalmente e a Fase 2.3.1 foi implementada no checkpoint `8d5832fdf8cd0e4f3ad18d4a92123c7596e6391b`, corrigida e validada no checkpoint `0f5c4abd0c62af6835465674b5b1004f2e4eeab9` para emissao manual simples de NFC-e. A Fase 2.3.2 foi validada somente para cancelamento padrao de NFC-e no checkpoint `a4ae87f7e3f4748369d0d68a90d30e21a0a3d71b`. A Fase 2.3.3 foi validada no checkpoint `08b9bf2e` para inutilizacao de numeracao NFC-e. A Fase 2.5.0 foi aprovada documentalmente para nao implementar credito/debito antes de IBS/CBS. A Fase 2.4.0 foi aprovada documentalmente e a Fase 2.4A+B foi validada no checkpoint `9eb217f2b5de2f834eb137305de1216d47e4b36e`, deixando NF-e normal e NFC-e manual simples adequadas ou bloqueadas com seguranca. A Fase 2.4C.0 foi aprovada documentalmente. A Fase 2.4C.1 foi validada no checkpoint `c28c58afb73245d188b9ca22fe3f688e12e07f11`. A Fase 2.4C.2 foi validada no checkpoint `11a9ba78c429936cedc7d10a5d45c6a683781be3`. A Fase 2.4C.3 foi validada no checkpoint `dd740d1fccbf692b95720a0b0de36fee1f294827`, mantendo ajuste sem IBS/CBS em `/1/nfe/ajuste/`. A Fase 2.4D.0 foi aprovada documentalmente; a Fase 2.4D.1 foi validada no checkpoint `52014780a89627e7183e4a7c2eb968a8d2d9e513` somente para `cod_evento=112110`. A Fase 2.4D.2 foi validada no checkpoint `dab3d559238954878259c1ad57cd503424f93d47` somente para cancelamento do evento `112110`. A Fase 2.4D.3 foi validada no checkpoint `b0f2e093` somente para `cod_evento=112150`. A Fase 2.4D.4 foi validada somente para cancelamento do evento `112150`.

A Fase 1 alterou somente os fluxos existentes de NF-e/NFS-e para estabilizacao, seguranca, idempotencia persistida, webhook, reconciliacao e permissoes conforme escopo aprovado. A revisao comprovou cobertura fiscal critica, incluindo teste transacional concorrente real. As falhas globais remanescentes em DRE, workshops, workorder, ruff/mypy e migrations nao fiscais foram aceitas como dividas preexistentes registradas em `11-backlog-e-pendencias.md`.

A Fase 2.1 criou `FiscalDocument`, `FiscalDocumentEvent` e extensoes minimas de `FiscalEmissionAttempt` para CC-e. A Fase 2.2A introduziu e validou `FiscalDocumentLink` e documentos derivados para devolucao/estorno. A Fase 2.2B.1 adicionou complementar local de preco/quantidade com `FiscalDocument(purpose="complementary", complementary_type="price_quantity")`, link `complements`, tentativa idempotente e UI minima no detalhe da NF-e. A Fase 2.2C adicionou ajuste com `FiscalDocument(purpose="adjustment", origin="manual")`, link `adjusts` opcional, tentativa `adjustment`, validacao de regime tributario por `WebmaniaCompany.regime_tributario` e UI minima no detalhe da NF-e. A Fase 2.3.1 adicionou NFC-e manual simples direto em `FiscalDocument(document_type="nfce", purpose="normal", origin="manual")`, sem `NfceRequest`, com configuracao por oficina em `WebmaniaCompany`, protecao de CSC, tentativa `nfce_emission`, webhook/reconciliacao, downloads e UI minima. A Fase 2.3.2 adicionou cancelamento padrao de NFC-e como `FiscalDocumentEvent(event_type="cancellation")`, tentativa `nfce_cancellation`, `PUT /1/nfe/cancelar/` sem `nfce_referenciada`, webhook/reconciliacao sem reenvio e XML de cancelamento protegido. A Fase 2.3.3 adicionou `FiscalNumberInutilization` para faixas NFC-e inutilizadas, tentativa `nfce_inutilization`, `modelo=2`, sem webhook/reconciliacao remota especifica e com `uncertain` reservando a faixa. A Fase 2.4A+B adicionou configuracao IBS/CBS em `TaxClassNfe`, sincronizacao de `ibs_cbs` em classes fiscais Webmania e bloqueio seguro das emissoes normais NF-e/NFC-e quando a classe fiscal nao estiver pronta. A Fase 2.4D ja validou eventos IBS/CBS `112110`, `112150`, `112130` e cancelamentos pontuais de `112110`, `112150` e `112130`. Permanecem fora de escopo ate nova autorizacao: `112120`, `112140`, eventos `211xxx`, credito/debito, complementar tributaria, complementar de adicao/importacao, contingencia/offline NFC-e, cancelamento por substituicao, inutilizacao funcional de NF-e, PDV/TEF/SAT/MFE, manifestacao, NFS-e, CT-e e demais familias fiscais.

Depois da Fase 2.4A+B, permanecem fora de escopo funcional: IBS/CBS em devolucao/estorno, complementar e ajuste; eventos IBS/CBS; contingencia/offline; cancelamento por substituicao; PDV completo; TEF/SAT/MFE; complementar tributaria; adicao/importacao; manifestacao; credito/debito funcional; NFS-e; CT-e; e demais familias fiscais.

Descoberta critica da Fase 2.4.0: a Webmania documenta IBS/CBS dentro de `produtos[].impostos.ibs_cbs` para NF-e/NFC-e e cronograma de obrigatoriedade em producao para NF-e/NFC-e com data de emissao maior ou igual a `05/01/2026`. Credito/debito (`finalidade=5/6`) devem enviar somente IBS/CBS nos itens. Antes de credito/debito, eventos IBS/CBS ou complementar tributaria, a prioridade passa a ser conformar os fluxos NF-e/NFC-e ja implementados.

Fase 2.4.0 aprovada documentalmente. A Fase 2.4A+B foi validada para combinar configuracao/modelagem IBS/CBS em classes fiscais NF-e/NFC-e com adequacao dos fluxos normais ja emissores: NF-e normal legada e NFC-e manual simples. A combinacao foi obrigatoria porque apenas criar campos locais sem bloquear/emissoes normais deixaria o produto exposto a rejeicao fiscal em producao. A Fase 2.4C.0 foi aprovada documentalmente. A Fase 2.4C.1 implementou somente devolucao e estorno por `/1/nfe/devolucao/`, usando snapshot fiscal da NF-e original local como fonte preferencial. A Fase 2.4C.2 foi validada para aplicar a mesma decisao de snapshot a Nota Complementar de preco/quantidade: `TaxClassNfe` atual nao e fallback automatico; o bloco `produtos[].impostos.ibs_cbs` vem do snapshot original e exige `base_calculo` conforme contrato oficial da complementar. A Fase 2.4C.3 mantem ajuste sem IBS/CBS por ausencia de contrato seguro em `/1/nfe/ajuste/`, bloqueia uso como credito/debito ou evento IBS/CBS e preserva estorno no fluxo de devolucao. A Fase 2.4D cobre parcialmente eventos IBS/CBS: `112110`, cancelamento do `112110`, `112150`, cancelamento do `112150`, `112130` e cancelamento do `112130`. Complementar tributaria, eventos `112120/112140`, eventos `211xxx`, credito/debito, NFS-e, CT-e e demais documentos permanecem fora do escopo funcional.

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

## Fase 4.2.0 - Carta de Correcao NF-e

- Escopo: finalizar a CC-e ja criada na Fase 2.1, mantendo endpoint `POST /1/nfe/cartacorrecao/`, modelagem `FiscalDocumentEvent(event_type="cce")`, tentativa `FiscalEmissionAttempt(operation_type="cce")`, webhook/reconciliacao sem novo POST e downloads XML/DACCE protegidos.
- Auditoria do checkout: service `apps/finance/services/nfe_events.py`, views/URLs/templates em `apps/finance/views/nfe.py`, `apps/finance/urls.py` e `apps/finance/templates/finance/nfe_request_detail.html`, webhook em `apps/finance/services/webmania_webhooks.py` e testes `FiscalPhaseTwoCorrection*` ja cobrem o nucleo de CC-e.
- Lacunas de fechamento: validar texto conservadoramente contra termos fiscais proibidos, ocultar acao quando houver CC-e ativa/incerta, adicionar permissao/rota de payload protegida e registrar testes/documentacao de homologacao.
- Fora de escopo: Fase 4.0.2, devolucao/estorno, NFS-e, CT-e, MDF-e, NFCom, DC-e, creditos/debitos, complementar tributaria, IBS/CBS pendentes e conectores externos.

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
| 2.3 - NFC-e                  | validada no ciclo simples | `07-plano-de-fases-e-criterios-de-aceite.md`                      | 2026-05-29      | 2026-05-29  | Emissao manual, cancelamento padrao e inutilizacao concluidas; substituicao e contingencia/offline nao iniciadas |
| 2.4.0 - Auditoria IBS/CBS NF-e/NFC-e | aprovada documentalmente | `07-plano-de-fases-e-criterios-de-aceite.md`             | N/A             | 2026-05-29 | Documental; base A+B autorizada |
| 2.4A+B - Base IBS/CBS e emissoes normais | validada | `07-plano-de-fases-e-criterios-de-aceite.md`                         | 2026-05-29      | 2026-05-29  | Checkpoint `9eb217f2b5de2f834eb137305de1216d47e4b36e`; derivados, eventos IBS/CBS e credito/debito pendentes |
| 2.4C.0 - Planejamento derivados com IBS/CBS | aprovada documentalmente | `07-plano-de-fases-e-criterios-de-aceite.md`                         | N/A             | 2026-06-02  | Documental; 2.4C.1 autorizada |
| 2.4C.1 - Devolucao/estorno IBS/CBS | validada | `07-plano-de-fases-e-criterios-de-aceite.md`                         | 2026-06-02      | 2026-06-02  | Somente `/1/nfe/devolucao/`; complementar/ajuste/eventos/credito-debito fora do escopo |
| 2.4C.2 - Complementar preco/quantidade IBS/CBS | validada | `07-plano-de-fases-e-criterios-de-aceite.md`                         | 2026-06-02      | 2026-06-02  | Checkpoint `11a9ba78c429936cedc7d10a5d45c6a683781be3`; complementar tributaria, ajuste, eventos e credito/debito fora do escopo |
| 2.4C.3 - Ajuste frente a Reforma Tributaria | validada | `07-plano-de-fases-e-criterios-de-aceite.md`                         | 2026-06-02      | 2026-06-02  | Nao inferir IBS/CBS; eventos, credito/debito e complementar tributaria bloqueados |
| 2.4C - Derivados com IBS/CBS | validada no escopo autorizado | `07-plano-de-fases-e-criterios-de-aceite.md`                         | 2026-06-02      | 2026-06-02  | Eventos IBS/CBS, credito/debito e complementar tributaria nao iniciados |
| 2.4D.0 - Planejamento Eventos IBS/CBS | documentada | `07-plano-de-fases-e-criterios-de-aceite.md`                         | N/A             | 2026-06-02  | Somente documental; endpoint proprio `/1/nfe/evento-ibs-cbs/`; cancelamento por `/1/nfe/evento-ibs-cbs/cancelar/` planejado em subfase separada |
| 2.4D.1 - Evento IBS/CBS 112110 | validada | `07-plano-de-fases-e-criterios-de-aceite.md`                         | 2026-06-02      | 2026-06-02  | Somente `cod_evento=112110`; cancelamento e demais eventos bloqueados |
| 2.4D.2 - Cancelamento evento IBS/CBS 112110 | validada | `07-plano-de-fases-e-criterios-de-aceite.md`                         | 2026-06-17      | 2026-06-17  | Somente cancelamento do evento 112110; demais eventos/cancelamentos bloqueados |
| 2.4D.3.0 - Priorizacao demais eventos IBS/CBS | aprovada documentalmente | `07-plano-de-fases-e-criterios-de-aceite.md`                         | N/A             | 2026-06-17  | Documental; 112150 autorizado |
| 2.4D.3 - Evento IBS/CBS 112150 | validada | `07-plano-de-fases-e-criterios-de-aceite.md`                         | 2026-06-17      | 2026-06-17  | Checkpoint `b0f2e093`; somente 112150 |
| 2.4D.4 - Cancelamento evento IBS/CBS 112150 | validada | `07-plano-de-fases-e-criterios-de-aceite.md`                         | 2026-06-17      | 2026-06-17  | Checkpoint `fe261d3c`; somente cancelamento do 112150; cancelamento generico e demais eventos bloqueados |
| 2.4D.5.0 - Planejamento eventos 112120/112130/112140 | aprovada | `07-plano-de-fases-e-criterios-de-aceite.md`                         | N/A             | 2026-06-18  | Somente documental; codigo funcional nao autorizado |
| 2.4D.5.1 - Evento IBS/CBS 112130 | validada | `07-plano-de-fases-e-criterios-de-aceite.md`                         | 2026-06-18      | 2026-06-18  | Somente `cod_evento=112130`; payload oficial com `itens[]`; 112120/112140/211xxx e cancelamento do 112130 fora do escopo |
| 2.4D.5.2 - Cancelamento evento IBS/CBS 112130 | validada | `07-plano-de-fases-e-criterios-de-aceite.md`                         | 2026-06-18      | 2026-06-18  | Checkpoint `d7a82117`; somente cancelamento do evento 112130 autorizado; cancelamento generico e demais eventos bloqueados |
| 2.4D.6.0 - Planejamento final 112120/112140 | aprovada | `07-plano-de-fases-e-criterios-de-aceite.md`                         | N/A             | 2026-06-19  | `112120` e `112140` adiados; sem generalizar cancelamento; `211xxx` adiados |
| 2.4D - Eventos IBS/CBS | implementacao parcial validada | `07-plano-de-fases-e-criterios-de-aceite.md`                         | 2026-06-02      | 2026-06-18  | 112110/112130/112150 e respectivos cancelamentos validados; 112120/112140/211xxx adiados |
| 2.4E - Credito/debito com IBS/CBS | nao iniciada | `07-plano-de-fases-e-criterios-de-aceite.md`                         | N/A             | N/A         | Bloqueada ate base validada |
| 2.5.0 - Planejamento credito/debito NF-e | aprovada documentalmente | `07-plano-de-fases-e-criterios-de-aceite.md`             | N/A             | 2026-05-29 | Codigo adiado ate base IBS/CBS |
| 2.5.1.0 - Replanejamento final credito/debito | aprovada | `03-prd-matriz-api-webmania.md`, `07-plano-de-fases-e-criterios-de-aceite.md` | N/A | 2026-06-19 | Todos os tipos adiados; fase preparatoria autorizada |
| 2.5.1P - Base fiscal referenciada | validada | `04-prd-dominio-e-modelagem.md`, `07-plano-de-fases-e-criterios-de-aceite.md` | 2026-06-19 | 2026-06-19 | Checkpoint `f199905d`; base auditavel pronta; emissao bloqueada |
| 2.5.2.0 - Selecao do primeiro tipo credito/debito | aprovada | `03-prd-matriz-api-webmania.md`, `07-plano-de-fases-e-criterios-de-aceite.md` | N/A | 2026-06-19 | Opcao D aprovada; nenhuma emissao |
| 2.5.2P - Base monetaria/comercial por item | validada | `04-prd-dominio-e-modelagem.md`, `07-plano-de-fases-e-criterios-de-aceite.md` | 2026-06-19 | 2026-06-19 | Nenhuma emissao; credito tipo 1 depende de nova aprovacao |
| 2.5.3.0 - Planejamento credito tipo 1 | documentada, aguardando aprovacao | `03-prd-matriz-api-webmania.md`, `07-plano-de-fases-e-criterios-de-aceite.md` | N/A | 2026-06-22 | Adiar emissao ate validar valoracao do produto e IBS/CBS de multa/juros |
| 2.5.3P - Preview fiscal multa/juros | validada | `04-prd-dominio-e-modelagem.md`, `07-plano-de-fases-e-criterios-de-aceite.md` | 2026-06-22 | 2026-06-22 | Pre-payload sem documento, tentativa ou gateway remoto |
| 2.5.4 - Emissao credito tipo 1 | validada | `04-prd-dominio-e-modelagem.md`, `07-plano-de-fases-e-criterios-de-aceite.md` | 2026-06-22 | 2026-06-22 | Somente multa/juros a partir de preview aprovada; demais tipos bloqueados |
| 2.5.5 - Cancelamento credito tipo 1 | validada | `05-prd-seguranca-idempotencia-webhooks.md`, `07-plano-de-fases-e-criterios-de-aceite.md` | 2026-06-22 | 2026-06-22 | Somente cancelamento padrao da NF-e de credito autorizada |
| 2.5.6.0 - Reavaliacao do proximo bloco | aprovada | `03-prd-matriz-api-webmania.md`, `07-plano-de-fases-e-criterios-de-aceite.md` | N/A | 2026-06-22 | Debito tipo 4 selecionado; emissao nao autorizada |
| 2.5.6P - Preview fiscal debito tipo 4 | validada | `04-prd-dominio-e-modelagem.md`, `07-plano-de-fases-e-criterios-de-aceite.md` | 2026-06-22 | 2026-06-22 | Checkpoint `189bf973`; preview propria sem gateway remoto |
| 2.5.7.0 - Planejamento emissao debito tipo 4 | aprovada | `03-prd-matriz-api-webmania.md`, `07-plano-de-fases-e-criterios-de-aceite.md` | N/A | 2026-06-22 | Emissao tipo 4 autorizada em fase propria |
| 2.5.7 - Emissao debito tipo 4 | validada | `04-prd-dominio-e-modelagem.md`, `05-prd-seguranca-idempotencia-webhooks.md` | 2026-06-22 | 2026-06-22 | Checkpoint `9214150d`; somente multa/juros local |
| 2.5.8 - Cancelamento debito tipo 4 | validada | `05-prd-seguranca-idempotencia-webhooks.md`, `07-plano-de-fases-e-criterios-de-aceite.md` | 2026-06-22 | 2026-06-23 | Checkpoint `df1a163e`; ciclo emissao/cancelamento completo |
| 2.6.0 - Reavaliacao do roadmap fiscal | aprovada | `03-prd-matriz-api-webmania.md`, `07-plano-de-fases-e-criterios-de-aceite.md` | 2026-06-23 | 2026-06-23 | Priorizada Fase 3.0 documental para NFS-e expandida |
| 3.0 - Auditoria e planejamento NFS-e expandida | em planejamento | `01-auditoria-as-is.md`, `03-prd-matriz-api-webmania.md`, `07-plano-de-fases-e-criterios-de-aceite.md` | N/A | 2026-06-23 | Somente documentacao; sem codigo funcional |
| 3.1 - Estabilizacao NFS-e legado | validada | `04-prd-dominio-e-modelagem.md`, `05-prd-seguranca-idempotencia-webhooks.md`, `07-plano-de-fases-e-criterios-de-aceite.md` | 2026-06-23 | 2026-06-23 | Capacidades, compatibilidade legada, timestamp remoto canonico e 297 testes direcionados aprovados |
| 3.2 - Consulta/reconciliacao NFS-e ampliada | validada | `03-prd-matriz-api-webmania.md`, `05-prd-seguranca-idempotencia-webhooks.md`, `07-plano-de-fases-e-criterios-de-aceite.md` | 2026-06-23 | 2026-06-23 | Consulta por UUID de item/lote e snapshot informativo de status municipal; 311 testes direcionados aprovados |
| 3.3 - Cancelamento idempotente NFS-e legado | validada tecnicamente | `05-prd-seguranca-idempotencia-webhooks.md`, `07-plano-de-fases-e-criterios-de-aceite.md`, `09-decisoes-arquiteturais.md` | 2026-06-23 | 2026-06-23 | Restrito a `NfseRequest`/`NfseItem`, tentativa persistida e `uncertain` sem reenvio |
| 3.4.0 - Planejamento da substituicao NFS-e | aprovada documentalmente | `03-prd-matriz-api-webmania.md`, `04-prd-dominio-e-modelagem.md`, `09-decisoes-arquiteturais.md` | N/A | 2026-06-23 | Decisao: preparar preview imutavel do novo RPS antes da operacao funcional |
| 3.4P - Preview substituicao NFS-e | validada | `04-prd-dominio-e-modelagem.md`, `07-plano-de-fases-e-criterios-de-aceite.md` | 2026-06-23 | 2026-06-23 | Checkpoint `747b6750a62d6ed59bed84c4616f89793c4247b4`; sem POST remoto |
| 3.4.1 - Substituicao remota NFS-e | validada tecnicamente | `03-prd-matriz-api-webmania.md`, `05-prd-seguranca-idempotencia-webhooks.md`, `07-plano-de-fases-e-criterios-de-aceite.md` | 2026-06-24 | 2026-06-24 | Checkpoint `5865c74d59459ce1f347d8a36a217098f20cb5a9`; manifestacao e emissao manual nova nao iniciadas |
| 3.5.0 - Reavaliacao apos NFS-e legada | validada | `03-prd-matriz-api-webmania.md`, `07-plano-de-fases-e-criterios-de-aceite.md`, `09-decisoes-arquiteturais.md` | N/A | 2026-06-26 | Decisao aprovada: manifestacao NFS-e Padrao Nacional |
| 3.6.0 - Planejamento manifestacao NFS-e Padrao Nacional | validada documentalmente | `03-prd-matriz-api-webmania.md`, `04-prd-dominio-e-modelagem.md`, `05-prd-seguranca-idempotencia-webhooks.md`, `07-plano-de-fases-e-criterios-de-aceite.md` | N/A | 2026-06-26 | Checkpoint `0a8dd0c9`; sem codigo funcional |
| 3.6.1 - Manifestacao NFS-e Padrao Nacional | validada | `04-prd-dominio-e-modelagem.md`, `05-prd-seguranca-idempotencia-webhooks.md`, `06-prd-ux-permissoes-e-workflows.md`, `08-plano-de-testes-e-operacao.md` | 2026-06-26 | 2026-06-27 | Checkpoint `da3b2b48`; restrita a NFS-e local Padrao Nacional |
| 3.7.0 - Reavaliacao apos manifestacao NFS-e | validada documentalmente | `03-prd-matriz-api-webmania.md`, `07-plano-de-fases-e-criterios-de-aceite.md`, `09-decisoes-arquiteturais.md` | N/A | 2026-06-27 | Checkpoint `1b60125c`; recomenda proxima fase preparatoria |
| 3.7P - Preview emissao manual nova NFS-e | validada | `04-prd-dominio-e-modelagem.md`, `06-prd-ux-permissoes-e-workflows.md`, `08-plano-de-testes-e-operacao.md` | 2026-06-27 | 2026-06-27 | Checkpoint `1fdded4e`; `NfseManualEmissionPreview` implementada; sem transmissao Webmania |
| 3.7.1 - Emissao manual nova NFS-e | validada | `03-prd-matriz-api-webmania.md`, `04-prd-dominio-e-modelagem.md`, `05-prd-seguranca-idempotencia-webhooks.md`, `06-prd-ux-permissoes-e-workflows.md`, `08-plano-de-testes-e-operacao.md` | 2026-06-28 | 2026-06-28 | Checkpoint `2cb35206`; somente a partir de preview aprovada; cancelamento/substituicao/manifestacao fora do escopo |
| 3.8.0 - Reavaliacao pos-emissao manual NFS-e | validada documentalmente | `03-prd-matriz-api-webmania.md`, `07-plano-de-fases-e-criterios-de-aceite.md`, `09-decisoes-arquiteturais.md` | N/A | 2026-06-28 | Checkpoint `1faf0a9`; decidiu cancelamento da NFS-e manual |
| 3.8.1 - Cancelamento NFS-e manual nova | validada | `05-prd-seguranca-idempotencia-webhooks.md`, `07-plano-de-fases-e-criterios-de-aceite.md`, `08-plano-de-testes-e-operacao.md` | 2026-06-28 | 2026-06-28 | Checkpoint `29f3f3a9`; ciclo manual minimo completo com cancelamento por `NfseCancellation` |
| 3.9.0 - Reavaliacao apos ciclo minimo NFS-e manual | validada documentalmente | `03-prd-matriz-api-webmania.md`, `07-plano-de-fases-e-criterios-de-aceite.md`, `09-decisoes-arquiteturais.md` | N/A | 2026-06-28 | Checkpoint `21d684e7`; decidiu substituicao da NFS-e manual |
| 3.9.1 - Substituicao NFS-e manual nova | validada | `03-prd-matriz-api-webmania.md`, `05-prd-seguranca-idempotencia-webhooks.md`, `08-plano-de-testes-e-operacao.md` | 2026-06-29 | 2026-06-29 | Checkpoint `99254f33`; extensao segura de `NfseSubstitutionPreview`/`NfseSubstitution` |
| 3.10.0 - Reavaliacao manifestacao NFS-e manual | validada documentalmente | `03-prd-matriz-api-webmania.md`, `07-plano-de-fases-e-criterios-de-aceite.md`, `09-decisoes-arquiteturais.md` | N/A | 2026-06-29 | Checkpoint `8d5c7192`; manifestacao manual adiada |
| 3.11.0 - Planejamento NFS-e recebida/importada | validada documentalmente | `03-prd-matriz-api-webmania.md`, `04-prd-dominio-e-modelagem.md`, `07-plano-de-fases-e-criterios-de-aceite.md` | N/A | 2026-06-29 | Checkpoint `6f36f7fc`; decidiu registro local por XML |
| 3.11.1 - Registro local NFS-e recebida por XML | validada tecnicamente | `04-prd-dominio-e-modelagem.md`, `05-prd-seguranca-idempotencia-webhooks.md`, `08-plano-de-testes-e-operacao.md` | 2026-06-29 | 2026-06-29 | Migration `0069`; upload XML unitario; sem manifestacao, Webmania, `NfseItem` ou `FiscalDocument(nfse)` |
| 3.12.0 - Reavaliacao manifestacao NFS-e recebida | validada documentalmente | `03-prd-matriz-api-webmania.md`, `04-prd-dominio-e-modelagem.md`, `05-prd-seguranca-idempotencia-webhooks.md`, `07-plano-de-fases-e-criterios-de-aceite.md` | N/A | 2026-06-29 | Checkpoint `a5b4f4b`; decidiu extensao segura de `NfseManifestation` |
| 3.12.1 - Manifestacao NFS-e recebida | validada | `04-prd-dominio-e-modelagem.md`, `05-prd-seguranca-idempotencia-webhooks.md`, `06-prd-ux-permissoes-e-workflows.md`, `08-plano-de-testes-e-operacao.md` | 2026-06-29 | 2026-06-29 | Checkpoint `6cc3a788`; migration `0070`; somente `NfseReceivedDocument` validado; sem manual, emissao, cancelamento ou substituicao de recebida |
| 3.13.0 - Reavaliacao pos-bloco NFS-e | validada documentalmente | `03-prd-matriz-api-webmania.md`, `07-plano-de-fases-e-criterios-de-aceite.md`, `09-decisoes-arquiteturais.md` | N/A | 2026-06-29 | Checkpoint `d83b37dc`; decidiu consulta auxiliar GET-only para NFS-e recebida |
| 3.13.1 - Consulta auxiliar NFS-e recebida | validada | `04-prd-dominio-e-modelagem.md`, `05-prd-seguranca-idempotencia-webhooks.md`, `06-prd-ux-permissoes-e-workflows.md`, `08-plano-de-testes-e-operacao.md` | 2026-06-29 | 2026-06-29 | Checkpoint `01f0924d`; migration `0071`; `NfseReceivedDocumentConsultation`; GET-only consultivo; sem sobrescrita destrutiva, manifestacao automatica, `NfseItem` ou `FiscalDocument(nfse)` |
| 3.14.0 - Reavaliacao apos NFS-e recebida completa | validada documentalmente | `03-prd-matriz-api-webmania.md`, `07-plano-de-fases-e-criterios-de-aceite.md`, `09-decisoes-arquiteturais.md`, `11-backlog-e-pendencias.md` | N/A | 2026-06-29 | Checkpoint `18d1840d`; decidiu lote XML local de NFS-e recebida |
| 3.14.1 - Importacao em lote XML NFS-e recebida | validada | `04-prd-dominio-e-modelagem.md`, `05-prd-seguranca-idempotencia-webhooks.md`, `06-prd-ux-permissoes-e-workflows.md`, `08-plano-de-testes-e-operacao.md` | 2026-06-29 | 2026-06-29 | Checkpoint `b53e862b`; migration `0072`; lote persistido; relatorio por arquivo; XML-only; sem Webmania/manifestacao automatica |
| 3.15.0 - Reavaliacao apos consolidacao NFS-e recebida | validada documentalmente | `03-prd-matriz-api-webmania.md`, `07-plano-de-fases-e-criterios-de-aceite.md`, `09-decisoes-arquiteturais.md`, `11-backlog-e-pendencias.md` | N/A | 2026-06-29 | Checkpoint `4815728b`; decidiu planejar integracao e-mail/ERP para XML NFS-e |
| 3.15.1 - Planejamento integracao e-mail/ERP XML NFS-e | validada documentalmente | `04-prd-dominio-e-modelagem.md`, `05-prd-seguranca-idempotencia-webhooks.md`, `06-prd-ux-permissoes-e-workflows.md`, `07-plano-de-fases-e-criterios-de-aceite.md`, `08-plano-de-testes-e-operacao.md` | N/A | 2026-06-30 | Checkpoint `5882cd4e`; decidiu inbox externa local/manual antes de conectores reais |
| 3.15.2 - Caixa de entrada externa XML NFS-e recebida | validada | `04-prd-dominio-e-modelagem.md`, `05-prd-seguranca-idempotencia-webhooks.md`, `06-prd-ux-permissoes-e-workflows.md`, `08-plano-de-testes-e-operacao.md` | 2026-06-30 | 2026-06-30 | Checkpoint `517d25b8`; migration `0073`; inbox local/manual validada |
| 3.16.0 - Reavaliacao apos inbox externa XML | validada documentalmente | `03-prd-matriz-api-webmania.md`, `07-plano-de-fases-e-criterios-de-aceite.md`, `09-decisoes-arquiteturais.md`, `11-backlog-e-pendencias.md` | N/A | 2026-06-30 | Checkpoint `267fc601`; decidiu ampliar inbox local |
| 3.16.1 - Ampliacao operacional da inbox XML NFS-e | validada | `04-prd-dominio-e-modelagem.md`, `05-prd-seguranca-idempotencia-webhooks.md`, `06-prd-ux-permissoes-e-workflows.md`, `08-plano-de-testes-e-operacao.md` | 2026-06-30 | 2026-06-30 | Checkpoint `166eda86`; filtros/busca, CSV sem XML bruto, acoes em massa e permissoes; sem conectores reais/Webmania automatica |
| 3.17.0 - Fechamento do bloco NFS-e recebida | validada documentalmente | `03-prd-matriz-api-webmania.md`, `07-plano-de-fases-e-criterios-de-aceite.md`, `09-decisoes-arquiteturais.md`, `11-backlog-e-pendencias.md` | N/A | 2026-06-30 | Checkpoint `424a3c2a`; decidiu auditoria tecnica/fiscal geral |
| 3.17.1 - Auditoria tecnica/fiscal geral | validada | `04-prd-dominio-e-modelagem.md`, `05-prd-seguranca-idempotencia-webhooks.md`, `06-prd-ux-permissoes-e-workflows.md`, `07-plano-de-fases-e-criterios-de-aceite.md`, `08-plano-de-testes-e-operacao.md`, `09-decisoes-arquiteturais.md`, `11-backlog-e-pendencias.md` | N/A | 2026-07-02 | Checkpoint `305dc22cf5d811f8c875812a178f68634583a986`; auditoria concluida sem alteracao funcional |
| 3.18.0 - Priorizacao pos-auditoria | validada documentalmente | `03-prd-matriz-api-webmania.md`, `07-plano-de-fases-e-criterios-de-aceite.md`, `09-decisoes-arquiteturais.md`, `11-backlog-e-pendencias.md` | N/A | 2026-07-02 | Checkpoint `274df7f7`; decidiu saneamento tecnico pos-auditoria |
| 3.18.1 - Saneamento tecnico pos-auditoria | validada | `04-prd-dominio-e-modelagem.md`, `05-prd-seguranca-idempotencia-webhooks.md`, `06-prd-ux-permissoes-e-workflows.md`, `07-plano-de-fases-e-criterios-de-aceite.md`, `08-plano-de-testes-e-operacao.md`, `09-decisoes-arquiteturais.md`, `10-log-de-implementacao.md`, `11-backlog-e-pendencias.md` | 2026-07-02 | 2026-07-02 | Checkpoint `96665e2142a3f8163508f36784b31d5af32247cb`; sem funcionalidade fiscal nova e sem alteracao de comportamento fiscal em producao |
| 3.19.0 - Encerramento temporario do ciclo fiscal funcional | validada documentalmente | `README.md`, `03-prd-matriz-api-webmania.md`, `04-prd-dominio-e-modelagem.md`, `05-prd-seguranca-idempotencia-webhooks.md`, `06-prd-ux-permissoes-e-workflows.md`, `07-plano-de-fases-e-criterios-de-aceite.md`, `08-plano-de-testes-e-operacao.md`, `09-decisoes-arquiteturais.md`, `10-log-de-implementacao.md`, `11-backlog-e-pendencias.md` | N/A | 2026-07-02 | Checkpoint `722ac3bb0561caf3720a2a967e9234506f8d7f92`; ciclo fiscal funcional temporariamente encerrado |
| 4.0.0 - Auditoria e mapeamento NF-e/NFC-e | validada documentalmente | `03-prd-matriz-api-webmania.md`, `04-prd-dominio-e-modelagem.md`, `05-prd-seguranca-idempotencia-webhooks.md`, `06-prd-ux-permissoes-e-workflows.md`, `07-plano-de-fases-e-criterios-de-aceite.md`, `08-plano-de-testes-e-operacao.md`, `09-decisoes-arquiteturais.md`, `10-log-de-implementacao.md`, `11-backlog-e-pendencias.md` | N/A | 2026-07-02 | Checkpoint `aa8414ea199c4a09dca53c246fe5fd49e6aa3a92`; decisao pela Opcao B |
| 4.0.1 - Saneamento Tecnico NF-e/NFC-e | validada | `04-prd-dominio-e-modelagem.md`, `05-prd-seguranca-idempotencia-webhooks.md`, `06-prd-ux-permissoes-e-workflows.md`, `07-plano-de-fases-e-criterios-de-aceite.md`, `08-plano-de-testes-e-operacao.md`, `09-decisoes-arquiteturais.md`, `10-log-de-implementacao.md`, `11-backlog-e-pendencias.md` | 2026-07-02 | 2026-07-02 | Checkpoint `613a73cb31de23e68883ac35ddbf396e3f08f030`; sem funcionalidade nova |
| 4.0.2 - Planejamento de permissoes dedicadas NF-e normal | em planejamento documental | `03-prd-matriz-api-webmania.md`, `04-prd-dominio-e-modelagem.md`, `05-prd-seguranca-idempotencia-webhooks.md`, `06-prd-ux-permissoes-e-workflows.md`, `07-plano-de-fases-e-criterios-de-aceite.md`, `08-plano-de-testes-e-operacao.md`, `09-decisoes-arquiteturais.md`, `10-log-de-implementacao.md`, `11-backlog-e-pendencias.md` | N/A | N/A | Somente documentacao; decidir permissoes dedicadas com fallback |
| 3 - Completar NFS-e          | nao iniciada         | `03-prd-matriz-api-webmania.md`                                       | N/A             | N/A         | Fase 1 validada          |
| 4 - CT-e e CT-e OS           | nao iniciada         | `03-prd-matriz-api-webmania.md`                                       | N/A             | N/A         | Fases prioritarias       |
| 5 - MDF-e                    | nao iniciada         | `03-prd-matriz-api-webmania.md`                                       | N/A             | N/A         | CT-e/MDF-e modelados     |
| 6 - NFCom                    | nao iniciada         | `03-prd-matriz-api-webmania.md`                                       | N/A             | N/A         | Confirmar relevancia     |
| 7 - DC-e                     | nao iniciada         | `03-prd-matriz-api-webmania.md`                                       | N/A             | N/A         | API v2.0.0; feature flag interna obrigatoria |
| 8 - Consolidacao e legado    | nao iniciada         | `04-prd-dominio-e-modelagem.md`                                       | N/A             | N/A         | Backfill aprovado        |

## Checklist de retomada

- Rodar `git status --short`.
- Confirmar se ha alteracoes nao relacionadas.
- Ler `01-auditoria-as-is.md` e validar se o codigo ainda corresponde.
- Ler `10-log-de-implementacao.md` para saber o que foi feito.
- Confirmar fase aprovada pelo usuario antes de editar codigo.
- Reconsultar documentacao oficial Webmania se endpoint, autenticacao ou payload tiver risco de mudanca.
