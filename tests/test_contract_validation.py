"""Focused tests for Phase 1B-3 and Phase 1C-0 contract-validator additions."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPOSITORY_ROOT / "scripts" / "validate-contracts.py"
SPEC = importlib.util.spec_from_file_location("contract_validation", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
CONTRACT_VALIDATION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONTRACT_VALIDATION)


class ContractValidationTests(unittest.TestCase):
    def load_schema(self) -> dict[str, object]:
        schema_path = REPOSITORY_ROOT / "packages" / "contracts" / "schemas" / "local-ai-console-contracts.schema.json"
        return json.loads(schema_path.read_text(encoding="utf-8"))

    def enums(self) -> dict[str, set[str]]:
        schema = self.load_schema()
        return {name: CONTRACT_VALIDATION.enum_values(schema, name) for name in CONTRACT_VALIDATION.ENUM_DEFINITIONS}

    def test_phase_1b_3_contracts_and_enums_are_canonical_schema_definitions(self) -> None:
        schema = self.load_schema()
        definitions = schema["$defs"]

        for definition in CONTRACT_VALIDATION.CONTRACT_DEFINITIONS.values():
            with self.subTest(definition=definition):
                self.assertIn(definition, definitions)
        self.assertEqual(
            self.enums()["capability_status"],
            {"supported", "unsupported", "partial", "inferred", "unverified", "unavailable"},
        )
        self.assertEqual(
            self.enums()["context_stability"],
            {"stable", "snapshot", "append_only", "dynamic"},
        )

    def test_phase_1b_3_semantics_reject_invalid_capability_stability_and_tool_permission(self) -> None:
        failures: list[str] = []
        enums = self.enums()

        CONTRACT_VALIDATION.validate_semantics(
            {"provider": "example_provider", "capabilities": {"streaming": {"status": "unknown"}}},
            "provider_capabilities",
            enums,
            "provider",
            failures,
        )
        CONTRACT_VALIDATION.validate_semantics(
            {
                "kind": "instruction",
                "source": {"kind": "reference", "reference": "public_template"},
                "stability": "volatile",
                "priority": 1,
            },
            "prompt_context_contribution",
            enums,
            "contribution",
            failures,
        )
        CONTRACT_VALIDATION.validate_semantics(
            {
                "input_schema": {},
                "permission": {"permission_class": "read_only", "approval_policy": "sometimes"},
                "executor": {"kind": "example_executor", "reference": "example_tool"},
            },
            "tool_definition",
            enums,
            "tool",
            failures,
        )

        self.assertTrue(any("provider.capabilities.streaming.status" in failure for failure in failures))
        self.assertTrue(any("contribution.stability" in failure for failure in failures))
        self.assertTrue(any("tool.permission.approval_policy" in failure for failure in failures))

    def test_skill_references_require_a_known_namespace_and_tool_definition(self) -> None:
        skill = {
            "knowledge_namespaces": ["comfyui/example"],
            "allowed_tool_ids": ["example_public_status_tool"],
        }
        example_path = REPOSITORY_ROOT / "packages" / "contracts" / "examples" / "skill-profile.example.json"
        failures: list[str] = []

        CONTRACT_VALIDATION.validate_references(
            [(example_path, skill, "skill_profile")],
            {"example_public_status_tool": "tool_definition"},
            {"comfyui/example"},
            failures,
        )
        self.assertEqual(failures, [])

        failures.clear()
        CONTRACT_VALIDATION.validate_references(
            [(example_path, skill, "skill_profile")],
            {},
            set(),
            failures,
        )
        self.assertEqual(len(failures), 2)

    def test_phase_1c_0_response_semantics_require_explicit_revision_artifacts(self) -> None:
        failures: list[str] = []

        CONTRACT_VALIDATION.validate_semantics(
            {
                "response_type": "revision",
                "assistant_text": "A sanitized revision proposal.",
                "warnings": [],
            },
            "prompt_workbench_response",
            self.enums(),
            "response",
            failures,
        )
        CONTRACT_VALIDATION.validate_semantics(
            {
                "response_type": "discussion",
                "assistant_text": "A sanitized discussion response.",
                "proposed_revision": {},
                "project_state_patch": {"unsupported": ["value"]},
                "warnings": [""],
            },
            "prompt_workbench_response",
            self.enums(),
            "response",
            failures,
        )

        self.assertTrue(any("revision responses require proposed_revision" in failure for failure in failures))
        self.assertTrue(any("non-revision responses cannot include proposed_revision" in failure for failure in failures))
        self.assertTrue(any("project_state_patch has unsupported fields" in failure for failure in failures))
        self.assertTrue(any("warnings must be an array" in failure for failure in failures))


if __name__ == "__main__":
    unittest.main()
