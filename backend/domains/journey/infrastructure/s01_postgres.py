"""PostgreSQL seam for the ``VS-GROWTH-01`` entry boundary.

This adapter deliberately owns no Journey aggregate writes.  It reads a
submitted assessment session and its current response evidence, reconstructs
the purpose-scoped consent grants needed by the application contract, and
provides one transactional audit/outbox/idempotency append for the accepted
signal.  The caller must supply an ``AsyncConnection`` that is already inside
an ``AsyncEngine.begin()`` transaction; committing and retrying the request is
therefore the composition root's responsibility.

The adapter is production-shaped but not production-complete.  Hypothesis,
intent, action and review projections still live behind the in-memory
``S01VerticalSlice`` until their durable tables and worker are wired.  No AI
output is written as a fact here, and no score/rank is calculated.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from backend.platform.consent import (
    ConsentGrant,
    ConsentPurpose,
    ConsentStatus,
    GuardianRelation,
    SubjectAge,
)

from ..application.s01_vertical_slice import AssessmentSignal
from ..domain.errors import JourneyConflictError, JourneyValidationError


class S01PostgresAssessmentRepository:
    """Read submitted assessment evidence and append the entry event.

    Every query includes ``tenant_id`` and ``family_id``.  A session that is
    still editable, exited, missing current evidence, or outside that scope
    is intentionally indistinguishable from not found (``None``), so a caller
    cannot probe another tenant's assessment state.
    """

    production_ready = False
    capability_id = "VS-GROWTH-01"

    def __init__(self, connection: AsyncConnection):
        self._connection = connection

    async def load_submitted_signal(
        self,
        *,
        tenant_id: str,
        family_id: str,
        assessment_session_id: str,
        locale: str = "zh-CN",
    ) -> AssessmentSignal | None:
        _assert_uuid(tenant_id, "tenant_id")
        _assert_uuid(family_id, "family_id")
        _assert_uuid(assessment_session_id, "assessment_session_id")
        _assert_locale(locale)
        result = await self._connection.execute(
            text(
                """
                select
                  s.assessment_session_id::text as assessment_session_id,
                  s.tenant_id::text as tenant_id,
                  s.family_id::text as family_id,
                  s.subject_person_id::text as subject_person_id,
                  coalesce(s.submitted_at, s.updated_at) as captured_at,
                  jsonb_agg(
                    jsonb_build_object(
                      'response_id', r.assessment_response_id::text,
                      'item_ref', r.item_ref,
                      'response_value', r.response_value,
                      'author_person_id', r.author_person_id::text
                    ) order by r.assessment_response_id
                  ) filter (where r.assessment_response_id is not null) as responses
                from family_assessment_sessions s
                join family_assessment_responses r
                  on r.assessment_session_id=s.assessment_session_id
                 and r.is_current=true
                where s.tenant_id=:tenant_id
                  and s.family_id=:family_id
                  and s.assessment_session_id=:assessment_session_id
                  and s.status in ('SUBMITTED','ANALYZING','READY','ACKNOWLEDGED')
                  and s.submitted_at is not null
                group by s.assessment_session_id,s.tenant_id,s.family_id,
                         s.subject_person_id,s.submitted_at,s.updated_at
                """
            ),
            {
                "tenant_id": tenant_id,
                "family_id": family_id,
                "assessment_session_id": assessment_session_id,
            },
        )
        row = result.mappings().first()
        if row is None:
            return None
        responses = tuple(row.get("responses") or ())
        focus = next(
            (item for item in responses if item.get("item_ref") == "FOCUS"),
            None,
        )
        if focus is None:
            return None
        if any(not item.get("author_person_id") for item in responses):
            return None
        evidence_refs = tuple(
            str(item["response_id"]) for item in responses if item.get("response_id")
        )
        if not evidence_refs:
            return None
        summary = _focus_summary(focus.get("response_value"))
        captured_at = _aware_timestamp(row.get("captured_at"))
        return AssessmentSignal(
            signal_id=str(row["assessment_session_id"]),
            tenant_id=str(row["tenant_id"]),
            family_id=str(row["family_id"]),
            subject_ref=str(row["subject_person_id"]),
            assessment_session_id=str(row["assessment_session_id"]),
            evidence_refs=evidence_refs,
            summary=summary,
            captured_at=captured_at,
            locale=locale,
        )

    async def load_consent_grants(
        self,
        *,
        family_id: str,
        subject_person_id: str,
        purpose: ConsentPurpose,
    ) -> tuple[ConsentGrant, ...]:
        """Load fresh purpose-scoped grants for the current transaction.

        The baseline consent table does not carry an expiry timestamp or a
        denormalized age.  Missing birth dates are fail-closed rather than
        guessed, and ``EXPIRED``/``WITHDRAWN`` rows remain visible to
        ``ConsentGate`` as denying facts.
        """

        _assert_uuid(family_id, "family_id")
        _assert_uuid(subject_person_id, "subject_person_id")
        result = await self._connection.execute(
            text(
                """
                select c.consent_id::text as consent_id,
                       c.subject_person_id::text as subject_person_id,
                       c.guardian_person_id::text as guardian_person_id,
                       c.purpose::text as purpose,
                       c.status::text as status,
                       c.granted_at,
                       p.birth_date
                from consents c
                join persons p
                  on p.person_id=c.subject_person_id
                 and p.family_id=c.family_id
                where c.family_id=:family_id
                  and c.subject_person_id=:subject_person_id
                  and c.purpose=:purpose
                order by c.granted_at desc
                """
            ),
            {
                "family_id": family_id,
                "subject_person_id": subject_person_id,
                "purpose": purpose.value.upper(),
            },
        )
        grants: list[ConsentGrant] = []
        for row in result.mappings():
            birth_date = row.get("birth_date")
            if birth_date is None:
                continue
            try:
                grants.append(_consent_grant(row, purpose, birth_date))
            except (ValueError, TypeError):
                # Invalid or incomplete consent provenance must deny rather
                # than accidentally widen the subject's processing scope.
                continue
        return tuple(grants)

    async def append_signal_acceptance(
        self,
        *,
        signal: AssessmentSignal,
        actor_id: str,
        idempotency_key: str,
        correlation_id: str,
        response: dict[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        """Append audit + outbox atomically and return ``(response, replay)``.

        ``idempotency_keys`` is a legacy global primary-key table, so the key
        is namespaced by tenant/family/capability before storage.  The
        caller's transaction must roll back all three writes together on any
        exception; no response is cached until audit and outbox succeed.
        """

        _assert_uuid(signal.tenant_id, "tenant_id")
        _assert_uuid(signal.family_id, "family_id")
        if not actor_id.strip() or not correlation_id.strip():
            raise JourneyValidationError("actor_and_correlation_required")
        if not idempotency_key.strip() or len(idempotency_key) > 128:
            raise JourneyValidationError("invalid_idempotency_key")
        scoped_key = _scoped_idempotency_key(signal.tenant_id, signal.family_id, idempotency_key)
        request_hash = _request_hash(
            signal=signal,
            actor_id=actor_id,
            correlation_id=correlation_id,
            response=response,
        )
        await self._connection.execute(
            text(
                """
                insert into idempotency_keys(idempotency_key,action_name,request_hash)
                values (:key,'VS-GROWTH-01.AcceptSignal',:request_hash)
                on conflict (idempotency_key) do nothing
                """
            ),
            {"key": scoped_key, "request_hash": request_hash},
        )
        existing_result = await self._connection.execute(
            text(
                """
                select action_name,request_hash,response_body
                from idempotency_keys
                where idempotency_key=:key
                for update
                """
            ),
            {"key": scoped_key},
        )
        existing = existing_result.mappings().first()
        if existing is None:
            raise JourneyValidationError("idempotency_claim_missing")
        if (
            existing["action_name"] != "VS-GROWTH-01.AcceptSignal"
            or existing["request_hash"] != request_hash
        ):
            raise JourneyConflictError("idempotency_conflict")
        if existing.get("response_body") is not None:
            cached = existing["response_body"]
            if isinstance(cached, str):
                cached = json.loads(cached)
            return dict(cached), True

        occurred_at = datetime.now(UTC)
        event_id = str(uuid4())
        resource_id = signal.assessment_session_id
        metadata = json.dumps(
            {
                "capability_id": self.capability_id,
                "tenant_id": signal.tenant_id,
                "signal_id": signal.signal_id,
                "evidence_refs": list(signal.evidence_refs),
                "locale": signal.locale,
                "boundary": "ASSESSMENT_SUBMITTED_EVIDENCE_NOT_FACT",
            },
            ensure_ascii=False,
        )
        await self._connection.execute(
            text(
                """
                insert into audit_logs(
                  family_id,actor_type,actor_id,action_name,resource_type,resource_id,
                  correlation_id,idempotency_key,result,metadata
                ) values (
                  :family_id,'USER',:actor_id,'VS-GROWTH-01.SignalAccepted',
                  'AssessmentSignal',:resource_id,:correlation_id,:idempotency_key,
                  'SUCCESS',cast(:metadata as jsonb)
                )
                """
            ),
            {
                "family_id": signal.family_id,
                "actor_id": actor_id,
                "resource_id": resource_id,
                "correlation_id": correlation_id,
                "idempotency_key": idempotency_key,
                "metadata": metadata,
            },
        )
        payload = json.dumps(
            {
                "event_id": event_id,
                "capability_id": self.capability_id,
                "tenant_id": signal.tenant_id,
                "family_id": signal.family_id,
                "actor_id": actor_id,
                "resource_id": resource_id,
                "signal_id": signal.signal_id,
                "evidence_refs": list(signal.evidence_refs),
                "locale": signal.locale,
                "occurred_at": occurred_at.isoformat(),
            },
            ensure_ascii=False,
        )
        await self._connection.execute(
            text(
                """
                insert into outbox_events(
                  aggregate_type,aggregate_id,event_name,event_version,event_id,
                  correlation_id,payload,occurred_at
                ) values (
                  'VS-GROWTH-01',:resource_id,'VS-GROWTH-01.SignalAccepted',1,
                  :event_id,:correlation_id,cast(:payload as jsonb),:occurred_at
                )
                """
            ),
            {
                "resource_id": resource_id,
                "event_id": event_id,
                "correlation_id": correlation_id,
                "payload": payload,
                "occurred_at": occurred_at,
            },
        )
        await self._connection.execute(
            text(
                """
                update idempotency_keys
                   set response_code=200,response_body=cast(:response_body as jsonb)
                 where idempotency_key=:key
                """
            ),
            {
                "key": scoped_key,
                "response_body": json.dumps(response, ensure_ascii=False),
            },
        )
        return response, False


def _consent_grant(row: Any, purpose: ConsentPurpose, birth_date: date) -> ConsentGrant:
    granted_at = _aware_timestamp(row["granted_at"])
    age = _age_years(birth_date, granted_at.date())
    subject_id = str(row["subject_person_id"])
    guardian_id = str(row["guardian_person_id"])
    relation = GuardianRelation.SELF if subject_id == guardian_id else GuardianRelation.GUARDIAN
    status = ConsentStatus(str(row["status"]).lower())
    return ConsentGrant(
        consent_id=str(row["consent_id"]),
        subject_person_id=subject_id,
        guardian_person_id=guardian_id,
        purpose=purpose,
        status=status,
        granted_at=granted_at,
        subject_age=SubjectAge(years=age),
        guardian_relation=relation,
    )


def _focus_summary(value: Any) -> str:
    if isinstance(value, str):
        focus = value.strip()
    else:
        focus = json.dumps(value, ensure_ascii=False, sort_keys=True)
    if not focus:
        raise JourneyValidationError("assessment_focus_required")
    return f"家庭测评已提交，当前关注点：{focus}"


def _age_years(birth_date: date, at: date) -> int:
    years = at.year - birth_date.year
    if (at.month, at.day) < (birth_date.month, birth_date.day):
        years -= 1
    return years


def _aware_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _assert_uuid(value: str, name: str) -> None:
    try:
        UUID(value)
    except (ValueError, AttributeError, TypeError) as error:
        raise JourneyValidationError(f"{name}_must_be_uuid") from error


def _assert_locale(locale: str) -> None:
    if not locale.strip() or len(locale) > 32:
        raise JourneyValidationError("invalid_locale")


def _scoped_idempotency_key(tenant_id: str, family_id: str, key: str) -> str:
    scoped = f"VS-GROWTH-01:{tenant_id}:{family_id}:{key}"
    if len(scoped) <= 128:
        return scoped
    digest = hashlib.sha256(scoped.encode()).hexdigest()
    return f"VS-GROWTH-01:{digest}"


def _request_hash(
    *,
    signal: AssessmentSignal,
    actor_id: str,
    correlation_id: str,
    response: dict[str, Any],
) -> str:
    canonical = json.dumps(
        {
            "capability_id": "VS-GROWTH-01",
            "tenant_id": signal.tenant_id,
            "family_id": signal.family_id,
            "signal_id": signal.signal_id,
            "actor_id": actor_id,
            "evidence_refs": signal.evidence_refs,
            "response": response,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


__all__ = ["S01PostgresAssessmentRepository"]
