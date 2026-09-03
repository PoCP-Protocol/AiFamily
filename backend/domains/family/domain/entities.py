"""Family core entities.

Field names mirror `database/baseline/0001_family_identity.sql` column-for-column
so the Python side and the SQL SSOT cannot drift. Direction of authority is
SQL → Python: `0001` is a baselined historical artefact and is not editable, so
where the two disagree the SQL wins and this module is wrong.

No FastAPI / SQLAlchemy import here (four-layer rule,
`docs/10_engineering/ENGINEERING_ARCHITECTURE.md`).

Four structural decisions, all load-bearing:

* **`FamilyMember` is one entity, not `Parent` and `Child`.** The task asked for a
  judgement with a reason if they were split, and they are not, because `persons`
  is one table with a `person_type` discriminator and a CHECK constraint
  (`parent_role_only_for_parent`) tying the one role column to it. Splitting into
  two aggregates in Python while one table holds both would mean a
  `person_id`-shaped foreign key that could point at either, and the acceptance
  spec reads them back as a single sorted `members` list
  (`members.map(person_type).sort() == ['CHILD','PARENT']`). Two classes would
  make that list heterogeneous for no gain. The discriminator invariant is
  enforced by `assert_parent_role_consistency`, which is what a split would have
  bought.
* **No field anywhere scores or ranks a family or a child.** R9. Unlike `service`
  — where `service_quality_rating` legitimately rates a *purchased session* —
  there is nothing in family core that rates anybody, and
  `policies.assert_no_family_scoring_field_names` is asserted against these
  classes' own field names by a test.
* **`birth_date` is a `date`, and nothing derives anything from it.** It exists
  because `persons.birth_date` exists and the spec round-trips `'2012-05-06'`. It
  is deliberately *not* accompanied by an `age` property: an `age` property is one
  autocomplete away from the LifeStage inference M1-E2E-08 forbids. Age is
  computed exactly once in this domain, inside `Consent.subject_age_years`, where
  a compliance question (PIPL 第28/31条 under-14) genuinely requires it.
* **Immutable, with transitions as methods.** Every state change returns a new
  copy with `version` bumped where the table has one. A caller cannot reach a
  status by assignment.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from pydantic import BaseModel, model_validator

from .errors import FamilyConflictError
from .policies import (
    assert_consent_purpose,
    assert_consent_status,
    assert_display_name,
    assert_family_status,
    assert_life_stage_code,
    assert_life_stage_source,
    assert_life_stage_window,
    assert_parent_role_consistency,
    assert_person_type,
    assert_policy_version,
    assert_relationship_endpoints,
    assert_relationship_type,
)
from .value_objects import (
    ConsentPurpose,
    ConsentStatus,
    FamilyStatus,
    LifeStageCode,
    ParentRole,
    PersonType,
    RelationshipType,
)


def utcnow() -> datetime:
    """Naive-UTC now.

    Naive rather than aware for the same reason `service` and `membership` do it:
    the SQLite fast test path drops `tzinfo`, so an aware value written and read
    back compares unequal to itself and every round-trip assertion becomes a
    false failure. Recorded as an accepted gap in
    `docs/06_platform/CONSENT.md` §3 gap 7; `ConsentGrant` tolerates both sides
    and normalises before comparing, so the platform consent gate is unaffected.
    """
    return datetime.now(UTC).replace(tzinfo=None)


class Family(BaseModel):
    """The `families` row.

    `primary_contact_person_id` is nullable and stays null until a member exists —
    the FK on it is `DEFERRABLE INITIALLY DEFERRED` in 0001 precisely because the
    family must be insertable before any person is. `attach_primary_contact` is
    the only way to set it, and it refuses to move an already-set contact so that
    "who speaks for this family" is not silently reassigned by a member being
    added.
    """

    model_config = {"frozen": True}

    family_id: str
    display_name: str
    status: FamilyStatus = "ACTIVE"
    primary_contact_person_id: str | None = None
    version: int = 1
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def _validate(self) -> Family:
        assert_display_name(self.display_name, field="family_display_name")
        assert_family_status(self.status)
        if self.version < 1:
            raise ValueError("families.version has CHECK (version >= 1)")
        return self

    def attach_primary_contact(self, person_id: str, *, actor: str) -> Family:
        """Bind the first member as primary contact. Refuses to overwrite."""
        del actor  # recorded by the caller's AuditEvent, not stored on this row
        if self.primary_contact_person_id is not None:
            if self.primary_contact_person_id == person_id:
                return self
            raise FamilyConflictError("family_primary_contact_already_set")
        return self.model_copy(
            update={
                "primary_contact_person_id": person_id,
                "version": self.version + 1,
                "updated_at": utcnow(),
            }
        )


class FamilyMember(BaseModel):
    """A `persons` row. PARENT and CHILD are one type — see the module docstring.

    A child is a data subject under PIPL 第28条 whenever they are under 14, at
    which point *every* field here is sensitive personal information. This class
    does not decide anything on that basis; the decision belongs to `Consent`,
    which is where guardian consent is actually required.
    """

    model_config = {"frozen": True}

    person_id: str
    family_id: str
    person_type: PersonType
    parent_role: ParentRole | None = None
    display_name: str
    birth_date: date | None = None
    #: The external account this person signs in as, when they have one. Children
    #: normally do not. Nullable in 0001 and nullable here.
    account_id: str | None = None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def _validate(self) -> FamilyMember:
        assert_display_name(self.display_name, field="person_display_name")
        assert_person_type(self.person_type)
        assert_parent_role_consistency(
            person_type=self.person_type, parent_role=self.parent_role
        )
        return self

    @property
    def is_child(self) -> bool:
        return self.person_type == "CHILD"


class FamilyRelationship(BaseModel):
    """A `family_relationships` row.

    Stored directionally — `uq_relationship_directional` is on
    `(family_id, person_a_id, person_b_id, relationship_type)`. Note that
    `database/baseline/0004_relationship_symmetric_uniqueness.sql` later adds a
    *symmetric* uniqueness constraint on top; the application layer's duplicate
    check therefore looks for both orderings, because Postgres will refuse the
    reversed pair and a caller deserves a typed 409 rather than an
    `IntegrityError`.

    This row is a fact about kinship and **authorises nothing** — see
    `policies.assert_no_consent_inference` (M1-E2E-07).
    """

    model_config = {"frozen": True}

    relationship_id: str
    family_id: str
    person_a_id: str
    person_b_id: str
    relationship_type: RelationshipType
    created_at: datetime

    @model_validator(mode="after")
    def _validate(self) -> FamilyRelationship:
        assert_relationship_type(self.relationship_type)
        assert_relationship_endpoints(
            person_a_id=self.person_a_id, person_b_id=self.person_b_id
        )
        return self

    @property
    def unordered_key(self) -> tuple[str, str, str]:
        """`(low, high, type)` — the shape 0004's symmetric index makes unique."""
        low, high = sorted((self.person_a_id, self.person_b_id))
        return (low, high, self.relationship_type)


class LifeStageAssignment(BaseModel):
    """A `life_stage_assignments` row: a *judgement* about a child, with a source.

    `source` defaults to `MANUAL` in the DDL and this class keeps that default.
    The column only means something if the answer can be something other than
    "we computed it from birth_date" — which is why
    `policies.assert_no_life_stage_inference` exists (M1-E2E-08).

    `effective_to is None` means "currently active", and `uq_active_life_stage` is
    a partial unique index over exactly that predicate, so one child has at most
    one active stage. `supersede` is how a stage ends: it closes the window rather
    than deleting the row, because the history of a professional judgement is part
    of the record.
    """

    model_config = {"frozen": True}

    assignment_id: str
    family_id: str
    child_id: str
    life_stage_code: LifeStageCode
    effective_from: datetime
    effective_to: datetime | None = None
    source: str = "MANUAL"
    created_at: datetime

    @model_validator(mode="after")
    def _validate(self) -> LifeStageAssignment:
        assert_life_stage_code(self.life_stage_code)
        assert_life_stage_source(self.source)
        assert_life_stage_window(
            effective_from=self.effective_from, effective_to=self.effective_to
        )
        return self

    @property
    def is_active(self) -> bool:
        return self.effective_to is None

    def supersede(self, *, at: datetime | None = None) -> LifeStageAssignment:
        if self.effective_to is not None:
            raise FamilyConflictError("life_stage_already_superseded")
        moment = at or utcnow()
        if moment <= self.effective_from:
            # `life_stage_time` CHECK. Happens when two assignments land inside
            # the same clock tick; nudging by a microsecond keeps the row legal
            # without inventing a window that ends before it starts.
            moment = self.effective_from.replace(
                microsecond=min(self.effective_from.microsecond + 1, 999_999)
            )
        return self.model_copy(update={"effective_to": moment})


class Consent(BaseModel):
    """A `consents` row — the *stored* consent decision.

    This is the body of a consent record; `backend/platform/consent` holds the
    *check* (`ConsentGate`) and its value objects but has no storage at all
    (its own docstring: "wiring this to a real database ... is explicitly deferred
    to whichever domain repository first needs it"). This class is that storage,
    and `infrastructure/consent_query.py` is the adapter that turns these rows
    into `ConsentGrant`s for the gate. The two layers stay separate: the gate must
    keep holding no state, and this row must keep being able to represent legacy
    purposes the gate's taxonomy does not have.

    **`withdraw` is not a delete.** 第10条 requires the withdrawal route to exist
    and the record of what was agreed to survive it; `status='WITHDRAWN'` plus
    `withdrawn_at` is what the DDL's `withdrawn_time_consistent` CHECK enforces,
    and the row stays.

    **`subject_age_years` is the only age arithmetic in this domain.** It exists
    because PIPL 第31条 makes guardian consent mandatory below 14 and the check is
    not expressible without it. Read the constant's docstring in
    `backend/platform/consent/models.py` before using it for anything else: per
    `COMPLIANCE_HARD_CONSTRAINTS.md` §9 the 14 line governs *consent to collect*
    and guardian-facing UI defaults, and must not be used to close the statutory
    data channel for guardians of 14–17 year olds. Nothing here keys an access
    decision on age.
    """

    model_config = {"frozen": True}

    consent_id: str
    family_id: str
    subject_person_id: str
    guardian_person_id: str
    purpose: ConsentPurpose
    status: ConsentStatus
    policy_version: str
    granted_at: datetime
    withdrawn_at: datetime | None = None
    created_at: datetime

    @model_validator(mode="after")
    def _validate(self) -> Consent:
        assert_consent_purpose(self.purpose)
        assert_consent_status(self.status)
        assert_policy_version(self.policy_version)
        # `withdrawn_time_consistent` CHECK from 0001.
        if self.status == "WITHDRAWN" and self.withdrawn_at is None:
            raise ValueError("consents.withdrawn_at is required when status='WITHDRAWN'")
        return self

    @property
    def is_active(self) -> bool:
        return self.status == "GRANTED"

    def withdraw(self, *, at: datetime | None = None) -> Consent:
        if self.status != "GRANTED":
            raise FamilyConflictError(f"consent_not_withdrawable:{self.status}")
        return self.model_copy(update={"status": "WITHDRAWN", "withdrawn_at": at or utcnow()})

    def expire(self) -> Consent:
        """Retire a superseded policy version. M1-E2E-06's mechanism.

        The spec grants `family-consent-v1` then `family-consent-v2` and asserts
        the rows end as `[EXPIRED, GRANTED]` ordered by policy version, with only
        the second exposed. So a new grant for the same (subject, purpose) does not
        stack — it supersedes, and the old row becomes EXPIRED rather than
        WITHDRAWN, because nobody took the consent back.
        """
        if self.status != "GRANTED":
            raise FamilyConflictError(f"consent_not_expirable:{self.status}")
        return self.model_copy(update={"status": "EXPIRED"})

    def subject_age_years(
        self, *, birth_date: date | None, at: datetime | None = None
    ) -> int | None:
        """The subject's whole-year age, or ``None`` when no birth date is stored.

        ``None`` is a real answer and callers must handle it as "unknown", never as
        "adult": `persons.birth_date` is nullable, and defaulting an unknown age to
        the permissive side would skip the under-14 guardian requirement for
        exactly the children whose records are least complete.
        """
        if birth_date is None:
            return None
        moment = (at or utcnow()).date()
        return (
            moment.year
            - birth_date.year
            - ((moment.month, moment.day) < (birth_date.month, birth_date.day))
        )
