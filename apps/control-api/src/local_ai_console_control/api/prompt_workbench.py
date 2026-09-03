"""Validated local REST API for private Prompt Workbench data."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator
from sqlalchemy.orm import Session

from local_ai_console_control.persistence.database import Database
from local_ai_console_control.persistence.models import (
    PromptMessage,
    PromptProject,
    PromptProjectState,
    PromptRevision,
    PromptSession,
)
from local_ai_console_control.persistence.service import (
    DEFAULT_WORKFLOW_PROFILE_ID,
    DEFAULT_WORKFLOW_MODE,
    PromptWorkbenchConflictError,
    PromptWorkbenchError,
    PromptWorkbenchNotFoundError,
    accept_revision,
    append_message,
    archive_project,
    create_project,
    create_proposed_revision,
    create_session,
    discard_revision,
    get_project as get_prompt_project,
    get_project_state,
    get_revision as get_prompt_revision,
    get_session as get_prompt_session,
    list_messages,
    list_projects,
    list_revisions,
    list_sessions,
    rename_project,
    set_project_workflow,
    update_project_state,
    utc_timestamp,
)
from local_ai_console_control.prompt_workbench.catalog import PromptWorkbenchCatalog, PromptWorkbenchCatalogError
from local_ai_console_control.prompt_workbench.context import PromptContextAssembler
from local_ai_console_control.prompt_workbench.knowledge import KnowledgeSourceLoadError, KnowledgeSourceLoader


router = APIRouter(prefix="/api", tags=["prompt-workbench"])


def _database_session(request: Request):
    database: Database = request.app.state.database
    with database.session_factory() as session:
        yield session


DatabaseSession = Annotated[Session, Depends(_database_session)]


def _raise_http_error(error: PromptWorkbenchError) -> None:
    if isinstance(error, PromptWorkbenchNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    if isinstance(error, PromptWorkbenchConflictError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Prompt Workbench request could not be completed.") from error


def _catalog(request: Request) -> PromptWorkbenchCatalog:
    return request.app.state.prompt_workbench_catalog


def _validate_workflow_selection(catalog: PromptWorkbenchCatalog, workflow_profile_id: str, workflow_mode: str) -> None:
    try:
        workflow = catalog.get_workflow(workflow_profile_id)
    except PromptWorkbenchCatalogError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Prompt Workbench workflow is unavailable.") from error
    if workflow_mode not in workflow.supported_modes:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Prompt Workbench mode is unavailable.")


def _required_text(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("This field cannot be empty.")
    return normalized


def _normalized_list(values: list[str]) -> list[str]:
    normalized = [_required_text(value) for value in values]
    return normalized


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PromptProjectResponse(ApiModel):
    id: str
    title: str
    workflow_profile_id: str
    workflow_mode: Literal["stable", "balanced", "detailed", "preserve"]
    created_at: datetime
    updated_at: datetime
    active_session_id: str | None
    current_revision_id: str | None
    status: Literal["active", "archived"]
    archived_at: datetime | None


class PromptSessionResponse(ApiModel):
    id: str
    project_id: str
    title: str | None
    status: Literal["active", "closed"]
    created_at: datetime
    updated_at: datetime


class PromptMessageResponse(ApiModel):
    id: str
    session_id: str
    role: Literal["user", "assistant", "system", "tool"]
    content: str
    metadata: dict[str, JsonValue] | None
    created_at: datetime


class PromptProjectStateResponse(ApiModel):
    id: str
    project_id: str
    objective: str
    important_constraints: list[str]
    must_preserve: list[str]
    known_problems: list[str]
    accepted_observations: list[str]
    updated_at: datetime


class PromptRevisionResponse(ApiModel):
    id: str
    project_id: str
    parent_revision_id: str | None
    positive_prompt: str
    negative_prompt: str
    parameters: dict[str, JsonValue]
    change_log: str
    status: Literal["proposed", "accepted", "discarded"]
    created_at: datetime


class CreateProjectRequest(ApiModel):
    title: str = Field(max_length=200)
    workflow_profile_id: str = Field(default=DEFAULT_WORKFLOW_PROFILE_ID, max_length=100)
    workflow_mode: Literal["stable", "balanced", "detailed", "preserve"] = DEFAULT_WORKFLOW_MODE

    @field_validator("title", "workflow_profile_id")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        return _required_text(value)


class RenameProjectRequest(ApiModel):
    title: str = Field(max_length=200)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        return _required_text(value)


class UpdateProjectWorkflowRequest(ApiModel):
    workflow_profile_id: str = Field(max_length=100)
    workflow_mode: Literal["stable", "balanced", "detailed", "preserve"]

    @field_validator("workflow_profile_id")
    @classmethod
    def validate_workflow_profile_id(cls, value: str) -> str:
        return _required_text(value)


class KnowledgeSourceResponse(ApiModel):
    id: str
    label: str
    source_kind: Literal["built_in", "private_runtime"]
    stability: Literal["stable", "snapshot", "append_only", "dynamic"]


class PromptWorkflowResponse(ApiModel):
    id: str
    display_name: str
    model_family: str
    supported_modes: list[Literal["stable", "balanced", "detailed", "preserve"]]
    default_mode: Literal["stable", "balanced", "detailed", "preserve"]
    knowledge_sources: list[KnowledgeSourceResponse]


class ContextContributionPreviewResponse(ApiModel):
    label: str
    kind: str
    source: str
    stability: Literal["stable", "snapshot", "append_only", "dynamic"]
    character_count: int
    token_count: int | None


class PromptContextPreviewResponse(ApiModel):
    workflow_profile_id: str
    workflow_mode: Literal["stable", "balanced", "detailed", "preserve"]
    contributions: list[ContextContributionPreviewResponse]


class CreateSessionRequest(ApiModel):
    title: str | None = Field(default=None, max_length=200)

    @field_validator("title")
    @classmethod
    def normalize_optional_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class AppendMessageRequest(ApiModel):
    role: Literal["user", "assistant", "system", "tool"]
    content: str
    metadata: dict[str, JsonValue] | None = None

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        return _required_text(value)


class UpdateProjectStateRequest(ApiModel):
    objective: str = ""
    important_constraints: list[str] = Field(default_factory=list)
    must_preserve: list[str] = Field(default_factory=list)
    known_problems: list[str] = Field(default_factory=list)
    accepted_observations: list[str] = Field(default_factory=list)

    @field_validator(
        "important_constraints",
        "must_preserve",
        "known_problems",
        "accepted_observations",
    )
    @classmethod
    def validate_state_lists(cls, values: list[str]) -> list[str]:
        return _normalized_list(values)


class CreateRevisionRequest(ApiModel):
    parent_revision_id: str | None = Field(default=None, max_length=40)
    positive_prompt: str
    negative_prompt: str = ""
    parameters: dict[str, JsonValue] = Field(default_factory=dict)
    change_log: str

    @field_validator("positive_prompt", "change_log")
    @classmethod
    def validate_required_revision_text(cls, value: str) -> str:
        return _required_text(value)

    @field_validator("negative_prompt")
    @classmethod
    def normalize_negative_prompt(cls, value: str) -> str:
        return value.strip()


def _project_response(project: PromptProject) -> PromptProjectResponse:
    return PromptProjectResponse(
        id=project.id,
        title=project.title,
        workflow_profile_id=project.workflow_profile_id,
        workflow_mode=project.workflow_mode,
        created_at=utc_timestamp(project.created_at),
        updated_at=utc_timestamp(project.updated_at),
        active_session_id=project.active_session_id,
        current_revision_id=project.current_revision_id,
        status=project.status,
        archived_at=utc_timestamp(project.archived_at) if project.archived_at is not None else None,
    )


def _workflow_response(workflow) -> PromptWorkflowResponse:
    return PromptWorkflowResponse(
        id=workflow.id,
        display_name=workflow.display_name,
        model_family=workflow.model_family,
        supported_modes=list(workflow.supported_modes),
        default_mode=workflow.default_mode,
        knowledge_sources=[
            KnowledgeSourceResponse(
                id=source.id,
                label=source.label,
                source_kind=source.source_kind,
                stability=source.stability,
            )
            for source in workflow.knowledge_sources
        ],
    )


def _session_response(prompt_session: PromptSession) -> PromptSessionResponse:
    return PromptSessionResponse(
        id=prompt_session.id,
        project_id=prompt_session.project_id,
        title=prompt_session.title,
        status=prompt_session.status,
        created_at=utc_timestamp(prompt_session.created_at),
        updated_at=utc_timestamp(prompt_session.updated_at),
    )


def _message_response(message: PromptMessage) -> PromptMessageResponse:
    return PromptMessageResponse(
        id=message.id,
        session_id=message.session_id,
        role=message.role,
        content=message.content,
        metadata=message.metadata_json,
        created_at=utc_timestamp(message.created_at),
    )


def _project_state_response(project_state: PromptProjectState) -> PromptProjectStateResponse:
    return PromptProjectStateResponse(
        id=project_state.id,
        project_id=project_state.project_id,
        objective=project_state.objective,
        important_constraints=project_state.important_constraints,
        must_preserve=project_state.must_preserve,
        known_problems=project_state.known_problems,
        accepted_observations=project_state.accepted_observations,
        updated_at=utc_timestamp(project_state.updated_at),
    )


def _revision_response(revision: PromptRevision) -> PromptRevisionResponse:
    return PromptRevisionResponse(
        id=revision.id,
        project_id=revision.project_id,
        parent_revision_id=revision.parent_revision_id,
        positive_prompt=revision.positive_prompt,
        negative_prompt=revision.negative_prompt,
        parameters=revision.parameters,
        change_log=revision.change_log,
        status=revision.status,
        created_at=utc_timestamp(revision.created_at),
    )


@router.get("/prompt-projects", response_model=list[PromptProjectResponse])
def get_projects(session: DatabaseSession, include_archived: bool = False) -> list[PromptProjectResponse]:
    return [_project_response(project) for project in list_projects(session, include_archived=include_archived)]


@router.get("/prompt-workflows", response_model=list[PromptWorkflowResponse])
def get_workflows(request: Request) -> list[PromptWorkflowResponse]:
    return [_workflow_response(workflow) for workflow in _catalog(request).list_workflows()]


@router.post("/prompt-projects", response_model=PromptProjectResponse, status_code=status.HTTP_201_CREATED)
def post_project(payload: CreateProjectRequest, request: Request, session: DatabaseSession) -> PromptProjectResponse:
    _validate_workflow_selection(_catalog(request), payload.workflow_profile_id, payload.workflow_mode)
    return _project_response(
        create_project(
            session,
            title=payload.title,
            workflow_profile_id=payload.workflow_profile_id,
            workflow_mode=payload.workflow_mode,
        )
    )


@router.get("/prompt-projects/{project_id}", response_model=PromptProjectResponse)
def get_project(project_id: str, session: DatabaseSession) -> PromptProjectResponse:
    try:
        return _project_response(get_prompt_project(session, project_id=project_id))
    except PromptWorkbenchError as error:
        _raise_http_error(error)


@router.patch("/prompt-projects/{project_id}", response_model=PromptProjectResponse)
def patch_project(project_id: str, payload: RenameProjectRequest, session: DatabaseSession) -> PromptProjectResponse:
    try:
        return _project_response(rename_project(session, project_id=project_id, title=payload.title))
    except PromptWorkbenchError as error:
        _raise_http_error(error)


@router.patch("/prompt-projects/{project_id}/workflow", response_model=PromptProjectResponse)
def patch_project_workflow(
    project_id: str,
    payload: UpdateProjectWorkflowRequest,
    request: Request,
    session: DatabaseSession,
) -> PromptProjectResponse:
    _validate_workflow_selection(_catalog(request), payload.workflow_profile_id, payload.workflow_mode)
    try:
        return _project_response(
            set_project_workflow(
                session,
                project_id=project_id,
                workflow_profile_id=payload.workflow_profile_id,
                workflow_mode=payload.workflow_mode,
            )
        )
    except PromptWorkbenchError as error:
        _raise_http_error(error)


@router.post("/prompt-projects/{project_id}/archive", response_model=PromptProjectResponse)
def post_project_archive(project_id: str, session: DatabaseSession) -> PromptProjectResponse:
    try:
        return _project_response(archive_project(session, project_id=project_id))
    except PromptWorkbenchError as error:
        _raise_http_error(error)


@router.get("/prompt-projects/{project_id}/sessions", response_model=list[PromptSessionResponse])
def get_sessions(project_id: str, session: DatabaseSession) -> list[PromptSessionResponse]:
    try:
        return [_session_response(item) for item in list_sessions(session, project_id=project_id)]
    except PromptWorkbenchError as error:
        _raise_http_error(error)


@router.post(
    "/prompt-projects/{project_id}/sessions",
    response_model=PromptSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_session(project_id: str, payload: CreateSessionRequest, session: DatabaseSession) -> PromptSessionResponse:
    try:
        return _session_response(create_session(session, project_id=project_id, title=payload.title))
    except PromptWorkbenchError as error:
        _raise_http_error(error)


@router.get("/prompt-sessions/{session_id}", response_model=PromptSessionResponse)
def get_session(session_id: str, session: DatabaseSession) -> PromptSessionResponse:
    try:
        return _session_response(get_prompt_session(session, session_id=session_id))
    except PromptWorkbenchError as error:
        _raise_http_error(error)


@router.get("/prompt-sessions/{session_id}/messages", response_model=list[PromptMessageResponse])
def get_messages(session_id: str, session: DatabaseSession) -> list[PromptMessageResponse]:
    try:
        return [_message_response(item) for item in list_messages(session, session_id=session_id)]
    except PromptWorkbenchError as error:
        _raise_http_error(error)


@router.post(
    "/prompt-sessions/{session_id}/messages",
    response_model=PromptMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_message(session_id: str, payload: AppendMessageRequest, session: DatabaseSession) -> PromptMessageResponse:
    try:
        return _message_response(
            append_message(
                session,
                session_id=session_id,
                role=payload.role,
                content=payload.content,
                metadata=payload.metadata,
            )
        )
    except PromptWorkbenchError as error:
        _raise_http_error(error)


@router.get("/prompt-projects/{project_id}/state", response_model=PromptProjectStateResponse)
def get_state(project_id: str, session: DatabaseSession) -> PromptProjectStateResponse:
    try:
        return _project_state_response(get_project_state(session, project_id=project_id))
    except PromptWorkbenchError as error:
        _raise_http_error(error)


@router.put("/prompt-projects/{project_id}/state", response_model=PromptProjectStateResponse)
def put_state(
    project_id: str,
    payload: UpdateProjectStateRequest,
    session: DatabaseSession,
) -> PromptProjectStateResponse:
    try:
        return _project_state_response(
            update_project_state(
                session,
                project_id=project_id,
                objective=payload.objective.strip(),
                important_constraints=payload.important_constraints,
                must_preserve=payload.must_preserve,
                known_problems=payload.known_problems,
                accepted_observations=payload.accepted_observations,
            )
        )
    except PromptWorkbenchError as error:
        _raise_http_error(error)


@router.get("/prompt-projects/{project_id}/context-preview", response_model=PromptContextPreviewResponse)
def get_context_preview(project_id: str, request: Request, session: DatabaseSession) -> PromptContextPreviewResponse:
    """Return contribution metadata only; no LLM request or prompt text exposure occurs here."""

    try:
        project = get_prompt_project(session, project_id=project_id)
        workflow = _catalog(request).get_workflow(project.workflow_profile_id)
        skill = _catalog(request).get_skill(workflow.skill_profile_id)
        project_state = get_project_state(session, project_id=project.id)
        accepted_revision = (
            get_prompt_revision(session, revision_id=project.current_revision_id)
            if project.current_revision_id is not None
            else None
        )
        session_messages = list_messages(session, session_id=project.active_session_id) if project.active_session_id else []
        knowledge_loader = KnowledgeSourceLoader(private_knowledge_root=request.app.state.runtime_paths.knowledge)
        context = PromptContextAssembler().assemble(
            skill=skill,
            workflow=workflow,
            mode=project.workflow_mode,
            project=project,
            project_state=project_state,
            accepted_revision=accepted_revision,
            session_messages=session_messages,
            selected_knowledge=knowledge_loader.load_for_workflow(workflow),
            current_user_message="Context preview only; do not generate a response.",
        )
    except PromptWorkbenchError as error:
        _raise_http_error(error)
    except (KnowledgeSourceLoadError, PromptWorkbenchCatalogError, ValueError) as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Prompt context preview is unavailable.") from error
    return PromptContextPreviewResponse(
        workflow_profile_id=workflow.id,
        workflow_mode=project.workflow_mode,
        contributions=[
            ContextContributionPreviewResponse(
                label=item.label,
                kind=item.kind,
                source=item.source,
                stability=item.stability,
                character_count=item.character_count,
                token_count=item.token_count,
            )
            for item in context.contributions
        ],
    )


@router.get("/prompt-projects/{project_id}/revisions", response_model=list[PromptRevisionResponse])
def get_revisions(project_id: str, session: DatabaseSession) -> list[PromptRevisionResponse]:
    try:
        return [_revision_response(item) for item in list_revisions(session, project_id=project_id)]
    except PromptWorkbenchError as error:
        _raise_http_error(error)


@router.post(
    "/prompt-projects/{project_id}/revisions",
    response_model=PromptRevisionResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_revision(
    project_id: str,
    payload: CreateRevisionRequest,
    session: DatabaseSession,
) -> PromptRevisionResponse:
    try:
        return _revision_response(
            create_proposed_revision(
                session,
                project_id=project_id,
                parent_revision_id=payload.parent_revision_id,
                positive_prompt=payload.positive_prompt,
                negative_prompt=payload.negative_prompt,
                parameters=payload.parameters,
                change_log=payload.change_log,
            )
        )
    except PromptWorkbenchError as error:
        _raise_http_error(error)


@router.get("/prompt-revisions/{revision_id}", response_model=PromptRevisionResponse)
def get_revision(revision_id: str, session: DatabaseSession) -> PromptRevisionResponse:
    try:
        return _revision_response(get_prompt_revision(session, revision_id=revision_id))
    except PromptWorkbenchError as error:
        _raise_http_error(error)


@router.post("/prompt-revisions/{revision_id}/accept", response_model=PromptRevisionResponse)
def post_revision_accept(revision_id: str, session: DatabaseSession) -> PromptRevisionResponse:
    try:
        return _revision_response(accept_revision(session, revision_id=revision_id))
    except PromptWorkbenchError as error:
        _raise_http_error(error)


@router.post("/prompt-revisions/{revision_id}/discard", response_model=PromptRevisionResponse)
def post_revision_discard(revision_id: str, session: DatabaseSession) -> PromptRevisionResponse:
    try:
        return _revision_response(discard_revision(session, revision_id=revision_id))
    except PromptWorkbenchError as error:
        _raise_http_error(error)
