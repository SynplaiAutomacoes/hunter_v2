# Fase 1.3.1-C — otimização efetiva do dashboard da Pessoa 1

Data: 2026-07-12

Branch: `fase1/pessoa1`

HEAD inicial: `9070a0000e7a76a604fc2c70a95463c6fc4c24f4`

Banco isolado: `hunter_v2_perf_3fb8ff31`

## Resultado

As duas reutilizações perdidas no merge foram reaplicadas sem alterar regras do dashboard ou o trabalho da Pessoa 3. Cada reutilização removeu uma consulta por request, reduzindo o dashboard de 29 para 27 queries nos dois períodos. Nenhuma alteração adicional foi mantida porque os demais candidatos seguros aparentes pertencem a N+1/prefetch/pricing/agregações da Pessoa 3 ou à próxima fase de filtros de data.

## Candidatos analisados

| Candidato | Query/cálculo atual | Motivo da redundância | Solução | Risco | Decisão |
|---|---|---|---|---|---|
| Receita mensal no markup | `_aggregate_revenue` repetia a soma já produzida por `_calculate_total_sold` | workshop, período, status, tipo e pagamentos são equivalentes | calcular receita antes e passá-la ao markup | baixo | implementar |
| Aprovados na taxa | segundo `COUNT` repetia `len(approved_budgets)` | mesmo workshop, período e status aprovado | passar `approved_count` já conhecido | baixo | implementar |
| Venda mensal e venda diária | duas somas de pagamento | parecem semelhantes, mas períodos são independentes | nenhuma | mudança de período/filtro | deixar para filtros de data |
| Budgets aprovados e rentabilidade | materialização e loop Python | necessários ao pricing/rentability atual | nenhuma | sobreposição com pricing/prefetch da Pessoa 3 | não implementar |
| Workorders entregues | materialização, separação e total de exibição | alimenta listas do template e usa prefetch/cache integrado | nenhuma | fora do escopo — N+1/Pessoa 3 | não implementar |
| Contagens de entrega | agrega conjunto semelhante aos workorders carregados | cálculo SQL também cobre retorno em garantia | nenhuma | agregação atribuída à Pessoa 3 | não implementar |
| Filtros `__month`/`__year` | extração de data em várias consultas | candidato real de índice | converter para ranges | fase própria | deixar para Fase 1.3.2 |

## Implementação

### Receita mensal

`compute()` agora executa `_calculate_total_sold` antes das métricas de budgets e fornece o mesmo `Decimal` ao cálculo do markup. `calculate_aggregate_markup` mantém fallback para chamadas isoladas, mas não repete `_aggregate_revenue` no fluxo principal.

Predicados preservados em ambas as consultas originais:

- mesmo `workshop_id`;
- status `approved` ou `draft`;
- `budget_type="sale"`;
- mesmo mês/ano de `due_date`;
- mesma fórmula das parcelas.

Resultado: uma query removida por request, sem alteração da fórmula `receita / custo`.

### Contagem aprovada

`_get_approved_budget_metrics` já materializa exatamente os budgets do workshop/período com status aprovado. Seu `approved_count` agora é passado à taxa de aprovação. O método conserva fallback para chamadas isoladas.

Resultado: um `COUNT` removido por request, com numerador idêntico.

Nenhuma materialização ou loop Python adicional pôde ser removido sem tocar responsabilidades da Pessoa 3.

## Equivalência funcional

O benchmark antes/depois usou o mesmo banco, processo, dataset, parâmetros, 2 warmups e 10 execuções medidas. O tamanho da resposta HTML permaneceu exatamente igual: 140.828 bytes no mês atual e 154.257 bytes no mês anterior.

| Métrica | Julho antes/depois | Junho antes/depois |
|---|---:|---:|
| receita mensal | 10.327,00 / 10.327,00 | 24.067,00 / 24.067,00 |
| markup | 2,16 / 2,16 | 2,98 / 2,98 |
| budgets criados | 20 / 20 | 50 / 50 |
| budgets aprovados | 5 / 5 | 10 / 10 |
| taxa de aprovação | 25% / 25% | 20% / 20% |
| carros do mês | 14 / 14 | 28 / 28 |
| budgets pendentes | 285.660,00 / 285.660,00 | 285.660,00 / 285.660,00 |
| total rejeitado | 1.545,00 / 1.545,00 | 4.208,00 / 4.208,00 |

Os oito testes específicos validam também workshop distinto, período anterior, oficina vazia, fallback e independência entre venda mensal e diária.

## Benchmark oficial

Referência pós-merge imediata: `person-one-dashboard-effective-optimization-reference.json`. Resultado oficial: `person-one-dashboard-effective-optimization.json`.

| Cenário | Mediana referência | Mediana nova | Variação | p95 referência | p95 novo | Variação | Queries referência | Queries novas |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| mês atual | 441,63 ms | 312,91 ms | -29,15% | 491,79 ms | 355,75 ms | -27,66% | 29 | 27 |
| mês anterior | 510,28 ms | 442,62 ms | -13,26% | 588,65 ms | 501,32 ms | -14,84% | 29 | 27 |

Tempo SQL mediano caiu de 122,21 para 85,42 ms no mês atual e de 116,27 para 91,94 ms no anterior. Como duas queries pequenas não explicam isoladamente toda a variação de latência, o ganho temporal deve ser lido junto da amostra curta e do ruído local; a redução determinística de duas queries é a evidência estrutural principal.

### Amostra curta de estabilidade

| Cenário | Mediana | p95 | Queries |
|---|---:|---:|---:|
| mês atual | 309,61 ms | 393,98 ms | 27 |
| mês anterior | 291,84 ms | 334,48 ms | 27 |

### Comparação com o baseline original da Fase 1.2

| Cenário | Mediana original | Mediana nova | Variação | p95 original | p95 novo | Variação | Queries originais | Queries novas |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| mês atual | 3.528,61 ms | 312,91 ms | -91,13% | 4.084,78 ms | 355,75 ms | -91,29% | 133 | 27 |
| mês anterior | 3.571,58 ms | 442,62 ms | -87,61% | 4.403,49 ms | 501,32 ms | -88,62% | 201 | 27 |

A comparação com a Fase 1.2 inclui ganhos integrados da Pessoa 3 e stored totals; não deve ser atribuída somente a esta fase. O delta causal da Fase 1.3.1-C é avaliado contra a referência pós-merge de 29 queries.

## Testes e checks

- testes específicos das reutilizações: 8/8;
- bateria auditada do dashboard: 29/29;
- smoke dos dois períodos: HTTP 200;
- respostas do benchmark: HTTP 200 em todas as execuções;
- `manage.py check`: aprovado;
- `makemigrations --check --dry-run`: sem mudanças;
- Ruff focado: aprovado;
- `git diff --check`: aprovado.

## Backlog

### Concluído nesta fase

- reutilização da receita mensal no markup;
- reutilização da contagem aprovada;
- duas queries sequenciais redundantes eliminadas;
- equivalência funcional confirmada;
- benchmark oficial e amostra curta concluídos.

### Fora do escopo — Pessoa 3

- N+1;
- prefetches e `select_related`;
- caches;
- pricing context;
- materializações necessárias ao template;
- agregações já integradas.

### Próxima fase — Pessoa 1

**Fase 1.3.2 — Conversão dos Filtros de Data do Dashboard para Ranges.**

### Fases posteriores

- helper compartilhado de tabelas e `COUNT(*)`;
- querysets completos de budgets/workorders;
- overfetch;
- materializações em outras rotas;
- `stock:report` em fase própria.

## Limites confirmados

Nenhuma migration, model, schema, stored total, backfill ou seed foi alterado. Também permaneceram inalterados filtros de data, helper de tabelas, paginação, workers, integrações, templates e regras de negócio. Nenhuma operação foi executada em `meu_crm`.
