"""Tests for built-in Prompt Workbench skill, knowledge, context, and response foundations."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from pydantic import ValidationError

from local_ai_console_control.persistence.models import PromptMessage, PromptProject, PromptProjectState, PromptRevision
from local_ai_console_control.prompt_workbench.catalog import (
    PromptWorkbenchCatalog,
    PromptWorkbenchCatalogError,
    builtin_prompt_engine_root,
)
from local_ai_console_control.prompt_workbench.context import PromptContextAssembler
from local_ai_console_control.prompt_workbench.knowledge import KnowledgeSourceLoadError, KnowledgeSourceLoader
from local_ai_console_control.prompt_workbench.responses import PromptWorkbenchStructuredResponse, ProjectStatePatch


class PromptEngineTests(unittest.TestCase):
    def catalog(self) -> PromptWorkbenchCatalog:
        return PromptWorkbenchCatalog.load(builtin_prompt_engine_root())

    def test_builtin_skill_and_anima_workflow_load_with_all_mode_semantics(self) -> None:
        catalog = self.catalog()
        skill = catalog.get_skill("comfyui_prompt_generator")
        workflow = catalog.get_workflow("anima_base_v1")

        self.assertEqual(skill.display_name, "ComfyUI Prompt Generator")
        self.assertIn("Never silently replace", skill.instruction_text)
        self.assertEqual(workflow.display_name, "Anima Base v1")
        self.assertEqual(set(workflow.supported_modes), {"stable", "balanced", "detailed", "preserve"})
        self.assertEqual(workflow.default_mode, "balanced")
        self.assertEqual(len(workflow.knowledge_sources), 5)
        self.assertEqual(
            tuple(source.id for source in workflow.knowledge_sources),
            (
                "anima_base_v1_fundamentals",
                "anima_base_v1_prompt_structure",
                "anima_base_v1_composition_pose",
                "anima_base_v1_anatomy_stability",
                "anima_base_v1_parameters",
            ),
        )

    def test_missing_skill_source_is_a_clean_catalog_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            package_root = Path(temporary_directory) / "prompt-engine"
            skill_directory = package_root / "skills" / "missing-source"
            workflow_directory = package_root / "workflows"
            skill_directory.mkdir(parents=True)
            workflow_directory.mkdir()
            (skill_directory / "skill.json").write_text(
                json.dumps(
                    {
                        "contract_type": "skill_profile",
                        "id": "missing_source_skill",
                        "display_name": "Missing Source Skill",
                        "description": "Test only.",
                        "instruction_source": {"kind": "public_package", "reference": "SKILL.md"},
                        "required_capabilities": [],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(PromptWorkbenchCatalogError):
                PromptWorkbenchCatalog.load(package_root)

    def test_knowledge_loader_is_deterministic_and_private_extensions_are_optional(self) -> None:
        workflow = self.catalog().get_workflow("anima_base_v1")
        with tempfile.TemporaryDirectory() as temporary_directory:
            private_root = Path(temporary_directory) / "knowledge"
            loader = KnowledgeSourceLoader(private_knowledge_root=private_root)
            built_in_only = loader.load_for_workflow(workflow)
            self.assertEqual(len(built_in_only), 5)
            self.assertTrue(all(document.source_kind == "built_in" for document in built_in_only))

            extension_directory = private_root / "comfyui" / "anima"
            extension_directory.mkdir(parents=True)
            (extension_directory / "z-note.md").write_text("Second private extension.", encoding="utf-8")
            (extension_directory / "a-note.md").write_text("First private extension.", encoding="utf-8")
            merged = loader.load_for_workflow(workflow)

            self.assertEqual([document.source_id for document in merged[-2:]], ["private_extension_001", "private_extension_002"])
            self.assertEqual([document.content for document in merged[-2:]], ["First private extension.", "Second private extension."])
            self.assertNotIn(str(extension_directory), "\n".join(document.source_id for document in merged))

    def test_private_knowledge_path_traversal_is_rejected(self) -> None:
        workflow = replace(self.catalog().get_workflow("anima_base_v1"), private_knowledge_namespace="../escape")
        with tempfile.TemporaryDirectory() as temporary_directory:
            with self.assertRaises(KnowledgeSourceLoadError):
                KnowledgeSourceLoader(private_knowledge_root=Path(temporary_directory)).load_for_workflow(workflow)

    def test_context_assembler_orders_contributions_and_keeps_current_request_last(self) -> None:
        catalog = self.catalog()
        skill = catalog.get_skill("comfyui_prompt_generator")
        workflow = catalog.get_workflow("anima_base_v1")
        timestamp = datetime(2026, 9, 3, tzinfo=timezone.utc)
        project = PromptProject(
            id="pp_test_project",
            title="Sanitized Project",
            workflow_profile_id=workflow.id,
            workflow_mode="preserve",
            created_at=timestamp,
            updated_at=timestamp,
            status="active",
        )
        project_state = PromptProjectState(
            id="pst_test_state",
            project_id=project.id,
            objective="Preserve the public objective.",
            important_constraints=["Keep the main subject."],
            must_preserve=["Readable composition"],
            known_problems=[],
            accepted_observations=[],
            updated_at=timestamp,
        )
        accepted_revision = PromptRevision(
            id="pr_test_revision",
            project_id=project.id,
            parent_revision_id=None,
            positive_prompt="generic subject",
            negative_prompt="artifacts",
            parameters={},
            change_log="Accepted test revision.",
            status="accepted",
            created_at=timestamp,
        )
        messages = [
            PromptMessage(
                id="pm_first",
                session_id="ps_test",
                role="user",
                content="First discussion message.",
                metadata_json=None,
                created_at=timestamp,
            ),
            PromptMessage(
                id="pm_second",
                session_id="ps_test",
                role="assistant",
                content="Second discussion message.",
                metadata_json=None,
                created_at=timestamp,
            ),
        ]
        with tempfile.TemporaryDirectory() as temporary_directory:
            context = PromptContextAssembler().assemble(
                skill=skill,
                workflow=workflow,
                mode="preserve",
                project=project,
                project_state=project_state,
                accepted_revision=accepted_revision,
                session_messages=messages,
                selected_knowledge=KnowledgeSourceLoader(
                    private_knowledge_root=Path(temporary_directory) / "knowledge"
                ).load_for_workflow(workflow),
                current_user_message="Only change the requested dimension.",
            )

        self.assertEqual(context.contributions[0].label, "Base System")
        self.assertEqual(context.contributions[-1].label, "Current Request")
        self.assertEqual(context.messages[-1].content, "Only change the requested dimension.")
        self.assertEqual(sum(message.role.value == "system" for message in context.messages), 1)
        self.assertIn("[Prompt Workbench contribution: Base System]", context.messages[0].content)
        self.assertIn("[Prompt Workbench contribution: Skill]", context.messages[0].content)
        self.assertIn("Knowledge source: Fundamentals", context.messages[0].content)
        self.assertIn("Accepted Revision", [item.label for item in context.contributions])
        discussion = [item for item in context.contributions if item.kind == "discussion"]
        self.assertEqual([item.message.content for item in discussion], ["First discussion message.", "Second discussion message."])
        self.assertEqual(
            {item.stability for item in context.contributions},
            {"stable", "snapshot", "append_only", "dynamic"},
        )

    def test_structured_response_requires_a_proposal_only_for_revision(self) -> None:
        discussion = PromptWorkbenchStructuredResponse.model_validate(
            {"response_type": "discussion", "assistant_text": "Discuss the request.", "warnings": []}
        )
        clarification = PromptWorkbenchStructuredResponse.model_validate(
            {"response_type": "clarification", "assistant_text": "Please clarify one dimension.", "warnings": []}
        )
        revision = PromptWorkbenchStructuredResponse.model_validate(
            {
                "response_type": "revision",
                "assistant_text": "Here is a proposal.",
                "proposed_revision": {
                    "positive_prompt": "generic subject",
                    "negative_prompt": "artifacts",
                    "parameters": {},
                    "change_log": "Proposed only.",
                },
                "warnings": ["Review before accepting."],
            }
        )
        self.assertEqual((discussion.response_type, clarification.response_type, revision.response_type), ("discussion", "clarification", "revision"))
        with self.assertRaises(ValidationError):
            PromptWorkbenchStructuredResponse.model_validate(
                {"response_type": "revision", "assistant_text": "Missing proposal.", "warnings": []}
            )
        with self.assertRaises(ValidationError):
            PromptWorkbenchStructuredResponse.model_validate(
                {
                    "response_type": "discussion",
                    "assistant_text": "Invalid artifact.",
                    "proposed_revision": {
                        "positive_prompt": "generic",
                        "negative_prompt": "",
                        "parameters": {},
                        "change_log": "Should fail.",
                    },
                    "warnings": [],
                }
            )
        with self.assertRaises(ValidationError):
            ProjectStatePatch.model_validate({})


if __name__ == "__main__":
    unittest.main()
