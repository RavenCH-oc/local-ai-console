# llama.cpp Prefix Cache Baseline

Phase 1B-2C measured common-prefix reuse on the already configured private Main
runtime. The repository contains the harness and this public-safe result only; it
contains no endpoint, credential, host information, model path, private prompt, or
generated response text.

## Scope and method

This is an in-memory, single-runtime (`parallel=1`) observation. It does not use
or require persistent slots, session restoration, a prompt cache service, or any
other persistent KV mechanism. It is not a production deployment setting.

The observed runtime was llama.cpp build `10760`, serving the Qwen3.8 27B Q6 model
family with a `98,304` token context on two RTX 2080 Ti GPUs (22 GB each). These
details identify the test class, not a private runtime location or configuration.

The harness uses reasoning off and deterministic, public-only synthetic chat
messages at temperature zero. It first calls the runtime's native full-chat
`/v1/chat/completions/input_tokens` endpoint to calibrate the shared prefix. The
selected prefix was 160 repeated public sentences and measured 6,166 input tokens,
which is within the 4K--8K target. It then streams each request and records only
bounded timing metadata and event timing; it discards generated text.

The client does **not** send an explicit `cache_prompt` field. The provider payload
was inspected for this baseline and has no such field, so the results below describe
the server's default in-memory behavior. No provider payload or runtime configuration
was changed as a consequence of this result.

Run the same private, opt-in measurement from `apps/control-api` only after a local
runtime is configured:

```powershell
$env:LOCAL_AI_CONSOLE_RUN_LIVE_LLM_TESTS = "1"
$env:LOCAL_AI_CONSOLE_RUN_PREFIX_CACHE_BENCHMARK_ONLY = "1"
.\.venv\Scripts\python.exe ..\..\scripts\verify-llama-cpp-runtime.py
```

The opt-in script emits no endpoint, API key, configured model alias, completion ID,
or model text. Re-run it after changing the runtime build, model family or quant,
context size, or prompt template behavior.

## Results

All times are milliseconds. `reuse` is safely calculated as
`cache_n / (cache_n + prompt_n)`; it is `0` for a cold request and `null` only if
the runtime omits usable timing counters. `first reasoning` is `--` because all
measurements deliberately had reasoning disabled. `first content` is the first
visible text delta.

| Variant | Condition | Input | Cache | Prompt | Reuse | Prompt ms | Prompt tok/s | Pred. n | Pred. ms | Pred. tok/s | First SSE | First reasoning | First content | Complete | Finish |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | --- |
| alpha | cold | 6,167 | 0 | 6,167 | 0.000000 | 7,098.611 | 868.76 | 4 | 142.635 | 21.03 | 7,984 | -- | 7,984 | 8,125 | stop |
| alpha | append-only | 6,206 | 6,148 | 58 | 0.990654 | 552.367 | 105.00 | 4 | 141.219 | 21.24 | 578 | -- | 578 | 719 | stop |
| alpha | final-suffix change | 6,207 | 6,184 | 23 | 0.996295 | 384.062 | 59.89 | 8 | 322.358 | 21.71 | 422 | -- | 422 | 734 | length |
| alpha | early-prefix mutation | 6,206 | 0 | 6,206 | 0.000000 | 7,040.829 | 881.43 | 4 | 141.404 | 21.22 | 7,813 | -- | 7,813 | 7,953 | stop |
| bravo | cold | 6,167 | 0 | 6,167 | 0.000000 | 7,156.614 | 861.72 | 4 | 141.484 | 21.20 | 8,000 | -- | 8,000 | 8,140 | stop |
| bravo | append-only | 6,206 | 6,148 | 58 | 0.990654 | 553.216 | 104.84 | 4 | 141.186 | 21.25 | 578 | -- | 578 | 719 | stop |
| bravo | final-suffix change | 6,207 | 6,184 | 23 | 0.996295 | 385.364 | 59.68 | 8 | 323.193 | 21.66 | 422 | -- | 422 | 750 | length |
| bravo | early-prefix mutation | 6,206 | 0 | 6,206 | 0.000000 | 7,127.866 | 870.67 | 4 | 141.317 | 21.23 | 7,907 | -- | 7,907 | 8,047 | stop |

The duplicate variants use different deterministic prefixes. Their agreement shows
that the result is not tied to a single text sequence: append-only and final-suffix
changes reuse about 99% of the prompt, while the tested early mutation starts cold.

### Dynamic context placement

The long static prefix is unchanged in all four requests below. “Early” places the
changing text immediately after that prefix in the system message; “late” places it
in the final user turn. The initial late request benefits from the previous unchanged
static prefix, while its changed follow-up reuses almost the whole prompt.

| Placement | Condition | Input | Cache | Prompt | Reuse | Prompt ms | Prompt tok/s | Pred. n | Pred. ms | Pred. tok/s | First SSE | First reasoning | First content | Complete | Finish |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | --- |
| early | initial | 6,174 | 0 | 6,174 | 0.000000 | 7,229.014 | 854.06 | 4 | 141.541 | 21.20 | 8,079 | -- | 8,079 | 8,219 | stop |
| early | changed | 6,174 | 5,658 | 516 | 0.916424 | 1,301.653 | 396.42 | 4 | 141.636 | 21.18 | 1,329 | -- | 1,329 | 1,485 | stop |
| late | initial | 6,173 | 5,658 | 515 | 0.916572 | 1,304.302 | 394.85 | 7 | 278.269 | 21.56 | 1,328 | -- | 1,328 | 1,609 | stop |
| late | changed | 6,173 | 6,146 | 27 | 0.995626 | 387.660 | 69.65 | 7 | 278.070 | 21.58 | 422 | -- | 422 | 703 | stop |

## Correctness and capability record

The semantic smoke test first gave an early instruction requiring marker A, then
changed that early instruction to marker B. Both instructions were followed, and the
second response did not contain the former marker. This is a narrow stale-prefix
check, not proof of correctness for arbitrary prompts.

| Capability | Baseline result |
| --- | --- |
| Timing observability | `cache_n`, `prompt_n`, `prompt_ms`, `prompt_per_second`, `predicted_n`, `predicted_ms`, and `predicted_per_second` were returned on completed streams. |
| Default in-memory common-prefix reuse | Observed. |
| Explicit `cache_prompt` request option | Not sent by the client; no behavior change made. |
| Persistent slot/KV state | Not used or relied upon. |
| Early-prefix invalidation | A changed early prefix had zero reuse in the paired alpha/bravo test. |
| Stale instruction after mutation | Not observed in the bounded semantic smoke test. |

## Prompt-shaping recommendations (not implemented here)

Keep the longest, least-changing material first: a versioned base policy, static
project facts, and a stable prompt-template prefix. Append canonical history and the
current turn after it. Put volatile request data, temporary tool state, and current
user instructions as late as their semantics allow. This preserves reuse without
allowing cache performance to change prompt meaning.

For a future `PromptProjectState`, model immutable project identity and template
version separately from changing work state. Treat an updated summary as a new,
versioned **summary epoch**: retain a stable base prefix before it, keep the summary
immutable during that epoch, and create a new epoch only when the summary genuinely
changes. Recent turns should follow the active summary. This is a prompt assembly
recommendation only; it introduces no persistent runtime cache or slot dependency.

Application correctness must continue to work when no reusable cache is available.
No product behavior should depend on persistent slot state, cache survival across a
runtime restart, or a particular cache counter value.
