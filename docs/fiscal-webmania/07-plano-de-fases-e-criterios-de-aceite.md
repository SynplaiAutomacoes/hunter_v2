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

Status: **validada tecnicamente em 2026-06-28**, com checkpoint desta entrega pendente. A Fase 3.7P foi aprovada no checkpoint `1fdded4e`.

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
