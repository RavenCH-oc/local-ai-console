"""Migration and HTTP coverage for private Prompt Workbench persistence."""

from __future__ import annotations

from contextlib import contextmanager
import tempfile
from pathlib import Path
import unittest

from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text

from local_ai_console_control.config.runtime_paths import initialize_runtime_layout, resolve_runtime_paths
from local_ai_console_control.main import create_app
from local_ai_console_control.persistence.models import PromptProject
from local_ai_console_control.persistence.database import (
    DatabaseSchemaError,
    database_path_for_runtime_data,
    database_url,
    migration_config,
    open_database,
    upgrade_database,
    validate_database_schema,
)


class PromptWorkbenchTestCase(unittest.TestCase):
    def prepare_runtime(self, temporary_directory: Path) -> tuple[Path, dict[str, str]]:
        repository = temporary_directory / "repository"
        repository.mkdir()
        runtime_root = temporary_directory / "controller-runtime"
        environ = {"LOCAL_AI_CONSOLE_HOME": str(runtime_root)}
        runtime_paths = resolve_runtime_paths(
            repository_root=repository,
            environ=environ,
            platform_name="non_windows",
        )
        initialize_runtime_layout(runtime_paths)
        upgrade_database(database_path_for_runtime_data(runtime_paths.data))
        return repository, environ

    @contextmanager
    def client(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            repository, environ = self.prepare_runtime(temporary_path)
            app = create_app(repository_root=repository, environ=environ, platform_name="non_windows")
            with TestClient(app) as client:
                yield client

    def create_project(self, client: TestClient, title: str = "Sanitized Test Project") -> dict[str, object]:
        response = client.post("/api/prompt-projects", json={"title": title})
        self.assertEqual(response.status_code, 201)
        return response.json()


class MigrationLifecycleTests(PromptWorkbenchTestCase):
    def test_fresh_migration_creates_and_validates_the_private_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            repository = temporary_path / "repository"
            repository.mkdir()
            runtime_paths = resolve_runtime_paths(
                repository_root=repository,
                environ={"LOCAL_AI_CONSOLE_HOME": str(temporary_path / "controller-runtime")},
                platform_name="non_windows",
            )
            initialize_runtime_layout(runtime_paths)
            database_path = database_path_for_runtime_data(runtime_paths.data)

            upgrade_database(database_path)
            validate_database_schema(database_path)
            database = open_database(database_path)
            try:
                self.assertEqual(
                    set(inspect(database.engine).get_table_names()),
                    {
                        "alembic_version",
                        "prompt_messages",
                        "prompt_project_states",
                        "prompt_projects",
                        "prompt_revisions",
                        "prompt_sessions",
                    },
                )
            finally:
                database.dispose()

    def test_upgrade_from_phase_1a_preserves_project_and_assigns_builtin_workflow_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            database_path = temporary_path / "console.sqlite3"
            config = migration_config(database_path)
            command.upgrade(config, "20260901_01")
            engine = create_engine(database_url(database_path))
            try:
                with engine.begin() as connection:
                    connection.execute(
                        text(
                            "INSERT INTO prompt_projects "
                            "(id, title, workflow_profile_id, created_at, updated_at, status) "
                            "VALUES (:id, :title, :workflow, :created_at, :updated_at, :status)"
                        ),
                        {
                            "id": "pp_legacy_project",
                            "title": "Legacy project",
                            "workflow": "example_image_prompt_workflow",
                            "created_at": "2026-09-01 00:00:00",
                            "updated_at": "2026-09-01 00:00:00",
                            "status": "active",
                        },
                    )
            finally:
                engine.dispose()

            command.upgrade(config, "head")
            database = open_database(database_path)
            try:
                with database.session_factory() as session:
                    project = session.get(PromptProject, "pp_legacy_project")
                    assert project is not None
                    self.assertEqual(project.workflow_profile_id, "anima_base_v1")
                    self.assertEqual(project.workflow_mode, "balanced")
            finally:
                database.dispose()

    def test_application_rejects_an_unmigrated_database_without_recreating_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            repository = temporary_path / "repository"
            repository.mkdir()
            runtime_root = temporary_path / "controller-runtime"
            app = create_app(
                repository_root=repository,
                environ={"LOCAL_AI_CONSOLE_HOME": str(runtime_root)},
                platform_name="non_windows",
            )

            with self.assertRaises(DatabaseSchemaError):
                with TestClient(app):
                    pass
            self.assertFalse((runtime_root / "data" / "console.sqlite3").exists())


class PromptWorkbenchEndpointTests(PromptWorkbenchTestCase):
    def test_project_session_message_state_archive_and_reload_persistence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            repository, environ = self.prepare_runtime(temporary_path)
            app = create_app(repository_root=repository, environ=environ, platform_name="non_windows")

            with TestClient(app) as client:
                project = self.create_project(client, "Reusable generic study")
                project_id = project["id"]
                initial_session_id = project["active_session_id"]
                self.assertEqual(project["workflow_profile_id"], "anima_base_v1")
                self.assertEqual(project["workflow_mode"], "balanced")

                workflows_response = client.get("/api/prompt-workflows")
                self.assertEqual(workflows_response.status_code, 200)
                workflow = workflows_response.json()[0]
                self.assertEqual(workflow["id"], "anima_base_v1")
                self.assertEqual(workflow["supported_modes"], ["stable", "balanced", "detailed", "preserve"])
                self.assertEqual([item["label"] for item in workflow["knowledge_sources"]], [
                    "Fundamentals",
                    "Prompt Structure",
                    "Composition and Pose",
                    "Anatomy Stability",
                    "Parameters",
                ])

                workflow_update = client.patch(
                    f"/api/prompt-projects/{project_id}/workflow",
                    json={"workflow_profile_id": "anima_base_v1", "workflow_mode": "preserve"},
                )
                self.assertEqual(workflow_update.status_code, 200)
                self.assertEqual(workflow_update.json()["workflow_mode"], "preserve")

                rename_response = client.patch(
                    f"/api/prompt-projects/{project_id}", json={"title": "Renamed generic study"}
                )
                self.assertEqual(rename_response.status_code, 200)
                self.assertEqual(rename_response.json()["title"], "Renamed generic study")

                state_payload = {
                    "objective": "Capture a sanitized workflow objective.",
                    "important_constraints": ["Keep examples public-safe."],
                    "must_preserve": ["Readable composition"],
                    "known_problems": ["No generator is connected."],
                    "accepted_observations": ["Manual revisions remain useful."],
                }
                state_response = client.put(f"/api/prompt-projects/{project_id}/state", json=state_payload)
                self.assertEqual(state_response.status_code, 200)
                self.assertEqual(state_response.json()["must_preserve"], ["Readable composition"])

                message_response = client.post(
                    f"/api/prompt-sessions/{initial_session_id}/messages",
                    json={"role": "user", "content": "Record a manual discussion note."},
                )
                self.assertEqual(message_response.status_code, 201)

                preview_response = client.get(f"/api/prompt-projects/{project_id}/context-preview")
                self.assertEqual(preview_response.status_code, 200)
                preview = preview_response.json()
                self.assertEqual(preview["workflow_mode"], "preserve")
                self.assertEqual(preview["contributions"][0]["label"], "Base System")
                self.assertEqual(preview["contributions"][-1]["label"], "Current Request")
                self.assertIn("Knowledge source: Fundamentals", [item["label"] for item in preview["contributions"]])
                self.assertTrue(all(item["token_count"] is None for item in preview["contributions"]))

                session_response = client.post(
                    f"/api/prompt-projects/{project_id}/sessions", json={"title": "Alternative discussion"}
                )
                self.assertEqual(session_response.status_code, 201)
                self.assertEqual(session_response.json()["project_id"], project_id)
                sessions_response = client.get(f"/api/prompt-projects/{project_id}/sessions")
                self.assertEqual(len(sessions_response.json()), 2)

            reloaded_app = create_app(repository_root=repository, environ=environ, platform_name="non_windows")
            with TestClient(reloaded_app) as reloaded_client:
                projects_response = reloaded_client.get("/api/prompt-projects")
                self.assertEqual(projects_response.status_code, 200)
                self.assertEqual(projects_response.json()[0]["title"], "Renamed generic study")
                messages_response = reloaded_client.get(f"/api/prompt-sessions/{initial_session_id}/messages")
                self.assertEqual([item["content"] for item in messages_response.json()], ["Record a manual discussion note."])
                state_response = reloaded_client.get(f"/api/prompt-projects/{project_id}/state")
                self.assertEqual(state_response.json()["objective"], state_payload["objective"])
                self.assertEqual(reloaded_client.get(f"/api/prompt-projects/{project_id}").json()["workflow_mode"], "preserve")

                archive_response = reloaded_client.post(f"/api/prompt-projects/{project_id}/archive")
                self.assertEqual(archive_response.status_code, 200)
                self.assertEqual(archive_response.json()["status"], "archived")
                self.assertEqual(reloaded_client.get("/api/prompt-projects").json(), [])
                self.assertEqual(
                    reloaded_client.get("/api/prompt-projects?include_archived=true").json()[0]["status"],
                    "archived",
                )

    def test_revision_lifecycle_lineage_and_raw_message_retention(self) -> None:
        with self.client() as client:
            project = self.create_project(client)
            project_id = project["id"]
            session_id = project["active_session_id"]
            client.post(
                f"/api/prompt-sessions/{session_id}/messages",
                json={"role": "user", "content": "Keep this raw note after revision actions."},
            )

            first = client.post(
                f"/api/prompt-projects/{project_id}/revisions",
                json={
                    "positive_prompt": "generic subject, clear composition",
                    "negative_prompt": "unwanted artifacts",
                    "parameters": {"width": 1024, "height": 1024},
                    "change_log": "Initial manual proposal.",
                },
            )
            self.assertEqual(first.status_code, 201)
            first_revision = first.json()
            accepted_first = client.post(f"/api/prompt-revisions/{first_revision['id']}/accept")
            self.assertEqual(accepted_first.status_code, 200)
            self.assertEqual(accepted_first.json()["status"], "accepted")

            discarded = client.post(
                f"/api/prompt-projects/{project_id}/revisions",
                json={
                    "parent_revision_id": first_revision["id"],
                    "positive_prompt": "alternative generic subject",
                    "negative_prompt": "unwanted artifacts",
                    "parameters": {},
                    "change_log": "Alternative proposal to discard.",
                },
            ).json()
            self.assertEqual(client.post(f"/api/prompt-revisions/{discarded['id']}/discard").json()["status"], "discarded")

            accepted_second = client.post(
                f"/api/prompt-projects/{project_id}/revisions",
                json={
                    "parent_revision_id": first_revision["id"],
                    "positive_prompt": "refined generic subject",
                    "negative_prompt": "unwanted artifacts",
                    "parameters": {"steps": 24},
                    "change_log": "Refined manual proposal.",
                },
            ).json()
            self.assertEqual(client.post(f"/api/prompt-revisions/{accepted_second['id']}/accept").status_code, 200)

            project_response = client.get(f"/api/prompt-projects/{project_id}")
            self.assertEqual(project_response.json()["current_revision_id"], accepted_second["id"])
            revisions_response = client.get(f"/api/prompt-projects/{project_id}/revisions")
            self.assertEqual(
                [(item["id"], item["status"]) for item in revisions_response.json()],
                [
                    (first_revision["id"], "accepted"),
                    (discarded["id"], "discarded"),
                    (accepted_second["id"], "accepted"),
                ],
            )
            self.assertEqual(
                client.get(f"/api/prompt-sessions/{session_id}/messages").json()[0]["content"],
                "Keep this raw note after revision actions.",
            )

    def test_validation_missing_resources_cross_project_parent_and_invalid_transitions(self) -> None:
        with self.client() as client:
            self.assertEqual(client.post("/api/prompt-projects", json={"title": "   "}).status_code, 422)
            self.assertEqual(
                client.post(
                    "/api/prompt-projects",
                    json={"title": "Unknown workflow", "workflow_profile_id": "missing_workflow", "workflow_mode": "balanced"},
                ).status_code,
                422,
            )
            self.assertEqual(client.get("/api/prompt-projects/missing").status_code, 404)
            self.assertEqual(client.get("/api/prompt-sessions/missing/messages").status_code, 404)

            first_project = self.create_project(client, "First project")
            second_project = self.create_project(client, "Second project")
            self.assertEqual(
                client.post(
                    f"/api/prompt-sessions/{first_project['active_session_id']}/messages",
                    json={"role": "invalid", "content": "This must be rejected."},
                ).status_code,
                422,
            )

            first_revision = client.post(
                f"/api/prompt-projects/{first_project['id']}/revisions",
                json={
                    "positive_prompt": "first generic prompt",
                    "change_log": "First proposal.",
                },
            ).json()
            self.assertEqual(
                client.post(
                    f"/api/prompt-projects/{second_project['id']}/revisions",
                    json={
                        "parent_revision_id": first_revision["id"],
                        "positive_prompt": "cross-project proposal",
                        "change_log": "Must be rejected.",
                    },
                ).status_code,
                409,
            )
            self.assertEqual(
                client.post(
                    f"/api/prompt-projects/{second_project['id']}/revisions",
                    json={
                        "parent_revision_id": "missing_revision",
                        "positive_prompt": "missing parent proposal",
                        "change_log": "Must be rejected.",
                    },
                ).status_code,
                404,
            )

            discarded = client.post(
                f"/api/prompt-projects/{first_project['id']}/revisions",
                json={"positive_prompt": "discarded prompt", "change_log": "Discard first."},
            ).json()
            self.assertEqual(client.post(f"/api/prompt-revisions/{discarded['id']}/discard").status_code, 200)
            self.assertEqual(client.post(f"/api/prompt-revisions/{discarded['id']}/accept").status_code, 409)

            self.assertEqual(client.post(f"/api/prompt-revisions/{first_revision['id']}/accept").status_code, 200)
            self.assertEqual(client.post(f"/api/prompt-revisions/{first_revision['id']}/discard").status_code, 409)


if __name__ == "__main__":
    unittest.main()
