"""Host operating-system adapter boundary."""

from .base import HostAdapter, HostMetadataError, HostSummary, OperatingSystemSummary
from .linux import LinuxHostAdapter, UnsupportedPlatformError, create_default_host_adapter

__all__ = [
    "HostAdapter",
    "HostMetadataError",
    "HostSummary",
    "LinuxHostAdapter",
    "OperatingSystemSummary",
    "UnsupportedPlatformError",
    "create_default_host_adapter",
]
