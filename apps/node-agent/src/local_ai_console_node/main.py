"""Node Agent FastAPI application factory and Linux production bootstrap."""

from __future__ import annotations

import uvicorn
from fastapi import FastAPI

from local_ai_console_node.api.system import APPLICATION_NAME, router as system_router
from local_ai_console_node.host.base import HostAdapter
from local_ai_console_node.host.linux import create_default_host_adapter
from local_ai_console_node.version import __version__


def create_app(host_adapter: HostAdapter) -> FastAPI:
    """Create a testable Node Agent application from an injected host adapter."""

    app = FastAPI(title=APPLICATION_NAME, version=__version__)
    app.state.host_adapter = host_adapter
    app.include_router(system_router)
    return app


def create_default_app() -> FastAPI:
    """Create the Linux-only production app and reject unsupported platforms."""

    return create_app(create_default_host_adapter())


def run() -> None:
    """Run the Node Agent through the installed console script."""

    uvicorn.run(create_default_app(), host="localhost", port=8000)
