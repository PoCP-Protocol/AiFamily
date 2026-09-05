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
from datetime import UTC, date, datetime
from hashlib import sha256
from types import MappingProxyType

from sqlalchemy import Date, DateTime, bindparam, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from backend.intelligence.context_engine.contracts import ContextScope, DataClass
from backend.intelligence.experience.contracts import DeletionRef, ExperienceScope
from backend.intelligence.experience.engagement_review import EngagementReviewer
from backend.intelligence.human_gate import ActorType as HumanGateActorType
from backend.platform.consent.gate import ConsentGate
from backend.platform.consent.models import (
    ConsentGrant,
    ConsentPurpose,
    ConsentStatus,
    GuardianRelation,
    SubjectAge,
)
from backend.platform.consent.versioning import (
    ConsentVersionEntry,
    canonical_consent_version,
)
from backend.platform.identity.session_port import IdentitySessionPort
from backend.platform.identity.trusted_context import (
    SqlAlchemyTrustedTenantScopeStoreFactory,
    TrustedTenantScope,
    TrustedTenantScopeResolver,
)

PrincipalResolver = Callable[[], "AuthenticatedPrincipal | Awaitable[AuthenticatedPrincipal]"]
PrincipalResolverFactory = Callable[[str], PrincipalResolver]
RequestPrincipalResolverFactory = Callable[
    [str, str | None, str | None, str | None], PrincipalResolver
]
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
class SqlAlchemyBearerPrincipalResolver:
    """Resolve a bearer session through the canonical identity session table."""

    engine: AsyncEngine
    authorization: str | None
    family_id: str
    correlation_id: str | None = None
    causation_id: str | None = None

    async def __call__(self) -> AuthenticatedPrincipal:
        token = _bearer_token(self.authorization)
        if not self.family_id.strip():
            raise ExperienceScopeError("FAMILY_ID_REQUIRED")
        token_hash = sha256(token.encode("utf-8")).hexdigest()
        statement = text(
            """
            SELECT s.session_id, COALESCE(a.account_id, s.account_id) AS account_id
            FROM identity_sessions AS s
            LEFT JOIN accounts AS a ON a.account_id = s.account_ref
            WHERE s.token_hash = :token_hash
              AND s.family_id = :family_id
              AND s.revoked_at IS NULL
              AND s.expires_at > CURRENT_TIMESTAMP
              AND (a.status = 'ACTIVE' OR a.status IS NULL)
            LIMIT 2
            """
        )
        async with self.engine.connect() as connection:
            result = await connection.execute(
                statement,
                {"token_hash": token_hash, "family_id": self.family_id},
            )
            rows = result.mappings().all()
        if len(rows) != 1:
            raise ExperienceScopeError("AUTHENTICATED_PRINCIPAL_UNAVAILABLE")
        row = rows[0]
        account_id = str(row.get("account_id") or "")
        session_id = str(row.get("session_id") or "")
        if not account_id or not session_id:
            raise ExperienceScopeError("AUTHENTICATED_PRINCIPAL_UNAVAILABLE")
        return AuthenticatedPrincipal(
            account_id=account_id,
            correlation_id=self.correlation_id or f"identity-session:{session_id}",
            causation_id=self.causation_id or f"identity-session:{session_id}",
        )


@dataclass(frozen=True, slots=True)
class HttpIdentityPrincipalResolver:
    """Resolve a bearer through the deployment-owned auth_identity service."""

    session_port: IdentitySessionPort
    authorization: str | None
    family_id: str
    correlation_id: str | None = None
    causation_id: str | None = None

    async def __call__(self) -> AuthenticatedPrincipal:
        token = _bearer_token(self.authorization)
        if not isinstance(self.family_id, str) or not self.family_id.strip():
            raise ExperienceScopeError("FAMILY_ID_REQUIRED")
        if not callable(getattr(self.session_port, "introspect", None)):
            raise ExperienceScopeError("IDENTITY_SESSION_INTROSPECTION_UNAVAILABLE")
        try:
            session = await self.session_port.introspect(access_token=token)
        except Exception as exc:  # noqa: BLE001 - identity boundary is fail-closed
            raise ExperienceScopeError("AUTHENTICATED_PRINCIPAL_UNAVAILABLE") from exc
        if session.family_id != self.family_id or session.expires_at <= datetime.now(UTC):
            raise ExperienceScopeError("AUTHENTICATED_PRINCIPAL_UNAVAILABLE")
        return AuthenticatedPrincipal(
            account_id=session.account_id,
            correlation_id=self.correlation_id or f"identity-session:{session.session_id}",
            causation_id=self.causation_id or f"identity-session:{session.session_id}",
        )


def build_http_identity_principal_resolver_factory(
    session_port: IdentitySessionPort,
) -> RequestPrincipalResolverFactory:
    """Bind one auth_identity session port to request-scoped principal resolvers."""

    if not callable(getattr(session_port, "introspect", None)):
        raise TypeError("session_port must implement introspect()")

    def factory(
        family_id: str,
        authorization: str | None,
        correlation_id: str | None,
        causation_id: str | None,
    ) -> PrincipalResolver:
        return HttpIdentityPrincipalResolver(
            session_port=session_port,
            authorization=authorization,
            family_id=family_id,
            correlation_id=correlation_id,
            causation_id=causation_id,
        )

    return factory


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


@dataclass(frozen=True, slots=True)
class AuthenticatedEngagementScopeResolver:
    """Project the authenticated context scope into the engagement contract."""

    context_resolver: AuthenticatedExperienceScopeResolver
    retention_policy: str = "consent-bound"

    def __post_init__(self) -> None:
        if not isinstance(self.context_resolver, AuthenticatedExperienceScopeResolver):
            raise TypeError("context_resolver must be an AuthenticatedExperienceScopeResolver")
        if not isinstance(self.retention_policy, str) or not self.retention_policy.strip():
            raise ValueError("retention_policy must be a non-empty string")

    async def resolve(self, family_id: str) -> ExperienceScope:
        context = await self.context_resolver.resolve(family_id)
        return ExperienceScope(
            global_id=(
                f"engagement-scope:{context.tenant_id}:{context.family_id}:"
                f"{context.consent_version}"
            ),
            tenant_id=context.tenant_id,
            region_id=context.region_id,
            family_id=context.family_id,
            subject_ids=context.subject_ids,
            purpose=context.purpose,
            consent_version=context.consent_version,
            consent_granted=context.consent_granted,
            data_class=context.data_class.value,
            locale=context.locale,
            content_locale=context.content_locale or context.locale,
            model_locale=context.model_locale or context.locale,
            policy_locale=context.policy_locale or context.locale,
            deletion_ref=DeletionRef(
                deletion_id=context.deletion_ref,
                retention_policy=self.retention_policy,
            ),
            correlation_id=context.correlation_id,
            causation_id=context.causation_id,
        )

    async def __call__(self, family_id: str) -> ExperienceScope:
        """Allow direct injection into callable production composition ports."""

        return await self.resolve(family_id)


@dataclass(frozen=True, slots=True)
class SqlAlchemyAuthenticatedEngagementScopeResolver:
    """Compose bearer identity, trusted tenant binding and SQL consent reads."""

    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    authorization: str | None
    correlation_id: str | None = None
    causation_id: str | None = None
    purpose: ConsentPurpose = ConsentPurpose.AI_PERSONALIZATION
    data_class: DataClass = DataClass.MINOR_PERSONAL_DATA
    locale: str = "zh-CN"
    principal_resolver_factory: PrincipalResolverFactory | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.session_factory, async_sessionmaker):
            raise TypeError("session_factory must be an async_sessionmaker")
        if not isinstance(self.purpose, ConsentPurpose):
            raise TypeError("purpose must be a ConsentPurpose")
        if not isinstance(self.data_class, DataClass):
            raise TypeError("data_class must be a DataClass")
        if not isinstance(self.locale, str) or not self.locale.strip():
            raise ValueError("locale must be a non-empty string")
        if self.principal_resolver_factory is not None and not callable(
            self.principal_resolver_factory
        ):
            raise TypeError("principal_resolver_factory must be callable")

    async def resolve(self, family_id: str) -> ExperienceScope:
        principal_resolver = (
            self.principal_resolver_factory(family_id)
            if self.principal_resolver_factory is not None
            else SqlAlchemyBearerPrincipalResolver(
                self.engine,
                self.authorization,
                family_id,
                correlation_id=self.correlation_id,
                causation_id=self.causation_id,
            )
        )
        context_resolver = AuthenticatedExperienceScopeResolver(
            principal_resolver=principal_resolver,
            trusted_scope_resolver=TrustedTenantScopeResolver(
                SqlAlchemyTrustedTenantScopeStoreFactory(self.session_factory)
            ),
            subject_ids_resolver=SqlAlchemyFamilySubjectIdsResolver(self.session_factory),
            consent_resolver=SqlAlchemyConsentSnapshotResolver(self.session_factory),
            purpose=self.purpose,
            data_class=self.data_class,
            locale=self.locale,
        )
        return await AuthenticatedEngagementScopeResolver(context_resolver).resolve(family_id)

    async def __call__(self, family_id: str) -> ExperienceScope:
        return await self.resolve(family_id)


@dataclass(frozen=True, slots=True)
class SqlAlchemyAuthenticatedEngagementReviewerResolver:
    """Resolve the bearer-bound active family guardian for Human Gate decisions."""

    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    authorization: str | None
    family_id: str
    principal_resolver_factory: PrincipalResolverFactory | None = None

    async def __call__(self, scope: ExperienceScope) -> EngagementReviewer:
        if scope.family_id != self.family_id:
            raise ExperienceScopeError("FAMILY_REVIEW_SCOPE_UNAVAILABLE")
        principal_resolver = (
            self.principal_resolver_factory(self.family_id)
            if self.principal_resolver_factory is not None
            else SqlAlchemyBearerPrincipalResolver(
                self.engine,
                self.authorization,
                self.family_id,
                correlation_id=scope.correlation_id,
                causation_id=scope.causation_id,
            )
        )
        principal = await _maybe_await(principal_resolver())
        if not isinstance(principal, AuthenticatedPrincipal):
            raise ExperienceScopeError("AUTHENTICATED_PRINCIPAL_UNAVAILABLE")
        statement = text(
            """
            SELECT fm.person_id, tm.tenant_id
            FROM accounts AS a
            JOIN tenant_account_memberships AS tm
              ON tm.account_id = a.account_id
             AND tm.status = 'ACTIVE'
             AND tm.valid_from <= CURRENT_TIMESTAMP
             AND (tm.valid_to IS NULL OR tm.valid_to > CURRENT_TIMESTAMP)
            JOIN tenant_family_bindings AS tfb
              ON tfb.tenant_id = tm.tenant_id
             AND tfb.family_id = :family_id
             AND tfb.status = 'ACTIVE'
             AND tfb.effective_from <= CURRENT_TIMESTAMP
             AND (tfb.effective_to IS NULL OR tfb.effective_to > CURRENT_TIMESTAMP)
            JOIN account_person_bindings AS apb
              ON apb.account_id = a.account_id
             AND apb.status = 'ACTIVE'
            JOIN family_memberships AS fm
              ON fm.family_id = tfb.family_id
             AND fm.person_id = apb.person_id
             AND fm.status = 'ACTIVE'
             AND fm.role IN ('OWNER_GUARDIAN', 'GUARDIAN')
            WHERE a.account_id = :account_id
              AND a.status = 'ACTIVE'
              AND tm.tenant_id = :tenant_id
            ORDER BY fm.membership_id
            LIMIT 2
            """
        )
        async with self.session_factory() as session:
            rows = (
                await session.execute(
                    statement,
                    {
                        "account_id": principal.account_id,
                        "family_id": self.family_id,
                        "tenant_id": scope.tenant_id,
                    },
                )
            ).mappings().all()
        if len(rows) != 1:
            raise ExperienceScopeError("GUARDIAN_REVIEWER_UNAVAILABLE")
        actor_id = str(rows[0].get("person_id") or "")
        if not actor_id:
            raise ExperienceScopeError("GUARDIAN_REVIEWER_UNAVAILABLE")
        return EngagementReviewer(
            actor_id=actor_id,
            actor_type=HumanGateActorType.GUARDIAN,
        )


@dataclass(frozen=True, slots=True)
class SqlAlchemyAuthenticatedContextScopeResolver:
    """Resolve the shared ContextScope for the production multimodal runtime."""

    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    authorization: str | None
    correlation_id: str | None = None
    causation_id: str | None = None
    purpose: ConsentPurpose = ConsentPurpose.AI_PERSONALIZATION
    data_class: DataClass = DataClass.MINOR_PERSONAL_DATA
    locale: str = "zh-CN"
    principal_resolver_factory: PrincipalResolverFactory | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.session_factory, async_sessionmaker):
            raise TypeError("session_factory must be an async_sessionmaker")
        if not isinstance(self.purpose, ConsentPurpose):
            raise TypeError("purpose must be a ConsentPurpose")
        if not isinstance(self.data_class, DataClass):
            raise TypeError("data_class must be a DataClass")
        if not isinstance(self.locale, str) or not self.locale.strip():
            raise ValueError("locale must be a non-empty string")
        if self.principal_resolver_factory is not None and not callable(
            self.principal_resolver_factory
        ):
            raise TypeError("principal_resolver_factory must be callable")

    async def resolve(self, family_id: str) -> ContextScope:
        principal_resolver = (
            self.principal_resolver_factory(family_id)
            if self.principal_resolver_factory is not None
            else SqlAlchemyBearerPrincipalResolver(
                self.engine,
                self.authorization,
                family_id,
                correlation_id=self.correlation_id,
                causation_id=self.causation_id,
            )
        )
        resolver = AuthenticatedExperienceScopeResolver(
            principal_resolver=principal_resolver,
            trusted_scope_resolver=TrustedTenantScopeResolver(
                SqlAlchemyTrustedTenantScopeStoreFactory(self.session_factory)
            ),
            subject_ids_resolver=SqlAlchemyFamilySubjectIdsResolver(self.session_factory),
            consent_resolver=SqlAlchemyConsentSnapshotResolver(self.session_factory),
            purpose=self.purpose,
            data_class=self.data_class,
            locale=self.locale,
        )
        return await resolver.resolve(family_id)

    async def __call__(self, family_id: str) -> ContextScope:
        return await self.resolve(family_id)


@dataclass(frozen=True, slots=True)
class SqlAlchemyConsentSnapshotResolver:
    """Read current consent rows from the canonical PostgreSQL identity schema."""

    session_factory: async_sessionmaker[AsyncSession]
    retention_policy: str = "consent-bound"

    def __post_init__(self) -> None:
        if not isinstance(self.session_factory, async_sessionmaker):
            raise TypeError("session_factory must be an async_sessionmaker")
        if not isinstance(self.retention_policy, str) or not self.retention_policy.strip():
            raise ValueError("retention_policy must be a non-empty string")

    async def __call__(
        self,
        trusted: TrustedTenantScope,
        subject_ids: tuple[str, ...],
        purpose: ConsentPurpose,
    ) -> ConsentSnapshot:
        if not subject_ids:
            raise ExperienceScopeError("SUBJECT_SCOPE_UNAVAILABLE")
        statement = text(
            """
            SELECT c.consent_id, c.subject_person_id, c.guardian_person_id,
                   c.purpose, c.status, c.policy_version, c.granted_at,
                   c.withdrawn_at, p.birth_date
            FROM consents AS c
            JOIN persons AS p ON p.person_id = c.subject_person_id
            WHERE c.family_id = :family_id
              AND c.subject_person_id IN :subject_ids
              AND c.purpose = :purpose
            ORDER BY c.subject_person_id, c.granted_at DESC, c.consent_id DESC
            """
        ).columns(
            granted_at=DateTime(timezone=True),
            withdrawn_at=DateTime(timezone=True),
            birth_date=Date(),
        ).bindparams(bindparam("subject_ids", expanding=True))
        async with self.session_factory() as session:
            result = await session.execute(
                statement,
                {
                    "family_id": trusted.family_id,
                    "subject_ids": list(subject_ids),
                    "purpose": purpose.value.upper(),
                },
            )
            rows = tuple(result.mappings().all())

        grants_by_subject: dict[str, tuple[ConsentGrant, ...]] = {
            subject_id: () for subject_id in subject_ids
        }
        version_entries: list[ConsentVersionEntry] = []
        grouped: dict[str, list[ConsentGrant]] = {subject_id: [] for subject_id in subject_ids}
        for row in rows:
            subject_id = str(row["subject_person_id"])
            if subject_id not in grouped:
                continue
            grant = _consent_grant_from_row(row, purpose=purpose)
            grouped[subject_id].append(grant)
            version_entries.append(
                ConsentVersionEntry(
                    consent_id=grant.consent_id,
                    status=grant.status.value,
                    granted_at=grant.granted_at,
                    guardian_person_id=grant.guardian_person_id,
                    subject_age=grant.subject_age.years,
                    policy_version=str(row["policy_version"]),
                )
            )
        grants_by_subject = {
            subject_id: tuple(grants) for subject_id, grants in grouped.items()
        }
        consent_version = canonical_consent_version(version_entries)
        return ConsentSnapshot(
            consent_version=consent_version,
            grants_by_subject=grants_by_subject,
            deletion_ref=f"consent-delete:{trusted.tenant_id}:{trusted.family_id}",
        )


@dataclass(frozen=True, slots=True)
class SqlAlchemyFamilySubjectIdsResolver:
    """Read the complete person set for a trusted family scope."""

    session_factory: async_sessionmaker[AsyncSession]

    def __post_init__(self) -> None:
        if not isinstance(self.session_factory, async_sessionmaker):
            raise TypeError("session_factory must be an async_sessionmaker")

    async def __call__(self, trusted: TrustedTenantScope) -> tuple[str, ...]:
        statement = text(
            "SELECT person_id FROM persons WHERE family_id = :family_id ORDER BY person_id"
        )
        async with self.session_factory() as session:
            result = await session.execute(statement, {"family_id": trusted.family_id})
            subject_ids = tuple(str(row[0]) for row in result.fetchall())
        if not subject_ids:
            raise ExperienceScopeError("SUBJECT_SCOPE_UNAVAILABLE")
        return subject_ids


def _consent_grant_from_row(row: Mapping[str, object], *, purpose: ConsentPurpose) -> ConsentGrant:
    try:
        status = ConsentStatus(str(row["status"]).lower())
        granted_at = row["granted_at"]
        if not isinstance(granted_at, datetime):
            raise ValueError("granted_at is not a datetime")
        birth_date = row["birth_date"]
        if not isinstance(birth_date, date):
            raise ValueError("birth_date is required")
        guardian_id = str(row["guardian_person_id"])
        subject_id = str(row["subject_person_id"])
        age = _age_at(birth_date, granted_at.date())
        return ConsentGrant(
            consent_id=str(row["consent_id"]),
            subject_person_id=subject_id,
            guardian_person_id=guardian_id,
            purpose=purpose,
            status=status,
            granted_at=granted_at,
            subject_age=SubjectAge(age),
            guardian_relation=(
                GuardianRelation.SELF if guardian_id == subject_id else GuardianRelation.GUARDIAN
            ),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ExperienceScopeError("CONSENT_SNAPSHOT_INVALID") from error


def _age_at(birth_date: date, moment: date) -> int:
    years = moment.year - birth_date.year
    if (moment.month, moment.day) < (birth_date.month, birth_date.day):
        years -= 1
    if years < 0:
        raise ValueError("birth_date cannot be in the future")
    return years


def _bearer_token(authorization: str | None) -> str:
    if authorization is None or not authorization.startswith("Bearer "):
        raise ExperienceScopeError("AUTHENTICATED_PRINCIPAL_UNAVAILABLE")
    token = authorization[7:].strip()
    if not token:
        raise ExperienceScopeError("AUTHENTICATED_PRINCIPAL_UNAVAILABLE")
    return token


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
    "AuthenticatedEngagementScopeResolver",
    "AuthenticatedExperienceScopeResolver",
    "AuthenticatedPrincipal",
    "HttpIdentityPrincipalResolver",
    "build_http_identity_principal_resolver_factory",
    "PrincipalResolverFactory",
    "RequestPrincipalResolverFactory",
    "ConsentSnapshot",
    "ExperienceScopeError",
    "SqlAlchemyConsentSnapshotResolver",
    "SqlAlchemyFamilySubjectIdsResolver",
    "SqlAlchemyBearerPrincipalResolver",
    "SqlAlchemyAuthenticatedEngagementReviewerResolver",
    "SqlAlchemyAuthenticatedEngagementScopeResolver",
    "SqlAlchemyAuthenticatedContextScopeResolver",
]
