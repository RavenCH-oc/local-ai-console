"""HTTP tests for the minimal local Control API."""

from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from local_ai_console_control.main import create_app
from local_ai_console_control.config.runtime_paths import RuntimeHomeInsideRepositoryError
from local_ai_console_control.version import __version__


class SystemEndpointTests(unittest.TestCase):
    def create_client(self, temporary_directory: Path) -> TestClient:
        repository = temporary_directory / "repository"
        repository.mkdir()
        runtime_root = temporary_directory / "controller-runtime"
        app = create_app(
            repository_root=repository,
            environ={
                "LOCAL_AI_CONSOLE_HOME": str(runtime_root),
                "TEST_ONLY_SECRET": "not-exported",
            },
            platform_name="non_windows",
        )
        return TestClient(app)

    def test_health_and_version_endpoints(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            with self.create_client(Path(temporary_directory)) as client:
                health_response = client.get("/health")
                version_response = client.get("/version")

            self.assertEqual(health_response.status_code, 200)
            self.assertEqual(
                health_response.json(),
                {"status": "ok", "service": "control-api", "version": __version__},
            )
            self.assertEqual(version_response.status_code, 200)
            self.assertEqual(version_response.json()["application"], "Local AI Console")
            self.assertEqual(version_response.json()["service"], "control-api")
            self.assertEqual(version_response.json()["version"], __version__)

    def test_runtime_info_is_initialized_and_does_not_dump_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            with self.create_client(temporary_path) as client:
                response = client.get("/runtime/info")

            body = response.json()
            self.assertEqual(response.status_code, 200)
            self.assertTrue(body["initialized"])
            self.assertEqual(body["source"], "environment_override")
            self.assertNotIn("environment", body)
            self.assertNotIn("credentials", body)
            self.assertNotIn("not-exported", str(body))
            self.assertEqual(set(body["paths"]), {"config", "data", "prompts", "knowledge", "logs", "cache", "backups"})

    def test_invalid_runtime_configuration_fails_at_startup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            repository = temporary_path / "repository"
            repository.mkdir()
            app = create_app(
                repository_root=repository,
                environ={"LOCAL_AI_CONSOLE_HOME": str(repository / "runtime")},
                platform_name="non_windows",
            )

            with self.assertRaises(RuntimeHomeInsideRepositoryError):
                with TestClient(app):
                    pass
