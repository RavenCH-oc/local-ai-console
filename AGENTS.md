Scope:
Only work inside this repository.

Allowed without approval:
- inspect repository files
- edit in-scope source/tests/docs
- run non-destructive build/test/lint/typecheck
- inspect git status/diff/log

Require user approval:
- commits
- writes outside repository
- external service/API calls
- destructive commands
- LLM PC operations
- expanding phase scope

Never:
- push
- force push
- access unrelated repositories
- read SSH/private credentials
- commit secrets or runtime data

Phase discipline:
Implement only the current sub-phase.
Do not silently continue to the next phase.