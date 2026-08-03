# Fase 4.2.10 — Preparação final da branch `fase1/pessoa1` para entrega

Data da auditoria: 31/07/2026.

## 1. Resumo executivo

A linha fiscal 4.2.x está consolidada na branch oficial `fase1/pessoa1`. O commit atual contém todos os commits fiscais auditados, a rota principal de emissão resolve para o gateway e não existem alterações pendentes no código fiscal.

A working tree não está limpa por causa de artefatos locais anteriores à consolidação. Esses arquivos foram preservados, não pertencem ao merge fiscal e precisam ser tratados separadamente antes de uma entrega da branch inteira.

Nenhum código foi alterado, nenhum commit foi criado e nenhum push foi realizado nesta fase. Este relatório é o único arquivo criado pela Fase 4.2.10.

## 2. Estado consolidado

- Branch: `fase1/pessoa1`.
- HEAD: `553b7ceb7380addafb0382ef5a0d7992c4dedf84`.
- Mensagem: `chore: merge fiscal workflow improvements into fase1`.
- Pais do merge:
  - `94a7dfeddd28076a4826effbab04a874473a77c8`, estado anterior da `fase1/pessoa1`;
  - `c250670c4b44053579a75e515fa50de23e8cf513`, fechamento da Fase 4.2.7D.
- Backup anterior ao merge: `backup/pre-fiscal-merge`, em `94a7dfeddd28076a4826effbab04a874473a77c8`.

Commits 4.2.x confirmados como ancestrais do HEAD:

| Fase | Commit | Entrega principal |
|---|---|---|
| 4.2.1 | `4f3b6939` | Gateway de operações fiscais |
| 4.2.2/4.2.3 | `314b234d` | Origem WORK_ORDER/MANUAL e emissão manual inicial |
| 4.2.4 | `0f75b9b7` | Cadastro rápido e múltiplos itens |
| 4.2.5 | `c67ad1d2` | Operações fiscais pelo gateway |
| 4.2.6 | `990ea921` | Revisão da Central Fiscal e permissões |
| 4.2.7A | `f4e33a2c` | Wizard manual integrado à emissão principal |
| 4.2.7B | `8a7f3922` | Navegação fiscal e Central de Notas |
| 4.2.7C | `79c399b6` | UX dos formulários fiscais |
| 4.2.7D | `c250670c` | Revisão final de UX e permissões |

## 3. Funcionalidades entregues

- `/finance/emissao/` abre `FiscalOperationGatewayView`.
- O wizard produtivo anterior permanece em `/finance/emissao/normal/`, por `EmissionRequestCreateView`.
- NF-e Normal permite escolher entre Ordem de Serviço e Emissão Manual.
- Emissão manual sem OS, orçamento ou dependência de estoque.
- Destinatário existente e cadastro rápido de pessoa no domínio já utilizado.
- Produto existente, cadastro rápido de produto e múltiplos itens.
- Revisão antes da emissão manual.
- Mesmo builder NF-e, payload Webmania, serviço fiscal e `FiscalEmissionAttempt` para WORK_ORDER e MANUAL.
- Devolução, Carta de Correção, Nota Complementar e Nota de Ajuste acessíveis pelo gateway e pela seleção da NF-e de referência.
- Transporte preservado dentro da NF-e por Ordem de Serviço.
- Central de Notas, histórico, downloads, cancelamento e inutilização preservados.
- Permissões existentes aplicadas na apresentação e nos endpoints finais.

## 4. Validações registradas

### Roteamento

O resolver Django confirmou:

```text
/finance/emissao/        -> FiscalOperationGatewayView
/finance/emissao/normal/ -> EmissionRequestCreateView
```

### Testes

- Regressão fiscal consolidada: **104/104 testes aprovados**.
- Cobertura exercitada: gateway, Central de Notas, NF-e via OS, NF-e manual, cadastro rápido, múltiplos itens, CC-e, devolução, complementar, ajuste, transporte, cancelamento, inutilização, permissões, histórico e downloads.
- Validação complementar de classes tributárias/NFS-e na consolidação: **15/15 testes aprovados**.
- A suíte ampla `apps.finance` registrou 273/281 aprovações. As oito falhas restantes pertencem a expectativas de texto corrompidas em `apps/finance/test_payroll.py`, como `cria├º├úo`, e não aos fluxos fiscais 4.2.x.

### Migrations

- `finance.0082_nferequest_emission_origin_and_more`: aplicada.
- `finance.0083_nferequestmanualitem_and_more`: aplicada.
- Todas as migrations de `finance` estão marcadas como aplicadas.
- `python manage.py migrate --plan`: nenhuma operação planejada.
- A migration local não rastreada `workshops.0031_alter_workshopcost_total_monthly_costs_and_more` também aparece como aplicada no banco atual.

### Qualidade e integridade

- `python manage.py check`: aprovado na consolidação.
- `python manage.py makemigrations finance --check --dry-run`: nenhuma alteração.
- Ruff nos arquivos integrados: aprovado após a resolução dos imports do merge.
- `git diff --check`: aprovado.
- Alterações pendentes em `apps/finance`, serviços Webmania e navegação fiscal: nenhuma.

## 5. Estado Git detalhado

### Alterações pertencentes ao merge fiscal

Nenhuma pendente. O conteúdo fiscal está registrado no commit `553b7ceb`.

### Alterações locais preexistentes

| Estado | Arquivo | Origem provável | Recomendação |
|---|---|---|---|
| Modificado, não staged | `.gitignore` | Inclusão local de `script.ps1` | Decidir se a regra é compartilhável. Se for pessoal, usar exclusão local do Git; se for padrão do projeto, registrar em commit próprio. |
| Modificado, não staged | `docs/performance-phase-1-person-1-baseline.md` | Atualização da Fase 1.3.1 de performance | Revisar e consolidar junto aos demais artefatos de performance, em commit separado do fiscal. |
| Modificado, não staged | `docs/performance-phase-1-person-1.md` | Atualização e auditoria pós-merge de performance | Mesma recomendação: commit próprio de performance após revisão. |
| Adicionado no índice e modificado fora do índice (`AM`) | `script.ps1` | Helper local para carregar variáveis do `.env` | O índice contém a versão vazia e a working tree contém 26 linhas. Corrigir intencionalmente o staging antes de qualquer commit; não incluir acidentalmente na entrega fiscal. |

### Arquivos não rastreados

| Arquivo | Origem provável | Recomendação |
|---|---|---|
| `apps/workshops/migrations/0031_alter_workshopcost_total_monthly_costs_and_more.py` | Migration gerada para campos monetários de custos da oficina | Está aplicada no banco atual. Revisar com os models correspondentes e versionar em commit próprio antes de entregar outro ambiente; não apagar automaticamente. |
| `docs/fiscal-webmania/12-fase-4-1-0-inventario-tecnico-nfe-operacional.md` | Inventário documental da Fase 4.1.0 | Revisar numeração/duplicidade e versionar como documentação fiscal se aprovado. |
| `docs/fiscal-webmania/12-fase-4-2-0-inventario-central-emissao.md` | Inventário documental da Fase 4.2.0 | Revisar numeração/duplicidade e versionar como documentação fiscal se aprovado. |
| `docs/performance-phase-1-person-1-dashboard-metrics.md` | Relatório da Fase 1.3.1 de performance | Agrupar com o commit próprio de performance. |
| `docs/performance-phase-1-person-1-dashboard-post-merge-audit.md` | Auditoria pós-merge de performance | Agrupar com o commit próprio de performance. |
| `docs/performance-results/person-one-dashboard-metrics-after-stability.json` | Evidência de benchmark | Validar tamanho, necessidade de versionamento e ausência de dados sensíveis antes do commit. |
| `docs/performance-results/person-one-dashboard-metrics-after.json` | Evidência de benchmark | Mesma recomendação; arquivo de aproximadamente 686 KiB. |

Após a criação deste relatório, `docs/fiscal-webmania/15-fase-4-2-10-preparacao-entrega.md` também permanece não rastreado por determinação da fase, que proíbe commit.

## 6. Pendências reais antes da entrega

1. Tratar intencionalmente o estado `AM` de `script.ps1`; no estado atual, um commit genérico pode registrar somente um arquivo vazio.
2. Revisar e versionar separadamente a migration `workshops.0031`, já aplicada no banco local, para que outro ambiente possa reproduzir o schema.
3. Decidir o destino dos documentos e resultados de performance sem misturá-los ao ciclo fiscal.
4. Revisar os dois inventários fiscais não rastreados e a duplicidade de prefixo `12-`.
5. Corrigir, em fase própria, as oito expectativas mojibake de `apps/finance/test_payroll.py` se a exigência de entrega for a suíte `apps.finance` totalmente verde.
6. A homologação com transmissão real para Webmania/SEFAZ não foi executada, pois geraria efeito externo; a integração foi validada com providers simulados.
7. A auditoria anterior identificou que um fornecedor cadastrado somente como `Supplier` ainda não é selecionável diretamente como destinatário manual; o fluxo atual reutiliza `Customer` e o cadastro rápido correspondente.

## 7. Conclusão

O ciclo fiscal 4.2.x está tecnicamente consolidado, versionado e sem modificações pendentes em seu código. A branch `fase1/pessoa1` ainda não deve ser tratada como working tree limpa para uma entrega indiscriminada: os arquivos locais listados precisam de decisões próprias. Nenhum deles deve ser removido, descartado ou incluído em commit fiscal automaticamente.
