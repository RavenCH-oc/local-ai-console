"""Opt-in live verification for a privately configured llama.cpp runtime.

This script intentionally contains no endpoint, credential, or model alias. It is
safe to keep in the public repository and exits successfully unless the operator
explicitly sets LOCAL_AI_CONSOLE_RUN_LIVE_LLM_TESTS=1.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time

from local_ai_console_control.config.runtime_paths import resolve_runtime_paths
from local_ai_console_control.llm.bridge import LlmRuntimeBridge
from local_ai_console_control.llm.llama_cpp import LlamaCppUnsupportedCapabilityError
from local_ai_console_control.llm.types import (
    GenerationSettings,
    LLMGenerationRequest,
    LLMMessage,
    LLMMessageRole,
    LLMStreamEvent,
    LLMStreamEventKind,
    ReasoningMode,
    ReasoningOptions,
    RuntimeSlot,
    RuntimeSlotState,
    StructuredOutputSpec,
    TaskKind,
)


LIVE_TEST_ENVIRONMENT_VARIABLE = "LOCAL_AI_CONSOLE_RUN_LIVE_LLM_TESTS"


def request(
    *,
    messages: tuple[LLMMessage, ...],
    reasoning: ReasoningOptions,
    max_output_tokens: int = 32,
    structured_output: StructuredOutputSpec | None = None,
) -> LLMGenerationRequest:
    return LLMGenerationRequest(
        messages=messages,
        task_kind=TaskKind.CHAT,
        generation=GenerationSettings(max_output_tokens=max_output_tokens, temperature=0),
        reasoning=reasoning,
        structured_output=structured_output,
    )


async def collect_stream(service, stream_request: LLMGenerationRequest) -> list[LLMStreamEvent]:
    return [event async for event in service.stream_generate(stream_request)]


def stream_summary(events: list[LLMStreamEvent]) -> dict[str, object]:
    completed = next((event for event in reversed(events) if event.kind is LLMStreamEventKind.COMPLETED), None)
    timing_fields: list[str] = []
    if completed is not None:
        timings = completed.provider_metadata.get("timings")
        if isinstance(timings, dict):
            timing_fields = sorted(timings)
    return {
        "started": any(event.kind is LLMStreamEventKind.STARTED for event in events),
        "reasoning_delta_count": sum(event.kind is LLMStreamEventKind.REASONING_DELTA for event in events),
        "text_delta_count": sum(event.kind is LLMStreamEventKind.TEXT_DELTA for event in events),
        "completed": completed is not None,
        "finish_reason": completed.finish_reason if completed is not None else None,
        "completion_id_observed": any(event.completion_id is not None for event in events),
        "usage_observed": completed is not None and completed.usage is not None,
        "timing_fields": timing_fields,
        "error_codes": [event.error_code for event in events if event.kind is LLMStreamEventKind.ERROR],
    }


def require_visible_completed_stream(summary: dict[str, object], label: str) -> None:
    if not summary["started"] or not summary["completed"] or not summary["text_delta_count"] or summary["error_codes"]:
        raise RuntimeError(f"The {label} stream did not produce a successful visible completion.")


def classify_reasoning_budget(
    *,
    default: dict[str, object],
    zero: dict[str, object],
    positive: dict[str, object],
) -> str:
    if default["error_codes"] or zero["error_codes"] or positive["error_codes"]:
        return "unsupported"
    if default["reasoning_delta_count"] and not zero["reasoning_delta_count"] and positive["completed"]:
        return "supported"
    return "partial"


async def verify() -> dict[str, object]:
    runtime_paths = resolve_runtime_paths()
    bridge = LlmRuntimeBridge(config_directory=runtime_paths.config)
    try:
        statuses = await bridge.probe()
        main_status = statuses[RuntimeSlot.MAIN]
        utility_status = statuses[RuntimeSlot.UTILITY]
        if main_status.state is not RuntimeSlotState.READY:
            raise RuntimeError("The configured Main runtime did not become ready.")
        if utility_status.state is not RuntimeSlotState.UNAVAILABLE:
            raise RuntimeError("Utility must remain unavailable for this verification.")

        service = bridge.service
        chat_messages = (
            LLMMessage(LLMMessageRole.SYSTEM, "You are a concise local runtime verification assistant."),
            LLMMessage(LLMMessageRole.USER, "請只回答：Local AI Console 連線成功"),
        )
        thinking_off = ReasoningOptions(mode=ReasoningMode.OFF)
        chat_request = request(messages=chat_messages, reasoning=thinking_off)
        token_count = await service.count_input_tokens(chat_request)
        if not isinstance(token_count.input_tokens, int):
            raise RuntimeError("The native input-token endpoint did not return an integer.")

        generated = await service.generate(chat_request)
        if "Local AI Console 連線成功" not in generated.assistant_text:
            raise RuntimeError("The UTF-8 verification response did not preserve the requested Chinese text.")

        schema = {
            "type": "object",
            "properties": {"status": {"type": "string"}},
            "required": ["status"],
            "additionalProperties": False,
        }
        structured_request = request(
            messages=(
                LLMMessage(LLMMessageRole.SYSTEM, "Return only JSON that satisfies the supplied schema."),
                LLMMessage(
                    LLMMessageRole.USER,
                    "Return a success status and also include an extra field named forbidden_extra.",
                ),
            ),
            reasoning=thinking_off,
            structured_output=StructuredOutputSpec(schema, name="runtime_status"),
        )
        structured = await service.generate(structured_request)
        try:
            structured_value = json.loads(structured.assistant_text)
        except json.JSONDecodeError as error:
            raise RuntimeError("The structured response was not valid JSON.") from error
        if not isinstance(structured_value, dict) or set(structured_value) != {"status"} or not isinstance(
            structured_value["status"], str
        ):
            raise RuntimeError("The structured response did not satisfy the requested schema.")

        off_stream = stream_summary(await collect_stream(service, chat_request))
        require_visible_completed_stream(off_stream, "thinking-off")
        if off_stream["reasoning_delta_count"]:
            raise RuntimeError("Thinking-off stream unexpectedly emitted substantive reasoning deltas.")

        reasoning_messages = (
            LLMMessage(LLMMessageRole.SYSTEM, "Think briefly, then provide a concise final answer."),
            LLMMessage(LLMMessageRole.USER, "What is one plus one?"),
        )
        thinking_on_request = request(
            messages=reasoning_messages,
            reasoning=ReasoningOptions(mode=ReasoningMode.ON),
            max_output_tokens=128,
        )
        on_stream = stream_summary(await collect_stream(service, thinking_on_request))
        require_visible_completed_stream(on_stream, "thinking-on")
        if not on_stream["reasoning_delta_count"]:
            raise RuntimeError("Thinking-on stream did not emit a reasoning delta for this runtime.")

        automatic_request = request(
            messages=reasoning_messages,
            reasoning=ReasoningOptions(mode=ReasoningMode.AUTO),
            max_output_tokens=128,
        )
        auto_stream = stream_summary(await collect_stream(service, automatic_request))
        require_visible_completed_stream(auto_stream, "automatic-reasoning")

        budget_default = on_stream
        budget_zero = stream_summary(
            await collect_stream(
                service,
                request(
                    messages=reasoning_messages,
                    reasoning=ReasoningOptions(mode=ReasoningMode.ON, budget=0),
                    max_output_tokens=128,
                ),
            )
        )
        budget_positive = stream_summary(
            await collect_stream(
                service,
                request(
                    messages=reasoning_messages,
                    reasoning=ReasoningOptions(mode=ReasoningMode.ON, budget=128),
                    max_output_tokens=160,
                ),
            )
        )
        reasoning_budget = classify_reasoning_budget(
            default=budget_default,
            zero=budget_zero,
            positive=budget_positive,
        )

        controlled_request = request(
            messages=reasoning_messages,
            reasoning=ReasoningOptions(mode=ReasoningMode.ON, enable_realtime_control=True),
            max_output_tokens=128,
        )
        controlled_events: list[LLMStreamEvent] = []
        controlled_stream = service.stream_generate(controlled_request)
        realtime_reasoning_end = "unknown"
        try:
            async for event in controlled_stream:
                controlled_events.append(event)
                if event.kind is LLMStreamEventKind.REASONING_DELTA and event.completion_id is not None:
                    try:
                        await service.end_reasoning(slot=RuntimeSlot.MAIN, completion_id=event.completion_id)
                    except LlamaCppUnsupportedCapabilityError:
                        realtime_reasoning_end = "unsupported"
                        await controlled_stream.aclose()
                        break
                    realtime_reasoning_end = "supported"
        finally:
            await controlled_stream.aclose()
        controlled_summary = stream_summary(controlled_events)
        if realtime_reasoning_end == "supported":
            require_visible_completed_stream(controlled_summary, "reasoning-control")
        elif realtime_reasoning_end == "unknown" and not controlled_summary["completion_id_observed"]:
            realtime_reasoning_end = "unknown_no_completion_id"

        cancellation_request = request(
            messages=reasoning_messages,
            reasoning=ReasoningOptions(mode=ReasoningMode.ON),
            max_output_tokens=256,
        )
        cancellation_stream = service.stream_generate(cancellation_request)
        cancellation_event_received = False
        cancel_started: float | None = None
        try:
            async for event in cancellation_stream:
                if event.kind in {LLMStreamEventKind.REASONING_DELTA, LLMStreamEventKind.TEXT_DELTA}:
                    cancellation_event_received = True
                    break
        finally:
            cancel_started = time.monotonic()
            await cancellation_stream.aclose()
        local_cancel_ms = round((time.monotonic() - cancel_started) * 1000)
        if not cancellation_event_received:
            raise RuntimeError("The cancellation smoke test did not receive a stream delta before cancellation.")

        slot_probe_started = time.monotonic()
        post_cancel = await service.generate(
            request(
                messages=(LLMMessage(LLMMessageRole.USER, "請只回答：OK"),),
                reasoning=thinking_off,
                max_output_tokens=8,
            )
        )
        post_cancel_slot_probe_ms = round((time.monotonic() - slot_probe_started) * 1000)
        if not post_cancel.assistant_text:
            raise RuntimeError("The post-cancel slot availability request did not return visible content.")

        timings = generated.provider_metadata.get("timings")
        timing_fields = sorted(timings) if isinstance(timings, dict) else []
        return {
            "main_state": main_status.state.value,
            "utility_state": utility_status.state.value,
            "model_alias_verified": main_status.expected_model_alias_configured,
            "native_input_tokens": token_count.input_tokens,
            "utf8_non_stream": True,
            "reasoning_disabled_request": True,
            "structured_json": True,
            "non_stream_timing_fields": timing_fields,
            "streaming": {
                "thinking_off": off_stream,
                "thinking_on": on_stream,
                "automatic": auto_stream,
                "reasoning_control": controlled_summary,
            },
            "reasoning_budget": {
                "result": reasoning_budget,
                "default": budget_default,
                "zero": budget_zero,
                "positive": budget_positive,
                "provider_accepted_budget_field": service.capabilities_for(RuntimeSlot.MAIN).supports_per_request_reasoning_budget,
            },
            "realtime_reasoning_end": realtime_reasoning_end,
            "realtime_reasoning_end_capability": service.capabilities_for(RuntimeSlot.MAIN).supports_realtime_reasoning_end,
            "cancellation": {
                "client_stream_cancelled": True,
                "local_cancel_ms": local_cancel_ms,
                "post_cancel_slot_probe_succeeded": True,
                "post_cancel_slot_probe_ms": post_cancel_slot_probe_ms,
                "server_generation_cancellation": "inferred_from_slot_availability_only",
            },
        }
    finally:
        await bridge.aclose()


def main() -> int:
    if os.environ.get(LIVE_TEST_ENVIRONMENT_VARIABLE) != "1":
        print(f"Skipped. Set {LIVE_TEST_ENVIRONMENT_VARIABLE}=1 to run private live-runtime verification.")
        return 0
    try:
        result = asyncio.run(verify())
    except RuntimeError as error:
        print(f"Live llama.cpp runtime verification failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
