"""Unit tests for public/private repository-hygiene path classification."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "check-repository-hygiene.py"
SPEC = importlib.util.spec_from_file_location("repository_hygiene", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
REPOSITORY_HYGIENE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPOSITORY_HYGIENE)


class RepositoryHygienePathTests(unittest.TestCase):
    def test_private_runtime_artifacts_are_rejected(self) -> None:
        private_paths = (
            ".env",
            ".env.local",
            "data/chats.sqlite3",
            "knowledge/private-notes.md",
            "backups/controller-export.backup",
            "models/main-model.gguf",
            "keys/operator.pem",
        )

        for path in private_paths:
            with self.subTest(path=path):
                self.assertTrue(REPOSITORY_HYGIENE.violates_private_boundary(path))

    def test_public_examples_remain_allowed(self) -> None:
        public_paths = (
            ".env.example",
            ".env.local.example",
            "config/examples/runtime.example.env",
            "docs/runtime-data-boundary.md",
            "prompts/examples/public-example.md",
        )

        for path in public_paths:
            with self.subTest(path=path):
                self.assertFalse(REPOSITORY_HYGIENE.violates_private_boundary(path))


if __name__ == "__main__":
    unittest.main()
