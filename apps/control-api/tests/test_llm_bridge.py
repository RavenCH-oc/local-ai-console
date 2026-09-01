"""Tests for the Phase 1B-1 LLM bridge without contacting a real runtime."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import tempfile
import unittest

import httpx

from local_ai_console_control.llm.bridge import LlmRuntimeBridge
from local_ai_console_control.llm.config import (
    LlmRuntimeConfigError,
    LlmRuntimeConfigLoader,
    LlmRuntimeSlotConfig,
    LlmTimeoutConfig,
    read_api_key,
)
from local_ai_console_control.llm.llama_cpp import LlamaCppClient, LlamaCppClientError, LlamaCppClientErrorKind
from local_ai_console_control.llm.resolver import RuntimeResolutionError, TaskRuntimeResolver
from local_ai_console_control.llm.types import (
    GenerationSettings,
    LLMGenerationRequest,
    LLMMessage,
    LLMMessageRole,
    LLMStreamEventKind,
    ReasoningMode,
    ReasoningOptions,
    RuntimeSlot,
    RuntimeSlotState,
    RuntimeTargetPreference,
    StructuredOutputSpec,
    TaskKind,
)


def slot_config(*, expected_model_alias: str | None = None, api_key_env: str | None = None) -> LlmRuntimeSlotConfig:
    return LlmRuntimeSlotConfig(
        slot=RuntimeSlot.MAIN,
        provider="llama_cpp",
        base_url="https://configured-runtime.invalid",
        api_key_env=api_key_env,
        expected_model_alias=expected_model_alias,
        timeouts=LlmTimeoutConfig(connect_seconds=2, read_seconds=5),
    )


def generation_request(*, structured: bool = False) -> LLMGenerationRequest:
    return LLMGenerationRequest(
        messages=(LLMMessage(LLMMessageRole.USER, "Test prompt"),),
        task_kind=TaskKind.CHAT,
        generation=GenerationSettings(max_output_tokens=64, temperature=0.2, stop=("END",)),
        reasoning=ReasoningOptions(mode=ReasoningMode.ON, budget=32),
        structured_output=StructuredOutputSpec({"type": "object"}, name="result") if structured else None,
    )


class LlmRuntimeConfigTests(unittest.TestCase):
    def test_missing_configuration_is_allowed_and_api_keys_are_references_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_directory = Path(temporary_directory)
            self.assertIsNone(LlmRuntimeConfigLoader(config_directory).load())

            config_directory.joinpath("llm-runtimes.json").write_text(
                json.dumps(
                    {
                        "schema_version": "1.0.0",
                        "slots": {
                            "main": {
                                "provider": "llama_cpp",
                                "base_url": "https://configured-runtime.invalid",
                                "api_key_env": "TEST_LLM_API_KEY",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            config = LlmRuntimeConfigLoader(config_directory).load()

        assert config is not None
        loaded_slot = config.slot_config(RuntimeSlot.MAIN)
        assert loaded_slot is not None
        self.assertEqual(read_api_key(loaded_slot, {"TEST_LLM_API_KEY": "test-only-value"}), "test-only-value")
        self.assertIsNone(read_api_key(loaded_slot, {}))

    def test_invalid_schema_provider_url_and_inline_key_are_rejected(self) -> None:
        invalid_entries = [
            {"schema_version": "2.0.0", "slots": {}},
            {
                "schema_version": "1.0.0",
                "slots": {"main": {"provider": "other", "base_url": "https://configured-runtime.invalid"}},
            },
            {
                "schema_version": "1.0.0",
                "slots": {"main": {"provider": "llama_cpp", "base_url": "/relative"}},
            },
            {
                "schema_version": "1.0.0",
                "slots": {
                    "main": {
                        "provider": "llama_cpp",
                        "base_url": "https://configured-runtime.invalid",
                        "api_key": "inline-not-allowed",
                    }
                },
            },
        ]
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "llm-runtimes.json"
            for payload in invalid_entries:
                config_path.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaises(LlmRuntimeConfigError):
                    LlmRuntimeConfigLoader(config_path.parent).load()


class TaskResolutionTests(unittest.TestCase):
    def test_auto_prefers_main_today_but_policy_can_prefer_utility_later(self) -> None:
        resolver = TaskRuntimeResolver()
        self.assertEqual(
            resolver.resolve(TaskKind.CHAT, RuntimeTargetPreference.AUTO, {RuntimeSlot.MAIN, RuntimeSlot.UTILITY}),
            RuntimeSlot.MAIN,
        )
        future_resolver = TaskRuntimeResolver({TaskKind.CHAT: (RuntimeSlot.UTILITY, RuntimeSlot.MAIN)})
        self.assertEqual(
            future_resolver.resolve(TaskKind.CHAT, RuntimeTargetPreference.AUTO, {RuntimeSlot.MAIN, RuntimeSlot.UTILITY}),
            RuntimeSlot.UTILITY,
        )
        with self.assertRaises(RuntimeResolutionError):
            resolver.resolve(TaskKind.CHAT, RuntimeTargetPreference.UTILITY, {RuntimeSlot.MAIN})


class LlamaCppClientTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.clients: list[httpx.AsyncClient] = []

    async def asyncTearDown(self) -> None:
        for client in self.clients:
            await client.aclose()

    def client(self, handler, *, expected_model_alias: str | None = None) -> LlamaCppClient:
        transport = httpx.MockTransport(handler)
        http_client = httpx.AsyncClient(transport=transport)
        self.clients.append(http_client)
        return LlamaCppClient(slot_config=slot_config(expected_model_alias=expected_model_alias), http_client=http_client)

    async def test_probe_handles_ready_loading_connection_authentication_and_model_identity(self) -> None:
        ready = self.client(lambda request: httpx.Response(200, json={"status": "ok"}))
        self.assertEqual((await ready.probe()).readiness, "ready")

        loading = self.client(lambda request: httpx.Response(503, json={}))
        self.assertEqual((await loading.probe()).readiness, "loading")

        def disconnected(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("unreachable", request=request)

        unavailable = self.client(disconnected)
        self.assertEqual((await unavailable.probe()).error_code, "connection_failure")

        denied = self.client(lambda request: httpx.Response(401, json={}))
        self.assertEqual((await denied.probe()).error_code, "authentication_failure")

        def model_handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/health":
                return httpx.Response(200, json={})
            return httpx.Response(200, json={"data": [{"id": "expected-model"}]})

        identified = self.client(model_handler, expected_model_alias="expected-model")
        self.assertEqual((await identified.probe()).readiness, "ready")

    async def test_generation_structured_output_and_provider_token_count_are_mapped(self) -> None:
        recorded_bodies: list[dict[str, object]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            recorded_bodies.append(body)
            if request.url.path.endswith("/tokenize"):
                return httpx.Response(200, json={"tokens": [1, 2, 3, 4]})
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "result"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
                },
            )

        client = self.client(handler)
        request = generation_request(structured=True)
        generated = await client.generate(request)
        counted = await client.count_input_tokens(request)

        self.assertEqual(generated.assistant_text, "result")
        self.assertEqual(generated.usage.total_tokens if generated.usage else None, 5)
        self.assertEqual(counted.input_tokens, 4)
        self.assertEqual(recorded_bodies[0]["max_tokens"], 64)
        self.assertEqual(recorded_bodies[0]["reasoning"], {"mode": "on", "budget": 32})
        self.assertEqual(recorded_bodies[0]["response_format"], {"type": "json_schema", "json_schema": {"schema": {"type": "object"}, "name": "result"}})

    async def test_stream_normalizes_deltas_handles_malformed_data_and_closes_on_cancellation(self) -> None:
        async def collect(client: LlamaCppClient) -> list:
            return [event async for event in client.stream_generate(generation_request())]

        streamed = self.client(
            lambda request: httpx.Response(
                200,
                content=(
                    b'data: {"choices":[{"delta":{"content":"Hel"}}]}\n\n'
                    b'data: {"choices":[{"delta":{"reasoning_content":"think"}}],"usage":{"prompt_tokens":1}}\n\n'
                    b"data: [DONE]\n\n"
                ),
            )
        )
        events = await collect(streamed)
        self.assertEqual([event.kind for event in events], ["text_delta", "usage", "reasoning_delta", "completed"])
        self.assertEqual(events[0].text, "Hel")
        self.assertEqual(events[1].usage.input_tokens if events[1].usage else None, 1)

        malformed = self.client(lambda request: httpx.Response(200, content=b"data: not-json\n\n"))
        malformed_events = await collect(malformed)
        self.assertEqual(malformed_events[-1].error_code, "malformed_stream")

        class TrackingStream(httpx.AsyncByteStream):
            closed = False

            async def __aiter__(self):
                yield b'data: {"choices":[{"delta":{"content":"first"}}]}\n\n'
                await asyncio.Event().wait()

            async def aclose(self) -> None:
                self.closed = True

        tracking_stream = TrackingStream()
        cancellable = self.client(lambda request: httpx.Response(200, stream=tracking_stream))
        generator = cancellable.stream_generate(generation_request())
        self.assertEqual((await anext(generator)).kind, LLMStreamEventKind.TEXT_DELTA)
        await generator.aclose()
        self.assertTrue(tracking_stream.closed)

    async def test_provider_failures_are_sanitized(self) -> None:
        client = self.client(lambda request: httpx.Response(500, text="private provider detail"))
        with self.assertRaises(LlamaCppClientError) as raised:
            await client.generate(generation_request())
        self.assertEqual(raised.exception.kind, LlamaCppClientErrorKind.PROVIDER_FAILURE)
        self.assertNotIn("private provider detail", str(raised.exception))


class LlmRuntimeBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_status_is_safe_when_unconfigured_or_credentials_are_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_directory = Path(temporary_directory)
            bridge = LlmRuntimeBridge(config_directory=config_directory, environ={})
            statuses = bridge.status()
            self.assertEqual(statuses[RuntimeSlot.MAIN].state, RuntimeSlotState.UNCONFIGURED)
            self.assertEqual(statuses[RuntimeSlot.UTILITY].state, RuntimeSlotState.UNAVAILABLE)
            await bridge.aclose()

            config_directory.joinpath("llm-runtimes.json").write_text(
                json.dumps(
                    {
                        "schema_version": "1.0.0",
                        "slots": {
                            "main": {
                                "provider": "llama_cpp",
                                "base_url": "https://configured-runtime.invalid",
                                "api_key_env": "MISSING_KEY",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            missing_credentials = LlmRuntimeBridge(config_directory=config_directory, environ={})
            safe_status = missing_credentials.status()[RuntimeSlot.MAIN]
            self.assertEqual(safe_status.error_code, "missing_credentials")
            self.assertNotIn("MISSING_KEY", str(safe_status))
            await missing_credentials.aclose()

    async def test_malformed_private_config_becomes_a_safe_status_without_startup_work(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_directory = Path(temporary_directory)
            config_directory.joinpath("llm-runtimes.json").write_text("{not valid json", encoding="utf-8")
            bridge = LlmRuntimeBridge(config_directory=config_directory, environ={})
            safe_status = bridge.status()[RuntimeSlot.MAIN]
            self.assertEqual(safe_status.state, RuntimeSlotState.ERROR)
            self.assertEqual(safe_status.error_code, "configuration_error")
            self.assertNotIn("not valid json", str(safe_status))
            await bridge.aclose()

    async def test_explicit_probe_maps_ready_loading_and_does_not_expose_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_directory = Path(temporary_directory)
            config_directory.joinpath("llm-runtimes.json").write_text(
                json.dumps(
                    {
                        "schema_version": "1.0.0",
                        "slots": {"main": {"provider": "llama_cpp", "base_url": "https://configured-runtime.invalid"}},
                    }
                ),
                encoding="utf-8",
            )
            requests: list[httpx.Request] = []

            def loading_handler(request: httpx.Request) -> httpx.Response:
                requests.append(request)
                return httpx.Response(503, json={})

            http_client = httpx.AsyncClient(transport=httpx.MockTransport(loading_handler))
            bridge = LlmRuntimeBridge(config_directory=config_directory, environ={}, http_client=http_client)
            self.assertEqual(bridge.status()[RuntimeSlot.MAIN].state, RuntimeSlotState.CHECKING)
            self.assertEqual(requests, [])
            statuses = await bridge.probe()
            self.assertEqual(statuses[RuntimeSlot.MAIN].state, RuntimeSlotState.LOADING)
            self.assertEqual(len(requests), 1)
            self.assertNotIn("configured-runtime", str(statuses))
            await bridge.aclose()
            await http_client.aclose()
