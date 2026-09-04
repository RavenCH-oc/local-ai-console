# Prompt Workbench discussion flow

Phase 1C-1 connects Prompt Workbench discussion to the existing private Main llama.cpp runtime through `PromptContextAssembler`, `LLMService`, `TaskRuntimeResolver`, and `LlamaCppClient`. It is not a new provider client and does not expose llama.cpp directly to the browser.

The Controller endpoint is `POST /api/prompt-sessions/{session_id}/discussion/stream`. It accepts only user text and the small `auto` / `off` / `on` thinking preference. Project, active session, workflow, mode, knowledge, state, accepted revision, and runtime selection are server-owned.

Before streaming, the Controller persists the raw user message, assembles authoritative context, obtains an exact native chat token count, and checks the reserved output plus a 1,024-token safety headroom against the 98,304-token runtime context. Context overflow does not reach the provider. A completed stream persists exactly one visible assistant message; no assistant row is written while deltas arrive or when a stream is stopped or fails.

The context preview retains discrete Base, Skill, Workflow, Mode, Knowledge, State, and Revision contributions. For the current llama.cpp/Qwen chat-template compatibility boundary, the stable leading system contributions are serialized as one labelled system message for the model; preview source metadata remains separate and inspectable.

Preparation errors are classified for the user without raw provider bodies, endpoints, configuration, or traceback: `MAIN runtime unavailable`, `Runtime authentication failed`, `Prompt context formatting failed`, `Input-token preflight failed`, `Prompt context is too large for the current runtime`, and `Generation could not start`. The opt-in verifier may additionally print a sanitized underlying error category and HTTP status; those fields never enter the browser response.

The browser receives Controller event types, never raw provider SSE. Reasoning deltas and visible answer deltas remain separate. A bounded reasoning record can be retained in private message metadata; visible assistant content remains the normal message body.

The optional [live verifier](../scripts/verify-prompt-workbench-discussion.py) is disabled unless `LOCAL_AI_CONSOLE_RUN_PROMPT_WORKBENCH_LIVE_TEST=1` is explicitly set. It uses a temporary sanitized runtime/database and prints only safe shapes, categories, HTTP status when applicable, booleans, and counters. It never prints a configured endpoint, key, model response, prompt content, or private knowledge.

This phase permits discussion and clarification only. It does not create Prompt Revisions, alter Project State from model output, run ComfyUI, execute tools, perform search, or start Phase 1C-2 structured revision generation.
