"""Load and validate built-in Prompt Workbench skill and workflow packages."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


WORKFLOW_MODES = frozenset(("stable", "balanced", "detailed", "preserve"))


class PromptWorkbenchCatalogError(ValueError):
    """Raised when a built-in skill or workflow package is malformed or unsafe."""


def builtin_prompt_engine_root() -> Path:
    """Locate source-managed built-ins relative to the installed Controller source tree."""

    return Path(__file__).resolve().parents[5] / "packages" / "prompt-engine"


@dataclass(frozen=True, slots=True)
class KnowledgeSourceDeclaration:
    """A workflow-declared knowledge source with no direct filesystem authority."""

    id: str
    label: str
    source_kind: str
    reference: str
    stability: str
    token_budget: int | None


@dataclass(frozen=True, slots=True)
class BuiltInSkill:
    """A parsed source-managed SkillProfile and its public instruction text."""

    id: str
    display_name: str
    description: str
    instruction_text: str
    required_capabilities: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BuiltInWorkflow:
    """A parsed built-in PromptWorkflowProfile with selected knowledge declarations."""

    id: str
    display_name: str
    model_family: str
    skill_profile_id: str
    supported_modes: tuple[str, ...]
    default_mode: str
    workflow_instructions: str
    mode_instructions: dict[str, str]
    knowledge_sources: tuple[KnowledgeSourceDeclaration, ...]
    private_knowledge_namespace: str
    package_directory: Path


def _require_text(value: Any, field: str, path: Path) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PromptWorkbenchCatalogError(f"{path.name} requires non-empty {field}.")
    return value.strip()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PromptWorkbenchCatalogError(f"Unable to load built-in manifest {path.name}.") from error
    if not isinstance(value, dict):
        raise PromptWorkbenchCatalogError(f"Built-in manifest {path.name} must contain an object.")
    return value


def resolve_package_file(package_directory: Path, reference: str, *, required: bool = True) -> Path:
    """Resolve a declared relative file while rejecting traversal and absolute paths."""

    relative_path = Path(reference)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise PromptWorkbenchCatalogError("Built-in package references must be relative and cannot traverse directories.")
    package_root = package_directory.resolve(strict=False)
    candidate = (package_root / relative_path).resolve(strict=False)
    try:
        candidate.relative_to(package_root)
    except ValueError as error:
        raise PromptWorkbenchCatalogError("Built-in package reference escapes its package directory.") from error
    if required and not candidate.is_file():
        raise PromptWorkbenchCatalogError("A declared built-in package source is missing.")
    return candidate


class PromptWorkbenchCatalog:
    """Registry of built-in workflow packages; it never reads private runtime data."""

    def __init__(self, *, package_root: Path, skills: dict[str, BuiltInSkill], workflows: dict[str, BuiltInWorkflow]) -> None:
        self.package_root = package_root
        self._skills = skills
        self._workflows = workflows

    @classmethod
    def load(cls, package_root: Path) -> "PromptWorkbenchCatalog":
        root = package_root.resolve(strict=False)
        skills_root = root / "skills"
        workflows_root = root / "workflows"
        if not skills_root.is_dir() or not workflows_root.is_dir():
            raise PromptWorkbenchCatalogError("Prompt-engine package is missing its skills or workflows directory.")

        skills: dict[str, BuiltInSkill] = {}
        for manifest_path in sorted(skills_root.glob("*/skill.json"), key=lambda item: item.as_posix().casefold()):
            skill = cls._load_skill(manifest_path)
            if skill.id in skills:
                raise PromptWorkbenchCatalogError("Built-in SkillProfile IDs must be unique.")
            skills[skill.id] = skill

        workflows: dict[str, BuiltInWorkflow] = {}
        for manifest_path in sorted(workflows_root.glob("*/workflow.json"), key=lambda item: item.as_posix().casefold()):
            workflow = cls._load_workflow(manifest_path)
            if workflow.id in workflows:
                raise PromptWorkbenchCatalogError("Built-in PromptWorkflowProfile IDs must be unique.")
            workflows[workflow.id] = workflow

        if not skills or not workflows:
            raise PromptWorkbenchCatalogError("At least one built-in skill and workflow are required.")
        for workflow in workflows.values():
            if workflow.skill_profile_id not in skills:
                raise PromptWorkbenchCatalogError("A workflow references a missing built-in SkillProfile.")
        return cls(package_root=root, skills=skills, workflows=workflows)

    @staticmethod
    def _load_skill(manifest_path: Path) -> BuiltInSkill:
        payload = _read_json(manifest_path)
        if payload.get("contract_type") != "skill_profile":
            raise PromptWorkbenchCatalogError("Built-in skill manifest must be a SkillProfile.")
        package_directory = manifest_path.parent
        source = payload.get("instruction_source")
        if not isinstance(source, dict) or source.get("kind") != "public_package":
            raise PromptWorkbenchCatalogError("Built-in SkillProfile must use a public package instruction source.")
        reference = _require_text(source.get("reference"), "instruction_source.reference", manifest_path)
        instruction_path = resolve_package_file(package_directory, reference)
        try:
            instruction_text = instruction_path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError) as error:
            raise PromptWorkbenchCatalogError("Built-in SkillProfile instruction source cannot be read.") from error
        if not instruction_text:
            raise PromptWorkbenchCatalogError("Built-in SkillProfile instruction source cannot be empty.")
        capabilities = payload.get("required_capabilities")
        if not isinstance(capabilities, list) or not all(isinstance(item, str) and item for item in capabilities):
            raise PromptWorkbenchCatalogError("Built-in SkillProfile requires capability IDs.")
        return BuiltInSkill(
            id=_require_text(payload.get("id"), "id", manifest_path),
            display_name=_require_text(payload.get("display_name"), "display_name", manifest_path),
            description=_require_text(payload.get("description"), "description", manifest_path),
            instruction_text=instruction_text,
            required_capabilities=tuple(capabilities),
        )

    @staticmethod
    def _load_workflow(manifest_path: Path) -> BuiltInWorkflow:
        payload = _read_json(manifest_path)
        if payload.get("contract_type") != "prompt_workflow_profile":
            raise PromptWorkbenchCatalogError("Built-in workflow manifest must be a PromptWorkflowProfile.")
        supported_modes = payload.get("supported_modes")
        if not isinstance(supported_modes, list) or set(supported_modes) != WORKFLOW_MODES:
            raise PromptWorkbenchCatalogError("Built-in workflow must support the four Prompt Workbench modes.")
        default_mode = _require_text(payload.get("default_mode"), "default_mode", manifest_path)
        if default_mode not in WORKFLOW_MODES:
            raise PromptWorkbenchCatalogError("Built-in workflow has an invalid default mode.")
        mode_instructions = payload.get("mode_instructions")
        if not isinstance(mode_instructions, dict) or set(mode_instructions) != WORKFLOW_MODES:
            raise PromptWorkbenchCatalogError("Built-in workflow must define instructions for each mode.")
        normalized_mode_instructions = {
            mode: _require_text(mode_instructions[mode], f"mode_instructions.{mode}", manifest_path)
            for mode in sorted(WORKFLOW_MODES)
        }
        declarations = payload.get("knowledge_sources")
        references = payload.get("knowledge_source_references")
        if not isinstance(declarations, list) or not isinstance(references, list):
            raise PromptWorkbenchCatalogError("Built-in workflow requires declared knowledge sources.")
        knowledge_sources: list[KnowledgeSourceDeclaration] = []
        source_ids: set[str] = set()
        for source in declarations:
            if not isinstance(source, dict):
                raise PromptWorkbenchCatalogError("A built-in knowledge declaration must be an object.")
            source_id = _require_text(source.get("id"), "knowledge source id", manifest_path)
            if source_id in source_ids:
                raise PromptWorkbenchCatalogError("Built-in knowledge source IDs must be unique.")
            source_ids.add(source_id)
            source_kind = _require_text(source.get("source_kind"), "knowledge source kind", manifest_path)
            if source_kind != "built_in":
                raise PromptWorkbenchCatalogError("Built-in workflow knowledge sources must be built_in.")
            reference = _require_text(source.get("reference"), "knowledge source reference", manifest_path)
            resolve_package_file(manifest_path.parent, reference)
            stability = _require_text(source.get("stability"), "knowledge source stability", manifest_path)
            if stability not in {"stable", "snapshot", "append_only", "dynamic"}:
                raise PromptWorkbenchCatalogError("Built-in knowledge source has an invalid stability value.")
            token_budget = source.get("token_budget")
            if token_budget is not None and (isinstance(token_budget, bool) or not isinstance(token_budget, int) or token_budget < 1):
                raise PromptWorkbenchCatalogError("Built-in knowledge token_budget must be a positive integer.")
            knowledge_sources.append(
                KnowledgeSourceDeclaration(
                    id=source_id,
                    label=_require_text(source.get("label"), "knowledge source label", manifest_path),
                    source_kind=source_kind,
                    reference=reference,
                    stability=stability,
                    token_budget=token_budget,
                )
            )
        if references != [source.id for source in knowledge_sources]:
            raise PromptWorkbenchCatalogError("Workflow knowledge source references must retain the declared order.")
        private_namespace = _require_text(payload.get("private_knowledge_namespace"), "private_knowledge_namespace", manifest_path)
        namespace_parts = private_namespace.split("/")
        if any(not part or part in {".", ".."} for part in namespace_parts):
            raise PromptWorkbenchCatalogError("Private knowledge namespace is invalid.")
        return BuiltInWorkflow(
            id=_require_text(payload.get("id"), "id", manifest_path),
            display_name=_require_text(payload.get("display_name"), "display_name", manifest_path),
            model_family=_require_text(payload.get("model_family"), "model_family", manifest_path),
            skill_profile_id=_require_text(payload.get("skill_profile_id"), "skill_profile_id", manifest_path),
            supported_modes=tuple(supported_modes),
            default_mode=default_mode,
            workflow_instructions=_require_text(payload.get("workflow_instructions"), "workflow_instructions", manifest_path),
            mode_instructions=normalized_mode_instructions,
            knowledge_sources=tuple(knowledge_sources),
            private_knowledge_namespace=private_namespace,
            package_directory=manifest_path.parent,
        )

    def list_workflows(self) -> tuple[BuiltInWorkflow, ...]:
        return tuple(self._workflows[key] for key in sorted(self._workflows))

    def get_workflow(self, workflow_id: str) -> BuiltInWorkflow:
        try:
            return self._workflows[workflow_id]
        except KeyError as error:
            raise PromptWorkbenchCatalogError("The requested Prompt Workbench workflow is not available.") from error

    def get_skill(self, skill_id: str) -> BuiltInSkill:
        try:
            return self._skills[skill_id]
        except KeyError as error:
            raise PromptWorkbenchCatalogError("The requested Prompt Workbench skill is not available.") from error
