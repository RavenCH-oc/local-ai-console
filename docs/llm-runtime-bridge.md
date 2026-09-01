# LLM Runtime Bridge

Phase 1B-1 establishes a private, controller-side bridge for a llama.cpp server that exposes an OpenAI-compatible HTTP API. It is an integration foundation, not a public generation API or a model-management system.

## Private configuration

The Controller reads only `<Controller Runtime>/config/llm-runtimes.json`. That directory is private runtime data and is not part of this repository. Start from the sanitized [`config/examples/llm-runtimes.example.json`](../config/examples/llm-runtimes.example.json) and create the real file locally.

The configuration supports `main` and optional `utility` slots. Each slot requires a supported provider (`llama_cpp`) and an absolute HTTP(S) `base_url`. It can also reference a credential by environment-variable name through `api_key_env`; it never accepts an inline key. The optional expected model alias is checked through the configured runtime's model metadata during an explicit probe. Connect and read timeouts are configured separately.

The loader rejects malformed JSON, unknown schema versions, unsupported providers, relative URLs, credentials embedded in URLs, inline credential fields, and unknown configuration fields. A missing configuration file is valid: Main is reported as `unconfigured` and Utility as `unavailable`. A malformed private configuration does not prevent the Controller from starting; its safe status is `error` with `configuration_error`.

## Runtime behavior

No request is sent at application startup or while `GET /api/llm/status` is handled. An explicit `POST /api/llm/probe` checks only configured slots, using the private target already loaded by the Controller. It accepts no URL, hostname, or provider data from the caller, so it cannot act as a general network-probing endpoint.

The adapter maps generic chat messages, generation settings, reasoning intent, structured JSON output, full-chat token counting, and streaming output to the provider. The initial token count path uses the provider's full-chat tokenization endpoint; it does not estimate tokens locally. Streaming emits normalized text, reasoning, usage, completion, and safe error events rather than exposing raw server-sent events. Cancellation is allowed to close the underlying HTTP stream, and generation requests have no automatic retry policy.

Reasoning fields are passed only as an adapter-level intent. Exact model/runtime support, generation endpoints, runtime lifecycle controls, and production task orchestration remain outside Phase 1B-1.

## Safe status surface

`GET /api/llm/status` and `POST /api/llm/probe` return only per-slot configuration/readiness state, provider name, whether an expected alias is configured, and a coarse error code. They do not return endpoint URLs, raw errors, credential references or values, model IDs or paths, prompt data, or host information.

The current lifecycle states are `unconfigured`, `unavailable`, `checking`, `loading`, `ready`, and `error`. `auto` task resolution currently prefers Main when both slots are available, while the resolver policy can prefer Utility for specific task kinds in a later phase.

For the Controller Runtime layout and its public/private boundary, see [Runtime data boundary](runtime-data-boundary.md).
