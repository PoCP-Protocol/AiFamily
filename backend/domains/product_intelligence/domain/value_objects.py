"""Value objects/status enums for the Product Intelligence domain.

No TS predecessor — new domain (project owner Override #6). Status names
follow the project owner's instruction 01/03 vocabulary verbatim.

`ActorType` and the legal-transition set added in PR-001R (chief-architect
review on PR #27, items 4/5): actor identity/type must come from a trusted
`ActorContext` (see `application/context.py`), never from client-supplied
request fields, and hypothesis validation must be a real state-machine
transition, not a string-prefix check.
"""
from __future__ import annotations

from typing import Literal

HypothesisStatus = Literal["DRAFT", "UNDER_REVIEW", "VALIDATED", "REJECTED", "RETIRED"]
ContradictionStatus = Literal["DRAFT", "UNDER_REVIEW", "APPROVED", "RETIRED"]
StrategyStatus = Literal["DRAFT", "UNDER_REVIEW", "APPROVED", "RETIRED"]
OpportunityStatus = Literal["INVEST", "EXPERIMENT", "WATCH", "MAINTAIN", "EXIT"]
ProductConceptStatus = Literal["DRAFT", "UNDER_REVIEW", "APPROVED", "RETIRED"]
GenericRecordStatus = Literal["DRAFT", "ACTIVE", "RETIRED"]

ActorType = Literal["HUMAN", "AI", "SYSTEM"]

HYPOTHESIS_VALIDATION_ALLOWED_FROM: frozenset[str] = frozenset({"DRAFT", "UNDER_REVIEW"})
"""Legal source states for a -> VALIDATED transition. REJECTED/RETIRED are
terminal for this transition — re-validating a previously rejected or
retired hypothesis requires creating a new hypothesis, not resurrecting the
old one, per the chief-architect ruling item 5.

NOTE: no command in this PR can ever set a hypothesis to `UNDER_REVIEW` —
`create_growth_hypothesis` always starts at `DRAFT`. `UNDER_REVIEW` is
included here as a reserved, currently-unreachable source state for a
future PR that adds an explicit "submit for review" step; it is not dead
code by mistake, it is dead code on purpose (found by independent review
during PR-001R — flagging so it isn't mistaken for an oversight later).
"""
