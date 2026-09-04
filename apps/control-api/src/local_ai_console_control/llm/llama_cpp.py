"""A narrow, testable adapter for llama.cpp's OpenAI-compatible HTTP surface."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
import json
import math

import httpx

from local_ai_console_control.llm.config import LlmRuntimeSlotConfig
from local_ai_console_control.llm.types import (
    JsonValue,
    LLMGenerationRequest,
    LLMGenerationResult,
    LLMRuntimeCapabilities,
    LLMStreamEvent,
    LLMStreamEventKind,
    LLMTokenCountResult,
    LLMUsage,
    ReasoningMode,
)


class LlamaCppClientErrorKind(StrEnum):
    """Stable, safe error categories; response text and endpoint details never escape."""

    AUTHENTICATION_FAILURE = "authentication_failure"
    CONNECTION_FAILURE = "connection_failure"
    TIMEOUT = "timeout"
    UNEXPECTED_RESPONSE = "unexpected_response"
    PROVIDER_FAILURE = "provider_failure"
    MODEL_MISMATCH = "model_mismatch"
    MALFORMED_STREAM = "malformed_stream"
    UNEXPECTED_STREAM_END = "unexpected_stream_end"
    UNSUPPORTED_CAPABILITY = "unsupported_capability"


class LlamaCppClientError(RuntimeError):
    """A provider failure with only a stable category and optional HTTP status.

    Response bodies, endpoints, and headers deliberately do not become exception
    data.  The status is sufficient for a local, opt-in diagnostic to distinguish
    a rejected request from an unavailable runtime without exposing private
    runtime configuration.
    """

    def __init__(self, kind: LlamaCppClientErrorKind, *, http_status: int | None = None) -> None:
        self.kind = kind
        self.http_status = http_status
        super().__init__(f"llama.cpp request failed: {kind.value}")


class LlamaCppUnsupportedCapabilityError(LlamaCppClientError):
    """Raised only when the installed provider rejects an optional control capability."""

    def __init__(self) -> None:
        super().__init__(LlamaCppClientErrorKind.UNSUPPORTED_CAPABILITY)


class LlamaCppReadiness(StrEnum):
    READY = "ready"
    LOADING = "loading"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class LlamaCppProbe:
    readiness: LlamaCppReadiness
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class LlamaCppModelInfo:
    model_ids: tuple[str, ...]


class LlamaCppClient:
    """Translate generic requests while retaining cancellation and timeout semantics from httpx."""

    def __init__(
        self,
        *,
        slot_config: LlmRuntimeSlotConfig,
        http_client: httpx.AsyncClient,
        api_key: str | None = None,
    ) -> None:
        self._slot_config = slot_config
        self._http_client = http_client
        self._api_key = api_key
        self._capabilities = LLMRuntimeCapabilities()
        self._timeout = httpx.Timeout(
            timeout=slot_config.timeouts.read_seconds,
            connect=slot_config.timeouts.connect_seconds,
        )

    @property
    def capabilities(self) -> LLMRuntimeCapabilities:
        return self._capabilities

    async def probe(self) -> LlamaCppProbe:
        """Check a configured runtime only when an explicit probe was requested."""

        try:
            response = await self._http_client.get(
                self._endpoint("/health"), headers=self._headers(), timeout=self._timeout
            )
        except httpx.TimeoutException:
            return LlamaCppProbe(LlamaCppReadiness.ERROR, LlamaCppClientErrorKind.TIMEOUT.value)
        except httpx.RequestError:
            return LlamaCppProbe(LlamaCppReadiness.ERROR, LlamaCppClientErrorKind.CONNECTION_FAILURE.value)

        if response.status_code == 503:
            return LlamaCppProbe(LlamaCppReadiness.LOADING)
        if response.status_code in {401, 403}:
            return LlamaCppProbe(LlamaCppReadiness.ERROR, LlamaCppClientErrorKind.AUTHENTICATION_FAILURE.value)
        if response.is_error:
            return LlamaCppProbe(LlamaCppReadiness.ERROR, LlamaCppClientErrorKind.PROVIDER_FAILURE.value)

        expected_alias = self._slot_config.expected_model_alias
        if expected_alias is None:
            return LlamaCppProbe(LlamaCppReadiness.READY)
        try:
            model_info = await self.model_info()
        except LlamaCppClientError as error:
            return LlamaCppProbe(LlamaCppReadiness.ERROR, error.kind.value)
        if expected_alias not in model_info.model_ids:
            return LlamaCppProbe(LlamaCppReadiness.ERROR, LlamaCppClientErrorKind.MODEL_MISMATCH.value)
        return LlamaCppProbe(LlamaCppReadiness.READY)

    async def model_info(self) -> LlamaCppModelInfo:
        response = await self._request("GET", "/v1/models")
        payload = self._json_object(response)
        entries = payload.get("data")
        if not isinstance(entries, list):
            raise LlamaCppClientError(LlamaCppClientErrorKind.UNEXPECTED_RESPONSE)
        model_ids: list[str] = []
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
                raise LlamaCppClientError(LlamaCppClientErrorKind.UNEXPECTED_RESPONSE)
            model_ids.append(entry["id"])
        return LlamaCppModelInfo(model_ids=tuple(model_ids))

    async def generate(self, request: LLMGenerationRequest) -> LLMGenerationResult:
        response = await self._request("POST", "/v1/chat/completions", json=self._chat_payload(request, stream=False))
        if request.reasoning.budget is not None:
            self._capabilities = replace(self._capabilities, supports_per_request_reasoning_budget=True)
        payload = self._json_object(response)
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise LlamaCppClientError(LlamaCppClientErrorKind.UNEXPECTED_RESPONSE)
        choice = choices[0]
        message = choice.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise LlamaCppClientError(LlamaCppClientErrorKind.UNEXPECTED_RESPONSE)
        finish_reason = choice.get("finish_reason")
        if finish_reason is not None and not isinstance(finish_reason, str):
            raise LlamaCppClientError(LlamaCppClientErrorKind.UNEXPECTED_RESPONSE)
        return LLMGenerationResult(
            assistant_text=message["content"],
            finish_reason=finish_reason,
            usage=self._usage_from_payload(payload.get("usage")),
            provider_metadata=self._provider_metadata(payload),
        )

    async def count_input_tokens(self, request: LLMGenerationRequest) -> LLMTokenCountResult:
        """Count the provider's complete chat request, including its configured chat template."""

        payload = self._chat_payload(request, stream=False)
        payload.pop("stream", None)
        response = await self._request("POST", "/v1/chat/completions/input_tokens", json=payload)
        response_payload = self._json_object(response)
        count = response_payload.get("input_tokens")
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise LlamaCppClientError(LlamaCppClientErrorKind.UNEXPECTED_RESPONSE)
        return LLMTokenCountResult(input_tokens=count, provider_metadata={"provider": "llama_cpp"})

    def safe_request_shape(self, request: LLMGenerationRequest, *, stream: bool) -> dict[str, JsonValue]:
        """Describe the mapped request without retaining prompt text or private config values."""

        payload = self._chat_payload(request, stream=stream)
        template_kwargs = payload.get("chat_template_kwargs")
        if isinstance(template_kwargs, dict):
            safe_template_kwargs: JsonValue = {
                key: value
                for key, value in template_kwargs.items()
                if key == "enable_thinking" and isinstance(value, bool)
            }
        else:
            safe_template_kwargs = None
        return {
            "adapter": "llama_cpp",
            "transport": "chat_completions",
            "stream": stream,
            "request_keys": sorted(payload),
            "message_count": len(request.messages),
            "message_roles": [message.role.value for message in request.messages],
            "system_message_count": sum(message.role.value == "system" for message in request.messages),
            "message_content_types": sorted({type(message.content).__name__ for message in request.messages}),
            "model_field": (
                "request_preference"
                if request.model_preference is not None
                else "configured_default"
                if self._slot_config.expected_model_alias is not None
                else "omitted"
            ),
            "chat_template_kwargs": safe_template_kwargs,
            "reasoning_mode": request.reasoning.mode.value,
            "reasoning_budget_field": "thinking_budget_tokens" in payload,
            "realtime_reasoning_control_field": "reasoning_control" in payload,
            "max_tokens": payload.get("max_tokens"),
            "structured_output_field": "response_format" in payload,
            "null_field_names": sorted(key for key, value in payload.items() if value is None),
        }

    async def end_reasoning(self, completion_id: str) -> None:
        """Stop reasoning only for a completion that opted into llama.cpp reasoning control."""

        if not completion_id:
            raise ValueError("completion_id is required for reasoning control.")
        try:
            await self._request(
                "POST",
                "/v1/chat/completions/control",
                json={"id": completion_id, "action": "reasoning_end"},
                unsupported_capability=True,
            )
        except LlamaCppUnsupportedCapabilityError:
            self._capabilities = replace(self._capabilities, supports_realtime_reasoning_end=False)
            raise
        self._capabilities = replace(self._capabilities, supports_realtime_reasoning_end=True)

    async def stream_generate(self, request: LLMGenerationRequest) -> AsyncIterator[LLMStreamEvent]:
        """Normalize SSE into typed events while leaving cancellation untouched for httpx to clean up."""

        try:
            async with self._http_client.stream(
                "POST",
                self._endpoint("/v1/chat/completions"),
                headers=self._headers(),
                json=self._chat_payload(request, stream=True),
                timeout=self._timeout,
            ) as response:
                if response.status_code >= 400:
                    if request.reasoning.budget is not None and response.status_code in {400, 404, 422}:
                        self._capabilities = replace(self._capabilities, supports_per_request_reasoning_budget=False)
                    yield LLMStreamEvent(
                        kind=LLMStreamEventKind.ERROR,
                        error_code=self._status_error_kind(response.status_code).value,
                    )
                    return
                if request.reasoning.budget is not None:
                    self._capabilities = replace(self._capabilities, supports_per_request_reasoning_budget=True)
                completion_id: str | None = None
                started = False
                last_usage: LLMUsage | None = None
                last_provider_metadata: Mapping[str, JsonValue] = {"provider": "llama_cpp"}
                async for line in response.aiter_lines():
                    if not line or line.startswith(":") or line.startswith(("event:", "id:", "retry:")):
                        continue
                    if not line.startswith("data:"):
                        yield LLMStreamEvent(
                            kind=LLMStreamEventKind.ERROR,
                            error_code=LlamaCppClientErrorKind.UNEXPECTED_RESPONSE.value,
                            completion_id=completion_id,
                        )
                        return
                    raw_data = line[5:].strip()
                    if raw_data == "[DONE]":
                        yield LLMStreamEvent(
                            kind=LLMStreamEventKind.COMPLETED,
                            usage=last_usage,
                            provider_metadata=last_provider_metadata,
                            completion_id=completion_id,
                        )
                        return
                    try:
                        payload = json.loads(raw_data)
                    except json.JSONDecodeError:
                        yield LLMStreamEvent(
                            kind=LLMStreamEventKind.ERROR,
                            error_code=LlamaCppClientErrorKind.MALFORMED_STREAM.value,
                            completion_id=completion_id,
                        )
                        return
                    if not isinstance(payload, dict):
                        yield LLMStreamEvent(
                            kind=LLMStreamEventKind.ERROR,
                            error_code=LlamaCppClientErrorKind.MALFORMED_STREAM.value,
                            completion_id=completion_id,
                        )
                        return
                    if "error" in payload:
                        yield LLMStreamEvent(
                            kind=LLMStreamEventKind.ERROR,
                            error_code=LlamaCppClientErrorKind.PROVIDER_FAILURE.value,
                            completion_id=completion_id,
                        )
                        return
                    payload_completion_id = payload.get("id")
                    if payload_completion_id is not None:
                        if not isinstance(payload_completion_id, str) or not payload_completion_id:
                            yield LLMStreamEvent(
                                kind=LLMStreamEventKind.ERROR,
                                error_code=LlamaCppClientErrorKind.UNEXPECTED_RESPONSE.value,
                                completion_id=completion_id,
                            )
                            return
                        completion_id = payload_completion_id
                    provider_metadata = self._provider_metadata(payload)
                    if "timings" in provider_metadata:
                        last_provider_metadata = provider_metadata
                    if not started:
                        started = True
                        yield LLMStreamEvent(
                            kind=LLMStreamEventKind.STARTED,
                            provider_metadata=provider_metadata,
                            completion_id=completion_id,
                        )
                    usage = self._usage_from_payload(payload.get("usage"))
                    if usage is not None:
                        last_usage = usage
                        yield LLMStreamEvent(
                            kind=LLMStreamEventKind.USAGE,
                            usage=usage,
                            provider_metadata=provider_metadata,
                            completion_id=completion_id,
                        )
                    choices = payload.get("choices")
                    if choices is None:
                        if usage is not None or payload_completion_id is not None:
                            continue
                        yield LLMStreamEvent(
                            kind=LLMStreamEventKind.ERROR,
                            error_code=LlamaCppClientErrorKind.UNEXPECTED_RESPONSE.value,
                            completion_id=completion_id,
                        )
                        return
                    if not isinstance(choices, list) or not choices:
                        yield LLMStreamEvent(
                            kind=LLMStreamEventKind.ERROR,
                            error_code=LlamaCppClientErrorKind.UNEXPECTED_RESPONSE.value,
                            completion_id=completion_id,
                        )
                        return
                    choice = choices[0]
                    if not isinstance(choice, dict):
                        yield LLMStreamEvent(
                            kind=LLMStreamEventKind.ERROR,
                            error_code=LlamaCppClientErrorKind.MALFORMED_STREAM.value,
                            completion_id=completion_id,
                        )
                        return
                    delta = choice.get("delta")
                    if delta is not None and not isinstance(delta, dict):
                        yield LLMStreamEvent(
                            kind=LLMStreamEventKind.ERROR,
                            error_code=LlamaCppClientErrorKind.MALFORMED_STREAM.value,
                            completion_id=completion_id,
                        )
                        return
                    if isinstance(delta, dict):
                        content = delta.get("content")
                        if content is not None and not isinstance(content, str):
                            yield LLMStreamEvent(
                                kind=LLMStreamEventKind.ERROR,
                                error_code=LlamaCppClientErrorKind.MALFORMED_STREAM.value,
                                completion_id=completion_id,
                            )
                            return
                        if isinstance(content, str) and content:
                            yield LLMStreamEvent(
                                kind=LLMStreamEventKind.TEXT_DELTA,
                                text=content,
                                provider_metadata=provider_metadata,
                                completion_id=completion_id,
                            )
                        reasoning = delta.get("reasoning_content", delta.get("reasoning"))
                        if reasoning is not None and not isinstance(reasoning, str):
                            yield LLMStreamEvent(
                                kind=LLMStreamEventKind.ERROR,
                                error_code=LlamaCppClientErrorKind.MALFORMED_STREAM.value,
                                completion_id=completion_id,
                            )
                            return
                        if isinstance(reasoning, str) and reasoning:
                            yield LLMStreamEvent(
                                kind=LLMStreamEventKind.REASONING_DELTA,
                                text=reasoning,
                                provider_metadata=provider_metadata,
                                completion_id=completion_id,
                            )
                    finish_reason = choice.get("finish_reason")
                    if finish_reason is not None and not isinstance(finish_reason, str):
                        yield LLMStreamEvent(
                            kind=LLMStreamEventKind.ERROR,
                            error_code=LlamaCppClientErrorKind.MALFORMED_STREAM.value,
                            completion_id=completion_id,
                        )
                        return
                    if isinstance(finish_reason, str):
                        yield LLMStreamEvent(
                            kind=LLMStreamEventKind.COMPLETED,
                            usage=last_usage,
                            provider_metadata=provider_metadata if "timings" in provider_metadata else last_provider_metadata,
                            completion_id=completion_id,
                            finish_reason=finish_reason,
                        )
                        return
                yield LLMStreamEvent(
                    kind=LLMStreamEventKind.ERROR,
                    error_code=LlamaCppClientErrorKind.UNEXPECTED_STREAM_END.value,
                    completion_id=completion_id,
                )
        except asyncio.CancelledError:
            raise
        except httpx.TimeoutException:
            yield LLMStreamEvent(kind=LLMStreamEventKind.ERROR, error_code=LlamaCppClientErrorKind.TIMEOUT.value)
        except httpx.RequestError:
            yield LLMStreamEvent(
                kind=LLMStreamEventKind.ERROR,
                error_code=LlamaCppClientErrorKind.CONNECTION_FAILURE.value,
            )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        unsupported_capability: bool = False,
        **kwargs: object,
    ) -> httpx.Response:
        try:
            response = await self._http_client.request(
                method,
                self._endpoint(path),
                headers=self._headers(),
                timeout=self._timeout,
                **kwargs,
            )
        except httpx.TimeoutException as error:
            raise LlamaCppClientError(LlamaCppClientErrorKind.TIMEOUT) from error
        except httpx.RequestError as error:
            raise LlamaCppClientError(LlamaCppClientErrorKind.CONNECTION_FAILURE) from error
        if response.status_code in {401, 403}:
            raise LlamaCppClientError(LlamaCppClientErrorKind.AUTHENTICATION_FAILURE, http_status=response.status_code)
        if unsupported_capability and response.status_code in {400, 404, 405, 501}:
            raise LlamaCppUnsupportedCapabilityError()
        if response.is_error:
            raise LlamaCppClientError(LlamaCppClientErrorKind.PROVIDER_FAILURE, http_status=response.status_code)
        return response

    def _chat_payload(self, request: LLMGenerationRequest, *, stream: bool) -> dict[str, JsonValue]:
        payload: dict[str, JsonValue] = {
            "messages": [{"role": message.role.value, "content": message.content} for message in request.messages],
            "stream": stream,
        }
        model = request.model_preference or self._slot_config.expected_model_alias
        if model is not None:
            payload["model"] = model
        settings = request.generation
        setting_values: Mapping[str, JsonValue] = {
            "max_tokens": settings.max_output_tokens,
            "temperature": settings.temperature,
            "top_p": settings.top_p,
            "top_k": settings.top_k,
            "min_p": settings.min_p,
            "repeat_penalty": settings.repeat_penalty,
            "seed": settings.seed,
        }
        payload.update({key: value for key, value in setting_values.items() if value is not None})
        if settings.stop:
            payload["stop"] = list(settings.stop)
        if request.reasoning.mode is ReasoningMode.OFF:
            payload["chat_template_kwargs"] = {"enable_thinking": False}
        elif request.reasoning.mode is ReasoningMode.ON:
            payload["chat_template_kwargs"] = {"enable_thinking": True}
        if request.reasoning.budget is not None:
            payload["thinking_budget_tokens"] = request.reasoning.budget
        if request.reasoning.enable_realtime_control:
            payload["reasoning_control"] = True
        if request.structured_output is not None:
            response_format: dict[str, JsonValue] = {
                "type": "json_schema",
                "json_schema": {"schema": dict(request.structured_output.json_schema)},
            }
            if request.structured_output.name is not None:
                response_format["json_schema"]["name"] = request.structured_output.name  # type: ignore[index]
            payload["response_format"] = response_format
        return payload

    def _endpoint(self, path: str) -> str:
        return f"{self._slot_config.base_url}{path}"

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self._api_key is not None:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    @staticmethod
    def _json_object(response: httpx.Response) -> dict[str, object]:
        try:
            payload = response.json()
        except (json.JSONDecodeError, ValueError) as error:
            raise LlamaCppClientError(LlamaCppClientErrorKind.UNEXPECTED_RESPONSE) from error
        if not isinstance(payload, dict):
            raise LlamaCppClientError(LlamaCppClientErrorKind.UNEXPECTED_RESPONSE)
        return payload

    @staticmethod
    def _usage_from_payload(payload: object) -> LLMUsage | None:
        if not isinstance(payload, dict):
            return None
        values: dict[str, int | None] = {}
        for destination, source in (
            ("input_tokens", "prompt_tokens"),
            ("output_tokens", "completion_tokens"),
            ("total_tokens", "total_tokens"),
        ):
            value = payload.get(source)
            if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
                return None
            values[destination] = value
        return LLMUsage(**values)

    @staticmethod
    def _provider_metadata(payload: Mapping[str, object]) -> dict[str, JsonValue]:
        """Keep only the finite llama.cpp timing fields useful for local diagnostics."""

        metadata: dict[str, JsonValue] = {"provider": "llama_cpp"}
        timings = payload.get("timings")
        if not isinstance(timings, dict):
            return metadata
        allowed_fields = (
            "cache_n",
            "prompt_n",
            "prompt_ms",
            "prompt_per_second",
            "predicted_n",
            "predicted_ms",
            "predicted_per_second",
        )
        safe_timings: dict[str, JsonValue] = {}
        for field in allowed_fields:
            value = timings.get(field)
            if (
                isinstance(value, bool)
                or not isinstance(value, int | float)
                or value < 0
                or not math.isfinite(value)
            ):
                continue
            safe_timings[field] = value
        if safe_timings:
            metadata["timings"] = safe_timings
        return metadata

    @staticmethod
    def _status_error_kind(status_code: int) -> LlamaCppClientErrorKind:
        if status_code in {401, 403}:
            return LlamaCppClientErrorKind.AUTHENTICATION_FAILURE
        if status_code >= 500:
            return LlamaCppClientErrorKind.PROVIDER_FAILURE
        return LlamaCppClientErrorKind.UNEXPECTED_RESPONSE
