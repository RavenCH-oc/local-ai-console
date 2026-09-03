# Local AI Console contracts

This directory contains the canonical, language-neutral architecture contracts shared by future controller, web, node, and workflow components. The canonical serialized form is JSON Schema Draft 2020-12 in `schemas/local-ai-console-contracts.schema.json`.

Each persisted or configurable contract has a `schema_version` and a stable machine `id` where it represents a named domain object. Existing Phase 0C examples use `1.0.0`; additive Phase 1B-3 contract types use `1.1.0`; and Phase 1C-0 workflow/structured-response additions use `1.2.0`. The validator accepts all three. Display names are presentation data, never primary identity. Cross-contract references use stable IDs such as `preferred_model_profile_id` rather than copied objects, display names, or filesystem paths. Knowledge namespaces use a separate hierarchical namespace ID such as `comfyui/example`.

## Layout

- `schemas/`: the canonical JSON Schema and its format notes.
- `examples/`: sanitized JSON examples; none contain a real host, path, credential, prompt, chat, or model file.
- `enums/`: location notes for the canonical enum definitions.

Run `python scripts/validate-contracts.py` from the repository root to parse schema/example JSON, check IDs and references (including Knowledge namespace and Tool references), and validate documented enum semantics without a framework dependency.

## Scope

These contracts define data shape and meaning only. They do not provide runtime routing, persistence, model loading, networking, or application types. Language-specific adapters belong to later phases and must be generated or derived from this canonical representation rather than maintained as competing contract sources.
