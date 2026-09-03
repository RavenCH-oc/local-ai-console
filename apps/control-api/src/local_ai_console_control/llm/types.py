"""Provider-neutral LLM request, response, routing, and streaming types."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Mapping, TypeAlias


JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]


class TaskKind(StrEnum):
    """Task kinds defined by the Phase 0C shared contracts."""

    CHAT = "chat"
    PROMPT_GENERATION = "prompt_generation"
    CONTEXT_COMPRESSION = "context_compression"


class RuntimeTargetPreference(StrEnum):
    """Caller preference; `auto` is routing policy rather than a runtime slot."""

    AUTO = "auto"
    MAIN = "main"
    UTILITY = "utility"


class RuntimeSlot(StrEnum):
    """Known physical/logical runtime capacity slots."""

    MAIN = "main"
    UTILITY = "utility"


class RuntimeSlotState(StrEnum):
    """Safe runtime lifecycle states surfaced by the Controller status API."""

    UNCONFIGURED = "unconfigured"
    UNAVAILABLE = "unavailable"
    CHECKING = "checking"
    LOADING = "loading"
    READY = "ready"
    ERROR = "error"


class LLMMessageRole(StrEnum):
    """Portable chat message roles supported by the initial bridge."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ReasoningMode(StrEnum):
    """Provider-neutral reasoning intent; exact model semantics remain adapter-specific."""

    DEFAULT = "default"
    OFF = "off"
    ON = "on"
    AUTO = "auto"


class LLMStreamEventKind(StrEnum):
    """Normalized stream events; raw SSE data does not escape the provider adapter."""

    STARTED = "started"
    TEXT_DELTA = "text_delta"
    REASONING_DELTA = "reasoning_delta"
    USAGE = "usage"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class LLMMessage:
    role: LLMMessageRole
    content: str

    def __post_init__(self) -> None:
        if not self.content:
            raise ValueError("LLM message content cannot be empty.")


@dataclass(frozen=True, slots=True)
class GenerationSettings:
    """The first stable generic generation controls, with provider mapping centralized later."""

    max_output_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    min_p: float | None = None
    repeat_penalty: float | None = None
    seed: int | None = None
    stop: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.max_output_tokens is not None and self.max_output_tokens < 1:
            raise ValueError("max_output_tokens must be at least 1.")
        if self.temperature is not None and self.temperature < 0:
            raise ValueError("temperature cannot be negative.")
        if self.top_p is not None and not 0 <= self.top_p <= 1:
            raise ValueError("top_p must be between 0 and 1.")
        if self.top_k is not None and self.top_k < 1:
            raise ValueError("top_k must be at least 1.")
        if self.min_p is not None and not 0 <= self.min_p <= 1:
            raise ValueError("min_p must be between 0 and 1.")
        if self.repeat_penalty is not None and self.repeat_penalty <= 0:
            raise ValueError("repeat_penalty must be positive.")
        if any(not value for value in self.stop):
            raise ValueError("stop values cannot be empty.")


@dataclass(frozen=True, slots=True)
class ReasoningOptions:
    mode: ReasoningMode = ReasoningMode.DEFAULT
    budget: int | None = None
    enable_realtime_control: bool = False

    def __post_init__(self) -> None:
        if self.budget is not None and self.budget < 0:
            raise ValueError("reasoning budget cannot be negative.")


@dataclass(frozen=True, slots=True)
class StructuredOutputSpec:
    """A provider-neutral JSON Schema request for a future structured response consumer."""

    json_schema: Mapping[str, JsonValue]
    name: str | None = None

    def __post_init__(self) -> None:
        if not self.json_schema:
            raise ValueError("structured output JSON Schema cannot be empty.")


@dataclass(frozen=True, slots=True)
class LLMGenerationRequest:
    messages: tuple[LLMMessage, ...]
    task_kind: TaskKind
    target_preference: RuntimeTargetPreference = RuntimeTargetPreference.AUTO
    model_preference: str | None = None
    generation: GenerationSettings = field(default_factory=GenerationSettings)
    reasoning: ReasoningOptions = field(default_factory=ReasoningOptions)
    structured_output: StructuredOutputSpec | None = None

    def __post_init__(self) -> None:
        if not self.messages:
            raise ValueError("LLM generation requests require at least one message.")
        if self.model_preference is not None and not self.model_preference.strip():
            raise ValueError("model_preference cannot be blank.")


@dataclass(frozen=True, slots=True)
class LLMUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class LLMGenerationResult:
    assistant_text: str
    finish_reason: str | None
    usage: LLMUsage | None
    provider_metadata: Mapping[str, JsonValue]


@dataclass(frozen=True, slots=True)
class LLMTokenCountResult:
    input_tokens: int
    provider_metadata: Mapping[str, JsonValue]


@dataclass(frozen=True, slots=True)
class LLMRuntimeCapabilities:
    """Small capability snapshot; detailed cross-provider contracts remain a later phase."""

    supports_realtime_reasoning_end: bool | None = None
    supports_per_request_reasoning_budget: bool | None = None


@dataclass(frozen=True, slots=True)
class LLMStreamEvent:
    kind: LLMStreamEventKind
    text: str | None = None
    usage: LLMUsage | None = None
    provider_metadata: Mapping[str, JsonValue] = field(default_factory=dict)
    error_code: str | None = None
    completion_id: str | None = None
    finish_reason: str | None = None
