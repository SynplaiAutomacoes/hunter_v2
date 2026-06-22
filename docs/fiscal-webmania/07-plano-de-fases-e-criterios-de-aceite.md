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
