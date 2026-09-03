"""Inspectable, prefix-cache-aware prompt context assembly without LLM invocation."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Sequence

from local_ai_console_control.llm.types import LLMMessage, LLMMessageRole
from local_ai_console_control.persistence.models import PromptMessage, PromptProject, PromptProjectState, PromptRevision
from local_ai_console_control.prompt_workbench.catalog import BuiltInSkill, BuiltInWorkflow
from local_ai_console_control.prompt_workbench.knowledge import LoadedKnowledgeDocument


BASE_SYSTEM_IDENTITY = (
    "You are the Local AI Console Prompt Workbench assistant. Work from the selected skill and workflow, "
    "preserve explicit project constraints, and treat accepted revisions as authoritative until the user accepts a proposal. "
    "Do not silently replace accepted artifacts."
)


@dataclass(frozen=True, slots=True)
class PromptContextContribution:
    """One inspectable message contribution and its assembly metadata."""

    label: str
    kind: str
    source: str
    stability: str
    priority: int
    message: LLMMessage
    token_count: int | None = None

    @property
    def character_count(self) -> int:
        return len(self.message.content)


@dataclass(frozen=True, slots=True)
class PromptContext:
    """Assembled messages plus metadata, intentionally independent of an LLM request."""

    contributions: tuple[PromptContextContribution, ...]

    @property
    def messages(self) -> tuple[LLMMessage, ...]:
        return tuple(contribution.message for contribution in self.contributions)


def _system_contribution(
    *, label: str, kind: str, source: str, stability: str, priority: int, content: str
) -> PromptContextContribution:
    return PromptContextContribution(
        label=label,
        kind=kind,
        source=source,
        stability=stability,
        priority=priority,
        message=LLMMessage(LLMMessageRole.SYSTEM, content),
    )


class PromptContextAssembler:
    """Assemble logical context in correctness-first order; this class never calls a runtime."""

    def assemble(
        self,
        *,
        skill: BuiltInSkill,
        workflow: BuiltInWorkflow,
        mode: str,
        project: PromptProject,
        project_state: PromptProjectState,
        accepted_revision: PromptRevision | None,
        session_messages: Sequence[PromptMessage],
        selected_knowledge: Sequence[LoadedKnowledgeDocument],
        current_user_message: str,
    ) -> PromptContext:
        if mode not in workflow.supported_modes:
            raise ValueError("The selected workflow mode is not supported by the active workflow.")
        if not current_user_message.strip():
            raise ValueError("A current user message is required for prompt context assembly.")

        contributions: list[PromptContextContribution] = [
            _system_contribution(
                label="Base System",
                kind="instruction",
                source="prompt_workbench_base",
                stability="stable",
                priority=100,
                content=BASE_SYSTEM_IDENTITY,
            ),
            _system_contribution(
                label="Skill",
                kind="skill_instruction",
                source=skill.id,
                stability="stable",
                priority=90,
                content=skill.instruction_text,
            ),
            _system_contribution(
                label="Workflow",
                kind="workflow_instruction",
                source=workflow.id,
                stability="stable",
                priority=80,
                content=workflow.workflow_instructions,
            ),
            _system_contribution(
                label="Mode",
                kind="mode_instruction",
                source=f"{workflow.id}:{mode}",
                stability="stable",
                priority=70,
                content=workflow.mode_instructions[mode],
            ),
        ]
        for document in selected_knowledge:
            contributions.append(
                _system_contribution(
                    label=f"Knowledge source: {document.label}",
                    kind="knowledge",
                    source=document.source_id,
                    stability=document.stability,
                    priority=60,
                    content=f"Knowledge source {document.source_id}:\n{document.content}",
                )
            )
        state_content = json.dumps(
            {
                "objective": project_state.objective,
                "important_constraints": project_state.important_constraints,
                "must_preserve": project_state.must_preserve,
                "known_problems": project_state.known_problems,
                "accepted_observations": project_state.accepted_observations,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        contributions.append(
            _system_contribution(
                label="Project State",
                kind="project_state",
                source=project.id,
                stability="snapshot",
                priority=50,
                content=f"Prompt Project State:\n{state_content}",
            )
        )
        if accepted_revision is not None:
            revision_content = json.dumps(
                {
                    "positive_prompt": accepted_revision.positive_prompt,
                    "negative_prompt": accepted_revision.negative_prompt,
                    "parameters": accepted_revision.parameters,
                    "change_log": accepted_revision.change_log,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            contributions.append(
                _system_contribution(
                    label="Accepted Revision",
                    kind="accepted_revision",
                    source=accepted_revision.id,
                    stability="snapshot",
                    priority=45,
                    content=f"Current accepted Prompt Revision:\n{revision_content}",
                )
            )
        for message in session_messages:
            contributions.append(
                PromptContextContribution(
                    label="Discussion",
                    kind="discussion",
                    source=message.id,
                    stability="append_only",
                    priority=30,
                    message=LLMMessage(LLMMessageRole(message.role), message.content),
                )
            )
        contributions.append(
            PromptContextContribution(
                label="Current Request",
                kind="current_request",
                source="current_user_message",
                stability="dynamic",
                priority=10,
                message=LLMMessage(LLMMessageRole.USER, current_user_message.strip()),
            )
        )
        return PromptContext(contributions=tuple(contributions))
