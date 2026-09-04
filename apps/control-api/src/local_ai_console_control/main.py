"""FastAPI application entry point for the Windows Controller."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Mapping

import uvicorn
from fastapi import FastAPI

from local_ai_console_control.api.llm import router as llm_router
from local_ai_console_control.api.prompt_workbench import router as prompt_workbench_router
from local_ai_console_control.api.system import APPLICATION_NAME, SERVICE_ROLE, router as system_router
from local_ai_console_control.config.runtime_paths import (
    find_repository_root,
    initialize_runtime_layout,
    resolve_runtime_paths,
)
from local_ai_console_control.persistence.database import database_path_for_runtime_data, open_database
from local_ai_console_control.llm.bridge import LlmRuntimeBridge
from local_ai_console_control.llm.service import LLMService
from local_ai_console_control.prompt_workbench.catalog import PromptWorkbenchCatalog, builtin_prompt_engine_root
from local_ai_console_control.prompt_workbench.discussion import PromptDiscussionCoordinator
from local_ai_console_control.version import __version__


def create_app(
    *,
    repository_root: Path | str | None = None,
    environ: Mapping[str, str] | None = None,
    platform_name: str | None = None,
    local_appdata: Path | str | None = None,
    llm_service: LLMService | None = None,
) -> FastAPI:
    """Create the API; runtime directories are initialized during startup only."""

    resolved_repository_root = Path(repository_root) if repository_root is not None else find_repository_root()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        runtime_paths = resolve_runtime_paths(
            repository_root=resolved_repository_root,
            environ=environ,
            platform_name=platform_name,
            local_appdata=local_appdata,
        )
        initialize_runtime_layout(runtime_paths)
        app.state.runtime_paths = runtime_paths
        app.state.prompt_workbench_catalog = PromptWorkbenchCatalog.load(builtin_prompt_engine_root())
        database = open_database(database_path_for_runtime_data(runtime_paths.data))
        app.state.database = database
        llm_runtime_bridge = LlmRuntimeBridge(config_directory=runtime_paths.config, environ=environ)
        app.state.llm_runtime_bridge = llm_runtime_bridge
        app.state.llm_service = llm_service or llm_runtime_bridge.service
        app.state.prompt_discussion_coordinator = PromptDiscussionCoordinator()
        try:
            yield
        finally:
            await llm_runtime_bridge.aclose()
            database.dispose()

    app = FastAPI(title=APPLICATION_NAME, version=__version__, lifespan=lifespan)
    app.include_router(system_router)
    app.include_router(system_router, prefix="/api")
    app.include_router(prompt_workbench_router)
    app.include_router(llm_router)
    app.state.service_role = SERVICE_ROLE
    return app


app = create_app()


def run() -> None:
    """Run the local development server through the installed console script."""

    uvicorn.run(app, host="127.0.0.1", port=8000)
