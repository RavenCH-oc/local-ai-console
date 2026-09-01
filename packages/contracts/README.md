# Local AI Console contracts

This directory contains the canonical, language-neutral architecture contracts shared by future controller, web, node, and workflow components. The canonical serialized form is JSON Schema Draft 2020-12 in `schemas/local-ai-console-contracts.schema.json`.

Each persisted or configurable contract has a `schema_version` and a stable machine `id` where it represents a named domain object. Display names are presentation data, never primary identity. Cross-contract references use stable IDs such as `preferred_model_profile_id` rather than copied objects, display names, or filesystem paths.

## Layout

- `schemas/`: the canonical JSON Schema and its format notes.
- `examples/`: sanitized JSON examples; none contain a real host, path, credential, prompt, chat, or model file.
- `enums/`: location notes for the canonical enum definitions.

Run `python scripts/validate-contracts.py` from the repository root to parse schema/example JSON, check IDs and references, and validate documented enum semantics without a framework dependency.

## Scope

These contracts define data shape and meaning only. They do not provide runtime routing, persistence, model loading, networking, or application types. Language-specific adapters belong to later phases and must be generated or derived from this canonical representation rather than maintained as competing contract sources.
