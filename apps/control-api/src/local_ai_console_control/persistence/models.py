"""SQLAlchemy models for the private Prompt Workbench domain."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    """Return the canonical timestamp used by persisted Controller data."""

    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Base class for the Controller's private SQLite schema."""


class PromptProject(Base):
    """A durable prompt-work item; accepted content remains in revisions."""

    __tablename__ = "prompt_projects"
    __table_args__ = (CheckConstraint("status IN ('active', 'archived')", name="ck_prompt_projects_status"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    workflow_profile_id: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    active_session_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    current_revision_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PromptSession(Base):
    """One sustained discussion context belonging to a Prompt Project."""

    __tablename__ = "prompt_sessions"
    __table_args__ = (CheckConstraint("status IN ('active', 'closed')", name="ck_prompt_sessions_status"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("prompt_projects.id"), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PromptMessage(Base):
    """An immutable raw discussion message; compression must not delete it."""

    __tablename__ = "prompt_messages"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant', 'system', 'tool')", name="ck_prompt_messages_role"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("prompt_sessions.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PromptProjectState(Base):
    """Typed structured state retained separately from raw discussion messages."""

    __tablename__ = "prompt_project_states"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("prompt_projects.id"), nullable=False, unique=True, index=True
    )
    objective: Mapped[str] = mapped_column(Text, nullable=False, default="")
    important_constraints: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    must_preserve: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    known_problems: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    accepted_observations: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PromptRevision(Base):
    """An immutable proposed, accepted, or discarded prompt artifact."""

    __tablename__ = "prompt_revisions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('proposed', 'accepted', 'discarded')", name="ck_prompt_revisions_status"
        ),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("prompt_projects.id"), nullable=False, index=True)
    parent_revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("prompt_revisions.id"), nullable=True, index=True
    )
    positive_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    negative_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    parameters: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    change_log: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="proposed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
