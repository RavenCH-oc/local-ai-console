"""Provider-neutral service facade for consumers that later need LLM generation."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from typing import Protocol

from local_ai_console_control.llm.resolver import TaskRuntimeResolver
from local_ai_console_control.llm.types import (
    JsonValue,
    LLMGenerationRequest,
    LLMGenerationResult,
    LLMRuntimeCapabilities,
    LLMStreamEvent,
    LLMTokenCountResult,
    RuntimeSlot,
)


class LlmProviderClient(Protocol):
    @property
    def capabilities(self) -> LLMRuntimeCapabilities: ...

    async def generate(self, request: LLMGenerationRequest) -> LLMGenerationResult: ...

    async def count_input_tokens(self, request: LLMGenerationRequest) -> LLMTokenCountResult: ...

    def stream_generate(self, request: LLMGenerationRequest) -> AsyncIterator[LLMStreamEvent]: ...

    async def end_reasoning(self, completion_id: str) -> None: ...


class LLMService:
    """Resolve the slot once, then delegate provider-specific work to the selected adapter."""

    def __init__(self, *, resolver: TaskRuntimeResolver, clients: Mapping[RuntimeSlot, LlmProviderClient]) -> None:
        self._resolver = resolver
        self._clients = dict(clients)

    def _client_for(self, request: LLMGenerationRequest) -> LlmProviderClient:
        slot = self.resolve_slot(request)
        return self._clients[slot]

    def resolve_slot(self, request: LLMGenerationRequest) -> RuntimeSlot:
        """Resolve a request explicitly when a caller needs a diagnostic stage boundary."""

        return self._resolver.resolve(request.task_kind, request.target_preference, set(self._clients))

    def safe_request_shape(self, request: LLMGenerationRequest, *, stream: bool) -> dict[str, JsonValue]:
        """Return a prompt-free adapter shape for opt-in diagnostics.

        This never exposes message content, model aliases, endpoint URLs, or
        authorization data.  Fakes without an adapter-specific implementation
        retain a useful provider-neutral summary for tests.
        """

        client = self._client_for(request)
        adapter_summary = getattr(client, "safe_request_shape", None)
        if callable(adapter_summary):
            summary = adapter_summary(request, stream=stream)
            if isinstance(summary, dict):
                return summary
        return {
            "adapter": "provider_neutral",
            "transport": "chat_completions",
            "stream": stream,
            "message_count": len(request.messages),
            "message_roles": [message.role.value for message in request.messages],
            "system_message_count": sum(message.role.value == "system" for message in request.messages),
            "message_content_types": sorted({type(message.content).__name__ for message in request.messages}),
            "model_field": "request_preference" if request.model_preference is not None else "adapter_default",
            "reasoning_mode": request.reasoning.mode.value,
            "max_tokens": request.generation.max_output_tokens,
            "structured_output_field": request.structured_output is not None,
            "null_field_names": [],
        }

    async def generate(self, request: LLMGenerationRequest) -> LLMGenerationResult:
        return await self._client_for(request).generate(request)

    async def count_input_tokens(self, request: LLMGenerationRequest) -> LLMTokenCountResult:
        return await self._client_for(request).count_input_tokens(request)

    async def stream_generate(self, request: LLMGenerationRequest) -> AsyncIterator[LLMStreamEvent]:
        provider_stream = self._client_for(request).stream_generate(request)
        try:
            async for event in provider_stream:
                yield event
        finally:
            closer = getattr(provider_stream, "aclose", None)
            if callable(closer):
                await closer()

    def capabilities_for(self, slot: RuntimeSlot) -> LLMRuntimeCapabilities:
        """Expose narrow provider capabilities without leaking transport implementation upward."""

        return self._clients[slot].capabilities

    async def end_reasoning(self, *, slot: RuntimeSlot, completion_id: str) -> None:
        """Request a reasoning-only stop; this intentionally does not cancel the generation stream."""

        await self._clients[slot].end_reasoning(completion_id)
