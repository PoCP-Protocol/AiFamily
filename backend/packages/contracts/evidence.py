"""Evidence/provenance vocabulary shared by the product-strategy skeleton
domains.

Aligned with (not duplicating) the evidence-tier vocabulary and gating logic
in `20_知识_knowledge/byresearch/evidence.py` (the single implementation of
record E0-E7 rules per `CLAUDE.md` section 4 — "证据等级刻度与门禁的唯一实现").
This module only re-declares the tier *names* as a type, plus the two extra
tiers this platform needs (`simulated`, `inferred`) that are already named in
`CLAUDE.md` section 4 ("溯源为 simulated/inferred/unverified/unknown 的...不可用于
支撑'成立'"). It must never re-implement the gating rules themselves.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

EvidenceLevel = Literal[
    "E0",
    "E1",
    "E2",
    "E3",
    "E4",
    "E5",
    "E6",
    "E7",
    "simulated",
    "inferred",
    "unverified",
    "unknown",
]

NON_ESTABLISHING_LEVELS: frozenset[str] = frozenset(
    {"simulated", "inferred", "unverified", "unknown"}
)
"""Levels that, per `CLAUDE.md` section 4, can generate hypotheses / set
acceptance gates but can never be used to claim something "成立" (established).
Any promotion method in this skeleton (`promote_to_invest`, `promote_to_pilot`)
must reject a `Provenance` whose `level` is in this set.
"""


class Provenance(BaseModel):
    """Required on every product-strategy/product-factory schema in this
    package — no default value, forcing every caller to state explicitly
    where a piece of data came from.
    """

    level: EvidenceLevel
    source_ref: str | None = None
