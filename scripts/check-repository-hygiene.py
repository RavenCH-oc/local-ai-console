"""Verify public/private runtime boundary rules without reading private data."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
import subprocess
import sys


REQUIRED_PUBLIC_FILES = (
    ".env.example",
    ".gitignore",
    "docs/runtime-data-boundary.md",
)

EXPECTED_IGNORED_PATHS = (
    ".env",
    "controller.sqlite3",
    "models/example.gguf",
    "runtime/private.db",
    "knowledge/private-notes.md",
    "backups/controller-export.backup",
)

EXPECTED_TRACKABLE_PATHS = (
    ".env.example",
    ".env.local.example",
    "config/examples/runtime.example.env",
    "prompts/examples/public-example.md",
)

PRIVATE_TOP_LEVEL_DIRECTORIES = frozenset(
    {
        "artifacts",
        "backups",
        "cache",
        "credentials",
        "data",
        "generated",
        "generated-images",
        "knowledge",
        "local-data",
        "logs",
        "models",
        "outputs",
        "runtime",
        "runtime-data",
        "secrets",
        "state",
        "storage",
    }
)

PRIVATE_FILENAMES = frozenset(
    {
        ".env",
        "id_ed25519",
        "id_ed25519.pub",
        "id_rsa",
        "id_rsa.pub",
    }
)

PRIVATE_SUFFIXES = (
    ".backup",
    ".bak",
    ".bin",
    ".ckpt",
    ".db",
    ".engine",
    ".ggml",
    ".gguf",
    ".key",
    ".keystore",
    ".onnx",
    ".p12",
    ".pem",
    ".pfx",
    ".pt",
    ".pth",
    ".safetensors",
    ".sqlite",
    ".sqlite3",
)


def run_git(repository_root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ("git", *arguments),
        cwd=repository_root,
        check=False,
        capture_output=True,
        text=True,
    )


def is_ignored(repository_root: Path, candidate: str) -> bool:
    result = run_git(repository_root, "check-ignore", "-q", "--no-index", "--", candidate)
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr.strip() or f"Unable to inspect ignore rule for {candidate}")
    return result.returncode == 0


def violates_private_boundary(tracked_path: str) -> bool:
    path = PurePosixPath(tracked_path)
    parts = tuple(part.lower() for part in path.parts)
    filename = path.name.lower()

    if parts and parts[0] in PRIVATE_TOP_LEVEL_DIRECTORIES:
        return True
    if "backups" in parts:
        return True
    if filename in PRIVATE_FILENAMES:
        return True
    if filename.startswith(".env.") and not filename.endswith(".example"):
        return True
    return filename.endswith(PRIVATE_SUFFIXES)


def main() -> int:
    repository_root = Path(__file__).resolve().parent.parent
    failures: list[str] = []

    for relative_path in REQUIRED_PUBLIC_FILES:
        if not (repository_root / relative_path).is_file():
            failures.append(f"Missing required public baseline file: {relative_path}")

    for candidate in EXPECTED_IGNORED_PATHS:
        if not is_ignored(repository_root, candidate):
            failures.append(f"Expected ignored path is trackable: {candidate}")

    for candidate in EXPECTED_TRACKABLE_PATHS:
        if is_ignored(repository_root, candidate):
            failures.append(f"Expected public example is ignored: {candidate}")

    tracked = run_git(repository_root, "ls-files", "-z")
    if tracked.returncode != 0:
        failures.append(tracked.stderr.strip() or "Unable to list tracked files")
    else:
        tracked_paths = (path for path in tracked.stdout.split("\0") if path)
        for tracked_path in tracked_paths:
            if violates_private_boundary(tracked_path):
                failures.append(f"Tracked private/runtime artifact: {tracked_path}")

    if failures:
        print("Repository hygiene checks failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print("Repository hygiene checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
