"""Alembic-backed SQLite lifecycle for the Controller Runtime database."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


DATABASE_FILENAME = "console.sqlite3"


class DatabaseSchemaError(RuntimeError):
    """Raised when a Controller Runtime database is absent or at the wrong revision."""


@dataclass(frozen=True, slots=True)
class Database:
    """A verified engine and session factory for a single Controller Runtime database."""

    path: Path
    engine: Engine
    session_factory: sessionmaker[Session]

    def dispose(self) -> None:
        """Release database resources during application shutdown."""

        self.engine.dispose()


def database_path_for_runtime_data(runtime_data_directory: Path) -> Path:
    """Return the only supported database location within the private Controller Runtime."""

    return runtime_data_directory / DATABASE_FILENAME


def database_url(database_path: Path) -> str:
    """Build a SQLite URL from an absolute RuntimePaths-derived path."""

    return f"sqlite+pysqlite:///{database_path.resolve().as_posix()}"


def migration_config(database_path: Path) -> Config:
    """Configure Alembic without relying on the process working directory."""

    config = Config()
    migration_directory = Path(__file__).resolve().parent / "migrations"
    config.set_main_option("script_location", str(migration_directory))
    config.set_main_option("sqlalchemy.url", database_url(database_path))
    return config


def expected_revision(database_path: Path) -> str:
    """Read Alembic's declared head revision for the bundled migration scripts."""

    script_directory = ScriptDirectory.from_config(migration_config(database_path))
    revision = script_directory.get_current_head()
    if revision is None:
        raise DatabaseSchemaError("No Controller database migration head is configured.")
    return revision


def upgrade_database(database_path: Path) -> None:
    """Apply the explicit Controller migration command to a private runtime database."""

    database_path.parent.mkdir(parents=True, exist_ok=True)
    command.upgrade(migration_config(database_path), "head")


def validate_database_schema(database_path: Path) -> None:
    """Reject a missing, unmanaged, or stale database without modifying it."""

    if not database_path.is_file():
        raise DatabaseSchemaError(
            "Controller database is not initialized. Run local-ai-console-control-api-migrate first."
        )

    engine = create_engine(database_url(database_path))
    try:
        with engine.connect() as connection:
            current_revision = MigrationContext.configure(connection).get_current_revision()
    finally:
        engine.dispose()

    migration_head = expected_revision(database_path)
    if current_revision != migration_head:
        raise DatabaseSchemaError(
            "Controller database schema is not current. Run local-ai-console-control-api-migrate before starting the API."
        )


def open_database(database_path: Path) -> Database:
    """Open a verified database only after its Alembic revision has been checked."""

    validate_database_schema(database_path)
    engine = create_engine(database_url(database_path))
    return Database(
        path=database_path,
        engine=engine,
        session_factory=sessionmaker(bind=engine, expire_on_commit=False),
    )
