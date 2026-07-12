# Fase 1 de performance — diagnóstico da Pessoa 1

Data do levantamento: 2026-07-12.

## Escopo e validade dos dados

Este documento cobre aplicação e banco de dados: dashboard, filtros de data, helper compartilhado de tabelas e telas com overfetch.

O levantamento estático foi executado no código atual. A linha de base dinâmica ainda não é válida porque o PostgreSQL local pertence a uma linha de migrations diferente do checkout. O primeiro acesso ORM que materializa `Workshop` falha com `UndefinedColumn` para `workshops_workshop.whatsapp_phone`, mas essa coluna é apenas o primeiro sintoma. O diagnóstico completo e o plano seguro estão em `docs/performance-phase-1-environment-regularization.md`.

Consequências:

- ainda não há números confiáveis para as cinco rotas mais lentas;
- ainda não há ranking medido de quantidade de queries por rota;
- o tempo do dashboard antes das correções deve permanecer como **não medido**, em vez de usar uma amostra inválida;
- os candidatos abaixo são priorizados por evidência estática e precisam ser confirmados em banco migrado com volume representativo.

Atualização da Fase 1.1: o ambiente isolado `hunter_v2_perf_4a57a015` foi criado, migrado e carregado com dados sintéticos determinísticos. A preparação e suas validações estão em `docs/performance-phase-1-benchmark-environment.md`. Os números quantitativos da Fase 1.2 continuam pendentes.

## Resumo executivo

O inventário encontrou:

- 37 ocorrências de `__month`, `__year` ou `__date` em oito arquivos Python de runtime;
- 73 arquivos Python de runtime contendo `list(...)` (o número inclui listas que não materializam querysets e serve apenas como universo de triagem);
- 29 arquivos Python de runtime contendo `prefetch_related(...)`;
- 30 templates de negócio que usam diretamente o helper compartilhado de tabela, além do wrapper `apps/core/templates/crud/partials/table.html`;
- nenhuma ativação atual de `disable_pagination_when_filtered`, embora o helper ainda suporte o modo caro;
- dois fluxos (`budget` e `workorder`) que entregam explicitamente o queryset completo ao `render_table`, deixando a paginação efetiva a cargo da inclusion tag.

## Dashboard — candidato P0

Rota: `core:dashboard` (`/core/`).

Arquivos principais:

- `apps/core/presentation/views.py`;
- `apps/core/infrastructure/services/dashboard_query_service.py`.

Evidências:

1. `DashboardQueryService.compute()` executa sequencialmente consultas para custo da oficina, orçamentos aprovados, OS entregues, total vendido, vendas do dia, taxa de aprovação, recebíveis pendentes, orçamentos pendentes e rejeitados.
2. A apuração de markup abre um segundo fluxo de consultas: receita, IDs de OS, OS + itens e custos.
3. Os filtros mensais usam `EXTRACT` por meio de `__month/__year` em pagamentos, OS e orçamentos. Isso tende a impedir o uso simples de índices B-tree sobre as colunas de data.
4. São materializados integralmente, com relações de itens:
   - todas as OS entregues no mês;
   - todos os orçamentos aprovados no mês;
   - todas as OS em rascunho da oficina, sem limite temporal;
   - todos os orçamentos abertos da oficina, sem limite temporal;
   - todos os orçamentos rejeitados no mês.
5. Métricas são calculadas em loops Python sobre objetos e propriedades de domínio. Isso amplia CPU, memória e custo de prefetch conforme a oficina cresce.
6. O serviço já emite `business_operation.duration`/log de `compute_dashboard`, mas não registra a decomposição por subconsulta. O middleware de request só registra requests acima do threshold configurado.

Hipótese a validar: o dashboard deve liderar simultaneamente tempo total, SQL acumulado e memória por request em oficinas com histórico longo.

## Filtros de data a converter para ranges

Padrão recomendado para `DateTimeField`: intervalo semiaberto `[início, próximo_início)`, usando datetimes timezone-aware. Para `DateField`, usar `__gte` e `__lt` com datas. O aniversário por mês é uma exceção funcional: não representa um período de um único ano e precisa de estratégia/indexação própria.

| Prioridade | Local | Campo/padrão atual | Conversão esperada |
| --- | --- | --- | --- |
| P0 | `dashboard_query_service.py` | `due_date__month/__year` (linhas de receita, IDs e total vendido) | `due_date__gte=month_start`, `due_date__lt=next_month_start` |
| P0 | `dashboard_query_service.py` | `delivered_at__month/__year` | range timezone-aware sobre `delivered_at` |
| P0 | `dashboard_query_service.py` | `entry_date__month/__year` em aprovados, taxa, rejeitados e relatórios | range sobre `entry_date` |
| P0 | `core/presentation/views.py` | `due_date__month/__year` no relatório financeiro do dashboard | mesmo range mensal do dashboard |
| P1 | `workorder/views.py` | `delivered_at__date` para início/fim | limites datetime `gte/lt` no helper compartilhado |
| P1 | `finance/views/issued_documents.py` | `criado_em__date__range` | `criado_em__gte` e `criado_em__lt` |
| P1 | `finance/views/commissions.py` | `criado_em__date__gte/lte` em dois fluxos | limites datetime `gte/lt` |
| P1 | `messaging/.../message_group_views.py` e duplicata legada `messaging/views.py` | `latest_os_at__date` | limites datetime `gte/lt`; consolidar a duplicata antes de alterar |
| P1 | `messaging/infrastructure/services/segment_query_builder.py` | `latest_os_at__date` e `criado_em__date` | limites datetime `gte/lt` |
| Exceção | `segment_query_builder.py` | `birth_date__month` | manter semântica de aniversário; avaliar índice funcional ou coluna derivada, não range anual |

## Helper compartilhado de tabelas

Arquivo: `apps/core/templatetags/table_tags.py`.

### Comportamento confirmado

- `Paginator(QuerySet, per_page)` chama `QuerySet.count()` para obter o total.
- Página fora do intervalo pode consultar `paginator.num_pages` novamente, embora o resultado de `count` normalmente fique em cache na instância do paginator.
- `disable_pagination_when_filtered=True` chama `ordered_items.count()` para transformar o total em `per_page` e depois materializa todas as linhas filtradas. Hoje não há consumidor ativando a flag.
- Para sequências, busca e ordenação criam novas listas, e `_paginate_sequence()` cria outra lista. Se uma view já materializou um queryset, o helper pode multiplicar o pico de memória.
- Busca e ordenação continuam sendo aplicadas dentro da template tag. Isso explica por que `BudgetListView` e `WorkOrderListView` sobrescrevem o contexto com `self.object_list`: o queryset paginado pela `ListView` não poderia mais ser filtrado pelo helper.

### Mapa de impacto

As superfícies diretamente identificadas são:

- catálogo: grupos, serviços, produtos e kits;
- clientes: lista e lista de histórico;
- orçamento e ordem de serviço;
- estoque: importações, movimentos e relatório;
- financeiro: contas, formas de pagamento, movimentos, grupos, NF-e, NFS-e e seletor da DRE;
- colaboradores, fornecedores, checklists, perguntas investigativas, papéis e oficinas/custos;
- mensagens: templates, grupos e seletor de clientes.

Há 30 templates consumidores diretos. Mudanças na assinatura ou paginação devem ser retrocompatíveis e validadas pelo menos em `budget`, `workorder`, `financial_movement`, `products`, `customer` e no seletor de clientes de mensagens.

### Risco de paginação desabilitada

Nenhum template passa atualmente `disable_pagination_when_filtered=True`. A variável ainda atravessa o wrapper genérico, portanto uma view pode habilitá-la apenas pelo contexto. Recomenda-se remover esse modo ou exigir limite máximo explícito antes de qualquer novo uso.

## Históricos e detalhes com overfetch

| Prioridade | Rota/superfície | Evidência | Risco |
| --- | --- | --- | --- |
| P0 | `customer:customer_history_detail` e `customer:vehicle_history_detail` | `_build_customer_history_context()` carrega todos os orçamentos do cliente, prefetch de todas as OS, converte a relação de cada orçamento em lista e ordena todo o histórico em Python | custo cresce com todo o histórico do cliente; nenhuma paginação/limite |
| P0 | `catalog:product_update` | quatro querysets completos (item direto e override de kit, em orçamento e OS), merge/deduplicação e ordenação em Python | produto muito usado cresce sem limite e retém objetos completos |
| P1 | `finance:issued_documents_list` | materializa listas completas de NF-e e NFS-e, faz merge/ordenação e só depois constrói a apresentação | memória e latência proporcionais ao arquivo fiscal filtrado |
| P1 | `suppliers:supplier_update` | prefetch de todos os `movements` do fornecedor ordenados por data | histórico completo em tela de edição |
| P1 | `workorder:workorder_detail` | contexto inclui `WorkOrderHistory.objects.filter(...).select_related('user')` sem limite | crescimento contínuo do histórico da OS |
| P2 | `stock:stock_list` | carrega até 50 importações e 50 transferências, combina, ordena e só então pagina em blocos de 10 | limitado a 100, mas busca/processa até dez páginas para mostrar uma |
| P2 | edição de colaborador, aba histórico | folha é limitada a 24 e movimentos pendentes são materializados integralmente | folha controlada; movimentos pendentes podem crescer |

## Materializações que merecem medição dirigida

Nem todo `list(queryset)` é defeito. A primeira rodada de profiling deve instrumentar especialmente:

- dashboard: `_aggregate_costs`, `_get_delivered_workorders`, `_get_approved_budget_metrics`, `_get_pending_receivable_metrics`, `_get_pending_budget_metrics`, `_get_rejected_budget_total` e `get_financial_indicator_data`;
- relatórios de status de orçamento e OS: `_get_selection_report_items()` materializa todo o queryset filtrado para resumo/PDF;
- relatórios financeiros: construção de IDs/referências antes da paginação em `finance/views/reports.py`;
- arquivo de notas emitidas: duas listas completas e merge em memória;
- fluxo de caixa e comissões: listas usadas para métricas/linhas;
- serviços de folha: listas de benefícios, comissões e movimentos por colaborador.

## Plano de medição reproduzível

### Pré-condições

1. Aplicar as migrations pendentes em um banco descartável ou backup restaurável.
2. Usar uma oficina com volume representativo e registrar cardinalidades mínimas: clientes, orçamentos, itens, OS, pagamentos, movimentos financeiros, notas e movimentos de estoque.
3. Fixar mês/ano e aquecer cada rota com uma chamada não contabilizada.
4. Medir ao menos 10 repetições por rota e registrar mediana e p95.

### Configuração já disponível

O projeto já possui `RequestPerformanceLoggingMiddleware`. Para diagnóstico local/staging:

```text
PERF_LOGGING_ENABLED=true
PERF_LOG_QUERIES=true
PERF_LOG_MIN_MS=0
```

`PERF_LOG_QUERIES` força debug cursor e tem overhead; não deve ser deixado ligado continuamente em produção.

### Campos mínimos por amostra

- nome da rota e parâmetros normalizados;
- status HTTP;
- duração total;
- quantidade de queries;
- tempo SQL acumulado;
- quantidade de queries duplicadas após normalizar literais;
- maior query individual e respectivo `EXPLAIN (ANALYZE, BUFFERS)`;
- cardinalidade do conjunto de dados;
- pico de memória do processo, quando disponível.

### Primeira bateria de rotas

1. `core:dashboard` para mês atual e mês com maior volume;
2. `budget:budget_list`, sem filtro, com busca e com filtros;
3. `workorder:workorder_list`, sem filtro, com busca e com filtros;
4. `customer:customer_history_detail` do cliente com maior histórico;
5. `catalog:product_update` do produto mais usado;
6. `finance:issued_documents_list` no maior intervalo aceito;
7. `finance:reports_home`;
8. `stock:stock_list` e `stock:report`;
9. `suppliers:supplier_update` do fornecedor com mais movimentos;
10. `workorder:workorder_detail` da OS com mais eventos/itens.

## Critérios para encerrar a frente da Pessoa 1

A frente ainda não está concluída. Ela estará concluída quando a bateria acima produzir:

- ranking das cinco rotas mais lentas por p95;
- ranking das rotas com mais queries;
- baseline do dashboard com duração total, queries e tempo SQL;
- top queries por tempo, com plano de execução;
- confirmação ou descarte dos candidatos de overfetch;
- backlog de correções ordenado por impacto medido e esforço.

Dependências externas bloqueantes e ocupação de workers pertencem primariamente às frentes Pessoas 2 e 3. A Pessoa 1 deve correlacionar esses dados com as rotas, mas não inferi-los apenas a partir do ORM.
