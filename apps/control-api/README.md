# Local AI Console Control API

This is the Windows Controller API foundation for Local AI Console. It currently resolves and initializes the Controller Runtime layout, then exposes only local metadata endpoints. It does not create a database, load a model, contact a node, or execute a shell command.

## Development on Windows PowerShell

From this directory, create and activate a Python 3.12+ environment:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Set a private development runtime outside the repository, then start the API:

```powershell
$env:LOCAL_AI_CONSOLE_HOME = Join-Path $env:TEMP "local-ai-console-control-api"
uvicorn local_ai_console_control.main:app --app-dir src --reload
```

The API starts by resolving the runtime root and creating only these empty directories: `config`, `data`, `prompts`, `knowledge`, `logs`, `cache`, and `backups`. Startup fails clearly if the runtime root is relative or resolves inside the source repository. It never falls back to a repository-local runtime path.

Run tests with:

```powershell
python -m unittest discover -s tests -v
```

## Endpoints

- `GET /health`: inexpensive service liveness metadata.
- `GET /version`: application identity and version.
- `GET /runtime/info`: local runtime path metadata and initialization status. It does not return environment variables, credentials, configuration values, prompts, chats, or model data.

For the public/private boundary and canonical layout, see [`docs/runtime-data-boundary.md`](../../docs/runtime-data-boundary.md).
