# Plano de fases e criterios de aceite

## Fase 0 - Auditoria e PRDs

- Objetivos: ler codigo, validar OpenAPI, criar docs.
- Dependencias: nenhuma.
- Arquivos previstos: somente `docs/fiscal-webmania/`.
- Alteracoes permitidas: documentacao.
- Alteracoes proibidas: codigo funcional e migrations.
- Migrations: nenhuma.
- Testes: nao aplicavel; validar `git diff`.
- Aceite: documentos criados, OpenAPI validado criado, parada para aprovacao.
- Riscos: documentacao desatualizar se codigo mudar antes da Fase 1.
- Rollback: remover pasta de docs.
- Status: validada em 2026-05-28.

## Fase 1 - Estabilizacao e nucleo fiscal NF-e/NFS-e atuais

- Objetivos: preservar fluxos atuais, resolver bugs reais, idempotencia persistida, webhook e reconciliacao seguros.
- Dependencias: Fase 0 aprovada.
- Arquivos previstos: `apps/finance/models/finance.py`, migrations novas, services fiscais, testes finance.
- Alteracoes permitidas: minimas e compatíveis.
- Alteracoes proibidas: novos documentos fiscais, remocao de legado.
- Migrations: sim, para tentativa/idempotencia/evento se aprovado.
- Testes: concorrencia, timeout, webhook duplicado, tenancy, downloads.
- Aceite: NF-e/NFS-e atuais seguem funcionando e nao duplicam emissao. Validacao fiscal direcionada passou, incluindo teste concorrente transacional real. Validacao ampla possui falhas globais comprovadas no baseline anterior e aceitas como dividas preexistentes.
- Rollback: manter legado como fonte operacional.
- Status: validada com dividas preexistentes registradas em 2026-05-28.

## Fase 2 - Completar NF-e/NFC-e

- Objetivos: NFC-e, carta de correcao, devolucao, complementar, ajuste, inutilizacao ampliada, manifestacao, IBS/CBS.
- Dependencias: Fase 1 validada.
- Migrations: provaveis.
- Testes: gateway mockado para cada operacao, permissoes e status.
- Status: Fase 2.0 aprovada documentalmente; Fase 2.1 implementada somente para CC-e e aguardando revisao/validacao.

### Fase 2.0 - Planejamento tecnico NF-e/NFC-e

- Escopo: documentar modelagem, compatibilidade, idempotencia, permissoes, subfases, arquivos previstos e criterios de aceite.
- Dependencias: Fase 1 validada com dividas preexistentes registradas.
- Alteracoes permitidas: somente `docs/fiscal-webmania/**`.
- Alteracoes proibidas: services, views, models, migrations, forms, templates e testes funcionais.
- OpenAPI: alterar apenas se houver correcao documental necessaria.
- Aceite: documentos atualizados e parada para aprovacao da Fase 2.1.
- Status: aprovada documentalmente.

### Fase 2.1 - CC-e

- Escopo: Carta de Correcao Eletronica para NF-e autorizada.
- Dependencias: Fase 2.0 aprovada; Fase 1 validada.
- Modelagem necessaria: `FiscalDocument`, `FiscalDocumentEvent` e extensao minima de `FiscalEmissionAttempt`; evento `cce` vinculado a NF-e original por projecao sob demanda de `NfeItem`. `FiscalDocumentLink` proibido nesta subfase.
- Endpoint Webmania: `POST /1/nfe/cartacorrecao/`; consulta/download via `GET /1/nfe/consulta/` e URLs retornadas.
- Arquivos previstos: `apps/finance/models/finance.py`, migration nova, `apps/finance/services/nfe_events.py`, `apps/finance/services/fiscal_attempts.py`, `apps/finance/services/webmania_webhooks.py`, `apps/finance/views/nfe.py`, `apps/finance/urls.py`, template de detalhe/modal CC-e, testes finance, docs.
- Alteracoes permitidas: evento CC-e, idempotencia da operacao, permissao `issue_nfe_correction`, UI condicional em NF-e autorizada.
- Alteracoes proibidas: devolucao, complementar, ajuste, NFC-e, manifestacao, IBS/CBS.
- Testes obrigatorios: CC-e autorizada com mock Webmania; NF-e nao autorizada bloqueia; duas requisicoes concorrentes geram uma chamada remota; timeout vira `uncertain`; webhook/consulta atualiza evento; usuario de outra oficina nao acessa; permissao exigida; payload sanitizado.
- Aceite: CC-e registrada como evento, nao como nota comum; NF-e original preservada; downloads/evento visiveis no detalhe compativel; nenhum reenvio automatico em `uncertain`; nenhuma criacao de `FiscalDocumentLink`.
- Riscos: sequencia de CC-e e regras legais de correcao textual; divergencias de retorno Webmania.
- Rollback: desabilitar action CC-e e ignorar tabelas/eventos novos; legado NF-e continua operacional.
- Status: validada em 2026-05-28; nao autoriza Fase 2.2.

### Fase 2.2 - Devolucao, complementar e ajuste

- Escopo: documentos derivados referenciando NF-e original.
- Dependencias: Fase 2.1 validada ou decisao explicita para iniciar com nucleo fiscal minimo ja aprovado.
- Modelagem necessaria: `FiscalDocument` para documento derivado, `FiscalDocumentLink` para relacao com original, tentativa idempotente por operacao.
- Endpoints Webmania: `POST /1/nfe/devolucao/`, `POST /1/nfe/complementar/`, `POST /1/nfe/ajuste/`, consulta/download por `GET /1/nfe/consulta/` e URLs retornadas.
- Arquivos previstos: services de documentos derivados, forms por tipo, views/actions, URLs, templates, testes de gateway e permissao, docs.
- Testes obrigatorios: derivado referencia original; item/valor obrigatorio; timeout `uncertain`; concorrencia nao duplica; cross-workshop negado; webhook atualiza documento derivado sem mexer indevidamente no original.
- Riscos: CFOP inverso, regras fiscais por UF/operacao, complementar parcial, estorno fora de prazo.
- Rollback: desabilitar actions e manter documentos ja emitidos consultaveis.
- Status: nao iniciada.

### Fase 2.3 - NFC-e

- Escopo: emissao NFC-e pela API v1, separada de NF-e, com configuracao por oficina.
- Dependencias: nucleo fiscal minimo e decisao sobre configuracao NFC-e por oficina.
- Modelagem necessaria: `FiscalDocument(kind="nfce")`, tentativa idempotente por origem/intencao, configuracao de serie/modelo NFC-e.
- Endpoints Webmania: `POST /1/nfe/emissao/` com modelo NFC-e; `PUT /1/nfe/cancelar/`; `GET /1/nfe/consulta/`; downloads por URLs retornadas.
- Arquivos previstos: gateway NFC-e, forms/telas de emissao, views/URLs, templates, testes de configuracao e permissao, docs.
- Testes obrigatorios: oficina sem NFC-e bloqueia; emissao mockada; concorrencia; timeout `uncertain`; cancelamento autorizado; downloads; separacao NF-e/NFC-e na UI.
- Riscos: contingencia/offline, CSC/token, impressao DANFE NFC-e, cancelamento por substituicao ainda pendente de confirmacao operacional.
- Rollback: feature/config desliga NFC-e sem afetar NF-e.
- Status: nao iniciada.

### Fase 2.4 - Manifestacao e IBS/CBS

- Escopo: eventos avancados de manifestacao do destinatario, IBS/CBS e cancelamento de IBS/CBS.
- Dependencias: nucleo de eventos validado; revalidacao da documentacao Webmania e regras da Reforma Tributaria.
- Modelagem necessaria: `FiscalDocumentEvent` com tipo, codigo, protocolo/status bruto, vinculo com evento original para cancelamento.
- Endpoints Webmania: `POST /1/nfe/manifesta/`, `POST /1/nfe/evento-ibs-cbs/`, `PUT /1/nfe/evento-ibs-cbs/cancelar/`.
- Arquivos previstos: services de eventos avancados, forms por evento, views/actions, URLs, testes de evento/cancelamento, docs.
- Testes obrigatorios: evento autorizado; evento duplicado bloqueado; cancelamento referencia evento original; fora de ordem nao regride; permissao restrita; logs/payloads sanitizados.
- Riscos: mudanca normativa IBS/CBS, codigos de evento novos, suporte remoto parcial.
- Rollback: desligar actions avancadas mantendo historico ja recebido.
- Status: nao iniciada.

## Fase 3 - Completar NFS-e

- Objetivos: emissao manual, RPS/lote, capacidades municipais, substituicao, manifestacao, agendamento e downloads.
- Dependencias: Fase 1 validada.
- Migrations: capacidades municipais.
- Testes: municipio com/sem recurso, substituicao, cancelamento agendado.
- Status: nao iniciada.

## Fase 4 - CT-e e CT-e OS

- Objetivos: emissao, consulta, cancelamento, correcao, entrega, pagamento, diferencas CT-e OS.
- Dependencias: dominio unificado suficiente.
- Status: nao iniciada.

## Fase 5 - MDF-e

- Objetivos: emissao, vinculo com NF-e/CT-e, consulta, encerramento, cancelamento, condutor, pendencias operacionais.
- Dependencias: vinculos entre documentos.
- Status: nao iniciada.

## Fase 6 - NFCom

- Objetivos: operacoes suportadas, emissao manual, status e downloads.
- Dependencias: dominio unificado.
- Alteracoes permitidas: somente atras de feature flag e habilitacao administrativa por oficina.
- Alteracoes proibidas: ativar NFCom por padrao para oficinas.
- Testes: feature flag desligada, permissao, emissao manual mockada, consulta, downloads e desligamento seguro.
- Aceite: NFCom pode ser desligada sem afetar outros modelos fiscais.
- Status: nao iniciada.

## Fase 7 - DC-e beta

- Objetivos: feature flag, emissao, consulta, cancelamento, sinalizacao beta.
- Dependencias: configuracao beta por oficina.
- Alteracoes permitidas: somente atras de feature flag, permissao especifica e habilitacao administrativa por oficina.
- Alteracoes proibidas: usar DC-e em producao sem decisao explicita e sem sinalizacao beta.
- Testes: feature flag desligada, permissao, emissao mockada, consulta, cancelamento e isolamento de erro beta.
- Aceite: DC-e pode ser desativada sem alterar comportamento de NF-e/NFS-e/NFC-e/CT-e/MDF-e/NFCom.
- Status: nao iniciada.

## Fase 8 - Consolidacao, migracao e remocao de legado

- Objetivos: backfill aprovado, migracao definitiva, remocao controlada, documentacao final.
- Dependencias: fases anteriores validadas.
- Status: nao iniciada.

## Gate permanente

Nenhuma fase posterior deve iniciar sem aceite explicito da anterior.
