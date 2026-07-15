# Fase 1.2 — baseline de performance da Pessoa 1

Data da coleta: 2026-07-12.

Status: **baseline concluído com uma limitação funcional explícita**. Foram obtidas métricas válidas para 26 dos 28 cenários. Os dois cenários de `stock:report` retornaram HTTP 500 antes da renderização completa e, por isso, não entram nos rankings de rotas saudáveis.

Nenhuma correção de dashboard, queryset, filtro de data, helper, paginação, prefetch, overfetch, cache, worker, integração, model, migration ou regra de negócio foi implementada.

## Identidade e metodologia

- SHA funcional: `4a57a0157c5dd10f8ab65e051f35f46730d4abc9`;
- checkpoint do ambiente e SHA medido: `64bd324f7183025e7bc55376d9a5f888f736daf7`;
- banco exclusivo: `hunter_v2_perf_4a57a015`;
- settings: `config.settings_benchmark`;
- dataset: sintético, determinístico, escala `standard`, data de referência `2026-07-12`;
- execução: Django test Client no mesmo processo, mesmo usuário `benchmark.owner`, mesma oficina ativa e mesmo banco;
- protocolo oficial: 2 warmups seguidos de 10 execuções medidas por cenário;
- janela: 2026-07-12 14:29:50–14:32:34 America/Sao_Paulo;
- duração separada em SQL acumulado e estimativa não SQL;
- percentil: nearest-rank para p95;
- SQL capturado por `connection.execute_wrapper`, normalizado para agrupar literais e espaços;
- chamadas HTTP externas capturadas em `requests.Session.request`;
- planos: `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` para os padrões elegíveis entre os dez de maior tempo acumulado.

O artefato bruto completo está em `docs/performance-results/person-one-baseline.json`. A amostra independente de estabilidade está em `docs/performance-results/person-one-baseline-stability-sample.json`.

Limitações: execução in-process, sem Gunicorn ou rede; caches aquecidos e não limpos entre amostras; cardinalidade sintética, não equivalente à produção; `rowcount` representa linhas devolvidas pelos cursores, não pico de memória nem objetos Python únicos; chamadas externas só seriam observadas se as rotas GET as invocassem; ocupação de workers não pode ser medida com Client sequencial.

## Resposta executiva

### Cinco cenários saudáveis mais lentos por p95

| Posição | Cenário | Mediana (ms) | p95 (ms) | Queries |
| ---: | --- | ---: | ---: | ---: |
| 1 | `dashboard_previous_month` | 3.571,58 | 4.403,49 | 201 |
| 2 | `dashboard_current_month` | 3.528,61 | 4.084,78 | 133 |
| 3 | `supplier_update_history` | 287,48 | 518,54 | 119 |
| 4 | `budget_list_default` | 230,05 | 474,32 | 11 |
| 5 | `workorder_list_page_2` | 263,03 | 364,56 | 10 |

`stock_report_default` e `stock_report_search` foram excluídos desse ranking porque responderam 500.

### Rotas saudáveis com mais queries

| Posição | Cenário | Queries | Únicas | Duplicadas | p95 (ms) |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | `dashboard_previous_month` | 201 | 33 | 168 | 4.403,49 |
| 2 | `dashboard_current_month` | 133 | 33 | 100 | 4.084,78 |
| 3 | `supplier_update_history` | 119 | 9 | 110 | 518,54 |
| 4 | `product_update_history` | 34 | 19 | 15 | 147,54 |
| 5 | `workorder_detail_history` | 33 | 25 | 8 | 205,49 |
| 6 | `financial_reports_home` | 22 | 20 | 2 | 303,52 |
| 7 | `customer_history_detail` | 20 | 12 | 8 | 126,93 |
| 8 | `budget_list_filtered` | 15 | 11 | 4 | 295,54 |

## Matriz completa das rotas

Tempos são medianas, salvo a coluna p95. `SQL` e `não SQL` estão em milissegundos. A coluna `N+1` usa a classificação detalhada adiante.

| Cenário | HTTP | Mediana | p95 | Queries | Únicas | Duplicadas | SQL | Não SQL | Query mais lenta observada | N+1 | Observação |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |
| `dashboard_current_month` | 200 | 3.528,61 | 4.084,78 | 133 | 33 | 100 | 317,39 | 3.203,28 | itens de OS, 333,06 ms | confirmado | julho/2026 |
| `dashboard_previous_month` | 200 | 3.571,58 | 4.403,49 | 201 | 33 | 168 | 404,74 | 3.164,71 | itens de budget, 340,07 ms | confirmado | junho/2026 |
| `budget_list_default` | 200 | 230,05 | 474,32 | 11 | 10 | 1 | 33,50 | 191,61 | itens de budget, 14,01 ms | não observado | 1.500 registros |
| `budget_list_page_2` | 200 | 263,02 | 333,33 | 11 | 10 | 1 | 37,09 | 222,90 | budgets, 10,27 ms | não observado | página 2 |
| `budget_list_search` | 200 | 127,28 | 138,23 | 11 | 11 | 0 | 40,65 | 86,83 | budgets, 13,41 ms | não observado | busca ativa |
| `budget_list_filtered` | 200 | 256,23 | 295,54 | 15 | 11 | 4 | 44,45 | 211,34 | budgets, 9,81 ms | não observado | status + período |
| `workorder_list_default` | 200 | 201,21 | 362,63 | 10 | 9 | 1 | 20,42 | 179,81 | OS, 7,47 ms | não observado | 1.000 registros |
| `workorder_list_page_2` | 200 | 263,03 | 364,56 | 10 | 9 | 1 | 28,53 | 235,90 | OS, 8,94 ms | não observado | página 2 |
| `workorder_list_search` | 200 | 110,75 | 180,00 | 10 | 10 | 0 | 29,02 | 83,26 | OS, 15,78 ms | não observado | busca ativa |
| `workorder_list_date_filter` | 200 | 199,33 | 306,66 | 10 | 9 | 1 | 23,66 | 177,32 | itens de OS, 7,82 ms | não observado | `delivered_at__date` |
| `customer_list_default` | 200 | 52,23 | 71,30 | 7 | 7 | 0 | 10,08 | 42,32 | — | não observado | 600 registros |
| `customer_list_page_2` | 200 | 58,97 | 79,50 | 7 | 7 | 0 | 10,66 | 48,80 | — | não observado | página 2 |
| `customer_list_search` | 200 | 60,21 | 74,89 | 7 | 7 | 0 | 13,90 | 46,98 | — | não observado | busca ativa |
| `product_list_default` | 200 | 63,21 | 79,40 | 9 | 9 | 0 | 10,46 | 53,13 | — | não observado | 250 registros |
| `product_list_page_2` | 200 | 75,24 | 108,29 | 9 | 9 | 0 | 12,58 | 61,30 | — | não observado | página 2 |
| `product_list_search` | 200 | 57,14 | 79,06 | 10 | 10 | 0 | 16,99 | 40,10 | itens de budget, 7,14 ms | não observado | busca ativa |
| `customer_history_detail` | 200 | 70,51 | 126,93 | 20 | 12 | 8 | 25,33 | 43,72 | — | não observado | cliente #1 |
| `product_update_history` | 200 | 116,77 | 147,54 | 34 | 19 | 15 | 31,61 | 85,07 | — | provável | produto #1 |
| `issued_documents_default` | 200 | 212,83 | 270,87 | 9 | 9 | 0 | 26,74 | 187,95 | NFS-e, 8,89 ms | não observado | 600 documentos |
| `issued_documents_date_filter` | 200 | 73,02 | 128,00 | 9 | 9 | 0 | 19,27 | 51,52 | — | não observado | intervalo de 2 meses |
| `supplier_update_history` | 200 | 287,48 | 518,54 | 119 | 9 | 110 | 110,74 | 176,74 | — | confirmado | fornecedor #1, 56 movimentos |
| `workorder_detail_history` | 200 | 154,47 | 205,49 | 33 | 25 | 8 | 49,55 | 104,17 | — | não observado | OS #1 |
| `stock_report_default` | 500 | 135,48 | 222,29 | 13 | 10 | 3 | 21,75 | 115,15 | — | inconclusivo | falha funcional antes do resultado |
| `stock_report_search` | 500 | 104,44 | 138,23 | 13 | 10 | 3 | 21,73 | 82,91 | — | inconclusivo | mesma falha com busca |
| `financial_reports_home` | 200 | 260,48 | 303,52 | 22 | 20 | 2 | 127,57 | 129,93 | movimentos, 105,51 ms | não observado | 1.500 movimentos |
| `financial_movement_default` | 200 | 263,04 | 314,00 | 8 | 8 | 0 | 102,82 | 155,89 | movimentos, 102,02 ms | não observado | página inicial |
| `financial_movement_date_filter` | 200 | 192,68 | 321,83 | 8 | 8 | 0 | 74,53 | 118,39 | movimentos, 77,68 ms | não observado | range nativo |
| `commission_date_filter` | 200 | 125,23 | 185,53 | 8 | 8 | 0 | 19,31 | 103,50 | — | inconclusivo | dataset sem comissões |

## Dashboard antes das correções

| Métrica | Julho/2026 | Junho/2026 |
| --- | ---: | ---: |
| Mediana total | 3.528,61 ms | 3.571,58 ms |
| p95 total | 4.084,78 ms | 4.403,49 ms |
| Queries | 133 | 201 |
| Queries únicas | 33 | 33 |
| Queries duplicadas | 100 | 168 |
| SQL acumulado mediano | 317,39 ms | 404,74 ms |
| Não SQL estimado mediano | 3.203,28 ms | 3.164,71 ms |
| Linhas SELECT observadas | 5.152 | 5.447 |
| Resposta mediana | 140.828 bytes | 154.257 bytes |

Evidência: o dashboard materializa listas completas de OS entregues, budgets aprovados, OS em rascunho, budgets pendentes e budgets rejeitados; calcula somas, contagens, partições e rentabilidade em Python. Há dois descritores de prefetch de itens, cada um com três relações aninhadas, além do prefetch de pagamentos. Apesar disso, foram confirmadas duas famílias repetidas por budget: itens (50/84 vezes) e overrides (50/84 vezes). O tempo não SQL representa cerca de 3,2 segundos da mediana e é o maior componente observado.

Filtros `EXTRACT(MONTH...)`/ano aparecem em 40 execuções do padrão de pagamentos e em padrões de OS/budgets. Os principais querysets de itens devolveram até 2.160 linhas numa consulta; a execução individual mais lenta chegou a 340,07 ms. Isso corresponde aos achados estáticos de materialização, loops de métricas, filtros `__month`/`__year` e prefetches amplos.

## Queries mais caras

### Dez execuções individuais mais lentas

| # | Cenário | Operação normalizada | Tempo (ms) | Linhas observadas |
| ---: | --- | --- | ---: | ---: |
| 1 | dashboard anterior | `SELECT budget_budgetitem ...` | 340,07 | 2.160 |
| 2 | dashboard atual | `SELECT workorder_workorderitem ...` | 333,06 | 1.002 |
| 3 | dashboard anterior | `SELECT budget_budgetkititemoverride ...` | 224,53 | n/d |
| 4 | relatórios financeiros | `SELECT DISTINCT finance_financialmovement ...` | 105,51 | 10 |
| 5 | relatórios financeiros | mesmo padrão, outra amostra | 103,76 | 10 |
| 6 | movimentos financeiros | `SELECT finance_financialmovement ...` | 102,02 | 10 |
| 7 | relatórios financeiros | mesmo padrão, outra amostra | 97,44 | 10 |
| 8 | relatórios financeiros | mesmo padrão, outra amostra | 96,38 | 10 |
| 9 | movimentos financeiros | mesmo padrão, outra amostra | 95,39 | 10 |
| 10 | movimentos financeiros | mesmo padrão, outra amostra | 92,92 | 10 |

### Dez padrões com maior tempo acumulado

| # | Padrão | Execuções | Total (ms) | Média (ms) | Máximo (ms) | Plano/observação |
| ---: | --- | ---: | ---: | ---: | ---: | --- |
| 1 | itens de budget por budget | 1.360 | 2.439,38 | 1,79 | 7,61 | index scan por `budget_id`, repetição domina |
| 2 | overrides por item de budget | 1.360 | 1.436,98 | 1,06 | 10,47 | bitmap index scan, repetição domina |
| 3 | overrides amplos do dashboard | 20 | 1.318,08 | 65,90 | 224,53 | seq scan; tabela vazia no seed |
| 4 | movimentos financeiros `DISTINCT` | 10 | 939,97 | 94,00 | 105,51 | joins, sort e unique; planejamento 52,86 ms |
| 5 | lista de movimentos financeiros | 10 | 866,79 | 86,68 | 102,02 | lê 1.500 movimentos antes do limit no plano |
| 6 | itens de budget amplos do dashboard | 20 | 753,92 | 37,70 | 340,07 | até 2.160 linhas por execução |
| 7 | resolução de memberships | 280 | 710,69 | 2,54 | 8,19 | custo request-level transversal |
| 8 | movimentos com range de data | 10 | 646,64 | 64,66 | 77,68 | predicate direto em `due_date` |
| 9 | update de sessão | 260 | 558,60 | 2,15 | 6,10 | efeito do Client/sessão, não regra de negócio |
| 10 | produto por movimento do fornecedor | 560 | 512,48 | 0,92 | 4,24 | N+1 confirmado |

Os planos completos e o SQL integral estão no JSON. O plano de movimentos sem filtro mostrou seq scan de 1.500 movimentos e ordenação antes do `LIMIT 10`; o plano do range de data reduziu o conjunto para 39 movimentos, embora ainda faça seq scan nesta cardinalidade.

## Queries duplicadas e N+1

| Rota | Query base | Query repetida | Repetições/request | Entidade | Classificação | Evidência | Prioridade |
| --- | --- | --- | ---: | --- | --- | --- | --- |
| dashboard anterior | budgets materializados | itens por `budget_id` | 84 | Budget | confirmado | 84 itens + 84 overrides; 201 queries, 168 duplicadas | P0 |
| dashboard atual | budgets materializados | itens por `budget_id` | 50 | Budget | confirmado | 50 itens + 50 overrides; 133 queries, 100 duplicadas | P0 |
| fornecedor | 56 movimentos prefetched | `StockProduct` por id | 56 | StockMovement | confirmado | exatamente uma busca por movimento | P0 |
| fornecedor | 56 movimentos prefetched | `Product` por id | 56 | Product | confirmado | exatamente uma busca por movimento | P0 |
| produto | histórico combinado | usuário por id | 9 | User | provável | padrão repetido 9 vezes em uma request | P1 |
| produto | histórico combinado | fornecedor por id | 8 | Supplier | provável | padrão repetido 8 vezes em uma request | P1 |
| cliente | 3 entradas renderizadas | padrões até 4 vezes | itens de OS | não observado | abaixo do limiar e cardinalidade pequena | P2 |
| detalhe da OS | 3 eventos | padrões até 4 vezes | movimentos/itens | não observado | repetição não proporcional ao histórico | P2 |
| estoque | resposta incompleta | padrões até 4 vezes | estoque/produto | inconclusivo | HTTP 500 impede conclusão | bloqueado |

## Helper compartilhado de tabelas

O helper aplica busca e ordenação e depois pagina. Para QuerySet, o `Paginator` executa `COUNT(*)`; algumas views também executam uma contagem própria, por isso budgets, workorders e customers exibem duas queries COUNT. Nenhum consumidor encontrado habilita hoje `disable_pagination_when_filtered=True`; se habilitado, o helper faz um COUNT adicional para definir `effective_per_page` e efetivamente remove o limite.

| Cenário | Total original | Exibidos | COUNTs | COUNT mediano (ms) | Queries | Busca | Página | Observação |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | --- |
| budgets padrão | 1.500 | 10 | 2 | 8,59 | 11 | não | 1 | queryset completo chega ao helper |
| budgets | 1.500 | 10 | 2 | 10,53 | 11 | não | 2 | custo não cai na página posterior |
| budgets busca | 1.500 | 3 | 2 | 14,46 | 11 | sim | 1 | maior COUNT mediano da matriz |
| budgets filtrado | 1.500 | 5 | 2 | 6,27 | 15 | não | 1 | 4 duplicadas |
| OS padrão | 1.000 | 10 | 2 | 2,47 | 10 | não | 1 | queryset completo chega ao helper |
| OS | 1.000 | 10 | 2 | 3,88 | 10 | não | 2 | mesmo número de queries |
| OS busca | 1.000 | 2 | 2 | 9,06 | 10 | sim | 1 | COUNT aumenta com busca |
| clientes padrão | 600 | 10 | 2 | 3,78 | 7 | não | 1 | — |
| clientes página 2 | 600 | 10 | 2 | 4,01 | 7 | não | 2 | — |
| clientes busca | 600 | 1 | 2 | 8,00 | 7 | sim | 1 | — |
| produtos padrão | 250 | 10 | 1 | 0,92 | 9 | não | 1 | — |
| produtos página 2 | 250 | 10 | 1 | 1,10 | 9 | não | 2 | — |
| produtos busca | 250 | 1 | 1 | 4,82 | 10 | sim | 1 | query adicional de busca |
| movimentos financeiros | 1.500 | 10 | 1 | 2,12 | 8 | não | 1 | query de dados, não COUNT, domina |

O mapa estático registra 30 templates consumidores diretos. Os módulos prioritários confirmados dinamicamente são budget, workorder, customer, catalog e finance; mensagens, grupos financeiros e demais consumidores continuam exigindo compatibilidade retroativa numa correção futura.

## Filtros de data representativos

| Arquivo/rota | Campo e lookup | Parâmetro | Forma SQL | SQL mediano da rota | Linhas SELECT observadas | Índice provável | Prioridade |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| dashboard | `due_date/entry_date/delivered_at__month/__year` | 06 e 07/2026 | `EXTRACT(MONTH...)` e limites de ano | 317–405 ms | 5.152+ | função na coluna dificulta índice composto | P0 |
| `workorder/views.py` / lista | `delivered_at__date` | 01–31/07/2026 | `(delivered_at AT TIME ZONE ...)::date` | 23,66 ms | 46 | cast na coluna pode impedir índice simples | P1 |
| notas emitidas | `criado_em__date__range` | 01/06–31/07/2026 | `(criado_em AT TIME ZONE ...)::date BETWEEN` | 19,27 ms | 76 | cast na coluna | P1 |
| comissões | `criado_em__date__gte/lte` | 01/01–31/07/2026 | cast de data esperado | 19,31 ms | 6 | inconclusivo: zero comissões | P2 |
| movimentos financeiros | `due_date__gte/lte` | 01–31/07/2026 | `due_date >= ... AND <= ...` | 74,53 ms | 15 | predicate direto, forma preferível | referência |

Entre as 37 ocorrências estáticas levantadas, a conversão futura deve começar pelo dashboard, depois notas emitidas e lista de OS. Comissões só deve ser comparada após dataset representativo. Nenhum lookup foi alterado nesta fase.

## Overfetch priorizado

`Linhas SELECT` e bytes são indicadores objetivos; não equivalem a objetos Python únicos ou memória de pico.

| Rota | Entidade | Escopo carregado | Linhas SELECT | Uso/renderização observada | Resposta | Queries | Evidência | Prioridade |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| notas emitidas | NF-e + NFS-e | 600 documentos | 1.204 | 600 linhas | 911.425 B | 9 | duas coleções completas, merge/ordenação antes da apresentação | P0 |
| fornecedor | StockMovement | 56 movimentos | 173 | 56 linhas | 184.691 B | 119 | histórico completo e dois N+1 de 56 | P0 |
| produto | usos do produto | 20 referências | 300 | 249 linhas HTML no primeiro `tbody` | 566.104 B | 34 | quatro fontes, merge/deduplicação e N+1 prováveis | P1 |
| detalhe da OS | WorkOrder | 3 eventos | 28 | 2 linhas | 236.156 B | 33 | contexto amplo para histórico pequeno | P1 |
| histórico do cliente | Budget/OS | 3 entradas | 28 | 3 linhas | 107.952 B | 20 | materialização/ordenação total; baixo volume neste seed | P2 agora, cresce sem limite |

## Dependências externas, background e workers

| Rota/operação | Dependência/tarefa | Durante request | Tempo | Bloqueia worker | Background | Evidência |
| --- | --- | --- | ---: | --- | --- | --- |
| 26 cenários GET saudáveis | HTTP externo via `requests` | não observado | 0 ms | não demonstrado | não classificado | zero chamadas capturadas |
| dashboard | cálculos e materializações locais | sim | mediana 3,53–3,57 s | sim, durante a request | candidata a análise; não decisão | tempo não SQL ~3,2 s e request síncrona |
| fornecedor | renderização de histórico + N+1 | sim | mediana 287,48 ms | sim, durante a request | não; corrigir acesso a dados primeiro | 119 queries |
| notas emitidas | merge/ordenação de 600 documentos | sim | mediana 212,83 ms | sim, durante a request | exportação/geração futura pode ser candidata | 911 KB de resposta; nenhuma integração chamada |
| `stock:report` | falha funcional | sim | n/a | request termina em erro | não aplicável | `AttributeError` antes do resultado |

Não há base para afirmar qual dependência externa mais bloqueia requests: nenhuma foi executada nessa bateria. Também não há medição de quantidade de workers ocupados; o máximo que a Pessoa 1 pode afirmar é que cada operação síncrona ocupa um worker pelo tempo da request. Concorrência, saturação, filas e integrações reais devem ser instrumentadas pelas Pessoas 2 e 3 em Gunicorn/staging.

## Falha funcional encontrada

`stock:report` falha consistentemente com `AttributeError: 'StockReportListView' object has no attribute '_build_stock_report_filter_descriptions'` em `apps/stock/views.py`. Foram 12 tentativas por cenário (2 warmups + 10 medidas), todas com HTTP 500. A falha não foi corrigida por estar fora do escopo de medição; os tempos parciais não representam performance da tela funcional.

## Estabilidade

Uma segunda coleta independente usou 1 warmup e 5 execuções em três cenários:

| Cenário | Oficial mediana | Repetição mediana | Diferença | Queries oficial/repetição |
| --- | ---: | ---: | ---: | ---: |
| dashboard atual | 3.528,61 ms | 3.367,13 ms | -4,6% | 133 / 133 |
| budgets padrão | 230,05 ms | 297,20 ms | +29,2% | 11 / 11 |
| fornecedor | 287,48 ms | 363,55 ms | +26,5% | 119 / 119 |

As formas e contagens de query são estáveis; os tempos locais têm ruído relevante. Comparações pós-correção devem repetir o protocolo oficial completo e considerar diferença material acima dessa variabilidade.

## Backlog da Pessoa 1

### Concluído

- diagnóstico estático, ambiente isolado, migrations estáveis e dataset determinístico;
- baseline oficial, rankings, queries, duplicações, N+1, helper, datas e overfetch;
- artefato estruturado e amostra de estabilidade;
- preservação do banco original.

### Achados quantitativos

1. P0: dashboard, 3,5 s de mediana, 133–201 queries e N+1 de 50–84 budgets.
2. P0: fornecedor, 119 queries para 56 movimentos e dois N+1 confirmados.
3. P0: notas emitidas, 600 documentos/911 KB materializados numa request.
4. P1: queries de movimentos financeiros, 65–94 ms de média por padrão dominante.
5. P1: produto, 34 queries, 566 KB e N+1 prováveis.
6. P1: helper, COUNT duplicado em budgets/OS/clientes e busca elevando custo do COUNT.
7. P1: filtros funcionais por mês/data, priorizando dashboard, notas e OS.
8. Bloqueio funcional separado: `stock:report` retorna 500.

### Pendências externas

- dependências externas reais e duração em staging: Pessoa 2/3;
- workers ocupados, concorrência e saturação: Pessoa 3;
- baseline Gunicorn/rede/infra: Pessoa 3;
- dataset representativo de comissões;
- correção funcional de `stock:report`, mediante autorização própria.

### Próxima fase proposta, não iniciada

**Fase 1.3 — Priorização das Correções de Performance da Pessoa 1**, ordenando correções por impacto, risco e esforço. Nenhuma correção dessa fase foi iniciada.
