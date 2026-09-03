"""Invariants the family core aggregate refuses to violate.

Most of this module is ordinary validation. Two functions are not, and they are
the reason it exists as a named module rather than inline `if`s:
`assert_no_consent_inference` and `assert_no_life_stage_inference` are the
executable form of M1-E2E-07 and M1-E2E-08.

Those two specs assert an *absence*: given a family that has a PARENT_CHILD
relationship, the aggregate's `consents` must be empty; given a child with a
`birth_date` of 2012-05-06, `lifeStages` must be empty. An absence is the hardest
kind of property to keep, because the way it breaks is somebody adding a helpful
default — "we know the parent is the guardian, so consent is implied", "we know
the child is 13, so the stage is EARLY_ADOLESCENCE_12_15". Both are one plausible
line of code, and both are unlawful:

* **Consent from relationship.** 《儿童个人信息网络保护规定》第9条 requires the
  guardian to be *told* and to *agree*; PIPL 第29条 requires 单独同意 per purpose.
  A relationship row records who is related to whom, which is a fact about the
  family, not an act of agreement about a purpose. Inferring consent from it
  manufactures the legal artefact whose entire value is that it was actually
  obtained.
* **LifeStage from birth_date.** A life stage is a professional judgement that
  drives which interventions a family is offered. Deriving it from arithmetic on
  a date makes it look like a Fact when it is at best a Perspective — the R9
  four-layer distinction (Fact ≠ Perspective ≠ Recommendation ≠ Action ≠ Outcome)
  applied to this domain's most tempting shortcut. The legacy DDL agrees: the
  assignment row carries `source varchar(64) NOT NULL DEFAULT 'MANUAL'`, so
  "where did this come from" is a stored column, which only makes sense if the
  answer can be something other than "we computed it".

Both functions are called from the *application* layer's read path, so the guard
sits between the repository and the caller and cannot be bypassed by a query that
forgets it.
"""

from __future__ import annotations

import datetime as _dt
import re
from collections.abc import Iterable, Sequence

from .errors import FamilyConflictError, FamilyForbiddenError, FamilyValidationError
from .value_objects import (
    CONSENT_PURPOSES,
    CONSENT_STATUSES,
    FAMILY_STATUSES,
    LIFE_STAGE_CODES,
    PARENT_ROLES,
    PERSON_TYPES,
    RELATIONSHIP_TYPES,
)

#: `families.display_name` and `persons.display_name` are both `varchar(100)`.
DISPLAY_NAME_MAX_LENGTH = 100
#: `consents.policy_version` is `varchar(64)`; so is `life_stage_assignments.source`.
POLICY_VERSION_MAX_LENGTH = 64
LIFE_STAGE_SOURCE_MAX_LENGTH = 64

#: R9's red line, expressed as tokens no family-core field may contain.
#:
#: Same device as `membership`'s `FORBIDDEN_TIER_FIELD_TOKENS`, applied to the one
#: place in this domain where an unreviewed field name could arrive: nothing here
#: takes free-form attributes today, so this guard is on the *entity field names*
#: and is asserted by a test that walks the models. It is here rather than only in
#: a test because a domain that states its own red line can be read by the next
#: author; a red line that lives only in `tests/` is discovered by breaking it.
FORBIDDEN_SCORING_TOKENS: frozenset[str] = frozenset(
    {
        "score",
        "scores",
        "scoring",
        "rank",
        "ranking",
        "rating",
        "grade",
        "percentile",
        "leaderboard",
        "total_points",
    }
)

_AI_ACTOR_PREFIX = "ai:"


def assert_human_actor(actor: str, *, code: str) -> None:
    """Refuse an `ai:`-prefixed actor.

    Every mutation in this domain writes a canonical Fact about a real family —
    who its members are, who is related to whom, what a guardian agreed to. R9
    puts AI output in the Perspective/Recommendation layer with a human gate
    before it can become Fact, so there is no family-core mutation an AI actor may
    perform. This is not "AI is untrusted"; it is that consent recorded by a model
    is not consent.
    """
    if actor.startswith(_AI_ACTOR_PREFIX):
        raise FamilyForbiddenError(f"human_actor_required:{code}")


def assert_family_scope(*, expected_family_id: str, actual_family_id: str) -> None:
    """Every row read or written must belong to the authenticated family."""
    if expected_family_id != actual_family_id:
        raise FamilyForbiddenError("family_scope_violation")


def assert_display_name(value: str, *, field: str) -> None:
    stripped = value.strip()
    if not stripped:
        raise FamilyValidationError(f"{field}_required")
    if len(value) > DISPLAY_NAME_MAX_LENGTH:
        raise FamilyValidationError(f"{field}_too_long")


def assert_family_status(value: str) -> None:
    if value not in FAMILY_STATUSES:
        raise FamilyValidationError(f"family_status_invalid:{value}")


def assert_person_type(value: str) -> None:
    if value not in PERSON_TYPES:
        raise FamilyValidationError(f"person_type_invalid:{value}")


def assert_parent_role_consistency(*, person_type: str, parent_role: str | None) -> None:
    """The `parent_role_only_for_parent` CHECK from 0001, in Python.

    Duplicated deliberately: the CHECK is the backstop, but a violation caught
    only by Postgres surfaces as an opaque `IntegrityError` at commit time, after
    the audit event has already been recorded. Refusing here means the refusal is
    a typed domain error with a code the HTTP layer can map.
    """
    if person_type == "PARENT":
        if parent_role is None:
            raise FamilyValidationError("parent_role_required_for_parent")
        if parent_role not in PARENT_ROLES:
            raise FamilyValidationError(f"parent_role_invalid:{parent_role}")
    elif person_type == "CHILD" and parent_role is not None:
        raise FamilyValidationError("parent_role_forbidden_for_child")


def assert_relationship_type(value: str) -> None:
    if value not in RELATIONSHIP_TYPES:
        raise FamilyValidationError(f"relationship_type_invalid:{value}")


def assert_relationship_endpoints(*, person_a_id: str, person_b_id: str) -> None:
    """The `relationship_not_self` CHECK from 0001."""
    if person_a_id == person_b_id:
        raise FamilyValidationError("relationship_not_self")


def assert_life_stage_code(value: str) -> None:
    if value not in LIFE_STAGE_CODES:
        raise FamilyValidationError(f"life_stage_code_invalid:{value}")


def assert_life_stage_window(
    *, effective_from: _dt.datetime, effective_to: _dt.datetime | None
) -> None:
    """The `life_stage_time` CHECK from 0001."""
    if effective_to is not None and effective_to <= effective_from:
        raise FamilyValidationError("life_stage_time_invalid")


def assert_consent_purpose(value: str) -> None:
    if value not in CONSENT_PURPOSES:
        raise FamilyValidationError(f"consent_purpose_invalid:{value}")


def assert_consent_status(value: str) -> None:
    if value not in CONSENT_STATUSES:
        raise FamilyValidationError(f"consent_status_invalid:{value}")


def assert_policy_version(value: str) -> None:
    """`consents.policy_version` is NOT NULL, and blank is not a version.

    A grant whose policy version is unknown cannot answer "what were they told
    when they agreed", which is exactly what 《儿童个人信息网络保护规定》第10条's
    七项告知 and its "substantive change requires re-consent" clause need it for.
    """
    stripped = value.strip()
    if not stripped:
        raise FamilyValidationError("consent_policy_version_required")
    if len(value) > POLICY_VERSION_MAX_LENGTH:
        raise FamilyValidationError("consent_policy_version_too_long")


def assert_life_stage_source(value: str) -> None:
    stripped = value.strip()
    if not stripped:
        raise FamilyValidationError("life_stage_source_required")
    if len(value) > LIFE_STAGE_SOURCE_MAX_LENGTH:
        raise FamilyValidationError("life_stage_source_too_long")


def assert_no_family_scoring_field_names(field_names: Iterable[str]) -> None:
    """R9 — no field in this domain scores or ranks a family or a child.

    Token-substring rather than exact match, so `family_score`,
    `harmony_rating_v2` and `child_percentile` are all caught. There is no
    allow-list escape hatch: unlike `service`, where a customer rating the
    provider's delivered session is the opposite direction of power and is
    legitimate, family core has no row that legitimately rates anybody. If one is
    ever proposed, it is an ADR.
    """
    offenders = sorted(
        name
        for name in field_names
        for token in FORBIDDEN_SCORING_TOKENS
        if token in re.sub(r"[^a-z0-9]+", "_", name.lower())
    )
    if offenders:
        raise FamilyValidationError("family_scoring_field_forbidden:" + ",".join(offenders))


# --------------------------------------------------------------------------
# The two negative-inference guards (M1-E2E-07 / M1-E2E-08)
# --------------------------------------------------------------------------


def assert_no_consent_inference(
    *,
    exposed_consent_ids: Sequence[str],
    stored_consent_ids: Sequence[str],
) -> None:
    """Every consent the aggregate exposes must be a row somebody wrote.

    This is M1-E2E-07 turned into an invariant that can fail. The spec's own
    assertion is "relationships has 1 entry and consents is empty", which is a
    statement about one fixture; the general property behind it is that the read
    model may not contain a consent that the repository did not return. So the
    application layer passes both sets and this refuses any id present in the
    first and absent from the second.

    That is checkable, unlike "did the author intend to infer". A helper like
    `_derive_guardian_consent(relationship)` fails here the first time it runs,
    because a synthesised grant has no stored counterpart — and if it borrows a
    stored id to look legitimate, the *count* differs, which is caught too.
    """
    stored = set(stored_consent_ids)
    fabricated = sorted(cid for cid in exposed_consent_ids if cid not in stored)
    if fabricated:
        raise FamilyForbiddenError("consent_inferred_not_granted:" + ",".join(fabricated))
    if len(exposed_consent_ids) > len(stored):
        raise FamilyForbiddenError("consent_count_exceeds_stored_grants")


def assert_no_life_stage_inference(
    *,
    exposed_assignment_ids: Sequence[str],
    stored_assignment_ids: Sequence[str],
    child_birth_dates: Sequence[_dt.date | None],
) -> None:
    """Every exposed LifeStage must be an assignment row, not arithmetic.

    Same construction as above, plus one extra check the birth dates make
    possible: if there are no stored assignments at all, the exposed list must be
    empty *even when* every child has a birth date that falls inside the one
    life-stage band this system knows about. That is the exact shape of
    M1-E2E-08 (child born 2012-05-06, stage EARLY_ADOLESCENCE_12_15 unassigned,
    `lifeStages` must be `[]`), and it is the case a birth-date-derived default
    would pass while the general id check alone might not, because a derivation
    that also persisted a row would have a stored id.

    `child_birth_dates` is therefore consumed, not decorative: it is what makes
    "there was enough information to guess, and we did not" an assertion.
    """
    stored = set(stored_assignment_ids)
    fabricated = sorted(aid for aid in exposed_assignment_ids if aid not in stored)
    if fabricated:
        raise FamilyForbiddenError("life_stage_inferred_not_assigned:" + ",".join(fabricated))
    if not stored and exposed_assignment_ids:
        raise FamilyForbiddenError(
            "life_stage_inferred_from_birth_date:"
            f"{len([d for d in child_birth_dates if d is not None])}_dated_children"
        )


def assert_unique_active_life_stage(*, existing_active_count: int) -> None:
    """The `uq_active_life_stage` partial unique index from 0001, in Python.

    Postgres enforces "at most one row per child with `effective_to IS NULL`".
    Refusing here turns the second assignment into a typed 409 instead of an
    `IntegrityError` raised after the audit event was written.
    """
    if existing_active_count > 0:
        raise FamilyConflictError("life_stage_already_active")
