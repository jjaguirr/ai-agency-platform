"""
Workflow generation from conversational process descriptions.

See docs/plans/2026-03-05-workflow-generation-design.md for the full picture.
This module is stateless: generate() takes a description and returns either a
workflow, a set of clarifying questions, or a template-match signal. The EA's
LangGraph owns the clarification loop.
"""
from typing import Literal

from pydantic import BaseModel, Field


# --- parsed process: LLM structured-output schema ---------------------------
# These models are both the Pydantic schema passed to the LLM and the input
# to the assembler. Keep them tight — every field here is something the model
# has to fill.


class TriggerSpec(BaseModel):
    kind: Literal["schedule", "webhook", "manual"]
    cron: str | None = None
    event_source: str | None = None


class StepSpec(BaseModel):
    action: str
    service: str | None = None
    inputs_from: list[int] = Field(default_factory=list)
    condition: str | None = None


class ParsedProcess(BaseModel):
    trigger: TriggerSpec
    steps: list[StepSpec]
    confidence: float = Field(ge=0.0, le=1.0)
    gaps: list[str] = Field(default_factory=list)
