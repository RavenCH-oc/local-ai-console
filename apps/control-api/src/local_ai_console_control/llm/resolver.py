"""Small task-to-runtime resolver that preserves future MAIN/UTILITY flexibility."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

from local_ai_console_control.llm.types import RuntimeSlot, RuntimeTargetPreference, TaskKind


class RuntimeResolutionError(RuntimeError):
    """Raised when a requested task has no configured runtime slot."""


DEFAULT_AUTO_SLOT_POLICY: Mapping[TaskKind, tuple[RuntimeSlot, ...]] = {
    TaskKind.CHAT: (RuntimeSlot.MAIN, RuntimeSlot.UTILITY),
    TaskKind.PROMPT_GENERATION: (RuntimeSlot.MAIN, RuntimeSlot.UTILITY),
    TaskKind.CONTEXT_COMPRESSION: (RuntimeSlot.MAIN, RuntimeSlot.UTILITY),
}


@dataclass(frozen=True, slots=True)
class TaskRuntimeResolver:
    """Resolve generic task semantics without leaking provider-specific branching upward."""

    auto_slot_policy: Mapping[TaskKind, Sequence[RuntimeSlot]] = field(
        default_factory=lambda: dict(DEFAULT_AUTO_SLOT_POLICY)
    )

    def resolve(
        self,
        task_kind: TaskKind,
        target_preference: RuntimeTargetPreference,
        configured_slots: set[RuntimeSlot],
    ) -> RuntimeSlot:
        if target_preference is RuntimeTargetPreference.MAIN:
            return self._require_configured(RuntimeSlot.MAIN, configured_slots)
        if target_preference is RuntimeTargetPreference.UTILITY:
            return self._require_configured(RuntimeSlot.UTILITY, configured_slots)

        for candidate in self.auto_slot_policy[task_kind]:
            if candidate in configured_slots:
                return candidate
        raise RuntimeResolutionError("No configured runtime is available for this task.")

    @staticmethod
    def _require_configured(slot: RuntimeSlot, configured_slots: set[RuntimeSlot]) -> RuntimeSlot:
        if slot not in configured_slots:
            raise RuntimeResolutionError("Requested runtime slot is not configured.")
        return slot
