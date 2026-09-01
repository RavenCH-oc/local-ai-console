"""Read-only Node Agent system endpoints."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from local_ai_console_node.host.base import HostAdapter, HostMetadataError
from local_ai_console_node.version import __version__


APPLICATION_NAME = "Local AI Console Node Agent"
SERVICE_ROLE = "node-agent"

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str


class VersionResponse(BaseModel):
    application: str
    service: str
    version: str


class OperatingSystemResponse(BaseModel):
    name: str
    kernel_release: str


class HostResponse(BaseModel):
    platform: str
    hostname: str
    uptime_seconds: float
    operating_system: OperatingSystemResponse


def _host_adapter(request: Request) -> HostAdapter:
    return request.app.state.host_adapter


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Return inexpensive service liveness metadata without reading the host."""

    return HealthResponse(status="ok", service=SERVICE_ROLE, version=__version__)


@router.get("/version", response_model=VersionResponse)
def version() -> VersionResponse:
    """Return application identity without fabricated build metadata."""

    return VersionResponse(application=APPLICATION_NAME, service=SERVICE_ROLE, version=__version__)


@router.get("/host", response_model=HostResponse)
def host(request: Request) -> HostResponse:
    """Return minimal non-sensitive metadata from the injected host adapter."""

    try:
        summary = _host_adapter(request).get_host_summary()
    except HostMetadataError as error:
        raise HTTPException(status_code=503, detail="Host metadata is unavailable.") from error

    return HostResponse(
        platform=summary.platform,
        hostname=summary.hostname,
        uptime_seconds=summary.uptime_seconds,
        operating_system=OperatingSystemResponse(
            name=summary.operating_system.name,
            kernel_release=summary.operating_system.kernel_release,
        ),
    )
