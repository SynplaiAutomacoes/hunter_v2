# Stack Selection

Use this reference when the task is mainly about choosing architecture or comparing stacks.

## Quick Decision Rules

- SEO-heavy product or marketing site -> Next.js with SSR or SSG
- Internal dashboard or SPA -> React or Vue with a simple API backend
- API-first backend with strong typing and performance focus -> FastAPI or Fastify
- Content-heavy business app with admin, auth, ORM, and server-rendered pages -> Django
- Enterprise workflow app with complex relational data -> Django or NestJS with PostgreSQL
- Real-time collaboration or streaming features -> add WebSockets and event boundaries early

## Default Recommendations

- Fastest path for a content and operations app: Django + PostgreSQL + Tailwind
- Fastest path for SEO + app shell: Next.js + PostgreSQL
- Fastest split frontend/backend stack: React + FastAPI + PostgreSQL
- If the team already knows Django and the problem is CRUD-heavy, prefer Django unless there is a strong reason not to

## Tradeoff Checklist

- rendering mode: SSR, SPA, static, or hybrid
- domain complexity: simple CRUD vs complex workflows
- team familiarity: existing speed beats theoretical ideal
- deployment target: Vercel, Railway, containers, or custom infra
- auth model: session-based vs token-based
- integrations: admin, webhooks, jobs, queues, or real-time events

## When Django Is The Best Fit

Prefer Django when the task benefits from:

- mature ORM and migrations
- admin interface
- built-in auth and permissions
- server-rendered forms and validation
- clear domain structure around apps

## Anti-Patterns

- Do not recommend a split frontend/backend architecture for simple CRUD unless there is a real product need.
- Do not choose MongoDB by default for relational business workflows.
- Do not optimize for scale assumptions that the current product does not have yet.
