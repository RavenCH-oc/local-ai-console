# Local AI Console Control API

This is the Windows Controller API foundation for Local AI Console. It resolves and initializes the Controller Runtime layout, exposes safe local metadata, persists Prompt Workbench data in private runtime SQLite storage, and includes a private llama.cpp-compatible runtime bridge. It does not load a model at startup, contact a node, execute a shell command, or expose a generation endpoint.

## Development on Windows PowerShell

From this directory, create and activate a Python 3.12+ environment:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Set a private development runtime outside the repository, apply the explicit database migration, then start the API:

```powershell
$env:LOCAL_AI_CONSOLE_HOME = Join-Path $env:TEMP "local-ai-console-control-api"
local-ai-console-control-api-migrate
uvicorn local_ai_console_control.main:app --app-dir src --reload
```

The API starts by resolving the runtime root and creating only these empty directories: `config`, `data`, `prompts`, `knowledge`, `logs`, `cache`, and `backups`. The explicit migration command creates or upgrades only `data/console.sqlite3`. Application startup verifies the Alembic schema revision and fails clearly if the database is missing or stale; it never runs `create_all()`, silently rebuilds a database, or falls back to a repository-local runtime path.

Run tests with:

```powershell
python -m unittest discover -s tests -v
```

## Endpoints

- `GET /health`: inexpensive service liveness metadata.
- `GET /version`: application identity and version.
- `GET /runtime/info`: local runtime path metadata and initialization status. It does not return environment variables, credentials, configuration values, prompts, chats, or model data.
- `/api/health`, `/api/version`, and `/api/runtime/info`: compatibility routes for the Web development proxy; the original root routes remain available.
- `/api/prompt-projects`, `/api/prompt-sessions`, and `/api/prompt-revisions`: private local Prompt Workbench project, session, message, structured state, and revision resources.
- `GET /api/llm/status`: safe Main/Utility runtime state only; it does not initiate a network request or return targets, credentials, model paths, or raw provider errors.
- `POST /api/llm/probe`: explicitly probes only the runtime slots already configured in the private Controller Runtime. It accepts no caller-supplied host or URL.

Prompt Workbench resources are private runtime data. The API accepts manually entered notes and revisions but does not call an LLM, generate prompts, evaluate quality, or connect to ComfyUI.

For the public/private boundary and canonical layout, see [`docs/runtime-data-boundary.md`](../../docs/runtime-data-boundary.md).
For the Prompt Workbench persistence and lifecycle design, see [`docs/prompt-workbench-domain.md`](../../docs/prompt-workbench-domain.md).
For the private LLM configuration format, provider boundary, and runtime states, see [`docs/llm-runtime-bridge.md`](../../docs/llm-runtime-bridge.md).
