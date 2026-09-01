"""Minimal host-adapter contract used by generic Node Agent code."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class HostMetadataError(RuntimeError):
    """Raised when safe host metadata cannot be read."""


@dataclass(frozen=True, slots=True)
class OperatingSystemSummary:
    """Small, non-sensitive operating-system metadata."""

    name: str
    kernel_release: str


@dataclass(frozen=True, slots=True)
class HostSummary:
    """Read-only Node Agent host metadata."""

    platform: str
    hostname: str
    uptime_seconds: float
    operating_system: OperatingSystemSummary


class HostAdapter(ABC):
    """Boundary for the Node Agent's minimal host-OS interactions."""

    @abstractmethod
    def get_platform(self) -> str:
        """Return the normalized platform identifier."""

    @abstractmethod
    def get_hostname(self) -> str:
        """Return the local hostname without reading environment configuration."""

    @abstractmethod
    def get_uptime_seconds(self) -> float:
        """Return host uptime in seconds."""

    @abstractmethod
    def get_operating_system_summary(self) -> OperatingSystemSummary:
        """Return a small operating-system and kernel summary."""

    def get_host_summary(self) -> HostSummary:
        """Compose the minimal host response from adapter-specific operations."""

        return HostSummary(
            platform=self.get_platform(),
            hostname=self.get_hostname(),
            uptime_seconds=self.get_uptime_seconds(),
            operating_system=self.get_operating_system_summary(),
        )
