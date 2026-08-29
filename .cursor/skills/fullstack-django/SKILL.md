---
name: fullstack-django
description: Unified fullstack and Django skill for stack selection, scaffolding, code quality, Django application work, and class-based view design. Use for new project setup, Django feature work, CRUD/views, and targeted code audits while keeping context usage low.
---

# Fullstack Django

Use this skill as a lightweight dispatcher for web application work.
Load only the reference that matches the task instead of carrying a large tutorial in memory.

## Use This Skill When

- choosing a stack or architecture direction
- scaffolding a new app or project skeleton
- building or extending a Django application
- creating CRUD flows, forms, auth, admin, or URL routing
- designing or reviewing Django class-based views
- auditing code quality, security, or complexity

## Do Not Use This Skill When

- the task is a tiny isolated edit that does not need framework guidance
- the task is unrelated to web application architecture or Django/fullstack development

## Triage

Pick one primary path first. Read a second reference only if the task clearly crosses boundaries.

1. Stack or architecture choice -> `references/stack-selection.md`
2. Project bootstrap or boilerplate -> `references/scaffolding.md`
3. Django models, auth, admin, ORM, forms, URLs -> `references/django-application.md`
4. CBV-specific design, CRUD composition, mixins -> `references/django-cbv-patterns.md`
5. Security, complexity, dependency, or quality review -> `references/code-quality.md`

## Default Workflow

1. Classify the task into one path.
2. Read only the matching reference.
3. Inspect the repository and prefer existing conventions over generic examples.
4. Make the smallest change that solves the problem.
5. Run targeted validation for the affected area.
6. Escalate to a second reference only when needed.

## Guardrails

- Prefer repo conventions over tutorial-style code.
- Prefer built-in Django features before custom abstractions.
- Keep business logic close to models, forms, services, or domain modules rather than bloating views.
- Use `select_related()` and `prefetch_related()` on query-heavy paths.
- Avoid outdated patterns such as `request.is_ajax()`.
- Avoid broad `except Exception` unless there is a clear boundary and a safe fallback.
- Keep examples compact; do not generate large boilerplate unless the user asked for scaffolding.
- For audits, report the highest-risk findings first and separate critical issues from follow-up cleanup.

## Reference Index

- `references/stack-selection.md` - choose stacks and architectural shape
- `references/scaffolding.md` - bootstrap projects and locate scaffold scripts
- `references/django-application.md` - models, ORM, auth, forms, admin, routing
- `references/django-cbv-patterns.md` - CBV selection, mixins, CRUD, testing, pitfalls
- `references/code-quality.md` - security and quality review workflow

## External integration skills

- SynplaiSign (assinatura eletrônica, webhooks, envelopes): global skill `~/.cursor/skills/synplaisign/`

## Output Expectations

- Start with a short plan tied to the active path.
- Mention which reference was used when the task is non-trivial.
- Keep explanations focused on the current task, not the whole framework.
- Suggest the next validation step when implementation changes code.
