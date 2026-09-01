"""Safe LLM runtime inspection endpoints; they never proxy arbitrary target URLs."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

from local_ai_console_control.llm.bridge import LlmRuntimeBridge, RuntimeSlotStatus
from local_ai_console_control.llm.types import RuntimeSlot


router = APIRouter(prefix="/api/llm", tags=["llm-runtime"])


class LlmSlotStatusResponse(BaseModel):
    configured: bool
    state: Literal["unconfigured", "unavailable", "checking", "loading", "ready", "error"]
    provider: str | None
    expected_model_alias_configured: bool
    error_code: str | None


class LlmRuntimeStatusResponse(BaseModel):
    main: LlmSlotStatusResponse
    utility: LlmSlotStatusResponse


def _bridge(request: Request) -> LlmRuntimeBridge:
    return request.app.state.llm_runtime_bridge


def _slot_response(status: RuntimeSlotStatus) -> LlmSlotStatusResponse:
    return LlmSlotStatusResponse(
        configured=status.configured,
        state=status.state.value,
        provider=status.provider,
        expected_model_alias_configured=status.expected_model_alias_configured,
        error_code=status.error_code,
    )


def _response(bridge: LlmRuntimeBridge) -> LlmRuntimeStatusResponse:
    statuses = bridge.status()
    return LlmRuntimeStatusResponse(
        main=_slot_response(statuses[RuntimeSlot.MAIN]),
        utility=_slot_response(statuses[RuntimeSlot.UTILITY]),
    )


@router.get("/status", response_model=LlmRuntimeStatusResponse)
def get_status(request: Request) -> LlmRuntimeStatusResponse:
    """Return only safe configuration and readiness state; endpoints, models, and errors stay private."""

    return _response(_bridge(request))


@router.post("/probe", response_model=LlmRuntimeStatusResponse)
async def post_probe(request: Request) -> LlmRuntimeStatusResponse:
    """Explicitly probe preconfigured slots. There is no user-controlled probe target."""

    bridge = _bridge(request)
    await bridge.probe()
    return _response(bridge)
