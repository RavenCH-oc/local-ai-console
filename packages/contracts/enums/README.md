# Enum location

Enum values are defined canonically in the shared JSON Schema rather than duplicated in a second serialized file. The relevant `$defs` are `runtimeSlot`, `runtimeTargetPreference`, `taskKind`, `contextMode`, `promptWorkflowMode`, `promptResponseKind`, `searchMode`, and `platform`.

Semantic explanations and current deployment assumptions are documented in `docs/architecture-contracts.md`.
