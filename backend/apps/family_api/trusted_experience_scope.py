"""Request-scoped identity and consent adapter for Web AI experiences.

The experience router intentionally receives only a family path and generation
intent.  This module supplies the trusted scope that the router must not accept
from JSON: an authenticated principal is resolved first, the account-to-tenant
and account-to-family chain is checked, then current consent is evaluated for
every subject before a ``ContextScope`` reaches Model Gateway.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from backend.intelligence.context_engine.contracts import ContextScope, DataClass
from backend.platform.consent.gate import ConsentGate
from backend.platform.consent.models import ConsentGrant, ConsentPurpose
from backend.platform.identity.trusted_context import (
    TrustedTenantScope,
    TrustedTenantScopeResolver,
)

PrincipalResolver = Callable[[], "AuthenticatedPrincipal | Awaitable[AuthenticatedPrincipal]"]
SubjectIdsResolver = Callable[
    [TrustedTenantScope], tuple[str, ...] | Awaitable[tuple[str, ...]]
]
ConsentResolver = Callable[
    [TrustedTenantScope, tuple[str, ...], ConsentPurpose],
    "ConsentSnapshot | Awaitable[ConsentSnapshot]",
]


class ExperienceScopeError(PermissionError):
    """A principal cannot receive a usable AI experience scope."""


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    """Request-authenticated identity, never parsed from model input JSON."""

    account_id: str
    correlation_id: str
    causation_id: str

    def __post_init__(self) -> None:
        for name, value in (
            ("account_id", self.account_id),
            ("correlation_id", self.correlation_id),
            ("causation_id", self.causation_id),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")


@dataclass(frozen=True, slots=True)
class ConsentSnapshot:
    """Fresh consent rows returned by the deployment-owned consent store."""

    consent_version: str
    grants_by_subject: Mapping[str, tuple[ConsentGrant, ...]]
    deletion_ref: str

    def __post_init__(self) -> None:
        if not isinstance(self.consent_version, str) or not self.consent_version.strip():
            raise ValueError("consent_version must be a non-empty string")
        if not isinstance(self.deletion_ref, str) or not self.deletion_ref.strip():
            raise ValueError("deletion_ref must be a non-empty string")
        for subject_id, grants in self.grants_by_subject.items():
            if not isinstance(subject_id, str) or not subject_id.strip():
                raise ValueError("consent subject ids must be non-empty strings")
            if not isinstance(grants, tuple):
                raise ValueError("consent grants must be immutable tuples")
            if any(not isinstance(grant, ConsentGrant) for grant in grants):
                raise ValueError("consent grants must contain ConsentGrant values")
        object.__setattr__(
            self,
            "grants_by_subject",
            MappingProxyType(dict(self.grants_by_subject)),
        )

    def grants_for(self, subject_id: str) -> tuple[ConsentGrant, ...]:
        return self.grants_by_subject.get(subject_id, ())


@dataclass(frozen=True, slots=True)
class AuthenticatedExperienceScopeResolver:
    """Compose authenticated identity, trusted family binding and consent."""

    principal_resolver: PrincipalResolver
    trusted_scope_resolver: TrustedTenantScopeResolver
    subject_ids_resolver: SubjectIdsResolver
    consent_resolver: ConsentResolver
    purpose: ConsentPurpose = ConsentPurpose.AI_PERSONALIZATION
    data_class: DataClass = DataClass.FAMILY_PRIVATE_TEXT
    locale: str = "zh-CN"

    def __post_init__(self) -> None:
        for name, value in (
            ("principal_resolver", self.principal_resolver),
            ("subject_ids_resolver", self.subject_ids_resolver),
            ("consent_resolver", self.consent_resolver),
        ):
            if not callable(value):
                raise TypeError(f"{name} must be callable")
        if not isinstance(self.trusted_scope_resolver, TrustedTenantScopeResolver):
            raise TypeError("trusted_scope_resolver must be a TrustedTenantScopeResolver")
        if not isinstance(self.purpose, ConsentPurpose):
            raise TypeError("purpose must be a ConsentPurpose")
        if not isinstance(self.data_class, DataClass):
            raise TypeError("data_class must be a DataClass")

    async def resolve(self, family_id: str) -> ContextScope:
        if not isinstance(family_id, str) or not family_id.strip():
            raise ExperienceScopeError("FAMILY_ID_REQUIRED")
        principal = await _maybe_await(self.principal_resolver())
        if not isinstance(principal, AuthenticatedPrincipal):
            raise ExperienceScopeError("AUTHENTICATED_PRINCIPAL_UNAVAILABLE")
        try:
            trusted = await self.trusted_scope_resolver.resolve(
                account_id=principal.account_id,
                family_id=family_id,
            )
        except PermissionError as error:
            raise ExperienceScopeError("TENANT_SCOPE_UNAVAILABLE") from error
        if trusted.family_id != family_id:
            raise ExperienceScopeError("TENANT_SCOPE_UNAVAILABLE")

        subject_ids = await _maybe_await(self.subject_ids_resolver(trusted))
        _validate_subject_ids(subject_ids)
        consent = await _maybe_await(
            self.consent_resolver(trusted, subject_ids, self.purpose)
        )
        if not isinstance(consent, ConsentSnapshot):
            raise ExperienceScopeError("CONSENT_SNAPSHOT_UNAVAILABLE")
        for subject_id in subject_ids:
            if not ConsentGate.check(
                subject_id,
                self.purpose,
                consent.grants_for(subject_id),
            ):
                raise ExperienceScopeError("CONSENT_REQUIRED")

        return ContextScope(
            tenant_id=trusted.tenant_id,
            region_id=trusted.region_id,
            family_id=trusted.family_id,
            subject_ids=subject_ids,
            purpose=self.purpose.value,
            consent_version=consent.consent_version,
            consent_granted=True,
            data_class=self.data_class,
            locale=self.locale,
            deletion_ref=consent.deletion_ref,
            correlation_id=principal.correlation_id,
            causation_id=principal.causation_id,
        )


async def _maybe_await(value: object) -> object:
    return await value if inspect.isawaitable(value) else value


def _validate_subject_ids(subject_ids: object) -> None:
    if not isinstance(subject_ids, tuple) or not subject_ids:
        raise ExperienceScopeError("SUBJECT_SCOPE_UNAVAILABLE")
    if any(not isinstance(subject_id, str) or not subject_id.strip() for subject_id in subject_ids):
        raise ExperienceScopeError("SUBJECT_SCOPE_UNAVAILABLE")
    if len(set(subject_ids)) != len(subject_ids):
        raise ExperienceScopeError("SUBJECT_SCOPE_UNAVAILABLE")


__all__ = [
    "AuthenticatedExperienceScopeResolver",
    "AuthenticatedPrincipal",
    "ConsentSnapshot",
    "ExperienceScopeError",
]
