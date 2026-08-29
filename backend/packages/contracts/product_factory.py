"""Composable Product Factory schemas — STRUCTURE_ONLY.

No TS predecessor. `ProductDefinition` is the Python schema restatement of
the FPDL example in the project-owner's original proposal (reconciled in
`FAMILY_PRODUCT_INTELLIGENCE_PLATFORM_TARGET_ARCHITECTURE_DRAFT_001.md` §4).
Field names deliberately match the proposal's YAML example 1:1 so a future
FPDL parser can map YAML keys to this schema without renaming.
"""

from __future__ import annotations

from pydantic import BaseModel

from .evidence import Provenance


class Component(BaseModel):
    component_id: str
    component_type: str
    version: int
    input_schema_ref: str | None = None
    output_schema_ref: str | None = None
    provenance: Provenance


class Pattern(BaseModel):
    pattern_id: str
    component_ids: list[str]
    description: str
    provenance: Provenance


class ProductDefinition(BaseModel):
    """FPDL v0 — field names match the proposal's YAML example
    (segment/growth_need/problem/contradiction/strategy/pattern/stages/
    human_trigger/evaluation)."""

    product_id: str
    version: int
    segment: dict
    growth_need: str
    problem: str
    contradiction: str | None = None
    strategy: str | None = None
    pattern: str
    stages: list[str]
    human_trigger: list[str] = []
    evaluation: str | None = None
    provenance: Provenance
