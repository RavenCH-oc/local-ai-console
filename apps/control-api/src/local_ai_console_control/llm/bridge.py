"""Private configuration, provider adapters, and safe Controller runtime status."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Mapping

import httpx

from local_ai_console_control.llm.config import (
    LlmRuntimeConfigError,
    LlmRuntimeConfigLoader,
    LlmRuntimeSlotConfig,
    read_api_key,
)
from local_ai_console_control.llm.llama_cpp import LlamaCppClient, LlamaCppProbe, LlamaCppReadiness
from local_ai_console_control.llm.resolver import TaskRuntimeResolver
from local_ai_console_control.llm.service import LLMService
from local_ai_console_control.llm.types import RuntimeSlot, RuntimeSlotState


@dataclass(frozen=True, slots=True)
class RuntimeSlotStatus:
    configured: bool
    state: RuntimeSlotState
    provider: str | None = None
    expected_model_alias_configured: bool = False
    error_code: str | None = None


class LlmRuntimeBridge:
    """Bridge private runtime configuration without starting network work during application startup."""

    def __init__(
        self,
        *,
        config_directory: Path,
        environ: Mapping[str, str] | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._environ = os.environ if environ is None else environ
        self._http_client = http_client or httpx.AsyncClient(trust_env=False)
        self._owns_http_client = http_client is None
        self._clients: dict[RuntimeSlot, LlamaCppClient] = {}
        self._statuses: dict[RuntimeSlot, RuntimeSlotStatus] = {
            RuntimeSlot.MAIN: RuntimeSlotStatus(False, RuntimeSlotState.UNCONFIGURED),
            RuntimeSlot.UTILITY: RuntimeSlotStatus(False, RuntimeSlotState.UNAVAILABLE),
        }
        try:
            config = LlmRuntimeConfigLoader(config_directory).load()
        except LlmRuntimeConfigError:
            self._statuses[RuntimeSlot.MAIN] = RuntimeSlotStatus(
                configured=False,
                state=RuntimeSlotState.ERROR,
                error_code="configuration_error",
            )
            return
        if config is None:
            return
        for slot, slot_config in config.slots.items():
            self._configure_slot(slot, slot_config)

    @property
    def service(self) -> LLMService:
        return LLMService(resolver=TaskRuntimeResolver(), clients=self._clients)

    def status(self) -> Mapping[RuntimeSlot, RuntimeSlotStatus]:
        return dict(self._statuses)

    async def probe(self) -> Mapping[RuntimeSlot, RuntimeSlotStatus]:
        """Probe only configured, credential-ready slots; no caller-supplied address is accepted."""

        for slot, client in self._clients.items():
            current = self._statuses[slot]
            self._statuses[slot] = RuntimeSlotStatus(
                configured=True,
                state=RuntimeSlotState.CHECKING,
                provider=current.provider,
                expected_model_alias_configured=current.expected_model_alias_configured,
            )
            result = await client.probe()
            self._statuses[slot] = self._status_from_probe(current, result)
        return self.status()

    async def aclose(self) -> None:
        if self._owns_http_client:
            await self._http_client.aclose()

    def _configure_slot(self, slot: RuntimeSlot, slot_config: LlmRuntimeSlotConfig) -> None:
        api_key = read_api_key(slot_config, self._environ)
        common = {
            "configured": True,
            "provider": slot_config.provider,
            "expected_model_alias_configured": slot_config.expected_model_alias is not None,
        }
        if slot_config.api_key_env is not None and api_key is None:
            self._statuses[slot] = RuntimeSlotStatus(
                state=RuntimeSlotState.ERROR,
                error_code="missing_credentials",
                **common,
            )
            return
        self._clients[slot] = LlamaCppClient(
            slot_config=slot_config,
            http_client=self._http_client,
            api_key=api_key,
        )
        self._statuses[slot] = RuntimeSlotStatus(state=RuntimeSlotState.CHECKING, **common)

    @staticmethod
    def _status_from_probe(previous: RuntimeSlotStatus, probe: LlamaCppProbe) -> RuntimeSlotStatus:
        state = {
            LlamaCppReadiness.READY: RuntimeSlotState.READY,
            LlamaCppReadiness.LOADING: RuntimeSlotState.LOADING,
            LlamaCppReadiness.ERROR: RuntimeSlotState.ERROR,
        }[probe.readiness]
        return RuntimeSlotStatus(
            configured=True,
            state=state,
            provider=previous.provider,
            expected_model_alias_configured=previous.expected_model_alias_configured,
            error_code=probe.error_code,
        )
