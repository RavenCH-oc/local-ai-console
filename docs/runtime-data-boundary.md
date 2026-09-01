# Runtime data boundary

## Purpose and terminology

Local AI Console separates its public source tree from each private runtime instance.

- **Repository**: the public source tree, containing code, documentation, and sanitized examples.
- **Controller Runtime**: Windows-side Local AI Console instance data.
- **Node Runtime**: Ubuntu LLM-node instance data.
- **Private Runtime Data**: user- or machine-specific durable data.
- **Cache**: safe-to-recreate, non-authoritative data.

The Repository is never the default location for Private Runtime Data. `.gitignore` and repository hygiene checks are defense in depth; the architecture must keep runtime roots outside the Repository even if files are manually added to Git.

## Runtime-root invariant

The Controller Runtime root must not resolve inside the source Repository. A future runtime resolver must resolve the configured path and reject it when it is the Repository itself or any of its descendants. This rule must be based on resolved paths, not a hard-coded repository location or a string-prefix comparison.

This phase defines the invariant and repository hygiene checks only. It does not create a runtime resolver, directories, or private data. The reusable runtime-path implementation belongs to a later phase.

## Windows Controller Runtime

The canonical default Controller Runtime root is:

```text
%LOCALAPPDATA%\LocalAIConsole
```

`LOCAL_AI_CONSOLE_HOME` is the single future override for this root. When it is empty or unset, the platform default applies. An override is private machine configuration and must resolve outside the Repository.

An instance uses this layout:

```text
LocalAIConsole/
├── config/
├── data/
├── prompts/
├── knowledge/
├── logs/
├── cache/
└── backups/
```

| Directory | Classification | Intended content |
| --- | --- | --- |
| `config/` | Private Runtime Data | Machine settings, service configuration, and future model or provider locations. |
| `data/` | Private Runtime Data | Durable application state such as future databases, chats, projects, revisions, summaries, and feedback. |
| `prompts/` | Private Runtime Data | Editable system prompts, user additions, and private workflow overrides. |
| `knowledge/` | Private Runtime Data | Prompt Workbench notes, curated examples, and workflow observations. |
| `logs/` | Private Runtime Data | Operator diagnostics; future logging must avoid unbounded full prompt or chat content. |
| `cache/` | Cache | Recreatable temporary artifacts only. |
| `backups/` | Private Runtime Data | Explicit durable backups and exports. |

`config/` and `prompts/` in this layout are not the Repository's public `config/examples/` and `prompts/examples/` directories.

## Ubuntu Node Runtime direction

The Node Runtime is distinct from the Controller Runtime and must not use the Windows layout.

- Configuration and credentials: `/etc/local-ai-console/`
- Mutable node state, where required: `/var/lib/local-ai-console/`
- Logging: prefer systemd/journald; define a dedicated file-log path only if one is needed later.

GGUF model storage is external to these application-data paths. Future ModelProfile or node configuration will reference model storage without assuming a directory name in this repository or in the Node Runtime.

## Secrets, reporting, and backups

Credentials, API keys, tokens, real host details, private prompts, chats, knowledge, generated outputs, logs, and backups are Private Runtime Data. They must not be committed, pasted into public issues, or included in public debugging reports. Reports should be redacted and avoid chat content, prompt text, model paths, IP addresses, MAC addresses, and credentials.

Backups are durable private exports, not source artifacts. Cache is the only category here that is safe to recreate without loss of authoritative user or machine state.

Future search-provider credentials, Discord or bot credentials/persona/memory, and Prompt Workbench projects, QA history, accepted revisions, and session state follow the same private boundary. The public repository may contain only generic integration code and sanitized examples.
