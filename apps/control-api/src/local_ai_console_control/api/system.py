"""Small, local-only system metadata endpoints."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

from local_ai_console_control.config.runtime_paths import RuntimePaths
from local_ai_console_control.version import __version__


APPLICATION_NAME = "Local AI Console"
SERVICE_ROLE = "control-api"

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str


class VersionResponse(BaseModel):
    application: str
    service: str
    version: str


class RuntimeLayoutResponse(BaseModel):
    config: str
    data: str
    prompts: str
    knowledge: str
    logs: str
    cache: str
    backups: str


class RuntimeInfoResponse(BaseModel):
    root: str
    source: str
    initialized: bool
    paths: RuntimeLayoutResponse


def _runtime_paths(request: Request) -> RuntimePaths:
    return request.app.state.runtime_paths


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Return inexpensive service liveness metadata."""

    return HealthResponse(status="ok", service=SERVICE_ROLE, version=__version__)


@router.get("/version", response_model=VersionResponse)
def version() -> VersionResponse:
    """Return application identity without fabricated build metadata."""

    return VersionResponse(application=APPLICATION_NAME, service=SERVICE_ROLE, version=__version__)


@router.get("/runtime/info", response_model=RuntimeInfoResponse)
def runtime_info(request: Request) -> RuntimeInfoResponse:
    """Return local runtime metadata without exposing environment or private content."""

    paths = _runtime_paths(request)
    return RuntimeInfoResponse(
        root=str(paths.root),
        source=paths.source.value,
        initialized=paths.is_initialized,
        paths=RuntimeLayoutResponse(
            config=str(paths.config),
            data=str(paths.data),
            prompts=str(paths.prompts),
            knowledge=str(paths.knowledge),
            logs=str(paths.logs),
            cache=str(paths.cache),
            backups=str(paths.backups),
        ),
    )
