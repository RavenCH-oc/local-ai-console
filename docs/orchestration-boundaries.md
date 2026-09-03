# Orchestration boundaries

Phase 1B-3 records the contracts that future orchestration may use. It does not
implement an agent, retrieval, a tool executor, prompt assembly, or a scheduler.

## Capability evidence and compatibility

`CapabilityStatus` describes the strength of a capability claim:

| Status | Meaning |
| --- | --- |
| `supported` | Verified by a runtime/provider test or a reliable explicit confirmation. |
| `unsupported` | Tested as rejected or explicitly not supported by the provider. |
| `partial` | A surface exists, but only part of its behavior has been established. |
| `inferred` | Indirect evidence exists without a native acknowledgement. |
| `unverified` | Plausible or documented, but not tested for the relevant deployment. |
| `unavailable` | The deployment lacks a resource; it is not a claim that the provider cannot support it. |

Use `unavailable` in a runtime compatibility record for the affected deployment,
rather than as a general statement about a provider's theoretical capability.

Three layers remain separate:

- Model capability answers what a model family or configuration declares it can do,
  such as reasoning, vision, or tool calling.
- Provider capability answers what a backend API surface can transport or expose,
  such as streaming, structured output, native token counting, or a reasoning-end
  control route.
- Runtime compatibility answers what a specific provider build, model profile, and
  chat template actually did in a test.

For example, a Qwen-class model may support reasoning, and llama.cpp may transport
reasoning fields, while the tested runtime compatibility result can still be
`partial` for a reasoning budget if accepted values have no observed semantic
difference. Likewise, client-side stream cancellation can be supported while
server-side termination is only inferred from indirect evidence. These observations
must never become permanent assumptions for every llama.cpp deployment.

`RuntimeCompatibilityRecord` may include a provider build/version, model-profile
reference, test time, assessed capabilities, optional bounded performance timing,
and an optional benchmark reference. Real records are private runtime data. Public
examples only illustrate shape and semantics.

## Timing and prompt-cache semantics

`PerformanceTiming` uses generic optional fields for input/output token counts,
prompt and generation duration, first-event/first-content latency, total duration,
and prompt/generation throughput. `ProviderCacheTiming` is deliberately bounded:
it can express cached versus uncached input tokens and a reuse ratio, without
copying a raw provider response or forcing every provider to expose cache details.

Prompt cache is an optimization. It is not persistence, memory, or the source of
truth for context. SQLite history, PromptProject, PromptProjectState, and future
ContextSummary records remain authoritative even if a runtime cache is empty or a
server restarts.

The Phase 1B-2C benchmark found high reuse for append-only suffix changes, little
or no reuse after an early-prefix mutation, and better reuse when dynamic content is
late. Those percentages belong only to the [benchmark baseline](llama-cpp-prefix-cache-baseline.md),
not to a generic contract or a correctness guarantee.

`PromptContextContribution` communicates a contribution's kind, content/source
reference, stability hint, relative priority, and optional token budget. It does
not prescribe a final message order. Priority is a selection/retention hint, not a
license to override role semantics, instruction hierarchy, security, or correctness.

| Stability | Meaning |
| --- | --- |
| `stable` | Long-lived instructions such as a base policy or workflow guidance. |
| `snapshot` | Low-frequency state such as an accepted project-state or summary snapshot. |
| `append_only` | Context that normally grows at the suffix, such as recent conversation turns. |
| `dynamic` | Per-turn material such as retrieval results, tool output, or transient research. |

A changed snapshot begins a new cache epoch. A necessary compact event therefore
creates `System + Summary B + append-only history` after `System + Summary A +
append-only history`; cache reuse must never prevent correctness-preserving compact
work.

For future PromptProjectState assembly, avoid reserializing a frequently changing
whole state at the prompt front on every turn. Prefer a stable or snapshot baseline
plus a dynamic patch when that preserves meaning. The Context Engine will decide
the actual assembly policy in Phase 1C.

## Knowledge, Skill, Tool, and Search

Knowledge is what the model needs to know. `KnowledgeNamespace` uses a hierarchical
stable string path such as `comfyui/anima` or `llama-cpp`; `KnowledgeReference`
identifies a source without embedding documents or chunks. Phase 1B-3 does not add
a document database, FTS5, embeddings, or retrieval.

Skill is how a task should be done. `SkillProfile` holds an instruction-source
reference, required capabilities, optional Knowledge namespaces, optional allowed
Tool IDs, and an optional default task kind. The instruction source can later point
to a public package file or a private runtime override; a Skill is not required to
be one large inline system prompt. The first formal ComfyUI Prompt Generator Skill
is deferred to Phase 1C.

Tool is an executable capability. `ToolDefinition` contains an input-schema
fragment, an executor reference, result limits, and a separate permission class and
approval policy. Permission classes are `read_only`, `local_write`, `remote_write`,
and `destructive`; approval policies are `auto`, `confirm`, and `disabled`.
`read_only` does not automatically mean safe in every product context. Knowledge
text that describes `shutdown_server()` is not executable authority and cannot
grant a ToolDefinition or bypass approval.

SearchProvider remains an external retrieval-provider contract. A future Tool or
orchestrator may use it for providers such as SearXNG, Civitai, Hugging Face, or
Brave, but it is not redesigned here and has no Gemini-specific fields.

## Future orchestration hooks

The eventual bounded flow is:

```text
User -> Skill selection -> Knowledge retrieval -> LLM -> optional ToolCall
     -> Tool executor -> LLM -> Final
```

The Console, not a model backend, owns maximum rounds, permission decisions,
timeouts, cancellation, logging, and loop protection. llama.cpp tool or MCP
features, if used later, are optional provider capabilities rather than the domain
core.

`TaskContext.runtime_affinity_hint` is an opaque, optional conversation-level hint.
It must not contain a provider slot ID or create a persistent slot mapping. With
`parallel=1` no scheduler is needed. A future scheduler may prefer the same active
conversation on a compatible runtime when `parallel > 1`, improving cache locality
without turning cache state into correctness or persistence state.

## Explicitly deferred

This phase implements no Agent loop, Tool executor, MCP integration, Knowledge DB,
FTS5, embeddings, search provider integration, prompt-generator behavior, context
assembly/compaction engine, Personal Chat/router, node lifecycle control, model
management, WOL, or ComfyUI execution.
