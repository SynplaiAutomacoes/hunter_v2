# Backlog e pendencias fiscais

## Decisoes que exigem aprovacao

- Manter models legados com camada de compatibilidade ou migrar diretamente para dominio unificado.
- Fase 2.2B.1 validada somente para complementar de preco/quantidade local; aprovar explicitamente a Fase 2.2B.2 antes de qualquer codigo de complementar tributaria.
- Fase 2.2C validada somente para Nota Fiscal de Ajuste; aprovar explicitamente qualquer evolucao de UI avulsa ampla, ajuste com novas origens ou outras operacoes NF-e.
- Aprovar politica final de permissoes fiscais para novas operacoes Fase 2.2+; Fase 2.1 nao concedeu emissao CC-e por fallback legado.
- Evoluir `FiscalEmissionAttempt` minimo para dominio unificado futuro.
- Politica final de permissoes fiscais.
- Fase 2.3.1 validada somente para NFC-e manual simples; aprovar explicitamente contingencia/offline, cancelamento por substituicao, PDV/TEF/SAT/MFE ou novas origens antes de qualquer codigo.
- Fase 2.3.2 validada somente para cancelamento padrao; cancelamento por substituicao com `nfce_referenciada` permanece fase futura.
- Fase 2.3.3 implementa somente inutilizacao NFC-e com `modelo=2`; inutilizacao funcional de NF-e, substituicao e contingencia/offline permanecem fora de escopo.
- Regras estaduais/prazos adicionais de cancelamento NFC-e devem ser avaliados antes de bloqueio local por prazo fixo.
- Avaliar migration futura de criptografia/backfill para valores CSC antigos que possam ter sido armazenados em texto puro antes da Fase 2.3.1; formularios atuais nao exibem os valores e criptografam novos envios.
- Prioridade real de CT-e/MDF-e para oficinas.
- Se NFCom deve ficar apenas manual.
- Criterios de ativacao interna de NFCom v2.0.0.
- Criterios de ativacao interna de DC-e v2.0.0.

## Divida tecnica

- `FiscalEmissionAttempt` ainda nao substitui `FiscalDocument` unificado.
- Compatibilidade temporaria de permissao NF-e ainda aceita fallback `nfserequest`.
- Dominio fiscal acoplado a OS.
- Reconciliacao especifica de eventos CC-e incertos deve ser aprofundada em fase posterior; a Fase 2.1 bloqueia reenvio e preserva auditoria local.

## Bloqueios externos observados na validacao da Fase 1

Estas dividas foram comprovadas no baseline anterior a Fase 1 e aceitas pelo usuario em 2026-05-28 para permitir validacao tecnica do nucleo fiscal da Fase 1.

- `makemigrations --check --dry-run` aponta migrations pendentes nao fiscais em `customer`, `scheduling` e `suppliers`.
- `apps.finance` falha em teste DRE de custo de kit/servico, fora do escopo fiscal alterado; a falha foi reproduzida no baseline anterior a Fase 1 no teste isolado `DreReportViewTests.test_dre_workorder_cost_total_includes_kit_service_cost`.
- `apps.workshops` falha em testes de logo/certificado Webmania existentes, fora do escopo da Fase 1.
- `apps.workorder` falha em testes de reabertura, assinatura, filtros e totais, fora do escopo da Fase 1.
- `ruff check .` falha por 5 ocorrencias F401 preexistentes em `apps/finance/views/movement_group.py`, `apps/workorder/reopening.py` e `apps/workorder/views.py`.
- `mypy .` falha com erros amplos preexistentes de stubs/tipos em centenas de pontos do repositorio; a branch da Fase 1 nao aumentou a contagem, medindo 2755 erros contra 2756 no baseline medido.

## Validacoes fiscais pendentes

- Revalidar em homologacao a CC-e implementada na Fase 2.1 contra respostas reais Webmania, sem emissao em testes automatizados.
- Confirmar dados obrigatorios de devolucao/estorno por CFOP inverso e finalidade.
- Confirmar variantes de NF-e complementar: preco/quantidade, impostos e adicao/importacao aplicaveis ao produto oficina.
- Revalidar payload oficial de `POST /1/nfe/complementar/` imediatamente antes do codigo de cada subtipo ainda nao implementado.
- Decidir se `complementary_tax` externa minima sera permitida na primeira implementacao ou bloqueada ate importacao/validacao documental.
- Manter `complementary_import_addition` adiada salvo aprovacao explicita por baixa relevancia para oficinas.
- Fase 2.2B.1 nao implementou complemento tributario, IBS/CBS, ICMS-ST, IPI, ISSQN, `agropecuario`, adicao/importacao ou NF-e externa minima para preco/quantidade.
- Confirmar em homologacao cenarios de ajuste que exigem ou dispensam documento original, embora a Fase 2.2C tenha implementado link opcional conforme endpoint oficial.
- Automatizar deteccao de estorno SC/ES por UF/finalidade quando houver dados locais suficientes; hoje a Fase 2.2C exige confirmacao operacional e direciona/bloqueia o uso de ajuste quando o usuario identificar o cenario.
- Revalidar tipos oficiais `tipo_credito` e `tipo_debito` antes de qualquer codigo da Fase 2.5, mesmo apos a matriz documental da Fase 2.5.0.
- Importacao/validacao de NF-e externa por XML ou API fiscal especifica fica fora da Fase 2.2A.
- Habilitar devolucao parcial de NF-e externa somente depois de importar/validar XML ou fonte fiscal que preserve sequenciais fiscais e quantidades originais.
- Confirmar requisitos NFC-e por oficina: serie, CSC/token, ambiente, contingencia e DANFE NFC-e; Fase 2.3.0 recomenda reaproveitar `WebmaniaCompany`.
- Confirmar suporte e semantica de cancelamento por substituicao de NFC-e antes de implementar essa variacao.
- Avaliar fase futura para inutilizacao funcional de NF-e; a Fase 2.3.3 usa a generalidade do contrato apenas para NFC-e.
- Avaliar importacao/consulta externa de numeros usados fora do Hunter; a validacao local de inutilizacao nao garante ausencia de uso no painel Webmania ou em outro emissor.
- Definir operacao administrativa futura para resolver inutilizacao NFC-e `uncertain`, pois a Fase 2.3.3 nao confirmou endpoint oficial de consulta ou webhook para inutilizacao.

## Pendencias Fase 2.5.0 - Credito/Debito

- Nao implementar NF-e de credito/debito antes de decisao sobre IBS/CBS, pois a Webmania relaciona finalidades 5/6 a IBS/CBS/Reforma Tributaria.
- Revalidar imediatamente antes do codigo a lista oficial de `tipo_credito` (`1` a `5`) e `tipo_debito` (`1` a `8`), incluindo eventuais mudancas normativas.
- Definir se a primeira entrega funcional sera adiada para depois da Fase 2.4 ou se havera subfase tributaria dedicada antes de credito/debito.
- Criar feature flag e habilitacao administrativa por oficina antes de expor qualquer action.
- Definir campo `fiscal_purpose_type` ou equivalente em `FiscalDocument` somente quando a implementacao funcional for autorizada.
- Validar quando `FiscalDocumentLink(role="credits"|"debits")` sera obrigatorio por tipo; ate haver evidencia oficial, manter opcional/condicional.
- Confirmar com contabilidade/produto se oficinas automotivas precisam dessa operacao agora ou se o valor e estritamente administrativo/contabil.

## Pendencias Fase 2.4 - IBS/CBS NF-e/NFC-e

- Fase 2.4A+B implementou a primeira base: `TaxClassNfe` com campos IBS/CBS normalizados, `ibs_cbs_details` JSON validado, sincronizacao de classe fiscal Webmania e bloqueio de NF-e/NFC-e normal sem classe pronta.
- A estrategia implementada usa `classe_imposto` como caminho operacional para emissao normal; payload inline `produtos[].impostos.ibs_cbs` permanece fora de uso ate fase aprovada exigir.
- Deploy pode bloquear NF-e/NFC-e normais para oficinas que ainda nao configuraram classes fiscais IBS/CBS validas.
- Validar tabela oficial de situacao/classificacao tributaria IBS/CBS imediatamente antes do codigo.
- Definir politica futura de homologacao controlada se houver necessidade operacional; a Fase 2.4A+B exige configuracao valida tambem em homologacao por padrao.
- Fase 2.4C.1 validou devolucao/estorno com IBS/CBS por snapshot original local; Fase 2.4C.2 validou complementar preco/quantidade local com `produtos[].impostos.ibs_cbs` vindo do snapshot original e `base_calculo` obrigatorio. Fase 2.4C.3 protege ajuste sem inserir IBS/CBS por ausencia de contrato seguro no endpoint `/1/nfe/ajuste/`.
- Manter credito/debito bloqueados ate 2.4E; finalidades 5/6 devem enviar somente IBS/CBS e barrar tributos antigos para evitar rejeicao 1001.
- Registrar em UI e logs que a classificacao tributaria e configurada por usuario/fiscal, nao inferida pelo Hunter.
- Fase 2.4C.0 decidiu que derivados IBS/CBS devem usar snapshot fiscal original. Devolucao/estorno e complementar preco/quantidade ja seguem essa decisao; qualquer derivado futuro ainda deve implementar captura/uso explicito do snapshot antes do gateway.
- Criar fluxo de importacao/validacao XML para NF-e externa antes de permitir devolucao parcial ou complementar preco/quantidade com IBS/CBS.
- Revalidar oficialmente antes de novas subfases se `/1/nfe/complementar/` mudou campos de IBS/CBS. Na validacao da Fase 2.4C.2, o contrato consultado aceitava `produtos[].impostos.ibs_cbs` por item para preco/quantidade e exigia `base_calculo`; `classe_imposto` atual nao foi usado como fallback.
- Revalidar oficialmente antes de qualquer ampliacao de ajuste. Na Fase 2.4C.3, `/1/nfe/ajuste/` permaneceu restrito a ICMS/ICMS-ST e dados de cliente/operacao; credito/debito, eventos IBS/CBS, complementar tributaria e produtos seguem pendentes de fases proprias.
- Revalidar `/1/nfe/ajuste/` frente a Reforma Tributaria; nao inserir produtos/IBS-CBS no ajuste sem contrato oficial.
- Resolver divergencia documental de cronograma IBS/CBS com decisao fiscal final: PRDs aprovados citam `05/01/2026`, enquanto a pagina oficial REST consultada em 2026-06-02 exibiu producao obrigatoria a partir de `01/01/2026`. A Fase 2.4C.1 deve usar temporariamente a regra conservadora desde `01/01/2026`.
- Fase 2.4D.1 implementou somente o evento IBS/CBS `112110`; Fase 2.4D.2 implementou somente o cancelamento desse mesmo evento autorizado por UUID remoto. Permanecem pendentes: cancelamento dos demais eventos IBS/CBS, demais codigos com itens/campos especificos, eventos de destinatario, relacao com credito/debito, complementar tributaria, NFS-e e CT-e.
- Fases 2.4D.3 e 2.4D.4 validaram o ciclo basico do `112150` para NF-e normal local autorizada: emissao do evento de previsao de entrega e cancelamento por UUID remoto. Permanecem pendentes: suporte NFC-e para `112150` caso a regra operacional seja confirmada, `112120`, `112130` e `112140` com itens/valores IBS-CBS/controle operacional, `211128` dependente de credito/debito e demais `211xxx` dependentes de papel destinatario, documento de aquisicao ou apuracao externa.
- Fase 2.4D.5.0 decidiu planejar `112120`, `112130` e `112140` um por vez. `112130` e o primeiro candidato funcional, mas exige snapshot fiscal do item, evento de transporte/estoque e valores de estorno confirmados. `112120` fica pendente de importacao ALC/ZFM validada. `112140` fica pendente de pagamento antecipado/nota de debito modelados.
- Para eventos com itens, criar/importar snapshot fiscal externo por XML antes de permitir documento externo minimo; chave manual isolada nao e suficiente.
- Nenhum evento IBS/CBS com itens deve usar `TaxClassNfe` atual como fallback automatico de documento ja emitido.
- Revalidar campos especificos de cada `cod_evento` imediatamente antes de implementar, mesmo apos a matriz 2.4D.0, porque a Reforma Tributaria pode alterar payloads e validacoes.
- Evento `211128` deve permanecer bloqueado ate Nota Fiscal de Credito/Debito com IBS/CBS estar implementada e validada.
- Eventos de destinatario exigem decisao de produto sobre papel fiscal da oficina como destinatario; nao liberar por fallback de emissao NF-e.
- Cancelamento de evento IBS/CBS deve continuar por subfase propria por UUID remoto do evento, sem reutilizar cancelamento NF-e/NFC-e. A subfase 2.4D.2 cobre apenas `112110`; demais codigos exigem nova revalidacao oficial.
- Definir se a reconciliacao de evento IBS/CBS tera consulta oficial suficiente; se nao houver contrato especifico, manter resposta sincrona/webhook e decisao administrativa para `uncertain`.

## Reforma Tributaria em outras familias

- NFS-e tambem exige auditoria equivalente antes de qualquer expansao funcional: a documentacao Webmania NFS-e informa `ibs_cbs` em `servico.impostos` e campos `situacao_tributaria`/`classificacao_tributaria`.
- CT-e deve ser planejado ja com IBS/CBS/Reforma Tributaria, evitando implementar fluxo legado incompatível antes da fase 4.
- CT-e OS, MDF-e, NFCom e DC-e devem ser reconsultados antes de implementacao para identificar regras IBS/CBS ou substitutos aplicaveis.
- Confirmar politica de consumidor/pagamento minimo para NFC-e manual.
- Revalidar eventos IBS/CBS e cancelamento conforme documentacao vigente da Reforma Tributaria.
- Campos obrigatorios completos de cada municipio/provedor NFS-e.
- Regras IBS/CBS por tipo documental.
- Particularidades de NFC-e em contingencia.
- Restricoes de CT-e OS versus CT-e.
- Relevancia de NFCom para oficinas.
- Confirmar, antes das Fases 6 e 7, se NFCom/DC-e continuam beta na documentacao oficial.

## Fora do escopo imediato

- CT-e, MDF-e, NFCom e DC-e antes da estabilizacao NF-e/NFS-e.
- Remocao de models legados.
- Emissao real em testes automatizados.
### Pendencias apos Fase 2.4D.5.1

- Implementar eventos IBS/CBS `112120` e `112140` em subfases proprias, sem reutilizar formulario generico do `112130`.
- Fase 2.4D.5.2 validou cancelamento do evento `112130` por UUID remoto, sem cancelamento generico.
- Planejar cancelamento dos eventos `112120` e `112140` somente depois de suas emissoes correspondentes serem implementadas e validadas.
- Manter eventos `211xxx` bloqueados ate decisao de papel destinatario, referencias externas e permissao fiscal.
- Manter evento `211128`, credito/debito e complementar tributaria bloqueados ate base IBS/CBS correspondente estar funcional e aprovada.
- Avaliar futura integracao com estoque/transporte para reduzir input manual do `112130`; a implementacao validada exige confirmacao fiscal e snapshot de item, mas nao automatiza baixa ou ocorrencia operacional.

### Pendencias apos Fase 2.4D.6.0

- `112120` permanece bloqueado ate existir importacao XML/projecao fiscal capaz de gerar `FiscalDocument` com itens, sequenciais fiscais, snapshot IBS/CBS e contexto ALC/ZFM validado.
- `112140` permanece bloqueado ate existir nota de debito/pagamento antecipado ou fluxo fiscal equivalente com item fiscal, vinculo financeiro e quantidade/unidade nao fornecida auditavel.
- Cancelamentos de `112120` e `112140` devem ficar em subfases posteriores a emissao correspondente, sem cancelamento generico.
- A proxima fase funcional recomendada nao deve ser `112120` nem `112140`; deve ser preparatoria para fonte fiscal confiavel ou seguir para outra area autorizada com menor dependencia.
- Decisao aprovada: adiar `112120` e `112140`; nao generalizar cancelamento; manter `211xxx` adiados.

## Pendencias Fase 2.5.1.0 - Credito/Debito apos IBS/CBS

- Modelar uma fonte fiscal especifica antes de liberar qualquer tipo; nenhum subconjunto e seguro hoje.
- Definir com responsavel fiscal qual tipo possui valor real para oficina e qual evidencia legal/operacional sera exigida.
- Criar importacao/projecao validada de documento e item fiscal externo; chave manual isolada nao basta.
- Modelar apuracao IBS/CBS para tipos 2/3/5/8 e hipoteses de cooperativa, imune/isenta, ZFM e sucessao.
- Modelar multa/juros fiscal separado de taxa de pagamento e vinculado ao DF-e/item.
- Modelar pagamento antecipado fiscal e vinculo financeiro -> item para debito 6 e futuro `112140`.
- Modelar perda fiscal de estoque separada de movimento generico para debito 7.
- Manter feature flag e habilitacao por oficina obrigatorias na futura implementacao.
- Revalidar obrigatoriedade de `nfe_referenciada` por `tipo_credito` antes do codigo, pois a pagina oficial documenta o campo e o exemplo, mas nao publica matriz condicional por tipo.

### Pendencias apos Fase 2.5.1P

- Integrar importacao XML externa validada a uma projecao `FiscalDocument`/item antes de preparar base externa pela UI.
- Criar fontes especializadas para apuracao, sucessao, ZFM, cooperativas, saidas imunes/isentas e desenquadramento SN.
- Diferenciar multa/juros fiscal de taxas financeiras operacionais.
- Modelar evidencia logistica de recusa/nao localizacao.
- Modelar perda fiscal de estoque e pagamento antecipado com vinculo por item.
- Emissao de credito/debito continua bloqueada mesmo para bases aprovadas ate nova fase explicita.

## Pendencias Fase 2.5.2.0

- Criar snapshot comercial imutavel por item antes de transmitir qualquer finalidade 5/6.
- Modelar principal, multa e juros separadamente, com soma e origem financeira auditaveis.
- Definir CFOP permitido para credito tipo 1 com responsavel fiscal; nao copiar automaticamente o CFOP original.
- Manter debito tipo 4 posterior ao credito tipo 1 devido a `dfe_referenciado` por produto.
- Demais 11 tipos continuam bloqueados por apuracao, estoque, sucessao, cooperativa, ZFM, logistica ou regime.
## Pendencias apos Fase 2.5.2P

- Definir fluxo auditavel para complementar bases antigas 2.5.1P sem `FiscalReferencedBasisItem`; nao existe backfill automatico.
- Validar com fiscal/contabilidade a hipotese de credito tipo 1 antes de autorizar payload remoto.
- Emissao, idempotencia remota, webhook, downloads e cancelamento de credito/debito permanecem nao iniciados.
- `112120`, `112140`, eventos `211xxx`, complementar tributaria, NFS-e e CT-e permanecem bloqueados.
## Pendencias Fase 2.5.3.0

- Obter confirmacao oficial/fiscal para representar multa/juros em `quantidade`, `subtotal` e `total`; nao assumir quantidade 1.
- Definir CFOP, descricao, NCM e unidade aplicaveis ao item de credito tipo 1; nao copiar automaticamente os dados originais.
- Definir quais campos e valores `ibs_cbs` representam a multa/juros e se existe proporcionalidade permitida; nao recalcular automaticamente.
- Resolver divergencia documental `modelo=1` no contrato operacional versus `modelo="nfe"` no exemplo oficial atual antes do codigo.
- Confirmar cliente, pedido/pagamento e natureza/operacao para o caso real da oficina.
- Criar permissoes/feature flag de emissao somente apos a validacao fiscal; a flag de preparacao nao autoriza gateway.
- Cancelamento futuro deve usar fluxo padrao NF-e e ficar fora da primeira emissao.
- Emissao credito/debito, `112120`, `112140`, eventos `211xxx`, complementar tributaria, NFS-e e CT-e continuam bloqueados.
## Pendencias apos implementacao 2.5.3P

- Submeter previews aprovados a validacao fiscal externa antes de autorizar transmissao.
- Confirmar se a regra administrativa explicita escolhida pode ser convertida em regra fiscal de emissao; nao promover automaticamente.
- Completar cliente, pedido/pagamento, natureza/operacao e contrato `modelo` somente em fase funcional futura aprovada.
- Definir flag administrativa de emissao separada; a flag atual continua apenas preparatoria.
- Cancelamento, webhook/reconciliacao e downloads de credito permanecem inexistentes porque nao ha documento emitido.

## Pendencias apos Fase 2.5.4

- Planejar cancelamento padrao da NF-e de credito em fase separada.
- Credito tipos 2-5 e toda NF-e de debito permanecem bloqueados.
- `112120`, `112140`, eventos `211xxx`, complementar tributaria, NFS-e e CT-e permanecem nao iniciados.

## Pendencias apos Fase 2.5.5

- Credito tipo 1 possui ciclo emissao/cancelamento; nenhuma extensao para tipos 2-5 foi autorizada.
- NF-e de debito permanece bloqueada.
- `112120`, `112140`, eventos `211xxx`, complementar tributaria, NFS-e, CT-e e demais familias permanecem nao iniciados.

## Pendencias apos Fase 2.5.6.0

- Aprovar ou rejeitar a Fase 2.5.6P proposta para preview fiscal de debito tipo 4 sem transmissao.
- Validar com responsavel fiscal o CFOP, natureza/operacao e representacao comercial de multa/juros no debito tipo 4; nao copiar automaticamente do credito tipo 1.
- Criar feature flag e permissoes preparatorias separadas para debito; a infraestrutura de credito nao concede debito.
- Manter emissao de debito bloqueada ate preview propria aprovada e nova autorizacao.
- Manter debitos 1/2/3/5/6/7/8 e creditos 2-5 adiados conforme dependencias da matriz 2.5.6.0.
- `112120` continua dependente de ALC/ZFM; `112140`, de pagamento antecipado/nao fornecimento; `211xxx`, de papel destinatario e fontes fiscais externas.
- NFS-e deve passar por auditoria IBS/CBS/municipal antes de expansao; CT-e deve nascer conforme Reforma Tributaria e dominio de transporte.

## Pendencias apos Fase 2.5.6P

- Emissao de debito tipo 4 exige nova fase documental/funcional e aprovacao explicita.
- Antes da transmissao, revalidar cliente, pedido/pagamento, natureza/operacao, CFOP e contrato remoto vigente.
- Criar `FiscalDocument(purpose="debit")`, link, tentativa, gateway, webhook/reconciliacao e downloads somente na fase de emissao.
- Cancelamento do debito deve permanecer em fase separada posterior a emissao validada.
- Creditos 2-5, demais debitos, `112120`, `112140`, `211xxx`, complementar tributaria, NFS-e e CT-e permanecem nao iniciados.

## Pendencias apos Fase 2.5.7.0

- Aguardar autorizacao explicita para implementar a emissao de debito tipo 4.
- Criar flag `nfe_debit_emission_enabled` e permissoes de emissao/consulta/download/payload na fase funcional.
- Restringir primeira emissao a origem local; importacao/origem externa permanece fora do escopo.
- Revalidar imediatamente antes do codigo `operacao`, natureza, cliente/pedido e resposta oficial vigente.
- Nao enviar `nfe_referenciada`; preservar `dfe_referenciado` por produto.
- Planejar cancelamento somente depois da emissao validada.
- Outros debitos, creditos 2-5, eventos pendentes, complementar tributaria, NFS-e e CT-e continuam bloqueados.

## Pendencias apos Fase 2.5.7

- Planejar cancelamento da NF-e de debito tipo 4 em fase independente pelo cancelamento NF-e padrao.
- Manter debitos 1-3/5-8, creditos 2-5, `112120`, `112140`, `211xxx`, complementar tributaria, NFS-e e CT-e bloqueados ate autorizacao especifica.
- Origem externa permanece bloqueada ate existir importacao/validacao fiscal suficiente.

## Pendencias apos Fase 2.5.8

- Debito tipo 4 possui ciclo de emissao/cancelamento completo; nao ampliar para outros tipos sem nova auditoria e autorizacao.
- Manter debitos 1-3/5-8, creditos 2-5, `112120`, `112140`, `211xxx`, complementar tributaria, NFS-e e CT-e bloqueados.
- Origem externa e qualquer politica adicional de prazo/UF permanecem fora do escopo ate fonte fiscal confiavel.

## Backlog apos Fase 2.6.0

- Executar Fase 3.0 documental para auditar NFS-e legada, capacidades municipais, Padrao Nacional, ISS/IBS-CBS, substituicao e manifestacao.
- Manter creditos 2-5 e debitos 1-3/5-8 bloqueados ate existirem fontes locais confiaveis para ZFM/ALC, cooperativas, imunes/isentas, sucessao, apuracao, pagamento antecipado ou estoque fiscal.
- `112120` continua dependente de importacao ALC/ZFM; `112140`, de nota de debito/pagamento antecipado e vinculo item-financeiro.
- Eventos `211xxx` continuam dependentes do papel de destinatario e de fontes fiscais externas auditaveis.
- Complementar tributaria permanece pendente de auditoria especifica por imposto e coexistencia IBS/CBS.
- CT-e deve ser planejado com conformidade IBS/CBS; MDF-e depende do dominio logistico/CT-e.
- NFCom e DC-e sao APIs Webmania v2.0.0, mas permanecem desabilitadas por feature flag/habilitacao administrativa ate haver necessidade de negocio e fase propria.

## Backlog apos Fase 3.0

- Aprovar ou rejeitar 3.1: estabilizacao NFS-e, capacidades municipais, `atualizado_em`, operation types e flags.
- Definir TTL e politica de falha fechada para `/2/nfse/status` por oficina/municipio.
- Corrigir cancelamento legado somente na 3.3: tentativa persistida, concorrencia, `uncertain` e confirmacao remota positiva.
- Definir ownership de RPS/lote por provedor e compatibilidade com numeracao Webmania/prefeitura antes de ampliar emissao.
- Planejar agendamento depois da estabilizacao, com timezone e cancelamento idempotente.
- Nao executar backfill `NfseItem -> FiscalDocument` sem fase propria, metricas e rollback.
- Manter todos os blocos adiados na Fase 2.6.0 fora do roadmap 3.x.

## Backlog apos Fase 3.1

- Fase 3.2: ampliar consulta/reconciliacao de item e lote, mantendo somente operacoes de leitura.
- Fase 3.3: implementar cancelamento NFS-e idempotente com tentativa anterior ao PUT e `uncertain` bloqueante.
- Sincronizacao automatica/TTL de capacidades via `/2/nfse/status`; a Fase 3.1 usa cadastro administrativo auditavel.
- Substituicao, manifestacao, emissao manual nova e projecao sob demanda `FiscalDocument(nfse)` exigem autorizacao propria.

## Backlog apos Fase 3.2

- Resolvido na Fase 3.3: cancelamento NFS-e idempotente com tentativa, concorrencia e `uncertain`, validado no checkpoint `401b6553302ae1250a5b8838c77a43fa32ef9daa`.
- Avaliar TTL/agendamento de `/2/nfse/status`; a 3.2 implementa consulta manual e snapshot informativo.
- Consulta por numero RPS nao foi implementada porque o contrato oficial confirmado exige UUID.
- Substituicao, manifestacao, emissao manual nova, projecao `FiscalDocument(nfse)` e backfill continuam dependendo de fases proprias.
## Apos a Fase 3.3

- substituicao NFS-e idempotente;
- manifestacao NFS-e, condicionada a contrato/capacidade municipal;
- emissao manual nova e eventual projecao `FiscalDocument(nfse)` sob demanda;
- regras municipais adicionais de prazo de cancelamento, sem inferencia local enquanto nao confirmadas.

## Apos a Fase 3.4.0

- Fase 3.4P implementada: preview imutavel do novo RPS, aprovacao fiscal, permissoes e feature flag, sem POST remoto;
- confirmar com fonte oficial/contratual se `uuid` tambem deve ser enviado ou se `codigo_verificacao` identifica integralmente a original;
- Implementado na Fase 3.4.1: `NfseSubstitution` + tentativa `nfse_substitution` e relacionamento original/substituta;
- definir reconciliacao administrativa quando timeout ocorrer antes de o UUID substituto ser conhecido;
- manifestacao e emissao manual nova permanecem fases independentes.

## Apos a Fase 3.5.0

- Proximo bloco recomendado: manifestacao de NFS-e Padrao Nacional em fase propria.
- Emissao manual nova de NFS-e e NFS-e expandida ampla continuam pendentes ate decisao especifica posterior a manifestacao ou fase equivalente.
- CT-e, MDF-e, NFCom, DC-e, eventos `112120`, `112140`, `211xxx`, creditos tipos 2-5, debitos tipos 1-3/5-8 e complementar tributaria continuam bloqueados.

## Apos o planejamento 3.6.0

- Implementar manifestacao NFS-e somente apos aprovacao funcional propria.
- Confirmar ou manter gate manual para Padrao Nacional/capability, pois `/2/nfse/status` nao lista `manifestar` de forma clara em `funcoes`.
- Nao implementar cancelamento/retificacao de manifestacao sem endpoint oficial.
- Nao criar emissao manual nova, NFS-e expandida ampla ou `FiscalDocument(nfse)` generalizado junto com manifestacao.

## Apos a Fase 3.6.1

- Desfazimento/cancelamento de manifestacao continua bloqueado ate endpoint oficial claro.
- NFS-e recebida/importada de terceiros continua adiada.
- Emissao manual nova de NFS-e, NFS-e expandida ampla e `FiscalDocument(nfse)` generalizado continuam fora de escopo.
- Manter eventos IBS/CBS pendentes, creditos 2-5, debitos restantes, CT-e, MDF-e, NFCom, DC-e e complementar tributaria bloqueados.

## Apos a Fase 3.7.0

- Proxima fase recomendada: `3.7P - Preview de emissao manual nova de NFS-e`, sem transmissao Webmania.
- Antes de emitir NFS-e manual nova, congelar tomador, servico, valores, ISS, IBS/CBS, retencoes, municipio/capability, ambiente, RPS/numeracao e payload planejado.
- Nao promover automaticamente o wizard legado por OS para emissao manual ampla; dados atuais sao mutaveis e devem virar snapshot aprovado.
- NFS-e recebida/importada permanece bloqueada ate existir XML/UUID/chave/codigo de verificacao, papel fiscal da oficina e associacao segura a cliente/oficina.
- CT-e, MDF-e, NFCom e DC-e continuam adiados por ausencia de dominio operacional local suficiente.
- `112120`, `112140`, eventos `211xxx`, creditos 2-5, debitos 1-3/5-8 e complementar tributaria continuam bloqueados ate fontes fiscais especificas existirem.

## Apos a Fase 3.7.1

- Emissao manual nova de NFS-e passa a existir somente a partir de `NfseManualEmissionPreview` aprovada.
- Pendencias remanescentes: cancelamento da NFS-e manual, substituicao da NFS-e manual, manifestacao da NFS-e manual, importacao de NFS-e recebida, projecao `FiscalDocument(nfse)`, backfill de NFS-e legada e expansao multi-RPS/manual ampla.
- CT-e, MDF-e, NFCom, DC-e, eventos IBS/CBS pendentes, creditos/debitos pendentes e complementar tributaria seguem nao iniciados.

## Apos a Fase 3.8.0

- Proxima pendencia prioritaria recomendada: cancelamento da NFS-e manual nova por extensao segura do fluxo `NfseCancellation`.
- Substituicao e manifestacao da NFS-e manual continuam pendentes e devem ser fases separadas.
- NFS-e recebida/importada, NFS-e expandida ampla, CT-e, MDF-e, NFCom, DC-e, eventos IBS/CBS `112120/112140/211xxx`, creditos 2-5, debitos 1-3/5-8 e complementar tributaria continuam adiados.

## Apos a Fase 3.8.1

- Cancelamento da NFS-e manual nova implementado por extensao de `NfseCancellation`.
- Checkpoint validado: `29f3f3a9`.
- Pendencias remanescentes: substituicao da NFS-e manual nova, manifestacao da NFS-e manual nova, NFS-e recebida/importada, consolidacao/`FiscalDocument(nfse)`, backfill de NFS-e legada e expansao multi-RPS/manual ampla.
- CT-e, MDF-e, NFCom, DC-e, eventos IBS/CBS pendentes, creditos/debitos pendentes e complementar tributaria seguem nao iniciados.

## Apos a Fase 3.9.0

- Proxima fase recomendada: substituicao da NFS-e manual nova por extensao segura de `NfseSubstitutionPreview`/`NfseSubstitution`.
- Adaptar elegibilidade para origem manual somente quando houver `NfseManualEmission.nfse_item`, UUID, `codigo_verificacao`, status autorizado, capability/flag de substituicao e permissao propria.
- Nao criar fluxo paralelo especifico para `NfseManualEmission` se o fluxo atual de substituicao puder ser estendido com seguranca.
- Manifestacao da NFS-e manual fica adiada ate Padrao Nacional/papel fiscal estarem claros.
- NFS-e recebida/importada exige fase propria para XML, identificadores, tomador/prestador, oficina correta, cross-workshop e manifestacao posterior.
- NFS-e expandida ampla, CT-e, MDF-e, NFCom, DC-e, eventos IBS/CBS `112120/112140/211xxx`, creditos 2-5, debitos 1-3/5-8 e complementar tributaria continuam adiados.

## Apos a Fase 3.9.1

- Substituicao da NFS-e manual nova implementada por extensao do fluxo atual.
- Pendencias remanescentes: manifestacao da NFS-e manual, NFS-e recebida/importada, consolidacao/`FiscalDocument(nfse)`, backfill de NFS-e legada, expansao multi-RPS/manual ampla e regras adicionais municipais.
- A manifestacao da NFS-e manual continua dependente de Padrao Nacional e papel fiscal claro.
- A NFS-e recebida/importada continua dependente de fluxo proprio de XML/identidade/tenancy.
- CT-e, MDF-e, NFCom, DC-e, eventos IBS/CBS `112120/112140/211xxx`, creditos 2-5, debitos 1-3/5-8 e complementar tributaria seguem nao iniciados.

## Apos a Fase 3.10.0

- Manifestacao da NFS-e manual permanece adiada.
- Motivo: risco fiscal de papel do manifestador; NFS-e manual emitida pela propria oficina nao prova atuacao como tomadora ou intermediaria.
- Proximo bloco recomendado: planejar NFS-e recebida/importada de terceiros antes de manifestacao de documentos recebidos.
- Bloqueios mantidos: NFS-e manual cancelada, substituida, uncertain, sem UUID, sem Padrao Nacional confirmado, municipal legada e recebida/importada sem dominio proprio.
- Demais blocos seguem adiados: NFS-e expandida ampla, CT-e, MDF-e, NFCom, DC-e, eventos IBS/CBS `112120/112140/211xxx`, creditos 2-5, debitos 1-3/5-8 e complementar tributaria.

## Apos a Fase 3.11.0

- Proximo bloco funcional recomendado: registro local de NFS-e recebida por upload de XML validado.
- Manifestacao de documentos recebidos continua posterior ao dominio recebido validado.
- Pendencias tecnicas: parser XML confiavel, hash/snapshot, validacao de CNPJs/papel fiscal, duplicidade, cross-workshop, status remoto e protecao de payload/XML.
- Consulta Webmania por identificador permanece apoio/reconciliacao, nao fonte unica inicial.
- CT-e, MDF-e, NFCom, DC-e, eventos IBS/CBS `112120/112140/211xxx`, creditos 2-5, debitos 1-3/5-8 e complementar tributaria seguem nao iniciados.

## Apos a Fase 3.11.1

- Registro local de NFS-e recebida por XML validado implementado no checkpoint `b25ad698`.
- Pendencia principal: manifestacao de NFS-e recebida a partir de `NfseReceivedDocument` validado.
- Importacao por consulta Webmania, lote, e-mail/ERP e integracoes externas continuam adiadas.
- Manifestacao da NFS-e manual permanece adiada por papel fiscal inseguro.
- CT-e, MDF-e, NFCom, DC-e, eventos IBS/CBS `112120/112140/211xxx`, creditos 2-5, debitos 1-3/5-8 e complementar tributaria seguem nao iniciados.

## Apos a Fase 3.12.0

- Proxima fase recomendada: `3.12.1 - Manifestacao de NFS-e Recebida`.
- Implementar como extensao segura de `NfseManifestation`, vinculando exatamente uma origem: `nfse_item` ou `NfseReceivedDocument`.
- Liberar somente roles `taker` e `intermediary`, com UUID seguro, XML validado, Padrao Nacional confirmado e `manifestation_enabled=True`.
- Bloquear provider, unknown, multiple, CNPJ divergente, XML invalido/ausente, sem UUID, sem Padrao Nacional, cancelado, substituido, uncertain, duplicado e cross-workshop.
- Nao criar `NfseItem`, `FiscalDocument(nfse)` ou fluxo paralelo de manifestacao recebida.
- Roadmap restante: consulta Webmania para recebidas, lote, e-mail/ERP, NFS-e expandida, CT-e, MDF-e, NFCom, DC-e, eventos IBS/CBS pendentes, creditos/debitos restantes e complementar tributaria continuam adiados.

## Apos a Fase 3.12.1

- Manifestacao de NFS-e recebida implementada e validada no checkpoint `6cc3a788`.
- `NfseManifestation` agora suporta origem por `NfseReceivedDocument` com constraint de origem unica; migration `0070` aplicada na fase.
- Pendencia recomendada: consulta/reconciliacao auxiliar para `NfseReceivedDocument`, somente consultiva, usando `GET /2/nfse/consulta/{identifier}` e eventualmente `/2/nfse/status`.
- A consulta futura nao deve criar documento recebido sem XML, nao substituir XML/hash/dados extraidos, nao criar manifestacao automaticamente, nao criar `NfseItem` e nao criar `FiscalDocument(nfse)`.
- Importacao em lote de XML, integracao e-mail/ERP e NFS-e expandida ampla permanecem adiadas ate subfase propria.
- Manifestacao da NFS-e manual permanece adiada por papel fiscal inseguro.
- CT-e, MDF-e, NFCom, DC-e, eventos IBS/CBS `112120/112140/211xxx`, creditos 2-5, debitos 1-3/5-8 e complementar tributaria seguem nao iniciados.

## Apos a Fase 3.13.1

- Consulta/reconciliacao auxiliar de NFS-e recebida implementada e validada no checkpoint `01f0924d`.
- `NfseReceivedDocumentConsultation` registra snapshot remoto e divergencias sem alterar `NfseReceivedDocument`.
- Pendencia recomendada: importacao em lote de XML de NFS-e recebida, baseada exclusivamente em XML, com relatorio por arquivo e bloqueio de duplicidades/cross-workshop.
- Pendencias remanescentes posteriores: integracao e-mail/ERP, eventual consulta como fonte de descoberta apenas apos fase propria, relatorios/reconciliacao operacional ampliada e consolidacao `FiscalDocument(nfse)` sob demanda.
- Manifestacao da NFS-e manual permanece adiada por papel fiscal inseguro.
- Emissao, cancelamento e substituicao de NFS-e recebida continuam fora de escopo.
- CT-e, MDF-e, NFCom, DC-e, eventos IBS/CBS `112120/112140/211xxx`, creditos 2-5, debitos 1-3/5-8 e complementar tributaria seguem nao iniciados.

## Apos a Fase 3.14.0

- Reavaliacao documental recomenda a Fase 3.14.1 para importacao em lote de XML de NFS-e recebida.
- E-mail/ERP permanece adiado ate existir lote local validado e desenho de pipeline externo.
- Consulta Webmania permanece apoio GET-only e nao fonte de criacao de documento recebido.
- NFS-e expandida ampla, CT-e, MDF-e, NFCom e DC-e permanecem adiados por falta de dominio local suficiente.
- Eventos IBS/CBS `112120`, `112140`, `211xxx`, creditos 2-5, debitos 1-3/5-8 e complementar tributaria permanecem dependentes de fontes fiscais especificas.

## Apos a Fase 3.14.1

- Importacao em lote de XML de NFS-e recebida implementada e validada no checkpoint `b53e862b`.
- Pendencia recomendada: fase preparatoria/documental para e-mail/ERP como origem externa de XMLs.
- Pendencias remanescentes: relatorios operacionais ampliados, eventual processamento assincrono de lotes grandes e consolidacao `FiscalDocument(nfse)` sob demanda.
- Consulta Webmania permanece apoio GET-only e nao fonte de criacao.
- Manifestacao automatica, emissao/cancelamento/substituicao de recebida e manifestacao manual permanecem fora de escopo.
- CT-e, MDF-e, NFCom, DC-e, eventos IBS/CBS `112120/112140/211xxx`, creditos 2-5, debitos 1-3/5-8 e complementar tributaria seguem nao iniciados.

## Apos a Fase 3.15.0

- Reavaliacao documental recomenda planejar integracao e-mail/ERP para XML NFS-e como fase preparatoria.
- Consulta Webmania ampliada permanece adiada para evitar substituicao indevida do XML.
- Manifestacao manual permanece adiada por papel fiscal inseguro.
- NFS-e expandida ampla e novos dominios fiscais permanecem adiados.
- Eventos IBS/CBS `112120/112140/211xxx`, creditos/debitos pendentes e complementar tributaria continuam dependentes de fontes fiscais especificas.

## Apos a Fase 3.15.1

- Decisao recomendada: implementar caixa de entrada externa de XML antes de qualquer conector real.
- Primeira fase funcional futura deve ser manual/assistida: criar itens candidatos, revisar, descartar ou enviar ao lote XML.
- Conectores reais de e-mail, Gmail/Microsoft, ERP, pasta monitorada e webhook externo permanecem adiados ate a inbox local estar validada.
- Importacao automatica, consulta Webmania automatica e manifestacao automatica permanecem proibidas.
- `NfseItem`, `FiscalDocument(nfse)` e `FiscalEmissionAttempt` nao devem ser criados pela origem externa de XML.
- Pendencias remanescentes: conectores reais, processamento assincrono completo, relatorios operacionais ampliados e eventual consolidacao `FiscalDocument(nfse)` sob demanda.

## Apos a Fase 3.15.2

- Inbox externa local/manual implementada para XMLs candidatos.
- Pendencias remanescentes: conector real de e-mail, OAuth/Gmail/Microsoft, ERP real, pasta monitorada, webhook externo real, job agendado e pipeline assincrono completo.
- Importacao automatica, consulta Webmania automatica e manifestacao automatica seguem proibidas ate fase propria.
- `NfseItem`, `FiscalDocument(nfse)` e `FiscalEmissionAttempt` continuam fora da inbox.

## Apos a Fase 3.16.0

- Reavaliacao recomenda ampliar a inbox local antes de conectores reais.
- Proxima fase sugerida: filtros, busca, relatorio/exportacao, acoes em massa controladas, retencao, reprocessamento seguro, painel de auditoria e vinculos mais claros com lote/documento.
- Conectores reais de e-mail/ERP, pasta monitorada e webhook externo continuam adiados ate autenticacao, segregacao e contratos externos estarem definidos.
- Consulta Webmania ampliada permanece consultiva e nao deve criar NFS-e recebida.
- Manifestacao manual, NFS-e expandida ampla, CT-e, MDF-e, NFCom, DC-e, eventos IBS/CBS pendentes, creditos/debitos pendentes e complementar tributaria continuam fora do escopo imediato.

## Apos a Fase 3.16.1

- Filtros, busca, CSV e acoes em massa da inbox local foram implementados.
- Pendencias remanescentes da inbox: politica de retencao/arquivamento logico, reprocessamento controlado de erro, painel de auditoria mais analitico e eventual job operacional futuro, todos dependentes de fase propria.
- Conectores reais de e-mail/ERP, OAuth, IMAP, Gmail API, Microsoft Graph, pasta monitorada, Drive, SharePoint e webhook externo continuam adiados.
- Consulta Webmania automatica, manifestacao automatica e criacao direta de documento recebido pela inbox continuam proibidas.
- `NfseItem`, `FiscalDocument(nfse)` e `FiscalEmissionAttempt` continuam fora da inbox.
- CT-e, MDF-e, NFCom, DC-e, eventos IBS/CBS `112120/112140/211xxx`, creditos 2-5, debitos 1-3/5-8 e complementar tributaria seguem nao iniciados.
