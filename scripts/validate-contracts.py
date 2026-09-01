"""Validate Local AI Console contract examples with only the Python standard library."""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
CONTRACTS_ROOT = REPOSITORY_ROOT / "packages" / "contracts"
SCHEMA_PATH = CONTRACTS_ROOT / "schemas" / "local-ai-console-contracts.schema.json"
EXAMPLES_DIR = CONTRACTS_ROOT / "examples"
EXPECTED_SCHEMA_VERSION = "1.0.0"
STABLE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")

CONTRACT_DEFINITIONS = {
    "model_profile": "modelProfile",
    "generation_preset": "generationPreset",
    "context_policy": "contextPolicy",
    "mode_profile": "modeProfile",
    "prompt_workflow_profile": "promptWorkflowProfile",
    "prompt_project": "promptProject",
    "prompt_session": "promptSession",
    "prompt_project_state": "promptProjectState",
    "prompt_revision": "promptRevision",
    "prompt_response": "promptResponse",
    "task_context": "taskContext",
    "task_routing": "taskRouting",
    "search_provider": "searchProvider",
    "search_request": "searchRequest",
    "search_response": "searchResponse",
    "host_profile": "hostProfile",
}

ENUM_DEFINITIONS = {
    "runtime_slot": "runtimeSlot",
    "runtime_target_preference": "runtimeTargetPreference",
    "runtime_slot_availability": "runtimeSlotAvailability",
    "task_kind": "taskKind",
    "context_mode": "contextMode",
    "prompt_workflow_mode": "promptWorkflowMode",
    "prompt_response_kind": "promptResponseKind",
    "search_mode": "searchMode",
    "platform": "platform",
}

SENSITIVE_PATTERNS = (
    re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    re.compile(r"\b[0-9a-f]{2}(?:[:-][0-9a-f]{2}){5}\b", re.IGNORECASE),
    re.compile(r"\bgh[pousr]_[a-z0-9_]{20,}\b", re.IGNORECASE),
    re.compile(r"\bAIza[0-9a-z_-]{20,}\b", re.IGNORECASE),
    re.compile(r"\b[a-z0-9_-]{24}\.[a-z0-9_-]{6}\.[a-z0-9_-]{27}\b", re.IGNORECASE),
    re.compile(r"[a-z]:\\users\\", re.IGNORECASE),
)


def load_json(path: Path, failures: list[str]) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        failures.append(f"Invalid JSON in {path.relative_to(REPOSITORY_ROOT)}: {error}")
        return None
    if not isinstance(data, dict):
        failures.append(f"Contract JSON must contain an object: {path.relative_to(REPOSITORY_ROOT)}")
        return None
    return data


def enum_values(schema: dict[str, Any], name: str) -> set[str]:
    values = schema["$defs"][ENUM_DEFINITIONS[name]]["enum"]
    return set(values)


def value_at(data: dict[str, Any], dotted_path: str) -> Any | None:
    value: Any = data
    for key in dotted_path.split("."):
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value


def validate_enum(value: Any, allowed: set[str], label: str, failures: list[str]) -> None:
    if value not in allowed:
        failures.append(f"{label} has unsupported value: {value!r}")


def validate_stable_id(value: Any, label: str, failures: list[str]) -> None:
    if not isinstance(value, str) or not STABLE_ID_PATTERN.fullmatch(value):
        failures.append(f"{label} must be a stable machine ID: {value!r}")


def validate_root_shape(
    example_path: Path,
    data: dict[str, Any],
    schema: dict[str, Any],
    failures: list[str],
) -> str | None:
    contract_type = data.get("contract_type")
    definition_name = CONTRACT_DEFINITIONS.get(contract_type)
    label = example_path.relative_to(REPOSITORY_ROOT).as_posix()
    if definition_name is None:
        failures.append(f"{label} has unknown contract_type: {contract_type!r}")
        return None

    definition = schema["$defs"][definition_name]
    required = set(definition.get("required", []))
    missing = sorted(required.difference(data))
    if missing:
        failures.append(f"{label} is missing required fields: {', '.join(missing)}")

    allowed = set(definition.get("properties", []))
    unexpected = sorted(set(data).difference(allowed))
    if unexpected:
        failures.append(f"{label} has unsupported fields: {', '.join(unexpected)}")

    if data.get("schema_version") != EXPECTED_SCHEMA_VERSION:
        failures.append(f"{label} must use schema_version {EXPECTED_SCHEMA_VERSION}")

    if "id" in data:
        validate_stable_id(data["id"], f"{label}.id", failures)
    return contract_type


def validate_task_preferences(
    preferences: Any,
    enums: dict[str, set[str]],
    label: str,
    failures: list[str],
) -> None:
    if not isinstance(preferences, list):
        failures.append(f"{label} must be an array")
        return
    for index, preference in enumerate(preferences):
        item_label = f"{label}[{index}]"
        if not isinstance(preference, dict):
            failures.append(f"{item_label} must be an object")
            continue
        validate_enum(preference.get("task_kind"), enums["task_kind"], f"{item_label}.task_kind", failures)
        validate_enum(
            preference.get("target_preference"),
            enums["runtime_target_preference"],
            f"{item_label}.target_preference",
            failures,
        )
        capabilities = preference.get("required_capabilities")
        if not isinstance(capabilities, list):
            failures.append(f"{item_label}.required_capabilities must be an array")
        elif len(capabilities) != len(set(capabilities)):
            failures.append(f"{item_label}.required_capabilities contains duplicates")


def validate_semantics(
    data: dict[str, Any],
    contract_type: str,
    enums: dict[str, set[str]],
    label: str,
    failures: list[str],
) -> None:
    if contract_type == "model_profile":
        validate_stable_id(data.get("backend"), f"{label}.backend", failures)
        location = data.get("model_location")
        if not isinstance(location, dict) or location.get("kind") not in {"external_path", "external_reference"}:
            failures.append(f"{label}.model_location must use an external path or reference")
        capabilities = data.get("capabilities")
        if not isinstance(capabilities, dict):
            failures.append(f"{label}.capabilities must be an object")

    if contract_type == "context_policy":
        validate_enum(data.get("mode"), enums["context_mode"], f"{label}.mode", failures)
        validate_enum(
            data.get("compression_task_target"),
            enums["runtime_target_preference"],
            f"{label}.compression_task_target",
            failures,
        )
        thresholds = [data.get(name) for name in ("notice_threshold", "urgent_threshold", "safety_threshold")]
        if not all(isinstance(value, (int, float)) for value in thresholds):
            failures.append(f"{label} thresholds must be numeric")
        elif not 0 < thresholds[0] < thresholds[1] < thresholds[2] <= 1:
            failures.append(f"{label} thresholds must satisfy 0 < notice < urgent < safety <= 1")
        if data.get("mode") == "llm_compact" and data.get("confirmation_required") is not True:
            failures.append(f"{label} must require confirmation for llm_compact")

    if contract_type in {"task_context", "task_routing"}:
        validate_enum(data.get("task_kind"), enums["task_kind"], f"{label}.task_kind", failures)
        validate_enum(
            data.get("target_preference"),
            enums["runtime_target_preference"],
            f"{label}.target_preference",
            failures,
        )

    if contract_type == "mode_profile":
        validate_task_preferences(data.get("task_routing_preferences"), enums, f"{label}.task_routing_preferences", failures)

    if contract_type == "prompt_workflow_profile":
        supported_modes = data.get("supported_modes")
        if not isinstance(supported_modes, list):
            failures.append(f"{label}.supported_modes must be an array")
        else:
            for mode in supported_modes:
                validate_enum(mode, enums["prompt_workflow_mode"], f"{label}.supported_modes", failures)
            if data.get("default_mode") not in supported_modes:
                failures.append(f"{label}.default_mode must occur in supported_modes")
        validate_enum(
            data.get("fallback_target_preference"),
            enums["runtime_target_preference"],
            f"{label}.fallback_target_preference",
            failures,
        )

    if contract_type == "prompt_response":
        validate_enum(data.get("response_kind"), enums["prompt_response_kind"], f"{label}.response_kind", failures)
        if data.get("response_kind") == "revision" and not data.get("revision_id"):
            failures.append(f"{label} revision responses require revision_id")

    if contract_type == "host_profile":
        validate_enum(data.get("platform"), enums["platform"], f"{label}.platform", failures)
        runtime_slots = data.get("runtime_slots")
        if not isinstance(runtime_slots, list):
            failures.append(f"{label}.runtime_slots must be an array")
        else:
            seen_slots: set[str] = set()
            for index, slot_state in enumerate(runtime_slots):
                item_label = f"{label}.runtime_slots[{index}]"
                if not isinstance(slot_state, dict):
                    failures.append(f"{item_label} must be an object")
                    continue
                slot = slot_state.get("slot")
                validate_enum(slot, enums["runtime_slot"], f"{item_label}.slot", failures)
                validate_enum(
                    slot_state.get("availability"),
                    enums["runtime_slot_availability"],
                    f"{item_label}.availability",
                    failures,
                )
                if isinstance(slot, str) and slot in seen_slots:
                    failures.append(f"{label}.runtime_slots contains duplicate slot {slot}")
                if isinstance(slot, str):
                    seen_slots.add(slot)


def require_reference(
    data: dict[str, Any],
    field: str,
    target_type: str,
    catalog: dict[str, str],
    label: str,
    failures: list[str],
) -> None:
    reference = value_at(data, field)
    if reference is None:
        return
    if catalog.get(reference) != target_type:
        failures.append(f"{label}.{field} must reference an example {target_type} ID: {reference!r}")


def validate_references(
    examples: list[tuple[Path, dict[str, Any], str]],
    catalog: dict[str, str],
    failures: list[str],
) -> None:
    reference_rules = {
        "model_profile": (("generation_defaults.generation_preset_id", "generation_preset"),),
        "mode_profile": (
            ("preferred_model_profile_id", "model_profile"),
            ("generation_preset_id", "generation_preset"),
            ("context_policy_id", "context_policy"),
        ),
        "prompt_workflow_profile": (("preferred_model_profile_id", "model_profile"),),
        "prompt_project": (
            ("workflow_profile_id", "prompt_workflow_profile"),
            ("active_session_id", "prompt_session"),
            ("current_revision_id", "prompt_revision"),
        ),
        "prompt_session": (("project_id", "prompt_project"),),
        "prompt_project_state": (
            ("project_id", "prompt_project"),
            ("current_revision_id", "prompt_revision"),
        ),
        "prompt_revision": (("project_id", "prompt_project"), ("parent_revision_id", "prompt_revision")),
        "prompt_response": (
            ("project_id", "prompt_project"),
            ("session_id", "prompt_session"),
            ("revision_id", "prompt_revision"),
        ),
        "task_context": (("model_profile_id", "model_profile"),),
        "task_routing": (("model_profile_id", "model_profile"),),
        "search_response": (("provider_id", "search_provider"),),
    }

    for path, data, contract_type in examples:
        label = path.relative_to(REPOSITORY_ROOT).as_posix()
        for field, target_type in reference_rules.get(contract_type, ()):
            require_reference(data, field, target_type, catalog, label, failures)
        if contract_type == "mode_profile":
            for index, preference in enumerate(data.get("task_routing_preferences", [])):
                if isinstance(preference, dict):
                    require_reference(
                        preference,
                        "model_profile_id",
                        "model_profile",
                        catalog,
                        f"{label}.task_routing_preferences[{index}]",
                        failures,
                    )


def check_sanitized_examples(example_paths: list[Path], failures: list[str]) -> None:
    for path in example_paths:
        text = path.read_text(encoding="utf-8")
        for pattern in SENSITIVE_PATTERNS:
            if pattern.search(text):
                failures.append(f"Potential private value in {path.relative_to(REPOSITORY_ROOT)}")
                break


def main() -> int:
    failures: list[str] = []
    schema = load_json(SCHEMA_PATH, failures)
    example_paths = sorted(EXAMPLES_DIR.glob("*.json"))
    if not example_paths:
        failures.append("No contract examples found")

    examples: list[tuple[Path, dict[str, Any], str]] = []
    catalog: dict[str, str] = {}

    if schema is not None:
        missing_definitions = sorted(set(CONTRACT_DEFINITIONS.values()).difference(schema.get("$defs", {})))
        if missing_definitions:
            failures.append(f"Schema is missing contract definitions: {', '.join(missing_definitions)}")
        missing_enums = sorted(set(ENUM_DEFINITIONS.values()).difference(schema.get("$defs", {})))
        if missing_enums:
            failures.append(f"Schema is missing enum definitions: {', '.join(missing_enums)}")
        enums = {name: enum_values(schema, name) for name in ENUM_DEFINITIONS}
    else:
        enums = {}

    for path in example_paths:
        data = load_json(path, failures)
        if data is None or schema is None:
            continue
        contract_type = validate_root_shape(path, data, schema, failures)
        if contract_type is None:
            continue
        label = path.relative_to(REPOSITORY_ROOT).as_posix()
        validate_semantics(data, contract_type, enums, label, failures)
        if "id" in data and isinstance(data["id"], str):
            prior_type = catalog.get(data["id"])
            if prior_type is not None:
                failures.append(f"Duplicate example ID {data['id']!r}: {prior_type} and {contract_type}")
            else:
                catalog[data["id"]] = contract_type
        examples.append((path, data, contract_type))

    if schema is not None:
        validate_references(examples, catalog, failures)
    check_sanitized_examples(example_paths, failures)

    if failures:
        print("Contract validation failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print(f"Contract validation passed for {len(examples)} sanitized examples.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
