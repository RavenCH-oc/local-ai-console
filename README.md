# Local AI Console

Local AI Console is a local-first control surface for AI runtime and workflow management. The project is in early development.

The planned architecture pairs a Windows 11 controller with a Linux/Ubuntu LLM node. A llama.cpp-based local model runtime is planned as a core backend, while a Prompt Workbench for local AI workflows is a primary product direction.

## Development status

This repository currently contains a public-safe project baseline, runtime-data boundary contract, shared architecture contracts, a minimal Windows Controller API foundation, and a minimal Linux Node Agent foundation. The current APIs expose only health, version, and safe local metadata; no model runtime, database, controller-to-node integration, or workflow feature is available yet.

## Public repository boundary

This repository contains code and sanitized templates only. Do not commit runtime data, credentials, chat history, private prompts, host information, actual model paths, generated artifacts, or model files. Use local ignored files for private configuration when later development phases introduce runtime paths.

See [Runtime data boundary](docs/runtime-data-boundary.md) for the Controller Runtime and Node Runtime contract, and [Shared architecture contracts](docs/architecture-contracts.md) for the language-neutral contract layer.

For local Control API setup and development commands, see [`apps/control-api/README.md`](apps/control-api/README.md). For Linux Node Agent setup and its read-only host metadata boundary, see [`apps/node-agent/README.md`](apps/node-agent/README.md).

## License

Licensed under the [MIT License](LICENSE).
