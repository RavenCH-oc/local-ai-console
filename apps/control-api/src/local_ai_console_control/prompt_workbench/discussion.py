"""Prompt Workbench discussion orchestration over the shared LLM service."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from enum import StrEnum
import math
from typing import Literal

from sqlalchemy.orm import Session

from local_ai_console_control.llm.llama_cpp import LlamaCppClientError, LlamaCppClientErrorKind
from local_ai_console_control.llm.resolver import RuntimeResolutionError
from local_ai_console_control.llm.service import LLMService
from local_ai_console_control.llm.types import (
    GenerationSettings,
    JsonValue,
    LLMGenerationRequest,
    LLMStreamEventKind,
    LLMUsage,
    ReasoningMode,
    ReasoningOptions,
    RuntimeTargetPreference,
    TaskKind,
)
from local_ai_console_control.persistence.models import PromptMessage, PromptProject
from local_ai_console_control.persistence.service import (
    PromptWorkbenchError,
    append_message,
    get_active_discussion_project,
    get_project_state,
    get_revision,
    list_messages,
)
from local_ai_console_control.prompt_workbench.catalog import PromptWorkbenchCatalog, PromptWorkbenchCatalogError
from local_ai_console_control.prompt_workbench.context import PromptContextAssembler
from local_ai_console_control.prompt_workbench.knowledge import KnowledgeSourceLoadError, KnowledgeSourceLoader


MAX_RUNTIME_CONTEXT_TOKENS = 98_304
CONTEXT_SAFETY_HEADROOM_TOKENS = 1_024
MAX_PERSISTED_REASONING_CHARACTERS = 32_000
_SAFE_TIMING_FIELDS = frozenset(
    {
        "cache_n",
        "prompt_n",
        "prompt_ms",
        "prompt_per_second",
        "predicted_n",
        "predicted_ms",
        "predicted_per_second",
    }
)


@dataclass(frozen=True, slots=True)
class PromptDiscussionGenerationProfile:
    """A conservative server-owned discussion profile, independent from React controls."""

    id: str
    max_context_tokens: int
    max_output_tokens: int
    temperature: float
    top_p: float

    def generation_settings(self) -> GenerationSettings:
        return GenerationSettings(
            max_output_tokens=self.max_output_tokens,
            temperature=self.temperature,
            top_p=self.top_p,
        )


ANIMA_BASE_V1_DISCUSSION_PROFILE = PromptDiscussionGenerationProfile(
    id="anima_base_v1_discussion",
    max_context_tokens=MAX_RUNTIME_CONTEXT_TOKENS,
    max_output_tokens=1_024,
    temperature=0.4,
    top_p=0.9,
)


class PromptDiscussionError(RuntimeError):
    """A safe failure that can be shown to the local Prompt Workbench user."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int,
        diagnostic: "PromptDiscussionDiagnostic | None" = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.diagnostic = diagnostic
        super().__init__(message)


class PromptDiscussionBusyError(PromptDiscussionError):
    def __init__(self, *, same_session: bool) -> None:
        code = "session_busy" if same_session else "runtime_busy"
        message = (
            "A discussion is already running for this Prompt Session."
            if same_session
            else "The MAIN runtime is busy with another Prompt Workbench discussion."
        )
        super().__init__(code, message, status_code=409)


class PromptDiscussionPrepareStage(StrEnum):
    """Safe internal milestones used by the opt-in verifier, never sent to React."""

    PROJECT_SESSION_LOAD = "project_session_load"
    WORKFLOW_SKILL_LOAD = "workflow_skill_load"
    KNOWLEDGE_LOAD = "knowledge_load"
    CONTEXT_ASSEMBLY = "context_assembly"
    MESSAGE_VALIDATION = "message_validation"
    RUNTIME_RESOLUTION = "runtime_resolution"
    GENERATION_SETTINGS = "generation_settings"
    INPUT_TOKEN_PREFLIGHT = "input_token_preflight"
    CONTEXT_RESERVE_CHECK = "context_reserve_check"
    STREAM_CREATION = "stream_creation"


@dataclass(frozen=True, slots=True)
class PromptDiscussionDiagnostic:
    """Prompt-free, credential-free detail for explicit local diagnostics only."""

    stage: PromptDiscussionPrepareStage
    cause_type: str | None = None
    cause_category: str | None = None
    provider_http_status: int | None = None
    request_shape: Mapping[str, JsonValue] | None = None

    def safe_summary(self) -> dict[str, JsonValue]:
        summary: dict[str, JsonValue] = {"stage": self.stage.value}
        if self.cause_type is not None:
            summary["underlying_error_type"] = self.cause_type
        if self.cause_category is not None:
            summary["sanitized_reason"] = self.cause_category
        if self.provider_http_status is not None:
            summary["provider_http_status"] = self.provider_http_status
        if self.request_shape is not None:
            summary["request_shape"] = dict(self.request_shape)
        return summary


class PromptDiscussionCoordinator:
    """Permit one generation per Session and one total generation on today's single Main runtime."""

    def __init__(self) -> None:
        self._active_session_ids: set[str] = set()
        self._active_runtime_session_id: str | None = None
        self._lock = asyncio.Lock()

    async def acquire(self, session_id: str) -> None:
        async with self._lock:
            if session_id in self._active_session_ids:
                raise PromptDiscussionBusyError(same_session=True)
            if self._active_runtime_session_id is not None:
                raise PromptDiscussionBusyError(same_session=False)
            self._active_session_ids.add(session_id)
            self._active_runtime_session_id = session_id

    async def release(self, session_id: str) -> None:
        async with self._lock:
            self._active_session_ids.discard(session_id)
            if self._active_runtime_session_id == session_id:
                self._active_runtime_session_id = None


@dataclass(frozen=True, slots=True)
class PreparedPromptDiscussion:
    """The complete, preflighted server-owned request ready for one stream."""

    session_id: str
    project: PromptProject
    user_message: PromptMessage
    request: LLMGenerationRequest
    input_tokens: int
    profile: PromptDiscussionGenerationProfile
    request_shape: Mapping[str, JsonValue]


@dataclass(frozen=True, slots=True)
class PromptDiscussionStreamEvent:
    """Controller-owned stream event; no llama.cpp SSE or identifiers leave this boundary."""

    kind: Literal["started", "reasoning_delta", "text_delta", "completed", "cancelled", "error"]
    data: Mapping[str, JsonValue]


def _profile_for_workflow(workflow_id: str) -> PromptDiscussionGenerationProfile:
    if workflow_id == "anima_base_v1":
        return ANIMA_BASE_V1_DISCUSSION_PROFILE
    raise PromptDiscussionError("workflow_unavailable", "The selected Prompt Workbench workflow is unavailable.", status_code=422)


def _reasoning_options(value: Literal["auto", "off", "on"]) -> ReasoningOptions:
    return ReasoningOptions(mode=ReasoningMode(value))


def _diagnostic_for_error(
    stage: PromptDiscussionPrepareStage,
    error: Exception,
    *,
    request_shape: Mapping[str, JsonValue] | None = None,
) -> PromptDiscussionDiagnostic:
    if isinstance(error, LlamaCppClientError):
        return PromptDiscussionDiagnostic(
            stage=stage,
            cause_type=type(error).__name__,
            cause_category=error.kind.value,
            provider_http_status=error.http_status,
            request_shape=request_shape,
        )
    return PromptDiscussionDiagnostic(
        stage=stage,
        cause_type=type(error).__name__,
        cause_category="application_error",
        request_shape=request_shape,
    )


def _safe_provider_error(
    error: LlamaCppClientError,
    *,
    request_shape: Mapping[str, JsonValue],
) -> PromptDiscussionError:
    messages: dict[LlamaCppClientErrorKind, tuple[str, int]] = {
        LlamaCppClientErrorKind.AUTHENTICATION_FAILURE: ("Runtime authentication failed.", 503),
        LlamaCppClientErrorKind.TIMEOUT: ("Input-token preflight timed out.", 504),
        LlamaCppClientErrorKind.CONNECTION_FAILURE: ("MAIN runtime unavailable.", 503),
    }
    code, message, status_code = "input_token_preflight_failed", "Input-token preflight failed.", 502
    if error.kind in messages:
        message, status_code = messages[error.kind]
        code = error.kind.value
    return PromptDiscussionError(
        code,
        message,
        status_code=status_code,
        diagnostic=_diagnostic_for_error(
            PromptDiscussionPrepareStage.INPUT_TOKEN_PREFLIGHT,
            error,
            request_shape=request_shape,
        ),
    )


def _safe_prepare_error(
    stage: PromptDiscussionPrepareStage,
    error: Exception,
    *,
    request_shape: Mapping[str, JsonValue] | None,
) -> PromptDiscussionError:
    messages: dict[PromptDiscussionPrepareStage, tuple[str, str, int]] = {
        PromptDiscussionPrepareStage.PROJECT_SESSION_LOAD: (
            "project_session_unavailable",
            "The selected Prompt Project or Session could not be loaded.",
            500,
        ),
        PromptDiscussionPrepareStage.WORKFLOW_SKILL_LOAD: (
            "workflow_unavailable",
            "The selected Prompt Workbench workflow is unavailable.",
            422,
        ),
        PromptDiscussionPrepareStage.KNOWLEDGE_LOAD: (
            "context_formatting_failed",
            "Prompt context formatting failed.",
            400,
        ),
        PromptDiscussionPrepareStage.CONTEXT_ASSEMBLY: (
            "context_formatting_failed",
            "Prompt context formatting failed.",
            400,
        ),
        PromptDiscussionPrepareStage.MESSAGE_VALIDATION: (
            "context_formatting_failed",
            "Prompt context formatting failed.",
            400,
        ),
        PromptDiscussionPrepareStage.RUNTIME_RESOLUTION: (
            "runtime_unavailable",
            "MAIN runtime unavailable.",
            503,
        ),
        PromptDiscussionPrepareStage.GENERATION_SETTINGS: (
            "generation_settings_failed",
            "Generation settings could not be constructed.",
            500,
        ),
        PromptDiscussionPrepareStage.INPUT_TOKEN_PREFLIGHT: (
            "input_token_preflight_failed",
            "Input-token preflight failed.",
            502,
        ),
        PromptDiscussionPrepareStage.CONTEXT_RESERVE_CHECK: (
            "context_overflow",
            "Prompt context is too large for the current runtime.",
            422,
        ),
    }
    code, message, status_code = messages[stage]
    return PromptDiscussionError(
        code,
        message,
        status_code=status_code,
        diagnostic=_diagnostic_for_error(stage, error, request_shape=request_shape),
    )


def _stream_error_message(code: str | None) -> str:
    messages = {
        LlamaCppClientErrorKind.AUTHENTICATION_FAILURE.value: "Runtime authentication failed.",
        LlamaCppClientErrorKind.TIMEOUT.value: "Generation could not start before the runtime timed out.",
        LlamaCppClientErrorKind.CONNECTION_FAILURE.value: "MAIN runtime unavailable.",
        LlamaCppClientErrorKind.MALFORMED_STREAM.value: "The MAIN runtime returned an invalid discussion stream.",
    }
    return messages.get(code, "Generation could not start.")


def _safe_usage(value: LLMUsage | None) -> dict[str, JsonValue]:
    if value is None:
        return {}
    usage: dict[str, JsonValue] = {}
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        count = getattr(value, key)
        if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
            usage[key] = count
    return usage


def _safe_timings(provider_metadata: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    timings = provider_metadata.get("timings")
    if not isinstance(timings, dict):
        return {}
    safe: dict[str, JsonValue] = {}
    for key, value in timings.items():
        if key in _SAFE_TIMING_FIELDS and isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value) and value >= 0:
            safe[key] = value
    return safe


class PromptDiscussionService:
    """Persist user turns, assemble context, preflight, and persist a completed visible answer once."""

    def __init__(
        self,
        *,
        llm_service: LLMService,
        catalog: PromptWorkbenchCatalog,
        knowledge_loader: KnowledgeSourceLoader,
        coordinator: PromptDiscussionCoordinator,
    ) -> None:
        self._llm_service = llm_service
        self._catalog = catalog
        self._knowledge_loader = knowledge_loader
        self._coordinator = coordinator

    async def prepare(
        self,
        session: Session,
        *,
        session_id: str,
        user_content: str,
        thinking_mode: Literal["auto", "off", "on"],
    ) -> PreparedPromptDiscussion:
        """Persist the raw user turn, then perform native token-count preflight before streaming."""

        await self._coordinator.acquire(session_id)
        stage = PromptDiscussionPrepareStage.PROJECT_SESSION_LOAD
        request_shape: Mapping[str, JsonValue] | None = None
        try:
            project, _ = get_active_discussion_project(session, session_id=session_id)
            stage = PromptDiscussionPrepareStage.WORKFLOW_SKILL_LOAD
            try:
                workflow = self._catalog.get_workflow(project.workflow_profile_id)
                skill = self._catalog.get_skill(workflow.skill_profile_id)
            except PromptWorkbenchCatalogError as error:
                raise PromptDiscussionError(
                    "workflow_unavailable", "The selected Prompt Workbench workflow is unavailable.", status_code=422
                ) from error

            stage = PromptDiscussionPrepareStage.GENERATION_SETTINGS
            profile = _profile_for_workflow(workflow.id)
            stage = PromptDiscussionPrepareStage.PROJECT_SESSION_LOAD
            user_message = append_message(
                session,
                session_id=session_id,
                role="user",
                content=user_content,
                metadata=None,
            )
            project_state = get_project_state(session, project_id=project.id)
            accepted_revision = get_revision(session, revision_id=project.current_revision_id) if project.current_revision_id else None
            stage = PromptDiscussionPrepareStage.KNOWLEDGE_LOAD
            try:
                selected_knowledge = self._knowledge_loader.load_for_workflow(workflow)
            except KnowledgeSourceLoadError as error:
                raise PromptDiscussionError(
                    "context_formatting_failed",
                    "Prompt context formatting failed.",
                    status_code=400,
                    diagnostic=_diagnostic_for_error(stage, error),
                ) from error
            stage = PromptDiscussionPrepareStage.CONTEXT_ASSEMBLY
            try:
                session_history = tuple(
                    message for message in list_messages(session, session_id=session_id) if message.id != user_message.id
                )
                context = PromptContextAssembler().assemble(
                    skill=skill,
                    workflow=workflow,
                    mode=project.workflow_mode,
                    project=project,
                    project_state=project_state,
                    accepted_revision=accepted_revision,
                    session_messages=session_history,
                    selected_knowledge=selected_knowledge,
                    current_user_message=user_message.content,
                )
            except (KnowledgeSourceLoadError, ValueError) as error:
                raise PromptDiscussionError(
                    "context_formatting_failed",
                    "Prompt context formatting failed.",
                    status_code=400,
                    diagnostic=_diagnostic_for_error(stage, error),
                ) from error

            stage = PromptDiscussionPrepareStage.MESSAGE_VALIDATION
            try:
                request = LLMGenerationRequest(
                    messages=context.messages,
                    task_kind=TaskKind.PROMPT_GENERATION,
                    target_preference=RuntimeTargetPreference.AUTO,
                    generation=profile.generation_settings(),
                    reasoning=_reasoning_options(thinking_mode),
                )
            except ValueError as error:
                raise PromptDiscussionError(
                    "context_formatting_failed",
                    "Prompt context formatting failed.",
                    status_code=400,
                    diagnostic=_diagnostic_for_error(stage, error),
                ) from error

            stage = PromptDiscussionPrepareStage.RUNTIME_RESOLUTION
            self._llm_service.resolve_slot(request)
            request_shape = self._llm_service.safe_request_shape(request, stream=False)
            stage = PromptDiscussionPrepareStage.INPUT_TOKEN_PREFLIGHT
            try:
                input_tokens = (await self._llm_service.count_input_tokens(request)).input_tokens
            except RuntimeResolutionError as error:
                raise PromptDiscussionError(
                    "runtime_unavailable",
                    "MAIN runtime unavailable.",
                    status_code=503,
                    diagnostic=_diagnostic_for_error(stage, error, request_shape=request_shape),
                ) from error
            except LlamaCppClientError as error:
                raise _safe_provider_error(error, request_shape=request_shape) from error
            stage = PromptDiscussionPrepareStage.CONTEXT_RESERVE_CHECK
            if input_tokens + profile.max_output_tokens + CONTEXT_SAFETY_HEADROOM_TOKENS > profile.max_context_tokens:
                raise PromptDiscussionError(
                    "context_overflow",
                    "Prompt context is too large for the current runtime.",
                    status_code=422,
                )
            return PreparedPromptDiscussion(
                session_id=session_id,
                project=project,
                user_message=user_message,
                request=request,
                input_tokens=input_tokens,
                profile=profile,
                request_shape=request_shape,
            )
        except (PromptDiscussionError, PromptWorkbenchError):
            await self._coordinator.release(session_id)
            raise
        except asyncio.CancelledError:
            session.rollback()
            await self._coordinator.release(session_id)
            raise
        except Exception as error:
            session.rollback()
            await self._coordinator.release(session_id)
            raise _safe_prepare_error(stage, error, request_shape=request_shape) from error

    async def stream(
        self,
        session: Session,
        prepared: PreparedPromptDiscussion,
    ) -> AsyncIterator[PromptDiscussionStreamEvent]:
        """Stream only separated deltas and write one assistant row after a successful completion."""

        visible_parts: list[str] = []
        reasoning_parts: list[str] = []
        last_usage: LLMUsage | None = None
        last_provider_metadata: Mapping[str, JsonValue] = {}
        provider_stream = self._llm_service.stream_generate(prepared.request)
        try:
            yield PromptDiscussionStreamEvent(
                kind="started",
                data={
                    "user_message_id": prepared.user_message.id,
                    "input_tokens": prepared.input_tokens,
                    "max_output_tokens": prepared.profile.max_output_tokens,
                },
            )
            async for event in provider_stream:
                if event.kind is LLMStreamEventKind.TEXT_DELTA and event.text:
                    visible_parts.append(event.text)
                    yield PromptDiscussionStreamEvent(kind="text_delta", data={"text": event.text})
                elif event.kind is LLMStreamEventKind.REASONING_DELTA and event.text:
                    reasoning_parts.append(event.text)
                    yield PromptDiscussionStreamEvent(kind="reasoning_delta", data={"text": event.text})
                elif event.kind is LLMStreamEventKind.USAGE:
                    last_usage = event.usage or last_usage
                    last_provider_metadata = event.provider_metadata or last_provider_metadata
                elif event.kind is LLMStreamEventKind.ERROR:
                    error_code = event.error_code or "provider_failure"
                    if error_code == "cancelled":
                        yield PromptDiscussionStreamEvent(kind="cancelled", data={})
                        return
                    yield PromptDiscussionStreamEvent(
                        kind="error",
                        data={
                            "code": error_code,
                            "message": _stream_error_message(error_code),
                        },
                    )
                    return
                elif event.kind is LLMStreamEventKind.COMPLETED:
                    last_usage = event.usage or last_usage
                    last_provider_metadata = event.provider_metadata or last_provider_metadata
                    visible_content = "".join(visible_parts).strip()
                    if not visible_content:
                        yield PromptDiscussionStreamEvent(
                            kind="error",
                            data={
                                "code": "empty_assistant_response",
                                "message": "The MAIN runtime completed without a visible assistant response.",
                            },
                        )
                        return
                    reasoning_content = "".join(reasoning_parts)
                    reasoning_truncated = len(reasoning_content) > MAX_PERSISTED_REASONING_CHARACTERS
                    generation_metadata: dict[str, JsonValue] = {
                        "workflow_profile_id": prepared.project.workflow_profile_id,
                        "generation_profile_id": prepared.profile.id,
                        "input_tokens": prepared.input_tokens,
                        "reasoning_mode": prepared.request.reasoning.mode.value,
                    }
                    provider = last_provider_metadata.get("provider")
                    if provider == "llama_cpp":
                        generation_metadata["provider"] = provider
                    if event.finish_reason and len(event.finish_reason) <= 80:
                        generation_metadata["finish_reason"] = event.finish_reason
                    usage = _safe_usage(last_usage)
                    if usage:
                        generation_metadata["usage"] = usage
                    timings = _safe_timings(last_provider_metadata)
                    if timings:
                        generation_metadata["timings"] = timings
                    if reasoning_content:
                        generation_metadata["reasoning_content"] = reasoning_content[:MAX_PERSISTED_REASONING_CHARACTERS]
                        generation_metadata["reasoning_truncated"] = reasoning_truncated
                    try:
                        assistant_message = append_message(
                            session,
                            session_id=prepared.session_id,
                            role="assistant",
                            content=visible_content,
                            metadata={"discussion_generation": generation_metadata},
                        )
                    except Exception:
                        session.rollback()
                        yield PromptDiscussionStreamEvent(
                            kind="error",
                            data={
                                "code": "persistence_failure",
                                "message": "The response completed but could not be saved to the local discussion.",
                            },
                        )
                        return
                    yield PromptDiscussionStreamEvent(
                        kind="completed",
                        data={
                            "assistant_message_id": assistant_message.id,
                            "finish_reason": event.finish_reason or "completed",
                            "input_tokens": prepared.input_tokens,
                            "timings": timings,
                        },
                    )
                    return
            yield PromptDiscussionStreamEvent(
                kind="error",
                data={
                    "code": "unexpected_stream_end",
                    "message": "The MAIN runtime ended the discussion stream unexpectedly.",
                },
            )
        except asyncio.CancelledError:
            # Client abort closes the provider stream; incomplete text is intentionally never persisted.
            raise
        except RuntimeResolutionError:
            yield PromptDiscussionStreamEvent(
                kind="error",
                data={"code": "runtime_unavailable", "message": "MAIN runtime unavailable."},
            )
        except LlamaCppClientError as error:
            yield PromptDiscussionStreamEvent(
                kind="error",
                data={"code": error.kind.value, "message": _stream_error_message(error.kind.value)},
            )
        except Exception:
            yield PromptDiscussionStreamEvent(
                kind="error",
                data={"code": "generation_start_failed", "message": "Generation could not start."},
            )
        finally:
            closer = getattr(provider_stream, "aclose", None)
            if callable(closer):
                await closer()
            await self._coordinator.release(prepared.session_id)
