# LLM Runtime Bridge

Phase 1B-1 established a private, controller-side bridge for a llama.cpp server that exposes an OpenAI-compatible HTTP API. Phase 1B-2A verifies that bridge against a privately configured runtime. It remains an integration foundation, not a public generation API or a model-management system.

## Private configuration

The Controller reads only `<Controller Runtime>/config/llm-runtimes.json`. That directory is private runtime data and is not part of this repository. Start from the sanitized [`config/examples/llm-runtimes.example.json`](../config/examples/llm-runtimes.example.json) and create the real file locally.

The configuration supports `main` and optional `utility` slots. Each slot requires a supported provider (`llama_cpp`) and an absolute HTTP(S) `base_url`. It can also reference a credential by environment-variable name through `api_key_env`; it never accepts an inline key. The optional expected model alias is checked through the configured runtime's model metadata during an explicit probe. Connect and read timeouts are configured separately.

The loader rejects malformed JSON, unknown schema versions, unsupported providers, relative URLs, credentials embedded in URLs, inline credential fields, and unknown configuration fields. A missing configuration file is valid: Main is reported as `unconfigured` and Utility as `unavailable`. A malformed private configuration does not prevent the Controller from starting; its safe status is `error` with `configuration_error`.

## Runtime behavior

No request is sent at application startup or while `GET /api/llm/status` is handled. An explicit `POST /api/llm/probe` checks only configured slots, using the private target already loaded by the Controller. It accepts no URL, hostname, or provider data from the caller, so it cannot act as a general network-probing endpoint.

The adapter maps generic chat messages, generation settings, reasoning intent, structured JSON output, full-chat token counting, and streaming output to the provider. For Qwen-oriented llama.cpp chat templates, explicit reasoning `off` and `on` map to `chat_template_kwargs.enable_thinking=false` and `true`. An optional reasoning budget maps to `thinking_budget_tokens`, but its semantic effect is a runtime compatibility result rather than a portable assumption. Input-token counting uses the provider's native `/v1/chat/completions/input_tokens` endpoint with the complete chat-shaped request; it does not estimate tokens locally or treat raw `/tokenize` as chat-equivalent.

Streaming emits typed `started`, `reasoning_delta`, `text_delta`, `usage`, `completed`, and safe `error` events rather than raw SSE lines. A completion ID is captured from the first provider event that supplies it. The final `completed` event carries the available finish reason, final usage, and the same bounded timing metadata used by non-stream responses. Reasoning text is never merged into visible assistant text. Cancellation preserves `asyncio.CancelledError` and closes the HTTP stream; it is distinct from the optional llama.cpp reasoning-only control request.

For a stream that opts in with `ReasoningOptions.enable_realtime_control`, `LLMService.end_reasoning(slot, completion_id)` maps to llama.cpp's reasoning-only control route. It does not cancel the generation. Whether the installed runtime supports that route, and whether a per-request reasoning budget is effective, must be established by the opt-in private test; neither capability is asserted for all llama.cpp deployments. Generation streams have no automatic retry policy.

Reasoning fields are passed only as an adapter-level intent. Public generation endpoints, runtime lifecycle controls, and production task orchestration remain outside this phase.

## Safe status surface

`GET /api/llm/status` and `POST /api/llm/probe` return only per-slot configuration/readiness state, provider name, whether an expected alias is configured, and a coarse error code. They do not return endpoint URLs, raw errors, credential references or values, model IDs or paths, prompt data, or host information.

The current lifecycle states are `unconfigured`, `unavailable`, `checking`, `loading`, `ready`, and `error`. `auto` task resolution currently prefers Main when both slots are available, while the resolver policy can prefer Utility for specific task kinds in a later phase.

## Manual live verification

[`scripts/verify-llama-cpp-runtime.py`](../scripts/verify-llama-cpp-runtime.py) is deliberately opt-in. It reads the already-private Controller Runtime configuration and its referenced environment variable; neither an endpoint nor a credential is present in the script. Without an explicit opt-in it exits successfully without making a network request.

From `apps/control-api`, after installing the local package and configuring a private runtime, run:

```powershell
$env:LOCAL_AI_CONSOLE_RUN_LIVE_LLM_TESTS = "1"
.\.venv\Scripts\python.exe ..\..\scripts\verify-llama-cpp-runtime.py
```

The script reports safe booleans, event counts, bounded timing-field names, and short local timing measurements only. It verifies status and expected-model matching, the native full-chat `input_tokens` endpoint, a UTF-8 non-stream request with reasoning disabled, schema-constrained JSON output, typed streaming with separated reasoning/content events, `on` and `auto` reasoning behavior, per-request budget compatibility, optional reasoning-only control, and local stream cancellation followed by a short slot-availability request. It does not print the configured endpoint, credential, completion ID, model response text, or raw provider response. Ordinary unit and CI tests continue to use `httpx.MockTransport` and never contact a private runtime.

For the Controller Runtime layout and its public/private boundary, see [Runtime data boundary](runtime-data-boundary.md).
