"""Linux-specific implementation of the minimal host adapter."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import platform as standard_platform
import socket

from .base import HostAdapter, HostMetadataError, OperatingSystemSummary


class UnsupportedPlatformError(RuntimeError):
    """Raised when the default Node Agent bootstrap is used outside Linux."""


def _read_proc_uptime() -> str:
    try:
        return Path("/proc/uptime").read_text(encoding="utf-8")
    except OSError as error:
        raise HostMetadataError("Unable to read Linux uptime metadata.") from error


class LinuxHostAdapter(HostAdapter):
    """Read safe Linux metadata without subprocesses, inventory, or telemetry."""

    def __init__(
        self,
        *,
        hostname_provider: Callable[[], str] = socket.gethostname,
        uname_provider: Callable[[], standard_platform.uname_result] = standard_platform.uname,
        uptime_reader: Callable[[], str] = _read_proc_uptime,
    ) -> None:
        self._hostname_provider = hostname_provider
        self._uname_provider = uname_provider
        self._uptime_reader = uptime_reader

    def get_platform(self) -> str:
        return "linux"

    def get_hostname(self) -> str:
        try:
            hostname = self._hostname_provider().strip()
        except OSError as error:
            raise HostMetadataError("Unable to read Linux hostname metadata.") from error
        if not hostname:
            raise HostMetadataError("Linux hostname metadata is empty.")
        return hostname

    def get_uptime_seconds(self) -> float:
        try:
            uptime_token = self._uptime_reader().split(maxsplit=1)[0]
            uptime_seconds = float(uptime_token)
        except HostMetadataError:
            raise
        except (IndexError, OSError, TypeError, ValueError) as error:
            raise HostMetadataError("Linux uptime metadata has an invalid format.") from error
        if uptime_seconds < 0:
            raise HostMetadataError("Linux uptime metadata cannot be negative.")
        return uptime_seconds

    def get_operating_system_summary(self) -> OperatingSystemSummary:
        try:
            uname = self._uname_provider()
        except OSError as error:
            raise HostMetadataError("Unable to read Linux operating-system metadata.") from error
        return OperatingSystemSummary(name=uname.system, kernel_release=uname.release)


def create_default_host_adapter(*, platform_name: str | None = None) -> HostAdapter:
    """Create the production adapter and explicitly reject unsupported platforms."""

    detected_platform = (platform_name or standard_platform.system()).casefold()
    if detected_platform != "linux":
        raise UnsupportedPlatformError("The Local AI Console Node Agent default bootstrap requires Linux.")
    return LinuxHostAdapter()
