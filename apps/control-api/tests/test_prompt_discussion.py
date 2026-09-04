"""Fake-transport coverage for the Phase 1C-1 Prompt Workbench discussion flow."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient

from local_ai_console_control.config.runtime_paths import initialize_runtime_layout, resolve_runtime_paths
from local_ai_console_control.llm.llama_cpp import LlamaCppClientError, LlamaCppClientErrorKind
from local_ai_console_control.llm.resolver import TaskRuntimeResolver
from local_ai_console_control.llm.service import LLMService
from local_ai_console_control.llm.types import (
    LLMGenerationRequest,
    LLMRuntimeCapabilities,
    LLMStreamEvent,
    LLMStreamEventKind,
    LLMTokenCountResult,
    LLMUsage,
    RuntimeSlot,
    RuntimeTargetPreference,
    TaskKind,
)
from local_ai_console_control.main import create_app
from local_ai_console_control.persistence.database import database_path_for_runtime_data, upgrade_database
from local_ai_console_control.persistence.service import create_project, list_messages
from local_ai_console_control.prompt_workbench.discussion import (
    PromptDiscussionBusyError,
    PromptDiscussionError,
    PromptDiscussionPrepareStage,
    PromptDiscussionService,
)
from local_ai_console_control.prompt_workbench.knowledge import KnowledgeSourceLoader


class FakeDiscussionClient:
    """A finite fake provider; no test ever contacts a configured private runtime."""

    def __init__(
        self,
        *,
        events: list[LLMStreamEvent],
        input_tokens: int = 128,
        count_error: Exception | None = None,
    ) -> None:
        self.events = events
        self.input_tokens = input_tokens
        self.count_error = count_error
        self.count_requests: list[LLMGenerationRequest] = []
        self.stream_requests: list[LLMGenerationRequest] = []

    @property
    def capabilities(self) -> LLMRuntimeCapabilities:
        return LLMRuntimeCapabilities()

    async def generate(self, request: LLMGenerationRequest):  # pragma: no cover - the discussion path streams only.
        raise AssertionError("Prompt discussion must not call non-stream generation.")

    async def count_input_tokens(self, request: LLMGenerationRequest) -> LLMTokenCountResult:
        self.count_requests.append(request)
        if self.count_error is not None:
            raise self.count_error
        return LLMTokenCountResult(input_tokens=self.input_tokens, provider_metadata={"provider": "llama_cpp"})

    def stream_generate(self, request: LLMGenerationRequest):
        self.stream_requests.append(request)

        async def events():
            for event in self.events:
                yield event

        return events()

    async def end_reasoning(self, completion_id: str) -> None:  # pragma: no cover - not exposed in this phase.
        raise AssertionError("Prompt discussion Stop must cancel the stream, not end reasoning only.")


def service_for(client: FakeDiscussionClient) -> LLMService:
    return LLMService(resolver=TaskRuntimeResolver(), clients={RuntimeSlot.MAIN: client})


def parse_sse(body: str) -> list[tuple[str, dict[str, object]]]:
    import json

    events: list[tuple[str, dict[str, object]]] = []
    for block in body.replace("\r", "").split("\n\n"):
        if not block.strip():
            continue
        event = next((line[7:] for line in block.splitlines() if line.startswith("event: ")), "")
        data = next((line[6:] for line in block.splitlines() if line.startswith("data: ")), "")
        events.append((event, json.loads(data)))
    return events


class PromptDiscussionTestCase(unittest.TestCase):
    @contextmanager
    def client(self, fake_client: FakeDiscussionClient):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            repository = temporary_path / "repository"
            repository.mkdir()
            runtime_root = temporary_path / "controller-runtime"
            environ = {"LOCAL_AI_CONSOLE_HOME": str(runtime_root)}
            runtime_paths = resolve_runtime_paths(
                repository_root=repository,
                environ=environ,
                platform_name="non_windows",
            )
            initialize_runtime_layout(runtime_paths)
            upgrade_database(database_path_for_runtime_data(runtime_paths.data))
            app = create_app(
                repository_root=repository,
                environ=environ,
                platform_name="non_windows",
                llm_service=service_for(fake_client),
            )
            with TestClient(app) as test_client:
                yield test_client, app

    def create_project(self, client: TestClient) -> dict[str, object]:
        response = client.post("/api/prompt-projects", json={"title": "Sanitized discussion project"})
        self.assertEqual(response.status_code, 201)
        return response.json()

    def discussion_response(self, client: TestClient, session_id: str, content: str = "Discuss a sanitized prompt change."):
        return client.post(
            f"/api/prompt-sessions/{session_id}/discussion/stream",
            json={"content": content, "thinking_mode": "on"},
        )

    def test_successful_discussion_uses_authoritative_context_and_persists_only_visible_answer(self) -> None:
        fake = FakeDiscussionClient(
            events=[
                LLMStreamEvent(kind=LLMStreamEventKind.STARTED, provider_metadata={"provider": "llama_cpp"}),
                LLMStreamEvent(kind=LLMStreamEventKind.REASONING_DELTA, text="Consider the preserved traits."),
                LLMStreamEvent(kind=LLMStreamEventKind.TEXT_DELTA, text="Discuss the clothing change "),
                LLMStreamEvent(kind=LLMStreamEventKind.TEXT_DELTA, text="before proposing a revision."),
                LLMStreamEvent(
                    kind=LLMStreamEventKind.USAGE,
                    usage=LLMUsage(input_tokens=128, output_tokens=12, total_tokens=140),
                    provider_metadata={"provider": "llama_cpp", "timings": {"prompt_n": 128, "prompt_ms": 4.0}},
                ),
                LLMStreamEvent(
                    kind=LLMStreamEventKind.COMPLETED,
                    usage=LLMUsage(input_tokens=128, output_tokens=12, total_tokens=140),
                    provider_metadata={"provider": "llama_cpp", "timings": {"prompt_n": 128, "prompt_ms": 4.0}},
                    finish_reason="stop",
                ),
            ]
        )
        with self.client(fake) as (client, _):
            project = self.create_project(client)
            response = self.discussion_response(client, str(project["active_session_id"]))

            self.assertEqual(response.status_code, 200)
            events = parse_sse(response.text)
            self.assertEqual([event[0] for event in events], ["started", "reasoning_delta", "text_delta", "text_delta", "completed"])
            self.assertEqual(events[0][1]["input_tokens"], 128)
            self.assertEqual(events[-1][1]["finish_reason"], "stop")

            messages = client.get(f"/api/prompt-sessions/{project['active_session_id']}/messages").json()
            self.assertEqual([message["role"] for message in messages], ["user", "assistant"])
            self.assertEqual(messages[1]["content"], "Discuss the clothing change before proposing a revision.")
            generation = messages[1]["metadata"]["discussion_generation"]
            self.assertEqual(generation["reasoning_content"], "Consider the preserved traits.")
            self.assertEqual(generation["input_tokens"], 128)
            self.assertEqual(generation["reasoning_mode"], "on")
            self.assertNotIn("completion_id", generation)
            self.assertEqual(client.get(f"/api/prompt-projects/{project['id']}/revisions").json(), [])

        self.assertEqual(len(fake.count_requests), 1)
        self.assertEqual(len(fake.stream_requests), 1)
        request = fake.stream_requests[0]
        self.assertEqual(request.task_kind, TaskKind.PROMPT_GENERATION)
        self.assertEqual(request.target_preference, RuntimeTargetPreference.AUTO)
        self.assertEqual(request.messages[-1].content, "Discuss a sanitized prompt change.")
        self.assertEqual(sum(message.content == "Discuss a sanitized prompt change." for message in request.messages), 1)
        self.assertEqual(sum(message.role.value == "system" for message in request.messages), 1)
        self.assertIn("Prompt Workbench discussion phase", request.messages[0].content)
        self.assertIn("Knowledge source anima_base_v1_fundamentals", request.messages[0].content)
        self.assertIn("[Prompt Workbench contribution: Skill]", request.messages[0].content)

    def test_no_assistant_is_persisted_before_completion_or_after_cancellation(self) -> None:
        fake = FakeDiscussionClient(
            events=[
                LLMStreamEvent(kind=LLMStreamEventKind.STARTED),
                LLMStreamEvent(kind=LLMStreamEventKind.TEXT_DELTA, text="Incomplete visible text"),
                LLMStreamEvent(kind=LLMStreamEventKind.COMPLETED, finish_reason="stop"),
            ]
        )
        with self.client(fake) as (client, app):
            project = self.create_project(client)
            session_id = str(project["active_session_id"])
            database_session = app.state.database.session_factory()
            try:
                discussion = PromptDiscussionService(
                    llm_service=app.state.llm_service,
                    catalog=app.state.prompt_workbench_catalog,
                    knowledge_loader=KnowledgeSourceLoader(private_knowledge_root=app.state.runtime_paths.knowledge),
                    coordinator=app.state.prompt_discussion_coordinator,
                )

                async def cancel_after_first_delta() -> None:
                    prepared = await discussion.prepare(
                        database_session,
                        session_id=session_id,
                        user_content="Keep this raw user history.",
                        thinking_mode="auto",
                    )
                    stream = discussion.stream(database_session, prepared)
                    self.assertEqual((await anext(stream)).kind, "started")
                    self.assertEqual((await anext(stream)).kind, "text_delta")
                    with self.assertRaises(PromptDiscussionBusyError):
                        await discussion.prepare(
                            database_session,
                            session_id=session_id,
                            user_content="A duplicate request must not be queued.",
                            thinking_mode="auto",
                        )
                    self.assertEqual(
                        [message.role for message in list_messages(database_session, session_id=session_id)],
                        ["user"],
                    )
                    await stream.aclose()

                asyncio.run(cancel_after_first_delta())
                self.assertEqual(
                    [message.content for message in list_messages(database_session, session_id=session_id)],
                    ["Keep this raw user history."],
                )
            finally:
                database_session.close()

    def test_provider_failure_and_malformed_stream_keep_the_raw_user_turn_without_an_assistant(self) -> None:
        for error_code in ("provider_failure", "malformed_stream"):
            with self.subTest(error_code=error_code):
                fake = FakeDiscussionClient(events=[LLMStreamEvent(kind=LLMStreamEventKind.ERROR, error_code=error_code)])
                with self.client(fake) as (client, _):
                    project = self.create_project(client)
                    response = self.discussion_response(client, str(project["active_session_id"]))
                    events = parse_sse(response.text)
                    self.assertEqual(events[-1][0], "error")
                    self.assertEqual(events[-1][1]["code"], error_code)
                    messages = client.get(f"/api/prompt-sessions/{project['active_session_id']}/messages").json()
                    self.assertEqual([message["role"] for message in messages], ["user"])
                    self.assertEqual(client.get(f"/api/prompt-projects/{project['id']}/revisions").json(), [])

    def test_context_overflow_blocks_streaming_after_preserving_the_user_turn(self) -> None:
        fake = FakeDiscussionClient(events=[], input_tokens=98_304)
        with self.client(fake) as (client, _):
            project = self.create_project(client)
            response = self.discussion_response(client, str(project["active_session_id"]))
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.json()["detail"], "Prompt context is too large for the current runtime.")
            messages = client.get(f"/api/prompt-sessions/{project['active_session_id']}/messages").json()
            self.assertEqual([message["role"] for message in messages], ["user"])
        self.assertEqual(fake.stream_requests, [])

    def test_input_token_preflight_failure_has_a_safe_user_message_and_internal_classification(self) -> None:
        fake = FakeDiscussionClient(
            events=[],
            count_error=LlamaCppClientError(LlamaCppClientErrorKind.PROVIDER_FAILURE, http_status=400),
        )
        with self.client(fake) as (client, app):
            project = self.create_project(client)
            session_id = str(project["active_session_id"])
            response = self.discussion_response(client, session_id)
            self.assertEqual(response.status_code, 502)
            self.assertEqual(response.json()["detail"], "Input-token preflight failed.")
            self.assertNotIn("provider_failure", response.text)
            self.assertNotIn("400", response.text)
            messages = client.get(f"/api/prompt-sessions/{session_id}/messages").json()
            self.assertEqual([message["role"] for message in messages], ["user"])

            database_session = app.state.database.session_factory()
            try:
                async def prepare_again() -> PromptDiscussionError:
                    discussion = PromptDiscussionService(
                        llm_service=app.state.llm_service,
                        catalog=app.state.prompt_workbench_catalog,
                        knowledge_loader=KnowledgeSourceLoader(private_knowledge_root=app.state.runtime_paths.knowledge),
                        coordinator=app.state.prompt_discussion_coordinator,
                    )
                    with self.assertRaises(PromptDiscussionError) as raised:
                        await discussion.prepare(
                            database_session,
                            session_id=session_id,
                            user_content="A second sanitized request for diagnostic classification.",
                            thinking_mode="auto",
                        )
                    return raised.exception

                error = asyncio.run(prepare_again())
                self.assertEqual(error.code, "input_token_preflight_failed")
                self.assertIsNotNone(error.diagnostic)
                assert error.diagnostic is not None
                self.assertEqual(error.diagnostic.stage, PromptDiscussionPrepareStage.INPUT_TOKEN_PREFLIGHT)
                self.assertEqual(error.diagnostic.cause_type, "LlamaCppClientError")
                self.assertEqual(error.diagnostic.cause_category, "provider_failure")
                self.assertEqual(error.diagnostic.provider_http_status, 400)
                self.assertNotIn("A second sanitized request", str(error.diagnostic.safe_summary()))
            finally:
                database_session.close()

    def test_cancelled_provider_event_keeps_the_raw_user_turn_without_an_assistant(self) -> None:
        fake = FakeDiscussionClient(events=[LLMStreamEvent(kind=LLMStreamEventKind.ERROR, error_code="cancelled")])
        with self.client(fake) as (client, _):
            project = self.create_project(client)
            response = self.discussion_response(client, str(project["active_session_id"]))
            self.assertEqual([event[0] for event in parse_sse(response.text)], ["started", "cancelled"])
            messages = client.get(f"/api/prompt-sessions/{project['active_session_id']}/messages").json()
            self.assertEqual([message["role"] for message in messages], ["user"])
            self.assertEqual(client.get(f"/api/prompt-projects/{project['id']}/revisions").json(), [])

    def test_only_the_active_session_can_start_a_discussion(self) -> None:
        fake = FakeDiscussionClient(events=[])
        with self.client(fake) as (client, _):
            project = self.create_project(client)
            first_session_id = str(project["active_session_id"])
            second_session = client.post(f"/api/prompt-projects/{project['id']}/sessions", json={"title": "Current session"})
            self.assertEqual(second_session.status_code, 201)

            response = self.discussion_response(client, first_session_id)
            self.assertEqual(response.status_code, 409)
            self.assertEqual(client.get(f"/api/prompt-sessions/{first_session_id}/messages").json(), [])
        self.assertEqual(fake.count_requests, [])


if __name__ == "__main__":
    unittest.main()
