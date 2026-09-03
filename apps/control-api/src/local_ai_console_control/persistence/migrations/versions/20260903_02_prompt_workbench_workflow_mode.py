"""Persist the active Prompt Workbench workflow mode.

Revision ID: 20260903_02
Revises: 20260901_01
Create Date: 2026-09-03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260903_02"
down_revision = "20260901_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add a safe default mode and move the former placeholder to the first built-in workflow."""

    op.add_column(
        "prompt_projects",
        sa.Column("workflow_mode", sa.String(length=32), nullable=False, server_default="balanced"),
    )
    op.execute(
        "UPDATE prompt_projects SET workflow_profile_id = 'anima_base_v1' "
        "WHERE workflow_profile_id = 'example_image_prompt_workflow'"
    )


def downgrade() -> None:
    """Remove the additive mode field for explicit local development rollback only."""

    op.drop_column("prompt_projects", "workflow_mode")
