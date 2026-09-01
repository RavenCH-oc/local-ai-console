"""Private Controller Runtime LLM configuration loading and validation."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
from typing import Mapping
from urllib.parse import urlsplit

from local_ai_console_control.llm.types import RuntimeSlot


LLM_RUNTIME_CONFIG_FILENAME = "llm-runtimes.json"
LLM_RUNTIME_CONFIG_SCHEMA_VERSION = "1.0.0"
SUPPORTED_PROVIDER = "llama_cpp"
_ENVIRONMENT_REFERENCE_PATTERN = re.compile(r"^[A-Z_][A-Z0-9_]*$")


class LlmRuntimeConfigError(ValueError):
    """A sanitized configuration error that never includes config content or secrets."""


@dataclass(frozen=True, slots=True)
class LlmTimeoutConfig:
    connect_seconds: float = 10.0
    read_seconds: float = 300.0


@dataclass(frozen=True, slots=True)
class LlmRuntimeSlotConfig:
    slot: RuntimeSlot
    provider: str
    base_url: str
    api_key_env: str | None
    expected_model_alias: str | None
    timeouts: LlmTimeoutConfig


@dataclass(frozen=True, slots=True)
class LlmRuntimeConfig:
    schema_version: str
    slots: Mapping[RuntimeSlot, LlmRuntimeSlotConfig]

    def slot_config(self, slot: RuntimeSlot) -> LlmRuntimeSlotConfig | None:
        return self.slots.get(slot)


class LlmRuntimeConfigLoader:
    """Load only the trusted private config file under the already-resolved Controller Runtime."""

    def __init__(self, config_directory: Path) -> None:
        self._config_path = config_directory / LLM_RUNTIME_CONFIG_FILENAME

    @property
    def config_path(self) -> Path:
        return self._config_path

    def load(self) -> LlmRuntimeConfig | None:
        """Return None for no configuration; reject malformed or unsupported configuration explicitly."""

        if not self._config_path.is_file():
            return None
        try:
            payload = json.loads(self._config_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise LlmRuntimeConfigError("LLM runtime configuration is unreadable or malformed JSON.") from error
        if not isinstance(payload, dict):
            raise LlmRuntimeConfigError("LLM runtime configuration root must be an object.")
        if set(payload).difference({"schema_version", "slots"}):
            raise LlmRuntimeConfigError("LLM runtime configuration contains an unsupported field.")
        if payload.get("schema_version") != LLM_RUNTIME_CONFIG_SCHEMA_VERSION:
            raise LlmRuntimeConfigError("LLM runtime configuration schema version is unsupported.")
        slots_payload = payload.get("slots")
        if not isinstance(slots_payload, dict):
            raise LlmRuntimeConfigError("LLM runtime configuration requires a slots object.")
        unknown_slots = set(slots_payload).difference({slot.value for slot in RuntimeSlot})
        if unknown_slots:
            raise LlmRuntimeConfigError("LLM runtime configuration contains an unknown slot.")

        slots: dict[RuntimeSlot, LlmRuntimeSlotConfig] = {}
        for slot in RuntimeSlot:
            entry = slots_payload.get(slot.value)
            if entry is None:
                continue
            slots[slot] = self._parse_slot(slot, entry)
        return LlmRuntimeConfig(schema_version=LLM_RUNTIME_CONFIG_SCHEMA_VERSION, slots=slots)

    def _parse_slot(self, slot: RuntimeSlot, entry: object) -> LlmRuntimeSlotConfig:
        if not isinstance(entry, dict):
            raise LlmRuntimeConfigError("Each configured LLM slot must be an object.")
        if set(entry).difference({"provider", "base_url", "api_key_env", "expected_model_alias", "timeouts"}):
            raise LlmRuntimeConfigError("LLM runtime slot contains an unsupported field.")
        provider = entry.get("provider")
        if provider != SUPPORTED_PROVIDER:
            raise LlmRuntimeConfigError("LLM runtime configuration contains an unsupported provider.")
        base_url = entry.get("base_url")
        if not isinstance(base_url, str) or not self._is_valid_base_url(base_url):
            raise LlmRuntimeConfigError("LLM runtime base URL must be an absolute HTTP(S) URL.")
        api_key_env = entry.get("api_key_env")
        if api_key_env is not None and (
            not isinstance(api_key_env, str) or not _ENVIRONMENT_REFERENCE_PATTERN.fullmatch(api_key_env)
        ):
            raise LlmRuntimeConfigError("LLM API key environment reference is invalid.")
        expected_model_alias = entry.get("expected_model_alias")
        if expected_model_alias is not None and (
            not isinstance(expected_model_alias, str) or not expected_model_alias.strip()
        ):
            raise LlmRuntimeConfigError("LLM expected model alias is invalid.")
        timeouts = self._parse_timeouts(entry.get("timeouts"))
        return LlmRuntimeSlotConfig(
            slot=slot,
            provider=provider,
            base_url=base_url.rstrip("/"),
            api_key_env=api_key_env,
            expected_model_alias=expected_model_alias.strip() if isinstance(expected_model_alias, str) else None,
            timeouts=timeouts,
        )

    @staticmethod
    def _is_valid_base_url(value: str) -> bool:
        parsed = urlsplit(value)
        return (
            parsed.scheme in {"http", "https"}
            and bool(parsed.netloc)
            and parsed.username is None
            and parsed.password is None
            and not parsed.query
            and not parsed.fragment
        )

    @staticmethod
    def _parse_timeouts(value: object) -> LlmTimeoutConfig:
        if value is None:
            return LlmTimeoutConfig()
        if not isinstance(value, dict):
            raise LlmRuntimeConfigError("LLM runtime timeouts must be an object.")
        if set(value).difference({"connect_seconds", "read_seconds"}):
            raise LlmRuntimeConfigError("LLM runtime timeouts contain an unsupported field.")
        connect = value.get("connect_seconds", 10.0)
        read = value.get("read_seconds", 300.0)
        if (
            isinstance(connect, bool)
            or isinstance(read, bool)
            or not isinstance(connect, int | float)
            or not isinstance(read, int | float)
            or connect <= 0
            or read <= 0
        ):
            raise LlmRuntimeConfigError("LLM runtime timeouts must be positive numbers.")
        return LlmTimeoutConfig(connect_seconds=float(connect), read_seconds=float(read))


def read_api_key(slot_config: LlmRuntimeSlotConfig, environ: Mapping[str, str] | None = None) -> str | None:
    """Resolve only the configured secret reference without exposing its value elsewhere."""

    if slot_config.api_key_env is None:
        return None
    environment = os.environ if environ is None else environ
    api_key = environment.get(slot_config.api_key_env)
    return api_key if api_key else None
