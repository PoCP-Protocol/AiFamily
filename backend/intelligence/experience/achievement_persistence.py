"""Durable evidence-bound achievement projection.

This adapter owns a read model only.  It stores the immutable achievement
payload emitted by :mod:`achievement`, keeps the complete scope/provenance
envelopes needed for replay and deletion, and never writes a Family/Journey/
Service/Commerce fact.  ``AsyncSession`` transaction ownership remains with
the composition root; this module only calls ``add`` and ``flush``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import JSON, DateTime, Index, String, Text, UniqueConstraint, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from backend.intelligence.experience.achievement import (
    Achievement,
    AchievementKey,
    AchievementProjectionPort,
)
from backend.intelligence.experience.contracts import (
    DeletionRef,
    ExperienceContractError,
    ExperienceProvenance,
    ExperienceScope,
    ProvenanceKind,
)
from backend.intelligence.experience.persistence import ExperiencePersistenceBase
from backend.intelligence.model_gateway.contracts import DataClass
from backend.platform.idempotency.keys import IdempotencyKey


class AchievementProjectionConflict(ExperienceContractError):
    """The same scope/key was replayed with different stable evidence."""


class AchievementProjectionRow(ExperiencePersistenceBase):
    """SQL read model; deliberately contains no score, rank, or total fields."""

    __tablename__ = "ai_achievement_projections"
    __table_args__ = (
        UniqueConstraint(
            "scope_fingerprint",
            "achievement_key",
            "occurrence_id",
            name="uq_ai_achievement_scope_key",
        ),
        Index(
            "ix_ai_achievement_scope_lookup",
            "tenant_id",
            "family_id",
            "scope_fingerprint",
            "earned_at",
        ),
    )

    achievement_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    achievement_key: Mapped[str] = mapped_column(String(64), nullable=False)
    occurrence_id: Mapped[str] = mapped_column(String(256), nullable=False, default="default")
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    region_id: Mapped[str] = mapped_column(String(16), nullable=False)
    family_id: Mapped[str] = mapped_column(String(128), nullable=False)
    subject_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    purpose: Mapped[str] = mapped_column(String(128), nullable=False)
    consent_version: Mapped[str] = mapped_column(String(128), nullable=False)
    scope_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    provenance_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)
    stable_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    earned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SqlAlchemyAchievementProjection(AchievementProjectionPort):
    """Async SQL implementation of the evidence-bound projection port."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(self, achievement: Achievement) -> Achievement:
        """Append once by exact scope/key and return the durable value.

        A replay with the same stable content returns the first row (including
        its original ``earned_at``).  Different evidence under the same
        identity fails closed instead of silently overwriting the projection.
        """

        _validate_achievement(achievement)
        scope_fingerprint = _scope_fingerprint(achievement.scope)
        existing = await self._session.scalar(
            select(AchievementProjectionRow).where(
                AchievementProjectionRow.scope_fingerprint == scope_fingerprint,
                AchievementProjectionRow.achievement_key == achievement.key.value,
                AchievementProjectionRow.occurrence_id == achievement.occurrence_id,
            )
        )
        fingerprint = _stable_fingerprint(achievement)
        if existing is not None:
            if existing.stable_fingerprint != fingerprint:
                raise AchievementProjectionConflict("ACHIEVEMENT_REPLAY_MISMATCH")
            return _stored(existing)

        row = AchievementProjectionRow(
            achievement_id=achievement.achievement_id,
            achievement_key=achievement.key.value,
            occurrence_id=achievement.occurrence_id,
            tenant_id=achievement.scope.tenant_id,
            region_id=achievement.scope.region_id,
            family_id=achievement.scope.family_id,
            subject_ids=list(achievement.scope.subject_ids),
            purpose=achievement.scope.purpose,
            consent_version=achievement.scope.consent_version,
            scope_fingerprint=scope_fingerprint,
            scope_payload=_scope_payload(achievement.scope),
            title=achievement.title,
            message=achievement.message,
            evidence_refs=list(achievement.evidence_refs),
            provenance_payload=_provenance_payload(achievement.provenance),
            idempotency_key=achievement.idempotency_key.scoped_value,
            stable_fingerprint=fingerprint,
            earned_at=_aware(achievement.earned_at),
        )
        self._session.add(row)
        await self._session.flush()
        return _stored(row)

    async def earned(self, scope: ExperienceScope) -> tuple[Achievement, ...]:
        """Read achievements for one exact tenant/family/consent scope."""

        _validate_scope(scope)
        result = await self._session.execute(
            select(AchievementProjectionRow)
            .where(
                AchievementProjectionRow.tenant_id == scope.tenant_id,
                AchievementProjectionRow.family_id == scope.family_id,
                AchievementProjectionRow.scope_fingerprint == _scope_fingerprint(scope),
            )
            .order_by(AchievementProjectionRow.earned_at, AchievementProjectionRow.achievement_id)
        )
        return tuple(_stored(row) for row in result.scalars())

    async def commit(self) -> None:
        """Commit the projection when used as an accepted-action handler."""

        await self._session.commit()

    async def rollback(self) -> None:
        """Rollback the projection transaction after a handler failure."""

        await self._session.rollback()


# Explicit alias for callers that name adapters as stores.
SqlAlchemyAchievementProjectionStore = SqlAlchemyAchievementProjection


def _validate_achievement(achievement: Achievement) -> None:
    if not isinstance(achievement, Achievement):
        raise ExperienceContractError("ACHIEVEMENT_REQUIRED")
    _validate_scope(achievement.scope)


def _validate_scope(scope: ExperienceScope) -> None:
    if not isinstance(scope, ExperienceScope):
        raise ExperienceContractError("EXPERIENCE_SCOPE_REQUIRED")


def _stored(row: AchievementProjectionRow) -> Achievement:
    try:
        return Achievement(
            achievement_id=row.achievement_id,
            key=AchievementKey(row.achievement_key),
            occurrence_id=row.occurrence_id,
            title=row.title,
            message=row.message,
            scope=_scope_from_payload(row.scope_payload),
            evidence_refs=tuple(row.evidence_refs or ()),
            provenance=_provenance_from_payload(row.provenance_payload),
            idempotency_key=IdempotencyKey(
                tenant_id=row.tenant_id,
                value=_idempotency_value(row.idempotency_key, row.tenant_id),
            ),
            earned_at=_aware(row.earned_at),
        )
    except (ExperienceContractError, ValueError, TypeError) as error:
        raise ExperienceContractError("ACHIEVEMENT_PROJECTION_ROW_INVALID") from error


def _idempotency_value(scoped_value: str, tenant_id: str) -> str:
    prefix = f"{len(tenant_id)}:{tenant_id}:"
    if not scoped_value.startswith(prefix):
        raise ExperienceContractError("ACHIEVEMENT_IDEMPOTENCY_INVALID")
    value = scoped_value.removeprefix(prefix)
    if not value:
        raise ExperienceContractError("ACHIEVEMENT_IDEMPOTENCY_INVALID")
    return value


def _scope_payload(scope: ExperienceScope) -> dict[str, Any]:
    return {
        "global_id": scope.global_id,
        "tenant_id": scope.tenant_id,
        "region_id": scope.region_id,
        "family_id": scope.family_id,
        "subject_ids": list(scope.subject_ids),
        "purpose": scope.purpose,
        "consent_version": scope.consent_version,
        "consent_granted": scope.consent_granted,
        "data_class": str(scope.data_class),
        "locale": scope.locale,
        "content_locale": scope.content_locale,
        "model_locale": scope.model_locale,
        "policy_locale": scope.policy_locale,
        "deletion_ref": {
            "deletion_id": scope.deletion_ref.deletion_id,
            "retention_policy": scope.deletion_ref.retention_policy,
            "requested_at": _iso(scope.deletion_ref.requested_at),
        },
        "correlation_id": scope.correlation_id,
        "causation_id": scope.causation_id,
    }


def _scope_from_payload(raw: Mapping[str, Any] | None) -> ExperienceScope:
    if not isinstance(raw, Mapping):
        raise ExperienceContractError("ACHIEVEMENT_SCOPE_PAYLOAD_INVALID")
    deletion = raw.get("deletion_ref")
    if not isinstance(deletion, Mapping):
        raise ExperienceContractError("ACHIEVEMENT_DELETION_PAYLOAD_INVALID")
    requested_at = deletion.get("requested_at")
    return ExperienceScope(
        global_id=_required(raw, "global_id"),
        tenant_id=_required(raw, "tenant_id"),
        region_id=_required(raw, "region_id"),
        family_id=_required(raw, "family_id"),
        subject_ids=_subjects(raw.get("subject_ids")),
        purpose=_required(raw, "purpose"),
        consent_version=_required(raw, "consent_version"),
        consent_granted=_required_bool(raw, "consent_granted"),
        data_class=cast(DataClass, _required(raw, "data_class")),
        locale=_required(raw, "locale"),
        content_locale=_required(raw, "content_locale"),
        model_locale=_required(raw, "model_locale"),
        policy_locale=_required(raw, "policy_locale"),
        deletion_ref=DeletionRef(
            deletion_id=_required(deletion, "deletion_id"),
            retention_policy=_required(deletion, "retention_policy"),
            requested_at=_parse_datetime(requested_at) if requested_at is not None else None,
        ),
        correlation_id=_required(raw, "correlation_id"),
        causation_id=_required(raw, "causation_id"),
    )


def _provenance_payload(provenance: ExperienceProvenance) -> dict[str, Any]:
    return {
        "provenance_ref": provenance.provenance_ref,
        "source_refs": list(provenance.source_refs),
        "kind": provenance.kind.value,
        "policy_version": provenance.policy_version,
        "context_snapshot_ref": provenance.context_snapshot_ref,
        "model_attempt_ref": provenance.model_attempt_ref,
        "captured_at": _iso(provenance.captured_at),
    }


def _provenance_from_payload(raw: Mapping[str, Any] | None) -> ExperienceProvenance:
    if not isinstance(raw, Mapping):
        raise ExperienceContractError("ACHIEVEMENT_PROVENANCE_PAYLOAD_INVALID")
    source_refs = raw.get("source_refs")
    if not isinstance(source_refs, (list, tuple)) or not source_refs:
        raise ExperienceContractError("ACHIEVEMENT_PROVENANCE_SOURCES_INVALID")
    return ExperienceProvenance(
        provenance_ref=_required(raw, "provenance_ref"),
        source_refs=tuple(_required_item(source_refs, "source_refs")),
        kind=ProvenanceKind(_required(raw, "kind")),
        policy_version=_required(raw, "policy_version"),
        context_snapshot_ref=_optional(raw.get("context_snapshot_ref")),
        model_attempt_ref=_optional(raw.get("model_attempt_ref")),
        captured_at=_parse_datetime(raw.get("captured_at")),
    )


def _scope_fingerprint(scope: ExperienceScope) -> str:
    # Match AchievementEngine's identity: global_id/correlation/causation are
    # retained in the payload but do not create a second earned row.
    identity = (
        scope.tenant_id,
        scope.region_id,
        scope.family_id,
        tuple(sorted(scope.subject_ids)),
        scope.purpose,
        scope.consent_version,
    )
    encoded = json.dumps(identity, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _stable_fingerprint(achievement: Achievement) -> str:
    payload = {
        "achievement_id": achievement.achievement_id,
        "key": achievement.key.value,
        "occurrence_id": achievement.occurrence_id,
        "title": achievement.title,
        "message": achievement.message,
        "scope": _scope_payload(achievement.scope),
        "evidence_refs": list(achievement.evidence_refs),
        "provenance": _provenance_payload(achievement.provenance),
        "idempotency_key": achievement.idempotency_key.scoped_value,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _required(mapping: Mapping[str, Any], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise ExperienceContractError(f"ACHIEVEMENT_{key.upper()}_REQUIRED")
    return value


def _required_bool(mapping: Mapping[str, Any], key: str) -> bool:
    value = mapping.get(key)
    if not isinstance(value, bool):
        raise ExperienceContractError(f"ACHIEVEMENT_{key.upper()}_REQUIRED")
    return value


def _subjects(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise ExperienceContractError("ACHIEVEMENT_SUBJECT_IDS_REQUIRED")
    if any(not isinstance(item, str) or not item for item in value):
        raise ExperienceContractError("ACHIEVEMENT_SUBJECT_IDS_INVALID")
    return tuple(value)


def _required_item(values: list[Any] | tuple[Any, ...], name: str) -> tuple[str, ...]:
    if any(not isinstance(item, str) or not item for item in values):
        raise ExperienceContractError(f"ACHIEVEMENT_{name.upper()}_INVALID")
    return tuple(cast(str, item) for item in values)


def _optional(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ExperienceContractError("ACHIEVEMENT_OPTIONAL_REF_INVALID")
    return value


def _parse_datetime(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        raise ExperienceContractError("ACHIEVEMENT_TIMESTAMP_REQUIRED")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ExperienceContractError("ACHIEVEMENT_TIMESTAMP_INVALID") from error
    return _aware(parsed)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


__all__ = [
    "AchievementProjectionConflict",
    "AchievementProjectionPort",
    "AchievementProjectionRow",
    "SqlAlchemyAchievementProjection",
    "SqlAlchemyAchievementProjectionStore",
]
