"""Tests for Controller Runtime resolution and initialization."""

from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from local_ai_console_control.config.runtime_paths import (
    MissingWindowsLocalAppDataError,
    RelativeRuntimeHomeError,
    RuntimeHomeInsideRepositoryError,
    RuntimeHomeSource,
    initialize_runtime_layout,
    is_repository_contained_path,
    resolve_runtime_paths,
)


class RuntimePathTests(unittest.TestCase):
    def make_repository(self, temporary_directory: Path) -> Path:
        repository = temporary_directory / "repository"
        repository.mkdir()
        return repository

    def test_absolute_override_is_resolved_and_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            paths = resolve_runtime_paths(
                repository_root=self.make_repository(temporary_path),
                environ={"LOCAL_AI_CONSOLE_HOME": str(temporary_path / "controller-runtime")},
                platform_name="non_windows",
            )

            self.assertEqual(paths.source, RuntimeHomeSource.ENVIRONMENT_OVERRIDE)
            self.assertEqual(paths.root, (temporary_path / "controller-runtime").resolve())

    def test_relative_override_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            with self.assertRaises(RelativeRuntimeHomeError):
                resolve_runtime_paths(
                    repository_root=self.make_repository(Path(temporary_directory)),
                    environ={"LOCAL_AI_CONSOLE_HOME": "relative-runtime"},
                    platform_name="non_windows",
                )

    def test_windows_default_layout_uses_localappdata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            paths = resolve_runtime_paths(
                repository_root=self.make_repository(temporary_path),
                environ={"LOCALAPPDATA": str(temporary_path / "appdata")},
                platform_name="windows",
            )

            self.assertEqual(paths.source, RuntimeHomeSource.WINDOWS_DEFAULT)
            self.assertEqual(paths.root, (temporary_path / "appdata" / "LocalAIConsole").resolve())

    def test_missing_windows_localappdata_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            with self.assertRaises(MissingWindowsLocalAppDataError):
                resolve_runtime_paths(
                    repository_root=self.make_repository(Path(temporary_directory)),
                    environ={},
                    platform_name="windows",
                )

    def test_repository_root_and_child_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = self.make_repository(Path(temporary_directory))
            for unsafe_path in (repository, repository / "runtime"):
                with self.subTest(unsafe_path=unsafe_path):
                    with self.assertRaises(RuntimeHomeInsideRepositoryError):
                        resolve_runtime_paths(
                            repository_root=repository,
                            environ={"LOCAL_AI_CONSOLE_HOME": str(unsafe_path)},
                            platform_name="non_windows",
                        )

    def test_sibling_and_normalized_external_paths_are_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            repository = self.make_repository(temporary_path)
            sibling_runtime = temporary_path / "controller-runtime"
            paths = resolve_runtime_paths(
                repository_root=repository,
                environ={"LOCAL_AI_CONSOLE_HOME": str(sibling_runtime / "nested" / "..")},
                platform_name="non_windows",
            )

            self.assertEqual(paths.root, sibling_runtime.resolve())

    def test_normalization_cannot_bypass_repository_guard(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = self.make_repository(Path(temporary_directory))
            unsafe_path = repository / "safe-looking" / ".." / "runtime"
            with self.assertRaises(RuntimeHomeInsideRepositoryError):
                resolve_runtime_paths(
                    repository_root=repository,
                    environ={"LOCAL_AI_CONSOLE_HOME": str(unsafe_path)},
                    platform_name="non_windows",
                )

    def test_windows_case_insensitive_repository_comparison_is_injectable(self) -> None:
        self.assertTrue(
            is_repository_contained_path(
                Path("/ExampleRepository/runtime"),
                Path("/examplerepository"),
                windows_case_insensitive=True,
            )
        )

    def test_initialization_creates_the_fixed_layout_idempotently(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            paths = resolve_runtime_paths(
                repository_root=self.make_repository(temporary_path),
                environ={"LOCAL_AI_CONSOLE_HOME": str(temporary_path / "controller-runtime")},
                platform_name="non_windows",
            )

            initialize_runtime_layout(paths)
            initialize_runtime_layout(paths)

            self.assertTrue(paths.is_initialized)
            self.assertEqual(
                {directory.name for directory in paths.layout_directories},
                {"config", "data", "prompts", "knowledge", "logs", "cache", "backups"},
            )
