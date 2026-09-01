# Local AI Console

Local AI Console is a local-first control surface for AI runtime and workflow management. The project is in early development.

The planned architecture pairs a Windows 11 controller with a Linux/Ubuntu LLM node. A llama.cpp-based local model runtime is planned as a core backend, while a Prompt Workbench for local AI workflows is a primary product direction.

## Development status

This repository currently contains only the public-safe project baseline. No application, API, node agent, model runtime, or workflow feature is available yet.

## Public repository boundary

This repository contains code and sanitized templates only. Do not commit runtime data, credentials, chat history, private prompts, host information, actual model paths, generated artifacts, or model files. Use local ignored files for private configuration when later development phases introduce runtime paths.

## License

Licensed under the [MIT License](LICENSE).
