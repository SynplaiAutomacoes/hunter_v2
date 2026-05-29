# Backlog e pendencias fiscais

## Decisoes que exigem aprovacao

- Manter models legados com camada de compatibilidade ou migrar diretamente para dominio unificado.
- Fase 2.2B.1 validada somente para complementar de preco/quantidade local; aprovar explicitamente a Fase 2.2B.2 antes de qualquer codigo de complementar tributaria.
- Fase 2.2C validada somente para Nota Fiscal de Ajuste; aprovar explicitamente qualquer evolucao de UI avulsa ampla, ajuste com novas origens ou outras operacoes NF-e.
- Aprovar politica final de permissoes fiscais para novas operacoes Fase 2.2+; Fase 2.1 nao concedeu emissao CC-e por fallback legado.
- Evoluir `FiscalEmissionAttempt` minimo para dominio unificado futuro.
- Politica final de permissoes fiscais.
- Aprovar explicitamente a Fase 2.3 funcional antes de qualquer codigo NFC-e.
- Confirmar politica de habilitacao NFC-e por oficina usando configuracao existente em `WebmaniaCompany`.
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
- Confirmar tipos oficiais `tipo_credito` e `tipo_debito` antes da Fase 2.5.
- Importacao/validacao de NF-e externa por XML ou API fiscal especifica fica fora da Fase 2.2A.
- Habilitar devolucao parcial de NF-e externa somente depois de importar/validar XML ou fonte fiscal que preserve sequenciais fiscais e quantidades originais.
- Confirmar requisitos NFC-e por oficina: serie, CSC/token, ambiente, contingencia e DANFE NFC-e; Fase 2.3.0 recomenda reaproveitar `WebmaniaCompany`.
- Confirmar suporte e semantica de cancelamento por substituicao de NFC-e antes de implementar essa variacao.
- Confirmar se inutilizacao NFC-e entra na primeira subfase funcional ou fica para subfase propria.
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
