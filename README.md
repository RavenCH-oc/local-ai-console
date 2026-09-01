# Local AI Console

Local AI Console is a local-first control surface for AI runtime and workflow management. The project is in early development.

The planned architecture pairs a Windows 11 controller with a Linux/Ubuntu LLM node. A llama.cpp-based local model runtime is planned as a core backend, while a Prompt Workbench for local AI workflows is a primary product direction.

## Development status

This repository currently contains a public-safe project baseline, runtime-data boundary contract, shared architecture contracts, a Windows Controller API with private Prompt Workbench SQLite persistence, a minimal Linux Node Agent foundation, and a desktop-first React web shell. Prompt Workbench currently supports manual project, discussion, state, and revision lifecycle management; no model runtime, controller-to-node integration, chat, prompt generation, or quality evaluation is available yet.

## Public repository boundary

This repository contains code and sanitized templates only. Do not commit runtime data, credentials, chat history, private prompts, host information, actual model paths, generated artifacts, or model files. Use local ignored files for private configuration when later development phases introduce runtime paths.

See [Runtime data boundary](docs/runtime-data-boundary.md) for the Controller Runtime and Node Runtime contract, and [Shared architecture contracts](docs/architecture-contracts.md) for the language-neutral contract layer.

For local Control API setup and development commands, see [`apps/control-api/README.md`](apps/control-api/README.md). For Linux Node Agent setup and its read-only host metadata boundary, see [`apps/node-agent/README.md`](apps/node-agent/README.md). For the React web shell and its local development proxy, see [`apps/web/README.md`](apps/web/README.md). For Prompt Workbench persistence and revision semantics, see [`docs/prompt-workbench-domain.md`](docs/prompt-workbench-domain.md).

## License

Licensed under the [MIT License](LICENSE).
