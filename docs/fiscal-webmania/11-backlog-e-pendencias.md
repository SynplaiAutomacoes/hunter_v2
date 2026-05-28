# Backlog e pendencias fiscais

## Decisoes que exigem aprovacao

- Manter models legados com camada de compatibilidade ou migrar diretamente para dominio unificado.
- Aprovar implementacao funcional da Fase 2.2A antes de qualquer codigo de devolucao/estorno.
- Aprovar implementacao funcional da Fase 2.2B antes de qualquer codigo de complementar.
- Aprovar implementacao funcional da Fase 2.2C antes de qualquer codigo de ajuste.
- Aprovar politica final de permissoes fiscais para novas operacoes Fase 2.2+; Fase 2.1 nao concedeu emissao CC-e por fallback legado.
- Evoluir `FiscalEmissionAttempt` minimo para dominio unificado futuro.
- Politica final de permissoes fiscais.
- Quando habilitar NFC-e.
- Confirmar se NFC-e tera feature/config por oficina antes de aparecer na UI.
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
- Confirmar cenarios de ajuste que exigem ou dispensam documento original.
- Confirmar tipos oficiais `tipo_credito` e `tipo_debito` antes da Fase 2.5.
- Importacao/validacao de NF-e externa por XML ou API fiscal especifica fica fora da Fase 2.2A.
- Confirmar requisitos NFC-e por oficina: serie, CSC/token, ambiente, contingencia e DANFE NFC-e.
- Confirmar suporte e semantica de cancelamento por substituicao de NFC-e antes de implementar essa variacao.
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
