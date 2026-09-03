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
PREFIX_CACHE_ONLY_ENVIRONMENT_VARIABLE = "LOCAL_AI_CONSOLE_RUN_PREFIX_CACHE_BENCHMARK_ONLY"
PREFIX_CACHE_BENCHMARK_REVISION = "phase-1b-2c-v3"


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


def synthetic_stable_prefix(*, variant: str, repetitions: int) -> str:
    """Build a deterministic public-only long prefix without embedding user/runtime data."""

    unit = (
        "This is public synthetic prefix-cache benchmark material. "
        "It contains no personal data, credentials, runtime configuration, or private prompts. "
        "Maintain the stated synthetic conversation boundaries and answer only the current request."
    )
    return (
        f"SYNTHETIC PREFIX BENCHMARK {PREFIX_CACHE_BENCHMARK_REVISION} VARIANT {variant}\n"
        "EARLY POLICY MARKER: baseline\n"
        + "\n".join(unit for _ in range(repetitions))
    )


def synthetic_messages(*, stable_prefix: str, current_request: str, appended: bool = False) -> tuple[LLMMessage, ...]:
    messages: list[LLMMessage] = [
        LLMMessage(LLMMessageRole.SYSTEM, stable_prefix),
        LLMMessage(LLMMessageRole.USER, "Synthetic conversation opening: summarize the public benchmark objective."),
        LLMMessage(LLMMessageRole.ASSISTANT, "Synthetic assistant acknowledgement of the public benchmark objective."),
    ]
    if appended:
        messages.extend(
            (
                LLMMessage(LLMMessageRole.USER, "Synthetic follow-up: preserve the established benchmark context."),
                LLMMessage(LLMMessageRole.ASSISTANT, "Synthetic assistant continuation with no external or private facts."),
            )
        )
    messages.append(LLMMessage(LLMMessageRole.USER, current_request))
    return tuple(messages)


def cache_reuse_ratio(cache_n: object, prompt_n: object) -> float | None:
    if (
        isinstance(cache_n, bool)
        or isinstance(prompt_n, bool)
        or not isinstance(cache_n, int | float)
        or not isinstance(prompt_n, int | float)
    ):
        return None
    denominator = cache_n + prompt_n
    return None if denominator == 0 else round(cache_n / denominator, 6)


async def measure_prefix_sample(service, *, label: str, sample_request: LLMGenerationRequest) -> dict[str, object]:
    """Measure a real stream without retaining or printing generated text."""

    input_token_result = await service.count_input_tokens(sample_request)
    started_at = time.monotonic()
    first_sse_ms: int | None = None
    first_reasoning_ms: int | None = None
    first_visible_ms: int | None = None
    completed_event: LLMStreamEvent | None = None
    errors: list[str | None] = []
    async for event in service.stream_generate(sample_request):
        elapsed_ms = round((time.monotonic() - started_at) * 1000)
        if event.kind is LLMStreamEventKind.STARTED and first_sse_ms is None:
            first_sse_ms = elapsed_ms
        elif event.kind is LLMStreamEventKind.REASONING_DELTA and first_reasoning_ms is None:
            first_reasoning_ms = elapsed_ms
        elif event.kind is LLMStreamEventKind.TEXT_DELTA and first_visible_ms is None:
            first_visible_ms = elapsed_ms
        elif event.kind is LLMStreamEventKind.COMPLETED:
            completed_event = event
        elif event.kind is LLMStreamEventKind.ERROR:
            errors.append(event.error_code)
    wall_time_ms = round((time.monotonic() - started_at) * 1000)
    if completed_event is None or errors:
        raise RuntimeError(f"Prefix-cache sample {label} did not complete cleanly.")
    timings = completed_event.provider_metadata.get("timings")
    timing_values = timings if isinstance(timings, dict) else {}
    cache_n = timing_values.get("cache_n")
    prompt_n = timing_values.get("prompt_n")
    return {
        "label": label,
        "input_tokens": input_token_result.input_tokens,
        "cache_n": cache_n,
        "prompt_n": prompt_n,
        "reuse_ratio": cache_reuse_ratio(cache_n, prompt_n),
        "prompt_ms": timing_values.get("prompt_ms"),
        "prompt_per_second": timing_values.get("prompt_per_second"),
        "predicted_n": timing_values.get("predicted_n"),
        "predicted_ms": timing_values.get("predicted_ms"),
        "predicted_per_second": timing_values.get("predicted_per_second"),
        "first_sse_event_ms": first_sse_ms,
        "first_reasoning_delta_ms": first_reasoning_ms,
        "first_visible_content_delta_ms": first_visible_ms,
        "completion_time_ms": wall_time_ms,
        "finish_reason": completed_event.finish_reason,
    }


async def calibrated_prefix_repetitions(service, *, reasoning: ReasoningOptions) -> tuple[int, int]:
    """Use the provider tokenizer rather than character count to target a practical 4K–8K prompt."""

    for repetitions in (160, 224, 288):
        calibration_request = request(
            messages=synthetic_messages(
                stable_prefix=synthetic_stable_prefix(variant="calibration", repetitions=repetitions),
                current_request="Synthetic token calibration request.",
            ),
            reasoning=reasoning,
            max_output_tokens=8,
        )
        input_tokens = (await service.count_input_tokens(calibration_request)).input_tokens
        if 4096 <= input_tokens <= 8192:
            return repetitions, input_tokens
    raise RuntimeError("Unable to calibrate a synthetic stable prefix into the 4K–8K token range.")


async def verify_prefix_cache_baseline(service) -> dict[str, object]:
    """Run public synthetic common-prefix measurements; persistent slot APIs are never used."""

    reasoning_off = ReasoningOptions(mode=ReasoningMode.OFF)
    repetitions, calibration_input_tokens = await calibrated_prefix_repetitions(service, reasoning=reasoning_off)
    experiment_samples: list[dict[str, object]] = []
    for variant in ("alpha", "bravo"):
        stable_prefix = synthetic_stable_prefix(variant=variant, repetitions=repetitions)
        baseline_messages = synthetic_messages(
            stable_prefix=stable_prefix,
            current_request="Return a short public benchmark acknowledgement.",
        )
        append_messages = synthetic_messages(
            stable_prefix=stable_prefix,
            appended=True,
            current_request="Return a short acknowledgement of the appended synthetic turn.",
        )
        changed_suffix_messages = synthetic_messages(
            stable_prefix=stable_prefix,
            appended=True,
            current_request="Return a different short acknowledgement for the current synthetic turn.",
        )
        mutated_prefix = stable_prefix.replace("EARLY POLICY MARKER: baseline", "EARLY POLICY MARKER: mutated", 1)
        mutated_messages = synthetic_messages(
            stable_prefix=mutated_prefix,
            appended=True,
            current_request="Return a short acknowledgement of the appended synthetic turn.",
        )
        experiment_samples.append(
            {
                "variant": variant,
                "cold": await measure_prefix_sample(
                    service,
                    label=f"cold-{variant}",
                    sample_request=request(messages=baseline_messages, reasoning=reasoning_off, max_output_tokens=8),
                ),
                "append": await measure_prefix_sample(
                    service,
                    label=f"append-{variant}",
                    sample_request=request(messages=append_messages, reasoning=reasoning_off, max_output_tokens=8),
                ),
                "suffix_change": await measure_prefix_sample(
                    service,
                    label=f"suffix-{variant}",
                    sample_request=request(messages=changed_suffix_messages, reasoning=reasoning_off, max_output_tokens=8),
                ),
                "early_mutation": await measure_prefix_sample(
                    service,
                    label=f"early-mutation-{variant}",
                    sample_request=request(messages=mutated_messages, reasoning=reasoning_off, max_output_tokens=8),
                ),
            }
        )

    stable_prefix = synthetic_stable_prefix(variant="dynamic-placement", repetitions=repetitions)
    history_messages = (
        LLMMessage(LLMMessageRole.USER, "Synthetic history request with public-only content."),
        LLMMessage(LLMMessageRole.ASSISTANT, "Synthetic history response with public-only content."),
    )
    early_v1 = (
        LLMMessage(LLMMessageRole.SYSTEM, stable_prefix + "\nDYNAMIC KNOWLEDGE: version one."),
        *history_messages,
        LLMMessage(LLMMessageRole.USER, "Return a short synthetic acknowledgement."),
    )
    early_v2 = (
        LLMMessage(LLMMessageRole.SYSTEM, stable_prefix + "\nDYNAMIC KNOWLEDGE: version two."),
        *history_messages,
        LLMMessage(LLMMessageRole.USER, "Return a short synthetic acknowledgement."),
    )
    late_v1 = (
        LLMMessage(LLMMessageRole.SYSTEM, stable_prefix),
        *history_messages,
        LLMMessage(LLMMessageRole.USER, "Return a short synthetic acknowledgement. DYNAMIC KNOWLEDGE: version one."),
    )
    late_v2 = (
        LLMMessage(LLMMessageRole.SYSTEM, stable_prefix),
        *history_messages,
        LLMMessage(LLMMessageRole.USER, "Return a short synthetic acknowledgement. DYNAMIC KNOWLEDGE: version two."),
    )
    dynamic_placement = {
        "dynamic_early_initial": await measure_prefix_sample(
            service,
            label="dynamic-early-v1",
            sample_request=request(messages=early_v1, reasoning=reasoning_off, max_output_tokens=8),
        ),
        "dynamic_early_changed": await measure_prefix_sample(
            service,
            label="dynamic-early-v2",
            sample_request=request(messages=early_v2, reasoning=reasoning_off, max_output_tokens=8),
        ),
        "dynamic_late_initial": await measure_prefix_sample(
            service,
            label="dynamic-late-v1",
            sample_request=request(messages=late_v1, reasoning=reasoning_off, max_output_tokens=8),
        ),
        "dynamic_late_changed": await measure_prefix_sample(
            service,
            label="dynamic-late-v2",
            sample_request=request(messages=late_v2, reasoning=reasoning_off, max_output_tokens=8),
        ),
    }

    correctness_prefix_a = synthetic_stable_prefix(variant="correctness", repetitions=repetitions) + (
        "\nFor this isolated correctness check, answer exactly CACHE-CORRECT-A."
    )
    correctness_prefix_b = correctness_prefix_a.replace("CACHE-CORRECT-A", "CACHE-CORRECT-B", 1)
    correctness_a = await service.generate(
        request(
            messages=synthetic_messages(
                stable_prefix=correctness_prefix_a,
                current_request="Return the required correctness marker.",
            ),
            reasoning=reasoning_off,
            max_output_tokens=8,
        )
    )
    correctness_b = await service.generate(
        request(
            messages=synthetic_messages(
                stable_prefix=correctness_prefix_b,
                current_request="Return the required correctness marker.",
            ),
            reasoning=reasoning_off,
            max_output_tokens=8,
        )
    )
    correctness_result = {
        "early_instruction_a_followed": "CACHE-CORRECT-A" in correctness_a.assistant_text,
        "early_instruction_b_followed": "CACHE-CORRECT-B" in correctness_b.assistant_text,
        "stale_a_not_observed_after_b": "CACHE-CORRECT-A" not in correctness_b.assistant_text,
    }
    if not all(correctness_result.values()):
        raise RuntimeError("The cache correctness smoke test observed possible cross-prompt state leakage.")

    return {
        "cache_prompt_explicitly_sent": False,
        "calibration": {"stable_prefix_repetitions": repetitions, "input_tokens": calibration_input_tokens},
        "individual_samples": experiment_samples,
        "dynamic_placement": dynamic_placement,
        "correctness": correctness_result,
        "persistent_slot_cache": "not_relied_upon",
    }


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

        prefix_cache_baseline = await verify_prefix_cache_baseline(service)

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
            "prefix_cache_baseline": prefix_cache_baseline,
        }
    finally:
        await bridge.aclose()


async def verify_prefix_cache_only() -> dict[str, object]:
    """Run only the opt-in Phase 1B-2C benchmark against the configured Main runtime."""

    runtime_paths = resolve_runtime_paths()
    bridge = LlmRuntimeBridge(config_directory=runtime_paths.config)
    try:
        statuses = await bridge.probe()
        main_status = statuses[RuntimeSlot.MAIN]
        if main_status.state is not RuntimeSlotState.READY:
            raise RuntimeError("The configured Main runtime did not become ready.")
        return {
            "main_state": main_status.state.value,
            "prefix_cache_baseline": await verify_prefix_cache_baseline(bridge.service),
        }
    finally:
        await bridge.aclose()


def main() -> int:
    if os.environ.get(LIVE_TEST_ENVIRONMENT_VARIABLE) != "1":
        print(f"Skipped. Set {LIVE_TEST_ENVIRONMENT_VARIABLE}=1 to run private live-runtime verification.")
        return 0
    try:
        verification = (
            verify_prefix_cache_only()
            if os.environ.get(PREFIX_CACHE_ONLY_ENVIRONMENT_VARIABLE) == "1"
            else verify()
        )
        result = asyncio.run(verification)
    except RuntimeError as error:
        print(f"Live llama.cpp runtime verification failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
