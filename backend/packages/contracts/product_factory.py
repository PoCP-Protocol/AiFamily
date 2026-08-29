"""Composable product factory contracts migrated from family-ai.

These are schemas only; they do not execute product or AI decisions.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

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
    product_id: str
    version: int
    segment: dict
    growth_need: str
    problem: str
    contradiction: str | None = None
    strategy: str | None = None
    pattern: str
    stages: list[str]
    human_trigger: list[str] = Field(default_factory=list)
    evaluation: str | None = None
    provenance: Provenance
