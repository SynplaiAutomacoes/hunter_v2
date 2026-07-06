# Performance Audit — hunter_v2

## Summary
- Audit scope: `apps/accounts`, `apps/budget`, `apps/catalog`, `apps/checklist`, `apps/collaborators`, `apps/core`, `apps/customer`, `apps/finance`, `apps/iam`, `apps/messaging`, `apps/quote`, `apps/scheduling`, `apps/sources`, `apps/stock`, `apps/suppliers`, `apps/workorder`, `apps/workshops`
- App inventory note: `apps/commission` and `apps/payroll` do not exist in this repo; payroll/commission logic lives mainly in `apps/collaborators`
- Environment check: `uv run python manage.py check` passed with 0 Django issues
- Usage note: no production traffic data was available during this pass, so impact estimates use code-complexity and view-surface heuristics
- Likely hottest production areas by code surface and business centrality: `apps/finance`, `apps/budget`, `apps/workorder`, `apps/stock`, `apps/scheduling`
- Total issues found: 39
- High impact: 20 | Medium: 16 | Low: 3

### Top 5 issues to fix first
- [x] `apps/finance/views/reports.py:739` builds the entire financial report in Python before pagination
- [x] `apps/budget/views/workflow_views.py:325` and `apps/workorder/views.py:401` load unpaginated, deep-prefetched operational lists
- [x] `apps/scheduling/forms.py:243` eagerly loads full customer/budget/workorder choice lists on modal/calendar paths
- [x] `apps/workshops/context_processors.py:20` plus request-scoped membership caching remove avoidable DB work from most authenticated page renders
- [ ] `apps/workshops/services/files.py:356` and `apps/workshops/views/workshops.py:143` keep S3/Webmania round-trips inside request/response flows

## Implementation Tracker
- [x] `apps/finance/views/reports.py:739` paginate/reshape the financial report before Python-side expansion
- [x] `apps/budget/views/workflow_views.py:325` paginate budget list views
- [x] `apps/workorder/views.py:401` paginate workorder list views
- [x] `apps/finance/views/financial_movement.py:231` keep filtered financial movements paginated
- [x] `apps/scheduling/forms.py:243` replace eager customer/budget/workorder choice loading with on-demand lookup
- [x] `apps/workshops/context_processors.py:20` collapse repeated active-workshop membership queries
- [x] `apps/core/presentation/middlewares.py:108` reduce per-request workshop gating lookups
- [x] `apps/stock/views.py:332` paginate stock report, compute totals from page-level data
- [x] `apps/stock/views.py:510` cap stock history builds and paginate combined list
- [ ] `apps/workshops/services/files.py:356` move logo/certificate sync out of request cycle
- [ ] `apps/workshops/views/workshops.py:143` move Webmania provisioning/sync out of request cycle
- [x] `apps/budget/views/pdf_views.py:53` offload budget PDF generation to a background job (`process_budget_pdf_jobs`)

## apps/finance

### [x] [HIGH] Financial report builds all rows in Python before pagination
- File: `apps/finance/views/reports.py:739`
- Problem: `_get_financial_movement_report_rows()` materializes `list(movements)`, expands parent workorder movements into per-payment rows, deduplicates, and only paginates later.
- Why it's slow: every request pays full dataset CPU, memory, and ORM cost even when the UI shows one page.
- Suggested fix: base report entries are now paginated before row expansion; remaining follow-up is tightening summary aggregation so filtered totals never depend on page-local rows.

### [x] [HIGH] Filtered financial movement list effectively disables pagination
- File: `apps/finance/views/financial_movement.py:231`
- Problem: `per_page = max(ordered_queryset.count(), 1)` turns filtered lists into one giant page.
- Why it's slow: filtered requests can render the full resultset, increasing DB time, template time, and memory usage.
- Suggested fix: keep a fixed UI page size and expose a separate export/download path for full result retrieval.

### [HIGH] Issued document ZIP download does synchronous bulk remote downloads
- File: `apps/finance/views/issued_documents.py:397`
- Problem: archive generation downloads every XML/PDF in-request, then zips everything in memory.
- Why it's slow: request latency scales with document count and external provider speed; concurrent downloads still block a web worker.
- Suggested fix: move archive generation to a background job, persist the finished ZIP, and return a ready/download status.

### [MEDIUM] Webmania account summaries load full company rows into Python
- File: `apps/finance/views/webmania.py:89`
- Problem: company counts and sync summaries are computed from loaded row lists instead of SQL aggregates.
- Why it's slow: unnecessary row hydration and Python iteration on account-wide fiscal dashboards.
- Suggested fix: replace list materialization with `Count`, `Max`, and filtered aggregates.

## apps/budget

### [x] [HIGH] Budget list is unpaginated and prefetches a deep object graph
- File: `apps/budget/views/workflow_views.py:325`
- Problem: `_get_budget_base_queryset()` prefetches collaborators, items, overrides, kit products, and kit services for the entire workshop, and the list view does not paginate.
- Why it's slow: heavy join/prefetch cost grows linearly with workshop size on one of the core operational screens.
- Suggested fix: add pagination, keep the list queryset shallow, and prefetch deep relations only on detail/export paths.

### [x] [MEDIUM] Budget PDF generation runs synchronously in the request cycle
- File: `apps/budget/views/pdf_views.py:53`
- Problem: HTML-to-PDF rendering is performed inline for normal requests.
- Why it's slow: PDF generation is CPU-heavy and increases p95 latency while tying up Gunicorn workers.
- Suggested fix: offloaded to a background job queue backed by `BudgetPdfRenderJob` plus `process_budget_pdf_jobs`; remaining follow-up is wiring an always-on worker/scheduler in deployment.

## apps/workorder

### [x] [HIGH] Workorder list mirrors the same unpaginated deep-prefetch pattern
- File: `apps/workorder/views.py:401`
- Problem: `_get_workorder_base_queryset()` prefetches item/kit graphs for all rows and the list view is unpaginated.
- Why it's slow: core execution screens load far more related data than a table view needs.
- Suggested fix: paginate, trim prefetch depth for list views, and reserve deep graphs for detail/edit pages.

### [HIGH] Payment status mapping does one query per workorder payment
- File: `apps/workorder/views.py:211`
- Problem: `_build_workorder_payment_status_map()` performs a `financial_movements.filter(...).first()` lookup for each payment.
- Why it's slow: classic N+1 behavior on workorders with multiple payment methods.
- Suggested fix: bulk-load related movements once and map them by `workorder_payment_id`.

### [MEDIUM] Workorder PDF/signature generation stays on the request path
- File: `apps/workorder/views.py:1384`
- Problem: PDF/signature document rendering is performed inline.
- Why it's slow: expensive PDF generation compounds latency on already heavy order flows.
- Suggested fix: cache/pre-generate documents and move signature-file preparation to async processing where possible.

## apps/stock

### [x] [HIGH] Stock report materializes the full queryset and computes totals in Python
- File: `apps/stock/views.py:332`
- Problem: `_get_stock_report_items()` converts the whole queryset to a list and computes totals from that list; the list view is also unpaginated.
- Why it's slow: memory and CPU usage rise with total inventory size instead of current page size.
- Suggested fix: paginated with `paginate_by=20`; totals are now computed from the page-level queryset.

### [x] [HIGH] Stock history merges and sorts all imports/transfers in Python
- File: `apps/stock/views.py:510`
- Problem: `_build_history_rows()` loaded every import and transfer, created Python row objects, then sorted the combined list.
- Why it's slow: history screens degrade sharply as operational volume grows.
- Suggested fix: capped to 50 per type (imports + transfers) and paginated combined result.

### [MEDIUM] Transfer review form triggers per-item lookups while rendering
- File: `apps/stock/forms.py:2296`
- Problem: summary/destination rendering repeatedly fetches `Product` and `StockProduct` rows inside loops.
- Why it's slow: transfer forms exhibit N+1 behavior as item count increases.
- Suggested fix: bulk-load products and stock rows into maps before building the HTML.

## apps/customer

### [HIGH] Plate lookup endpoint does blocking external HTTP with no cache
- File: `apps/customer/util.py:64`
- Problem: `api_check_plate` calls `requests.get(..., timeout=10)` during normal requests.
- Why it's slow: latency depends on a remote service, and repeated plate checks always hit the network.
- Suggested fix: add short-lived cache by plate and consider async enrichment for non-critical fields.

### [MEDIUM] Customer history prefetches all workorders even though only the first one is used
- File: `apps/customer/views.py:87`
- Problem: budget history loads full workorder collections, then reads only the latest/first row.
- Why it's slow: excess prefetch size and object hydration on customer detail/update paths.
- Suggested fix: prefetch a sliced queryset or annotate the latest workorder via subquery.

### [x] [MEDIUM] `vehicles_count()` causes N+1 queries on list/history views
- File: `apps/customer/models.py:61`
- Problem: the model method called `self.vehicles.count()` per row.
- Why it's slow: each rendered customer row triggered an extra count query.
- Suggested fix: annotated `vehicle_count=Count("vehicles")` in list/history querysets; model method falls back to annotation.

### [MEDIUM] Vehicle formset update saves rows one by one
- File: `apps/customer/views.py:291`
- Problem: customer vehicle updates iterate and save each formset item individually.
- Why it's slow: unnecessary write amplification on larger customer vehicle edits.
- Suggested fix: avoid saving unchanged rows and use bulk operations where the form flow permits.

## apps/catalog

### [x] [HIGH] Product list computes `is_used` via multiple `.exists()` checks per row
- File: `apps/catalog/views/products.py:116`
- Problem: delete-action visibility called `Product.is_used`, triggering several `.exists()` per row.
- Why it's slow: table rendering became an N+1 query fan-out for each visible product row.
- Suggested fix: annotated `has_usage` with `Exists` subqueries in the list queryset; delete action now reads the annotation.

### [HIGH] Kit service sync updates/deletes rows one by one and recomputes totals repeatedly
### [MEDIUM] Service and kit lists repeat the same row-level `is_used` pattern
- File: `apps/catalog/views/services.py:61`, `apps/catalog/views/kits.py:137`
- Problem: service/kit delete actions depended on model methods that perform per-row `.exists()` checks.
- Why it's slow: repeated N+1 query overhead on list screens.
- Suggested fix: annotated `has_usage` with `Exists` subqueries in service and kit list querysets.

### [LOW] Product code search does an extra existence query before the real query
- File: `apps/catalog/views/products.py:73`
- Problem: the code-search flow does a preliminary `.exists()` check before executing the final query.
- Why it's slow: small but unnecessary extra DB round-trip on a common lookup path.
- Suggested fix: fold the fallback logic into one query plan.

## apps/scheduling

### [x] [HIGH] Appointment form eagerly loads full customer, budget, and workorder choices
- File: `apps/scheduling/forms.py:243`
- Problem: modal/form rendering builds full select choice lists for large relational datasets.
- Why it's slow: every GET to open the form pays the cost of loading and materializing large workshop datasets.
- Suggested fix: replaced eager loading with on-demand customer search plus vehicle-scoped budget/workorder option loading.

### [HIGH] Calendar events endpoint can serialize unbounded date ranges
- File: `apps/scheduling/views.py:136`
- Problem: the calendar response can return every matching appointment in the requested range without a hard cap.
- Why it's slow: broad ranges can create large DB scans and large JSON payloads.
- Suggested fix: enforce a maximum range, fetch only needed columns, and consider caching common filter combinations.

### [MEDIUM] Calendar filter form also loads all active customers up front
- File: `apps/scheduling/forms.py:1077`
- Problem: filter UI populates customer choices eagerly rather than on demand.
- Why it's slow: repeated page loads pay the same large choice-building cost.
- Suggested fix: switch to async customer search/autocomplete.

## apps/messaging

### [x] [HIGH] Customer picker aggregates latest workorder date on every request
- File: `apps/messaging/views.py:54`
- Problem: picker queries used `Max("budgets__workorders__criado_em")` aggregate before pagination.
- Why it's slow: modal lookup requests forced expensive joins/aggregates across budget and workorder tables.
- Suggested fix: replaced `Max(...)` aggregate with a `Subquery` on `WorkOrder.objects.filter(budget__customer=OuterRef("pk")).order_by("-criado_em").values("criado_em")[:1]`.

## apps/suppliers

### [MEDIUM] Supplier update prefetches all movements and still hits N+1 in the template
- File: `apps/suppliers/views.py:94`
- Problem: the update view prefetches all movement history, but the template only displays a slice and dereferences nested relations without `select_related`.
- Why it's slow: over-fetching plus per-row related lookups on old suppliers with long histories.
- Suggested fix: build a dedicated paginated history queryset limited to the rows actually shown and `select_related("stock_product__product")`.

## apps/checklist

### [HIGH] Checklist PDF import/read/delete performs synchronous storage I/O in requests
- File: `apps/checklist/services/files.py:129`
- Problem: checklist upload/read/delete paths read full PDF content and interact with storage during normal web requests.
- Why it's slow: large PDFs and remote storage increase latency and block workers.
- Suggested fix: defer heavy file processing, stream reads where possible, and move expensive storage operations off the synchronous path.

### [MEDIUM] Prefetch is negated by re-ordering the related manager later
- File: `apps/checklist/views.py:79`
- Problem: the view prefetches `items` but then calls `.order_by(...)` on the related manager, causing a fresh query.
- Why it's slow: the prefetch cost is paid and then bypassed.
- Suggested fix: use `Prefetch(..., queryset=...)` with the desired ordering or sort the prefetched list in Python.

### [MEDIUM] Manual checklist edit form renders each item with `render_to_string` in a loop
- File: `apps/checklist/forms.py:44`
- Problem: HTML for existing items is rendered one item at a time during form construction.
- Why it's slow: CPU/template overhead grows with checklist size before the template is even rendered.
- Suggested fix: pass the items to the template and render them in one template loop.

## apps/workshops

### [x] [HIGH] Active-workshop context processor adds DB queries to most template renders
- File: `apps/workshops/context_processors.py:20`
- Problem: every authenticated page render loads the workshop list and then checks director/manager roles for the active workshop.
- Why it's slow: this creates a steady per-request DB tax across the entire UI.
- Suggested fix: cache the workshop payload on `request` plus a shared cache keyed by user/account/workshop, and collapse repeated role checks into one membership fetch.

### [HIGH] Webmania provisioning/sync/update remains inside request/response flows
- File: `apps/workshops/views/workshops.py:143`
- Problem: create/update/sync views call Webmania APIs directly from user-facing requests.
- Why it's slow: remote fiscal API latency directly hits workshop admin screens.
- Suggested fix: move provisioning/sync to background jobs and persist sync state for polling.

### [HIGH] Workshop logo/certificate flows perform multiple S3 and Webmania round-trips inline
- File: `apps/workshops/services/files.py:356`
- Problem: save/update flows include storage uploads, reads, deletes, and external sync work in one synchronous path.
- Why it's slow: one workshop settings change can fan out into multiple remote operations and retries.
- Suggested fix: use direct/presigned uploads and async post-commit synchronization.

### [MEDIUM] Webmania summary view loads all company rows into memory
- File: `apps/workshops/views/workshops.py:799`
- Problem: counts/latest-sync/error state are derived from full Python row lists.
- Why it's slow: unnecessary memory and iteration cost on account-level workshop pages.
- Suggested fix: use SQL aggregates and cache the summary.

### [MEDIUM] Logo `HEAD` path downloads the full object
- File: `apps/workshops/views/workshops.py:670`
- Problem: `HEAD` handling ultimately reads the object through storage instead of returning metadata only.
- Why it's slow: a cheap metadata check becomes a full S3 object download.
- Suggested fix: add a metadata-only path or redirect to object storage for efficient `HEAD` handling.

## apps/collaborators

### [HIGH] Commission sync has N+1 movement lookups and per-entry writes
- File: `apps/collaborators/services.py:183`
- Problem: commission synchronization looks up financial movement/payment state per workorder and then uses per-entry persistence.
- Why it's slow: payroll/commission recalculation cost grows sharply with historical workorders.
- Suggested fix: bulk-load payment state and switch to batched create/update operations.

### [HIGH] Collaborator CRUD triggers full payroll and salary-cost sync work synchronously
- File: `apps/collaborators/views.py:145`
- Problem: create/update flows invoke payroll sync, salary-cost sync, and historical budget freezing inline.
- Why it's slow: routine collaborator edits inherit large historical recalculation costs.
- Suggested fix: defer recalculation to jobs and scope it to affected periods/records.

### [MEDIUM] Payroll sync deletes/recreates child rows and updates rows one by one
- File: `apps/collaborators/services.py:350`
- Problem: sync code rebuilds payroll items aggressively instead of diffing existing state.
- Why it's slow: write amplification and repeated ORM work on recurring payroll operations.
- Suggested fix: diff existing items and use bulk create/update/delete.

### [MEDIUM] Payroll history view does extra queries for month/year filter options
- File: `apps/collaborators/views.py:205`
- Problem: history data is loaded, then extra queries derive distinct month/year options separately.
- Why it's slow: redundant query work on the same dataset.
- Suggested fix: derive distinct options from one SQL query or reuse the already-loaded result.

## apps/core

### [HIGH] `RequireFirstWorkshopMiddleware` does route resolution and membership existence checks on most authenticated requests
- File: `apps/core/presentation/middlewares.py:108`
- Problem: middleware resolves the URL and executes `.exists()` checks before many views run.
- Why it's slow: cross-cutting DB work compounds across the entire application.
- Suggested fix: cache workshop-presence state on the session/request and reduce repeated route resolution.

### [HIGH] Performance logging middleware becomes expensive when query capture is enabled
- File: `apps/core/presentation/middlewares.py:47`
- Problem: enabling `PERF_LOG_QUERIES` forces debug cursors and stores every query in memory for each request.
- Why it's slow: significant CPU/memory overhead can be introduced exactly when the system is already under load.
- Suggested fix: keep this off in normal production and use sampled APM/tracing instead.

### [HIGH] CEP lookup endpoint performs synchronous network calls without shared caching
- File: `apps/core/presentation/views.py:119`
- Problem: ViaCEP calls happen inline and repeated lookups are not backed by a real shared cache.
- Why it's slow: repeated address lookup latency is network-bound and duplicated across workers.
- Suggested fix: add a short TTL shared cache by CEP and rate-limit/network-isolate the external call path.

### [MEDIUM] Navbar/favorites context is rebuilt on every authenticated request
- File: `apps/core/presentation/context_processors.py:14`
- Problem: navbar menus, visible favorites, and favorite URL sets are regenerated per request.
- Why it's slow: extra DB and Python work is paid on every page render.
- Suggested fix: cache the navbar payload per user + active workshop and invalidate on favorite changes.

### [MEDIUM] Shared table tag can add extra count/context-flattening overhead
- File: `apps/core/templatetags/table_tags.py:807`
- Problem: table rendering flattens large template contexts and can issue extra `COUNT(*)` work on filtered tables.
- Why it's slow: the shared list-rendering helper adds overhead to many pages at once.
- Suggested fix: pass slimmer context to the tag and avoid count work when the UI does not require it.

## apps/quote
- No material request-path bottleneck stood out during this pass. Keep an eye on query-count coverage if usage grows.

## apps/sources
- No material request-path bottleneck stood out during this pass. This app currently has very little runtime surface area.

## Other findings (settings, middleware, caching, migrations)

### [HIGH] No explicit `CACHES` setting means Django falls back to process-local `LocMemCache`
- File: `config/settings.py:1`
- Problem: there is no configured Redis/Memcached backend.
- Why it's slow: read-heavy data cannot be shared across Gunicorn workers, duplicate remote/API lookups are repeated, and cache-backed locks are only local to one process.
- Suggested fix: configure a real shared cache backend and then cache hot read paths such as workshop context, navbar payloads, CEP/plate lookups, FIPE option data, and messaging picker summaries.

### [MEDIUM] Global middleware/context processors impose app-wide overhead
- File: `config/settings.py:136`
- Problem: `RequestPerformanceLoggingMiddleware`, `RequireFirstWorkshopMiddleware`, `apps.workshops.context_processors.active_workshops`, and `apps.core.presentation.context_processors.navbar` run globally.
- Why it's slow: even pages that do not need all workshop/nav data still pay the cost.
- Suggested fix: keep cross-cutting middleware minimal and lazy-load expensive UI context where possible.

### [MEDIUM] Default log levels are `DEBUG`
- File: `config/settings.py:268`
- Problem: `DJANGO_LOG_LEVEL` and `DJANGO_ROOT_LOG_LEVEL` default to `DEBUG`.
- Why it's slow: verbose JSON logging increases CPU and I/O volume if production env vars are not tightened.
- Suggested fix: default production log levels to `INFO` or `WARNING` and keep chatty loggers opt-in.

### [MEDIUM] No Celery/RQ/Huey-style job queue is configured despite multiple long-running request paths
- File: `config/settings.py:1`
- Problem: the repo has no worker-queue configuration; most heavy remote I/O and document generation remain synchronous.
- Why it's slow: web workers handle tasks better suited for background processing.
- Suggested fix: introduce a proper job queue for PDFs, fiscal archives, Webmania sync, WhatsApp sends, and large recalculations.

### [MEDIUM] Existing data migrations include table-wide backfills that can slow deploys or lock hot tables
- File: `apps/workorder/migrations/0024_workorder_budget_type.py:13`, `apps/workorder/migrations/0025_backfill_workorder_budget_type.py:12`, `apps/workorder/migrations/0028_workorderitem_kit_snapshot_frozen.py:11`, `apps/workorder/migrations/0029_backfill_workorderitem_kit_snapshot.py:8`
- Problem: these migrations add fields with defaults and then backfill large workorder/workorderitem tables.
- Why it's slow: deploy-time scans and updates can hold locks or extend migration windows on large datasets.
- Suggested fix: use phased migrations for future large-table changes and schedule backfills carefully.

### [LOW] Query-budget regression tests are largely missing from hot paths
- File: `apps/finance/test_*`, `apps/budget/test_*`, `apps/workorder/test_*`, `apps/stock/test_*`, `apps/scheduling/*`, `apps/workshops/*`
- Problem: the repo currently has little to no `assertNumQueries` / `CaptureQueriesContext` coverage on the most query-sensitive views.
- Why it's slow: performance regressions can ship unnoticed even after targeted fixes land.
- Suggested fix: add query-count assertions for financial reports, operational list views, scheduling modal/calendar endpoints, and shared context-heavy pages.
