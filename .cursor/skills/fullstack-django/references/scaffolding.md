# Scaffolding

Use this reference when the user wants to generate a new project or bootstrap structure quickly.

## Available Scaffold Script

The existing project scaffold utility is located at:

- `.opencode/skills/fullstack-django/scripts/project_scaffolder.py`

Run it from repository root.

```bash
python .opencode/skills/fullstack-django/scripts/project_scaffolder.py --list-templates
python .opencode/skills/fullstack-django/scripts/project_scaffolder.py nextjs my-app
python .opencode/skills/fullstack-django/scripts/project_scaffolder.py fastapi-react my-api
python .opencode/skills/fullstack-django/scripts/project_scaffolder.py mern my-project
python .opencode/skills/fullstack-django/scripts/project_scaffolder.py django-react my-app
```

## Bootstrap Workflow

1. Confirm the stack choice.
2. Generate the scaffold.
3. Verify the expected entry files exist.
4. Install dependencies.
5. Copy environment templates.
6. Run the simplest possible smoke check.

## Verify By Stack

- Next.js / React: confirm `package.json`, then run install and dev server
- Python backend: confirm `pyproject.toml` or `requirements.txt`, then install and run app startup
- Django: confirm `manage.py`, settings module, and app registration

## Guardrails

- Prefer the smallest scaffold that matches the task.
- Do not generate optional infrastructure unless the user needs it.
- Keep generated structure aligned with the repo's existing conventions when scaffolding inside an existing codebase.
