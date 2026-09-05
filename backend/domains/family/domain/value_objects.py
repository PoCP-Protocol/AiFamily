"""Closed vocabularies for the family core aggregate.

Every literal below is transcribed from `database/baseline/0001_family_identity.sql`,
which creates the Postgres enum types this domain's rows are constrained by. The
direction of authority is SQL → Python: `0001` is a baselined historical artefact
that must stay checksum-identical to the legacy migration
(`database/tests/test_baseline_linearisation.py` asserts it), so where the two
disagree the SQL is right and this module is wrong.

Two of these vocabularies are narrower than a reader might expect, and both are
faithful rather than accidental:

* ``LifeStageCode`` has exactly one member. The legacy enum
  ``life_stage_code`` is a single-value enum (``EARLY_ADOLESCENCE_12_15``), which
  is what M1 shipped. Widening it means an ``ALTER TYPE`` in a new revision plus
  the product decision about what the other stages *are* — not a Python edit.
* ``ConsentPurpose`` here has eight members while
  ``backend/platform/consent/models.py``'s ``ConsentPurpose`` has four. They are
  different vocabularies with different jobs and are deliberately not unified —
  see ``consent_purpose_to_platform`` below for why, and for the mapping that
  makes them meet.
"""

from __future__ import annotations

from typing import Literal, get_args

from backend.platform.consent.models import ConsentPurpose as PlatformConsentPurpose

from .errors import FamilyValidationError

FamilyStatus = Literal["ACTIVE", "INACTIVE", "ARCHIVED"]
PersonType = Literal["PARENT", "CHILD"]
ParentRole = Literal["MOTHER", "FATHER", "GUARDIAN", "OTHER_GUARDIAN"]
RelationshipType = Literal["PARENT_CHILD", "SPOUSE", "SIBLING", "GUARDIAN_CHILD", "OTHER"]
LifeStageCode = Literal["EARLY_ADOLESCENCE_12_15"]

#: The legacy `consent_purpose` enum. Eight members, of which four have no
#: counterpart in the platform taxonomy.
ConsentPurpose = Literal[
    "SERVICE",
    "ASSESSMENT",
    "AI_PERSONALIZATION",
    "GROWTH_TRACKING",
    "EXPERT_SERVICE",
    "RESEARCH",
    "MODEL_IMPROVEMENT",
    "CONTENT_PUBLICATION",
]

#: The legacy `consent_status` enum: three members, no REFUSED.
#:
#: `backend/platform/consent/models.py::ConsentStatus` has a fourth, ``REFUSED``,
#: added to close a real legal gap (《儿童个人信息网络保护规定》第10条 requires the
#: refusal option to be offered, and a refusal that cannot be recorded is not
#: provably offered). This domain **cannot** persist it: the column's Postgres
#: type has three labels and adding a fourth is `ALTER TYPE ... ADD VALUE`, which
#: is a migration plus a product decision about the refusal UI, not a Python
#: literal. Registered as a known gap rather than papered over by mapping REFUSED
#: onto WITHDRAWN — those two are different facts (§10 is satisfied by the first
#: and not by the second), and collapsing them would destroy the distinction the
#: platform layer exists to preserve.
ConsentStatus = Literal["GRANTED", "WITHDRAWN", "EXPIRED"]

FAMILY_STATUSES: frozenset[str] = frozenset(get_args(FamilyStatus))
PERSON_TYPES: frozenset[str] = frozenset(get_args(PersonType))
PARENT_ROLES: frozenset[str] = frozenset(get_args(ParentRole))
RELATIONSHIP_TYPES: frozenset[str] = frozenset(get_args(RelationshipType))
LIFE_STAGE_CODES: frozenset[str] = frozenset(get_args(LifeStageCode))
CONSENT_PURPOSES: frozenset[str] = frozenset(get_args(ConsentPurpose))
CONSENT_STATUSES: frozenset[str] = frozenset(get_args(ConsentStatus))

#: Legacy purpose → platform purpose. Partial on purpose.
#:
#: `ConsentGate` is the only consent check in this repository and it takes
#: `backend.platform.consent.models.ConsentPurpose`. So a stored `consents` row
#: has to be translatable into that taxonomy before any domain can act on it.
#: The four legacy purposes with no platform counterpart (EXPERT_SERVICE,
#: RESEARCH, MODEL_IMPROVEMENT, CONTENT_PUBLICATION) are **absent from this map
#: rather than folded into the nearest neighbour**. Mapping MODEL_IMPROVEMENT
#: onto AI_PERSONALIZATION would be the single most dangerous line this domain
#: could contain: PIPL 第29条 单独同意 means "consented to personalised
#: recommendations" is not "consented to have my child's data train a model", and
#: a lookup table is not the place to make that equivalence. A grant for an
#: unmapped purpose therefore permits nothing through `ConsentGate` — the same
#: answer as no grant at all, which is the fail-closed direction.
_PLATFORM_PURPOSE_BY_LEGACY: dict[str, PlatformConsentPurpose] = {
    "SERVICE": PlatformConsentPurpose.SERVICE,
    "ASSESSMENT": PlatformConsentPurpose.ASSESSMENT,
    "AI_PERSONALIZATION": PlatformConsentPurpose.AI_PERSONALIZATION,
    "GROWTH_TRACKING": PlatformConsentPurpose.GROWTH_TRACKING,
}

#: Legacy purposes with no platform counterpart. Named so callers can say
#: "unmapped" rather than "unknown", which are different problems.
UNMAPPED_CONSENT_PURPOSES: frozenset[str] = CONSENT_PURPOSES - set(_PLATFORM_PURPOSE_BY_LEGACY)


def consent_purpose_to_platform(purpose: str) -> PlatformConsentPurpose | None:
    """The platform purpose for a stored legacy purpose, or ``None`` if unmapped.

    ``None`` is a real answer, not an error: the grant exists and is a fact worth
    keeping, it simply cannot authorise anything through a gate whose vocabulary
    does not contain its purpose.
    """
    return _PLATFORM_PURPOSE_BY_LEGACY.get(purpose)


def platform_purpose_to_legacy(purpose: PlatformConsentPurpose) -> str:
    """Inverse of the above. Total, because the platform taxonomy is a subset."""
    for legacy, platform in _PLATFORM_PURPOSE_BY_LEGACY.items():
        if platform is purpose:
            return legacy
    raise FamilyValidationError(f"consent_purpose_not_representable:{purpose.value}")
