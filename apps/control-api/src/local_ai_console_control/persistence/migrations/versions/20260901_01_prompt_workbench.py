"""Create the Prompt Workbench persistence baseline.

Revision ID: 20260901_01
Revises:
Create Date: 2026-09-01
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260901_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the first private Controller Runtime schema."""

    op.create_table(
        "prompt_projects",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("workflow_profile_id", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active_session_id", sa.String(length=40), nullable=True),
        sa.Column("current_revision_id", sa.String(length=40), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('active', 'archived')", name="ck_prompt_projects_status"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "prompt_sessions",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('active', 'closed')", name="ck_prompt_sessions_status"),
        sa.ForeignKeyConstraint(["project_id"], ["prompt_projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_prompt_sessions_project_id", "prompt_sessions", ["project_id"], unique=False)
    op.create_table(
        "prompt_messages",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("session_id", sa.String(length=40), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('user', 'assistant', 'system', 'tool')", name="ck_prompt_messages_role"),
        sa.ForeignKeyConstraint(["session_id"], ["prompt_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_prompt_messages_session_id", "prompt_messages", ["session_id"], unique=False)
    op.create_table(
        "prompt_project_states",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("important_constraints", sa.JSON(), nullable=False),
        sa.Column("must_preserve", sa.JSON(), nullable=False),
        sa.Column("known_problems", sa.JSON(), nullable=False),
        sa.Column("accepted_observations", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["prompt_projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id"),
    )
    op.create_index("ix_prompt_project_states_project_id", "prompt_project_states", ["project_id"], unique=True)
    op.create_table(
        "prompt_revisions",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("parent_revision_id", sa.String(length=40), nullable=True),
        sa.Column("positive_prompt", sa.Text(), nullable=False),
        sa.Column("negative_prompt", sa.Text(), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("change_log", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('proposed', 'accepted', 'discarded')", name="ck_prompt_revisions_status"
        ),
        sa.ForeignKeyConstraint(["parent_revision_id"], ["prompt_revisions.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["prompt_projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_prompt_revisions_parent_revision_id", "prompt_revisions", ["parent_revision_id"], unique=False)
    op.create_index("ix_prompt_revisions_project_id", "prompt_revisions", ["project_id"], unique=False)


def downgrade() -> None:
    """Remove the Phase 1A schema for explicit local development rollback only."""

    op.drop_index("ix_prompt_revisions_project_id", table_name="prompt_revisions")
    op.drop_index("ix_prompt_revisions_parent_revision_id", table_name="prompt_revisions")
    op.drop_table("prompt_revisions")
    op.drop_index("ix_prompt_project_states_project_id", table_name="prompt_project_states")
    op.drop_table("prompt_project_states")
    op.drop_index("ix_prompt_messages_session_id", table_name="prompt_messages")
    op.drop_table("prompt_messages")
    op.drop_index("ix_prompt_sessions_project_id", table_name="prompt_sessions")
    op.drop_table("prompt_sessions")
    op.drop_table("prompt_projects")
