# Prompt Workbench architecture

Phase 1C-0 establishes the first source-managed Prompt Workbench Skill and workflow foundation. It remains a local Controller feature with no real LLM request, prompt generation, ComfyUI call, retrieval, QA verdict, tool execution, or automatic persistence write.

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

## Response and persistence boundary

The `prompt_workbench_response` schema represents a generic future assistant result. A response can be `discussion`, `clarification`, or `revision`; only `revision` may carry a required proposed artifact. It can carry an optional project-state patch and warnings, but it never automatically changes private SQLite data.

The user must explicitly accept a proposed revision through the existing lifecycle. A future interpreter may display, validate, or save a structured response only after it has a separately authorized behavior design.

## Public and private knowledge

The controller loads built-in knowledge only from the declared public package paths. It may additionally read an optional extension directory under the existing private runtime knowledge root, inside the workflow's declared private namespace. Private extension files are ordered deterministically and are represented to the context only by generic safe identities such as `private_extension_001`; filesystem paths are not exposed.

Private extensions are local runtime data. They must not be committed, copied into public workflow documents, returned as preview text, or treated as public configuration. A missing private extension directory is valid and simply contributes no extensions.

## Deferred work

Future Phase 1C work may add a real runtime-backed request path, structured-response interpretation, evaluated generation and QA behavior, and richer workflow assets. Those are deliberately not part of Phase 1C-0.
