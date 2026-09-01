"""HTTP tests for Node Agent metadata endpoints with injected fake adapters."""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from local_ai_console_node.host.base import HostAdapter, HostMetadataError, OperatingSystemSummary
from local_ai_console_node.main import create_app
from local_ai_console_node.version import __version__


class FakeHostAdapter(HostAdapter):
    def get_platform(self) -> str:
        return "linux"

    def get_hostname(self) -> str:
        return "fake-node"

    def get_uptime_seconds(self) -> float:
        return 42.5

    def get_operating_system_summary(self) -> OperatingSystemSummary:
        return OperatingSystemSummary(name="Linux", kernel_release="6.8.0-test")


class FailingHostAdapter(FakeHostAdapter):
    def get_host_summary(self):
        raise HostMetadataError("test-only host metadata failure")


class SystemEndpointTests(unittest.TestCase):
    def test_health_and_version_do_not_need_host_metadata(self) -> None:
        with TestClient(create_app(FailingHostAdapter())) as client:
            health_response = client.get("/health")
            version_response = client.get("/version")

        self.assertEqual(health_response.status_code, 200)
        self.assertEqual(
            health_response.json(),
            {"status": "ok", "service": "node-agent", "version": __version__},
        )
        self.assertEqual(version_response.status_code, 200)
        self.assertEqual(version_response.json()["application"], "Local AI Console Node Agent")
        self.assertEqual(version_response.json()["service"], "node-agent")
        self.assertEqual(version_response.json()["version"], __version__)

    def test_host_returns_only_safe_fake_metadata(self) -> None:
        with TestClient(create_app(FakeHostAdapter())) as client:
            response = client.get("/host")

        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["platform"], "linux")
        self.assertEqual(body["hostname"], "fake-node")
        self.assertEqual(body["uptime_seconds"], 42.5)
        self.assertEqual(body["operating_system"], {"name": "Linux", "kernel_release": "6.8.0-test"})
        self.assertEqual(set(body), {"platform", "hostname", "uptime_seconds", "operating_system"})
        self.assertNotIn("environment", body)
        self.assertNotIn("interfaces", body)
        self.assertNotIn("model_paths", body)

    def test_host_metadata_failure_is_a_clear_api_error(self) -> None:
        with TestClient(create_app(FailingHostAdapter())) as client:
            response = client.get("/host")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "Host metadata is unavailable."})
