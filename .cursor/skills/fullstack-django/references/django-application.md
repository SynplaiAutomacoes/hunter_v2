# Django Application

Use this reference for Django feature work outside of narrow CBV-specific questions.

## Core Areas

- models and schema design
- ORM queries and optimization
- forms and validation
- authentication and permissions
- URL routing
- admin customization
- app boundaries and domain organization

## Included Assets

- schema validation helper: `.opencode/skills/fullstack-django/scripts/validate-schema.sh`
- SQL migration stub: `.opencode/skills/fullstack-django/templates/migration-template.sql`

## Default Implementation Order

1. model or domain change
2. form or serializer boundary
3. view logic
4. URL wiring
5. template or response shape
6. admin and tests if relevant

## Preferred Django Patterns

- keep domain code under `apps/<domain>/`
- use forms for input validation in server-rendered flows
- keep authorization explicit in views, mixins, or services
- use `transaction.atomic()` for multi-step writes
- add indexes for frequently filtered or joined fields
- use `select_related()` and `prefetch_related()` where query count matters

## ORM Guidance

- use ORM expressions and queryset methods before raw SQL
- keep query shaping in managers, queryset methods, or service functions when reused
- evaluate expensive query paths with real template and relation access patterns

## Auth And Permissions

- use built-in auth primitives first
- prefer permission mixins or explicit checks over implicit template-only restrictions
- separate authentication from domain-specific authorization rules

## Admin

- use admin for internal operations, not as a substitute for product UX
- optimize admin lists with `list_select_related`, filters, search, and readonly fields when needed

## Keep Views Thin

Views should orchestrate request/response work, not own all business rules.
If a rule is reused or non-trivial, move it into a model method, form, service, or domain module.
