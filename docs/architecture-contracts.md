# Shared architecture contracts

## Purpose

Phase 0C freezes the first language-neutral contract layer for Local AI Console. These contracts describe configuration and domain data shared by future controller, web, node, workflow, context, and search components. They do not implement any application behavior. Phase 1B-3 adds capability, orchestration-boundary, Knowledge, Skill, Tool, and prompt-context contracts without replacing the Phase 0C source. Phase 1C-0 adds the additive Prompt Workbench response and source-declaration shapes used by the first source-managed built-in workflow.

The canonical serialized representation is JSON Schema Draft 2020-12 in `packages/contracts/schemas/local-ai-console-contracts.schema.json`. Sanitized examples live beside it in `packages/contracts/examples/`.

## Identity, versioning, and references

Named domain objects use stable machine IDs such as `example_main_model`, `personal`, and `example_image_prompt_workflow`. Display names are for presentation only. Persisted or configurable contracts include `schema_version`; existing `1.0.0` and `1.1.0` contracts remain valid, and the additive Phase 1C-0 contract types start at `1.2.0`.

Cross-contract links use explicit ID fields such as `preferred_model_profile_id`, `generation_preset_id`, `context_policy_id`, and `workflow_profile_id`. Contracts do not copy whole referenced objects, use a display name as an identity, or use a filesystem path as an identity.

`extensions` and `metadata` are bounded locations for backend- or provider-specific data. They do not replace the documented core fields.

## Distinctions that remain separate

| Distinction | Contract meaning |
| --- | --- |
| Model != Mode | A ModelProfile describes a model configuration; a ModeProfile describes a product experience that selects preferences. |
| Mode != Task | A mode is a first-class user-facing profile; a task is a unit of requested work. |
| Task != Runtime Slot | A task declares kind and preference; a runtime slot is an actual execution capacity. |
| Runtime Target `auto` != Runtime Slot | `auto` is routing preference only, never a slot. Slots are `main` and `utility`. |
| GenerationPreset != Model startup config | Presets contain per-request defaults; startup settings are load-time/runtime settings in ModelProfile. |
| Prompt Project != Chat | A project is a long-lived prompt-work item with structured state; a chat is not its replacement. |
| Prompt Revision != LLM message | Revisions are versioned prompt artifacts; discussion can occur without producing one. |
| SearchProvider != LLM runtime | Search is an independent provider abstraction, not an LLM runtime slot. |
| Model capability != Provider capability != Runtime compatibility | A model declaration, a backend transport surface, and a tested build/model/template result answer different questions. |
| Knowledge != Skill != Tool | Knowledge is data, a Skill is procedure, and a Tool is an executable capability subject to permission. |

## Runtime slots and tasks

`RuntimeSlot` is exactly `main` or `utility`. `RuntimeTargetPreference` is `auto`, `main`, or `utility`; `auto` does not represent an installed runtime.

The currently documented deployment assumption is an Ubuntu LLM node with 2 × RTX 2080 Ti, one available `main` slot, and an unavailable `utility` slot. In that deployment, the following initial task preferences resolve to `main`:

```text
chat                -> main
prompt_generation   -> main
context_compression -> main
```

This is a current deployment example, not a permanent contract constraint. A future independent Utility LLM can make the `utility` slot available without changing TaskContext, TaskRouting, ModeProfile, or ContextPolicy shapes.

TaskKind is intentionally limited to `chat`, `prompt_generation`, and `context_compression`. TaskContext and TaskRouting can express task kind, target preference, required capabilities, optional model-profile preference, and bounded metadata/extensions. No runtime router is implemented in this phase.

## Model and generation contracts

ModelProfile represents a model configuration, not a hard-coded model file. It has a backend identifier, an external model-location concept, startup settings, a default GenerationPreset reference, capability flags, and an optional request-adapter identifier. `llama_cpp` is the first known backend identifier, but the backend field is extensible.

Model locations can be an external path in private runtime configuration or an opaque external reference. They are never public repository identities, and public examples use only an opaque reference.

Startup settings include load-time concerns such as context size, GPU placement, KV cache, batch size, flash attention, and parallelism. GenerationPreset contains per-request defaults only: output limit, sampling values, seed, stop strings, and reasoning defaults. A preset must not contain model paths, GPU placement, context size, or KV settings.

The initial capability flags are `supports_thinking`, `supports_reasoning_budget`, `supports_system_prompt`, `supports_native_context_shift`, `supports_images`, and `supports_tools`. They are static model/configuration declarations, not evidence that a particular deployed runtime has passed an integration test. Backend-specific request behavior belongs behind `request_adapter` or `extensions`, not scattered through generic contracts.

`ProviderCapabilities` describes the generic API surface a provider can declare, including streaming, structured output, native chat token counting, reasoning transport and controls, timing, prompt-cache observability, vision, tool calling, and model lifecycle. Each declared capability has a `CapabilityStatus`, optional notes, and optional evidence metadata; providers omit capabilities they do not know how to describe.

`RuntimeCompatibilityRecord` is separate and applies a capability assessment to a specific provider build, model profile, and chat-template combination. Such records are future private runtime data. The public repository supplies only a sanitized shape/example and never a configured target, model path, credential, or deployment measurement. For the current conceptual example: a Qwen-class model can declare reasoning support, llama.cpp can expose reasoning transport, while an actual compatibility record may report reasoning transport as `supported` and a reasoning-budget effect as `partial`.

## Context policy

ContextMode is `native_shift`, `manual`, or `llm_compact`. `native_shift` delegates to a model backend's supported context-shift behavior; `manual` makes compaction a user-directed action. The initial `llm_compact` meaning is user notification plus confirmation, followed by compression using the same available `main` model. Its compression task target is `auto`, which currently resolves to `main` because Utility is unavailable.

ContextPolicy keeps editable thresholds, confirmation requirement, recent raw-context target, summary target, and compression target. The sanitized default example uses approximately 75%, 85%, and 92% for notice, urgent, and safety thresholds. They are values, not immutable constants.

Future occupancy calculation must consider active prompt tokens, reserved output tokens, and reserved reasoning tokens; it is not merely `prompt_tokens / context_size`. The Context Engine implementation is out of scope.

## Modes and Prompt Workbench

ModeProfile is extensible through `mode_kind`; current reserved IDs include `personal`, `discord_bot`, `waifu_bot`, and `prompt_workbench`. A ModeProfile selects model, generation, context, task preferences, UI/module identity, and required capabilities. It contains no Discord or Waifu business logic.

PromptWorkflowProfile defines generic Prompt Workbench behavior. It does not hard-code a particular workflow. It can select a preferred model, fallback target preference, supported workflow modes, system-component references, knowledge/example source references, optional output/parameter schema references, and extensions.

Prompt workflow modes are semantic values:

- `stable`: prioritize anatomy, pose stability, and fewer high-information elements.
- `balanced`: default trade-off between stability and useful detail.
- `detailed`: increase useful material, atmosphere, lighting, camera, or visual detail without merely making a prompt longer.
- `preserve`: modify requested dimensions while retaining unrelated accepted attributes.

## Prompt project, workflow knowledge, and response semantics

PromptProject is a durable long-running prompt-work item and references its workflow, active session, current accepted revision, and selected workflow mode. PromptSession represents the discussion session without defining a message database. PromptProjectState carries objective, constraints, preservation requirements, known problems, accepted observations, and a current revision reference so compression does not discard essential state.

PromptRevision is immutable versioned prompt content with a project reference, optional parent revision, positive/negative fields, parameters, change log, and timestamp. It supports future comparison, restore, branching, and acceptance without overwriting a prompt on every turn.

The Phase 1C-0 `knowledgeSourceDeclaration` makes source kind, public reference, stability, and optional budget explicit on a workflow. It supports public `built_in` material plus a non-serialized `private_runtime` extension boundary; it does not establish a knowledge database or retrieval system.

`prompt_workbench_response` is the generic structured response shape. It distinguishes `discussion`, `revision`, and `clarification`, carries assistant text and warnings, may propose a project-state patch, and requires a proposed prompt artifact only for `revision`. It is a transport/validation contract: accepting a proposed revision remains an explicit user action, and no response automatically writes database state. No real Prompt Generator behavior is implemented by this contract.

## Search contract

SearchMode is `off`, `manual`, or `auto`: `off` performs no search, `manual` requires explicit user invocation, and `auto` permits a future orchestrator to decide. SearchProvider is generic and leaves provider-specific behavior in extensions. SearchRequest carries a query and optional options. SearchResponse carries a provider ID, optional synthesized answer, stable-ID sources, citations pointing to source IDs, and provider metadata. This leaves room for a future grounded-search provider without making a provider-specific class the only abstraction.

No search UI, credential, API key, network request, or provider integration exists in Phase 0C.

SearchProvider remains the generic contract for an external retrieval provider that a future Tool or orchestration layer may use. It is not a Knowledge database, a ToolDefinition, or an LLM runtime. No provider-specific search fields were added in Phase 1B-3.

## Capability and orchestration supplements

Phase 1B-3 adds generic `PerformanceTiming`, bounded provider-cache timing, `PromptContextContribution`, `KnowledgeNamespace`, `KnowledgeReference`, `SkillProfile`, and `ToolDefinition` shapes. It also adds an optional `runtime_affinity_hint` to TaskContext for a future scheduler; current `parallel=1` behavior neither needs nor implements affinity scheduling.

The detailed responsibility boundaries, context-stability semantics, cache rule, permission model, future agent-loop boundary, and explicit non-goals are in [Orchestration boundaries](orchestration-boundaries.md). The empirical prefix-cache numbers remain outside contracts in [llama.cpp prefix cache baseline](llama-cpp-prefix-cache-baseline.md).

## Host contract and public/private boundary

HostProfile contains only stable identity, display name, platform (`windows` or `linux`), role, runtime-slot availability, and extensions. It deliberately excludes URL, IP address, MAC address, hostname, Wake-on-LAN data, model paths, and credentials.

The Repository remains public source only. Runtime/private data stays outside it according to [Runtime data boundary](runtime-data-boundary.md). Public examples must remain sanitized: no real host information, user paths, model files, API keys, bot credentials, system prompts, conversations, or private QA/knowledge. Public workflow reference data belongs under source paths such as `packages/prompt-engine/`, never the repository-root `knowledge/` runtime directory.

## Deferred work

Later phases will derive language-specific adapters/types and implement persistence, routing, Context Engine behavior, model runtime control, and integrations. The Phase 0D Control API implements the separate Controller Runtime path resolver; this phase deliberately implements none of those runtime behaviors. Phase 1B-3 likewise implements no Agent loop, Tool executor, Knowledge database, retrieval, context compaction, search integration, or Prompt Generator behavior. Phase 1C-0 adds a deterministic, inspectable context-assembly foundation only; it makes no LLM request and implements no generation, tool execution, RAG, search, or QA decision.
