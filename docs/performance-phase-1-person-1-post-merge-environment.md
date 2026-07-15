# Fase 1.3.1-B — estabilização do ambiente pós-merge

Data: 2026-07-12

Branch: `fase1/pessoa1`

HEAD inicial: `3fb8ff318b7ebfd2f396a28e198ae079af9bb059`

Banco novo: `hunter_v2_perf_3fb8ff31`

## Decisão

**Opção A — merge migration, backfill e seed concluídos.** O ambiente integrado está reproduzível e apto a testes e a uma coleta posterior de baseline. Nenhuma das duas reutilizações da Pessoa 1 foi reaplicada.

O checkpoint desta fase é seletivo: a working tree começou com documentos, teste e JSONs modificados/não rastreados de fases anteriores. Esses artefatos foram preservados fora do staging e do commit.

## Estado inicial

- `docs/performance-phase-1-person-1-baseline.md` e `docs/performance-phase-1-person-1.md` já estavam modificados;
- teste, documentos e JSONs da Fase 1.3.1 já estavam não rastreados;
- `dashboard_query_service.py` estava limpo e idêntico ao blob integrado da `main_otimizada`.

## Grafo de migrations

| App | Migration | Dependência | Conteúdo | Conflito | Decisão |
|---|---|---|---|---|---|
| budget | `0056_alter_budgetpdfrenderjob_options_and_more` | `0055_merge_20260706_0122` | metadados do job de PDF | folha 1 | preservar/unir |
| budget | `0056_phase3_hot_path_indexes` | `0055_merge_20260706_0122` | índices | linha integrada | preservar |
| budget | `0057_alter_budgetpdfrenderjob_options_and_more` | `0056_phase3_hot_path_indexes` | metadados equivalentes | intermediária | preservar |
| budget | `0058_wave2_stored_totals` | `0057_alter_budgetpdfrenderjob_options_and_more` | total de Budget | folha 2 | preservar/unir |
| workorder | `0036_phase3_hot_path_indexes` | `0035_workorderitem_is_customer_supplied` | índices | não | preservar |
| workorder | `0037_wave2_stored_totals` | `0036_phase3_hot_path_indexes` | total e pago | não | preservar |
| finance | `0044_phase3_hot_path_indexes` | linha própria | índices | sem dependência cruzada | inalterada |
| stock | `0012_stockmovement_workorder_reversal_of` | linha própria | schema atual | sem dependência cruzada | inalterada |

Foi criada `budget.0059_merge_0056_alter_0058_stored_totals`, dependente das duas folhas e com `operations = []`. Ela não repete operação, não altera schema e não altera dados.

## Stored totals

| Model | Campo | Moeda | Tipo/default/nulo | Regra oficial | Migration | Estado anterior |
|---|---|---|---|---|---|---|
| Budget | `stored_total_amount` | `stored_total_amount_currency` | Money(14,2), zero, não nulo | `pricing_snapshot.total_budget_value` | budget 0058 | write path, sem backfill |
| Budget | `stored_total_amount_currency` | — | CurrencyField, BRL, não nulo | moeda do total | budget 0058 | default BRL |
| WorkOrder | `stored_total_amount` | `stored_total_amount_currency` | Money(14,2), zero, não nulo | `pricing_snapshot.total_budget_value` | workorder 0037 | write path, sem backfill |
| WorkOrder | `stored_total_amount_currency` | — | CurrencyField, BRL, não nulo | moeda do total | workorder 0037 | default BRL |
| WorkOrder | `stored_paid_amount` | `stored_paid_amount_currency` | Money(14,2), zero, não nulo | soma de `payment.total_paid` | workorder 0037 | pagamento, sem backfill |
| WorkOrder | `stored_paid_amount_currency` | — | CurrencyField, BRL, não nulo | moeda do pago | workorder 0037 | default BRL |

Os write paths atuais atualizam Budget/BudgetItem, WorkOrder/WorkOrderItem e WorkOrderPaymentMethod. Sem itens ou pagamentos, a regra produz zero BRL. Descontos, kits, benefícios, peças do cliente, fretes, slider e custos congelados são resolvidos pelo snapshot existente. Dinheiro usa `Decimal`, quantização em centavos e BRL; campos ausentes seguem a normalização vigente para zero.

## Backfill

| Opção | Abordagem | Vantagem | Risco | Decisão |
|---|---|---|---|---|
| A | migration chamando regra atual | automática | modelos históricos não expõem o pricing completo | rejeitada |
| B | fórmula local versionada | histórica | duplicação extensa e risco de divergência | rejeitada |
| C | management command | reutiliza a regra canônica e é reexecutável | passo operacional após migrate | **escolhida** |
| D | apenas benchmark | simples | não resolve bancos existentes | somente complementar |

`backfill_stored_totals` processa em lotes, aceita `--workshop-id`, examina todos os registros no escopo e grava somente divergências. Não chama integrações e não depende de request, usuário ou cache. A migration isolada resolve o grafo; a consistência de bancos existentes exige executar o comando após `migrate`.

```powershell
uv run python manage.py backfill_stored_totals --batch-size 250
```

Reexecução validada: 1.500 budgets e 1.000 workorders examinados, zero atualizações necessárias.

## Seed

| Entidade | Criação | Problema | Correção | Validação |
|---|---|---|---|---|
| Budget/BudgetItem | `bulk_create` | write path não executa | recálculo após itens e custos | 1.500/4.500 cobertos |
| WorkOrder/WorkOrderItem | `bulk_create` | write path não executa | recálculo após itens | 1.000/3.000 cobertos |
| Payment | `bulk_create` | total pago não atualiza | mesmo recálculo após pagamentos | 1.500 cobertos |

Foi escolhida criação em lote seguida de reconstrução, preservando desempenho e a regra oficial. O seed padrão pós-correção durou aproximadamente 64 segundos. Não há tempo anterior comparável: o banco pré-merge não tinha as colunas. Repetição no mesmo banco continua recusada; o comportamento suportado é recriar um banco descartável.

## Banco e valores

- migrations do zero: sucesso;
- migrations pendentes: nenhuma;
- Workshop: 2; Budget: 1.500; WorkOrder: 1.000;
- divergências canônicas em 1.500 budgets: 0;
- divergências de total/pago em 1.000 workorders: 0;
- soma Budget: 595071.00 BRL;
- soma WorkOrder: 396633.00 BRL;
- soma paga: 605000.00 BRL.

| Entidade | Itens | Stored | Recalculado | Pago stored/recalculado | Moeda | Diferença |
|---|---:|---:|---:|---:|---|---:|
| Budget 1 | 3 | 345.00 | 345.00 | — | BRL | 0.00 |
| Budget 2 | 3 | 347.00 | 347.00 | — | BRL | 0.00 |
| Budget 1500 | 3 | 341.00 | 341.00 | — | BRL | 0.00 |
| WorkOrder 1 | 3 | 345.00 | 345.00 | 600.00/600.00 | BRL | 0.00 |
| WorkOrder 2 | 3 | 347.00 | 347.00 | 502.00/502.00 | BRL | 0.00 |
| WorkOrder 1000 | 3 | 350.00 | 350.00 | 598.00/598.00 | BRL | 0.00 |

Testes adicionais cobrem ausência de itens/pagamentos, múltiplos itens, frações, moeda, equivalência e idempotência.

## Testes, smoke e checks

| Conjunto | Coletados | Executados | Passaram | Erros | Bloqueados |
|---|---:|---:|---:|---:|---:|
| 29 auditados | 29 | 29 | 26 | 3 | 0 |
| setup do benchmark | 5 | 5 | 5 | 0 | 0 |
| backfill novo | 3 | 3 | 3 | 0 | 0 |

Os três erros auditados são exatamente as APIs pendentes da próxima fase: `approved_count` em dois testes e `total_revenue` em um. O bloqueio de migrations/coleta foi eliminado.

Smoke autenticado: dashboard mês atual 200, dashboard mês anterior 200, lista de budgets 200, lista de workorders 200 e detalhe de workorder 200. Tempos incidentais não são baseline.

| Check | Resultado |
|---|---|
| `showmigrations budget` | todas aplicadas, inclusive 0059 |
| `makemigrations --check --dry-run` | sem mudanças |
| `migrate --plan` | nenhuma operação |
| `migrate --check` | sucesso |
| `manage.py check` | zero issues |
| Ruff focado | aprovado |
| Mypy focado | bloqueado por 153 erros preexistentes/importados em 34 arquivos; nenhum apontado diretamente nos quatro alvos |
| `git diff --check` | aprovado |
| `git diff --cached --check` | aprovado; sete arquivos seletivamente staged |
| `git status --short` | mudanças externas legítimas preservadas fora do checkpoint seletivo |
| hash normalizado de `dashboard_query_service.py` | `b074083464baa75d3245bd63daab0dac86cc54a0`, igual ao HEAD |
| `meu_crm` antes | `307:66305be6345440df62c233acac610189` |
| `meu_crm` depois | `307:66305be6345440df62c233acac610189` |

## Arquivos funcionais

- `apps/budget/migrations/0059_merge_0056_alter_0058_stored_totals.py`;
- `apps/core/infrastructure/services/stored_totals.py`;
- `apps/core/management/commands/backfill_stored_totals.py`;
- `apps/core/management/commands/seed_performance_benchmark.py`;
- `apps/core/test_stored_totals_backfill.py`.

## Backlog

Concluído nesta fase: merge migration, backfill, seed, banco novo, validação integral, testes desbloqueados e smoke.

Pendente da Pessoa 1: reaplicar receita mensal no markup e contagem aprovada, fazer os 29 testes passarem, coletar baseline, repetir benchmark e encerrar a Fase 1.3.1.

Fora do escopo da Pessoa 3: prefetches, caches, pricing context, agregações e N+1 permaneceram preservados.

Próxima fase: **Fase 1.3.1-C — Reaplicação das Duas Reutilizações de Métricas da Pessoa 1**.
