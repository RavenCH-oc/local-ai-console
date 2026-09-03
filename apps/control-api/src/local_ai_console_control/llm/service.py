"""Provider-neutral service facade for consumers that later need LLM generation."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from typing import Protocol

from local_ai_console_control.llm.resolver import TaskRuntimeResolver
from local_ai_console_control.llm.types import (
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
        slot = self._resolver.resolve(request.task_kind, request.target_preference, set(self._clients))
        return self._clients[slot]

    async def generate(self, request: LLMGenerationRequest) -> LLMGenerationResult:
        return await self._client_for(request).generate(request)

    async def count_input_tokens(self, request: LLMGenerationRequest) -> LLMTokenCountResult:
        return await self._client_for(request).count_input_tokens(request)

    async def stream_generate(self, request: LLMGenerationRequest) -> AsyncIterator[LLMStreamEvent]:
        async for event in self._client_for(request).stream_generate(request):
            yield event

    def capabilities_for(self, slot: RuntimeSlot) -> LLMRuntimeCapabilities:
        """Expose narrow provider capabilities without leaking transport implementation upward."""

        return self._clients[slot].capabilities

    async def end_reasoning(self, *, slot: RuntimeSlot, completion_id: str) -> None:
        """Request a reasoning-only stop; this intentionally does not cancel the generation stream."""

        await self._clients[slot].end_reasoning(completion_id)
