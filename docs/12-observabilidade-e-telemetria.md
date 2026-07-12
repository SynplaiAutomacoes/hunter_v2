# Observabilidade e telemetria

[Voltar ao README principal](../README.md) | [Indice da documentacao](README.md) | [Anterior: Glossario](11-glossario.md)

## Objetivo

Esta arquitetura define como o projeto deve emitir `logs`, `traces` e `metrics` para o stack ja conectado ao Grafana via OpenTelemetry.

O foco e responder rapidamente perguntas como:

- qual rota esta lenta agora
- a lentidao vem de SQL, provider externo, fila ou renderizacao interna
- qual integracao piorou nas ultimas horas
- quais operacoes de negocio estao mais caras em p95 e p99

## Estado atual do projeto

Hoje o repositorio ja possui uma base operacional:

- exportacao OTLP de logs, traces e metrics em `apps/core/otel_logging.py` (quando `OTLP_AUTH_HEADER` e `OTEL_EXPORTER_OTLP_ENDPOINT` estao configurados)
- auto-instrumentacao de Django, `requests` e `psycopg`
- logging JSON estruturado em `config/settings.py`
- contexto de request com `request_id`, `workshop_id`, `user_id` e `account_id` em `apps/core/logging_filters.py`
- middleware de performance estruturado em `apps/core/presentation/middlewares.py` (logger `performance.request`)
- helper padrao `observe_dependency_call` / `observe_business_operation` em `apps/core/observability.py`
- dashboard Grafana versionado em `grafana/dashboards/hunter-observability.json`

Contrato do log final de request (quando `PERF_LOGGING_ENABLED=1`):

- `route`, `method`, `path`, `status_code`, `duration_ms`
- `workshop_id` (quando disponivel ao final da request)
- `query_count` e `sql_time_ms` (quando `PERF_LOG_QUERIES=1`, via `SqlTimingWrapper`)
- `dependency_time_ms` e `dependency_call_count`
- `request_id` / correlacao OTEL (`trace_id`, `span_id`)

Lacunas remanescentes:

- instrumentacao de RabbitMQ e alguns providers ainda parcial
- `PERF_LOG_QUERIES` continua opt-in por custo e deve ficar off no steady-state
- baseline de p50/p95/p99 depende de trafego real apos ativar perf logging + OTLP

## Como ler o baseline (p50 / p95 / p99)

1. Confirme `ENVIRONMENT=production`, `PERF_LOGGING_ENABLED=1`, `PERF_LOG_QUERIES=0` e OTLP configurado.
2. Abra o dashboard `hunter-observability` e selecione `$environment`.
3. Na linha **Resumo / HTTP Requests**, leia:
   - p50 / p95 / p99 global a partir de `http.server.request.duration`
   - p95 por `http.route`
   - error rate 5xx por rota
4. Para SQL, ligue `PERF_LOG_QUERIES=1` apenas em janela curta e use os paineis Loki de `query_count` / `sql_time_ms`.
5. Para dependencias externas, use os paineis de `dependency.client.duration`.
6. Registre o baseline apos 24–72h de traffego representativo antes de mudar `GUNICORN_WORKERS` / `GUNICORN_THREADS`.

## Capacidade Gunicorn (recomendacao inicial)

Defaults em `gunicorn.conf.py`: `2` workers x `4` threads (~8 requests concorrentes).

Heuristica apos o baseline:

| Sintoma | Acao sugerida |
| --- | --- |
| p95 alto + CPU baixa | aumentar threads (mais concorrencia I/O) |
| CPU ~100% / risco de OOM (PDF) | reduzir threads ou aumentar RAM/CPU |
| 1 vCPU / 512MB–1GB | manter 2 workers, 4–8 threads |
| 2 vCPU / 2GB | avaliar 3–4 workers com 4–8 threads |

Correlacione Railway CPU/RAM com a metrica `http.server.active_requests`.
## Stack recomendada

### Aplicacao Python

- `opentelemetry-sdk`
- `opentelemetry-exporter-otlp-proto-http`
- `opentelemetry-instrumentation-django`
- `opentelemetry-instrumentation-logging`
- `opentelemetry-instrumentation-requests`
- `opentelemetry-instrumentation-psycopg` para spans de banco
- `opentelemetry-instrumentation-system-metrics` para CPU, memoria e GC, se o ambiente suportar o custo

### Pipeline de observabilidade

- aplicacao Django emitindo OTLP HTTP
- OpenTelemetry Collector como ponto central de recebimento, enrichment e roteamento
- Grafana consumindo:
  - Loki para logs
  - Tempo para traces
  - Prometheus/Mimir para metrics

## Principios de desenho

- logs, traces e metrics devem compartilhar os mesmos `resource attributes`
- metricas precisam usar baixa cardinalidade
- dados sensiveis ficam em logs e spans, nunca em labels de metricas
- traces lentos e com erro nao devem ser descartados por sampling
- rotas devem ser agregadas por template ou nome da view, nunca por path cru com ids
- integracoes externas devem seguir um contrato unico de instrumentacao

## Topologia da telemetria

### 1. Resource attributes

Todo sinal deve carregar os mesmos atributos basicos:

- `service.name`: nome fixo da aplicacao, por exemplo `hunter-web`
- `service.namespace`: por exemplo `synplai`
- `service.version`: versao da release ou commit SHA
- `deployment.environment`: `development`, `staging`, `production`
- `host.name` e `process.pid` quando o runtime preencher automaticamente

Observacao importante: o projeto nao deve usar `ENVIRONMENT` como `service.name`. O nome do servico e o ambiente precisam ser separados.

### 2. Correlacao entre sinais

Cada request e operacao deve ser correlacionavel por:

- `trace_id`
- `span_id`
- `request_id`

Nos logs, manter tambem:

- `user_id`
- `workshop_id`
- `account_id`, se disponivel sem custo alto

## Arquitetura por camada

### Camada A - Request lifecycle

Responsabilidade:

- criar ou reaproveitar `request_id`
- abrir span principal do request
- registrar metricas HTTP
- anexar atributos estaveis de request e tenancy
- publicar log final estruturado do request

Metricas recomendadas:

- `http.server.request.duration` como histogram
- `http.server.request.count` como counter
- `http.server.request.errors` como counter
- `http.server.active_requests` como up/down counter opcional

Atributos recomendados:

- `http.method`
- `http.route`
- `http.status_code`
- `http.target_group` opcional para agrupar areas como `budget`, `finance`, `workorder`
- `error`

Dados que nao devem virar label de metricas:

- `request_id`
- `user_id`
- `workshop_id`
- `path` bruto contendo ids

### Camada B - Banco de dados

Responsabilidade:

- medir tempo total de SQL por request
- contar queries por request
- criar spans por operacao SQL quando necessario
- destacar queries lentas com amostragem e sanitizacao

Estrutura recomendada:

- usar instrumentacao do `psycopg` para spans SQL
- adicionar um agregador leve por request para:
  - `db.client.operation.duration`
  - `db.client.operation.count`
  - `db.client.slow_query.count`

Objetivo operacional:

- identificar endpoints com N+1
- separar latencia de banco do resto da request
- encontrar picos de query count por rota

### Camada C - Dependencias externas

Todas as integracoes devem passar por instrumentacao uniforme.

Alvos prioritarios do projeto:

- Webmania
- SuperSign
- ViaCEP
- WDAPI veicular
- FIPE
- S3 compativel via boto3
- RabbitMQ

Contrato minimo por chamada:

- um span por operacao
- um histogram de duracao
- um counter de sucesso ou falha
- atributos de provider e operacao

Metricas recomendadas:

- `dependency.client.duration`
- `dependency.client.request.count`
- `dependency.client.error.count`

Atributos recomendados:

- `dependency.type`: `http`, `storage`, `queue`
- `dependency.name`: `webmania`, `supersign`, `fipe`, `wdapi`, `s3`, `rabbitmq`
- `operation`: `emit_nfe`, `consulta_cep`, `upload_logo`, `publish_dispatch_item`
- `result`: `success`, `error`, `timeout`
- `http.status_code` quando aplicavel

### Camada D - Operacoes de negocio

Essa camada mede o que importa para o time de produto e operacao.

Operacoes prioritarias do dominio:

- emissao de NFe e NFSe
- renderizacao de PDF
- dashboard financeiro
- sincronizacao e conciliacao fiscal
- upload e leitura de arquivos da oficina
- despacho de mensagens em lote
- consultas de placa e FIPE

Cada operacao deve emitir:

- span manual de alto nivel
- log estruturado de inicio e fim quando agregar valor
- histogram de duracao
- counter de falha

Metricas recomendadas:

- `business.operation.duration`
- `business.operation.count`
- `business.operation.error.count`

Atributos recomendados:

- `operation.name`
- `operation.group`
- `result`

### Camada E - Jobs e comandos

Management commands e rotinas de longa duracao precisam ser instrumentados como first-class citizens.

Exemplos do repositorio:

- `dispatch_message_groups`
- `reconcile_webmania_documents`
- `webhook`
- rotinas de reconciliacao e backfill

Cada execucao deve registrar:

- tempo total
- quantidade de itens processados
- quantidade de falhas
- tempo medio por item ou lote

Metricas recomendadas:

- `job.run.duration`
- `job.run.count`
- `job.item.processed.count`
- `job.item.error.count`

## Padrao de logs

Os logs devem continuar estruturados em JSON, mas com uma taxonomia unica.

Campos basicos obrigatorios:

- `timestamp`
- `level`
- `logger`
- `message`
- `environment`
- `trace_id`
- `span_id`
- `request_id`

Campos contextuais quando houver:

- `user_id`
- `workshop_id`
- `account_id`
- `duration_ms`
- `operation`
- `provider`
- `status_code`
- `query_count`
- `sql_time_ms`

Regras:

- logs de request final devem existir para toda request, nao so para as lentas
- requests lentas devem ganhar nivel `warning`
- erros devem carregar stack trace e contexto suficiente para triagem
- payloads sensiveis precisam ser mascarados

## Padrao de traces

Hierarquia desejada para requests web:

1. span do request HTTP
2. spans de operacoes de negocio internas
3. spans de SQL
4. spans de HTTP externo, storage e fila

Eventos uteis dentro de spans longos:

- `retry_started`
- `retry_finished`
- `fallback_started`
- `fallback_finished`
- `batch_started`
- `batch_finished`

Status do span:

- `OK` para sucesso
- `ERROR` para falha de negocio ou integracao

## Padrao de metrics

### Naming

- usar nomes estaveis em ingles
- um nome por conceito tecnico, nao por tela especifica
- privilegiar histograms para latencia
- counters para volume e erro

### Buckets de latencia sugeridos

Para HTTP e dependencias:

- `5ms`, `10ms`, `25ms`, `50ms`, `100ms`, `250ms`, `500ms`, `1s`, `2.5s`, `5s`, `10s`, `30s`

Para jobs e operacoes pesadas:

- `100ms`, `250ms`, `500ms`, `1s`, `2.5s`, `5s`, `10s`, `30s`, `60s`, `120s`, `300s`

### Cardinalidade

Pode usar como atributo de metricas:

- metodo HTTP
- rota normalizada
- status code
- provider
- operation group
- result

Nao pode usar como atributo de metricas:

- ids de usuario, oficina, conta, documento ou pedido
- placa, CPF, CNPJ, chassi, e-mail, telefone
- URLs externas completas com parametros
- erro bruto ou mensagem completa

## Collector

O OpenTelemetry Collector deve centralizar:

- recepcao OTLP HTTP da aplicacao
- enrichment com atributos de ambiente se necessario
- batch processor
- memory limiter
- tail sampling para traces, preservando erros e spans lentos
- exportacao para Loki, Tempo e Prometheus/Mimir

Politica inicial de sampling sugerida:

- 100% para erros
- 100% para requests acima de limiar de lentidao
- 10% a 20% para trafego saudavel de alto volume

## Dashboards iniciais

### 1. Overview

- RPS
- p50, p95 e p99 de requests
- taxa de erro
- top rotas lentas
- top dependencias lentas

### 2. HTTP server

- latencia por rota
- throughput por rota
- percentuais de 4xx e 5xx
- requests lentas com link para trace

### 3. Database

- tempo total de SQL por rota
- query count por rota
- top queries lentas amostradas
- comparacao entre latencia HTTP e latencia SQL

### 4. Dependencies

- Webmania, SuperSign, FIPE, WDAPI, ViaCEP, S3 e RabbitMQ
- p95 por provider e operacao
- falhas, timeouts e retries

### 5. Business operations

- emissao fiscal
- PDFs
- dashboards gerenciais
- uploads
- dispatch de mensagens

### 6. Jobs and commands

- duracao total
- quantidade processada
- falhas por execucao
- tendencia por tipo de job

## Alertas iniciais

- `http.server.request.duration` p95 acima do SLO por 5 minutos
- taxa de erro 5xx acima do limite por 5 minutos
- dependencia externa com erro alto ou timeout elevado
- aumento anormal de `db.client.operation.count` por rota
- job critico com falha ou duracao acima do baseline

## Plano de rollout

### Fase 1 - Fundacao

- corrigir `resource attributes`
- habilitar OTLP metrics
- adicionar correlacao `trace_id` e `span_id` nos logs
- padronizar log final de request

### Fase 2 - Request e banco

- emitir metrics HTTP em toda request
- substituir estrategia pesada de query logging por instrumentacao de banco mais barata
- adicionar agregacao de `query_count` e `sql_time_ms` por request

### Fase 3 - Dependencias externas

- criar helper comum para spans, logs e metrics de providers externos
- aplicar primeiro em Webmania, SuperSign, FIPE, WDAPI, ViaCEP, S3 e RabbitMQ

### Fase 4 - Operacoes de negocio

- instrumentar fluxos de alto impacto operacional
- criar dashboard e alertas orientados a dominio

### Fase 5 - Jobs e rotinas

- instrumentar management commands e processamentos em lote
- adicionar paineis de duracao, backlog e erro

## Mapeamento de hotspots atuais do projeto

Pontos que merecem prioridade de instrumentacao por ja apresentarem maior chance de latencia:

- `apps/core/presentation/middlewares.py` para request lifecycle
- `apps/core/infrastructure/services/webmania/` para emissao e consulta fiscal
- `apps/core/infrastructure/gateways/supersign.py` para assinatura
- `apps/core/infrastructure/services/storage.py` para bucket S3 compativel
- `apps/messaging/infrastructure/queue/rabbitmq_publisher.py` para fila
- `apps/core/presentation/views.py` no dashboard e ViaCEP
- `apps/catalog/fipe_service.py` para FIPE
- `apps/customer/util.py` para consulta veicular

## Dashboards disponiveis

O dashboard esta versionado em `grafana/dashboards/hunter-observability.json`. Ele e um dashboard unico com **variaveis globais** na parte superior que permitem alternar entre ambientes e servicos sem precisar de dashboards separados:

- `$environment` -- `producao`, `homologacao`, `desenvolvimento` (filtra todas as metricas e logs)
- `$service_name` -- nome do servico (`hunter-web`)
- `$rate_interval` -- janela de agregacao para rates (auto, 2m, 5m, 10m)

O dashboard e organizado em **linhas colapsaveis** por dominio:

- **Resumo** -- cards com RPS, p95 latencia, erro 5xx, requests ativas
- **HTTP Requests** -- RPS, p95 e error rate por rota; tabela de todas as rotas
- **Database SQL** -- SQL time e query count por rota (via Loki), deteccao de N+1
- **External Dependencies** -- p95, erros e throughput por Webmania, SuperSign, S3, FIPE, WDAPI, ViaCEP
- **Business Operations** -- duracao e falhas de DRE, dashboard, PDF
- **Logs & Traces** -- explorer de logs com filtros por rota, lentidao, erro e provider

Para usar: expanda a linha do dominio que voce quer investigar e mantenha as outras recolhidas. Troque `$environment` no dropdown para comparar prod vs homolog.

Os datasources usados sao:
- Prometheus (metrics)
- Loki (logs, com derived field `trace_id` linkando para Tempo)
- Tempo (traces)

Para importar: Grafana > Dashboards > Import > carregar o JSON e selecionar os datasources corretos.

## Definicao de pronto para observabilidade

Uma area do sistema so e considerada bem instrumentada quando possui:

- metricas de volume, latencia e erro
- spans navegaveis no trace
- logs estruturados com contexto minimo
- dashboard consumindo os sinais
- alerta para degradacao relevante

## Leitura complementar

- [Configuracao do ambiente](03-configuracao-do-ambiente.md)
- [Deploy, build e operacao](10-deploy-build-e-operacao.md)
- [Refactoring guide](REFACTORING_GUIDE.md)

[Anterior: Glossario](11-glossario.md) | [Indice da documentacao](README.md) | [Voltar ao README principal](../README.md)
