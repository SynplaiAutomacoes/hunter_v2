# Code Quality

Use this reference for audits, security review, complexity review, and implementation quality checks.

## Existing Analyzer

The existing analyzer script is located at:

- `.opencode/skills/fullstack-django/scripts/code_quality_analyzer.py`

Common usage from repository root:

```bash
python .opencode/skills/fullstack-django/scripts/code_quality_analyzer.py .
python .opencode/skills/fullstack-django/scripts/code_quality_analyzer.py . --verbose
python .opencode/skills/fullstack-django/scripts/code_quality_analyzer.py . --json --output report.json
```

## Review Order

1. critical security findings
2. auth and permission gaps
3. unsafe data handling or injection risks
4. high-complexity files and deep nesting
5. dependency health
6. missing tests around risky paths

## What To Look For

- hardcoded secrets or tokens
- broad exception handling that hides failures
- unbounded queries or N+1 issues
- missing validation at trust boundaries
- duplicated business rules across views and forms
- weak permission checks around writes, exports, or admin-only behavior

## Reporting Style

- separate must-fix now from follow-up cleanup
- explain why the issue matters, not just where it is
- prefer a short prioritized list over a long dump

## Validation After Fixes

- rerun the narrowest relevant tests first
- rerun lint or static checks if the change affects many files
- rerun the analyzer when the goal is a formal audit
