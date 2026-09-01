"""Explicit Controller Runtime migration command."""

from __future__ import annotations

from local_ai_console_control.config.runtime_paths import (
    find_repository_root,
    initialize_runtime_layout,
    resolve_runtime_paths,
)
from local_ai_console_control.persistence.database import database_path_for_runtime_data, upgrade_database


def run() -> None:
    """Initialize the private layout and upgrade its database to Alembic head."""

    runtime_paths = resolve_runtime_paths(repository_root=find_repository_root())
    initialize_runtime_layout(runtime_paths)
    upgrade_database(database_path_for_runtime_data(runtime_paths.data))
