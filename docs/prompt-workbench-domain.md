# Prompt Workbench domain and persistence

Phase 1A introduces private, local persistence for Prompt Workbench data. It implements no model request, prompt generation, ComfyUI integration, QA judgment, or context compression. The Phase 1C-0 source-managed Skill, workflow, knowledge, structured-response, and context-preview foundation is documented separately in [Prompt Workbench architecture](prompt-workbench-architecture.md); it does not change the explicit persistence lifecycle described here.

## Private database lifecycle

The Controller database is always `console.sqlite3` under the existing Controller Runtime `data/` directory. Its location is derived from `RuntimePaths`; it is never calculated from the working directory or committed to this repository.

Schema changes use the bundled Alembic migrations in the Control API source tree. The application deliberately does not run migrations or call `create_all()` at startup. Instead:

1. Run `local-ai-console-control-api-migrate` after choosing a private Controller Runtime.
2. Start the Control API.
3. The API verifies that the database revision is at the bundled migration head. A missing or stale schema fails startup with a command-oriented error and is never recreated silently.

The migration command is the explicit operation permitted to create or upgrade the private SQLite file.

## Entities

- `PromptProject` is a durable work item with title, workflow profile, active session pointer, current accepted revision pointer, UTC timestamps, and archive state.
- `PromptSession` is a discussion context belonging to one project. Creating a project also creates an initial session.
- `PromptMessage` stores immutable raw discussion history. Future context compression must retain these rows.
- `PromptProjectState` stores typed objective, constraints, preservation requirements, known problems, and accepted observations separately from messages.
- `PromptRevision` stores immutable positive/negative prompt content, validated JSON parameters, a change log, lineage parent, UTC timestamp, and lifecycle status.

Opaque UUID-derived IDs use a semantic prefix while remaining compatible with the Phase 0C stable-ID character rules. Timestamps are canonical UTC values and API responses contain timezone-qualified ISO 8601 values.

## Revision lifecycle

New revisions are always `proposed`. An explicit accept action changes one proposed revision to `accepted` and updates `PromptProject.current_revision_id` in the same database commit. Older accepted rows stay preserved. An explicit discard action changes only a proposed revision to `discarded` and never changes the current accepted pointer.

An accepted or discarded revision cannot be accepted again. The current accepted revision cannot be discarded. Parent revisions must belong to the same project, preserving future branch and comparison capability.

Restore is intentionally not a Phase 1A UI action. A future restore must create a new revision with copied artifact content and an explicit proposed/accepted action; it must never mutate an old revision row in place.

## API boundary

The local Controller exposes the private Prompt Workbench resources under `/api/prompt-projects`, `/api/prompt-sessions`, and `/api/prompt-revisions`. The Web UI calls them through its existing Vite `/api/*` development proxy.

Prompt Projects, messages, state, and revisions are private runtime data. Tests use only temporary SQLite databases and sanitized fixtures. They are not public repository assets and must not be exported, committed, or included in frontend configuration.
