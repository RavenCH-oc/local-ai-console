"""Controller Runtime path resolution and layout initialization."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import os
from pathlib import Path
from typing import Mapping


RUNTIME_HOME_ENVIRONMENT_VARIABLE = "LOCAL_AI_CONSOLE_HOME"
RUNTIME_DIRECTORY_NAMES = (
    "config",
    "data",
    "prompts",
    "knowledge",
    "logs",
    "cache",
    "backups",
)


class RuntimePathConfigurationError(ValueError):
    """Raised when the Controller Runtime root cannot be configured safely."""


class RelativeRuntimeHomeError(RuntimePathConfigurationError):
    """Raised when LOCAL_AI_CONSOLE_HOME is not absolute."""


class MissingWindowsLocalAppDataError(RuntimePathConfigurationError):
    """Raised when the Windows default cannot be determined."""


class RuntimeHomeInsideRepositoryError(RuntimePathConfigurationError):
    """Raised when a runtime root resolves to the Repository or a descendant."""


class RuntimeInitializationError(RuntimeError):
    """Raised when the runtime directory layout cannot be initialized."""


class RuntimeHomeSource(str, Enum):
    """How the Controller Runtime root was selected."""

    ENVIRONMENT_OVERRIDE = "environment_override"
    WINDOWS_DEFAULT = "windows_default"


@dataclass(frozen=True, slots=True)
class RuntimePaths:
    """Resolved Controller Runtime root and its canonical private layout."""

    root: Path
    source: RuntimeHomeSource
    config: Path
    data: Path
    prompts: Path
    knowledge: Path
    logs: Path
    cache: Path
    backups: Path

    @property
    def layout_directories(self) -> tuple[Path, ...]:
        """Return the required private directories, excluding the root itself."""

        return (
            self.config,
            self.data,
            self.prompts,
            self.knowledge,
            self.logs,
            self.cache,
            self.backups,
        )

    @property
    def is_initialized(self) -> bool:
        """Whether every required runtime directory currently exists."""

        return self.root.is_dir() and all(path.is_dir() for path in self.layout_directories)

    @classmethod
    def from_root(cls, root: Path, source: RuntimeHomeSource) -> "RuntimePaths":
        """Build the fixed Phase 0B runtime layout from a resolved root."""

        return cls(
            root=root,
            source=source,
            config=root / "config",
            data=root / "data",
            prompts=root / "prompts",
            knowledge=root / "knowledge",
            logs=root / "logs",
            cache=root / "cache",
            backups=root / "backups",
        )


def find_repository_root(start_path: Path | None = None) -> Path:
    """Find this source repository without relying on a current working directory."""

    search_start = (start_path or Path(__file__)).resolve()
    for candidate in (search_start, *search_start.parents):
        if (candidate / ".git").exists() and (candidate / "AGENTS.md").is_file():
            return candidate.resolve()
    raise RuntimePathConfigurationError("Unable to determine the Local AI Console repository root.")


def is_repository_contained_path(
    candidate: Path,
    repository_root: Path,
    *,
    windows_case_insensitive: bool,
) -> bool:
    """Return whether a canonical path is the Repository or one of its descendants."""

    canonical_candidate = candidate.resolve(strict=False)
    canonical_repository = repository_root.resolve(strict=False)
    candidate_parts = canonical_candidate.parts
    repository_parts = canonical_repository.parts

    if windows_case_insensitive:
        candidate_parts = tuple(part.casefold() for part in candidate_parts)
        repository_parts = tuple(part.casefold() for part in repository_parts)

    return len(candidate_parts) >= len(repository_parts) and candidate_parts[: len(repository_parts)] == repository_parts


def resolve_runtime_paths(
    *,
    repository_root: Path | str | None = None,
    environ: Mapping[str, str] | None = None,
    platform_name: str | None = None,
    local_appdata: Path | str | None = None,
) -> RuntimePaths:
    """Resolve a safe Controller Runtime root without creating any directories."""

    environment = os.environ if environ is None else environ
    is_windows = (platform_name or ("windows" if os.name == "nt" else "non_windows")).casefold() == "windows"
    source_repository = Path(repository_root) if repository_root is not None else find_repository_root()
    canonical_repository = source_repository.resolve(strict=False)
    override = environment.get(RUNTIME_HOME_ENVIRONMENT_VARIABLE, "").strip()

    if override:
        try:
            runtime_root = Path(override).expanduser()
        except (OSError, ValueError) as error:
            raise RuntimePathConfigurationError("LOCAL_AI_CONSOLE_HOME is not a valid path.") from error
        if not runtime_root.is_absolute():
            raise RelativeRuntimeHomeError("LOCAL_AI_CONSOLE_HOME must be an absolute path.")
        source = RuntimeHomeSource.ENVIRONMENT_OVERRIDE
    else:
        if not is_windows:
            raise RuntimePathConfigurationError(
                "LOCAL_AI_CONSOLE_HOME must be set for non-Windows Controller development or tests."
            )
        local_appdata_value = local_appdata if local_appdata is not None else environment.get("LOCALAPPDATA", "").strip()
        if not local_appdata_value:
            raise MissingWindowsLocalAppDataError(
                "LOCALAPPDATA is required to determine the Windows Controller Runtime root."
            )
        try:
            runtime_root = Path(local_appdata_value).expanduser() / "LocalAIConsole"
        except (OSError, ValueError) as error:
            raise RuntimePathConfigurationError("LOCALAPPDATA is not a valid path.") from error
        if not runtime_root.is_absolute():
            raise RuntimePathConfigurationError("LOCALAPPDATA must resolve to an absolute path.")
        source = RuntimeHomeSource.WINDOWS_DEFAULT

    try:
        canonical_runtime_root = runtime_root.resolve(strict=False)
    except OSError as error:
        raise RuntimePathConfigurationError("Unable to resolve the Controller Runtime root.") from error

    if is_repository_contained_path(
        canonical_runtime_root,
        canonical_repository,
        windows_case_insensitive=is_windows,
    ):
        raise RuntimeHomeInsideRepositoryError(
            "Controller Runtime root must not be the source repository or a directory inside it."
        )

    return RuntimePaths.from_root(canonical_runtime_root, source)


def initialize_runtime_layout(paths: RuntimePaths) -> None:
    """Create the fixed runtime layout without writing private content or configuration."""

    try:
        paths.root.mkdir(parents=True, exist_ok=True)
        for directory in paths.layout_directories:
            directory.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise RuntimeInitializationError("Unable to initialize the Controller Runtime directory layout.") from error
