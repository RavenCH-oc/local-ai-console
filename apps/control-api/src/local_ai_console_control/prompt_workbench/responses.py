"""Typed future LLM structured-output DTOs; no response is generated in this phase."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


class PromptWorkbenchResponseValidationError(ValueError):
    """Reserved for application translation of a rejected structured response."""


class StructuredResponseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProposedRevisionPayload(StructuredResponseModel):
    positive_prompt: str = Field(min_length=1)
    negative_prompt: str = ""
    parameters: dict[str, JsonValue] = Field(default_factory=dict)
    change_log: str = Field(min_length=1)


class ProjectStatePatch(StructuredResponseModel):
    objective: str | None = None
    important_constraints_add: list[str] = Field(default_factory=list)
    must_preserve_add: list[str] = Field(default_factory=list)
    known_problems_add: list[str] = Field(default_factory=list)
    accepted_observations_add: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_a_meaningful_patch(self) -> "ProjectStatePatch":
        values = [
            self.objective.strip() if self.objective is not None else "",
            *self.important_constraints_add,
            *self.must_preserve_add,
            *self.known_problems_add,
            *self.accepted_observations_add,
        ]
        if not any(isinstance(value, str) and value.strip() for value in values):
            raise ValueError("Project state patches must propose at least one non-empty value.")
        return self


class PromptWorkbenchStructuredResponse(StructuredResponseModel):
    response_type: Literal["discussion", "revision", "clarification"]
    assistant_text: str
    proposed_revision: ProposedRevisionPayload | None = None
    project_state_patch: ProjectStatePatch | None = None
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def enforce_revision_artifact_lifecycle(self) -> "PromptWorkbenchStructuredResponse":
        if self.response_type == "revision" and self.proposed_revision is None:
            raise ValueError("Revision responses require a proposed revision artifact.")
        if self.response_type != "revision" and self.proposed_revision is not None:
            raise ValueError("Only revision responses can include a proposed revision artifact.")
        if any(not warning.strip() for warning in self.warnings):
            raise ValueError("Warnings cannot contain blank values.")
        return self
