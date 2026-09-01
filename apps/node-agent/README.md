# Local AI Console Node Agent

The Node Agent is the future Ubuntu/Linux-side service for Local AI Console. This foundation exposes only read-only host metadata and does not require a GPU, NVIDIA driver, CUDA, llama.cpp, or model files.

## Scope and security boundary

The production target is Ubuntu Linux. The initial endpoints are not production-secure because authentication has not been implemented. Authentication must be added before any destructive or process-control endpoint exists.

This agent does not provide arbitrary shell execution and will never expose generic `/shell` or `/exec` endpoints. Future model lifecycle work must use validated profiles, validated argument construction, and a controlled process manager.

No llama.cpp control, GPU metrics, model loading, systemd installation, shutdown/reboot, network inventory, or Controller-to-node integration exists in this phase.

## Development

From this directory, create and activate a Python 3.12+ environment:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

On Linux, start the development service with:

```bash
uvicorn local_ai_console_node.main:create_default_app --factory --host localhost --port 8000
```

Run tests with:

```bash
python -m unittest discover -s tests -v
```

## Endpoints

- `GET /health`: inexpensive liveness metadata.
- `GET /version`: application identity and version.
- `GET /host`: platform, hostname, uptime, and operating-system/kernel summary.

`/host` never returns environment variables, filesystem paths, credentials, IP/MAC/interface inventory, usernames, model paths, or process lists.

## Future runtime direction

Future production configuration and credentials are expected under `/etc/local-ai-console/`; mutable node state, where needed, is expected under `/var/lib/local-ai-console/`. This foundation does not create either directory.
