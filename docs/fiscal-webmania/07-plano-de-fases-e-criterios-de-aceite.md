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
- Status: Fase 2.0 aprovada documentalmente; Fases 2.1, 2.2A, 2.2B.1, 2.2C e ciclo simples 2.3 validado. Fase 2.4.0 aprovada documentalmente; Fase 2.4A+B validada para classes fiscais NF-e, NF-e normal e NFC-e manual; credito/debito adiado ate base tributaria completa.

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

### Fase 2.2A - Devolucao e estorno

- Escopo: NF-e de devolucao parcial/total e cenario de estorno pelo endpoint de devolucao.
- Dependencias: Fase 2.1 validada e autorizacao explicita da subfase.
- Modelagem necessaria: `FiscalDocument(kind="nfe", purpose="return" ou "reversal")`; `FiscalDocumentLink` obrigatorio para NF-e original local ou externa; suporte a itens/quantidades parciais.
- Endpoint Webmania: `POST /1/nfe/devolucao/`; consulta/download por `GET /1/nfe/consulta/` e URLs retornadas.
- NF-e externa: permitir chave manual de 44 digitos, validar formato, criar documento externo minimo com `origin=external`, registrar que nao foi emitido localmente e exigir confirmacao explicita; nao usar `/1/nfe/consulta/` como garantia de validacao de outro emissor.
- Idempotencia: criar `FiscalDocument` derivado antes do gateway e usar tentativa associada ao derivado com chave `hash(workshop_id, derived_document_id, operation_type, request_generation)`; payload sanitizado congelado apos envio.
- Contrato parcial: `POST /1/nfe/devolucao/` deve enviar `produtos` como sequenciais fiscais da NF-e original e `quantidade` alinhado pelo mesmo indice; devolucao total e estorno nao enviam selecao parcial desnecessaria.
- Restricao externa: NF-e externa minima por chave manual nao permite devolucao parcial ate haver XML/importacao validada com ordem fiscal dos itens.
- Testes obrigatorios: link obrigatorio; devolucao parcial; estorno via devolucao; timeout `uncertain`; concorrencia nao duplica; cross-workshop negado; webhook atualiza derivado sem alterar original; NF-e externa marcada.
- Rollback: desabilitar actions de devolucao/estorno e manter documentos ja emitidos consultaveis.
- Status: validada em 2026-05-28; Fase 2.2B nao iniciada.

### Fase 2.2B - Nota complementar

- Escopo: complementar preco/quantidade, complementar impostos e documento de adicao/importacao quando aplicavel.
- Dependencias: Fase 2.2A validada ou decisao explicita para executar em paralelo documentalmente aprovada.
- Modelagem necessaria: `FiscalDocument(kind="nfe", purpose="complementary")` com `complementary_type`; `FiscalDocumentLink(role="complements")` obrigatorio para NF-e original local ou externa.
- Endpoint Webmania: `POST /1/nfe/complementar/`.
- Subtipos: `complementary_price_quantity`, `complementary_tax`, `complementary_import_addition`.
- Decisao externa: bloquear `complementary_price_quantity` para NF-e externa minima sem XML/importacao validada; permitir `complementary_tax` externa somente se aprovado com confirmacao forte, payload auditavel e permissao restrita; adiar `complementary_import_addition` por baixa prioridade.
- Idempotencia: criar documento complementar derivado antes do gateway; chave `hash(workshop_id, complementary_document_id, operation_type, request_generation)`; payload congelado apos envio.
- Testes obrigatorios: complemento de preco local; complemento de quantidade local; complemento tributario por imposto suportado; vinculo obrigatorio ao original; documento externo minimo; bloqueio de preco/quantidade externa sem itens validados; regra para imposto complementar externo; webhook; idempotencia; concorrencia; timeout `uncertain`; permissao; cross-workshop; downloads; payload sanitizado.
- Rollback: desabilitar action complementar.
- Status: Fase 2.2B.0 aprovada documentalmente; Fase 2.2B.1 validada somente para preco/quantidade local. Complementar tributaria, IBS/CBS e adicao/importacao permanecem nao implementadas e exigem nova autorizacao.

#### Fase 2.2B.1 - Complementar de preco/quantidade para NF-e local

- Escopo implementado: `POST /1/nfe/complementar/` para NF-e original local autorizada/elegivel, com itens fiscais conhecidos, permissao especifica e confirmacao explicita.
- Modelagem implementada: `FiscalDocument(purpose="complementary", complementary_type="price_quantity", origin="local")`; `FiscalDocumentLink(role="complements")`; `FiscalEmissionAttempt(operation_type="complementary_price_quantity")`.
- Payload permitido: `chave` ou `uuid`, `operacao`, `natureza_operacao`, `codigo_cfop`, `ambiente`, `cliente`, `produtos`, `url_notificacao`. Cada produto preserva dados fiscais do item original, substituindo apenas quantidade/valor complementar, CFOP e situacao tributaria ICMS informados.
- Alteracoes proibidas ainda vigentes: objeto `impostos`, ICMS-ST, IPI, ISSQN, IBS/CBS, `agropecuario`, documento de adicao/importacao, NF-e externa minima para preco/quantidade, central fiscal nova.
- Testes executados: Fases 1, 2.1, 2.2A e 2.2B.1 direcionadas com 58 testes OK; `makemigrations finance --check --dry-run` OK; `ruff check` nos Python tocados OK.
- Rollback: desabilitar rota/action `nfe_complementary_price_quantity_issue`; documentos complementares emitidos seguem consultaveis por `FiscalDocument`.

### Fase 2.2C - Nota de ajuste

- Escopo: NF-e de ajuste fiscal com `operacao`, `natureza_operacao`, `codigo_cfop`, `valor_icms`, `ambiente` e `cliente`.
- Dependencias: autorizacao explicita da subfase e revisao fiscal do payload.
- Modelagem necessaria: `FiscalDocument(kind="nfe", purpose="adjustment")`; `FiscalDocumentLink` opcional, usado somente quando houver relacao de negocio real ou exigencia futura confirmada.
- Endpoint Webmania: `POST /1/nfe/ajuste/`.
- Regime tributario: emissao permitida somente para Lucro Real/Normal ou Lucro Presumido configurado em `WebmaniaCompany.regime_tributario`; Simples Nacional, MEI e valor desconhecido bloqueiam antes do gateway.
- Excecao SC/ES: estorno de SC/ES com finalidade de ajuste deve usar fluxo de devolucao/estorno por `/1/nfe/devolucao/`, nao o endpoint de ajuste.
- Testes obrigatorios: ajuste sem original permitido; ajuste com original opcional; timeout `uncertain`; concorrencia nao duplica; permissao restrita; payload sanitizado.
- Rollback: desabilitar action ajuste sem afetar devolucao/complementar.
- Status: validada em 2026-05-28; Fase 2.2B.1 validada no checkpoint `5faacd9c05960c153eaf69d239bf885da9985df7`. Implementacao limitada a ajuste com regime tributario local validado, link opcional, webhook/reconciliacao sem emissao e sem iniciar complementar tributaria, NFC-e, manifestacao, IBS/CBS ou credito/debito.

### Fase 2.3 - NFC-e

- Escopo: emissao NFC-e pela API v1, separada de NF-e, com configuracao por oficina.
- Dependencias: Fase 2.3.0 documental aprovada, nucleo fiscal minimo validado e configuracao NFC-e da oficina revisada.
- Modelagem necessaria: `FiscalDocument(document_type="nfce", purpose="normal")`, tentativa `operation_type="nfce_emission"` por documento local, configuracao NFC-e via `WebmaniaCompany`.
- Endpoints Webmania: `POST /1/nfe/emissao/` com `modelo=2`; `PUT /1/nfe/cancelar/`; `GET /1/nfe/consulta/`; `PUT /1/nfe/inutilizar/` com `modelo=2` se aprovado; downloads por URLs retornadas.
- Arquivos previstos: `apps/finance/models/finance.py`, migration de choices/permissoes se necessario, `apps/finance/services/nfce_emission.py`, extensoes controladas em `webmania_webhooks.py` e `reconcile_webmania_documents.py`, views/URLs/templates de NFC-e, forms de emissao, testes finance, docs.
- Alteracoes permitidas na primeira subfase funcional: emissao NFC-e normal, consulta/reconciliacao, webhook, downloads e UI minima.
- Alteracoes proibidas na primeira subfase funcional: contingencia/offline, cancelamento por substituicao, PDV completo, TEF/SAT/MFE, manifestacao, IBS/CBS, credito/debito e complementar tributaria.
- Testes obrigatorios: oficina sem NFC-e bloqueia; ambiente exige campos corretos de serie/numero/CSC; emissao mockada com `modelo=2`; concorrencia da mesma intencao gera uma chamada; timeout `uncertain`; webhook `modelo=nfce` nao atualiza NF-e; reconciliacao consulta sem emitir; permissao; cross-workshop; downloads; payload/log sanitizados; separacao NF-e/NFC-e na UI.
- Riscos: contingencia/offline, CSC/token, numeracao por ambiente, consumidor/pagamento, impressao DANFE NFC-e, cancelamento por substituicao ainda pendente de confirmacao operacional.
- Rollback: desabilitar action NFC-e e manter documentos ja emitidos consultaveis; nao afetar NF-e.
- Status: Fase 2.3.0 documentada em 2026-05-29; Fase 2.3.1 validada para emissao manual simples de NFC-e com `FiscalDocument(document_type="nfce")`, `WebmaniaCompany.nfce_enabled`, CSC/ID CSC protegidos como segredos, tentativa `nfce_emission`, webhook/reconciliacao e UI minima. Fase 2.3.2 validada para cancelamento padrao com evento `cancellation`, tentativa `nfce_cancellation`, webhook/reconciliacao sem reenvio e XML de cancelamento protegido. Fase 2.3.3 validada no checkpoint `08b9bf2e` para inutilizacao de numeracao NFC-e. O ciclo simples NFC-e esta concluido com emissao manual, cancelamento padrao e inutilizacao; substituicao, contingencia/offline, inutilizacao funcional de NF-e, PDV/TEF/SAT/MFE e demais operacoes nao foram iniciadas.

### Fase 2.3.2 - Cancelamento padrao NFC-e

- Escopo: cancelamento padrao de NFC-e autorizada via `PUT /1/nfe/cancelar/`.
- Body permitido: `chave` ou `uuid`, `motivo`.
- Campo proibido: `nfce_referenciada`, pois ativa cancelamento por substituicao e permanece fora de escopo.
- Modelagem: reutilizar `FiscalDocument(document_type="nfce", purpose="normal")`; registrar `FiscalDocumentEvent(event_type="cancellation")`; tentativa `operation_type="nfce_cancellation"`.
- Alteracoes proibidas: cancelamento por substituicao, contingencia/offline, inutilizacao, PDV/TEF/SAT/MFE, manifestacao, IBS/CBS, credito/debito e complementar tributaria.
- Testes obrigatorios: elegibilidade, motivo 15-255, body sem `nfce_referenciada`, idempotencia, concorrencia, `uncertain`, webhook/reconciliacao, permissao `cancel_nfce`, cross-workshop e downloads.
- Status: validada em 2026-05-29. Implementacao limitada a cancelamento padrao; nao envia `nfce_referenciada`; nao implementa substituicao, contingencia/offline, inutilizacao ou PDV.

### Fase 2.3.3 - Inutilizacao de numeracao NFC-e

- Escopo: inutilizacao manual de numero ou intervalo de numeracao NFC-e pelo endpoint `PUT /1/nfe/inutilizar/`, sempre com `modelo=2`.
- Dependencias: Fase 2.3.2 validada no checkpoint `a4ae87f7e3f4748369d0d68a90d30e21a0a3d71b`; configuracao NFC-e por oficina validada em `WebmaniaCompany`.
- Modelagem necessaria: entidade propria `FiscalNumberInutilization` para faixa inutilizada, sem associar a `FiscalDocumentEvent` de NFC-e existente; tentativa `FiscalEmissionAttempt(operation_type="nfce_inutilization")`.
- Endpoints Webmania: `PUT /1/nfe/inutilizar/` com `sequencia`, `motivo`, `ambiente`, `serie`, `modelo=2`.
- Observacao oficial: a secao textual da Webmania descreve inutilizacao de numero de NF-e, mas o contrato da mesma secao aceita `modelo=1` para NF-e e `modelo=2` para NFC-e. Esta fase implementa somente `modelo=2`; NF-e permanece apenas possibilidade arquitetural futura.
- Alteracoes permitidas: modelo minimo, migration, service, views/URLs/templates minimos, permissoes, testes, docs e extensao de idempotencia para inutilizacao NFC-e.
- Alteracoes proibidas: cancelamento por substituicao, contingencia/offline, inutilizacao funcional de NF-e, PDV/TEF/SAT/MFE, manifestacao, IBS/CBS, credito/debito, complementar tributaria e demais documentos.
- Testes obrigatorios: body fixo com `modelo=2`; motivo/serie/ambiente/faixa validos; bloqueio de faixa com NFC-e local conhecida; bloqueio de sobreposicao ativa ou `uncertain`; concorrencia; timeout `uncertain`; permissao; cross-workshop; payload/log sanitizados; nenhuma alteracao em `NfeItem` ou NFC-e emitida.
- Riscos: a validacao local cobre apenas documentos/faixas conhecidos pelo Hunter; numeros usados fora do Hunter ou no painel Webmania so sao confirmados pela resposta remota/SEFAZ.
- Rollback: desabilitar action de inutilizacao e preservar registros ja criados para auditoria; nao afeta emissao ou cancelamento NFC-e.
- Status: validada em 2026-05-29. A implementacao adiciona entidade propria, idempotencia persistida, bloqueio de faixa local, permissao especifica e UI minima. Nao implementa webhook/reconciliacao remota para inutilizacao por ausencia de contrato oficial confirmado.

### Fase 2.4 - Conformidade IBS/CBS NF-e/NFC-e

- Escopo: adequar NF-e/NFC-e existentes a IBS/CBS antes de eventos avancados, credito/debito ou complementar tributaria.
- Dependencias: Fase 2.3.3 validada e Fase 2.5.0 documental aprovada com decisao de adiar credito/debito.
- Status: Fase 2.4.0 aprovada documentalmente; Fase 2.4A+B implementada e validada em conjunto para classe fiscal NF-e, NF-e normal e NFC-e manual simples.

#### Fase 2.4.0 - Auditoria e planejamento tecnico IBS/CBS

- Alteracoes permitidas: somente `docs/fiscal-webmania/**` e OpenAPI validado.
- Alteracoes proibidas: codigo funcional, migrations, services, views, templates e testes.
- Aceite: diagnostico de conformidade dos fluxos atuais, matriz de risco, subfases 2.4A-2.4E, ADRs e bloqueio seguro documentados.
- Status: aprovada documentalmente.

#### Fase 2.4A - Base IBS/CBS em classes fiscais e produtos

- Objetivo: modelar e configurar IBS/CBS local para NF-e/NFC-e.
- Dependencias: Fase 2.4.0 aprovada.
- Arquivos implementados: `apps/finance/models/finance.py`, migration `0049`, `apps/finance/services/ibs_cbs.py`, `apps/finance/services/tax_classes.py`, `apps/finance/forms/tax_class.py`, `apps/finance/views/tax_class.py`, `apps/finance/tests.py`, docs.
- Alteracoes permitidas: campos/modelos de configuracao IBS/CBS, serializacao para classe de imposto, validadores e bloqueio seguro antes do gateway.
- Alteracoes proibidas: emitir eventos IBS/CBS, credito/debito, complementar tributaria ou alterar endpoints de emissao sem gate.
- Testes: classe fiscal com IBS/CBS, validacao de situacao/classificacao, permissao administrativa, cross-workshop, sanitizacao, bloqueio quando ausente.
- Rollback: desabilitar uso da configuracao nova e manter classes antigas; dados novos permanecem auditaveis.
- Status: validada em conjunto com 2.4B.

#### Fase 2.4B - Emissao NF-e/NFC-e normal conforme IBS/CBS

- Objetivo: adequar NF-e e NFC-e normais ao uso de classe fiscal IBS/CBS-ready, preservando coexistencia com tributos antigos no cadastro da classe.
- Dependencias: Fase 2.4A implementada em conjunto.
- Arquivos implementados: services `nfe_emission.py`, `nfce_emission.py`, validador `ibs_cbs.py`, testes de bloqueio/payload por `classe_imposto`, docs.
- Alteracoes permitidas: classe fiscal validada com `ibs_cbs`; bloqueio antes do gateway sem configuracao; payload de emissao continua usando `classe_imposto`.
- Alteracoes proibidas: credito/debito e eventos IBS/CBS.
- Testes: producao/homologacao bloqueiam sem classe IBS/CBS-ready; sincronizacao de classe envia `ibs_cbs`; NF-e/NFC-e normais preservam idempotencia; NFC-e nao expõe CSC.
- Rollback: feature flag/gate fiscal para desativar emissao com IBS/CBS sem reemitir documentos.
- Status: validada em conjunto com 2.4A.

#### Fase 2.4C - Documentos derivados ja implementados

- Objetivo: revisar devolucao/estorno, complementar preco/quantidade e ajuste com regras IBS/CBS especificas por operacao.
- Dependencias: Fase 2.4B validada.
- Arquivos previstos: `nfe_returns.py`, `nfe_complementary.py`, `nfe_adjustment.py`, validadores por operacao, testes, docs.
- Alteracoes permitidas: payloads IBS/CBS aplicaveis, bloqueios por operacao, snapshots tributarios.
- Alteracoes proibidas: complementar tributaria geral sem autorizacao propria.
- Testes: cada derivado com e sem IBS/CBS conforme regra, `uncertain` preservando payload, original nao alterado.

##### Fase 2.4C.0 - Planejamento tecnico documental

- Status: em planejamento documental.
- Escopo: auditar os services `nfe_returns.py`, `nfe_complementary.py` e `nfe_adjustment.py`; decidir snapshot original, NF-e externa e bloqueios seguros.
- Alteracoes permitidas: somente `docs/fiscal-webmania/**` e OpenAPI validado se houver correcao oficial.
- Aceite: matriz de risco por derivado, subfases 2.4C.1 a 2.4C.3, testes planejados e ADRs atualizados.

##### Fase 2.4C.1 - Devolucao e estorno com IBS/CBS

- Status: validada em 2026-06-02.
- Escopo implementado: adequar `POST /1/nfe/devolucao/` para devolucao total/parcial e estorno quando a operacao exigir IBS/CBS.
- Dependencias: Fase 2.4A+B validada e snapshot fiscal original disponivel.
- Modelagem: reusar `FiscalDocument(purpose=return|reversal)`, `FiscalDocumentLink(role=returns|reverses)` e `FiscalEmissionAttempt(operation_type=return|reversal)`.
- Criterios de aceite: parcial usa sequenciais fiscais e quantidades alinhadas; IBS/CBS vem do snapshot original ou bloqueia; NF-e externa minima nao permite parcial; estorno usa payload proprio; original nao altera status.
- Rollback: desabilitar gate IBS/CBS de derivados e manter documentos existentes consultaveis.
- Arquivos alterados: `apps/finance/services/nfe_returns.py`, `apps/finance/tests.py` e docs. Sem migration.
- Validacao: 100 testes direcionados das fases fiscais 1, 2.1, 2.2A, 2.2B.1, 2.2C, 2.3.1, 2.3.2, 2.3.3, 2.4A+B e 2.4C.1 passaram com `--keepdb`; `makemigrations finance --check --dry-run`, `ruff check` nos Python tocados e `git diff --check` passaram.

##### Fase 2.4C.2 - Complementar preco/quantidade com IBS/CBS

- Status: validada em 2026-06-02.
- Escopo implementado: permitir IBS/CBS somente no complemento de preco/quantidade local ja validado.
- Dependencias: snapshot fiscal original local e Fase 2.2B.1 validada; 2.4C.1 recomendada antes para consolidar regra de snapshot.
- Modelagem: reusar `FiscalDocument(purpose=complementary, complementary_type=price_quantity)`, link `complements` e tentativa `complementary_price_quantity`.
- Criterios de aceite: produto complementar envia apenas acrescimo; nao copia valores originais; IBS/CBS aplica ao acrescimo por `produtos[].impostos.ibs_cbs`; `base_calculo` e obrigatorio no snapshot usado para complementar; `TaxClassNfe` atual nao e fallback automatico; complementar tributaria, ICMS-ST, IPI, ISSQN, importacao e IBS/CBS amplo continuam fora de escopo.
- Rollback: bloquear complementar IBS/CBS e preservar complementar sem IBS/CBS ja emitida.
- Arquivos alterados: `apps/finance/services/nfe_complementary.py`, `apps/finance/tests.py` e docs. Sem migration.
- Validacao: `makemigrations finance --check --dry-run`, 105 testes direcionados fiscais com `--keepdb`, `ruff check` nos Python tocados e `git diff --check` passaram.

##### Fase 2.4C.3 - Ajuste frente a Reforma Tributaria

- Status: validada em 2026-06-02.
- Escopo: revisar `POST /1/nfe/ajuste/` diante de IBS/CBS sem presumir produtos.
- Dependencias: revalidacao oficial do contrato de ajuste e regime tributario local configurado.
- Modelagem: manter `FiscalDocument(purpose=adjustment, origin=manual)` e link `adjusts` opcional.
- Criterios de aceite: ajuste continua sem documento original obrigatorio; nao envia produtos/IBS-CBS sem contrato oficial; bloqueia tentativa de usar ajuste como credito/debito, evento IBS/CBS ou estorno; estorno SC/ES continua no fluxo de devolucao.
- Rollback: manter ajuste ICMS/ICMS-ST validado e bloquear qualquer ampliacao IBS/CBS.
- Arquivos alterados: `apps/finance/services/nfe_adjustment.py`, `apps/finance/templates/finance/nfe_request_detail.html`, `apps/finance/tests.py` e docs. Sem migration.
- Validacao: `makemigrations finance --check --dry-run`, 145 testes direcionados fiscais com `--keepdb`, `ruff check` nos Python tocados e `git diff --check` passaram.

#### Fase 2.4D - Eventos IBS/CBS

- Objetivo: planejar e implementar `/1/nfe/evento-ibs-cbs/` e cancelamento de evento depois da base conformada.
- Dependencias: Fase 2.4B e decisoes de evento aprovadas.
- Modelagem necessaria: `FiscalDocumentEvent` com codigo de evento, sequencia, autor, status remoto e vinculo com evento original para cancelamento.
- Testes: evento autorizado, duplicidade, fora de ordem, cancelamento referencia evento original, permissao restrita e payload sanitizado.

##### Fase 2.4D.0 - Planejamento tecnico documental dos eventos IBS/CBS

- Status: documentada em 2026-06-02.
- Escopo: validar contrato oficial `POST /1/nfe/evento-ibs-cbs/`, `PUT /1/nfe/evento-ibs-cbs/cancelar/`, codigos oficiais, modelagem, idempotencia, webhook, permissoes, UI minima e testes.
- Alteracoes permitidas: somente `docs/fiscal-webmania/**` e OpenAPI validado.
- Alteracoes proibidas: qualquer codigo funcional, migration, service, view, form, template ou teste.
- Aceite: matriz completa de codigos, decisao de `FiscalDocumentEvent`, subfases funcionais e recomendacao de primeira entrega.

Subfases funcionais recomendadas:

| Subfase | Escopo | Dependencia | Risco |
| ------- | ------ | ----------- | ----- |
| 2.4D.1 | Evento `112110` em NF-e/NFC-e normal local autorizada | 2.4D.0 aprovada | Baixo/medio; sem campos especificos, mas exige sequencia/idempotencia. |
| 2.4D.2 | Cancelamento do evento `112110` | 2.4D.1 validada e evento autorizado com UUID remoto | Medio; nao pode cancelar documento base por engano. |
| 2.4D.3 | Evento `112150` - data de previsao de entrega | Validada | Baixo/medio; payload estreito; cancelamento do 112150 segue fora do escopo. |
| 2.4D.4 | Cancelamento do evento `112150` | Validada | Baixo; reutiliza cancelamento por UUID, sem generalizar demais codigos. |
| 2.4D.5.0 | Planejamento dos eventos de emitente com itens/controle: `112120`, `112130`, `112140` | Aprovada documentalmente | Medio/alto; definir fontes de snapshot, itens e bloqueios antes de codigo. |
| 2.4D.5.1 | Evento `112130` isolado | Validada | Medio/alto; estorno IBS/CBS e perecimento/perda/roubo/furto em transporte contratado pelo fornecedor. |
| 2.4D.5.2 | Cancelamento do evento `112130` | Validada | Medio; reutiliza cancelamento por UUID sem generalizar demais codigos. |
| 2.4D.6.0 | Planejamento final dos eventos `112120` e `112140` | Aprovada | Alto; decisao aprovada de adiar ambos e exigir fase preparatoria. |
| 2.4D.6.P | Fase preparatoria para `112120/112140` | 2.4D.6.0 aprovada e escopo autorizado | Alto; importacao XML/snapshot fiscal, ALC/ZFM, credito/debito ou pagamento antecipado. |
| 2.4D.6.1 | Evento `112120` isolado | Fase preparatoria validada e contexto ALC/ZFM comprovado | Alto; importacao/beneficio fiscal com baixa aderencia oficina. |
| 2.4D.6.2 | Evento `112140` isolado | Fase preparatoria validada e nota de debito/pagamento antecipado definidos | Alto; depende de pagamento antecipado/nota de debito. |
| 2.4D.6.3 | Cancelamento dos eventos `112120/112140` e futuros cancelamentos pontuais | Evento correspondente validado e autorizado com UUID remoto | Medio/alto; nao generalizar sem testes por codigo. |
| 2.4D.7 | Eventos de destinatario: `211110`, `211120`, `211124`, `211130`, `211140`, `211150` | Decisao de papel destinatario e permissao | Alto; papel fiscal diferente e referencias externas. |
| 2.4D.8 | Evento `211128` e relacao com credito/debito | 2.4E/2.5 funcional aprovada | Alto; depende de nota de credito/debito. |
| 2.4D.9 | Cancelamento dos demais eventos IBS/CBS | Eventos correspondentes autorizados com UUID remoto | Medio/alto; cada codigo pode ter regra propria de reversao. |

##### Fase 2.4D.1 - Evento IBS/CBS 112110

- Status: validada em 2026-06-02.
- Escopo implementado: `POST /1/nfe/evento-ibs-cbs/` somente para `cod_evento=112110`.
- Modelagem: `FiscalDocumentEvent(event_type="ibs_cbs", event_code="112110")` vinculado ao `FiscalDocument` base; nao cria `FiscalDocument`.
- Tentativa: `FiscalEmissionAttempt(operation_type="nfe_ibs_cbs_event")`.
- Payload: apenas `chave`, `ambiente`, `cod_evento`, `evento` e `url_notificacao` quando disponivel.
- Aceite validado: uma chamada remota por intencao, timeout vira `uncertain`, webhook idempotente, ambiguidade sem update, permissoes especificas, download/payload protegidos e documento base sem alteracao de status.
- Fora do escopo: cancelamento do evento, demais codigos IBS/CBS, credito/debito, complementar tributaria, NFS-e e CT-e.

##### Fase 2.4D.2 - Cancelamento do Evento IBS/CBS 112110

- Escopo implementado: `PUT /1/nfe/evento-ibs-cbs/cancelar/` somente para cancelamento de evento `112110` ja autorizado.
- Modelagem: `FiscalDocumentEvent(event_type="ibs_cbs_cancellation")` vinculado ao evento original por `related_event`; nao cria documento fiscal nem `FiscalDocumentLink`.
- Payload autorizado: `uuid` do evento original, `ambiente` opcional e `url_notificacao` quando aplicavel.
- Campo proibido: `chave`, `cod_evento`, `evento`, `ibs_cbs`, produtos, credito/debito, complementar tributaria ou payload da NF-e/NFC-e.
- Aceite validado: uma chamada remota por intencao, timeout vira `uncertain`, duplicidade bloqueada, webhook idempotente, ambiguidade sem update, permissao `cancel_ibs_cbs_event`, download/payload protegidos e documento base sem alteracao de status.
- Fora do escopo: demais cancelamentos de eventos IBS/CBS, outros codigos, credito/debito, complementar tributaria, NFS-e, CT-e e qualquer evento que exija itens/campos especificos.

##### Fase 2.4D.3.0 - Priorizacao dos demais Eventos IBS/CBS

- Status: documentada em 2026-06-18, aguardando aprovacao.
- Escopo: revalidar eventos `112120`, `112130`, `112140`, `112150`, `211110`, `211120`, `211124`, `211128`, `211130`, `211140` e `211150` sem alterar codigo funcional.
- Decisao: a proxima subfase funcional recomendada e `2.4D.3 - Implementar somente evento IBS/CBS 112150`.
- Justificativa: `112150` tem payload especifico minimo (`data_previsao_entrega`), nao depende de credito/debito, nao exige `itens[]`, nao exige papel de destinatario e reaproveita a infraestrutura `112110`.
- Bloqueios: `112120`, `112130` e `112140` exigem itens/valores/controle e devem ficar para subfases separadas; `211128` depende de credito/debito; eventos `211xxx` restantes dependem de papel destinatario/apuracao externa.
- Cancelamento: nao generalizar o cancelamento 2.4D.2 para todos os codigos sem decisao explicita. Para `112150`, cancelar deve ser subfase posterior ou criterio adicional aprovado separadamente.

##### Fase 2.4D.3 - Evento IBS/CBS 112150

- Status: validada.
- Escopo entregue: `POST /1/nfe/evento-ibs-cbs/` somente com `cod_evento=112150`, para NF-e normal local autorizada.
- Criterios aceitos: payload com `chave`, `ambiente`, `cod_evento`, `evento`, `data_previsao_entrega` e `url_notificacao` opcional; sem `ibs_cbs`, `itens`, `produtos`, credito/debito ou cancelamento; idempotencia persistida por evento/tentativa; webhook idempotente; tenancy e permissoes mantidas.
- Fora de escopo confirmado: NFC-e, derivados, ajuste, cancelamento do `112150`, eventos `112120/112130/112140`, eventos `211xxx`, credito/debito, complementar tributaria, NFS-e e CT-e.

##### Fase 2.4D.4 - Cancelamento do Evento IBS/CBS 112150

- Status: validada.
- Escopo entregue: `PUT /1/nfe/evento-ibs-cbs/cancelar/` somente para evento `112150` autorizado com UUID remoto.
- Criterios aceitos: payload somente com `uuid`, `ambiente` e `url_notificacao` quando aplicavel; sem `chave`, `cod_evento`, `evento`, `data_previsao_entrega`, `ibs_cbs`, produtos ou payload de nota; cancelamento modelado como `FiscalDocumentEvent(event_type=ibs_cbs_cancellation, event_code=112150)` vinculado ao evento original; tentativa `nfe_ibs_cbs_event_cancellation`; webhook idempotente; tenancy e permissoes mantidas.
- Fora de escopo confirmado: cancelamento generico, eventos `112120/112130/112140`, eventos `211xxx`, credito/debito, complementar tributaria, NFS-e e CT-e.

##### Fase 2.4D.5.0 - Planejamento dos Eventos IBS/CBS 112120, 112130 e 112140

- Status: aprovada documentalmente em 2026-06-18.
- Escopo: revalidar oficialmente `112120`, `112130` e `112140`; auditar a infraestrutura validada de `112110/112150`; definir fontes locais, bloqueios, idempotencia, UI, permissao, testes e subfases.
- Alteracoes permitidas: somente `docs/fiscal-webmania/**` e OpenAPI validado quando houver correcao oficial.
- Alteracoes proibidas: codigo funcional, migrations, services, views, forms, templates e testes.
- Decisao de agrupamento: implementar um por vez. Os tres exigem itens e valores IBS/CBS, mas possuem semantica fiscal e fontes operacionais diferentes.
- Fonte local obrigatoria futura: snapshot fiscal do documento original com sequencial fiscal e IBS/CBS por item. `TaxClassNfe` atual nao pode ser fallback automatico para evento de documento ja emitido.
- Bloqueios: documento externo sem XML/importacao validada; documento sem snapshot; item sem sequencial fiscal confiavel; divergencia de itens; valores IBS/CBS incompletos; tentativa de usar evento como credito/debito.
- Cancelamento: subfase separada apos validar emissao de cada codigo; nao criar cancelamento generico.
- Fase 2.4D.5.1 autorizada para implementacao: somente `cod_evento=112130`, com payload oficial de `itens[]`. Eventos `112120`, `112140`, `211xxx`, cancelamento do `112130`, credito/debito e complementar tributaria permanecem bloqueados.

##### Fase 2.4D.5.1 - Evento IBS/CBS 112130

- Status: validada em 2026-06-18.
- Escopo entregue: `POST /1/nfe/evento-ibs-cbs/` somente para `cod_evento=112130`, perecimento, perda, roubo ou furto durante transporte contratado pelo fornecedor.
- Payload oficial confirmado: envelope `chave`, `ambiente`, `cod_evento`, `evento`, `url_notificacao` opcional e `itens[]` com `item`, `valor_ibs`, `valor_cbs` e `controle_estoque.quantidade_perecimento`, `unidade_perecimento`, `valor_ibs_estorno`, `valor_cbs_estorno`.
- Regra de seguranca validada: usar somente NF-e normal local autorizada com snapshot fiscal original contendo sequencial fiscal e IBS/CBS por item; nao usar `TaxClassNfe` atual como fallback automatico.
- Aceite validado: payload sem top-level `ibs_cbs`; bloqueios de documento inelegivel, snapshot ausente e item invalido antes do gateway; duplicidade por payload bloqueada; payload distinto permitido; timeout vira `uncertain`; webhook idempotente; ambiguidade sem update; permissao/download/payload protegidos; documento base sem alteracao de status.
- Fora de escopo: `112120`, `112140`, eventos `211xxx`, cancelamento do `112130`, credito/debito, complementar tributaria, NFS-e e CT-e.

##### Fase 2.4D.5.2 - Cancelamento do Evento IBS/CBS 112130

- Status: validada em 2026-06-18.
- Escopo entregue: `PUT /1/nfe/evento-ibs-cbs/cancelar/` somente para cancelamento de evento `112130` ja autorizado com UUID remoto.
- Payload autorizado: `uuid`, `ambiente` opcional coerente com o documento/evento original e `url_notificacao` quando aplicavel.
- Campos proibidos: `chave`, `cod_evento`, `evento`, `itens`, `ibs_cbs`, produtos, payload de nota fiscal, credito/debito ou complementar tributaria.
- Modelagem: reutilizar `FiscalDocumentEvent(event_type="ibs_cbs_cancellation", event_code="112130", related_event=<112130>)` e `FiscalEmissionAttempt(operation_type="nfe_ibs_cbs_event_cancellation")`; nao criar `FiscalDocument`.
- Aceite validado: uma chamada remota por intencao, timeout vira `uncertain`, duplicidade bloqueada, webhook idempotente, ambiguidade sem update, permissao `cancel_ibs_cbs_event`, download/payload protegidos e documento base sem alteracao de status.
- Fora de escopo: eventos `112120`, `112140`, `211xxx`, cancelamento generico, credito/debito, complementar tributaria, NFS-e e CT-e.

##### Fase 2.4D.6.0 - Planejamento final dos Eventos IBS/CBS 112120 e 112140

- Status: em planejamento documental.
- Escopo: revalidar oficialmente `112120` e `112140`, auditar fontes locais e decidir se algum pode ser implementado agora.
- Resultado recomendado: **adiar ambos** e planejar fase preparatoria.
- `112120`: exige NF-e de importacao referenciada, contexto ALC/ZFM, item sequencial fiscal, valores IBS/CBS e `controle_estoque.quantidade/unidade`. O Hunter ainda nao possui projecao fiscal de XML/importacao com contexto ALC/ZFM para evento.
- `112140`: exige item da nota de debito de pagamento antecipado, valores IBS/CBS e `controle_estoque.quantidade_nao_fornecida/unidade_nao_fornecida`. O Hunter ainda nao possui nota de debito/credito IBS/CBS funcional nem vinculo fiscal item-pagamento antecipado.
- Cancelamento: manter por subfase posterior ao evento correspondente validado; nao generalizar cancelamento por UUID sem emissao/teste do codigo.
- Fora de escopo confirmado: codigo funcional, migrations, services, views, templates, testes, eventos `211xxx`, credito/debito, complementar tributaria, NFS-e e CT-e.

#### Fase 2.4E - Credito e debito

- Objetivo: implementar finalidades 5/6 somente apos base IBS/CBS validada.
- Dependencias: Fase 2.4B validada e decisao 2.5 funcional aprovada.
- Regras: produtos devem enviar somente `impostos.ibs_cbs`; tributos ICMS/ISSQN/IPI/II/PIS/COFINS e correlatos devem ser barrados preventivamente.
- Testes: rejeicao preventiva de tributos incompatíveis, tipos oficiais, `dfe_referenciado` quando aplicavel, idempotencia e feature flag.

### Fase 2.5 - Nota Fiscal de Credito e Nota Fiscal de Debito

- Escopo: NF-e de credito (`finalidade=5`, `tipo_credito`) e NF-e de debito (`finalidade=6`, `tipo_debito`).
- Dependencias: revalidacao oficial da Reforma Tributaria, decisao de produto, feature flag, habilitacao administrativa por oficina e suporte IBS/CBS ou decisao formal de subconjunto seguro.
- Modelagem necessaria: `FiscalDocument(document_type="nfe", purpose="credit")` e `FiscalDocument(document_type="nfe", purpose="debit")`; campo planejado `fiscal_purpose_type`; links `credits`/`debits` opcionais/condicionais conforme tipo e regra oficial.
- Endpoint Webmania: `POST /1/nfe/emissao/`.
- Idempotencia: `FiscalEmissionAttempt(operation_type="nfe_credit_emission")` ou `operation_type="nfe_debit_emission"` associado ao documento local criado antes do gateway.
- Testes obrigatorios: `tipo_credito`/`tipo_debito` obrigatorios; finalidade correta; documento referenciado quando tipo exigir; bloqueio quando IBS/CBS for dependencia nao implementada; timeout `uncertain`; permissao restrita; cross-workshop; webhook/reconciliacao sem emissao; downloads e payload sanitizados.
- Rollback: feature/action desligavel sem afetar NF-e normal.
- Status: Fase 2.5.0 aprovada documentalmente. Recomendacao atual aceita: adiar codigo funcional ate fase IBS/CBS ou aprovacao explicita de subconjunto seguro.

#### Fase 2.5.1.0 - Replanejamento final apos IBS/CBS

- Status: aprovada; decisao de adiar todos os tipos aceita.
- Decisao: adiar credito/debito funcional; nenhum dos 13 tipos possui fonte local fiscal completa.
- Menor subconjunto seguro: nenhum. Multa/juros e o menor contrato remoto, mas o Hunter nao possui multa/juros fiscal IBS/CBS vinculada a item/DF-e.

#### Fase 2.5.1P - Preparacao de fontes fiscais

- Status: validada em 2026-06-19.
- Escopo: preparar base fiscal referenciada auditavel, sem emissao de credito/debito e sem chamada remota de emissao.
- Modelar/importar documento e item fiscal referenciado, snapshot IBS/CBS e evidencia da hipotese legal.
- Criar vinculos auditaveis financeiro -> documento/item e estoque -> documento/item apenas para casos priorizados.
- Definir primeiro tipo de negocio com contador/fiscal e validar payload em homologacao.
- Criterio de aceite: uma fonte local deterministica, permissao, tenancy, rollback e testes de contrato para um unico tipo.
- Resultado: base interna, snapshot imutavel, referencias opcionais, flag e UI administrativa implementados; emissao permanece bloqueada. Hipoteses que exigem financeiro/estoque nao aprovam sem referencia real.

#### Fase 2.5.2 - Primeiro tipo isolado

- Somente depois de 2.5.1P validada e autorizacao explicita.
- Candidato remoto mais simples: multa/juros; nao e candidato funcional enquanto a fonte fiscal permanecer ausente.
- Demais tipos permanecem bloqueados e devem ser liberados individualmente.

#### Fase 2.5.2.0 - Selecao documental

- Status: documentada, aguardando aprovacao.
- Decisao: Opcao D; nenhum tipo sera implementado ainda.
- Justificativa: a base 2.5.1P nao congela os valores comerciais e a composicao monetaria por item exigidos pelo payload.
- Candidato apos preparacao: credito tipo 1, menor que debito tipo 4 por nao exigir `dfe_referenciado` em cada produto.

#### Fase 2.5.2P - Base monetaria por item

- Congelar snapshot comercial, CFOP, quantidade/unidade, principal, multa, juros e total por item.
- Vincular cada parcela ao `FinancialMovement` e ao item fiscal sem inferencia automatica.
- Validar somas, imutabilidade, permissao, tenancy e ausencia de emissao.
- Somente apos validacao permitir solicitar fase funcional de credito tipo 1.

## Fase 3 - Completar NFS-e

- Objetivos: emissao manual, RPS/lote, capacidades municipais, substituicao, manifestacao, agendamento e downloads.
- Dependencias: Fase 1 validada.
- Migrations: capacidades municipais.
- Testes: municipio com/sem recurso, substituicao, cancelamento agendado.
- Status: Fase 3.0 documental em planejamento; nenhuma subfase funcional iniciada.

### Roadmap aprovado para detalhamento na Fase 3.0

| Subfase | Objetivo | Dependencias | Risco | Criterio principal |
| --- | --- | --- | --- | --- |
| 3.1 | Estabilizar legado, operation type, `atualizado_em`, capacidades e feature flag | 3.0 aprovada | Alto | Emissao existente preservada e bloqueada quando capacidade/configuracao forem invalidas |
| 3.2 | Consulta e reconciliacao de item/lote por UUID | 3.1 | Medio | Nenhum caminho de reconciliacao transmite operacao mutavel |
| 3.3 | Cancelamento idempotente | 3.1/3.2 | Alto | Tentativa antes do PUT, timeout `uncertain`, status apenas com confirmacao valida |
| 3.4 | Substituicao | 3.1-3.3 | Alto | Novo documento/link auditavel, capacidade municipal e uma chamada por intencao |
| 3.5.0 | Reavaliacao apos NFS-e legada | 3.1-3.4.1 | Medio | Proximo bloco escolhido sem codigo funcional |
| 3.6.0 | Planejamento da manifestacao Padrao Nacional | 3.5.0 | Medio/alto | Papel/evento/rejeicao, elegibilidade e idempotencia documentados |
| 3.6.x | Manifestacao Padrao Nacional funcional | 3.6.0 aprovada | Medio/alto | Documento original preservado e webhook/reconciliacao sem ambiguidade |
| 3.7 | Rollout municipal e emissao manual | 3.6.x | Alto | Flags por oficina/municipio, sem request legado paralelo |
| 3.8 | Downloads e observabilidade | transversal | Medio | XML/PDF/RPS protegidos, logs sanitizados e metricas operacionais |

Agendamento deve ser planejado como extensao posterior de 3.3/rollout municipal. Lote RPS nao e subfase isolada: faz parte da estabilizacao e reconciliacao porque ja existe no legado.

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

## Fase 7 - DC-e v2.0.0 com rollout interno controlado

- Objetivos: feature flag interna, emissao, consulta, cancelamento e rollout controlado.
- Dependencias: habilitacao administrativa por oficina.
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
## Fase 2.5.2P - Base monetaria e comercial por item

Status: implementada e validada em 2026-06-19. A Fase 2.5.2.0 foi aprovada com decisao de nao emitir credito/debito ainda.

Escopo: criar snapshot imutavel por item fiscal com sequencial, descricao, codigo, NCM, CFOP, quantidade, unidade, valor unitario, total original e composicao explicita de principal, multa, juros e outros. Para hipoteses de multa/juros, a base futura e `multa + juros`; para as demais, `principal + multa + juros + outros`. A movimentacao financeira e somente evidencia e nao preenche valores automaticamente.

Criterios: permitir rascunho incompleto, bloquear aprovacao sem fonte comercial historica completa ou composicao valida, manter feature flag/permissoes existentes, impedir alteracao apos aprovacao e provar ausencia de `FiscalDocument`, `FiscalEmissionAttempt` e chamada Webmania de credito/debito.
## Fase 2.5.3.0 - Planejamento final credito tipo 1

Status: documentada em 2026-06-22, aguardando aprovacao. A Fase 2.5.2P foi validada no checkpoint `638d4c12`.

Decisao: adiar a emissao funcional. A base local atende identidade, snapshot, valores e imutabilidade, mas o contrato consultado nao define com seguranca a valoracao de `produtos[]` para multa/juros nem os valores IBS/CBS correspondentes.

Proxima fase recomendada: `2.5.3P - Validacao fiscal do produto de multa/juros`, exclusivamente documental/configuracional e sem transmissao. Criterios: confirmar modelo operacional (`1` versus `"nfe"`), CFOP, descricao/NCM/unidade, quantidade, subtotal, total, regra IBS/CBS, cliente/pedido e evidencias exigidas. Somente depois uma `2.5.3.1` funcional podera ser autorizada.
## Fase 2.5.3P - Validacao fiscal do produto multa/juros

Status: em implementacao controlada. Opcao A aprovada tecnicamente para a previa: quantidade, valor unitario, total e CFOP sao informados explicitamente por usuario autorizado; nenhuma regra e inferida. A aprovacao exige `quantidade x unitario = total` dentro de R$ 0,01 e `total = multa + juros`, com IBS/CBS vindo somente do snapshot aprovado.

Esta fase nao cria documento fiscal, tentativa remota, gateway ou botao de emissao.

Resultado: implementada e validada em 2026-06-22 com model local, valores explicitos, revisao, validacao, aprovacao imutavel, UI minima e permissoes proprias. A regressao fiscal completa passou antes do checkpoint.

## Fase 2.5.4 - Emissao NF-e de credito tipo 1 por multa/juros

Status: implementada e validada tecnicamente em 2026-06-22, apos validacao da Fase 2.5.3P no checkpoint `0d95a026`.

Escopo: emitir exclusivamente `modelo=1`, `finalidade=5`, `tipo_credito=1` por `POST /1/nfe/emissao/`, consumindo uma unica `FiscalCreditProductPreview` aprovada. O documento local deve ser criado antes do gateway, ligado a base fiscal e a NF-e original, protegido por tentativa `nfe_credit_emission` e atualizado por webhook/reconciliacao sem alterar origem, base ou preview.

Bloqueios: debito; credito tipos 2-5; cancelamento de credito; eventos `112120`, `112140` e `211xxx`; complementar tributaria; NFS-e; CT-e; e demais familias.

Criterios de aceite: payload contem somente IBS/CBS nos produtos; idempotencia persistida gera uma chamada por preview; timeout resulta em `uncertain`; permissoes e oficina sao validadas antes do gateway; XML/DANFE e payload ficam protegidos; webhook/reconciliacao atingem somente o documento de credito; testes direcionados, Ruff, migrations e diff check passam.

## Fase 2.5.5 - Cancelamento NF-e de credito tipo 1

Status: implementada e validada tecnicamente em 2026-06-22, apos validacao da Fase 2.5.4 no checkpoint `a79f6b7f`.

Escopo: cancelar somente `FiscalDocument(document_type="nfe", purpose="credit", fiscal_purpose_type="1")` autorizado, por `PUT /1/nfe/cancelar/`, com chave ou UUID e motivo entre 15 e 255 caracteres. O contrato oficial nao inclui `ambiente` no body; o ambiente permanece auditado localmente. O cancelamento e evento do documento, nao evento IBS/CBS.

Bloqueios: debito, credito tipos 2-5, novos tipos de emissao, `112120`, `112140`, eventos `211xxx`, complementar tributaria e demais familias fiscais.

## Fase 2.5.6.0 - Reavaliacao do proximo bloco

Status: aprovada em 2026-06-22. A Fase 2.5.5 foi validada no checkpoint `5d612544` e encerrou o ciclo do credito tipo 1.

### Decisao recomendada

Escolher **Opcao E - nova fase preparatoria**: `Fase 2.5.6P - Preview fiscal de debito tipo 4 (multa/juros), sem transmissao`.

Justificativa: debito tipo 4 e o candidato funcional com maior reaproveitamento, pois o contrato exige `dfe_referenciado` por item e a base atual ja possui chave, sequencial, snapshots IBS/CBS, comercial/monetario e multa+juros. Entretanto, nao e seguro reaproveitar diretamente a preview de credito: finalidade, tipo, CFOP, produto e intencao fiscal precisam ser aprovados como debito.

### Escopo proposto para 2.5.6P

- model irmao `FiscalDebitProductPreview`, ou equivalente explicitamente restrito a `finalidade=6`/`tipo_debito=4`;
- nenhuma chamada Webmania, `FiscalDocument` ou `FiscalEmissionAttempt`;
- fonte exclusiva em base/item aprovados da mesma oficina;
- congelamento de `dfe_referenciado`, produto, CFOP, valores e IBS/CBS;
- feature flag administrativa para preparacao de debito e permissoes separadas;
- UI administrativa de preparar, revisar e aprovar sem botao de emissao;
- bloqueio de tributos tradicionais, valores nao positivos, snapshots ausentes, cross-workshop e fallback atual.

### Criterios de aceite propostos

1. Preview registra `finalidade=6`, `tipo_debito=4` e `dfe_referenciado` por item sem transmitir.
2. Base e item precisam estar aprovados e congelados.
3. Multa + juros, produto, quantidade, valor unitario, total, CFOP e IBS/CBS devem ser coerentes e auditaveis.
4. Payload aprovado e imutavel e contem somente IBS/CBS.
5. Nao cria documento, tentativa, webhook, reconciliacao ou download fiscal remoto.
6. Permissoes e feature flag nao liberam emissao.
7. Demais tipos, eventos, NFS-e e CT-e continuam bloqueados.

Uma futura `2.5.7` podera planejar a emissao do debito tipo 4; cancelamento ficara em subfase posterior independente.

## Fase 2.5.6P - Preview fiscal de debito tipo 4

Status: implementada e validada tecnicamente em 2026-06-22, aguardando checkpoint.

Escopo autorizado: modelagem, validacao e UI administrativa de preview propria para `finalidade=6`, `tipo_debito=4`, com `dfe_referenciado` obrigatorio e sem transmissao. Reutiliza a flag preparatoria geral existente, mas cria permissoes distintas das de credito. Emissao, documento fiscal de debito, tentativa remota, webhook, reconciliacao e cancelamento permanecem bloqueados.

Resultado: criterios atendidos por `FiscalDebitProductPreview`, migration `0057`, service local, UI e 14 testes novos. A regressao fiscal dirigida passou com 260 testes.

## Fase 2.5.7.0 - Planejamento final da emissao de debito tipo 4

Status: aprovada em 2026-06-22. A Fase 2.5.6P foi validada no checkpoint `189bf973`.

### Matriz de pre-condicoes

| Pre-condicao | Fonte atual | Existe? | Bloqueio se ausente? | Observacao |
| --- | --- | ---: | ---: | --- |
| Base aprovada | `FiscalReferencedBasis` | Sim | Sim | Hipotese `debit_fine_interest` |
| Item aprovado/congelado | `FiscalReferencedBasisItem` | Sim | Sim | Imutavel com base aprovada |
| Preview aprovada | `FiscalDebitProductPreview` | Sim | Sim | Intencao exclusiva tipo 4 |
| Chave original | Base/preview | Sim | Sim | 44 digitos |
| `dfe_referenciado` | Preview/produto | Sim | Sim | Chave e item por produto |
| Sequencial fiscal | Base/item/preview | Sim | Sim | 1 a 999 |
| Snapshot IBS/CBS | Base/preview | Sim | Sim | Sem recalcule/fallback |
| Snapshot comercial | Item/preview | Sim | Sim | Descricao, codigo, NCM, unidade |
| Snapshot monetario | Item/preview | Sim | Sim | Multa e juros auditaveis |
| CFOP | Preview | Sim | Sim | Na raiz do produto |
| Quantidade fiscal | Preview | Sim | Sim | Valor explicito |
| Valor unitario fiscal | Preview | Sim | Sim | Valor explicito |
| Valor total fiscal | Preview | Sim | Sim | Fecha com quantidade x unitario |
| Multa | Item | Sim | Sim | Nao negativa |
| Juros | Item | Sim | Sim | Nao negativo |
| Base multa + juros | Item/preview | Sim | Sim | Deve ser positiva e igual ao total |
| Feature flag de emissao | Ainda nao existe | Nao | Sim | Criar separada da flag preparatoria |
| Permissao `issue_nfe_debit` | Ainda nao existe | Nao | Sim | Criar somente na fase funcional |

### Decisao

Recomendar implementacao funcional como proxima fase, limitada a preview local aprovada. A lacuna restante e deliberadamente de controle de rollout: flag e permissoes de emissao, criadas junto com o documento/tentativa. Nao ha lacuna fiscal de item/payload que exija nova fase preparatoria.

### Escopo proposto

- documento derivado `purpose="debit"`, tipo `4`, link `debits`, preview/base obrigatorias;
- POST unico em `/1/nfe/emissao/`, idempotencia persistida e `uncertain`;
- cliente/pedido derivados da origem operacional local, como no credito tipo 1;
- webhook, reconciliacao, payload e XML/DANFE protegidos;
- sem cancelamento, origem externa, outros tipos ou eventos.

## Fase 2.5.7 - Emissao da NF-e de debito tipo 4

Status: validada tecnicamente em 2026-06-22; checkpoint desta entrega pendente.

Escopo autorizado: somente `modelo=1`, `finalidade=6`, `tipo_debito=4`, origem local, preview/base aprovadas, `dfe_referenciado` por produto e IBS/CBS exclusivo. Cancelamento e qualquer outro tipo permanecem fora do escopo.

Resultado: migration `0058`, service, UI, permissoes, flag, webhook, reconciliacao e downloads implementados. Os 16 testes especificos e o conjunto fiscal dirigido de 276 testes passaram, incluindo concorrencia real, timeout `uncertain`, ambiguidade de webhook e regressao do credito tipo 1.

## Fase 2.5.8 - Cancelamento da NF-e de debito tipo 4

Status: validada tecnicamente em 2026-06-22; checkpoint desta entrega pendente.

Escopo: cancelar somente `FiscalDocument(document_type="nfe", purpose="debit", fiscal_purpose_type="4")` autorizado por `PUT /1/nfe/cancelar/`. O evento/tentativa deve ser persistido antes do gateway, timeout deve resultar em `uncertain`, e webhook/reconciliacao devem atualizar somente o documento de debito. Outros tipos e eventos permanecem bloqueados.

Resultado: migration `0059`, service, UI, webhook, reconciliacao e permissao implementados. Os 10 testes especificos, 51 regressivos de credito/debito e 286 testes fiscais dirigidos passaram, incluindo concorrencia real, timeout, ambiguidade entre credito/debito e protecao cross-workshop.

## Fase 2.6.0 - Reavaliacao do roadmap fiscal

Status: em planejamento documental em 2026-06-23. A Fase 2.5.8 foi validada no checkpoint `df1a163e`.

Decisao: selecionar a Opcao D por meio de uma etapa preparatoria. A proxima fase recomendada e `Fase 3.0 - Auditoria e Planejamento Tecnico da NFS-e Expandida`, sem codigo funcional. NFS-e combina alto valor para oficinas com infraestrutura legada existente; a variacao municipal, o Padrao Nacional e a transicao ISS/IBS-CBS impedem expansao segura sem auditoria previa.

### Escopo proposto da Fase 3.0

- auditar models, services, views, forms, templates, URLs, webhook, reconciliacao, downloads, permissoes e tenancy NFS-e atuais;
- comparar o fluxo com `/2/nfse/emissao`, `/consulta/{identifier}`, `/status`, `/cancelar`, `/substituir` e `/manifestar`;
- mapear RPS/lotes, capacidades municipais/provedor, ISS, IBS/CBS e Padrao Nacional;
- definir compatibilidade do legado, idempotencia persistida, `uncertain`, webhook e reconciliacao sem emissao;
- propor subfases 3.1 estabilizacao/capacidades, 3.2 consulta/reconciliacao, 3.3 cancelamento, 3.4 substituicao, reavaliacao 3.5.0, planejamento 3.6.0 de manifestacao, eventual 3.6.x funcional e fases posteriores para rollout/emissao manual e downloads/observabilidade;
- documentar rollout, rollback, gaps, ADRs e criterios de aceite, sem migrations ou codigo.

### Criterios de aceite da Fase 3.0

1. Inventario as-is NFS-e com evidencias de arquivos e fluxos reais.
2. Matriz endpoint/capacidade municipal/estado local completa.
3. Decisao explicita sobre legado, projecao fiscal e eventual backfill.
4. Contratos de idempotencia, webhook, reconciliacao, tenancy e permissao definidos.
5. Plano de testes, rollout e rollback por subfase.
6. Nenhuma alteracao funcional realizada.

Resultado da auditoria: a primeira fase funcional recomendada e 3.1. Nao iniciar 3.2 ou posteriores automaticamente.

## Fase 3.1 - Estabilizacao NFS-e legado

Status: em implementacao controlada em 2026-06-23.

Escopo: capacidade municipal minima, flag de compatibilidade legada, bloqueios pre-gateway, persistencia/ordenacao por `atualizado_em`, reconciliacao sem operacoes mutaveis e UI administrativa minima. Preservar `NfseRequest`, `NfseBatch`, `NfseItem`, wizard por OS, RPS/lote, tentativa existente e downloads.

Fora do escopo: cancelamento idempotente, substituicao, manifestacao, emissao manual, projecao generalizada `FiscalDocument(nfse)`, backfill e demais familias fiscais.

Status: **validada em 2026-06-23**. Migration `0060_nfsebatch_remote_updated_at_and_more`; 13 testes especificos e 297 testes fiscais direcionados aprovados. `makemigrations finance --check --dry-run`, Ruff nos Python tocados e `git diff --check` aprovados. Nenhuma subfase 3.2+ foi iniciada.

## Fase 3.2 - Consulta e reconciliacao NFS-e ampliada

Status: **validada em 2026-06-23**. A Fase 3.1 foi encerrada no checkpoint `3901cf9325864663412af29e72a98d9500907b15` com `NfseMunicipalCapability` e `atualizado_em` canonico.

Escopo: consolidar o GET `/2/nfse/consulta/{uuid}` para item e lote, aplicar o retorno pelo `modelo` remoto, reconciliar itens de `info_nfse`, consultar `/2/nfse/status` como snapshot informativo sanitizado e expor acoes protegidas. Nenhum caminho pode emitir, cancelar, substituir ou manifestar.

Resultado: migration `0061_alter_nfsemunicipalcapability_options_and_more`; 14 testes especificos da 3.2, 2 regressões legadas de consulta e 311 testes fiscais direcionados aprovados. `makemigrations finance --check --dry-run`, Ruff dos Python tocados e `git diff --check` aprovados. Fase 3.3 nao iniciada.

## Fase 3.3 - Cancelamento idempotente de NFS-e legada

Status: **implementada e validada tecnicamente em 2026-06-23**. A Fase 3.2 foi encerrada no checkpoint `ad93e87308959d9f4b0f6fc69cfa9ec83c45b428`.

Escopo: substituir o PUT legado direto por cancelamento persistido ligado a `NfseItem`, tentativa `nfse_cancellation`, concorrencia segura, payload congelado, timeout `uncertain`, confirmacao por retorno/webhook e reconciliacao somente consultiva. Nenhum `FiscalDocument(nfse)`, substituicao, manifestacao ou emissao manual nova.

Resultado: migration `0062_alter_nfserequest_options_and_more`; 14 testes especificos da Fase 3.3, 219 testes dos alvos fiscais existentes e 104 testes dos alvos de credito/debito localizados em modulos separados aprovados. Migration-check, Ruff e diff-check aprovados; mypy permaneceu bloqueado pelo baseline amplo preexistente do repositorio.

## Fase 3.4.0 - Planejamento da substituicao NFS-e legada

Status: **planejamento documental concluido em 2026-06-23**. A Fase 3.3 foi validada no checkpoint `401b6553302ae1250a5b8838c77a43fa32ef9daa`.

Decisao: **Opcao B - Fase 3.4P preparatoria**. O endpoint requer um novo objeto RPS e a base legada atual so consegue reconstrui-lo de fontes mutaveis. A 3.4P deve congelar preview completa e auditavel, sem POST, tentativa remota ou alteracao da NFS-e original.

Ordem proposta: `3.4P` preview e aprovacao local -> `3.4.1` transmissao idempotente de preview aprovada -> `3.4.2` revisao/validacao e fechamento. Manifestacao e emissao manual nova continuam fora de escopo.

### Fase 3.4P

Status: **implementada e validada tecnicamente em 2026-06-23**. Migration `0063` cria flag e preview; service, forms, views, templates e testes comprovam preparacao/aprovacao local sem HTTP, tentativa, item substituto ou mudanca da original. A 3.4.1 continua bloqueada ate confirmacao contratual e nova autorizacao.

### Fase 3.4.1

Status: **implementada e validada tecnicamente em 2026-06-24**. Migration `0064`; POST restrito ao payload aprovado; original/substituta confirmadas de forma atomica; idempotencia, webhook, reconciliacao consultiva, UI e downloads protegidos. Manifestacao e emissao manual nova seguem bloqueadas.

## Fase 3.5.0 - Reavaliacao do proximo bloco apos NFS-e legada

Status: **validada em 2026-06-26**. A Fase 3.4.1 foi validada no checkpoint `5865c74d59459ce1f347d8a36a217098f20cb5a9` e encerrou o ciclo seguro atual da NFS-e legada: estabilizacao, consulta/reconciliacao, cancelamento idempotente e substituicao idempotente a partir de preview aprovada.

Alteracoes permitidas: somente `docs/fiscal-webmania/**` e, se necessario, `docs/fiscal-webmania/api/webmania_fiscal_openapi_validated.json`.

Alteracoes proibidas: codigo funcional, migrations, services, views, forms, templates, testes e comandos operacionais.

### Decisao

Priorizar **manifestacao de NFS-e Padrao Nacional** como proximo bloco fiscal. A decisao nao autoriza implementacao automatica nesta fase documental; ela apenas define a proxima fase candidata.

### Justificativa

Manifestacao e o menor passo util depois de cancelamento/substituicao NFS-e: e um evento sobre documento existente, possui endpoint especifico, pode usar `NfseMunicipalCapability.manifestation_enabled`, reaproveita tentativa/idempotencia/webhook/payload sanitizado e nao cria nova NFS-e nem nova familia fiscal. Emissao manual nova e NFS-e expandida tem valor maior, mas exigem reconstruir RPS/ISS/IBS-CBS, rollout municipal e modelagem fiscal nova. CT-e, MDF-e, NFCom, DC-e, eventos IBS/CBS pendentes, creditos/debitos restantes e complementar tributaria dependem de dominios locais ainda insuficientes ou risco fiscal maior.

### Escopo recomendado para a proxima fase funcional

- Criar trilha de manifestacao NFS-e local, restrita a `NfseItem` elegivel e oficina ativa.
- Exigir capacidade municipal, flag/permissao especifica e confirmacao explicita.
- Enviar somente o contrato oficial de `POST /2/nfse/manifestar`: ambiente, identificador permitido, manifestador, evento e motivo/justificativa quando exigidos.
- Persistir tentativa antes do POST, payload congelado e resposta sanitizada.
- Timeout ou resposta inconclusiva deve gerar `uncertain` e bloquear retry automatico.
- Webhook deve resolver sem ambiguidade e nao pode alterar cancelamento/substituicao ou NFS-e de outra oficina.
- Reconciliacao deve ser apenas consultiva e nunca repetir manifestacao.

### Testes planejados

- Bloqueio por ausencia de capacidade `manifestation_enabled`.
- Permissao e tenancy por oficina.
- Payload permitido para cada manifestador/evento autorizado.
- Justificativa obrigatoria quando o motivo remoto exigir texto.
- Concorrencia/idempotencia com uma chamada remota.
- Timeout `uncertain` bloqueante.
- Webhook duplicado, fora de ordem e ambiguo.
- Reconciliacao sem POST.
- XML/evento separado, sem sobrescrever XML original.

### Riscos

- Manifestacao e restrita ao Padrao Nacional; municipios/provedores fora desse contexto devem permanecer bloqueados.
- O papel do manifestador e a semantica de aceite/rejeicao precisam de copy e permissao fortes para evitar uso operacional incorreto.
- Se a Webmania retornar evento sem identificador suficiente, reconciliacao deve manter pendencia administrativa em vez de inferir sucesso.

### Fora de escopo

Emissao manual nova de NFS-e, NFS-e expandida ampla, agendamento, `FiscalDocument(nfse)` generalizado, CT-e, MDF-e, NFCom, DC-e, eventos `112120`, `112140`, `211xxx`, creditos tipos 2-5, debitos tipos 1-3/5-8 e complementar tributaria.

## Fase 3.6.0 - Planejamento Tecnico da Manifestacao de NFS-e Padrao Nacional

Status: **validada documentalmente em 2026-06-26** no checkpoint `0a8dd0c9`. A Fase 3.5.0 foi aprovada e encerrada com a decisao de priorizar manifestacao NFS-e Padrao Nacional.

Alteracoes permitidas: somente `docs/fiscal-webmania/**` e, se necessario, `docs/fiscal-webmania/api/webmania_fiscal_openapi_validated.json`.

Alteracoes proibidas: codigo funcional, migrations, services, views, forms, templates e testes.

### Contrato revalidado

- Endpoint: `POST /2/nfse/manifestar`.
- Payload: `ambiente`, `chave` ou `uuid`, `manifestador`, `evento`.
- `manifestador=1`: tomador.
- `manifestador=2`: intermediario.
- `evento=1`: confirmacao.
- `evento=2`: rejeicao.
- Rejeicao: `motivo_rejeicao` com codigos `1`, `2`, `3`, `4`, `5` ou `9`; `justificativa_rejeicao` obrigatoria para `9`, de 15 a 255 caracteres.
- Escopo oficial: Padrao Nacional.

Lacuna registrada: a documentacao de `/2/nfse/status` nao confirma claramente `manifestar` em `funcoes`. A fase funcional deve bloquear quando Padrao Nacional/capability nao estiverem confirmados.

### Decisao tecnica

Recomendar implementacao direta em fase funcional pequena, sem preview previa. Motivo: manifestacao nao cria RPS nem nova NFS-e; o payload e pequeno e pode ser congelado na propria intencao. Rejeicao exige confirmacao explicita e validacao de motivo/justificativa.

### Escopo funcional futuro

- Model proprio `NfseManifestation` vinculado a `NfseItem`.
- Operation type `nfse_manifestation`.
- Capability/flag `nfse_manifestation_enabled` ou uso equivalente de `NfseMunicipalCapability.manifestation_enabled` combinado com flag administrativa de oficina.
- Permissoes: `issue_nfse_manifestation`, `view_nfse_manifestation`, `download_nfse_manifestation`, `view_nfse_manifestation_payload`.
- UI minima: acao em NFS-e elegivel, tipo/papel/motivo, confirmacao explicita, historico, payload e artefatos protegidos.

### Criterios de aceite futuros

1. Bloquear NFS-e municipal legada ou sem Padrao Nacional confirmado.
2. Bloquear cancelada, substituida, incerta ou sem identificador suficiente.
3. Criar manifestacao/tentativa antes do POST com payload congelado.
4. Garantir uma chamada remota por intencao mesmo sob concorrencia.
5. Timeout vira `uncertain` e bloqueia retry automatico.
6. Webhook sem identificador suficiente fica pendente, nao infere sucesso.
7. Reconciliacao nao repete `POST /2/nfse/manifestar`.
8. Cancelamento e substituicao NFS-e continuam intactos.

## Fase 3.6.1 - Manifestacao de NFS-e Padrao Nacional

Status: **validada em 2026-06-27** no checkpoint `da3b2b48`.

Escopo: implementar somente manifestacao de NFS-e local com Padrao Nacional confirmado por `NfseMunicipalCapability.national_standard_enabled` e `manifestation_enabled`, usando `POST /2/nfse/manifestar`.

Fora de escopo: emissao manual nova de NFS-e, NFS-e recebida/importada de terceiros, municipal legada sem Padrao Nacional confirmado, desfazimento/cancelamento de manifestacao, CT-e, MDF-e, NFCom, DC-e, eventos IBS/CBS pendentes, creditos/debitos restantes e complementar tributaria.

Resultado: model `NfseManifestation`, operation type `nfse_manifestation`, payload congelado, timeout `uncertain`, bloqueio de retry automatico, webhook seguro, reconciliacao consultiva, permissoes proprias, capability `national_standard_enabled` + `manifestation_enabled`, UI minima e testes direcionados. O PostgreSQL local foi normalizado para a validacao; os testes focados e as regressoes diretas de NFS-e passaram. Emissao manual nova, NFS-e recebida/importada, CT-e, MDF-e, NFCom, DC-e, eventos IBS/CBS pendentes, creditos/debitos restantes e complementar tributaria nao foram iniciados.

## Fase 3.7.0 - Reavaliacao do roadmap apos manifestacao NFS-e

Status: **validada documentalmente em 2026-06-27** no checkpoint `1b60125c`. A Fase 3.6.1 foi aprovada e encerrada no checkpoint `da3b2b48`.

Alteracoes permitidas: somente `docs/fiscal-webmania/**` e, se houver correcao oficialmente confirmada, `docs/fiscal-webmania/api/webmania_fiscal_openapi_validated.json`.

Alteracoes proibidas: codigo funcional, migrations, services, views, forms, templates, testes e comandos operacionais.

### Matriz comparativa obrigatoria

| Bloco | Fonte local existe? | Contrato Webmania claro? | Reaproveita infraestrutura atual? | Dependencia externa | Risco fiscal | Valor de negocio | Recomendacao |
| ----- | ------------------: | -----------------------: | --------------------------------: | ------------------- | ------------ | ---------------- | ------------ |
| Emissao manual nova de NFS-e | Parcial: legado por OS possui tomador, servico, valores, RPS e classe fiscal, mas dados sao mutaveis e acoplados a OS | Sim para `/2/nfse/emissao`, com variacao municipal e Padrao Nacional | Alta: NfseRequest/NfseItem, capacidade municipal, tentativa, webhook, reconciliacao e downloads | Municipio/provedor, ISS, IBS/CBS, numeracao/RPS, ambiente e rollout por oficina | Alto | Muito alto | **Opcao F: fase preparatoria de preview/snapshot antes de transmissao** |
| NFS-e recebida/importada de terceiros | Nao suficiente: nao ha dominio de entrada/importacao, XML validado ou papel fiscal da oficina | Parcial: consulta/manifestacao existem, mas fonte do documento nao | Media: consulta, webhook e manifestacao poderiam ser reaproveitados depois | XML/UUID/chave/codigo, papel tomador/intermediario, associacao cliente/oficina | Alto | Alto | Adiar ate existir importacao/registro seguro |
| NFS-e expandida | Parcial: base legado existe, mas `FiscalDocument(nfse)` generalizado nao | Parcial: varios endpoints claros, mas municipalidade/Padrao Nacional variam | Media/alta | Provedores, DPS/RPS, ISS/IBS-CBS e eventual backfill | Alto | Muito alto | Quebrar em subfases; nao executar como bloco amplo |
| CT-e | Nao | Sim em alto nivel, mas exige modelagem propria | Media tecnica, baixa de dominio | Transporte, remetente/destinatario/tomador, carga, veiculos e documentos relacionados | Alto | Baixo/medio | Adiar |
| MDF-e | Nao | Sim em alto nivel | Baixa | CT-e/NF-e vinculados, veiculo, condutor, percurso, encerramento | Alto | Baixo | Adiar ate haver dominio logistico/CT-e |
| NFCom | Nao | Sim; API v2.0.0 documentada | Media tecnica | Dominio de telecomunicacoes, habilitacao administrativa e baixa aderencia ao produto | Alto | Muito baixo | Adiar; manter feature flag interna |
| DC-e | Nao | Sim; API v2.0.0 documentada | Media tecnica | Dominio especifico e demanda nao confirmada | Alto | Muito baixo | Adiar; manter feature flag interna |
| Eventos IBS/CBS 112120 | Nao suficiente | Sim, com campos de item/controle | Alta tecnica | Importacao ALC/ZFM, XML/projecao fiscal e contexto de isencao | Alto | Baixo | Adiar |
| Eventos IBS/CBS 112140 | Nao suficiente | Sim, com item de debito/pagamento antecipado | Alta tecnica | Debito tipo 6, pagamento antecipado, item fiscal e quantidade nao fornecida | Alto | Medio | Adiar ate fonte fiscal/financeira existir |
| Eventos IBS/CBS 211xxx | Nao suficiente | Parcial por codigo | Media tecnica | Papel destinatario, entrada/importacao, estoque, ativo, combustivel ou apuracao externa | Alto | Baixo/medio | Adiar |
| Creditos 2-5 | Nao suficiente | Sim em alto nivel, mas condicoes variam por tipo | Alta tecnica | ZFM/ALC, cooperativa, sucessao, apuracao ou outras evidencias fiscais | Alto | Baixo/medio | Adiar |
| Debitos 1-3 e 5-8 | Nao suficiente | Sim em alto nivel, mas condicoes variam por tipo | Alta tecnica para alguns tipos | Cooperativa, imunes/isentas, fora da apuracao, sucessao, pagamento antecipado, estoque fiscal ou desenquadramento SN | Alto | Baixo/medio | Adiar |
| Complementar tributaria | Parcial | Parcial: complementar existe, mas imposto/IBS-CBS exigem revalidacao especifica | Alta | Base tributaria por imposto, XML/snapshot e regra fiscal aprovada | Alto | Medio | Fase preparatoria futura, nao agora |

### Decisao

Escolher **Opcao F - Fase preparatoria**, direcionada ao proximo bloco de maior valor: **emissao manual nova de NFS-e**.

A emissao manual nova tem maior valor de produto do que importacao recebida, CT-e/MDF-e/NFCom/DC-e ou novos tipos NF-e, e reaproveita a infraestrutura NFS-e ja validada. Ainda assim, ela nao deve ser funcional de imediato: criar uma NFS-e nova consome RPS/numeracao e depende de tomador, servico, valores, ISS, IBS/CBS, municipio/capability, ambiente e regras de duplicidade. Esses dados existem parcialmente no legado, mas hoje sao derivados de OS e cadastros mutaveis. A decisao segura e planejar primeiro uma preview/snapshot imutavel.

### Proxima fase recomendada

`Fase 3.7P - Preview de emissao manual nova de NFS-e`, sem transmissao Webmania.

Objetivo: congelar uma intencao completa de RPS/NFS-e manual nova, auditavel e aprovada, antes de qualquer `POST /2/nfse/emissao`.

Escopo:

- criar planejamento para preview local de NFS-e manual nova, preferencialmente fora do fluxo obrigatorio por OS, mas compatível com ele quando houver origem operacional;
- congelar tomador, endereco, servico, codigo municipal, discriminacao, CNAE/atividade quando aplicavel, valores, descontos, retencoes, ISS, IBS/CBS, ambiente, serie/numero/RPS ou politica de numeracao Webmania, municipio/capability e payload planejado;
- exigir `NfseMunicipalCapability` ativa e compatibilidade com Padrao Nacional/municipal conforme o municipio;
- nao criar `NfseItem`, `FiscalEmissionAttempt`, documento emitido, webhook, reconciliacao remota ou download fiscal;
- preparar criterios para uma fase funcional posterior que consumira somente preview aprovada.

Endpoint Webmania futuro: `POST /2/nfse/emissao`. Na fase preparatoria nao ha chamada HTTP.

Modelagem futura: entidade de preview/snapshot propria para NFS-e manual nova, com status `draft`, `ready`, `approved`, `rejected` e `archived`, payload planejado sanitizado, hash, criador/aprovador e imutabilidade apos aprovacao. A fase funcional posterior podera criar `NfseRequest`/`NfseItem` ou uma projecao fiscal nova conforme decisao aprovada, mas isso nao pertence a 3.7P.

Idempotencia: sem idempotencia remota na fase preparatoria. A fase funcional posterior deve criar tentativa antes do POST, com chave por oficina, preview aprovada e geracao da intencao; `uncertain` bloqueia retry automatico.

Permissoes: criar na fase futura permissoes separadas de preparacao/aprovacao/visualizacao/payload. Preparar preview nao concede emissao.

Feature flag/capability: exigir flag administrativa de preparacao/emissao manual NFS-e e `NfseMunicipalCapability` coerente. Capability remota nao substitui aprovacao administrativa.

UI minima: lista de previews, criacao/edicao enquanto rascunho, validacao, aprovacao fiscal, payload sanitizado e aviso explicito de que nao ha transmissao.

Webhook/reconciliacao: inexistentes na 3.7P. A fase funcional posterior deve usar webhook NFS-e padrao e reconciliacao somente consultiva.

Testes planejados:

- preview congela tomador, servico, valores, impostos e ambiente;
- bloqueia municipio sem capability, feature flag desligada, oficina divergente e usuario sem permissao;
- valida ISS/IBS-CBS e campos obrigatorios sem fallback mutavel;
- payload aprovado e imutavel;
- nenhuma chamada HTTP, `FiscalEmissionAttempt`, NfseItem emitido, webhook ou reconciliacao e criada;
- regressao de emissao legada por OS, cancelamento, substituicao e manifestacao permanece intacta.

Riscos:

- variacao municipal pode exigir campos nao cobertos por um formulario manual generico;
- duplicidade de RPS/numeracao se a fase funcional nao reservar a intencao corretamente;
- ISS/IBS-CBS e retencoes podem divergir por municipio/provedor;
- UI manual pode contornar origem operacional se nao houver permissao e aprovacao fortes.

Criterios de aceite:

1. A preview aprovada representa um RPS/NFS-e completo e auditavel.
2. Dados mutaveis de OS, cliente, servico ou classe fiscal nao alteram preview aprovada.
3. Nenhuma transmissao, tentativa remota, webhook ou reconciliacao e criada.
4. Capability, feature flag, permissao e tenancy bloqueiam corretamente.
5. Fase funcional posterior fica explicitamente dependente de preview aprovada.

OpenAPI: schema atual permanece suficiente; nenhuma correcao oficial nova foi confirmada nesta reavaliacao.

## Fase 3.7P - Preview Imutavel de Emissao Manual Nova de NFS-e

Status: **validada e encerrada em 2026-06-27** no checkpoint `1fdded4e`. A Fase 3.7.0 aprovou criar preview/snapshot antes de qualquer emissao manual nova.

Escopo: criar camada preparatoria para montar, validar, congelar e aprovar payload futuro de `POST /2/nfse/emissao`, sem chamada remota.

Fora de escopo: `POST /2/nfse/emissao`, NFS-e autorizada, `NfseItem` remoto, XML/DANFSE, `FiscalEmissionAttempt`, cancelamento/substituicao/manifestacao da nova NFS-e, NFS-e recebida/importada, CT-e, MDF-e, NFCom, DC-e, eventos IBS/CBS pendentes, creditos/debitos pendentes e complementar tributaria.

### Auditoria tecnica inicial

- Emissao legada: `build_nfse_payload` monta `ambiente`, `url_notificacao` e lista `rps`; `emit_nfse_request` reserva RPS e cria `FiscalEmissionAttempt` apenas no momento da transmissao.
- Cancelamento NFS-e: `NfseCancellation` usa payload congelado `{uuid, motivo}`, tentativa `nfse_cancellation`, timeout `uncertain`, webhook e reconciliacao consultiva.
- Substituicao NFS-e: `NfseSubstitutionPreview` ja demonstra padrao local de preview imutavel sem HTTP; `NfseSubstitution` transmite somente preview aprovada.
- Manifestacao NFS-e: `NfseManifestation` transmite contrato pequeno para Padrao Nacional e preserva XML/status original.
- `NfseItem`: representa retorno remoto autorizado/processado, XML/PDF/RPS e status; nao deve ser criado na preview manual.
- `WebmaniaCompany`: possui credenciais, ambiente operacional via settings, RPS serie/numero/producao/homologacao e flags NFS-e legadas/substituicao; precisa de flag preparatoria propria.
- Capabilities municipais: `NfseMunicipalCapability` controla emissao, consulta, cancelamento, substituicao, manifestacao, RPS, codigo de servico, CNAE e aliquota ISS; a preview deve exigir capability ativa e emissao habilitada.
- Numeracao/RPS: `reserve_nfse_request_rps_number` consome contador somente na transmissao legada; a preview deve validar numero/serie informados sem consumir contador oficial.
- Tomador: legada deriva de cliente da OS via CPF/CNPJ e nome/razao social; preview manual deve congelar o snapshot.
- Servico/valores: legada deriva descricao, slider e classe fiscal; preview manual deve congelar discriminacao, valor e tributacao.
- ISS/IBS-CBS/retenções: podem vir de `classe_imposto` ou payload de impostos/retenções; preview deve validar existencia e preservar snapshot sem recalculo.
- Webhook/reconciliacao/downloads: pertencem a documentos transmitidos; inexistem na preview.
- Testes existentes: ha cobertura de emissao legada, cancelamento, substituicao, manifestacao e regressoes NFS-e em `apps.finance.tests`.

### Criterios de aceite

1. Preview completa pode ser criada, validada e aprovada sem chamada Webmania.
2. Preview aprovada e imutavel em oficina, empresa, capability, ambiente, RPS, tomador, servico, valores e tributacao.
3. Feature flag, capability, permissao e cross-workshop bloqueiam corretamente.
4. Payload protegido exige permissao propria.
5. Nenhum `NfseItem`, `FiscalEmissionAttempt`, XML/DANFSE, webhook ou reconciliacao remota e criado.

Resultado local:

- Model `NfseManualEmissionPreview`, flags `nfse_manual_emission_preview_enabled` e `manual_emission_enabled`, services, views, forms e templates adicionados sem endpoint remoto de emissao.
- Payload planejado fica restrito a `{"ambiente": int, "rps": [rps_snapshot]}` e campos remotos/autorizados como `uuid`, `codigo_verificacao`, cancelamento, substituicao e manifestacao sao bloqueados na preview.
- Aprovacao congela oficina, empresa, capability, ambiente, RPS, tomador, servico, valores, tributacao, retencoes e IBS/CBS.
- Testes focados cobriram preview nova, cancelamento, manifestacao, preview de substituicao e substituicao NFS-e.

## Fase 3.7.1 - Emissao Manual Nova de NFS-e a partir de Preview Aprovada

Status: **validada e encerrada em 2026-06-28** no checkpoint `2cb35206`. A Fase 3.7P foi aprovada no checkpoint `1fdded4e`.

Escopo: transmitir `POST /2/nfse/emissao` exclusivamente a partir de `NfseManualEmissionPreview` aprovada, persistindo uma intencao remota idempotente e criando `NfseItem` somente apos confirmacao remota valida.

Contrato efetivo: o payload enviado deve ser o `request_payload` congelado na preview aprovada. Nao recalcular tomador, servico, valores, tributacao, retencoes, IBS/CBS ou RPS a partir de formulario, cadastro atual, OS, cliente, servico ou input livre.

Pre-condicoes obrigatorias:

- `NfseManualEmissionPreview` aprovada e pertencente a oficina ativa.
- Feature flag de emissao manual separada da flag de preview.
- `NfseMunicipalCapability.manual_emission_enabled=True`, ativa e coerente com a empresa.
- Permissao especifica de emissao manual, distinta de preparar/aprovar preview, cancelamento, substituicao e manifestacao.
- Empresa emissora configurada.
- RPS numero/serie e payload aprovado completos.
- Ausencia de emissao ativa, autorizada ou incerta para a mesma preview e ausencia de RPS local ja autorizado para a mesma empresa/oficina/ambiente.

Fora de escopo nesta fase: cancelamento da nova NFS-e, substituicao da nova NFS-e, manifestacao automatica da nova NFS-e, NFS-e recebida/importada, CT-e, MDF-e, NFCom, DC-e, eventos IBS/CBS pendentes, creditos/debitos pendentes e complementar tributaria.

Criterios de aceite:

1. Uma preview aprovada gera no maximo uma emissao ativa/autorizada/incerta.
2. `FiscalEmissionAttempt(operation_type="nfse_manual_emission")` e criado antes do HTTP e bloqueia retry da mesma intencao.
3. Timeout ou resposta inconclusiva marca a emissao como `uncertain` e nao reenvia automaticamente.
4. `NfseItem` e criado apenas com retorno remoto inequivoco.
5. Webhook e reconciliacao atualizam somente a emissao manual/NFS-e correspondente quando a identificacao for segura e nunca repetem `POST`.
6. Payload, resposta, XML e DANFSE sao protegidos por permissao e oficina.
7. Preview aprovada permanece imutavel.

Resultado local: migration `0067`; model `NfseManualEmission`; flag separada de emissao manual; tentativa `nfse_manual_emission`; envio idempotente do `request_payload` aprovado; criacao de `NfseItem` somente apos retorno remoto aprovado; webhook e reconciliacao sem novo `POST`; UI minima e permissoes proprias. A validacao obrigatoria de 49 testes NFS-e passou, migration-check e Ruff focado passaram. `mypy .` foi executado e segue bloqueado por baseline amplo preexistente; uma regressao adicional fora da bateria obrigatoria tambem expôs fragilidades legadas ja fora do escopo desta fase.

## Fase 3.8.0 - Reavaliacao do Ciclo Pos-Emissao Manual de NFS-e

Status: **validada documentalmente em 2026-06-28** no checkpoint `1faf0a9`. A Fase 3.7.1 foi validada e encerrada no checkpoint `2cb35206`.

Alteracoes permitidas: somente `docs/fiscal-webmania/**` e, se houver correcao oficialmente confirmada, `docs/fiscal-webmania/api/webmania_fiscal_openapi_validated.json`.

Alteracoes proibidas: codigo funcional, migrations, services, views, forms, templates e testes.

### Revalidacao oficial

Fonte revalidada em 2026-06-28: [documentacao oficial Webmania NFS-e](https://webmania.com.br/docs/rest-api-nfse/). O contrato NFS-e permanece compatível com o OpenAPI local validado:

- `POST /2/nfse/emissao`: emissao por `ambiente` e `rps` em lista, com retorno `nfse` ou `lote_rps`, status e URLs de XML/PDF quando disponiveis.
- `PUT /2/nfse/cancelar`: cancelamento padrao por `uuid` e `motivo` (`1`, `2` ou `4`), mesmo contrato usado no cancelamento NFS-e ja implementado.
- `POST /2/nfse/substituir`: substituicao por `ambiente`, `codigo_verificacao`, `motivo` e novo `rps` objeto, mesmo contrato ja usado pela substituicao implementada.
- `POST /2/nfse/manifestar`: manifestacao de participacao no Padrao Nacional por `ambiente`, `uuid|chave`, `manifestador` e `evento`, com motivo/justificativa para rejeicao.
- `GET /2/nfse/consulta/{identifier}`: consulta/reconciliacao por identificador remoto, sem reemissao.
- `GET /2/nfse/status`: status/capacidades municipais; funcoes devem continuar tratadas como capability administrativa, nao como autorizacao automatica.

Nao foi encontrada diferenca oficial especifica para uma NFS-e emitida manualmente pelo Hunter: apos confirmacao remota valida, ela se materializa como `NfseItem` com UUID/codigo/artefatos e deve usar os mesmos contratos externos de cancelamento, substituicao, manifestacao e consulta. A diferenca local e a origem: `NfseManualEmission` e sua preview aprovada devem permanecer imutaveis.

### Matriz comparativa obrigatoria

| Bloco | Fonte local existe? | Reaproveita infraestrutura atual? | Dependencia externa | Risco fiscal | Valor de negocio | Recomendacao |
| ----- | ------------------: | --------------------------------: | ------------------- | ------------ | ---------------- | ------------ |
| Cancelamento da NFS-e manual nova | Sim: `NfseManualEmission` vincula `NfseItem` autorizado com UUID | Alta: `NfseCancellation`, tentativa `nfse_cancellation`, webhook e reconciliacao consultiva | Baixa: mesmo `PUT /2/nfse/cancelar` por UUID/motivo | Medio, controlavel por UUID e oficina | Alto | **Opcao A: Fase 3.8.1** |
| Substituicao da NFS-e manual nova | Parcial: `NfseItem` possui UUID/codigo; falta elegibilidade por origem manual | Alta: `NfseSubstitutionPreview`/`NfseSubstitution` ja existem | Media: novo RPS completo e capability `substitution_enabled` | Medio/alto por criar nova NFS-e substituta | Alto | Adiar apos cancelamento; adaptar elegibilidade |
| Manifestacao da NFS-e manual nova | Parcial: UUID existe, mas Padrao Nacional precisa ser confirmado | Alta: `NfseManifestation` ja existe | Media: exige Padrao Nacional, papel e capability | Medio/alto por relacao fiscal/papel | Medio/alto | Fase separada apos confirmar Padrao Nacional |
| NFS-e recebida/importada | Nao suficiente: sem dominio de entrada/importacao | Media: consulta/manifestacao poderiam ser reaproveitadas | Alta: XML/UUID/chave, papel fiscal e associacao segura | Alto | Alto | Adiar ate fonte documental segura |
| NFS-e expandida | Parcial: legado + manual existem; `FiscalDocument(nfse)` generalizado nao | Media/alta | Alta: Padrao Nacional, DPS/RPS, municipio/provedor e backfill | Alto | Muito alto | Quebrar em subfases; nao executar agora |
| CT-e | Nao | Media tecnica | Alta: transporte, tomador, remetente/destinatario, carga | Alto | Baixo/medio | Adiar |
| MDF-e | Nao | Baixa | Alta: CT-e/NF-e vinculados, veiculo, condutor, percurso | Alto | Baixo | Adiar apos CT-e |
| NFCom | Nao | Media tecnica | Alta: dominio telecom e habilitacao administrativa | Alto | Muito baixo | Adiar; manter flag interna |
| DC-e | Nao | Media tecnica | Alta: dominio especifico sem demanda confirmada | Alto | Muito baixo | Adiar; manter flag interna |
| Eventos IBS/CBS 112120 | Nao suficiente | Alta tecnica | Alta: importacao ALC/ZFM e estoque/controle | Alto | Baixo | Adiar |
| Eventos IBS/CBS 112140 | Nao suficiente | Alta tecnica | Alta: debito tipo 6 e pagamento antecipado por item | Alto | Medio | Adiar ate base de debito tipo 6 |
| Eventos IBS/CBS 211xxx | Nao suficiente | Media/alta tecnica | Alta: papel destinatario, entrada, ativo, combustivel ou apuracao | Alto | Baixo/medio | Adiar |
| Creditos 2-5 | Nao suficiente | Alta tecnica | Alta: ZFM, recusa, reducao, sucessao e apuracao | Alto | Baixo/medio | Adiar |
| Debitos 1-3 e 5-8 | Nao suficiente | Alta tecnica para alguns tipos | Alta: cooperativa, imunes/isentas, apuracao, sucessao, pagamento antecipado, estoque ou SN | Alto | Baixo/medio | Adiar |
| Complementar tributaria | Parcial | Alta | Alta: base tributaria aprovada por imposto/IBS-CBS | Alto | Medio | Auditoria preparatoria posterior |

### Avaliacoes especificas

Cancelamento: `NfseManualEmission` ja vincula `NfseItem`; o `NfseItem` autorizado possui UUID suficiente; o contrato externo e o mesmo da NFS-e legada; XML de cancelamento deve permanecer separado; webhook/reconciliacao ja resolvem a NFS-e por UUID; preview e emissao manual devem continuar imutaveis. Recomendacao: extensao segura do cancelamento NFS-e existente, nao um gateway novo.

Substituicao: pode reutilizar `NfseSubstitutionPreview`, `NfseSubstitution`, `POST /2/nfse/substituir`, preservacao do XML original e criacao de `NfseItem` substituta. Precisa adaptar elegibilidade para aceitar `NfseItem` originado por `NfseManualEmission` sem depender de `NfseRequest`/OS.

Manifestacao: deve ser fase separada. NFS-e manual so pode manifestar quando houver Padrao Nacional confirmado, `NfseMunicipalCapability.national_standard_enabled=True`, `manifestation_enabled=True` e UUID/chave seguro. Nao deve ser automatica apos emissao.

### Decisao

Escolher **Opcao A - Implementar cancelamento da NFS-e manual nova** como proxima fase funcional pequena, porque fecha o primeiro ciclo pos-emissao, usa contrato oficial claro, possui fonte local confiavel (`NfseManualEmission` -> `NfseItem` autorizado), reaproveita a infraestrutura validada de `NfseCancellation`, minimiza risco de webhook ambiguo por UUID e nao depende de NFS-e recebida/importada, CT-e/MDF-e/NFCom/DC-e ou novos eventos IBS/CBS.

### Escopo proposto da Fase 3.8.1 - Cancelamento da NFS-e Manual Nova

Tipo de implementacao recomendado: **A) extensao segura do cancelamento NFS-e existente**. Nao criar um gateway remoto paralelo; adaptar elegibilidade, UI e relacoes para aceitar NFS-e manual autorizada.

- Objetivo: permitir `PUT /2/nfse/cancelar` para NFS-e manual nova autorizada, vinculada a `NfseManualEmission`, mantendo preview/emissao imutaveis.
- Endpoint: `PUT /2/nfse/cancelar` com payload congelado `{uuid, motivo}` e motivo permitido `1`, `2` ou `4`.
- Modelagem: reutilizar `NfseCancellation` quando possível, associando ao `NfseItem` manual; se a modelagem atual exigir `NfseRequest`, ajustar de forma compativel sem criar `FiscalDocument(nfse)`.
- Operacao/idempotencia: reutilizar `FiscalEmissionAttempt(operation_type="nfse_cancellation")`; uma chamada por intencao; timeout `uncertain`; retry automatico bloqueado.
- Permissoes: exigir `cancel_nfse` e permissoes de visualizacao/download/payload ja aplicaveis ao cancelamento; permissao de emitir manualmente nao cancela.
- Feature flag/capability: exigir capability municipal de cancelamento (`cancellation_enabled` ou equivalente atual) e oficina/empresa coerentes; flag de emissao manual nao libera cancelamento sozinha.
- UI minima: acao no detalhe da emissao manual/NFS-e manual autorizada, confirmacao explicita, motivo, historico de cancelamento, payload/retorno protegidos.
- Webhook/reconciliacao: atualizar somente o `NfseCancellation`/`NfseItem` correspondente por UUID seguro; ambiguidade fica pendente; reconciliacao usa somente GET/consulta, nunca repete PUT.
- Downloads/payload: XML de cancelamento separado do XML original; payload e resposta sanitizados; cross-workshop bloqueado.
- Bloqueios obrigatorios: NFS-e sem UUID, nao autorizada, ja cancelada, substituida, com cancelamento `sent/succeeded/uncertain`, outra oficina, sem permissao, capability desligada ou retorno remoto ambiguo.
- Testes planejados: contrato `{uuid, motivo}`; cancelamento de NFS-e manual autorizada; bloqueio sem UUID/sem `NfseItem`/preview apenas aprovada; duplicidade; timeout `uncertain`; webhook seguro; reconciliacao sem PUT; XML separado; permissoes; cross-workshop; regressao do cancelamento legado, substituicao, manifestacao e emissao manual.
- Criterios de aceite: nenhuma alteracao na preview aprovada ou no payload de emissao; nenhuma substituicao/manifestacao automatica; cancelamento manual e legado compartilham contrato seguro; working tree validada com testes focados e Ruff.

OpenAPI: o schema atual permanece suficiente; nenhuma correcao oficial nova foi confirmada nesta reavaliacao.

## Fase 3.8.1 - Cancelamento da NFS-e Manual Nova

Status: **validada e encerrada em 2026-06-28** no checkpoint `29f3f3a9`. A Fase 3.8.0 foi aprovada e encerrada no checkpoint `1faf0a9`.

Escopo: cancelar somente NFS-e manual nova gerada por `NfseManualEmission` e materializada em `NfseItem` autorizado, usando `PUT /2/nfse/cancelar` com payload congelado `{uuid, motivo}`.

Estrategia aprovada: extensao segura do cancelamento NFS-e existente, reutilizando `NfseCancellation`, `FiscalEmissionAttempt(operation_type="nfse_cancellation")`, webhook e reconciliacao consultiva quando a associacao por UUID/oficina for segura.

Fora de escopo nesta fase: substituicao da NFS-e manual nova, manifestacao automatica da NFS-e manual nova, NFS-e recebida/importada, emissao manual adicional, CT-e, MDF-e, NFCom, DC-e, eventos IBS/CBS `112120/112140/211xxx`, creditos 2-5, debitos 1-3/5-8 e complementar tributaria.

Resultado local: migration `0068`; `NfseCancellation.request` passou a ser opcional para permitir cancelamento de `NfseItem` manual sem `NfseRequest`; `cancel_nfse_item` aceita NFS-e manual somente quando ha `NfseManualEmission` vinculada, `NfseItem` autorizado, UUID seguro, capability de cancelamento ativa e nenhuma intencao ativa/incerta. O payload remoto continua estrito em `{uuid, motivo}`. Webhook e reconciliacao confirmam cancelamento manual sem repetir `PUT` e preservam XML original. A UI minima foi adicionada no detalhe da emissao manual com permissao `cancel_nfse`.

Criterios atendidos: contrato remoto preservado; `NfseCancellation` reutilizado; tentativa `nfse_cancellation` reutilizada; XML de cancelamento separado; preview/emissao manual imutaveis; substituicao e manifestacao da NFS-e manual nao iniciadas.

## Fase 3.9.0 - Reavaliacao apos Ciclo Minimo da NFS-e Manual

Status: **validada documentalmente em 2026-06-28** no checkpoint `21d684e7`. A Fase 3.8.1 foi validada e encerrada no checkpoint `29f3f3a9`.

Alteracoes permitidas: somente `docs/fiscal-webmania/**` e, se houver correcao oficialmente confirmada, `docs/fiscal-webmania/api/webmania_fiscal_openapi_validated.json`.

Alteracoes proibidas: codigo funcional, migrations, services, views, forms, templates e testes.

### Contexto

A NFS-e manual nova atingiu o ciclo minimo operacional:

```text
preview -> emissao -> cancelamento
```

O ciclo validado preserva os invariantes fiscais principais: `NfseManualEmissionPreview` aprovada imutavel, `NfseManualEmission.request_payload` imutavel, `NfseItem` criado somente apos confirmacao remota valida, cancelamento por `NfseCancellation`, `NfseCancellation.request` opcional para origem manual, contrato remoto de cancelamento `PUT /2/nfse/cancelar` com `{uuid, motivo}`, XML original preservado e XML de cancelamento separado.

Fonte oficial reconsultada em 2026-06-28: a documentacao Webmania NFS-e v3.1.1 continua compatível com o OpenAPI local para emissao, cancelamento, substituicao, manifestacao, consulta e status. Nenhum ajuste de schema foi identificado.

### Matriz comparativa obrigatoria

| Bloco | Fonte local existe? | Reaproveita infraestrutura atual? | Dependencia externa | Risco fiscal | Valor de negocio | Recomendacao |
| ----- | ------------------: | --------------------------------: | ------------------- | ------------ | ---------------- | ------------ |
| Substituicao da NFS-e manual | Sim: `NfseManualEmission` vincula `NfseItem` autorizado com UUID/codigo verificacao | Alta: `NfseSubstitutionPreview`, `NfseSubstitution`, tentativa `nfse_substitution`, webhook e reconciliacao ja existem | Media: capability `substitution_enabled`, novo RPS completo e resposta com substituta | Medio/alto, controlavel por preview imutavel | Alto | **Opcao A: proxima fase funcional recomendada** |
| Manifestacao da NFS-e manual | Parcial: UUID existe; Padrao Nacional/papel fiscal precisam ser confirmados | Alta: `NfseManifestation`, tentativa `nfse_manifestation`, webhook e reconciliacao ja existem | Media: Padrao Nacional, `national_standard_enabled`, `manifestation_enabled`, papel tomador/intermediario | Medio/alto por papel fiscal | Medio/alto | Adiar; avaliar apos substituicao ou NFS-e recebida |
| NFS-e recebida/importada | Nao suficiente: nao ha dominio local de XML recebido/importado | Media: consulta, manifestacao e payload sanitizado poderiam ser reaproveitados | Alta: XML/chave/UUID/codigo verificacao, papel tomador/prestador e associacao segura | Alto | Alto | Preparar somente em fase documental propria |
| NFS-e expandida | Parcial: legado e manual existem, mas sem `FiscalDocument(nfse)` generalizado | Media/alta | Alta: Padrao Nacional, municipio/provedor, backfill e convivencia | Alto | Muito alto | Quebrar em subfases; nao executar como bloco amplo |
| CT-e | Nao | Media tecnica: idempotencia/webhook/downloads fiscais podem ser padronizados | Alta: dominio de transporte, carga, tomador/remetente/destinatario e API v2 | Alto | Baixo/medio | Adiar |
| MDF-e | Nao | Baixa/media: depende de documentos vinculados e dominio logistico | Alta: CT-e/NF-e, veiculo, condutor, percurso e encerramento | Alto | Baixo | Adiar apos CT-e ou demanda logistica clara |
| NFCom | Nao | Media tecnica | Alta: dominio telecom, credenciamento e baixa aderencia ao produto oficina | Alto | Muito baixo | Adiar; manter flag interna |
| DC-e | Nao | Media tecnica | Alta: dominio especifico, demanda nao comprovada e API v2 | Alto | Muito baixo | Adiar; manter flag interna |
| Eventos IBS/CBS `112120` | Nao suficiente | Alta tecnica: `FiscalDocumentEvent` e eventos IBS/CBS ja existem | Alta: ALC/ZFM, estoque e campos por item | Alto | Baixo | Adiar |
| Eventos IBS/CBS `112140` | Nao suficiente | Alta tecnica: trilha de eventos ja existe | Alta: debito tipo 6, pagamento antecipado e nao fornecimento por item | Alto | Medio | Adiar ate base do debito tipo 6 |
| Eventos IBS/CBS `211xxx` | Nao suficiente | Media/alta tecnica | Alta: papel destinatario, entrada fiscal, ativo, combustivel ou apuracao | Alto | Baixo/medio | Adiar |
| Creditos 2-5 | Nao suficiente | Alta tecnica: base de credito/debito existe para tipo 1/4 | Alta: ZFM, recusa, reducao, sucessao e apuracao IBS/CBS | Alto | Baixo/medio | Adiar |
| Debitos 1-3 e 5-8 | Nao suficiente | Alta tecnica para alguns tipos | Alta: cooperativa, imunes/isentas, apuracao, sucessao, pagamento antecipado, estoque e SN | Alto | Baixo/medio | Adiar |
| Complementar tributaria | Parcial: complementar preco/quantidade existe | Alta tecnica | Alta: regra por imposto, IBS/CBS, snapshots tributarios e validacao fiscal | Alto | Medio | Adiar para auditoria propria |

### Avaliacao especifica da substituicao da NFS-e manual

Reaproveitamento possivel:

- `NfseSubstitutionPreview`: pode continuar congelando o novo RPS, motivo, ambiente, codigo de verificacao original e snapshots auditaveis.
- `NfseSubstitution`: pode continuar representando a operacao remota e a ligacao entre original e substituta.
- Endpoint: `POST /2/nfse/substituir` permanece o contrato adequado.
- XML original: deve permanecer preservado como na substituicao legada e na emissao manual.
- Nova `NfseItem` substituta: ja e o padrao da Fase 3.4.1 e deve ser mantido.
- Webhook/reconciliacao: ja existem com associacao por UUID substituto e `nfse_substituida`.
- Idempotencia: `nfse_substitution` ja foi validada com tentativa antes do POST, `uncertain` bloqueante e sem retry automatico.

Riscos e ajustes:

- `NfseSubstitutionPreview` atual foi criada para original ligada ao fluxo legado e pode depender de `NfseRequest`/OS em consultas, forms ou templates; a proxima fase deve adaptar elegibilidade para `NfseManualEmission.nfse_item` sem acoplar a OS.
- A NFS-e manual precisa ter `codigo_verificacao` confiavel; sem ele, a substituicao deve ser bloqueada porque o contrato efetivo usa `codigo_verificacao`.
- O novo RPS pode ser congelado com seguranca se seguir o mesmo padrao de preview imutavel, sem recompor dados a partir de cadastros mutaveis.
- O XML da emissao manual nao pode ser sobrescrito pela consulta/substituicao; XML original, XML substituto e eventual payload de substituicao devem ficar separados.
- A substituicao cria nova NFS-e; portanto o risco e maior que manifestacao/cancelamento, mas a infraestrutura ja reduz bastante a superficie nova.

Decisao tecnica: a substituicao da NFS-e manual deve ser **A) extensao segura do fluxo atual de substituicao NFS-e**, nao um fluxo paralelo especifico vinculado diretamente a `NfseManualEmission`.

### Avaliacao especifica da manifestacao da NFS-e manual

A manifestacao da NFS-e manual e tecnicamente possivel somente quando:

- a NFS-e manual for Padrao Nacional confirmado;
- `NfseMunicipalCapability.national_standard_enabled=True`;
- `NfseMunicipalCapability.manifestation_enabled=True`;
- houver UUID ou chave/identificador seguro;
- o papel fiscal da oficina como tomador ou intermediario estiver claro.

O reaproveitamento direto de `NfseManifestation` e provavel, mas a fase deve ser adiada porque a manifestacao tem maior risco de papel fiscal: uma NFS-e emitida manualmente pela propria oficina normalmente representa prestador/emissor, enquanto a manifestacao do Padrao Nacional depende de participacao como tomador ou intermediario. Sem NFS-e recebida/importada, a utilidade da manifestacao sobre uma NFS-e manual propria pode ser menor e mais sensivel.

Decisao: tratar como extensao pequena de elegibilidade somente apos confirmar Padrao Nacional e papel fiscal. Se o objetivo for manifestar documentos recebidos, priorizar antes NFS-e recebida/importada.

### Avaliacao especifica de NFS-e recebida/importada

A base local ainda nao e suficiente para importar NFS-e recebida com seguranca. Lacunas:

- nao ha fluxo de upload/importacao de XML NFS-e recebido;
- nao ha validacao local completa de UUID/chave/codigo de verificacao para terceiro;
- nao ha identificacao segura de tomador/prestador contra oficina ativa;
- nao ha associacao auditavel a cliente/oficina sem risco cross-workshop;
- nao ha reconciliacao de documento recebido sem emissao propria;
- manifestacao posterior dependeria de papel fiscal e Padrao Nacional confirmados.

Decisao: preparar NFS-e recebida/importada apenas em fase documental propria, com matriz de XML, identidade, papel fiscal, tenancy e manifestacao posterior. Nao e o menor risco imediato.

### Decisao

Escolher **Opcao A - Implementar substituicao da NFS-e manual** como proximo bloco funcional, em subfase propria, porque:

- e a continuidade natural do ciclo da NFS-e manual apos preview, emissao e cancelamento;
- reaproveita `NfseSubstitutionPreview`, `NfseSubstitution`, `POST /2/nfse/substituir`, idempotencia, webhook, reconciliacao, XML separado e testes existentes;
- exige ajuste pequeno de elegibilidade para aceitar `NfseItem` originado por `NfseManualEmission`;
- gera alto valor de negocio sem abrir nova familia fiscal nem introduzir NFS-e recebida/importada;
- mantem riscos fiscais sob controle por preview imutavel e bloqueios ja conhecidos.

Manifestacao da NFS-e manual fica adiada por depender de Padrao Nacional e papel fiscal mais claro. NFS-e recebida/importada deve ser planejada separadamente antes de manifestacao de documentos de terceiros. CT-e, MDF-e, NFCom, DC-e, eventos IBS/CBS pendentes, creditos/debitos restantes e complementar tributaria continuam adiados.

### Escopo proposto da proxima fase - Substituicao da NFS-e Manual

Tipo de implementacao: **A) extensao segura do fluxo atual de substituicao NFS-e**.

- Objetivo: permitir substituicao de NFS-e manual autorizada, vinculada a `NfseManualEmission.nfse_item`, consumindo uma preview imutavel de substituicao e criando uma nova `NfseItem` substituta.
- Endpoint: `POST /2/nfse/substituir` com `ambiente`, `codigo_verificacao`, `motivo` e `rps` congelado; nao enviar payload de emissao manual, payload de cancelamento ou campos livres.
- Modelagem: reutilizar `NfseSubstitutionPreview` e `NfseSubstitution`; adaptar vinculos/elegibilidade para original manual sem exigir `NfseRequest` quando houver `NfseManualEmission`; nao criar `FiscalDocument(nfse)`.
- Operacao/idempotencia: reutilizar `FiscalEmissionAttempt(operation_type="nfse_substitution")`; uma chamada por preview aprovada; `sent/succeeded/uncertain` bloqueiam reenvio.
- Permissoes: manter separacao entre preparar/aprovar preview e executar substituicao; `substitute_nfse` continua necessaria; `issue_nfse_manual_emission` e `cancel_nfse` nao substituem.
- Feature flag/capability: exigir `NfseMunicipalCapability.substitution_enabled=True`, capability ativa/coerente com empresa/oficina e flag administrativa de substituicao.
- UI minima: permitir preparar substituicao a partir do detalhe da emissao manual autorizada; exibir original manual, novo RPS, motivo, confirmacao, status, original/substituta, payload e downloads protegidos.
- Webhook/reconciliacao: resolver por UUID da substituta ou por `nfse_substituida` coerente com original manual; ambiguidade fica pendente; reconciliacao usa somente GET e nunca repete POST.
- Downloads/payload: preservar XML original manual; armazenar XML/PDF substituto separadamente; payload e resposta sanitizados e escopados por oficina.
- Bloqueios obrigatorios: NFS-e sem UUID/codigo verificacao, nao autorizada, cancelada, ja substituida, incerta, com cancelamento/substituicao ativa ou incerta, outra oficina, sem permissao, capability/flag desligada, preview nao aprovada ou payload mutavel.
- Testes planejados: elegibilidade manual; bloqueio de original inelegivel; preview imutavel com origem manual; POST exato sem `uuid` e sem payload da emissao manual; criacao de substituta; XML original preservado; webhook/reconciliacao sem re-POST; `uncertain`; duplicidade; permissao; cross-workshop; regressao de substituicao legada, cancelamento manual, manifestacao e emissao manual.
- Criterios de aceite: substituicao manual reutiliza o fluxo NFS-e existente; preview/emissao manual permanecem imutaveis; original manual so vira substituida com confirmacao remota; substituta possui `NfseItem` proprio; nenhuma NFS-e recebida/importada, manifestacao manual, CT-e/MDF-e/NFCom/DC-e, evento IBS/CBS, credito/debito ou complementar tributaria e iniciada.

OpenAPI: o schema atual permanece suficiente; nenhuma correcao oficial nova foi confirmada nesta reavaliacao.

## Fase 3.9.1 - Substituicao da NFS-e Manual Nova

Status: **validada tecnicamente em 2026-06-29**, com checkpoint criado nesta entrega. A Fase 3.9.0 foi validada documentalmente no checkpoint `21d684e7`.

Escopo: substituir somente NFS-e manual nova gerada por `NfseManualEmission`, materializada em `NfseItem` autorizado, com UUID, codigo de verificacao e XML original preservado.

Estrategia implementada: **A) extensao segura do fluxo atual de substituicao NFS-e**. Foram reutilizados `NfseSubstitutionPreview`, `NfseSubstitution`, `FiscalEmissionAttempt(operation_type="nfse_substitution")`, endpoint `POST /2/nfse/substituir`, webhook e reconciliacao ja existentes.

Fora de escopo nesta fase: manifestacao da NFS-e manual nova, NFS-e recebida/importada, emissao manual adicional, CT-e, MDF-e, NFCom, DC-e, eventos IBS/CBS `112120/112140/211xxx`, creditos 2-5, debitos 1-3/5-8 e complementar tributaria.

Resultado local:

- elegibilidade de preview/substituicao adaptada para aceitar `NfseManualEmission.nfse_item`;
- capability manual validada por `NfseManualEmission.preview.municipal_capability.substitution_enabled`;
- bloqueio de original manual sem UUID, codigo de verificacao, XML, autorizacao, capability, flag, permissao ou com cancelamento/substituicao ativa/incerta;
- payload remoto permanece exatamente o payload aprovado da preview: `ambiente`, `codigo_verificacao`, `motivo`, `rps`;
- substituta criada como nova `NfseItem` somente apos confirmacao remota valida;
- original manual marcada como `substituido` somente apos confirmacao remota valida;
- XML original da emissao manual preservado; XML/PDF da substituta separados;
- UI minima no detalhe da emissao manual para preparar substituicao elegivel.

Criterios atendidos: fluxo paralelo nao criado; `FiscalDocument(nfse)` nao criado; manifestacao manual nao iniciada; NFS-e recebida/importada nao iniciada; webhook/reconciliacao nao repetem POST; testes direcionados e regressoes NFS-e passaram.

## Fase 3.10.0 - Reavaliacao da Manifestacao da NFS-e Manual

Status: **em planejamento documental em 2026-06-29**. A Fase 3.9.1 foi validada e encerrada no checkpoint `99254f33`.

Escopo autorizado: somente documentacao em `docs/fiscal-webmania/**`. Nenhum codigo funcional, migration, service, view, template ou teste deve ser alterado nesta fase.

### Revalidacao e contexto

A manifestacao NFS-e ja existe no Hunter por `NfseManifestation` e `operation_type="nfse_manifestation"`, restrita a Padrao Nacional, com idempotencia, webhook e reconciliacao consultiva. A documentacao oficial Webmania NFS-e revalidada em 2026-06-29 continua tratando `POST /2/nfse/manifestar` como manifestacao de participacao no Padrao Nacional, por tomador ou intermediario.

A Fase 3.9.1 deixou a NFS-e manual substituivel, mas nao mudou o papel fiscal da oficina. A NFS-e manual emitida pelo sistema normalmente e documento emitido pela propria oficina prestadora, nao documento recebido contra ela.

### Matriz de elegibilidade

| Documento | Elegivel para manifestacao? | Pre-condicoes | Bloqueios | Risco |
| --------- | --------------------------: | ------------- | --------- | ----- |
| NFS-e manual autorizada Padrao Nacional | Nao nesta fase | UUID seguro, autorizada, `national_standard_enabled`, `manifestation_enabled`, papel tomador/intermediario confirmado | papel fiscal nao confirmado para nota emitida pela propria oficina | Alto |
| NFS-e manual substituta Padrao Nacional | Nao nesta fase | substituicao sucedida, `replacement_nfse` autorizada, UUID seguro, Padrao Nacional confirmado | mesmo risco fiscal da original manual; substituta tambem e emitida pela oficina | Alto |
| NFS-e manual cancelada | Nao | N/A | documento terminal | Alto |
| NFS-e manual substituida | Nao | N/A | original encerrada por substituicao | Alto |
| NFS-e manual uncertain | Nao | reconciliacao previa | estado remoto inconclusivo | Alto |
| NFS-e manual sem UUID | Nao | N/A | identificador inseguro para webhook/reconciliacao | Alto |
| NFS-e manual sem Padrao Nacional confirmado | Nao | N/A | endpoint oficial restrito ao Padrao Nacional | Alto |
| NFS-e recebida/importada de terceiros | Nao nesta fase | exigiria XML/UUID/chave, papel fiscal e tenancy | dominio local inexistente | Alto |
| NFS-e legada municipal | Nao | N/A | sem Padrao Nacional confirmado | Medio/alto |

### Decisao

Escolher **Opcao B - adiar manifestacao da NFS-e manual**.

Justificativa: a infraestrutura atual e tecnicamente reaproveitavel, mas ainda ha ambiguidade fiscal sobre manifestar uma NFS-e que a propria oficina emitiu. O contrato oficial fala em tomador/intermediario. Sem prova local do papel da oficina, uma fase funcional poderia permitir manifestacao indevida.

### Proxima fase recomendada

Nao autorizar `Fase 3.10.1 - Manifestacao da NFS-e Manual` ainda. A proxima fase documental recomendada e avaliar **NFS-e recebida/importada de terceiros**, porque esse fluxo tende a possuir aderencia fiscal mais clara ao papel de tomador/intermediario, mas depende de dominio de importacao, XML, identidade remota, associacao a oficina e bloqueio cross-workshop.

Se, mesmo assim, uma fase futura de manifestacao manual for aprovada, ela deve ser **A) extensao segura de `NfseManifestation` existente**, nunca fluxo paralelo, e deve exigir: Padrao Nacional confirmado, capability ativa, UUID seguro, papel fiscal explicito, permissao `issue_nfse_manifestation`, payload restrito, idempotencia `nfse_manifestation`, webhook por UUID da manifestacao e reconciliacao sem POST.

### Roadmap curto

| Bloco | Status | Recomendacao |
| ----- | ------ | ------------ |
| NFS-e recebida/importada | nao iniciada | preparar fase documental antes de manifestacao de terceiros |
| NFS-e expandida | nao iniciada | quebrar por subfases apos identidade/importacao |
| CT-e | nao iniciada | adiar ate dominio operacional proprio |
| MDF-e | nao iniciada | adiar ate CT-e/MDF-e terem fonte local |
| NFCom | nao iniciada | adiar; confirmar relevancia e feature flag |
| DC-e | nao iniciada | adiar; API v2.0.0 exige dominio proprio |
| Eventos IBS/CBS 112120/112140/211xxx | adiados | reavaliar depois dos eventos ja validados |
| Creditos 2-5 | adiados | manter bloqueados ate fonte fiscal suficiente |
| Debitos 1-3 e 5-8 | adiados | manter bloqueados ate fonte fiscal suficiente |
| Complementar tributaria | adiada | exige auditoria propria de base tributaria |

## Fase 3.12.1 - Manifestacao de NFS-e Recebida

Status: **validada em 2026-06-29** no checkpoint `6cc3a788`. A Fase 3.12.0 foi validada documentalmente no checkpoint `a5b4f4b`.

Escopo autorizado: manifestar somente `NfseReceivedDocument` validado, papel `taker` ou `intermediary`, por `POST /2/nfse/manifestar`, reutilizando `NfseManifestation` e `FiscalEmissionAttempt(operation_type="nfse_manifestation")`.

Fora de escopo: manifestacao da NFS-e manual, emissao, cancelamento ou substituicao de recebida, consulta Webmania como fonte de importacao, lote, e-mail/ERP, CT-e, MDF-e, NFCom, DC-e, eventos IBS/CBS pendentes, creditos/debitos pendentes e complementar tributaria.

Criterios de aceite validados: payload remoto restrito a `ambiente`, `uuid`, `manifestador`, `evento`, `motivo_rejeicao` e `justificativa_rejeicao`; somente roles `taker`/`intermediary`; Padrao Nacional e capability de manifestacao exigidos; idempotencia por documento/evento/manifestador; webhook/reconciliacao sem repetir POST; XML recebido e dados extraidos imutaveis; nenhum `NfseItem`; nenhum `FiscalDocument(nfse)`.

Implementacao: `NfseManifestation.received_document` com constraint de origem unica, migration `0070_remove_nfsemanifestation_unique_active_nfse_manifestation_and_more.py`, capability segura para recebido, service `manifest_nfse_received_document`, UI minima no detalhe de `NfseReceivedDocument`, payload/download protegidos e testes `FiscalPhaseThreeNfseReceivedManifestationTests`.

Validacao executada: migration check, 69 testes fiscais direcionados de NFS-e recebida/manifestacao/manual/cancelamento/substituicao, Ruff nos Python tocados e `git diff --check`. `mypy .` nao foi executado nesta fase por nao ser bloqueante e por baseline amplo preexistente registrado nas fases anteriores.

OpenAPI: nenhuma alteracao aplicada.

## Fase 3.13.0 - Reavaliacao do Roadmap apos Fechamento do Bloco NFS-e

Status: **validada documentalmente em 2026-06-29** no checkpoint `d83b37dc`. A Fase 3.12.1 foi validada e encerrada no checkpoint `6cc3a788`.

Escopo autorizado: somente `docs/fiscal-webmania/**` e, se houver correcao oficialmente confirmada, `docs/fiscal-webmania/api/webmania_fiscal_openapi_validated.json`. Nenhum codigo funcional, migration, service, view, template ou teste deve ser alterado nesta fase.

### Contexto implementado

O bloco NFS-e passou a conter cancelamento NFS-e legada, substituicao NFS-e, manifestacao NFS-e Padrao Nacional, preview de emissao manual NFS-e, emissao manual NFS-e, cancelamento da NFS-e manual, substituicao da NFS-e manual, registro de NFS-e recebida por XML e manifestacao de NFS-e recebida. A Fase 3.12.1 estendeu `NfseManifestation` com origem por `NfseReceivedDocument`, criou a migration `0070`, preservou payload restrito para `POST /2/nfse/manifestar`, implementou bloqueios por papel fiscal, UUID, XML/hash, status, Padrao Nacional, capability e duplicidade, e confirmou ausencia de `NfseItem` e `FiscalDocument(nfse)` no fluxo de recebidas. A manifestacao da NFS-e manual permanece adiada por risco fiscal de papel do manifestador.

### Matriz comparativa

| Bloco | Fonte local existe? | Contrato Webmania claro? | Reaproveita infraestrutura atual? | Dependencia externa | Risco fiscal | Valor de negocio | Recomendacao |
| ----- | ------------------: | -----------------------: | --------------------------------: | ------------------- | ------------ | ---------------- | ------------ |
| Consulta Webmania para apoiar NFS-e recebida | Sim: `NfseReceivedDocument` validado por XML, UUID/identificador e company | Sim para `GET /2/nfse/consulta/{identifier}` e `GET /2/nfse/status`, mas retorno nao substitui XML | Alta: consulta, status municipal, sanitizacao, permissao e reconciliacao consultiva ja existem em NFS-e | API Webmania e disponibilidade do identificador remoto | Medio se for somente consultiva; alto se criar/reescrever documento | Alto | Recomendar proxima fase consultiva |
| Importacao em lote de XML de NFS-e recebida | Sim por arquivo unitario; lote ainda nao existe | N/A para upload local; contrato externo nao e necessario | Alta: parser XML, hash, duplicidade e validacao de papel ja existem | Tamanho de upload, UX de relatorio e processamento parcial | Medio/alto por cross-workshop, lote misto e falha parcial | Alto | Adiar para depois da consulta auxiliar ou planejar subfase propria |
| Integracao futura com e-mail/ERP para XML de NFS-e | Nao; origem externa ainda nao modelada | N/A; depende de provedores e protocolos externos | Media: parser XML poderia ser reaproveitado, mas pipeline nao existe | Autenticacao, anexos, ERP/e-mail, filas e seguranca operacional | Alto por documento errado, anexo adulterado e identidade externa | Medio/alto | Adiar; exige fase preparatoria propria |
| Manifestacao da NFS-e manual | Parcial: UUID e `NfseItem` existem quando manual autorizada | Sim para manifestacao, mas papel fiscal da oficina nao esta claro | Alta: `NfseManifestation` ja suporta origem local e recebida | Confirmacao juridico/fiscal de papel tomador/intermediario em nota propria | Alto | Medio | Manter adiada |
| NFS-e expandida | Parcial: legado/manual/recebida existem, mas `FiscalDocument(nfse)` generalizado nao | Parcial: varios endpoints claros, mas variacao municipal/Padrao Nacional permanece | Media/alta por services NFS-e existentes | Backfill, convivencia legado/manual/recebida, provedores municipais | Alto | Muito alto | Nao abrir bloco amplo; quebrar em auditoria/subfases |
| CT-e | Nao; nao ha dominio operacional de transporte/carga | Sim em alto nivel, mas exige modelagem propria | Media tecnica para idempotencia/webhook/downloads; baixa de dominio | Transporte, tomador, remetente/destinatario, veiculos, carga e documentos | Alto | Baixo/medio | Adiar |
| MDF-e | Nao; depende de CT-e/NF-e/logistica | Sim em alto nivel | Baixa/media | CT-e/NF-e vinculados, veiculo, condutor, percurso e encerramento | Alto | Baixo | Adiar ate dominio logistico/CT-e |
| NFCom | Nao | Sim; API v2.0.0 documentada | Media tecnica | Dominio de comunicacao/telecom, credenciamento e demanda especifica | Alto | Muito baixo | Adiar; manter feature flag interna |
| DC-e | Nao | Sim; API v2.0.0 documentada | Media tecnica | Dominio especifico, demanda nao comprovada e documentos externos | Alto | Muito baixo | Adiar |
| Eventos IBS/CBS 112120 | Nao suficiente | Sim em matriz anterior, mas depende de contexto fiscal especifico | Alta tecnica: eventos IBS/CBS ja existem | ALC/ZFM, importacao, XML/projecao fiscal e contexto de isencao | Alto | Baixo | Adiar |
| Eventos IBS/CBS 112140 | Nao suficiente | Sim em matriz anterior, mas depende de contexto fiscal especifico | Alta tecnica | Informacoes fiscais por item e evento ainda nao modeladas | Alto | Baixo | Adiar |
| Eventos IBS/CBS 211xxx | Nao suficiente | Parcial; familia ampla e sem prioridade definida | Media/alta tecnica, baixa de dominio | Regras especificas por evento, bases e documentos relacionados | Alto | Baixo/medio | Adiar; exigir auditoria propria |
| Creditos 2-5 | Parcial: base de credito tipo 1 existe, mas fontes dos demais tipos nao | Parcial por tipo | Media/alta tecnica: preview/emissao/cancelamento tipo 1 existem | Fonte local fiscal/monetaria por tipo e IBS/CBS exclusivo | Alto | Medio | Adiar |
| Debitos 1-3 e 5-8 | Parcial: debito tipo 4 existe, mas demais tipos nao | Parcial por tipo | Media/alta tecnica: preview/emissao/cancelamento tipo 4 existem | Fonte local fiscal/monetaria por tipo e referencias | Alto | Medio | Adiar |
| Complementar tributaria | Nao suficiente | Parcial; complementar atual cobre preco/quantidade, nao tributos | Media: `FiscalDocument`/links/tentativas existem | Base tributaria historica, IBS/CBS, XML original e regras por imposto | Alto | Medio/alto | Adiar ate auditoria tributaria |

### Avaliacoes especificas

Consulta Webmania para NFS-e recebida: `GET /2/nfse/consulta/{identifier}` pode apoiar status remoto, URLs e reconciliacao de uma NFS-e recebida ja validada por XML, desde que o identificador seja seguro e o retorno seja tratado como informativo. `GET /2/nfse/status` pode apoiar confirmacao de capacidade municipal e Padrao Nacional, mas nao deve substituir a capability local ja validada nem criar autorizacao automatica. A consulta pode atualizar campos consultivos como `remote_status`, snapshots de resposta e timestamps de reconciliacao, mas nao deve substituir `xml_snapshot`, `xml_hash`, CNPJs, papel fiscal ou dados extraidos do XML. A consulta nao deve criar documento recebido sozinha, nao deve criar manifestacao, nao deve criar `NfseItem` e nao deve criar `FiscalDocument(nfse)`.

Importacao em lote de XML: reaproveita o parser unitario, hash, UUID/identificador e validacao de papel fiscal, mas exige UX de lote, limites de tamanho, relatorio por arquivo, importacao parcial segura e tratamento claro de rollback. O risco principal e misturar XMLs de outra oficina/empresa, duplicidades parciais e falhas no meio do lote. E viavel, mas deve vir em subfase propria depois de estabilizar consulta auxiliar ou com planejamento especifico.

Integracao e-mail/ERP: permanece adiada. A origem dos XMLs exigiria autenticacao externa, leitura de anexos, validacao de remetente, protecao contra anexos adulterados, pipeline assincrono e observabilidade operacional. O parser local pode ser reaproveitado, mas a origem esta fora do dominio fiscal imediato.

Manifestacao da NFS-e manual: nada mudou o suficiente para liberar. A manifestacao recebida resolveu o caso em que a oficina e tomadora/intermediaria validada por XML de terceiro; uma NFS-e manual emitida pela propria oficina continua presumindo papel de prestadora/emissora. Sem confirmacao oficial/juridica de papel fiscal valido, permanece adiada.

NFS-e expandida: nao deve ser aberta como bloco amplo. Qualquer expansao deve ser quebrada em subfase documental/preparatoria, provavelmente para mapear convivencia entre legado, manual, recebida e eventual `FiscalDocument(nfse)` sem backfill prematuro.

CT-e, MDF-e, NFCom e DC-e: devem permanecer adiados. Embora haja contratos Webmania em alto nivel, nao existe fonte local operacional suficiente no produto para transporte/carga/logistica, comunicacao/telecom ou dominios especificos. Implementar qualquer familia agora abriria modulo fiscal grande sem fonte local deterministica.

IBS/CBS, creditos/debitos e complementar tributaria: o fechamento NFS-e nao reduz as dependencias fiscais desses blocos. Eventos `112120`, `112140` e `211xxx` ainda dependem de contexto fiscal especifico, bases por item e regras fora do fluxo NFS-e. Creditos 2-5 e debitos 1-3/5-8 ainda dependem de fontes locais por tipo. Complementar tributaria ainda exige auditoria de base tributaria historica, XML/projecao fiscal e regras por imposto.

### Decisao

Escolher **Opcao A - Implementar consulta/reconciliacao auxiliar para NFS-e recebida** como proxima fase funcional pequena, desde que permaneça estritamente consultiva.

Justificativa: o bloco recebido agora possui fonte local suficiente (`NfseReceivedDocument` validado por XML), UUID/identificador, company, oficina, XML/hash e papel fiscal. O contrato de consulta/status e pequeno e reaproveita infraestrutura NFS-e ja validada. O valor de negocio e real porque reduz incerteza operacional antes/depois de manifestacao, mas o risco fiscal fica controlado se a consulta nao criar documento, nao substituir XML e nao disparar manifestacao.

### Escopo proposto da proxima fase - Consulta/Reconciliacao Auxiliar para NFS-e Recebida

- Objetivo: consultar/reconciliar `NfseReceivedDocument` ja validado por XML, usando identificador remoto seguro, para atualizar somente informacoes consultivas de status remoto e resposta de consulta.
- Endpoint: `GET /2/nfse/consulta/{identifier}` para documento recebido existente; `GET /2/nfse/status` apenas como apoio de capability/status municipal quando aplicavel.
- Modelagem: adicionar, se necessario, campos consultivos em `NfseReceivedDocument` ou entidade historica leve para snapshot de consulta, timestamp remoto/local e ultima resposta sanitizada. Nao criar `NfseItem` e nao criar `FiscalDocument(nfse)`.
- Idempotencia: consulta e GET-only; nao precisa de `FiscalEmissionAttempt`. Se houver registro de execucao, deve ser historico consultivo, sem bloquear importacao/manifestacao salvo estado remoto terminal/incerto confirmado.
- Permissoes: reutilizar/estender permissoes de visualizacao/consulta de NFS-e recebida, sem permitir que permissoes de manifestacao, emissao, cancelamento ou substituicao acionem consulta automaticamente.
- Feature flag/capability: usar `nfse_received_import_enabled` como gate do modulo recebido e capability municipal/status apenas como informacao de apoio; nao substituir `national_standard_enabled` e `manifestation_enabled` usados na manifestacao.
- UI minima: acao no detalhe da NFS-e recebida para consultar status, exibir ultima consulta sanitizada, data da consulta e divergencias com o XML validado.
- Webhook/reconciliacao: reconciliacao deve ser somente GET, sem POST, sem criacao automatica de documentos e sem manifestacao automatica. Webhook sem documento previo permanece pendente/fora de escopo.
- Bloqueios explicitos: nao cria documento recebido sem XML; nao substitui XML validado; nao altera hash; nao altera CNPJs/papel fiscal extraidos; nao cria manifestacao automaticamente; nao cria `NfseItem`; nao cria `FiscalDocument(nfse)`; nao consulta documento de outra oficina.
- Testes planejados: consulta de recebido validado atualiza apenas status/snapshot consultivo; consulta nao altera XML/hash/dados extraidos; consulta bloqueia cross-workshop; consulta sem UUID/identificador seguro bloqueia; status remoto cancelado/substituido e registrado sem cancelar/substituir localmente por inferencia destrutiva; permissao exigida; payload/resposta sanitizados; reconciliacao GET-only nao chama POST; importacao e manifestacao recebida nao regridem.
- Riscos: retorno Webmania insuficiente, divergencia entre XML validado e consulta, status municipal por provedor nao confiavel para todos os municipios, ambiguidade de identificador e expectativa de usuario de que consulta substitua importacao.
- Criterios de aceite: consulta auxiliar implementada sem fonte primaria nova; nenhum documento recebido e criado sem XML; XML validado permanece fonte de verdade; nenhuma manifestacao automatica; nenhuma emissao/cancelamento/substituicao; nenhum `NfseItem`; nenhum `FiscalDocument(nfse)`; testes determinísticos com gateway mockado.

OpenAPI: o schema atual permanece suficiente; nenhuma correcao oficial nova foi confirmada nesta reavaliacao.

## Fase 3.13.1 - Consulta/Reconciliacao Auxiliar para NFS-e Recebida

Status: **validada em 2026-06-29** no checkpoint `01f0924d`. A Fase 3.13.0 foi validada documentalmente no checkpoint `d83b37dc`.

Escopo autorizado: implementar consulta GET-only para `NfseReceivedDocument` ja registrado por XML validado. A consulta deve ser apoio consultivo e nao pode criar documento recebido sem XML, substituir XML/hash/dados fiscais extraidos, manifestar automaticamente, criar `NfseItem`, criar `FiscalDocument(nfse)` ou executar emissao, cancelamento ou substituicao.

Modelagem planejada: preferir entidade propria de snapshot consultivo (`NfseReceivedDocumentConsultation` ou equivalente), preservando `NfseReceivedDocument` como fonte primaria imutavel.

Criterios de aceite cumpridos: consulta por identificador seguro; resposta sanitizada; divergencias registradas sem sobrescrita; permissoes especificas; feature flag propria; UI minima no detalhe da recebida; nenhuma regressao da importacao XML ou da manifestacao de recebida.

Validacao tecnica: migration `0071`; testes focados `FiscalPhaseThreeNfseReceivedConsultationTests`; bateria fiscal direcionada com importacao XML, manifestacao recebida, consulta recebida e fluxos NFS-e manuais/legados; `makemigrations finance --check --dry-run`; Ruff nos Python tocados; `git diff --check`.

Implementacao validada: `NfseReceivedDocumentConsultation`, flag `WebmaniaCompany.nfse_received_consultation_enabled`, consulta GET-only, divergencias consultivas sem sobrescrita destrutiva, preservacao de XML/hash/dados extraidos, ausencia de manifestacao automatica, ausencia de `NfseItem` e ausencia de `FiscalDocument(nfse)`.

## Fase 3.14.0 - Reavaliacao apos NFS-e Recebida Completa

Status: **validada documentalmente em 2026-06-29** no checkpoint `18d1840d`. A Fase 3.13.1 foi validada e encerrada no checkpoint `01f0924d`.

Escopo autorizado: somente `docs/fiscal-webmania/**` e OpenAPI validado apenas se houver correcao oficialmente confirmada. Nenhum codigo funcional, migration, service, view, template ou teste deve ser alterado nesta fase.

### Contexto implementado

O bloco NFS-e recebida agora possui registro local por XML, manifestacao de NFS-e recebida e consulta/reconciliacao auxiliar GET-only. O registro por XML criou a fonte local primaria (`NfseReceivedDocument`) com XML snapshot/hash e dados extraidos. A manifestacao recebida estendeu `NfseManifestation` sem criar `NfseItem` ou `FiscalDocument(nfse)`. A consulta auxiliar criou `NfseReceivedDocumentConsultation`, migration `0071` e flag `nfse_received_consultation_enabled`, mantendo o retorno Webmania como snapshot consultivo separado.

### Matriz comparativa

| Bloco | Fonte local existe? | Contrato Webmania claro? | Reaproveita infraestrutura atual? | Dependencia externa | Risco fiscal | Valor de negocio | Recomendacao |
| ----- | ------------------: | -----------------------: | --------------------------------: | ------------------- | ------------ | ---------------- | ------------ |
| Importacao em lote de XML de NFS-e recebida | Sim: parser unitario, `NfseReceivedDocument`, hash, UUID/identificador e papel fiscal ja existem | N/A, pois o lote deve ser upload local de XML | Alta: reaproveita parser, validacao, duplicidade, permissoes, XML protegido e UI de recebidas | Baixa/media: tamanho de upload, armazenamento temporario e UX de lote | Medio, controlavel com validacao por arquivo e bloqueio cross-workshop | Alto | Recomendar como proxima fase funcional |
| Integracao futura com e-mail/ERP para XML de NFS-e | Parcial: parser XML existe, mas origem externa nao | N/A para e-mail/ERP; depende de provedores externos | Media: reaproveita parser, mas exige pipeline novo | Alta: autenticacao, anexos, caixas, ERP, filas e monitoramento | Alto por origem incorreta e anexo adulterado | Medio/alto | Adiar; exigir fase preparatoria propria |
| Consulta Webmania como apoio futuro ampliado | Sim: `NfseReceivedDocument` e `NfseReceivedDocumentConsultation` existem | Sim para `GET /2/nfse/consulta/{identifier}` e `/2/nfse/status` | Alta para reconciliacao consultiva | API Webmania e disponibilidade de identificador | Medio se continuar consultiva; alto se virar fonte primaria | Medio | Manter como apoio; nao usar para criar recebida sem XML |
| Manifestacao da NFS-e manual | Parcial: NFS-e manual autorizada possui UUID/`NfseItem` | Sim para manifestacao, mas papel fiscal da oficina em nota propria segue inseguro | Alta tecnica: `NfseManifestation` existe | Confirmacao fiscal/juridica externa | Alto | Medio | Manter adiada |
| NFS-e expandida | Parcial: legado, manual e recebida existem; consolidacao geral nao | Parcial: endpoints claros, mas variacao municipal permanece | Media/alta | Provedores municipais, backfill e convivencia de origens | Alto | Alto | Nao abrir amplo; se retomada, fazer subfase documental |
| CT-e | Nao: falta dominio operacional de transporte/carga | Sim em alto nivel | Media tecnica, baixa de dominio | Alta: remetente, destinatario, veiculo, carga, entrega | Alto | Baixo/medio | Adiar |
| MDF-e | Nao: depende de logistica, veiculos, condutor e documentos vinculados | Sim em alto nivel | Baixa/media | Alta: CT-e/NF-e, percurso, encerramento | Alto | Baixo | Adiar |
| NFCom | Nao: nao ha dominio de comunicacao/telecom no produto | Sim; API v2.0.0 documentada | Media tecnica | Alta: credenciamento e dominio especializado | Alto | Muito baixo | Adiar; manter feature flag interna futura |
| DC-e | Nao: nao ha dominio local especifico | Sim; API v2.0.0 documentada | Media tecnica | Alta: documento externo e demanda nao comprovada | Alto | Muito baixo | Adiar |
| Eventos IBS/CBS 112120 | Nao suficiente: falta contexto ALC/ZFM/importacao fiscal por item | Sim/parcial ja mapeado | Alta tecnica pelos eventos ja validados, baixa de dominio | Alta: ALC/ZFM, estoque, item fiscal e isencao | Alto | Baixo | Adiar |
| Eventos IBS/CBS 112140 | Nao suficiente: falta pagamento antecipado fiscal e nao fornecimento por item | Sim/parcial ja mapeado | Alta tecnica, baixa de dominio | Alta: nota de debito/pagamento antecipado/item | Alto | Baixo | Adiar |
| Eventos IBS/CBS 211xxx | Nao suficiente | Parcial; familia ampla e sem fonte local definida | Media | Alta: papel destinatario, documentos externos e apuracao | Alto | Baixo/medio | Adiar; exigir auditoria propria |
| Creditos 2-5 | Parcial: ciclo credito tipo 1 existe, mas fontes dos demais tipos nao | Parcial por tipo | Media/alta | Media/alta: fonte fiscal e monetaria por tipo | Alto | Medio | Adiar |
| Debitos 1-3 e 5-8 | Parcial: debito tipo 4 existe, mas demais tipos nao | Parcial por tipo | Media/alta | Media/alta: referencias e fontes por tipo | Alto | Medio | Adiar |
| Complementar tributaria | Nao suficiente: complemento atual nao cobre tributos | Parcial | Media | Alta: base tributaria historica, IBS/CBS e regras por imposto | Alto | Medio/alto | Adiar ate auditoria tributaria |

### Avaliacoes especificas

Importacao em lote de XML de NFS-e recebida: e o menor proximo passo com fonte local suficiente. Reaproveita o parser XML unitario, `NfseReceivedDocument`, hash, UUID/identificador, validacao de papel fiscal, permissao de recebidas e protecao de XML/payload. Deve validar cada arquivo isoladamente, detectar duplicidade por hash, UUID e identificador, gerar relatorio por arquivo, permitir importacao parcial segura, limitar quantidade/tamanho, bloquear cross-workshop e nunca substituir XML validado de documento existente. Rollback total nao deve ser regra padrao quando parte do lote for valida; a decisao recomendada e persistir os arquivos validos e registrar erros dos invalidos no relatorio do lote.

Integracao e-mail/ERP: deve permanecer adiada. Embora possa alimentar o mesmo parser XML no futuro, a origem dos XMLs exige autenticacao, permissoes, tratamento de anexos, seguranca contra documentos errados, filas/pipeline assincrono, observabilidade e regras de duplicidade fora do dominio fiscal imediato. E-mail/ERP deve entrar somente apos o lote local por XML estar validado.

Consulta Webmania ampliada: permanece apoio consultivo. A Fase 3.13.1 ja implementou GET-only com snapshot separado; ampliar esse apoio pode ser util para relatorios e reconciliacao, mas nao deve virar fonte de criacao de NFS-e recebida sem XML nem disparar manifestacao.

Manifestacao da NFS-e manual: permanece adiada. A NFS-e manual emitida pela oficina nao prova, por si, que a oficina possa manifestar como tomadora ou intermediaria. Sem confirmacao fiscal clara, liberar isso criaria risco maior que valor imediato.

NFS-e expandida: nao ha recomendacao para fase ampla. Qualquer retomada deve ser documental/preparatoria e mapear convivencia entre legado, manual, recebida e eventual consolidacao `FiscalDocument(nfse)`, sem backfill prematuro.

CT-e, MDF-e, NFCom e DC-e: permanecem adiados. Os contratos Webmania existem em alto nivel, mas faltam fontes locais operacionais e dominios de produto para transporte, logistica, comunicacao/telecom ou documentos especificos.

IBS/CBS, creditos/debitos e complementar tributaria: o fechamento de NFS-e recebida nao resolve as dependencias desses blocos. Eventos `112120`, `112140` e `211xxx` ainda exigem fontes fiscais por item e contexto operacional especifico. Creditos 2-5, debitos 1-3/5-8 e complementar tributaria continuam dependentes de auditorias por tipo/regra tributaria.

### Decisao

Escolher **Opcao A - Implementar importacao em lote de XML de NFS-e recebida** como proxima fase funcional, em subfase propria apos esta reavaliacao.

Justificativa: e o bloco com melhor combinacao de fonte local existente, reaproveitamento de infraestrutura validada, escopo pequeno/preparatorio, valor de produto e testes deterministicos. Ele fortalece o dominio recebido sem depender de inferencia fiscal fragil, sem criar documento por consulta Webmania, sem abrir familia fiscal nova e sem alterar documentos ja registrados.

### Escopo proposto da proxima fase - Fase 3.14.1 Importacao em Lote de XML de NFS-e Recebida

- Objetivo: permitir upload de multiplos XMLs de NFS-e recebida, processando cada arquivo de forma independente e gerando relatorio de sucesso/erro por arquivo.
- Endpoint: nao ha endpoint Webmania; entrada local por formulario/upload de arquivos XML.
- Modelagem: reaproveitar `NfseReceivedDocument`; se necessario, criar entidade leve de lote/resultado para auditoria do processamento e relatorio por arquivo. Nao criar documento recebido sem XML.
- Idempotencia: bloquear duplicidades por hash, UUID e identificador dentro da oficina/empresa; tratar duplicidade dentro do proprio lote como erro do arquivo duplicado, sem substituir documento existente.
- Permissoes: permissao especifica para importacao em lote de recebidas, separada de manifestacao, consulta e payload.
- Feature flag/capability: usar `nfse_received_import_enabled`; nao exigir capability Webmania para importar XML local; capability de manifestacao continua separada.
- UI minima: tela de upload multiplo, resumo de processados/importados/ignorados/com erro, download/visualizacao de relatorio e links para documentos criados.
- Webhook/reconciliacao: nenhum webhook e nenhuma consulta automatica nesta fase. Consulta Webmania continua acao manual/consultiva ja validada.
- Testes planejados: lote com todos validos; lote com validos e invalidos; duplicidade por hash, UUID e identificador; duplicidade no mesmo lote; XML de outra oficina/empresa bloqueado; limite de tamanho/quantidade; relatorio por arquivo; importacao parcial sem rollback dos validos; XML/payload protegido; nenhuma manifestacao automatica; nenhuma chamada Webmania; nenhum `NfseItem`; nenhum `FiscalDocument(nfse)`.
- Riscos: consumo de memoria em lotes grandes, UX de erro pouco clara, arquivos malformados, duplicidade parcial, XML de empresa errada e expectativa de rollback total.
- Criterios de aceite: usa apenas XML; nao cria documento recebido sem XML; nao substitui XML validado de documento existente; nao manifesta automaticamente; nao consulta Webmania automaticamente; nao cria `NfseItem`; nao cria `FiscalDocument(nfse)`; gera relatorio por arquivo; bloqueia duplicidades e cross-workshop; testes determinísticos cobrem falhas parciais.

OpenAPI: nenhuma alteracao. A proxima fase recomendada e importacao local por XML e nao depende de novo endpoint Webmania.

## Fase 3.14.1 - Importacao em Lote de XML de NFS-e Recebida

Status: **validada em 2026-06-29** no checkpoint `b53e862b`. A Fase 3.14.0 foi validada documentalmente no checkpoint `18d1840d`.

Escopo implementado: importacao local de multiplos XMLs de NFS-e recebida, com lote e itens persistidos, relatorio por arquivo, importacao parcial segura, duplicidade por hash/UUID/identificador, limites conservadores e reaproveitamento do parser/importador unitario.

Modelagem implementada: `NfseReceivedImportBatch` e `NfseReceivedImportBatchItem`, migration `0072`. O lote registra oficina, empresa, origem XML, status, totais, duplicados, erros e usuario. Cada item registra arquivo, hash, status, documento recebido quando importado, erro, validacoes e resumo parseado.

Limites implementados: ate 20 arquivos por lote, 2 MB por XML e 20 MB no total; extensao `.xml`, conteudo iniciado por XML e arquivo nao vazio.

Permissoes implementadas: `import_nfse_received_batch` e `view_nfse_received_batch`, separadas de consulta e manifestacao. A flag reaproveitada e `nfse_received_import_enabled`, porque o lote e extensao conservadora da importacao XML local.

Criterios de aceite cumpridos: usa apenas XML; nao cria documento sem XML; nao sobrescreve XML validado; nao consulta Webmania automaticamente; nao manifesta automaticamente; nao cria `NfseItem`, `FiscalDocument(nfse)` ou `FiscalEmissionAttempt`; gera relatorio por arquivo; bloqueia duplicidades e cross-workshop; testes determinísticos cobrem falhas parciais.

Validacao tecnica: `makemigrations finance --check --dry-run` OK; `FiscalPhaseThreeNfseReceivedBatchImportTests` com 6 testes OK; bateria fiscal direcionada com 79 testes OK; Ruff nos Python tocados OK.

## Fase 3.15.0 - Reavaliacao do Roadmap apos Consolidacao de NFS-e Recebida

Status: **validada documentalmente em 2026-06-29** no checkpoint `4815728b`. A Fase 3.14.1 foi validada e encerrada no checkpoint `b53e862b`.

Escopo autorizado: somente `docs/fiscal-webmania/**` e OpenAPI validado apenas se houver correcao oficialmente confirmada. Nenhum codigo funcional, migration, service, view, template ou teste deve ser alterado nesta fase.

### Contexto implementado

O bloco NFS-e recebida agora possui registro unitario por XML, manifestacao de NFS-e recebida, consulta/reconciliacao auxiliar GET-only e importacao em lote de XML. A base local consolidada inclui XML/hash/dados extraidos, papel fiscal, duplicidades, lote persistido e relatorio por arquivo. Consulta Webmania continua apoio consultivo e nao fonte primaria. Manifestacao automatica continua proibida.

### Matriz comparativa

| Bloco | Fonte local existe? | Contrato Webmania claro? | Reaproveita infraestrutura atual? | Dependencia externa | Risco fiscal | Valor de negocio | Recomendacao |
| ----- | ------------------: | -----------------------: | --------------------------------: | ------------------- | ------------ | ---------------- | ------------ |
| Integracao futura com e-mail/ERP para XML de NFS-e | Parcial: parser, lote XML e documentos recebidos existem; origem externa nao | N/A para e-mail/ERP; Webmania nao participa da origem | Alta para ingestao XML; baixa/media para conectores externos | Alta: caixas, ERP, autenticacao, anexos, filas e observabilidade | Alto se importar origem errada; medio se for apenas fase preparatoria | Alto | Recomendar fase preparatoria/documental |
| Consulta Webmania ampliada para NFS-e recebida | Sim: consulta GET-only ja existe | Sim para `GET /2/nfse/consulta/{identifier}` e `/2/nfse/status` | Alta | API Webmania e identificador seguro | Medio; alto se usuario esperar substituicao do XML | Medio | Manter como apoio; adiar automacao |
| Manifestacao da NFS-e manual | Parcial: NFS-e manual possui UUID/`NfseItem` | Contrato de manifestacao claro, papel fiscal nao | Alta tecnica | Confirmacao fiscal/juridica de papel tomador/intermediario | Alto | Medio | Manter adiada |
| NFS-e expandida | Parcial: legado, manual e recebida consolidados; `FiscalDocument(nfse)` ainda nao | Parcial; varios endpoints claros com variacao municipal | Media/alta | Backfill, convivencia de origens, municipio/provedor | Alto | Alto | Nao abrir bloco amplo; exigir subfase documental |
| CT-e | Nao | Sim em alto nivel | Media tecnica; baixa de dominio | Transporte, carga, remetente, destinatario, veiculos | Alto | Baixo/medio | Adiar |
| MDF-e | Nao | Sim em alto nivel | Baixa/media | Logistica, veiculo, condutor, documentos vinculados | Alto | Baixo | Adiar |
| NFCom | Nao | Sim; API v2.0.0 mapeada | Media tecnica | Dominio comunicacao/telecom e credenciamento | Alto | Muito baixo | Adiar |
| DC-e | Nao | Sim; API v2.0.0 mapeada | Media tecnica | Dominio especifico e demanda nao comprovada | Alto | Muito baixo | Adiar |
| Eventos IBS/CBS 112120 | Nao suficiente | Parcial/confirmado em matriz anterior | Alta tecnica, baixa de dominio | ALC/ZFM, importacao fiscal por item e contexto de isencao | Alto | Baixo | Adiar |
| Eventos IBS/CBS 112140 | Nao suficiente | Parcial/confirmado em matriz anterior | Alta tecnica, baixa de dominio | Pagamento antecipado, nota de debito e nao fornecimento por item | Alto | Baixo/medio | Adiar |
| Eventos IBS/CBS 211xxx | Nao suficiente | Parcial; familia ampla | Media | Papel destinatario, documentos externos, estoque ou apuracao | Alto | Baixo/medio | Adiar; exigir auditoria propria |
| Creditos 2-5 | Parcial: credito tipo 1 existe | Parcial por tipo | Media/alta | Fonte fiscal/monetaria por tipo | Alto | Medio | Adiar |
| Debitos 1-3 e 5-8 | Parcial: debito tipo 4 existe | Parcial por tipo | Media/alta | Fonte fiscal/monetaria por tipo; debito 6 liga ao 112140 | Alto | Medio | Adiar |
| Complementar tributaria | Nao suficiente | Parcial | Media | Base tributaria historica, XML/projecao fiscal e regras por imposto | Alto | Medio/alto | Adiar ate auditoria tributaria |

### Avaliacoes especificas

Integracao e-mail/ERP: deve virar somente fase preparatoria/documental. O valor de negocio e claro porque o lote XML local ja existe e oficinas podem receber XMLs por canais externos. Porem a origem dos XMLs exige autenticacao, permissoes, anexos, seguranca contra documento errado, tratamento de duplicidade, auditoria, fila/job e observabilidade. Implementar pipeline real agora abriria dependencia fora do dominio fiscal. A proxima fase deve desenhar fontes, riscos, contratos internos e limites antes de qualquer conector.

Consulta Webmania ampliada: o GET atual e suficiente para consulta manual e historico consultivo. Rotina automatica/agendada pode ter valor, mas traz risco de usuario interpretar retorno como substituto do XML. Deve continuar apenas apoio, nao fonte primaria, e qualquer automacao deve ser posterior a politicas de reconciliacao claras.

Manifestacao da NFS-e manual: permanece adiada. A oficina emissora/prestadora nao tem papel de tomadora/intermediaria confirmado para manifestar a propria NFS-e manual.

NFS-e expandida: ha infraestrutura ampla, mas nao ha subescopo funcional pequeno sem risco de consolidacao/backfill. Se retomada, deve ser nova fase documental para convivencia entre legado, manual, recebida e eventual `FiscalDocument(nfse)`.

CT-e, MDF-e, NFCom e DC-e: permanecem adiados. Ha contratos Webmania em alto nivel, mas faltam fontes locais operacionais e dominio de produto para transporte, logistica, comunicacao/telecom ou documentos especificos.

IBS/CBS, creditos/debitos e complementar tributaria: a consolidacao NFS-e recebida nao resolve as fontes fiscais desses blocos. `112120` segue dependente de ALC/ZFM/importacao fiscal por item; `112140` depende de pagamento antecipado e debito/nao fornecimento; `211xxx` depende de papel destinatario e documentos externos. Creditos 2-5, debitos 1-3/5-8 e complementar tributaria continuam exigindo auditorias por tipo.

### Decisao

Escolher **Opcao A - Planejar integracao e-mail/ERP para XML de NFS-e** como proxima fase, estritamente **preparatoria/documental**, sem implementar pipeline real ainda.

Justificativa: depois de registro unitario, manifestacao, consulta e lote XML, a maior lacuna operacional do bloco recebido e a origem dos XMLs. Uma fase preparatoria agrega valor sem risco fiscal imediato, define fronteiras de autenticacao/anexos/fila/auditoria e impede que e-mail/ERP seja implementado como atalho inseguro para importar documento errado.

### Escopo proposto da proxima fase - Fase 3.15.1 Planejamento de Integracao E-mail/ERP para XML NFS-e

- Objetivo: planejar pipeline futuro para receber XMLs de NFS-e por e-mail/ERP e alimentar o lote XML validado.
- Endpoint: nenhum Webmania; conectores externos a definir documentalmente.
- Modelagem: mapear fontes, credenciais, anexos, fila/job, deduplicacao, auditoria e relacao com `NfseReceivedImportBatch`.
- Idempotencia: planejar fingerprint por fonte/anexo/hash e deduplicacao antes do parser.
- Permissoes: planejar permissoes separadas para configurar origem externa, visualizar caixa/fila e aprovar processamento.
- Feature flag/capability: planejar flag propria para integracao externa, separada de `nfse_received_import_enabled`.
- UI minima: planejamento de tela de fontes, fila de anexos, erros, reprocessamento e vinculo a lotes.
- Webhook/reconciliacao: nenhum webhook fiscal; e-mail/ERP deve apenas fornecer XML ao pipeline local.
- Testes planejados: mocks de origem externa, anexos validos/invalidos, duplicidade, permissao, fila, isolamento por oficina e garantia de que nao ha chamada Webmania/manifestacao automatica.
- Riscos: credenciais, anexos adulterados, documento de outra oficina, importacao silenciosa indevida, LGPD/dados sensiveis, volume alto e reprocessamento.
- Criterios de aceite: fase documental sem codigo funcional; nenhuma integracao real; nenhuma chamada remota; nenhuma importacao automatica; plano seguro para fase funcional futura.

OpenAPI: nenhuma alteracao. A fase recomendada nao depende de endpoint Webmania novo.

## Fase 3.15.1 - Planejamento de Integracao E-mail/ERP para XML NFS-e

Status: **em planejamento documental em 2026-06-29**. A Fase 3.15.0 foi validada documentalmente e encerrada no checkpoint `4815728b`.

Escopo autorizado: somente documentacao em `docs/fiscal-webmania/**` e OpenAPI apenas se houver correcao oficial confirmada. Nenhum codigo funcional, migration, service, view, template ou teste deve ser alterado nesta fase.

### Objetivo

Planejar uma futura integracao para entrada de XMLs de NFS-e recebida a partir de fontes externas: e-mail, ERP, armazenamento externo e outros sistemas operacionais da oficina. A fase define arquitetura, riscos, fronteiras, contratos internos e criterios de aceite antes de qualquer implementacao real.

### Principio central

A fonte externa nao e fonte fiscal autonoma. Ela apenas entrega arquivos XML candidatos ao dominio local. O pipeline validado de XML continua sendo o nucleo fiscal: XML como fonte primaria, importacao unitaria/lote como fronteira fiscal, validacoes de `NfseReceivedDocument`, duplicidade por hash/UUID/identificador, bloqueio cross-workshop, sem manifestacao automatica, sem consulta Webmania automatica e sem documento recebido sem XML.

### Matriz de fontes externas

| Fonte | Como receber XML | Autenticacao | Risco | Recomendacao |
| ----- | ---------------- | ------------ | ----- | ------------ |
| Caixa de e-mail dedicada por oficina | Ler anexos XML de conta exclusiva | OAuth/IMAP com credencial por oficina | Credencial externa, anexo adulterado, volume e retencao | Boa candidata futura; exigir inbox pendente e revisao humana |
| Caixa de e-mail compartilhada | Ler anexos de conta comum a varias oficinas/empresas | OAuth/IMAP central com regras de roteamento | Alto risco de cross-workshop e CNPJ errado | Evitar como primeira implementacao; usar somente com segregacao forte |
| Encaminhamento manual de e-mail | Usuario baixa ou encaminha anexos para a plataforma | Sessao do usuario e permissao local | Menor automacao, erro humano no anexo | Aceitavel como transicao, mas deve cair na mesma caixa pendente |
| IMAP/Gmail API/Microsoft Graph | Coleta programatica de anexos | OAuth com escopos minimos, revogacao e rotacao | Dependencia externa, consentimento, paginacao e duplicidade por mensagem | Planejar depois da inbox; nao implementar nesta fase |
| ERP com exportacao manual | Usuario exporta XML do ERP e envia ao Hunter | Permissao local do usuario | Arquivo errado, origem nao auditada | Manter como fallback via upload/lote ou inbox manual |
| ERP com API | Conector busca XMLs em endpoint do ERP | Token por oficina/empresa, escopos minimos | Contrato variavel, indisponibilidade e identidade da empresa | Adiar ate existir contrato concreto de ERP |
| Pasta monitorada/Drive/SharePoint | Coletar arquivos de pasta configurada | OAuth/credencial por pasta e oficina | Arquivos mistos, path traversal, permissao ampla | Somente com allowlist e revisao humana |
| Upload manual como fallback | Usuario seleciona XMLs no fluxo existente | Permissao `import_nfse_received_batch` | Baixo, ja controlado pelo lote | Manter como nucleo operacional validado |
| Webhook externo, se existir | Sistema externo envia XML candidato | Assinatura/token, allowlist e rate limit | Spoofing, payload grande, importacao silenciosa | Aceitar apenas para criar item pendente; nunca importar direto |

### Matriz de arquitetura

| Arquitetura | Descricao | Vantagem | Risco | Recomendacao |
| ----------- | --------- | -------- | ----- | ------------ |
| Importacao manual assistida a partir de anexos | Usuario coleta anexos e envia ao lote ou inbox | Simples, sem credencial externa | Pouca automacao | Manter como fallback e caminho de baixo risco |
| Conector e-mail com fila | Job coleta anexos de caixas configuradas e cria itens pendentes | Alto valor para oficinas com volume | Credenciais, spoofing, duplicidade por mensagem | Fase futura apos inbox local |
| Conector ERP com fila | Job busca XMLs em API/exportacao ERP e cria itens pendentes | Automatiza origem operacional | Contratos variaveis por ERP | Adiar ate contrato conhecido |
| Pasta monitorada | Coleta arquivos de Drive/SharePoint/pasta externa | Facil para operacao | Arquivos indevidos e permissao ampla | Usar apenas com allowlist e limites |
| Job agendado | Executa coleta periodica de fontes configuradas | Observavel e controlavel | Reprocessamento e falhas parciais | Planejar com idempotencia antes de implementar |
| Importacao sob demanda pelo usuario | Usuario aciona coleta de uma fonte configurada | Controle humano e menor risco | Menos automatica | Preferivel para primeira implementacao funcional |
| Pipeline assincrono completo | Coleta, valida, enfileira, revisa e importa em background | Escala melhor | Maior complexidade operacional | Adiar; nao e a proxima fase funcional minima |

### Contrato interno planejado

Modelo conceitual recomendado: `NfseExternalXmlInbox` e `NfseExternalXmlInboxItem`, ou nomes equivalentes.

Campos planejados para item externo: `workshop`, `company`, `source_type`, `source_identifier`, `original_filename`, `content_type`, `xml_snapshot`, `xml_hash`, `received_at`, `status`, `validation_errors`, `linked_batch`, `linked_received_document`, `created_at` e `updated_at`.

Estados planejados: `pending_review`, `approved_for_batch`, `imported`, `discarded`, `rejected`, `duplicate` e `error`.

O item externo pendente nao e documento fiscal. Ele so pode virar documento recebido quando aprovado e processado pelo lote/importador XML validado.

### Relacao com lote XML

Decisao: escolher **B - caixa de entrada pendente para usuario revisar e acionar lote**.

Motivo: a criacao automatica de lote a partir dos XMLs coletados aumentaria o risco de importacao silenciosa, CNPJ/oficina errada, anexo adulterado e expectativa de manifestacao automatica. A inbox pendente preserva revisao humana e reaproveita `NfseReceivedImportBatch`, `NfseReceivedImportBatchItem`, parser XML, duplicidade, validacao de papel fiscal, relatorio por arquivo, limites e permissoes.

### Seguranca, autenticacao e limites

Controles planejados: bloquear anexo adulterado, e-mail spoofado, remetente nao confiavel, XML de outra oficina, XML de outro CNPJ, ZIP inseguro, arquivo grande demais, arquivo duplicado, arquivo nao XML, malware/executavel, path traversal, exposicao indevida de XML fiscal, cross-workshop e permissoes fracas.

Autenticacao planejada: OAuth para Gmail/Microsoft quando aplicavel, credenciais por oficina/empresa, conta dedicada, escopos minimos, revogacao, rotacao, auditoria de acesso e segregacao por oficina.

Auditoria planejada: fonte, data/hora de recebimento, usuario ou job, remetente ou sistema externo, hash do XML, vinculo com lote, vinculo com documento recebido, descartes, erros e reprocessamentos.

Idempotencia planejada: hash XML, identificador fiscal, identificador externo da fonte, id da mensagem de e-mail quando houver, fingerprint de anexo e `source_identifier`.

Limites planejados: quantidade maxima de anexos por e-mail, tamanho maximo por XML, tamanho maximo por mensagem, quantidade maxima por execucao, frequencia de job, retencao de itens rejeitados e retencao de XMLs descartados.

### UX, permissoes e flags planejadas

Telas futuras: configurar fonte externa, visualizar caixa de entrada, ver origem/remetente/sistema, revisar XML antes da importacao, descartar item, enviar para lote, visualizar erros, historico e desativar fonte externa.

Permissoes planejadas: `configure_nfse_external_xml_source`, `view_nfse_external_xml_inbox`, `process_nfse_external_xml_inbox`, `discard_nfse_external_xml_inbox` e `view_nfse_external_xml_payload`.

Decisao: `import_nfse_received_batch` nao deve processar a caixa externa sozinha. A inbox precisa de permissao separada; o lote fiscal permanece governado por permissao propria.

Flags planejadas: `nfse_external_xml_inbox_enabled`, `nfse_email_xml_import_enabled` e `nfse_erp_xml_import_enabled`. As flags devem ser por oficina/empresa quando envolverem fonte ou credencial externa; uma flag global pode existir como kill switch operacional.

### Decisao

Escolher **Opcao A - Implementar caixa de entrada externa de XML** como proxima recomendacao funcional futura, mas a fase 3.15.1 permanece apenas documental/preparatoria.

Justificativa tecnica/fiscal: a inbox local cria fronteira clara entre origem operacional e dominio fiscal. E-mail, ERP, pasta externa ou webhook podem fornecer XML candidato, mas o documento recebido so nasce pelo pipeline validado de XML/lote. Isso reduz risco de credenciais, spoofing, anexo adulterado, documento de outra oficina e importacao silenciosa.

### Escopo da proxima fase funcional sugerida

Objetivo: implementar a caixa de entrada externa manual/assistida de XML, sem conector real de e-mail/ERP ainda.

Escopo planejado: modelagem `NfseExternalXmlInbox`/`NfseExternalXmlInboxItem` ou equivalente, permissoes e flags separadas, tela de inbox/detalhe, validacao basica de arquivo XML candidato, hash/fingerprint, status pendente, descarte auditavel, envio manual de itens aprovados ao lote XML, vinculo com `NfseReceivedImportBatch`/`NfseReceivedDocument` e auditoria.

Fora de escopo da proxima fase funcional: conector real IMAP/Gmail/Microsoft, conector ERP real, pasta monitorada real, webhook externo real, pipeline assincrono completo, importacao automatica, consulta Webmania automatica, manifestacao automatica e qualquer criacao de `NfseItem`, `FiscalDocument(nfse)` ou `FiscalEmissionAttempt`.

### Testes planejados

- registra XML candidato vindo de fonte externa;
- bloqueia arquivo nao XML;
- bloqueia arquivo grande;
- bloqueia XML duplicado;
- bloqueia XML de outra oficina;
- mantem item pendente ate revisao;
- envia item aprovado para lote;
- nao cria documento recebido diretamente sem pipeline validado;
- nao manifesta automaticamente;
- nao consulta Webmania automaticamente;
- nao cria `NfseItem`;
- nao cria `FiscalDocument(nfse)`;
- verifica permissoes de configuracao;
- verifica permissoes de processamento;
- bloqueia cross-workshop;
- registra auditoria;
- permite reprocessamento idempotente.

### Criterios de aceite documentais

- Fase 3.15.0 marcada como validada no checkpoint `4815728b`.
- Matriz de fontes externas documentada.
- Matriz de arquitetura documentada.
- Contrato interno planejado documentado.
- Relacao com lote XML definida como inbox pendente com revisao humana.
- Permissoes, flags, auditoria, idempotencia, limites e testes planejados documentados.
- OpenAPI Webmania mantido sem alteracao.
- Nenhum codigo funcional, migration, service, view, template ou teste alterado.

## Fase 3.15.2 - Caixa de Entrada Externa de XML para NFS-e Recebida

Status: **em implementacao controlada em 2026-06-30**. A Fase 3.15.1 foi validada documentalmente e encerrada no checkpoint `5882cd4e`.

Escopo autorizado: inbox local/manual/assistida para XMLs candidatos. Conectores reais de e-mail/ERP, IMAP, Gmail API, Microsoft Graph, pasta monitorada, webhook externo real, job agendado, pipeline assincrono completo, consulta Webmania automatica, manifestacao automatica, documento sem XML, `NfseItem`, `FiscalDocument(nfse)` e `FiscalEmissionAttempt` permanecem fora de escopo.

Implementacao prevista nesta fase: `NfseExternalXmlInbox`, `NfseExternalXmlInboxItem`, flag `nfse_external_xml_inbox_enabled`, service local, forms, views, rotas, templates, testes e documentacao. O processamento deve reaproveitar `NfseReceivedImportBatch` e vincular item da inbox ao item de lote/documento quando houver sucesso.

Criterios de aceite: item candidato nao cria documento fiscal; item aprovado nao cria documento fiscal; somente processamento humano envia aprovados ao lote XML; duplicidades e cross-workshop sao bloqueados; payload/XML e protegido por permissao; nenhuma chamada Webmania automatica e feita.

## Fase 3.16.0 - Reavaliacao apos Inbox Externa de XML NFS-e

Status: **em planejamento documental em 2026-06-30**. A Fase 3.15.2 foi validada e encerrada no checkpoint `517d25b8`.

Escopo autorizado: somente documentacao em `docs/fiscal-webmania/**` e OpenAPI apenas se houver correcao oficial confirmada. Nenhum codigo funcional, migration, service, view, template ou teste deve ser alterado nesta fase.

### Contexto implementado

O bloco NFS-e recebida possui registro unitario por XML, manifestacao de NFS-e recebida, consulta/reconciliacao auxiliar GET-only, importacao em lote de XML, caixa de entrada externa local/manual/assistida e processamento da inbox via lote XML validado.

Implementado e validado no checkpoint `517d25b8`: `NfseExternalXmlInbox`, `NfseExternalXmlInboxItem`, migration `0073`, flag `nfse_external_xml_inbox_enabled`, upload manual/assistido de XMLs candidatos, aprovacao humana, descarte com motivo/auditoria, processamento de aprovados via `NfseReceivedImportBatch` e vinculo com lote, item de lote e `NfseReceivedDocument`. Permanecem ausentes conectores reais de e-mail/ERP, consulta Webmania automatica, manifestacao automatica, documento recebido sem XML, `NfseItem`, `FiscalDocument(nfse)` e `FiscalEmissionAttempt`.

### Matriz comparativa

| Bloco | Fonte local existe? | Contrato externo claro? | Reaproveita infraestrutura atual? | Dependencia externa | Risco fiscal/seguranca | Valor de negocio | Recomendacao |
| ----- | ------------------: | ----------------------: | --------------------------------: | ------------------- | ---------------------- | ---------------- | ------------ |
| Conector real de e-mail para XML NFS-e | Parcial: inbox local existe; origem e-mail real nao | Nao; IMAP/Gmail/Microsoft/OAuth nao definidos | Alta via inbox/lote | Alta: conta, OAuth/IMAP, message-id, anexos | Alto sem segregacao por oficina e revogacao claras | Alto | Adiar; exigir fase propria de autenticacao/segregacao |
| Conector real de ERP para XML NFS-e | Parcial: inbox local existe; ERP real nao | Nao; nenhum ERP/contrato definido | Alta via inbox/lote | Alta: API/token/exportacao por ERP | Alto por CNPJ errado e contrato variavel | Medio/alto | Adiar ate ERP especifico |
| Pasta monitorada/Drive/SharePoint | Parcial: inbox local existe | Parcial; depende de provedor | Alta via inbox/lote | Media/alta: OAuth/pasta/permissoes | Alto por arquivo adulterado e acesso amplo | Medio | Adiar; nao e mais simples que melhorar inbox local |
| Webhook externo de XML | Parcial: inbox local existe | Nao; assinatura/payload ausentes | Alta via inbox/lote | Alta: origem externa, assinatura, rate limit | Alto por spoofing e importacao silenciosa | Medio | Adiar; apenas futuro item pendente de inbox |
| Ampliacao da inbox externa local | Sim: `NfseExternalXmlInbox` implementado | N/A | Muito alta | Baixa | Baixo/medio, controlavel por permissoes | Alto operacional | **Recomendar Opcao D** |
| Consulta Webmania ampliada para NFS-e recebida | Sim: documentos XML e consulta GET-only existem | Sim para GET/status | Alta | API Webmania | Medio; risco de virar fonte primaria indevida | Medio | Manter consultiva; nao criar por consulta |
| Manifestacao da NFS-e manual | Parcial: NFS-e manual local existe | Endpoint claro, papel fiscal nao | Alta tecnica | Confirmacao fiscal/juridica | Alto por papel de manifestador inseguro | Medio | Manter adiada |
| NFS-e expandida | Parcial: legado/manual/recebida existem | Parcial; varios endpoints | Media/alta | Backfill e convivencia de origens | Alto em bloco amplo | Alto | Adiar; se retomada, subfase documental propria |
| CT-e | Nao | Sim em alto nivel | Baixa/media | Transporte/carga/documentos | Alto | Baixo/medio | Adiar |
| MDF-e | Nao | Sim em alto nivel | Baixa/media | Logistica/veiculo/condutor | Alto | Baixo | Adiar |
| NFCom | Nao | Sim; API mapeada | Media tecnica, baixa dominio | Comunicacao/telecom | Alto | Muito baixo | Adiar |
| DC-e | Nao | Sim; API mapeada | Media tecnica, baixa dominio | Dominio especifico | Alto | Muito baixo | Adiar |
| Eventos IBS/CBS 112120 | Nao suficiente | Parcial | Alta tecnica, baixa fonte fiscal | ALC/ZFM/importacao fiscal por item | Alto | Baixo | Adiar |
| Eventos IBS/CBS 112140 | Nao suficiente | Parcial | Alta tecnica, baixa fonte fiscal | Pagamento antecipado/debito/nao fornecimento | Alto | Baixo/medio | Adiar |
| Eventos IBS/CBS 211xxx | Nao suficiente | Parcial; familia ampla | Media | Papel destinatario/documentos externos | Alto | Baixo/medio | Adiar; exigir auditoria propria |
| Creditos 2-5 | Parcial: credito tipo 1 existe | Parcial por tipo | Media/alta | Fonte fiscal/monetaria por tipo | Alto | Medio | Adiar |
| Debitos 1-3 e 5-8 | Parcial: debito tipo 4 existe | Parcial por tipo | Media/alta | Fonte fiscal/monetaria por tipo | Alto | Medio | Adiar |
| Complementar tributaria | Nao suficiente | Parcial | Media | Base tributaria historica e regras por imposto | Alto | Medio/alto | Adiar ate auditoria tributaria |

### Avaliacoes especificas

Conector real de e-mail: deve permanecer adiado. Caixa dedicada por oficina e melhor que caixa compartilhada, mas ainda exige definicao de OAuth/IMAP/Gmail/Microsoft, escopos, revogacao, segregacao, message-id, remetente confiavel, anexos, limites, fila/job e observabilidade. Sem autenticacao e segregacao claras, o risco operacional e alto demais.

Conector ERP: deve permanecer adiado. Nao ha ERP especifico, API, formato de exportacao, token, periodicidade ou mapeamento por oficina/empresa. Sem contrato claro, a inbox receberia XMLs de origem insegura.

Pasta monitorada/Drive/SharePoint: nao deve ser a proxima fase. Parece simples, mas exige OAuth/permissao de pasta, segregacao por oficina, controle de origem, job e protecao contra arquivo adulterado. Deve passar pela inbox apenas em fase futura.

Webhook externo: apenas possibilidade futura. Sem assinatura, idempotencia, payload e auditoria definidos, webhook externo abre risco de origem falsa. Se existir no futuro, deve criar item pendente na inbox e nunca importar direto.

Ampliacao da inbox local: e o menor proximo bloco com valor real. Filtros, busca, relatorio/exportacao, acoes em massa, retencao, reprocessamento controlado, painel de auditoria e vinculos mais claros com lote/documento melhoram operacao sem introduzir credenciais externas.

Consulta Webmania ampliada: permanece apoio consultivo. Nao deve ser fonte de criacao de NFS-e recebida e nao deve substituir XML validado.

Manifestacao da NFS-e manual: manter adiada por papel fiscal inseguro da oficina como tomadora/intermediaria de documento emitido por ela propria.

NFS-e expandida: nao abrir fase ampla. Se retomada, deve ser nova fase documental com subescopo pequeno e convivencia entre legado, manual, recebida, lote e inbox.

CT-e, MDF-e, NFCom e DC-e: permanecem adiados por ausencia de fonte local operacional e por exigirem dominios de transporte, logistica, comunicacao ou documentos especificos.

IBS/CBS, creditos/debitos e complementar tributaria: a inbox NFS-e nao resolve fontes fiscais desses blocos. Eventos `112120`, `112140`, `211xxx`, creditos 2-5, debitos 1-3/5-8 e complementar tributaria continuam dependentes de auditoria por tipo.

### Decisao

Escolher **Opcao D - Ampliar inbox local** como proxima recomendacao funcional pequena.

Justificativa: a inbox local ja existe, nao depende de contrato externo, reaproveita `NfseExternalXmlInbox`, `NfseExternalXmlInboxItem`, `NfseReceivedImportBatch` e `NfseReceivedDocument`, tem baixo risco fiscal e aumenta valor operacional antes de qualquer conector real. Conectores de e-mail/ERP/pasta/webhook devem aguardar definicao de autenticacao, segregacao e contratos externos.

### Escopo proposto da proxima fase - Fase 3.16.1 Ampliacao Operacional da Inbox XML NFS-e

- Objetivo: melhorar operacao local da inbox sem conectores reais.
- Modelagem: preferir campos/metadados existentes; criar campos novos apenas se necessarios para retencao, reprocessamento ou auditoria.
- Permissoes: manter permissoes separadas de visualizar, enviar, aprovar, processar, descartar e payload; avaliar permissao para exportar relatorio se criada.
- Feature flags: continuar usando `nfse_external_xml_inbox_enabled`.
- UX: filtros, busca, relatorio/exportacao, acoes em massa com confirmacao, painel de auditoria e vinculos mais claros com lote/documento.
- Relacao com inbox/lote: nenhum item cria documento fiscal diretamente; aprovados continuam seguindo para `NfseReceivedImportBatch`.
- Validacoes: preservar duplicidade por hash/UUID/identificador, cross-workshop, arquivo inseguro, status invalido e item ja processado.
- Auditoria: evidenciar criacao, aprovacao, descarte, processamento, vinculo com lote/documento e erros.
- Testes: filtros/busca, exportacao se houver, acoes em massa, retencao/reprocessamento controlado, permissoes, cross-workshop e garantia de ausencia de Webmania/manifestacao automatica.
- Riscos: acoes em massa indevidas, exportacao de XML/payload sem permissao, reprocessamento duplicado e relatorios ambíguos.
- Criterios de aceite: nenhuma integracao externa real; nenhuma importacao automatica; nenhuma consulta Webmania automatica; nenhuma manifestacao automatica; nenhum documento sem XML; nenhum `NfseItem`, `FiscalDocument(nfse)` ou `FiscalEmissionAttempt`.

OpenAPI: nenhuma alteracao. A proxima fase recomendada e local e nao depende de endpoint Webmania novo.

## Fase 3.11.0 - Planejamento Tecnico da NFS-e Recebida/Importada de Terceiros

Status: **em planejamento documental em 2026-06-29**. A Fase 3.10.0 foi validada documentalmente no checkpoint `8d5c7192`.

Escopo autorizado: somente documentacao em `docs/fiscal-webmania/**` e OpenAPI apenas se houver correcao oficial confirmada. Nenhum codigo funcional, migration, service, view, template ou teste deve ser alterado nesta fase.

### Objetivo

Planejar dominio seguro para registrar NFS-e emitida por terceiros e recebida pela oficina antes de permitir qualquer manifestacao futura. O dominio deve responder: fonte confiavel, XML/UUID/chave/codigo, oficina correta, papel fiscal, duplicidade, cross-workshop e elegibilidade de manifestacao.

### Revalidacao oficial

Fonte oficial revalidada em 2026-06-29: documentacao Webmania NFS-e. A API REST confirma consulta por identificador/UUID, status/capabilities e manifestacao Padrao Nacional. Nao foi encontrado endpoint REST claro de importacao/sincronizacao de NFS-e recebida com XML completo e papel fiscal validado.

### Matriz de origem do documento

| Origem | Possui XML? | Possui UUID/chave? | Confianca | Risco | Recomendacao |
| ------ | ----------: | -----------------: | --------- | ----- | ------------ |
| Upload manual de XML | Sim | Normalmente sim | Alta apos parser/hash/validacao | XML falso, incompleto ou da propria oficina | Fonte inicial preferencial |
| Consulta Webmania por identificador | Nao garantido | Sim | Media | retorno insuficiente para papel fiscal | Complemento/reconciliacao |
| Webhook sem documento previo | Nao | Possivel | Baixa/media | oficina ambigua e sem XML | Pendenciar ate registro validado |
| Digitacao manual de UUID/chave/codigo | Nao | Sim | Baixa | erro humano e sem papel fiscal | Somente rascunho/consulta assistida |
| Importacao por lote | Sim, se lote XML | Normalmente sim | Alta apos validacao individual | duplicidade e falha parcial | Posterior ao fluxo unitario |
| E-mail/ERP futuro | Variavel | Variavel | Media | origem externa e anexos divergentes | Adiar; alimentar pipeline XML |

### Matriz de papel fiscal

| Papel da oficina | Como validar | Elegivel para manifestacao? | Risco | Observacao |
| ---------------- | ------------ | --------------------------: | ----- | ---------- |
| Tomador | CNPJ da empresa/oficina aparece como tomador no XML | Sim, depois de validado e Padrao Nacional confirmado | Medio | Usa `manifestador=1` |
| Intermediario | CNPJ aparece como intermediario no XML | Sim, depois de validado e Padrao Nacional confirmado | Medio/alto | Usa `manifestador=2`; campo pode faltar |
| Prestador | CNPJ aparece como prestador/emissor | Nao | Alto | Bloquear manifestacao; pode ser documento proprio |
| Desconhecido | CNPJ da oficina nao aparece em papel reconhecido | Nao | Alto | Requer correcao manual/administrativa |
| Multiplos papeis | CNPJ aparece em mais de um papel | Nao ate resolucao | Alto | Ambiguo; exigir decisao administrativa |
| CNPJ divergente | XML nao corresponde a empresa/oficina ativa | Nao | Alto | Bloquear cross-workshop |

### Decisao

Escolher **Opcao A - criar preview/registro local de NFS-e recebida**. Upload e validacao de XML sao a fonte mais segura para estabelecer identidade, hash, prestador, tomador/intermediario, municipio, ambiente e papel fiscal. Consulta por identificador deve ser apoio posterior, porque a documentacao oficial nao confirma importacao REST suficiente.

### Escopo da proxima fase proposta

Fase futura recomendada: `3.11.1 - Registro local de NFS-e recebida por XML`.

- Objetivo: criar `NfseReceivedDocument` local validado, sem manifestar.
- Dados congelados: XML snapshot, hash, UUID/chave/codigo, CNPJs, municipio, ambiente, valores, status e payload parseado.
- Modelagem: entidade propria, sem `NfseItem` e sem `FiscalDocument(nfse)`.
- Validacoes: XML, duplicidade, papel fiscal, oficina, municipio, ambiente, status terminal/incerto e documento proprio.
- Permissoes: `import_nfse_received`, `view_nfse_received`, `view_nfse_received_payload`, `download_nfse_received_xml`.
- Feature flag/capability: flag administrativa de importacao; manifestacao futura ainda exige `national_standard_enabled` e `manifestation_enabled`.
- UX: upload XML, resultado de validacao, divergencias, papel fiscal, status manifestavel/nao manifestavel, downloads protegidos.
- Testes: importacao valida, XML invalido, duplicidades, papeis, cross-workshop, documento proprio, payload/XML protegido e ausencia de criacao de `NfseItem`/`FiscalDocument(nfse)`.
- Criterios de aceite: documento recebido validado e auditavel, sem POST de manifestacao, sem alterar fluxos manuais/legados e com manifestacao futura bloqueada ate fase propria.

OpenAPI: nenhuma alteracao aplicada; nao ha schema oficial suficiente para importacao REST de NFS-e recebida.

## Fase 3.11.1 - Registro Local de NFS-e Recebida por XML

Status: **validada tecnicamente em 2026-06-29**. A Fase 3.11.0 foi validada documentalmente no checkpoint `6f36f7fc`.

Escopo: criar registro local unitario de NFS-e recebida/importada de terceiros a partir de upload manual de XML validado. Manifestacao de NFS-e recebida, manifestacao manual, emissao, cancelamento/substituicao de recebida, consulta Webmania como fonte unica, importacao em lote, e-mail/ERP, CT-e, MDF-e, NFCom, DC-e, eventos IBS/CBS pendentes, creditos/debitos pendentes e complementar tributaria permanecem fora do escopo.

Criterios de aceite: XML original preservado; hash e duplicidade validados; papel fiscal determinado com seguranca; acesso protegido por oficina/permissao; nenhuma chamada Webmania; nenhuma `NfseManifestation`; nenhum `NfseItem`; nenhum `FiscalDocument(nfse)`; nenhum `FiscalEmissionAttempt`.

Implementacao: `NfseReceivedDocument`, flag `WebmaniaCompany.nfse_received_import_enabled`, servico local `nfse_received`, form/view/templates de importacao/lista/detalhe/payload/XML e migration `0069_webmaniacompany_nfse_received_import_enabled_and_more.py`.

Validacao executada: nova classe `FiscalPhaseThreeNfseReceivedDocumentTests`, regressao das classes de manifestacao, emissao manual, cancelamento e substituicao NFS-e, `makemigrations --check --dry-run`, Ruff nos Python tocados e `git diff --check`. `mypy .` foi executado e permanece bloqueado por baseline amplo preexistente do projeto.

## Fase 3.12.0 - Reavaliacao da Manifestacao de NFS-e Recebida

Status: **em planejamento documental em 2026-06-29**. A Fase 3.11.1 foi validada e encerrada no checkpoint `b25ad698`; o checkpoint documental anterior da Fase 3.11.0 e `6f36f7fc`.

Escopo autorizado: somente documentacao em `docs/fiscal-webmania/**` e OpenAPI apenas se houver correcao oficial confirmada. Nenhum codigo funcional, migration, service, view, template ou teste deve ser alterado nesta fase.

### Contexto implementado pela Fase 3.11.1

`NfseReceivedDocument` foi implementado como registro local de NFS-e recebida por XML validado. A fase entregou `nfse_received_import_enabled`, snapshot/hash de XML, extracao de identificadores, CNPJs, municipio, ambiente, valor/status remoto, validacao de papel fiscal, duplicidade e protecao por oficina/permissao. O fluxo de importacao nao chama Webmania e confirmou ausencia de criacao de `NfseItem`, `FiscalDocument(nfse)`, `FiscalEmissionAttempt` e `NfseManifestation`.

### Revalidacao oficial Webmania

Fonte oficial revalidada em 2026-06-29: documentacao Webmania NFS-e em `https://webmania.com.br/docs/rest-api-nfse/`. `POST /2/nfse/manifestar` permanece documentado como manifestacao de participacao da NFS-e do Padrao Nacional. O contrato segue pequeno: ambiente, identificador remoto (`uuid` ou chave quando aplicavel), manifestador `1` tomador ou `2` intermediario, evento `1` confirmacao ou `2` rejeicao, e campos condicionais de rejeicao. Motivos aceitos continuam `1`, `2`, `3`, `4`, `5` e `9`; motivo `9` exige justificativa entre 15 e 255 caracteres; justificativa e proibida quando o motivo nao for `9`. Nao foi identificado endpoint oficial claro para desfazer/cancelar manifestacao.

Consulta/reconciliacao permanecem consultivas: usar `GET /2/nfse/consulta/{identifier}` somente quando houver UUID remoto seguro da manifestacao/documento, sem repetir `POST`. `/2/nfse/status` segue como base de capability municipal; localmente a regra segura continua exigir `national_standard_enabled=True` e `manifestation_enabled=True`.

OpenAPI: nenhuma alteracao aplicada; o schema atual ja cobre manifestacao, webhook `modelo=manifestacao_nfse`, consulta e status. Nao ha correcao oficial nova confirmada.

### Matriz de elegibilidade

| Documento recebido | Elegivel para manifestacao? | Pre-condicoes | Bloqueios | Risco |
| ------------------ | --------------------------: | ------------- | --------- | ----- |
| Validado como tomador | Sim, em fase funcional futura | `NfseReceivedDocument.validation_status=validated`, role `taker`, XML snapshot/hash, UUID seguro, oficina/empresa coerentes, Padrao Nacional e capability confirmados | cancelado, substituido, uncertain, duplicado, cross-workshop, sem UUID ou sem capability | Medio |
| Validado como intermediario | Sim, em fase funcional futura | Mesmo bloco anterior, role `intermediary`, manifestador `2` coerente | ausencia de CNPJ intermediario seguro, ambiguidade de papel, sem Padrao Nacional | Medio/alto |
| Validado como prestador | Nao | N/A | oficina e prestadora/emissora, nao tomadora/intermediaria | Alto |
| Papel desconhecido | Nao | N/A | CNPJ da oficina nao aparece em papel fiscal reconhecido | Alto |
| Multiplos papeis | Nao | N/A | oficina aparece em mais de um papel; manifestador ambiguo | Alto |
| CNPJ divergente | Nao | N/A | XML nao corresponde a empresa/oficina ativa ou cross-workshop | Alto |
| XML invalido | Nao | N/A | fronteira de confianca quebrada | Alto |
| XML ausente | Nao | N/A | sem snapshot/hash e sem prova de papel fiscal | Alto |
| Sem UUID/identificador seguro | Nao | N/A | payload e webhook/reconciliacao inseguros | Alto |
| Sem Padrao Nacional confirmado | Nao | N/A | endpoint oficial e restrito ao Padrao Nacional | Alto |
| Com Padrao Nacional confirmado | Depende do papel | role `taker` ou `intermediary`, capability ativa e UUID seguro | role `provider`, `unknown`, `multiple` ou status terminal | Medio |
| Cancelado | Nao | N/A | estado fiscal terminal | Alto |
| Substituido | Nao | N/A | documento original encerrado por substituicao | Alto |
| Uncertain | Nao | reconciliacao previa obrigatoria | estado remoto inconclusivo | Alto |
| Duplicado | Nao | N/A | duplicidade por hash, UUID ou identificador | Alto |
| Cross-workshop | Nao | N/A | violacao de tenancy/oficina | Alto |

### Matriz de evento e manifestador

| Evento | Manifestador | Campos obrigatorios | Elegivel para recebido? | Observacao |
| ------ | ------------ | ------------------- | ----------------------: | ---------- |
| Confirmacao | Tomador (`1`) | `ambiente`, `uuid`, `manifestador=1`, `evento=1` | Sim, se role `taker` | Nao enviar motivo ou justificativa |
| Confirmacao | Intermediario (`2`) | `ambiente`, `uuid`, `manifestador=2`, `evento=1` | Sim, se role `intermediary` | Nao enviar motivo ou justificativa |
| Rejeicao | Tomador (`1`) | `ambiente`, `uuid`, `manifestador=1`, `evento=2`, `motivo_rejeicao` | Sim, se role `taker` | Exige motivo oficial |
| Rejeicao | Intermediario (`2`) | `ambiente`, `uuid`, `manifestador=2`, `evento=2`, `motivo_rejeicao` | Sim, se role `intermediary` | Exige motivo oficial |
| Rejeicao motivo diferente de `9` | Tomador ou intermediario conforme role | Campos da rejeicao sem `justificativa_rejeicao` | Sim | Justificativa proibida |
| Rejeicao motivo `9` | Tomador ou intermediario conforme role | Campos da rejeicao + `justificativa_rejeicao` | Sim | Justificativa obrigatoria entre 15 e 255 caracteres |
| Justificativa obrigatoria | Tomador ou intermediario | `motivo_rejeicao=9` + justificativa valida | Sim | Falta de justificativa bloqueia antes do POST |
| Justificativa proibida | Tomador ou intermediario | `motivo_rejeicao` em `1..5` | Sim, sem justificativa | Qualquer justificativa deve bloquear |

### Decisao

Escolher **Opcao A - implementar manifestacao de NFS-e recebida** em fase funcional futura, com ajuste controlado do fluxo existente.

Justificativa: apos a Fase 3.11.1, `NfseReceivedDocument` validado fornece a prova local que faltava para documentos de terceiros: XML congelado, hash, CNPJs extraidos, papel fiscal, oficina, identificadores e duplicidade. A manifestacao deve ser permitida somente para roles `taker` e `intermediary`, com Padrao Nacional confirmado por capability segura e UUID remoto seguro. O fluxo atual `NfseManifestation` ja possui contrato, idempotencia, timeout `uncertain`, webhook e reconciliacao GET-only, mas a modelagem atual exige `nfse_item`; portanto a proxima fase deve ser **A) extensao segura de `NfseManifestation` existente**, nao fluxo paralelo, adicionando vinculo opcional/alternativo a `NfseReceivedDocument`.

### Escopo da proxima fase proposta

Fase futura recomendada: `3.12.1 - Manifestacao de NFS-e Recebida`.

- Objetivo: permitir manifestacao de `NfseReceivedDocument` validado como tomador ou intermediario.
- Endpoint: `POST /2/nfse/manifestar`.
- Modelagem: estender `NfseManifestation` para aceitar origem recebida por `received_document` ou campo equivalente, mantendo `nfse_item` para origem local existente; bloquear instancias sem exatamente uma origem.
- Operacao/idempotencia: chave por oficina, origem (`nfse_item` ou `received_document`), evento, manifestador e geracao da intencao; estados `sent`, `succeeded` e `uncertain` bloqueiam reenvio.
- Vinculo com `NfseReceivedDocument`: exigir mesma oficina, `validation_status=validated`, role `taker`/`intermediary`, UUID seguro, XML preservado e dados fiscais imutaveis.
- Permissoes: reutilizar `issue_nfse_manifestation`, `view_nfse_manifestation`, `view_nfse_manifestation_payload` e `download_nfse_manifestation`; permissoes de importacao, emissao, cancelamento ou substituicao nao manifestam.
- Feature flag/capability: exigir `NfseReceivedDocument.company` com capability municipal ativa, `national_standard_enabled=True` e `manifestation_enabled=True`; se a capability nao puder ser resolvida com seguranca, bloquear.
- UI minima: acao no detalhe da NFS-e recebida validada, selecao de evento/manifestador coerente com role, motivo/justificativa quando rejeicao, confirmacao explicita, historico e payload/download protegidos.
- Webhook/reconciliacao: webhook `modelo=manifestacao_nfse` resolve por UUID remoto unico da manifestacao; ambiguidade fica pendente; reconciliacao usa GET por UUID remoto da manifestacao e nunca repete POST.
- Downloads/payload: payload sanitizado e XML/artefato de manifestacao separados do XML recebido original.
- Bloqueios: provider, unknown, multiple, divergente, XML invalido/ausente, sem UUID, sem Padrao Nacional, cancelado, substituido, uncertain, duplicado e cross-workshop.
- Criterios de aceite: nenhuma criacao de `NfseItem` ou `FiscalDocument(nfse)`, nenhum ajuste no XML recebido, dados extraidos imutaveis, payload remoto restrito e regressao da manifestacao local existente preservada.

### Testes planejados

Elegibilidade: manifestar recebido validado como tomador; manifestar recebido validado como intermediario; bloquear prestador, desconhecido, multiplos papeis, CNPJ divergente, XML invalido, sem UUID, sem Padrao Nacional, cancelado, substituido, uncertain, duplicado e cross-workshop.

Payload: enviar somente `ambiente`, `uuid`, `manifestador`, `evento`; rejeicao envia `motivo_rejeicao`; `justificativa_rejeicao` somente com motivo `9`; nao enviar XML, dados fiscais extraidos, payload de emissao, cancelamento ou substituicao.

Modelagem: criar `NfseManifestation` vinculada ao recebido; nao criar `NfseItem`; nao criar `FiscalDocument(nfse)`; nao alterar XML recebido; nao alterar dados extraidos; manter idempotencia por documento/evento/manifestador.

Seguranca: exigir `issue_nfse_manifestation`; proteger payload/downloads; provar que permissoes de importacao, emissao, cancelamento e substituicao nao manifestam; bloquear cross-workshop.

Webhook/reconciliacao: webhook seguro atualiza a manifestacao recebida correta; webhook ambiguo fica pendente; reconciliacao consulta sem reenviar POST; reconciliacao ambigua nao atualiza.

Regressao: importacao de NFS-e recebida, manifestacao NFS-e existente, emissao manual, cancelamento manual, substituicao manual, NFS-e legada e NF-e/NFC-e nao regridem.

### Roadmap curto

| Bloco | Status | Recomendacao |
| ----- | ------ | ------------ |
| Manifestacao da NFS-e manual | adiada | manter bloqueada ate haver prova de papel tomador/intermediario |
| NFS-e recebida por consulta Webmania | nao iniciada | usar apenas como apoio/reconciliacao apos XML validado |
| Importacao em lote | nao iniciada | adiar ate fluxo unitario recebido estar estavel |
| Integracao e-mail/ERP | nao iniciada | adiar; deve alimentar pipeline de XML validado |
| NFS-e expandida | nao iniciada | quebrar por subfases apos manifestacao recebida |
| CT-e | nao iniciada | adiar ate dominio operacional proprio |
| MDF-e | nao iniciada | adiar ate CT-e/MDF-e terem fonte local |
| NFCom | nao iniciada | adiar; confirmar relevancia e feature flag |
| DC-e | nao iniciada | adiar; API v2.0.0 exige dominio proprio |
| Eventos IBS/CBS 112120/112140/211xxx | adiados | reavaliar depois dos eventos ja validados |
| Creditos 2-5 | adiados | manter bloqueados ate fonte fiscal suficiente |
| Debitos 1-3 e 5-8 | adiados | manter bloqueados ate fonte fiscal suficiente |
| Complementar tributaria | adiada | exige auditoria propria de base tributaria |
