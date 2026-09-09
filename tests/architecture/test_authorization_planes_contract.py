"""Authorization Planes Contract — the requirement-spec oracle for "which
plane is this request coming through, and what must be true before it is
granted".

Python re-implementation (disposition MIGRATE) of
``50_开发_dev/evals/authorization-planes/authorization-planes.contract.spec.ts``
from the legacy repository, registered under:

  - governance/MIGRATION_MANIFEST.yaml -> test_oracle_excluded_contract_specs
  - governance/DOMAIN_REGISTRY.yaml    -> test_oracle_excluded_contract_specs
    (canonical_path: tests/architecture)

Same honesty note as ``test_subject_isolation_contract.py``: in the source
repository this spec sat outside the vitest workspace and asserted against an
inline reimplementation, not production code. It is carried over here as a
requirement oracle, not a coverage claim — nothing in ``backend/`` calls
``evaluate_authorization_plane``. This is deliberately a different decision
shape from ``backend/platform/authorization/policy.py``'s ``PolicyEngine``:
``PolicyEngine`` answers "may this (actor, action, resource_type) proceed"
for a single tenant-scoped caller, while this oracle answers "may this
request, arriving through the family/school/partner/operations plane, reach
a subject in a *different* tenant/family at all" — a purpose-and-grant-scoped
question that sits in front of, not instead of, PolicyEngine. They are not
duplicates of each other and this file does not change PolicyEngine's
behaviour.

Decision rules, unchanged from the TypeScript source:

1. Any request flagged as direct-database-access is denied outright — no
   plane, purpose or grant can excuse bypassing the access layer.
2. Cross-tenant and cross-family requests are denied before purpose is even
   considered.
3. A missing or disallowed purpose is denied (no "purpose-less" access).
4. A revoked or expired consent grant is denied.
5. The `operations` plane additionally requires an *approved* Human Gate —
   `PENDING` is `REVIEW_REQUIRED` (not a silent deny, not a silent allow),
   `DENIED` is `DENY`. Other planes do not carry this extra gate.
6. Anything that clears all of the above is `ALLOW`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

AuthorizationPlane = Literal["family", "school", "partner", "operations"]
Decision = Literal["ALLOW", "DENY", "REVIEW_REQUIRED"]
HumanGateState = Literal["NOT_REQUIRED", "PENDING", "APPROVED", "DENIED"]
GrantStatus = Literal["ACTIVE", "REVOKED"]


@dataclass(frozen=True, slots=True)
class AuthorizationInput:
    plane: AuthorizationPlane
    tenant_id: str
    subject_tenant_id: str
    family_id: str
    subject_family_id: str
    purpose_allowed: bool
    grant_status: GrantStatus
    now: str
    human_gate: HumanGateState
    direct_database_access: bool
    purpose: str | None = None
    expires_at: str | None = None


@dataclass(frozen=True, slots=True)
class AuthorizationResult:
    decision: Decision
    reason: str


def evaluate_authorization_plane(data: AuthorizationInput) -> AuthorizationResult:
    """Pure re-implementation of the TypeScript `evaluateAuthorizationPlane`."""
    if data.direct_database_access:
        return AuthorizationResult("DENY", "direct-database-access-forbidden")

    if data.tenant_id != data.subject_tenant_id:
        return AuthorizationResult("DENY", "cross-tenant-scope")

    if data.family_id != data.subject_family_id:
        return AuthorizationResult("DENY", "cross-family-scope")

    if not data.purpose or not data.purpose_allowed:
        return AuthorizationResult("DENY", "unknown-or-missing-purpose")

    if data.grant_status == "REVOKED":
        return AuthorizationResult("DENY", "grant-revoked")

    if data.expires_at is not None and data.expires_at <= data.now:
        return AuthorizationResult("DENY", "grant-expired")

    if data.plane == "operations" and data.human_gate != "APPROVED":
        if data.human_gate == "DENIED":
            return AuthorizationResult("DENY", "human-gate-denied")
        return AuthorizationResult("REVIEW_REQUIRED", "human-gate-required")

    return AuthorizationResult("ALLOW", "authorization-granted")


def _base_input(**overrides: object) -> AuthorizationInput:
    defaults: dict[str, object] = dict(
        plane="family",
        tenant_id="tenant-a",
        subject_tenant_id="tenant-a",
        family_id="family-a",
        subject_family_id="family-a",
        purpose="family-growth-read",
        purpose_allowed=True,
        grant_status="ACTIVE",
        now="2026-08-26T00:00:00.000Z",
        human_gate="NOT_REQUIRED",
        direct_database_access=False,
    )
    defaults.update(overrides)
    return AuthorizationInput(**defaults)  # type: ignore[arg-type]


def test_allows_family_access_within_the_same_tenant_and_family_scope() -> None:
    result = evaluate_authorization_plane(_base_input())
    assert result == AuthorizationResult("ALLOW", "authorization-granted")


def test_denies_school_access_when_purpose_is_missing() -> None:
    result = evaluate_authorization_plane(_base_input(plane="school", purpose=None))
    assert result == AuthorizationResult("DENY", "unknown-or-missing-purpose")


def test_denies_an_expired_partner_grant() -> None:
    result = evaluate_authorization_plane(
        _base_input(plane="partner", expires_at="2026-08-25T23:59:59.999Z")
    )
    assert result == AuthorizationResult("DENY", "grant-expired")


def test_requires_review_for_operations_access_without_an_approved_human_gate() -> None:
    result = evaluate_authorization_plane(_base_input(plane="operations", human_gate="PENDING"))
    assert result == AuthorizationResult("REVIEW_REQUIRED", "human-gate-required")


def test_denies_operations_access_when_the_human_gate_denies_it() -> None:
    result = evaluate_authorization_plane(_base_input(plane="operations", human_gate="DENIED"))
    assert result == AuthorizationResult("DENY", "human-gate-denied")


def test_denies_cross_tenant_access() -> None:
    result = evaluate_authorization_plane(_base_input(subject_tenant_id="tenant-b"))
    assert result == AuthorizationResult("DENY", "cross-tenant-scope")


def test_denies_a_revoked_grant() -> None:
    result = evaluate_authorization_plane(_base_input(grant_status="REVOKED"))
    assert result == AuthorizationResult("DENY", "grant-revoked")


def test_denies_an_unknown_purpose() -> None:
    result = evaluate_authorization_plane(
        _base_input(purpose="unregistered-purpose", purpose_allowed=False)
    )
    assert result == AuthorizationResult("DENY", "unknown-or-missing-purpose")


def test_denies_agent_or_provider_direct_database_access() -> None:
    result = evaluate_authorization_plane(_base_input(direct_database_access=True))
    assert result == AuthorizationResult("DENY", "direct-database-access-forbidden")
