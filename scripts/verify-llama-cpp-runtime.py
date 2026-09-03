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

from local_ai_console_control.config.runtime_paths import resolve_runtime_paths
from local_ai_console_control.llm.bridge import LlmRuntimeBridge
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
    StructuredOutputSpec,
    TaskKind,
)


LIVE_TEST_ENVIRONMENT_VARIABLE = "LOCAL_AI_CONSOLE_RUN_LIVE_LLM_TESTS"


def request(*, messages: tuple[LLMMessage, ...], structured_output: StructuredOutputSpec | None = None) -> LLMGenerationRequest:
    return LLMGenerationRequest(
        messages=messages,
        task_kind=TaskKind.CHAT,
        generation=GenerationSettings(max_output_tokens=32, temperature=0),
        reasoning=ReasoningOptions(mode=ReasoningMode.OFF),
        structured_output=structured_output,
    )


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
        chat_request = request(messages=chat_messages)
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

        stream_events = [event async for event in service.stream_generate(chat_request)]
        if not any(event.kind is LLMStreamEventKind.TEXT_DELTA for event in stream_events) or not any(
            event.kind is LLMStreamEventKind.COMPLETED for event in stream_events
        ):
            raise RuntimeError("The streaming response did not produce typed text and completion events.")

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
            "streaming": True,
            "timing_fields": timing_fields,
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
