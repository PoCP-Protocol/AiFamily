"""AuditEvent — the record R6 requires, extended to cover read access.

Two legal obligations meet in this one record type.

**R6 (state mutation)** — REPOSITORY_CONSTITUTION.md: "任何对权威业务状态的写入，
必须产生 AuditEvent，至少记录 actor / tenant / action / resource / before /
after / reason / correlation_id / timestamp."

**《未成年人网络保护条例》第36条 (read access)** — staff access to a minor's
personal information must be minimally authorised, **approved** by the
responsible person or an authorised manager, and the **access itself
recorded**. See `docs/12_governance/COMPLIANCE_HARD_CONSTRAINTS.md` §8: this
is an explicit extension of R6, because R6 as written only covers writes.

Why one type with a discriminator rather than two sibling types
---------------------------------------------------------------
A read has no `before`/`after`; a mutation has no `purpose`/`approval`. Both
were expressible as "just leave the field None" if the two shapes shared an
undiscriminated record — and "leave it None" is exactly how a read access
event ends up indistinguishable from a create-with-no-prior-state. The
`AuditActionKind` discriminator makes the distinction a *type-level* fact:

* `MUTATION` may carry `before`/`after`, and forbids the read-access fields
  (`subject_person_id` / `accessed_fields` / `access_purpose` /
  `approval_ref`) — a write is not an access grant.
* `READ` forbids `before`/`after`, and **requires** `subject_person_id`,
  `accessed_fields` and `access_purpose`. `approval_ref` is required whenever
  `subject_is_minor` is True — that is 第36条's 审批 requirement expressed as
  an invariant instead of a convention.

The consequence that matters: "a read of minor data was not recorded" becomes
a checkable claim, and "it was recorded but without approval" cannot even be
constructed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class AuditActionKind(StrEnum):
    """What kind of action the event records.

    Deliberately closed and deliberately small. A third kind (e.g. EXPORT)
    should only be added alongside the invariants that make it distinguishable
    from these two — an undiscriminated catch-all is the failure mode this
    enum exists to prevent.
    """

    MUTATION = "mutation"
    READ = "read"


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """One immutable record of an action against authoritative data.

    Defaults keep every pre-existing R6 call site valid: `action_kind`
    defaults to MUTATION, and the read-only fields default to None/empty.
    """

    actor_id: str
    tenant_id: str
    action: str
    resource_type: str
    resource_id: str
    reason: str
    correlation_id: str
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    action_kind: AuditActionKind = AuditActionKind.MUTATION
    # --- READ-only fields (条例 第36条) -----------------------------------
    # Whose data was read. Distinct from `resource_id`: reading a family
    # aggregate may expose one specific child, and 第36条 records access to
    # *the minor's* information, not to the container that held it.
    subject_person_id: str | None = None
    # True when the subject is a minor, which is what turns approval from
    # good practice into a legal precondition. Callers must state this
    # explicitly rather than let the recorder guess.
    subject_is_minor: bool = False
    # Which fields/attributes were exposed. Coarse ("*") is permitted but
    # discouraged; an empty tuple on a READ is rejected, because "we logged
    # that someone read something" is not a record of access.
    accessed_fields: tuple[str, ...] = ()
    # Why. A free-text `reason` is for the human narrative; `access_purpose`
    # is the declared processing purpose, which must line up with the
    # consent purpose taxonomy (backend/platform/consent ConsentPurpose).
    access_purpose: str | None = None
    # Reference to the approval record (第36条 审批). Required for minors.
    approval_ref: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        required_fields = {
            "actor_id": self.actor_id,
            "tenant_id": self.tenant_id,
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "reason": self.reason,
            "correlation_id": self.correlation_id,
        }
        missing = [name for name, value in required_fields.items() if not value]
        if missing:
            raise ValueError(f"AuditEvent is missing required field(s): {missing}")

        if self.action_kind is AuditActionKind.READ:
            self._validate_read()
        else:
            self._validate_mutation()

    # -- invariants ------------------------------------------------------

    def _validate_read(self) -> None:
        if self.before is not None or self.after is not None:
            raise ValueError(
                "AuditEvent(action_kind=READ) must not carry before/after state; "
                "a read does not change state. Use action_kind=MUTATION for writes."
            )
        if not self.subject_person_id:
            raise ValueError(
                "AuditEvent(action_kind=READ) requires subject_person_id — "
                "《未成年人网络保护条例》第36条 records access to a person's information, "
                "so the person must be named."
            )
        if not self.accessed_fields:
            raise ValueError(
                "AuditEvent(action_kind=READ) requires accessed_fields — recording "
                "that 'something was read' is not a record of access."
            )
        if not self.access_purpose:
            raise ValueError(
                "AuditEvent(action_kind=READ) requires access_purpose — 最小授权 is "
                "unverifiable without the declared purpose of the access."
            )
        if self.subject_is_minor and not self.approval_ref:
            raise ValueError(
                "AuditEvent(action_kind=READ) on a minor requires approval_ref — "
                "《未成年人网络保护条例》第36条 requires access to be approved by the "
                "responsible person or an authorised manager before it happens."
            )

    def _validate_mutation(self) -> None:
        # No "must carry before/after" rule here, deliberately. Existing R6 call
        # sites legitimately record decisions with neither — see
        # backend/domains/membership/api/routes.py, which audits
        # `<action>:denied` and `<action>:human_gate_passed` with no state delta.
        # Those are authorization outcomes on an attempted mutation, not reads,
        # and forcing a synthetic `after={}` on them would make the record less
        # honest, not more. If a distinct DECISION kind is ever wanted it needs
        # its own invariants and an ADR, not a silent third meaning of MUTATION.
        access_only = {
            "subject_person_id": self.subject_person_id,
            "access_purpose": self.access_purpose,
            "approval_ref": self.approval_ref,
        }
        set_fields = sorted(name for name, value in access_only.items() if value)
        if set_fields:
            raise ValueError(
                f"AuditEvent(action_kind=MUTATION) must not set read-access field(s) "
                f"{set_fields}; they belong to action_kind=READ. A write is not an "
                "access grant."
            )
        if self.accessed_fields:
            raise ValueError(
                "AuditEvent(action_kind=MUTATION) must not set accessed_fields; "
                "use before/after to describe what changed."
            )

    # -- convenience -----------------------------------------------------

    @property
    def is_read(self) -> bool:
        return self.action_kind is AuditActionKind.READ

    @property
    def is_mutation(self) -> bool:
        return self.action_kind is AuditActionKind.MUTATION
