"""Opt-in private verification for the Prompt Workbench discussion-only LLM path.

The script contains no endpoint, credentials, model alias, private knowledge, or
generated response text. It exits successfully unless the operator explicitly
sets LOCAL_AI_CONSOLE_RUN_PROMPT_WORKBENCH_LIVE_TEST=1.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Literal

from local_ai_console_control.config.runtime_paths import initialize_runtime_layout, resolve_runtime_paths
from local_ai_console_control.llm.bridge import LlmRuntimeBridge
from local_ai_console_control.llm.llama_cpp import LlamaCppClientError
from local_ai_console_control.llm.types import (
    GenerationSettings,
    LLMGenerationRequest,
    LLMMessage,
    LLMMessageRole,
    ReasoningMode,
    ReasoningOptions,
    TaskKind,
)
from local_ai_console_control.persistence.database import database_path_for_runtime_data, open_database, upgrade_database
from local_ai_console_control.persistence.service import (
    create_project,
    get_project_state,
    list_messages,
    list_revisions,
    set_project_workflow,
    update_project_state,
)
from local_ai_console_control.prompt_workbench.catalog import PromptWorkbenchCatalog, builtin_prompt_engine_root
from local_ai_console_control.prompt_workbench.discussion import (
    PromptDiscussionCoordinator,
    PromptDiscussionError,
    PromptDiscussionService,
)
from local_ai_console_control.prompt_workbench.context import PromptContextAssembler
from local_ai_console_control.prompt_workbench.knowledge import KnowledgeSourceLoader


LIVE_TEST_ENVIRONMENT_VARIABLE = "LOCAL_AI_CONSOLE_RUN_PROMPT_WORKBENCH_LIVE_TEST"


async def legacy_multi_system_preflight(
    *,
    bridge: LlmRuntimeBridge,
    catalog: PromptWorkbenchCatalog,
    knowledge_loader: KnowledgeSourceLoader,
    project,
    project_state,
) -> dict[str, object]:
    """Reproduce the pre-fix role shape once, without emitting any prompt content."""

    workflow = catalog.get_workflow(project.workflow_profile_id)
    skill = catalog.get_skill(workflow.skill_profile_id)
    context = PromptContextAssembler().assemble(
        skill=skill,
        workflow=workflow,
        mode=project.workflow_mode,
        project=project,
        project_state=project_state,
        accepted_revision=None,
        session_messages=(),
        selected_knowledge=knowledge_loader.load_for_workflow(workflow),
        current_user_message="請只回覆：可以。",
    )
    request = LLMGenerationRequest(
        messages=tuple(contribution.message for contribution in context.contributions),
        task_kind=TaskKind.PROMPT_GENERATION,
        generation=GenerationSettings(max_output_tokens=1024, temperature=0.4, top_p=0.9),
        reasoning=ReasoningOptions(mode=ReasoningMode.ON),
    )
    request_shape = bridge.service.safe_request_shape(request, stream=False)
    try:
        result = await bridge.service.count_input_tokens(request)
    except LlamaCppClientError as error:
        return {
            "result": "rejected",
            "underlying_error_type": type(error).__name__,
            "sanitized_reason": error.kind.value,
            "provider_http_status": error.http_status,
            "request_shape": request_shape,
        }
    return {
        "result": "accepted",
        "input_tokens": result.input_tokens,
        "request_shape": request_shape,
    }


async def run_turn(
    discussion: PromptDiscussionService,
    database_session,
    *,
    session_id: str,
    content: str,
    thinking_mode: Literal["auto", "off", "on"],
) -> dict[str, object]:
    prepared = await discussion.prepare(
        database_session,
        session_id=session_id,
        user_content=content,
        thinking_mode=thinking_mode,
    )
    event_kinds: list[str] = []
    reasoning_delta_count = 0
    text_delta_count = 0
    completed = False
    errors: list[str] = []
    async for event in discussion.stream(database_session, prepared):
        event_kinds.append(event.kind)
        if event.kind == "reasoning_delta":
            reasoning_delta_count += 1
        elif event.kind == "text_delta":
            text_delta_count += 1
        elif event.kind == "completed":
            completed = True
        elif event.kind == "error":
            code = event.data.get("code")
            errors.append(code if isinstance(code, str) else "unknown")
    messages = list_messages(database_session, session_id=session_id)
    assistant = messages[-1] if messages and messages[-1].role == "assistant" else None
    reasoning_stored_separately = False
    if assistant is not None and isinstance(assistant.metadata_json, dict):
        generation = assistant.metadata_json.get("discussion_generation")
        reasoning_stored_separately = isinstance(generation, dict) and (
            "reasoning_content" in generation or reasoning_delta_count == 0
        )
    if not completed or errors or assistant is None or not assistant.content:
        raise RuntimeError("The discussion verification stream did not produce a persisted visible assistant response.")
    return {
        "event_kinds": event_kinds,
        "input_tokens": prepared.input_tokens,
        "native_input_token_preflight": True,
        "request_shape": dict(prepared.request_shape),
        "reasoning_delta_count": reasoning_delta_count,
        "text_delta_count": text_delta_count,
        "reasoning_stored_separately": reasoning_stored_separately,
        "assistant_persisted": True,
    }


async def verify() -> dict[str, object]:
    runtime_paths = resolve_runtime_paths()
    bridge = LlmRuntimeBridge(config_directory=runtime_paths.config)
    try:
        phase_1b_2a_baseline = LLMGenerationRequest(
            messages=(
                LLMMessage(LLMMessageRole.SYSTEM, "Sanitized Phase 1B-2A request-shape baseline."),
                LLMMessage(LLMMessageRole.USER, "Sanitized UTF-8 request-shape baseline."),
            ),
            task_kind=TaskKind.CHAT,
            generation=GenerationSettings(max_output_tokens=32, temperature=0),
            reasoning=ReasoningOptions(mode=ReasoningMode.OFF),
        )
        phase_1b_2a_shape = bridge.service.safe_request_shape(phase_1b_2a_baseline, stream=False)

        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            repository_root = temporary_root / "repository"
            repository_root.mkdir()
            verification_runtime_root = temporary_root / "controller-runtime"
            verification_paths = resolve_runtime_paths(
                repository_root=repository_root,
                environ={"LOCAL_AI_CONSOLE_HOME": str(verification_runtime_root)},
                platform_name="non_windows",
            )
            initialize_runtime_layout(verification_paths)
            database_path = database_path_for_runtime_data(verification_paths.data)
            upgrade_database(database_path)
            database = open_database(database_path)
            try:
                with database.session_factory() as database_session:
                    catalog = PromptWorkbenchCatalog.load(builtin_prompt_engine_root())
                    discussion = PromptDiscussionService(
                        llm_service=bridge.service,
                        catalog=catalog,
                        knowledge_loader=KnowledgeSourceLoader(private_knowledge_root=verification_paths.knowledge),
                        coordinator=PromptDiscussionCoordinator(),
                    )
                    project = create_project(
                        database_session,
                        title="Sanitized live discussion verification",
                        workflow_profile_id="anima_base_v1",
                    )
                    assert project.active_session_id is not None
                    state = get_project_state(database_session, project_id=project.id)
                    legacy_preflight = await legacy_multi_system_preflight(
                        bridge=bridge,
                        catalog=catalog,
                        knowledge_loader=KnowledgeSourceLoader(private_knowledge_root=verification_paths.knowledge),
                        project=project,
                        project_state=state,
                    )
                    first_turn = await run_turn(
                        discussion,
                        database_session,
                        session_id=project.active_session_id,
                        content="請只回覆：可以。",
                        thinking_mode="on",
                    )
                    set_project_workflow(
                        database_session,
                        project_id=project.id,
                        workflow_profile_id="anima_base_v1",
                        workflow_mode="preserve",
                    )
                    update_project_state(
                        database_session,
                        project_id=project.id,
                        objective=state.objective,
                        important_constraints=state.important_constraints,
                        must_preserve=["Maintain generic character traits."],
                        known_problems=state.known_problems,
                        accepted_observations=state.accepted_observations,
                    )
                    second_turn = await run_turn(
                        discussion,
                        database_session,
                        session_id=project.active_session_id,
                        content="請只回覆：已保留。",
                        thinking_mode="auto",
                    )
                    if list_revisions(database_session, project_id=project.id):
                        raise RuntimeError("The discussion-only verification unexpectedly created a Prompt Revision.")
                    return {
                        "runtime_health_probe": "not_run; this verifier exercises the discussion path directly",
                        "phase_1b_2a_request_shape": phase_1b_2a_shape,
                        "legacy_multi_system_preflight": legacy_preflight,
                        "first_turn": first_turn,
                        "second_turn": second_turn,
                        "preserve_mode_context_assembled": True,
                        "prompt_revisions_created": 0,
                        "private_runtime_data_written": "temporary verification runtime only",
                    }
            finally:
                database.dispose()
    finally:
        await bridge.aclose()


def main() -> int:
    if os.environ.get(LIVE_TEST_ENVIRONMENT_VARIABLE) != "1":
        print(f"Skipped. Set {LIVE_TEST_ENVIRONMENT_VARIABLE}=1 to run private live discussion verification.")
        return 0
    try:
        result = asyncio.run(verify())
    except PromptDiscussionError as error:
        diagnostic = error.diagnostic.safe_summary() if error.diagnostic is not None else {}
        print(
            json.dumps(
                {
                    "verification": "failed",
                    "error_code": error.code,
                    "user_message": error.message,
                    "diagnostic": diagnostic,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    except RuntimeError as error:
        print(f"Live Prompt Workbench discussion verification failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
