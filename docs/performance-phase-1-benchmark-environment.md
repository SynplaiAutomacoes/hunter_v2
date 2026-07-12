# Fase 1.1 — ambiente isolado de benchmark da Pessoa 1

Data de preparação: 2026-07-12.

Status: **ambiente isolado criado, migrado, semeado e aprovado para iniciar a Fase 1.2**.

Esta etapa não alterou dashboard, querysets, filtros de data, helper de tabelas, paginação, prefetches, cache, workers ou integrações.

## Identidade da baseline

- SHA-base selecionado: `4a57a0157c5dd10f8ab65e051f35f46730d4abc9`;
- branch de preparação: `fase1/pessoa1`;
- decisão de linhagem: usar exclusivamente as migrations presentes nessa linha de `main`, acrescidas da migration de estabilização de estado `budget.0056`;
- banco: `hunter_v2_perf_4a57a015`;
- usuário PostgreSQL: `usuario_crm`;
- settings: `config.settings_benchmark`;
- dataset: `standard`, sintético e determinístico;
- data de referência do dataset: `2026-07-12`;
- banco preservado: `meu_crm`.

O SHA acima identifica o código funcional anterior aos arquivos de preparação. O checkpoint desta etapa contém somente migration de estado, settings, seed, testes e documentação; a coleta deve registrar também o `HEAD` retornado por `git rev-parse HEAD`.

## Decisão sobre o drift de `BudgetPdfRenderJob`

Decisão: **Opção A — criar a migration antes do benchmark**, dentro da branch técnica já existente `fase1/pessoa1`.

O model e a migration inicial foram introduzidos juntos pelo commit `70da0f25674421a580b838736f7183b902bab365`, em 2026-07-06. A migration foi escrita manualmente e não refletiu integralmente o estado do model.

| Item | Estado no model | Estado nas migrations antes da preparação | Migration esperada | Pertence ao SHA escolhido | Impacto no benchmark | Decisão |
| --- | --- | --- | --- | --- | --- | --- |
| `Meta.ordering` | não definido em `BudgetPdfRenderJob` | `0054` registrava `['-criado_em', '-pk']` | `AlterModelOptions` removendo o ordering divergente | sim; a divergência nasceu no commit de criação | não muda coluna, mas fazia `makemigrations --check` falhar e tornava o grafo não reproduzível | corrigir em `budget.0056` |
| `criado_em.verbose_name` | herdado como `Data de Criação` | `0054` omitia `verbose_name` | `AlterField` de estado/metadata | sim | sem alteração material de dados; necessário para estado coerente | corrigir em `budget.0056` |
| `atualizado_em.verbose_name` | herdado como `Data de Atualização` | `0054` omitia `verbose_name` | `AlterField` de estado/metadata | sim | sem alteração material de dados; necessário para estado coerente | corrigir em `budget.0056` |

A migration criada foi `apps/budget/migrations/0056_alter_budgetpdfrenderjob_options_and_more.py`. Após sua inclusão, `makemigrations --check --dry-run` retornou `No changes detected` e código zero.

O drift não exige fase funcional própria: ele é estritamente uma correção de reprodutibilidade do grafo e não modifica regras de negócio ou performance.

## Estratégia do banco

| Item | Decisão | Justificativa | Risco | Critério de conclusão |
| --- | --- | --- | --- | --- |
| SHA utilizado | `4a57a015...` como SHA-base funcional | corresponde à `main` selecionada para a Fase 1 | confundir SHA-base com checkpoint do ambiente | registrar ambos no relatório da coleta |
| Branch | `fase1/pessoa1` | já é a branch técnica isolada da frente | acumular correções funcionais indevidas | aceitar apenas preparação/medição até a Fase 1.2 |
| Banco | `hunter_v2_perf_4a57a015` | nome contém propósito e SHA curto | colisão com recriação anterior | seed recusa banco não vazio |
| Usuário | `usuario_crm` | usuário local já autorizado no container | privilégio também alcança `meu_crm` | settings e comando possuem guard por nome |
| Configuração | `DJANGO_SETTINGS_MODULE=config.settings_benchmark` e `BENCHMARK_DB_NAME=hunter_v2_perf_4a57a015` | não altera `.env` compartilhado ou produção | esquecer uma variável | import do settings falha sem prefixo correto |
| Isolamento | prefixo obrigatório `hunter_v2_perf_`; `meu_crm` explicitamente proibido | impede uso acidental do default | execução fora do settings protegido | comando valida também a conexão ativa |
| Criação | `createdb` explícito no container PostgreSQL | simples e reproduzível | criar sobre nome existente | `createdb` falha se já existir |
| Limpeza | descartar somente o nome aprovado, após conferência literal | benchmark deve ser recriável do zero | comando destrutivo aplicado ao nome errado | gate manual e prefixo antes de `dropdb` |
| Recriação | criar banco vazio, migrar e executar seed | elimina resíduos entre rodadas | tempo de migrations/seed | checks de migrations e contagens devem repetir |
| Seed | management command protegido, `--scale standard` | dados sintéticos, determinísticos e versionados | `bulk_create` não exercita todos os signals/normalizadores | apropriado para forma/carga de consultas; não usar como teste funcional completo |
| Proteção adicional | seed exige `BENCHMARK_ENVIRONMENT=True`, prefixo e banco sem `Account` | evita contaminação e seed parcial | guard removido em mudança futura | cinco testes unitários do guard/determinização |

### Configuração

```powershell
$env:DJANGO_SETTINGS_MODULE = 'config.settings_benchmark'
$env:BENCHMARK_DB_NAME = 'hunter_v2_perf_4a57a015'
```

`config.settings_benchmark` também usa email em memória, conexão sem persistência e habilita a instrumentação já existente para a futura Fase 1.2. Nenhuma integração externa é configurada pelo seed.

### Comandos utilizados

```powershell
docker compose exec -T postgres createdb -U usuario_crm -O usuario_crm hunter_v2_perf_4a57a015

$env:DJANGO_SETTINGS_MODULE = 'config.settings_benchmark'
$env:BENCHMARK_DB_NAME = 'hunter_v2_perf_4a57a015'

uv run python manage.py makemigrations --check --dry-run
uv run python manage.py migrate --plan
uv run python manage.py migrate --noinput
uv run python manage.py migrate --check
uv run python manage.py check
uv run python manage.py seed_performance_benchmark --scale standard
```

### Processo documentado de recriação

O drop não foi executado nesta etapa. Para uma rodada futura, exige aprovação e conferência literal do nome:

```powershell
$benchmarkDb = 'hunter_v2_perf_4a57a015'
if (-not $benchmarkDb.StartsWith('hunter_v2_perf_')) { throw 'Nome de banco recusado' }
if ($benchmarkDb -eq 'meu_crm') { throw 'Banco protegido' }

docker compose exec -T postgres dropdb -U usuario_crm --if-exists $benchmarkDb
docker compose exec -T postgres createdb -U usuario_crm -O usuario_crm $benchmarkDb
```

Depois, repetir migrations, checks e seed. O seed se recusa a executar se já houver uma `Account`; a estratégia é recriar, nunca apagar parcialmente os dados pelo comando.

## Dados determinísticos

| Entidade | Volume standard | Relações necessárias | Rota atendida | Motivo |
| --- | ---: | --- | --- | --- |
| Contas | 1 | owner | autenticação/tenancy | sessão reproduzível |
| Workshops | 2 | mesma conta e membership | dashboard e escopo multi-oficina | validar oficina ativa sem misturar tenants |
| Usuários | 1 | owner, role Diretor, todas as permissões | todas as rotas críticas | usuário sintético autorizado |
| Clientes | 600 | um veículo cada | listas e histórico do cliente | paginação, busca e histórico |
| Veículos | 600 | cliente/workshop | budget, OS e histórico | relações exibidas nas telas críticas |
| Produtos | 250 | grupo e estoque | lista/edição de produto | `COUNT(*)`, uso histórico e prefetch |
| Serviços | 80 | workshop | itens de budget/OS | cálculo e relações heterogêneas |
| Fornecedores | 40 | estoque/movimentos | edição de fornecedor | histórico com overfetch |
| Budgets | 1.500 | cliente, veículo, usuário e workshop | dashboard e lista de orçamentos | volume, status e datas em 24 meses |
| Itens de budget | 4.500 | dois produtos e um serviço por budget | dashboard, históricos e detalhe de produto | detectar custo por item/relação |
| Histórico de budget | 3.000 | dois eventos por budget | detalhe/histórico | overfetch e ordenação |
| Ordens de serviço | 1.000 | budget/workshop | dashboard, lista e detalhe | rascunhos e entregues em datas diferentes |
| Itens de OS | 3.000 | dois produtos e um serviço por OS | dashboard e produto | carga de prefetch e propriedades calculadas |
| Pagamentos de OS | 1.500 | 1–2 por OS | dashboard/financeiro | filtros mensais e somas |
| Histórico de OS | 3.000 | três eventos por OS | detalhe da OS | crescimento do histórico |
| NF-e requests/items | 300/300 | OS/workshop | notas emitidas | merge, prefetch e arquivo fiscal |
| NFS-e requests/items | 300/300 | OS/workshop | notas emitidas | segundo ramo do merge fiscal |
| Movimentos financeiros | 1.500 | pagamento, OS, grupo e forma de pagamento | relatórios financeiros | paginação, filtros e agrupamentos |
| Produtos em estoque | 250 | produto/fornecedor | estoque e produto | consulta de saldo |
| Movimentos de estoque | 2.000 | oito por produto | estoque e fornecedor | históricos e ordenação |
| Custos da oficina | 24 | dias trabalhados por mês | dashboard | projeções em 24 meses |

As datas são distribuídas deterministicamente ao longo de 730 dias anteriores a 2026-07-12. Isso cobre `__date`, `__month`, `__year`, períodos atuais/anteriores e múltiplos estados.

## Validações executadas

| Validação | Resultado |
| --- | --- |
| conexão antes das migrations | banco ativo confirmado como `hunter_v2_perf_4a57a015`; diferente de `meu_crm` |
| `makemigrations --check --dry-run` | código 0; `No changes detected` |
| `migrate --plan` antes da aplicação | grafo completo e exclusivo do checkout, incluindo `budget.0056` |
| aplicação limpa | todas as migrations aplicadas com sucesso no banco descartável |
| migrations registradas | 306 registros; zero registrados sem arquivo e zero arquivos não aplicados |
| `migrate --check` | código 0 |
| `manage.py check` | zero issues |
| materialização de `Workshop` | `Workshop.objects.first()` executou; após seed retornou `Oficina Benchmark 1` |
| consultas por entidade | contagens do seed confirmadas em todas as entidades da matriz |
| smoke de rotas | 10/10 rotas retornaram HTTP 200 |
| testes do setup | 5 testes passaram; banco não utilizado pelo runner |
| lint focado | passou nos arquivos novos/alterados antes do fechamento |
| lint completo | bloqueado por 165 erros preexistentes fora do escopo |
| mypy completo | bloqueado por 305 erros preexistentes em 99 arquivos; nenhum erro apontado para os arquivos novos |
| teste existente `apps.budget.test_pdf_jobs` | 1 passou e 2 falharam: esperavam HTTP 202, receberam 200; não alterado por estar fora do setup |

Rotas do smoke:

- `core:dashboard`;
- `budget:budget_list`;
- `workorder:workorder_list`;
- `customer:customer_history_detail`;
- `catalog:product_update`;
- `finance:issued_documents_list`;
- `finance:reports_home`;
- `stock:stock_list`;
- `suppliers:supplier_update`;
- `workorder:workorder_detail`.

O smoke do dashboard registrou incidentalmente uma única execução fria de aproximadamente 15 segundos. Esse número **não é baseline**: não houve warm-up, repetição, mediana, p95 nem protocolo de coleta. Ele não deve ser usado como entregável quantitativo da Fase 1.2.

## Prova de preservação de `meu_crm`

Antes da criação do ambiente, o histórico de `meu_crm` tinha:

```text
307:66305be6345440df62c233acac610189
```

Depois de migrations, seed e smoke no banco descartável, a assinatura permaneceu exatamente igual:

```text
307:66305be6345440df62c233acac610189
```

Formato: `quantidade_de_registros:md5(app/name/applied ordenados)`.

Confirmações:

- nenhuma migration foi aplicada em `meu_crm`;
- `django_migrations` de `meu_crm` não foi alterado;
- schema e dados de `meu_crm` não foram alterados por esta etapa;
- o banco descartável possui histórico independente (`306` registros) e tamanho aproximado de 25 MB após o seed.

## Riscos residuais

1. O SHA-base não inclui os arquivos de preparação; a coleta deve registrar também o SHA do checkpoint do ambiente.
2. O seed usa `bulk_create` para volume e deliberadamente não reproduz todos os signals/normalizadores. Ele serve para forma e carga de consultas, não para homologação funcional.
3. O volume standard é controlado, não equivalente a produção. A Fase 1.2 deve sempre registrar cardinalidades junto das métricas.
4. A data de referência é fixa. Reexecuções futuras devem manter essa versão ou informar `mes=7&ano=2026` nas rotas do dashboard.
5. Integrações externas não possuem credenciais/dados reais. Medição de dependências requer mocks controlados ou ambiente de staging explicitamente autorizado.
6. O projeto já possui falhas globais de Ruff, mypy e dois testes de PDF; elas devem ser registradas, não misturadas com correções de performance.
7. O dashboard imprime custos em stdout durante o smoke. Não foi alterado porque pertence ao código funcional fora do escopo.

## Backlog atualizado

### Concluído

- diagnóstico estático da Pessoa 1;
- mapeamento de filtros de data;
- mapeamento do helper de tabelas;
- levantamento inicial de overfetch;
- identificação do bloqueio e da divergência de linhagem;
- preservação comprovada de `meu_crm`;
- seleção do SHA-base e branch;
- estabilização do drift de `BudgetPdfRenderJob`;
- configuração protegida do benchmark;
- criação e migração limpa do banco descartável;
- seed sintético determinístico standard;
- validação de entidades e smoke das rotas críticas.

### Bloqueio atual

- baseline quantitativo ainda não coletado;
- estratégia específica para dependências externas/workers ainda pertence à coleta coordenada com Pessoas 2 e 3.

### Próximo passo

**Fase 1.2 — Coleta do Baseline de Performance da Pessoa 1**:

- executar warm-up;
- medir repetições controladas;
- calcular mediana/p50 e p95;
- capturar quantidade e tempo SQL;
- normalizar e contar queries duplicadas;
- confirmar N+1;
- obter `EXPLAIN (ANALYZE, BUFFERS)` das queries mais caras;
- produzir ranking das rotas.

Nenhum gargalo deve ser corrigido durante essa coleta.

### Futuro técnico

- converter filtros de data para ranges;
- revisar helper de tabelas e paginação;
- reduzir overfetch e cálculos em Python;
- revisar prefetches;
- medir integrações e ocupação de workers;
- somente depois iniciar correções priorizadas pelos dados.
