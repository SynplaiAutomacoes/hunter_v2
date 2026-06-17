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
- Criterios de ativacao de NFCom beta.
- Criterios de ativacao de DC-e beta.

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
- Fase 2.4D.3 validou somente `112150` para NF-e normal local autorizada. Permanecem pendentes: cancelamento do `112150`, suporte NFC-e para `112150` caso a regra operacional seja confirmada, `112120`, `112130` e `112140` com itens/valores IBS-CBS/controle operacional, `211128` dependente de credito/debito e demais `211xxx` dependentes de papel destinatario, documento de aquisicao ou apuracao externa.
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
