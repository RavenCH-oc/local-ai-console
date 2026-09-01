"""Alembic migration environment; database URLs are supplied by the explicit runner."""

from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

from local_ai_console_control.persistence.models import Base


config = context.config
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations without a live connection when Alembic explicitly requests SQL output."""

    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against the private SQLite database selected by RuntimePaths."""

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
