from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.apps.family_api.trusted_experience_scope import (
    SqlAlchemyConsentSnapshotResolver,
    SqlAlchemyFamilySubjectIdsResolver,
)
from backend.platform.consent.models import ConsentPurpose
from tests.apps.family_api.test_trusted_experience_scope import _trusted_scope


@pytest.fixture
async def consent_session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.execute(
            text(
                """
                CREATE TABLE persons (
                    person_id TEXT PRIMARY KEY,
                    family_id TEXT NOT NULL,
                    birth_date DATE NOT NULL
                )
                """
            )
        )
        await connection.execute(
            text(
                """
                CREATE TABLE consents (
                    consent_id TEXT PRIMARY KEY,
                    family_id TEXT NOT NULL,
                    subject_person_id TEXT NOT NULL,
                    guardian_person_id TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    status TEXT NOT NULL,
                    policy_version TEXT NOT NULL,
                    granted_at DATETIME NOT NULL,
                    withdrawn_at DATETIME NULL
                )
                """
            )
        )
        await connection.execute(
            text(
                "INSERT INTO persons(person_id, family_id, birth_date) "
                "VALUES ('child-1', 'family-1', '2015-01-01')"
            )
        )
        await connection.execute(
            text(
                """
                INSERT INTO consents(
                    consent_id, family_id, subject_person_id, guardian_person_id,
                    purpose, status, policy_version, granted_at, withdrawn_at
                ) VALUES (
                    'consent-1', 'family-1', 'child-1', 'guardian-1',
                    'AI_PERSONALIZATION', 'GRANTED', 'policy.v1',
                    '2026-08-01 00:00:00', NULL
                )
                """
            )
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_sqlalchemy_consent_resolver_reads_current_grant_and_builds_version(
    consent_session_factory,
) -> None:
    snapshot = await SqlAlchemyConsentSnapshotResolver(consent_session_factory)(
        _trusted_scope(),
        ("child-1",),
        ConsentPurpose.AI_PERSONALIZATION,
    )

    grant = snapshot.grants_for("child-1")[0]
    assert grant.consent_id == "consent-1"
    assert grant.status.value == "granted"
    assert grant.subject_age.years == 11
    assert snapshot.consent_version.startswith("db:")
    assert snapshot.deletion_ref == "consent-delete:tenant-1:family-1"


@pytest.mark.asyncio
async def test_sqlalchemy_consent_resolver_returns_empty_subject_grants_fail_closed(
    consent_session_factory,
) -> None:
    snapshot = await SqlAlchemyConsentSnapshotResolver(consent_session_factory)(
        _trusted_scope(),
        ("unknown-child",),
        ConsentPurpose.AI_PERSONALIZATION,
    )

    assert snapshot.grants_for("unknown-child") == ()


@pytest.mark.asyncio
async def test_sqlalchemy_subject_resolver_reads_family_members(consent_session_factory) -> None:
    async with consent_session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO persons(person_id, family_id, birth_date) "
                "VALUES ('child-2', 'family-1', '2012-01-01')"
            )
        )
    subject_ids = await SqlAlchemyFamilySubjectIdsResolver(consent_session_factory)(
        _trusted_scope()
    )
    assert subject_ids == ("child-1", "child-2")
