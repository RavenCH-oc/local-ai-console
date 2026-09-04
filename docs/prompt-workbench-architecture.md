# Prompt Workbench architecture

Phase 1C-0 establishes the first source-managed Prompt Workbench Skill and workflow foundation. Phase 1C-1 adds a local Controller discussion-only request path through the existing Main LLM bridge. It performs no ComfyUI call, retrieval, QA verdict, tool execution, automatic Project State change, or LLM-created Prompt Revision.

## Domain boundary

`PromptProject` is the durable user work item. It selects a workflow profile and mode, owns a discussion session, retains structured project state, and can point to one accepted `PromptRevision`. A `PromptRevision` is a proposed or accepted prompt artifact; a `PromptSession` contains discussion history rather than replacing revisions.

A Skill is a public procedural package. The built-in `comfyui_prompt_generator` Skill describes how a future assistant should inspect state, preserve accepted material, use selected workflow knowledge, and decide whether to discuss, clarify, or propose a revision. It is not an executable agent and cannot call a model or a tool.

A workflow is a public composition of one Skill, model-family intent, supported modes, mode instructions, and declared knowledge sources. The initial `anima_base_v1` workflow has four persisted modes: `stable`, `balanced`, `detailed`, and `preserve`. The web UI receives this workflow registry from the Controller; it does not hard-code the workflow list.

Knowledge is data, separate from both Skill procedure and executable Tools. Built-in workflow documentation is public, short, generic, and source-managed under `packages/prompt-engine/`. It contains no private prompt history, empirical user results, real model path, or third-party prompt corpus.

## Context assembly and preview

`PromptContextAssembler` produces ordered `LLMMessage` values and accompanying contribution metadata for inspection. It uses this logical order:

1. Stable base, Skill, workflow, and selected-mode instructions.
2. Declared workflow knowledge, ordered deterministically.
3. The structured project-state snapshot and accepted-revision snapshot when present.
4. Stored session messages in their existing order.
5. The current user request as the final dynamic message.

Each contribution records a label, kind, safe source identity, stability category, character count, and optional token count. Token counts are intentionally unknown unless a future runtime supplies a trustworthy value. The Context Preview endpoint exposes metadata only and does not call an LLM or return prompt contents.

Prompt-prefix caching is a secondary optimization. Stable ordering helps future caching, but no cache key, cache measurement, or runtime prefill behavior is introduced here.

## Discussion-only LLM flow

`POST /api/prompt-sessions/{session_id}/discussion/stream` accepts only current user text and a reasoning preference (`auto`, `off`, or `on`). The Controller authoritatively resolves the active Project/session, Skill, workflow, mode, knowledge, state, accepted revision, and Main runtime. The browser cannot supply instructions, knowledge contents, model endpoint, or runtime target.

The server saves the raw user message first, assembles context through `PromptContextAssembler`, uses the provider-native full-chat token count, and rejects a request when input plus the server-owned output reserve and a 1,024-token safety headroom exceeds the configured 98,304-token context bound. It sends `prompt_generation` with target preference `auto`, which currently resolves to Main. Generation settings are held in a small server-owned discussion profile rather than in React.

The Controller translates provider events to `started`, `reasoning_delta`, `text_delta`, `completed`, `cancelled`, and `error` event names. It never forwards llama.cpp SSE frames, a provider URL, completion identifier, raw payload, credential, or model path. Reasoning and visible text remain separate. The UI renders reasoning in a collapsible element and displays the visible answer independently.

Only after a successful completion with visible text does the Controller write one assistant `PromptMessage`. It writes no database row per token. The visible answer is `PromptMessage.content`; bounded reasoning, safe usage/timing fields, finish reason, selected mode, and profile metadata may be retained under the message's private metadata. Cancellation, malformed streams, provider failures, and persistence failures do not create a normal assistant message. The already-saved user message remains raw history.

At most one generation may be active per Prompt Session, and the current single Main runtime accepts only one Prompt Workbench generation at a time. A concurrent request receives a clear busy error; no queue is implemented. Browser Stop aborts the stream; it is not the future reasoning-only control operation. No automatic retry is implemented.

## Response and persistence boundary

The `prompt_workbench_response` schema represents a generic future assistant result. A response can be `discussion`, `clarification`, or `revision`; only `revision` may carry a required proposed artifact. It can carry an optional project-state patch and warnings, but it never automatically changes private SQLite data.

The user must explicitly accept a proposed revision through the existing lifecycle. A future interpreter may display, validate, or save a structured response only after it has a separately authorized behavior design.

## Public and private knowledge

The controller loads built-in knowledge only from the declared public package paths. It may additionally read an optional extension directory under the existing private runtime knowledge root, inside the workflow's declared private namespace. Private extension files are ordered deterministically and are represented to the context only by generic safe identities such as `private_extension_001`; filesystem paths are not exposed.

Private extensions are local runtime data. They must not be committed, copied into public workflow documents, returned as preview text, or treated as public configuration. A missing private extension directory is valid and simply contributes no extensions.

## Deferred work

Future Phase 1C-2 work may add structured revision proposals and a separately designed interpretation/persistence path. Evaluated generation, QA behavior, ComfyUI execution, retrieval, and richer workflow assets remain deferred. They are deliberately not part of Phase 1C-1.
