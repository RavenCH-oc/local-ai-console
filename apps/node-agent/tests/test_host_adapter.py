"""Unit tests for Linux host metadata parsing and platform bootstrap."""

from __future__ import annotations

from types import SimpleNamespace
import unittest

from local_ai_console_node.host.base import HostMetadataError
from local_ai_console_node.host.linux import LinuxHostAdapter, UnsupportedPlatformError, create_default_host_adapter


class LinuxHostAdapterTests(unittest.TestCase):
    def make_adapter(self, uptime: str = "123.45 67.89\n") -> LinuxHostAdapter:
        return LinuxHostAdapter(
            hostname_provider=lambda: "fake-node",
            uname_provider=lambda: SimpleNamespace(system="Linux", release="6.8.0-test"),
            uptime_reader=lambda: uptime,
        )

    def test_host_summary_uses_injected_safe_metadata(self) -> None:
        summary = self.make_adapter().get_host_summary()

        self.assertEqual(summary.platform, "linux")
        self.assertEqual(summary.hostname, "fake-node")
        self.assertEqual(summary.uptime_seconds, 123.45)
        self.assertEqual(summary.operating_system.name, "Linux")
        self.assertEqual(summary.operating_system.kernel_release, "6.8.0-test")

    def test_invalid_uptime_has_a_clear_error(self) -> None:
        with self.assertRaises(HostMetadataError):
            self.make_adapter("not-an-uptime-value").get_uptime_seconds()

    def test_unreadable_uptime_has_a_clear_error(self) -> None:
        adapter = LinuxHostAdapter(
            hostname_provider=lambda: "fake-node",
            uname_provider=lambda: SimpleNamespace(system="Linux", release="6.8.0-test"),
            uptime_reader=lambda: (_ for _ in ()).throw(OSError("test-only read failure")),
        )

        with self.assertRaises(HostMetadataError):
            adapter.get_uptime_seconds()

    def test_default_bootstrap_rejects_unsupported_platform(self) -> None:
        with self.assertRaises(UnsupportedPlatformError):
            create_default_host_adapter(platform_name="Windows")
