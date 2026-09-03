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
SUPPORTED_SCHEMA_VERSIONS = frozenset(("1.0.0", "1.1.0", "1.2.0"))
STABLE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
NAMESPACE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:/[a-z0-9][a-z0-9_-]*)*$")

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
    "provider_capabilities": "providerCapabilities",
    "runtime_compatibility_record": "runtimeCompatibilityRecord",
    "prompt_context_contribution": "promptContextContribution",
    "knowledge_namespace": "knowledgeNamespace",
    "knowledge_reference": "knowledgeReference",
    "skill_profile": "skillProfile",
    "tool_definition": "toolDefinition",
    "prompt_workbench_response": "promptWorkbenchResponse",
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
    "capability_status": "capabilityStatus",
    "context_stability": "contextStability",
    "tool_permission_class": "toolPermissionClass",
    "tool_approval_policy": "toolApprovalPolicy",
    "runtime_affinity_scope": "runtimeAffinityScope",
}

PROVIDER_CAPABILITY_NAMES = frozenset(
    (
        "streaming",
        "structured_output",
        "native_chat_token_count",
        "reasoning_transport",
        "thinking_toggle",
        "reasoning_budget",
        "realtime_reasoning_end",
        "client_stream_cancel",
        "server_generation_cancel",
        "timings",
        "prompt_cache",
        "vision",
        "tool_calling",
        "model_lifecycle",
        "extensions",
    )
)

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


def validate_namespace_id(value: Any, label: str, failures: list[str]) -> None:
    if not isinstance(value, str) or not NAMESPACE_ID_PATTERN.fullmatch(value):
        failures.append(f"{label} must be a hierarchical namespace ID: {value!r}")


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

    if data.get("schema_version") not in SUPPORTED_SCHEMA_VERSIONS:
        supported = ", ".join(sorted(SUPPORTED_SCHEMA_VERSIONS))
        failures.append(f"{label} must use a supported schema_version ({supported})")

    if "id" in data:
        validate_stable_id(data["id"], f"{label}.id", failures)
    if "namespace_id" in data:
        validate_namespace_id(data["namespace_id"], f"{label}.namespace_id", failures)
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


def validate_capability_set(
    value: Any,
    enums: dict[str, set[str]],
    label: str,
    failures: list[str],
) -> None:
    if not isinstance(value, dict):
        failures.append(f"{label} must be an object")
        return
    unexpected = sorted(set(value).difference(PROVIDER_CAPABILITY_NAMES))
    if unexpected:
        failures.append(f"{label} has unsupported capability names: {', '.join(unexpected)}")
    for name, assessment in value.items():
        if name == "extensions":
            continue
        item_label = f"{label}.{name}"
        if not isinstance(assessment, dict):
            failures.append(f"{item_label} must be an assessment object")
            continue
        validate_enum(assessment.get("status"), enums["capability_status"], f"{item_label}.status", failures)
        if "notes" in assessment and (not isinstance(assessment["notes"], str) or not assessment["notes"]):
            failures.append(f"{item_label}.notes must be a non-empty string when present")
        evidence = assessment.get("evidence")
        if evidence is not None:
            if not isinstance(evidence, dict) or not isinstance(evidence.get("source"), str) or not evidence["source"]:
                failures.append(f"{item_label}.evidence must contain a non-empty source")


def validate_reference_object(value: Any, label: str, failures: list[str]) -> None:
    if not isinstance(value, dict):
        failures.append(f"{label} must be an object")
        return
    validate_stable_id(value.get("kind"), f"{label}.kind", failures)
    if not isinstance(value.get("reference"), str) or not value["reference"]:
        failures.append(f"{label}.reference must be a non-empty opaque reference")


def validate_unique_identifiers(
    values: Any,
    validator: Any,
    label: str,
    failures: list[str],
) -> None:
    if not isinstance(values, list):
        failures.append(f"{label} must be an array")
        return
    if all(isinstance(value, str) for value in values) and len(values) != len(set(values)):
        failures.append(f"{label} contains duplicates")
    for index, value in enumerate(values):
        validator(value, f"{label}[{index}]", failures)


def validate_performance_timing(value: Any, label: str, failures: list[str]) -> None:
    if not isinstance(value, dict):
        failures.append(f"{label} must be an object")
        return
    integer_fields = {"input_tokens", "output_tokens"}
    number_fields = {
        "prompt_time_ms",
        "generation_time_ms",
        "time_to_first_event_ms",
        "time_to_first_content_ms",
        "total_time_ms",
        "prompt_tokens_per_second",
        "generation_tokens_per_second",
    }
    allowed = integer_fields | number_fields | {"provider_cache", "extensions"}
    unexpected = sorted(set(value).difference(allowed))
    if unexpected:
        failures.append(f"{label} has unsupported fields: {', '.join(unexpected)}")
    for field in integer_fields:
        if field in value and (isinstance(value[field], bool) or not isinstance(value[field], int) or value[field] < 0):
            failures.append(f"{label}.{field} must be a non-negative integer")
    for field in number_fields:
        if field in value and (isinstance(value[field], bool) or not isinstance(value[field], (int, float)) or value[field] < 0):
            failures.append(f"{label}.{field} must be a non-negative number")
    cache = value.get("provider_cache")
    if cache is not None:
        if not isinstance(cache, dict):
            failures.append(f"{label}.provider_cache must be an object")
        else:
            allowed_cache = {"cached_input_tokens", "uncached_input_tokens", "reuse_ratio", "extensions"}
            unexpected_cache = sorted(set(cache).difference(allowed_cache))
            if unexpected_cache:
                failures.append(f"{label}.provider_cache has unsupported fields: {', '.join(unexpected_cache)}")
            for field in {"cached_input_tokens", "uncached_input_tokens"}:
                if field in cache and (isinstance(cache[field], bool) or not isinstance(cache[field], int) or cache[field] < 0):
                    failures.append(f"{label}.provider_cache.{field} must be a non-negative integer")
            if "reuse_ratio" in cache and (
                isinstance(cache["reuse_ratio"], bool)
                or not isinstance(cache["reuse_ratio"], (int, float))
                or not 0 <= cache["reuse_ratio"] <= 1
            ):
                failures.append(f"{label}.provider_cache.reuse_ratio must be between 0 and 1")


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
        if contract_type == "task_context" and "runtime_affinity_hint" in data:
            affinity = data["runtime_affinity_hint"]
            if not isinstance(affinity, dict):
                failures.append(f"{label}.runtime_affinity_hint must be an object")
            else:
                validate_enum(
                    affinity.get("scope"),
                    enums["runtime_affinity_scope"],
                    f"{label}.runtime_affinity_hint.scope",
                    failures,
                )
                if not isinstance(affinity.get("key"), str) or not affinity["key"]:
                    failures.append(f"{label}.runtime_affinity_hint.key must be a non-empty opaque key")
                if "target_preference" in affinity:
                    validate_enum(
                        affinity["target_preference"],
                        enums["runtime_target_preference"],
                        f"{label}.runtime_affinity_hint.target_preference",
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
        if "skill_profile_id" in data:
            validate_stable_id(data["skill_profile_id"], f"{label}.skill_profile_id", failures)
        if "knowledge_sources" in data:
            knowledge_sources = data["knowledge_sources"]
            if not isinstance(knowledge_sources, list):
                failures.append(f"{label}.knowledge_sources must be an array")
            else:
                source_ids: set[str] = set()
                for index, source in enumerate(knowledge_sources):
                    item_label = f"{label}.knowledge_sources[{index}]"
                    if not isinstance(source, dict):
                        failures.append(f"{item_label} must be an object")
                        continue
                    source_id = source.get("id")
                    validate_stable_id(source_id, f"{item_label}.id", failures)
                    if isinstance(source_id, str):
                        if source_id in source_ids:
                            failures.append(f"{label}.knowledge_sources contains duplicate ID {source_id!r}")
                        source_ids.add(source_id)
                    if source.get("source_kind") not in {"built_in", "private_runtime"}:
                        failures.append(f"{item_label}.source_kind must be built_in or private_runtime")
                    if not isinstance(source.get("reference"), str) or not source["reference"]:
                        failures.append(f"{item_label}.reference must be a non-empty source reference")
                    validate_enum(source.get("stability"), enums["context_stability"], f"{item_label}.stability", failures)
                references = data.get("knowledge_source_references")
                if isinstance(references, list) and set(references) != source_ids:
                    failures.append(f"{label}.knowledge_source_references must match knowledge_sources IDs")
        if "mode_instructions" in data:
            mode_instructions = data["mode_instructions"]
            if not isinstance(mode_instructions, dict):
                failures.append(f"{label}.mode_instructions must be an object")
            else:
                expected_modes = {"stable", "balanced", "detailed", "preserve"}
                if set(mode_instructions) != expected_modes:
                    failures.append(f"{label}.mode_instructions must define all four workflow modes")
                for mode, instruction in mode_instructions.items():
                    if not isinstance(instruction, str) or not instruction.strip():
                        failures.append(f"{label}.mode_instructions.{mode} must be non-empty text")

    if contract_type == "prompt_response":
        validate_enum(data.get("response_kind"), enums["prompt_response_kind"], f"{label}.response_kind", failures)
        if data.get("response_kind") == "revision" and not data.get("revision_id"):
            failures.append(f"{label} revision responses require revision_id")

    if contract_type == "prompt_workbench_response":
        response_type = data.get("response_type")
        validate_enum(response_type, enums["prompt_response_kind"], f"{label}.response_type", failures)
        proposed_revision = data.get("proposed_revision")
        if response_type == "revision":
            if not isinstance(proposed_revision, dict):
                failures.append(f"{label} revision responses require proposed_revision")
            else:
                for field in ("positive_prompt", "negative_prompt", "parameters", "change_log"):
                    if field not in proposed_revision:
                        failures.append(f"{label}.proposed_revision is missing {field}")
        elif proposed_revision is not None:
            failures.append(f"{label} non-revision responses cannot include proposed_revision")
        patch = data.get("project_state_patch")
        if patch is not None:
            if not isinstance(patch, dict) or not patch:
                failures.append(f"{label}.project_state_patch must be a non-empty object")
            else:
                allowed_patch_fields = {
                    "objective",
                    "important_constraints_add",
                    "must_preserve_add",
                    "known_problems_add",
                    "accepted_observations_add",
                }
                unexpected_patch_fields = sorted(set(patch).difference(allowed_patch_fields))
                if unexpected_patch_fields:
                    failures.append(
                        f"{label}.project_state_patch has unsupported fields: {', '.join(unexpected_patch_fields)}"
                    )
        warnings = data.get("warnings")
        if not isinstance(warnings, list) or any(not isinstance(item, str) or not item.strip() for item in warnings):
            failures.append(f"{label}.warnings must be an array of non-empty strings")

    if contract_type == "provider_capabilities":
        validate_stable_id(data.get("provider"), f"{label}.provider", failures)
        validate_capability_set(data.get("capabilities"), enums, f"{label}.capabilities", failures)

    if contract_type == "runtime_compatibility_record":
        validate_stable_id(data.get("provider"), f"{label}.provider", failures)
        validate_stable_id(data.get("model_profile_id"), f"{label}.model_profile_id", failures)
        validate_capability_set(data.get("capabilities"), enums, f"{label}.capabilities", failures)
        if "performance_timing" in data:
            validate_performance_timing(data["performance_timing"], f"{label}.performance_timing", failures)

    if contract_type == "prompt_context_contribution":
        validate_stable_id(data.get("kind"), f"{label}.kind", failures)
        validate_enum(data.get("stability"), enums["context_stability"], f"{label}.stability", failures)
        if isinstance(data.get("priority"), bool) or not isinstance(data.get("priority"), int) or data["priority"] < 0:
            failures.append(f"{label}.priority must be a non-negative integer")
        if "token_budget" in data and (
            isinstance(data["token_budget"], bool) or not isinstance(data["token_budget"], int) or data["token_budget"] < 1
        ):
            failures.append(f"{label}.token_budget must be a positive integer")
        source = data.get("source")
        if not isinstance(source, dict):
            failures.append(f"{label}.source must be an object")
        elif source.get("kind") == "inline_text":
            if not isinstance(source.get("content"), str):
                failures.append(f"{label}.source.content must be text for inline_text")
        elif source.get("kind") == "reference":
            if not isinstance(source.get("reference"), str) or not source["reference"]:
                failures.append(f"{label}.source.reference must be non-empty for reference")
        else:
            failures.append(f"{label}.source.kind must be inline_text or reference")

    if contract_type == "knowledge_namespace":
        if not isinstance(data.get("label"), str) or not data["label"]:
            failures.append(f"{label}.label must be a non-empty string")
        if not isinstance(data.get("source_reference"), str) or not data["source_reference"]:
            failures.append(f"{label}.source_reference must be a non-empty opaque reference")

    if contract_type == "knowledge_reference":
        validate_namespace_id(data.get("namespace_id"), f"{label}.namespace_id", failures)
        if not isinstance(data.get("source_reference"), str) or not data["source_reference"]:
            failures.append(f"{label}.source_reference must be a non-empty opaque reference")

    if contract_type == "skill_profile":
        validate_reference_object(data.get("instruction_source"), f"{label}.instruction_source", failures)
        validate_unique_identifiers(
            data.get("required_capabilities"), validate_stable_id, f"{label}.required_capabilities", failures
        )
        if "knowledge_namespaces" in data:
            validate_unique_identifiers(
                data["knowledge_namespaces"], validate_namespace_id, f"{label}.knowledge_namespaces", failures
            )
        if "allowed_tool_ids" in data:
            validate_unique_identifiers(data["allowed_tool_ids"], validate_stable_id, f"{label}.allowed_tool_ids", failures)
        if "default_task_kind" in data:
            validate_enum(data["default_task_kind"], enums["task_kind"], f"{label}.default_task_kind", failures)

    if contract_type == "tool_definition":
        if not isinstance(data.get("input_schema"), dict):
            failures.append(f"{label}.input_schema must be an object")
        permission = data.get("permission")
        if not isinstance(permission, dict):
            failures.append(f"{label}.permission must be an object")
        else:
            validate_enum(
                permission.get("permission_class"),
                enums["tool_permission_class"],
                f"{label}.permission.permission_class",
                failures,
            )
            validate_enum(
                permission.get("approval_policy"),
                enums["tool_approval_policy"],
                f"{label}.permission.approval_policy",
                failures,
            )
        if "result_limits" in data:
            limits = data["result_limits"]
            if not isinstance(limits, dict):
                failures.append(f"{label}.result_limits must be an object")
            else:
                for field in ("max_result_bytes", "max_result_tokens", "timeout_ms"):
                    if field in limits and (
                        isinstance(limits[field], bool) or not isinstance(limits[field], int) or limits[field] < 1
                    ):
                        failures.append(f"{label}.result_limits.{field} must be a positive integer")
        validate_reference_object(data.get("executor"), f"{label}.executor", failures)

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


def require_namespace_reference(
    reference: Any,
    namespaces: set[str],
    label: str,
    failures: list[str],
) -> None:
    if reference not in namespaces:
        failures.append(f"{label} must reference an example knowledge_namespace: {reference!r}")


def validate_references(
    examples: list[tuple[Path, dict[str, Any], str]],
    catalog: dict[str, str],
    namespaces: set[str],
    failures: list[str],
) -> None:
    reference_rules = {
        "model_profile": (("generation_defaults.generation_preset_id", "generation_preset"),),
        "mode_profile": (
            ("preferred_model_profile_id", "model_profile"),
            ("generation_preset_id", "generation_preset"),
            ("context_policy_id", "context_policy"),
        ),
        "prompt_workflow_profile": (
            ("preferred_model_profile_id", "model_profile"),
            ("skill_profile_id", "skill_profile"),
        ),
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
        "runtime_compatibility_record": (("model_profile_id", "model_profile"),),
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
        if contract_type == "knowledge_reference":
            require_namespace_reference(data.get("namespace_id"), namespaces, f"{label}.namespace_id", failures)
        if contract_type == "skill_profile":
            for index, namespace_id in enumerate(data.get("knowledge_namespaces", [])):
                require_namespace_reference(
                    namespace_id,
                    namespaces,
                    f"{label}.knowledge_namespaces[{index}]",
                    failures,
                )
            for index, tool_id in enumerate(data.get("allowed_tool_ids", [])):
                require_reference(
                    {"tool_id": tool_id},
                    "tool_id",
                    "tool_definition",
                    catalog,
                    f"{label}.allowed_tool_ids[{index}]",
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
    namespaces: set[str] = set()

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
        if contract_type == "knowledge_namespace" and isinstance(data.get("namespace_id"), str):
            namespace_id = data["namespace_id"]
            if namespace_id in namespaces:
                failures.append(f"Duplicate knowledge namespace ID {namespace_id!r}")
            else:
                namespaces.add(namespace_id)
        examples.append((path, data, contract_type))

    if schema is not None:
        validate_references(examples, catalog, namespaces, failures)
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
