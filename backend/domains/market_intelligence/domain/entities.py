"""Market Intelligence domain entities — empty-shell only.

No TS predecessor, and unlike `product_strategy`, this domain has **no
reserved slot** in `architecture/FAMILY_AI_PYTHON_ONLY_MIGRATION_PLAN_V1.md`
§8's Batch list — see
`architecture/FAMILY_PRODUCT_INTELLIGENCE_PLATFORM_TARGET_ARCHITECTURE_DRAFT_001.md`
§3, which flags Market Intelligence as the one piece of the original
proposal needing a new Batch (candidate Batch 9), not a slot inside Batch 7.

These two entities are intentionally empty shells (no methods, no
guardrails) — Market Intelligence has no approved P0/P1 increment at all
(unlike `product_strategy`, which mirrors the already-approved
`primary_contradiction` field), so there is nothing yet to encode behaviour
around.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from backend.packages.contracts.evidence import Provenance


class RawSignal(BaseModel):
    signal_id: str
    raw_text: str
    observed_at: datetime
    provenance: Provenance


class SignalCluster(BaseModel):
    cluster_id: str
    signal_ids: list[str]
    label: str
    provenance: Provenance
