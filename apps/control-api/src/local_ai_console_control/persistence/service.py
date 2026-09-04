"""Small synchronous application service for Prompt Workbench persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from local_ai_console_control.persistence.models import (
    PromptMessage,
    PromptProject,
    PromptProjectState,
    PromptRevision,
    PromptSession,
    utc_now,
)


DEFAULT_WORKFLOW_PROFILE_ID = "anima_base_v1"
DEFAULT_WORKFLOW_MODE = "balanced"


class PromptWorkbenchError(RuntimeError):
    """Base error for predictable Prompt Workbench application failures."""


class PromptWorkbenchNotFoundError(PromptWorkbenchError):
    """Raised when a requested project, session, message, or revision is absent."""


class PromptWorkbenchConflictError(PromptWorkbenchError):
    """Raised when an operation would break lifecycle or project ownership rules."""


def opaque_id(prefix: str) -> str:
    """Create an opaque ID that also conforms to the Phase 0C stable-ID character set."""

    return f"{prefix}_{uuid4().hex}"


def utc_timestamp(value: datetime) -> datetime:
    """Normalize SQLite's timezone-naive reads to the domain's canonical UTC timestamps."""

    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _require_project(session: Session, project_id: str) -> PromptProject:
    project = session.get(PromptProject, project_id)
    if project is None:
        raise PromptWorkbenchNotFoundError("Prompt Project was not found.")
    return project


def _require_active_project(session: Session, project_id: str) -> PromptProject:
    project = _require_project(session, project_id)
    if project.status == "archived":
        raise PromptWorkbenchConflictError("Archived Prompt Projects cannot be changed.")
    return project


def _require_session(session: Session, session_id: str) -> PromptSession:
    prompt_session = session.get(PromptSession, session_id)
    if prompt_session is None:
        raise PromptWorkbenchNotFoundError("Prompt Session was not found.")
    return prompt_session


def _require_revision(session: Session, revision_id: str) -> PromptRevision:
    revision = session.get(PromptRevision, revision_id)
    if revision is None:
        raise PromptWorkbenchNotFoundError("Prompt Revision was not found.")
    return revision


def get_project(session: Session, *, project_id: str) -> PromptProject:
    """Return one project, including archived projects for direct resource reads."""

    return _require_project(session, project_id)


def get_session(session: Session, *, session_id: str) -> PromptSession:
    """Return one discussion session by its opaque public API identity."""

    return _require_session(session, session_id)


def get_active_discussion_project(session: Session, *, session_id: str) -> tuple[PromptProject, PromptSession]:
    """Return the active Project/session pair permitted to receive one discussion generation."""

    prompt_session = _require_session(session, session_id)
    if prompt_session.status != "active":
        raise PromptWorkbenchConflictError("The Prompt Session is not active.")
    project = _require_active_project(session, prompt_session.project_id)
    if project.active_session_id != prompt_session.id:
        raise PromptWorkbenchConflictError("Only the active Prompt Session can start a discussion.")
    return project, prompt_session


def get_revision(session: Session, *, revision_id: str) -> PromptRevision:
    """Return one revision without altering its immutable artifact content."""

    return _require_revision(session, revision_id)


def _touch(project: PromptProject, now: datetime) -> None:
    project.updated_at = now


def list_projects(session: Session, *, include_archived: bool = False) -> Sequence[PromptProject]:
    """List user projects without silently exposing archived items by default."""

    statement = select(PromptProject).order_by(PromptProject.updated_at.desc())
    if not include_archived:
        statement = statement.where(PromptProject.status == "active")
    return session.scalars(statement).all()


def create_project(
    session: Session,
    *,
    title: str,
    workflow_profile_id: str,
    workflow_mode: str = DEFAULT_WORKFLOW_MODE,
) -> PromptProject:
    """Create a project with its initial state and discussion session atomically."""

    now = utc_now()
    project = PromptProject(
        id=opaque_id("pp"),
        title=title,
        workflow_profile_id=workflow_profile_id,
        workflow_mode=workflow_mode,
        created_at=now,
        updated_at=now,
        status="active",
    )
    prompt_session = PromptSession(
        id=opaque_id("ps"),
        project_id=project.id,
        title="Initial discussion",
        status="active",
        created_at=now,
        updated_at=now,
    )
    project.active_session_id = prompt_session.id
    project_state = PromptProjectState(
        id=opaque_id("pst"),
        project_id=project.id,
        objective="",
        important_constraints=[],
        must_preserve=[],
        known_problems=[],
        accepted_observations=[],
        updated_at=now,
    )
    session.add_all((project, prompt_session, project_state))
    session.commit()
    return project


def set_project_workflow(
    session: Session,
    *,
    project_id: str,
    workflow_profile_id: str,
    workflow_mode: str,
) -> PromptProject:
    """Persist the active workflow/mode only after the caller has validated the built-in registry."""

    project = _require_active_project(session, project_id)
    project.workflow_profile_id = workflow_profile_id
    project.workflow_mode = workflow_mode
    _touch(project, utc_now())
    session.commit()
    return project


def rename_project(session: Session, *, project_id: str, title: str) -> PromptProject:
    project = _require_active_project(session, project_id)
    project.title = title
    _touch(project, utc_now())
    session.commit()
    return project


def archive_project(session: Session, *, project_id: str) -> PromptProject:
    project = _require_project(session, project_id)
    if project.status == "archived":
        return project
    now = utc_now()
    project.status = "archived"
    project.archived_at = now
    _touch(project, now)
    session.commit()
    return project


def create_session(session: Session, *, project_id: str, title: str | None) -> PromptSession:
    project = _require_active_project(session, project_id)
    now = utc_now()
    prompt_session = PromptSession(
        id=opaque_id("ps"),
        project_id=project.id,
        title=title,
        status="active",
        created_at=now,
        updated_at=now,
    )
    project.active_session_id = prompt_session.id
    _touch(project, now)
    session.add(prompt_session)
    session.commit()
    return prompt_session


def list_sessions(session: Session, *, project_id: str) -> Sequence[PromptSession]:
    _require_project(session, project_id)
    return session.scalars(
        select(PromptSession).where(PromptSession.project_id == project_id).order_by(PromptSession.created_at.asc())
    ).all()


def append_message(
    session: Session,
    *,
    session_id: str,
    role: str,
    content: str,
    metadata: dict[str, object] | None,
) -> PromptMessage:
    prompt_session = _require_session(session, session_id)
    project = _require_active_project(session, prompt_session.project_id)
    now = utc_now()
    message = PromptMessage(
        id=opaque_id("pm"),
        session_id=prompt_session.id,
        role=role,
        content=content,
        metadata_json=metadata,
        created_at=now,
    )
    prompt_session.updated_at = now
    _touch(project, now)
    session.add(message)
    session.commit()
    return message


def list_messages(session: Session, *, session_id: str) -> Sequence[PromptMessage]:
    _require_session(session, session_id)
    return session.scalars(
        select(PromptMessage).where(PromptMessage.session_id == session_id).order_by(PromptMessage.created_at.asc())
    ).all()


def get_project_state(session: Session, *, project_id: str) -> PromptProjectState:
    _require_project(session, project_id)
    project_state = session.scalar(
        select(PromptProjectState).where(PromptProjectState.project_id == project_id)
    )
    if project_state is None:
        raise PromptWorkbenchNotFoundError("Prompt Project State was not found.")
    return project_state


def update_project_state(
    session: Session,
    *,
    project_id: str,
    objective: str,
    important_constraints: list[str],
    must_preserve: list[str],
    known_problems: list[str],
    accepted_observations: list[str],
) -> PromptProjectState:
    project = _require_active_project(session, project_id)
    project_state = get_project_state(session, project_id=project_id)
    now = utc_now()
    project_state.objective = objective
    project_state.important_constraints = important_constraints
    project_state.must_preserve = must_preserve
    project_state.known_problems = known_problems
    project_state.accepted_observations = accepted_observations
    project_state.updated_at = now
    _touch(project, now)
    session.commit()
    return project_state


def create_proposed_revision(
    session: Session,
    *,
    project_id: str,
    parent_revision_id: str | None,
    positive_prompt: str,
    negative_prompt: str,
    parameters: dict[str, object],
    change_log: str,
) -> PromptRevision:
    project = _require_active_project(session, project_id)
    if parent_revision_id is not None:
        parent_revision = _require_revision(session, parent_revision_id)
        if parent_revision.project_id != project.id:
            raise PromptWorkbenchConflictError("A parent revision must belong to the same Prompt Project.")

    now = utc_now()
    revision = PromptRevision(
        id=opaque_id("pr"),
        project_id=project.id,
        parent_revision_id=parent_revision_id,
        positive_prompt=positive_prompt,
        negative_prompt=negative_prompt,
        parameters=parameters,
        change_log=change_log,
        status="proposed",
        created_at=now,
    )
    _touch(project, now)
    session.add(revision)
    session.commit()
    return revision


def list_revisions(session: Session, *, project_id: str) -> Sequence[PromptRevision]:
    _require_project(session, project_id)
    return session.scalars(
        select(PromptRevision)
        .where(PromptRevision.project_id == project_id)
        .order_by(PromptRevision.created_at.asc())
    ).all()


def accept_revision(session: Session, *, revision_id: str) -> PromptRevision:
    """Accept a proposal and update the sole current accepted pointer in one commit."""

    revision = _require_revision(session, revision_id)
    project = _require_active_project(session, revision.project_id)
    if revision.status != "proposed":
        raise PromptWorkbenchConflictError("Only a proposed revision can be accepted.")

    now = utc_now()
    revision.status = "accepted"
    project.current_revision_id = revision.id
    _touch(project, now)
    session.commit()
    return revision


def discard_revision(session: Session, *, revision_id: str) -> PromptRevision:
    revision = _require_revision(session, revision_id)
    project = _require_active_project(session, revision.project_id)
    if project.current_revision_id == revision.id:
        raise PromptWorkbenchConflictError("The current accepted revision cannot be discarded.")
    if revision.status != "proposed":
        raise PromptWorkbenchConflictError("Only a proposed revision can be discarded.")

    revision.status = "discarded"
    _touch(project, utc_now())
    session.commit()
    return revision
