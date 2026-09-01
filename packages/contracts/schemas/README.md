# Schema format

`local-ai-console-contracts.schema.json` uses JSON Schema Draft 2020-12. Its `$defs` are the canonical definitions for the named contracts and shared value sets; the root `oneOf` accepts each top-level contract object.

The schema keeps backend- and provider-specific details inside explicit `extensions` objects. Core relationships and semantics remain named fields so the contracts do not collapse into unstructured metadata.
