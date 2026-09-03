"""Bounded built-in and private-runtime knowledge loading for Prompt Workbench."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from local_ai_console_control.prompt_workbench.catalog import (
    BuiltInWorkflow,
    PromptWorkbenchCatalogError,
    resolve_package_file,
)


class KnowledgeSourceLoadError(ValueError):
    """Raised when a selected knowledge source is unsafe or cannot be read."""


@dataclass(frozen=True, slots=True)
class LoadedKnowledgeDocument:
    """Source-identified knowledge content without a local path in the public interface."""

    source_id: str
    label: str
    source_kind: str
    stability: str
    content: str
    token_budget: int | None


class KnowledgeSourceLoader:
    """Load declared built-ins plus optional private extensions under one safe root."""

    def __init__(self, *, private_knowledge_root: Path) -> None:
        self._private_knowledge_root = private_knowledge_root.resolve(strict=False)

    @staticmethod
    def _read_text(path: Path, *, error_message: str) -> str:
        try:
            content = path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError) as error:
            raise KnowledgeSourceLoadError(error_message) from error
        if not content:
            raise KnowledgeSourceLoadError(error_message)
        return content

    def load_for_workflow(self, workflow: BuiltInWorkflow) -> tuple[LoadedKnowledgeDocument, ...]:
        built_in_documents: list[LoadedKnowledgeDocument] = []
        for source in workflow.knowledge_sources:
            try:
                path = resolve_package_file(workflow.package_directory, source.reference)
            except PromptWorkbenchCatalogError as error:
                raise KnowledgeSourceLoadError("A declared built-in knowledge source is unsafe or missing.") from error
            built_in_documents.append(
                LoadedKnowledgeDocument(
                    source_id=source.id,
                    label=source.label,
                    source_kind="built_in",
                    stability=source.stability,
                    content=self._read_text(path, error_message="A built-in knowledge source cannot be read."),
                    token_budget=source.token_budget,
                )
            )
        return tuple(built_in_documents + self._load_private_extensions(workflow.private_knowledge_namespace))

    def _load_private_extensions(self, namespace: str) -> list[LoadedKnowledgeDocument]:
        namespace_parts = namespace.split("/")
        if any(not part or part in {".", ".."} for part in namespace_parts):
            raise KnowledgeSourceLoadError("Private knowledge namespace is invalid.")
        candidate_directory = (self._private_knowledge_root.joinpath(*namespace_parts)).resolve(strict=False)
        try:
            candidate_directory.relative_to(self._private_knowledge_root)
        except ValueError as error:
            raise KnowledgeSourceLoadError("Private knowledge namespace escapes the runtime knowledge root.") from error
        if not candidate_directory.exists():
            return []
        if not candidate_directory.is_dir():
            raise KnowledgeSourceLoadError("Private knowledge extension location is not a directory.")
        private_paths = sorted(
            (path for path in candidate_directory.iterdir() if path.is_file() and path.suffix.casefold() in {".md", ".txt"}),
            key=lambda path: path.name.casefold(),
        )
        documents: list[LoadedKnowledgeDocument] = []
        for index, path in enumerate(private_paths, start=1):
            documents.append(
                LoadedKnowledgeDocument(
                    source_id=f"private_extension_{index:03d}",
                    label=f"Private knowledge extension {index}",
                    source_kind="private_runtime",
                    stability="snapshot",
                    content=self._read_text(path, error_message="A private knowledge extension cannot be read."),
                    token_budget=None,
                )
            )
        return documents
