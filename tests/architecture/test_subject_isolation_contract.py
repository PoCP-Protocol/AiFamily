"""Subject Isolation Contract — the requirement-spec oracle behind R2/R9's
"who is this data about, and may the caller see it" boundary.

This is a Python re-implementation (disposition MIGRATE, not REIMPLEMENT: the
decision logic is carried over unchanged, only the language changes) of
``50_开发_dev/evals/subject-isolation/subject-isolation.contract.spec.ts`` from
the legacy repository, registered under:

  - governance/MIGRATION_MANIFEST.yaml -> test_oracle_excluded_contract_specs
  - governance/DOMAIN_REGISTRY.yaml    -> test_oracle_excluded_contract_specs
    (canonical_path: tests/architecture)

Honesty note carried over from the manifest evidence field: in the source
repository this spec was **never wired into any vitest/workspace config**
(``evals/`` sat outside ``pnpm-workspace.yaml``) and its assertions were an
inline reimplementation of the rule, not a call into production code. It was
a requirement oracle, not a coverage proof, and it stays one here: nothing in
``backend/`` imports ``evaluate_subject_isolation`` below. It exists so that
whichever domain later builds real subject-scoped access control (family
core, consent records, cross-family sharing) has an executable statement of
what "isolated" must mean, instead of a paragraph of prose nobody re-checks.
If a real implementation of subject-scoped access appears, the correct next
step is to point this test file's assertions at that implementation directly
(replacing the local ``evaluate_subject_isolation`` shim) rather than letting
both drift independently — see R14.

Five isolation rules, unchanged from the TypeScript source:

1. A subject must be named explicitly — no implicit "current family" default.
2. A "global child super-profile" (one profile spanning every child a
   recipient can see) is forbidden outright, regardless of scoping.
3. The subject's tenant must match the request's tenant.
4. The subject's family must match the request's family.
5. If a recipient scope is given, it must exactly match the subject's
   (tenant, family, subject_id) triple — a caller cannot ask about child A
   while an explicit recipient scope silently resolves to child B.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SubjectKind = Literal["child", "parent", "teacher", "school", "provider", "operations"]


@dataclass(frozen=True, slots=True)
class SubjectRef:
    tenant_id: str
    family_id: str
    subject_id: str
    kind: SubjectKind


@dataclass(frozen=True, slots=True)
class RecipientScope:
    tenant_id: str
    family_id: str
    subject_id: str


@dataclass(frozen=True, slots=True)
class SubjectContext:
    tenant_id: str
    family_id: str
    subject: SubjectRef | None = None
    recipient_scope: RecipientScope | None = None
    global_child_super_profile: bool = False


@dataclass(frozen=True, slots=True)
class IsolationResult:
    allowed: bool
    reason: str | None = None

    @classmethod
    def allow(cls) -> IsolationResult:
        return cls(allowed=True, reason=None)

    @classmethod
    def deny(cls, reason: str) -> IsolationResult:
        return cls(allowed=False, reason=reason)


def evaluate_subject_isolation(context: SubjectContext) -> IsolationResult:
    """Pure re-implementation of the TypeScript `evaluateSubjectIsolation`."""
    subject = context.subject
    if subject is None:
        return IsolationResult.deny("subject-required")
    if context.global_child_super_profile:
        return IsolationResult.deny("global-child-super-profile-forbidden")
    if subject.tenant_id != context.tenant_id:
        return IsolationResult.deny("cross-tenant-subject")
    if subject.family_id != context.family_id:
        return IsolationResult.deny("cross-family-subject")

    scope = context.recipient_scope
    if scope is not None and (
        scope.tenant_id != subject.tenant_id
        or scope.family_id != subject.family_id
        or scope.subject_id != subject.subject_id
    ):
        return IsolationResult.deny("recipient-scope-mismatch")

    return IsolationResult.allow()


def _child(subject_id: str, family_id: str = "family-a", tenant_id: str = "tenant-a") -> SubjectRef:
    return SubjectRef(tenant_id=tenant_id, family_id=family_id, subject_id=subject_id, kind="child")


def test_allows_a_subject_in_the_same_family_and_tenant() -> None:
    result = evaluate_subject_isolation(
        SubjectContext(tenant_id="tenant-a", family_id="family-a", subject=_child("child-1"))
    )
    assert result == IsolationResult.allow()


def test_rejects_a_request_with_no_subject() -> None:
    result = evaluate_subject_isolation(SubjectContext(tenant_id="tenant-a", family_id="family-a"))
    assert result == IsolationResult.deny("subject-required")


def test_rejects_a_subject_from_another_family() -> None:
    result = evaluate_subject_isolation(
        SubjectContext(
            tenant_id="tenant-a",
            family_id="family-a",
            subject=_child("child-1", family_id="family-b"),
        )
    )
    assert result == IsolationResult.deny("cross-family-subject")


def test_rejects_a_subject_from_another_tenant() -> None:
    result = evaluate_subject_isolation(
        SubjectContext(
            tenant_id="tenant-a",
            family_id="family-a",
            subject=_child("child-1", family_id="family-a", tenant_id="tenant-b"),
        )
    )
    assert result == IsolationResult.deny("cross-tenant-subject")


def test_rejects_a_recipient_scope_that_does_not_match_the_explicit_subject() -> None:
    mismatched_scope = RecipientScope(
        tenant_id="tenant-a", family_id="family-a", subject_id="child-2"
    )
    result = evaluate_subject_isolation(
        SubjectContext(
            tenant_id="tenant-a",
            family_id="family-a",
            subject=_child("child-1"),
            recipient_scope=mismatched_scope,
        )
    )
    assert result == IsolationResult.deny("recipient-scope-mismatch")


def test_rejects_a_global_child_super_profile() -> None:
    result = evaluate_subject_isolation(
        SubjectContext(
            tenant_id="tenant-a",
            family_id="family-a",
            subject=_child("child-1"),
            global_child_super_profile=True,
        )
    )
    assert result == IsolationResult.deny("global-child-super-profile-forbidden")


def test_allows_multiple_children_only_when_each_request_names_its_subject() -> None:
    requests = [
        SubjectContext(
            tenant_id="tenant-a",
            family_id="family-a",
            subject=_child(subject_id),
            recipient_scope=RecipientScope(
                tenant_id="tenant-a", family_id="family-a", subject_id=subject_id
            ),
        )
        for subject_id in ("child-1", "child-2")
    ]

    results = [evaluate_subject_isolation(request) for request in requests]
    assert results == [IsolationResult.allow(), IsolationResult.allow()]

    unscoped = evaluate_subject_isolation(
        SubjectContext(tenant_id="tenant-a", family_id="family-a")
    )
    assert unscoped == IsolationResult.deny("subject-required")
