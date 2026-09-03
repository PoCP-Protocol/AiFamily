"""Persistent synthetic Live session control-plane HTTP sandbox.

This is a disposable product-domain sandbox. It stores only synthetic live
session state and operation receipts. It is not AiFamily's canonical Identity,
Consent, Audit/Outbox, Deletion, or financial ledger and never mounts into
``family_api``.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Literal

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, model_validator

from poc.standalone_live_control_sandbox.control_plane import (
    LIVE_ATTENDANCE_PURPOSE,
    CanonicalConsentDecision,
    CanonicalConsentPort,
)
from poc.standalone_live_moderation_sandbox.question_api import (
    SANDBOX_SOURCE,
    SyntheticActor,
    actor_headers,
    require_role,
    require_scope,
)

ReviewStatus = Literal["DRAFT", "APPROVED", "REJECTED", "WITHDRAWN"]
LifecycleStatus = Literal["SCHEDULED", "LIVE", "ENDED", "WITHDRAWN"]


class CreateSessionRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    session_ref: str = Field(min_length=3, max_length=120)
    idempotency_key: str = Field(min_length=3, max_length=120)
    title: str = Field(min_length=3, max_length=160)
    speaker: str = Field(min_length=2, max_length=120)
    expert_summary: str = Field(min_length=3, max_length=500)
    applicable_scope: str = Field(min_length=2, max_length=160)
    problem_tags: list[str] = Field(min_length=1, max_length=8)
    starts_at: datetime
    ends_at: datetime
    audience_scope: Literal["FAMILY"] = "FAMILY"

    @model_validator(mode="after")
    def validate_window(self) -> CreateSessionRequest:
        if self.starts_at.tzinfo is None or self.ends_at.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware")
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must follow starts_at")
        if any(not tag.strip() for tag in self.problem_tags):
            raise ValueError("problem tags must not be blank")
        return self


class ReviewSessionRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    decision_key: str = Field(min_length=3, max_length=120)
    action: Literal["APPROVE", "REJECT", "WITHDRAW"]
    reason: str = Field(min_length=2, max_length=240)
    review_ref: str = Field(min_length=3, max_length=120)


class LifecycleRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    action_key: str = Field(min_length=3, max_length=120)
    action: Literal["GO_LIVE", "END", "WITHDRAW"]
    reason: str = Field(min_length=2, max_length=240)


class RegistrationRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    idempotency_key: str = Field(min_length=3, max_length=120)
    correlation_id: str = Field(min_length=3, max_length=120)


class RegistrationView(BaseModel):
    registration_ref: str
    session_ref: str
    tenant_id: str
    family_id: str
    guardian_id: str
    consent_ref: str
    status: Literal["CONFIRMED", "CANCELLED"]
    replayed: bool
    receipt_ref: str
    purpose: Literal["live_attendance"] = LIVE_ATTENDANCE_PURPOSE
    source: Literal["SANDBOX_SYNTHETIC"] = SANDBOX_SOURCE
    fixture_only: Literal[True] = True
    audit_mode: Literal["SANDBOX_RECEIPT_ONLY"] = "SANDBOX_RECEIPT_ONLY"
    external_effect: Literal[False] = False


class SyntheticConsentProjection:
    """Ephemeral CLI-only Consent adapter for the disposable sandbox."""

    def __init__(self, *, ttl: timedelta = timedelta(minutes=10)) -> None:
        if ttl <= timedelta(0) or ttl > timedelta(minutes=15):
            raise ValueError("synthetic Consent TTL must be within 15 minutes")
        self._ttl = ttl

    def require_grant(
        self,
        *,
        tenant_id: str,
        family_id: str,
        guardian_id: str,
        purpose: str,
        session_ref: str,
        now: datetime,
    ) -> CanonicalConsentDecision:
        identifiers = (tenant_id, family_id, guardian_id, session_ref)
        if now.tzinfo is None:
            raise ValueError("synthetic Consent clock must be timezone-aware")
        if purpose != LIVE_ATTENDANCE_PURPOSE or not all(
            value.startswith(prefix)
            for value, prefix in zip(
                identifiers,
                ("tenant.synthetic", "family.synthetic", "actor.synthetic", "live.synthetic"),
                strict=True,
            )
        ):
            raise ValueError("synthetic Consent scope rejected")
        consent_hash = sha256(
            ":".join((*identifiers, purpose, now.isoformat())).encode()
        ).hexdigest()[:24]
        return CanonicalConsentDecision(
            consent_ref=f"consent.synthetic.ephemeral.{consent_hash}",
            tenant_id=tenant_id,
            family_id=family_id,
            guardian_id=guardian_id,
            purpose=purpose,
            granted=True,
            expires_at=now + self._ttl,
        )


class SessionView(BaseModel):
    session_ref: str
    title: str
    speaker: str
    problem_tags: list[str]
    expert_summary: str
    applicable_scope: str
    starts_at: str
    ends_at: str
    review_ref: str | None
    version: str
    status: LifecycleStatus
    approval_status: ReviewStatus
    expiry_state: Literal["UNEXPIRED", "EXPIRED"]
    audience_scope: Literal["FAMILY"]
    family_visibility: Literal["family-private"] = "family-private"
    capabilities: dict[str, Literal["LOCKED"]]
    playback_state: Literal["WAITING_AUTHORIZATION"] = "WAITING_AUTHORIZATION"
    section: Literal["live-now", "upcoming", "ended"]
    as_of: str
    source: Literal["SANDBOX_SYNTHETIC"] = SANDBOX_SOURCE
    fixture_only: Literal[True] = True
    external_effect: Literal[False] = False
    audit_mode: Literal["SANDBOX_RECEIPT_ONLY"] = "SANDBOX_RECEIPT_ONLY"


def create_app(database_path: Path, *, consent: CanonicalConsentPort | None = None) -> FastAPI:
    initialise(database_path)
    synthetic_consent_enabled = isinstance(consent, SyntheticConsentProjection)
    app = FastAPI(title="Xiao Ju Deng Live Control Plane sandbox")
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^http://127\.0\.0\.1:\d+$",
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "source": SANDBOX_SOURCE,
            "fixture_only": True,
            "synthetic_consent_enabled": synthetic_consent_enabled,
            "consent_persistence": False,
            "external_effect": False,
        }

    @app.post("/sandbox/live-control/sessions", response_model=SessionView, status_code=201)
    def create_session(
        request: CreateSessionRequest,
        actor: Annotated[SyntheticActor, Depends(actor_headers())],
    ) -> SessionView:
        require_role(actor, {"CREATOR"})
        fingerprint = create_fingerprint(request, actor)
        with connect(database_path) as database:
            prior = database.execute(
                "SELECT * FROM live_sessions WHERE create_idempotency_key = ?",
                (request.idempotency_key,),
            ).fetchone()
            if prior is not None:
                if prior["create_fingerprint"] != fingerprint:
                    raise HTTPException(status_code=409, detail="idempotency key conflict")
                return session_view(prior, now_utc())
            timestamp = now_iso()
            try:
                database.execute(
                    """
                    INSERT INTO live_sessions (
                        session_ref, tenant_id, family_id, creator_id, title, speaker,
                        expert_summary, applicable_scope, problem_tags, audience_scope,
                        starts_at, ends_at, review_status, lifecycle_status, review_ref,
                        version, create_idempotency_key, create_fingerprint, created_at,
                        updated_at, source, fixture_only
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'FAMILY', ?, ?, 'DRAFT',
                              'SCHEDULED', NULL, 1, ?, ?, ?, ?, ?, 1)
                    """,
                    (
                        request.session_ref,
                        actor.tenant_id,
                        actor.family_id,
                        actor.actor_id,
                        request.title.strip(),
                        request.speaker.strip(),
                        request.expert_summary.strip(),
                        request.applicable_scope.strip(),
                        json.dumps(
                            [tag.strip() for tag in request.problem_tags], ensure_ascii=False
                        ),
                        iso_utc(request.starts_at),
                        iso_utc(request.ends_at),
                        request.idempotency_key,
                        fingerprint,
                        timestamp,
                        timestamp,
                        SANDBOX_SOURCE,
                    ),
                )
                append_receipt(
                    database,
                    receipt_key=f"create:{request.idempotency_key}",
                    session_ref=request.session_ref,
                    actor=actor,
                    action="SESSION_CREATED",
                    reason="creator submitted synthetic session",
                )
                database.commit()
            except sqlite3.IntegrityError as exc:
                raise HTTPException(status_code=409, detail="session reference conflict") from exc
            row = require_session(database, request.session_ref)
        return session_view(row, now_utc())

    @app.post("/sandbox/live-control/sessions/{session_ref}/review", response_model=SessionView)
    def review_session(
        session_ref: str,
        request: ReviewSessionRequest,
        actor: Annotated[SyntheticActor, Depends(actor_headers())],
    ) -> SessionView:
        require_role(actor, {"CONTENT_REVIEWER"})
        with connect(database_path) as database:
            row = require_session(database, session_ref)
            require_scope(actor, row["tenant_id"], row["family_id"])
            replay = database.execute(
                "SELECT session_ref, tenant_id, family_id, reviewer_id, action, reason, review_ref "
                "FROM live_review_decisions "
                "WHERE decision_key = ?",
                (request.decision_key,),
            ).fetchone()
            if replay is not None:
                expected = (
                    session_ref,
                    actor.tenant_id,
                    actor.family_id,
                    actor.actor_id,
                    request.action,
                    request.reason,
                    request.review_ref,
                )
                if tuple(replay) != expected:
                    raise HTTPException(status_code=409, detail="decision key conflict")
                return session_view(require_session(database, session_ref), now_utc())
            current = row["review_status"]
            allowed = (current == "DRAFT" and request.action in {"APPROVE", "REJECT"}) or (
                current == "APPROVED" and request.action == "WITHDRAW"
            )
            if not allowed:
                raise HTTPException(status_code=409, detail="review transition rejected")
            next_review = {
                "APPROVE": "APPROVED",
                "REJECT": "REJECTED",
                "WITHDRAW": "WITHDRAWN",
            }[request.action]
            next_lifecycle = (
                "WITHDRAWN" if request.action == "WITHDRAW" else row["lifecycle_status"]
            )
            database.execute(
                """
                UPDATE live_sessions
                SET review_status = ?, lifecycle_status = ?, review_ref = ?,
                    version = version + 1, updated_at = ?
                WHERE session_ref = ?
                """,
                (next_review, next_lifecycle, request.review_ref, now_iso(), session_ref),
            )
            database.execute(
                """
                INSERT INTO live_review_decisions (
                    decision_key, session_ref, tenant_id, family_id, reviewer_id,
                    action, reason, review_ref, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request.decision_key,
                    session_ref,
                    actor.tenant_id,
                    actor.family_id,
                    actor.actor_id,
                    request.action,
                    request.reason,
                    request.review_ref,
                    now_iso(),
                ),
            )
            append_receipt(
                database,
                receipt_key=f"review:{request.decision_key}",
                session_ref=session_ref,
                actor=actor,
                action=f"SESSION_{request.action}",
                reason=request.reason,
            )
            database.commit()
            updated = require_session(database, session_ref)
        return session_view(updated, now_utc())

    @app.post("/sandbox/live-control/sessions/{session_ref}/lifecycle", response_model=SessionView)
    def change_lifecycle(
        session_ref: str,
        request: LifecycleRequest,
        actor: Annotated[SyntheticActor, Depends(actor_headers())],
    ) -> SessionView:
        require_role(actor, {"LIVE_OPERATOR"})
        with connect(database_path) as database:
            row = require_session(database, session_ref)
            require_scope(actor, row["tenant_id"], row["family_id"])
            replay = database.execute(
                "SELECT session_ref, tenant_id, family_id, operator_id, action, reason "
                "FROM live_lifecycle_actions WHERE action_key = ?",
                (request.action_key,),
            ).fetchone()
            if replay is not None:
                expected = (
                    session_ref,
                    actor.tenant_id,
                    actor.family_id,
                    actor.actor_id,
                    request.action,
                    request.reason,
                )
                if tuple(replay) != expected:
                    raise HTTPException(status_code=409, detail="action key conflict")
                return session_view(require_session(database, session_ref), now_utc())
            next_status = lifecycle_transition(row, request.action, now_utc())
            database.execute(
                "UPDATE live_sessions SET lifecycle_status = ?, version = version + 1, "
                "updated_at = ? "
                "WHERE session_ref = ?",
                (next_status, now_iso(), session_ref),
            )
            database.execute(
                """
                INSERT INTO live_lifecycle_actions (
                    action_key, session_ref, tenant_id, family_id, operator_id,
                    action, reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request.action_key,
                    session_ref,
                    actor.tenant_id,
                    actor.family_id,
                    actor.actor_id,
                    request.action,
                    request.reason,
                    now_iso(),
                ),
            )
            append_receipt(
                database,
                receipt_key=f"lifecycle:{request.action_key}",
                session_ref=session_ref,
                actor=actor,
                action=f"SESSION_{request.action}",
                reason=request.reason,
            )
            database.commit()
            updated = require_session(database, session_ref)
        return session_view(updated, now_utc())

    @app.get(
        "/sandbox/live-control/families/{family_id}/sessions",
        response_model=list[SessionView],
    )
    def discover_sessions(
        family_id: str,
        response: Response,
        actor: Annotated[SyntheticActor, Depends(actor_headers())],
    ) -> list[SessionView]:
        response.headers["Cache-Control"] = "no-store"
        require_role(actor, {"ADULT_VIEWER"})
        require_scope(actor, actor.tenant_id, family_id)
        now = now_utc()
        with connect(database_path) as database:
            rows = database.execute(
                """
                SELECT * FROM live_sessions
                WHERE tenant_id = ? AND family_id = ? AND audience_scope = 'FAMILY'
                  AND review_status = 'APPROVED'
                  AND lifecycle_status IN ('SCHEDULED', 'LIVE')
                  AND ends_at > ?
                ORDER BY CASE lifecycle_status WHEN 'LIVE' THEN 0 ELSE 1 END,
                         starts_at ASC, session_ref ASC
                """,
                (actor.tenant_id, actor.family_id, iso_utc(now)),
            ).fetchall()
        return [session_view(row, now) for row in rows]

    @app.get(
        "/sandbox/live-control/operator/sessions",
        response_model=list[SessionView],
    )
    def operator_sessions(
        response: Response,
        actor: Annotated[SyntheticActor, Depends(actor_headers())],
    ) -> list[SessionView]:
        response.headers["Cache-Control"] = "no-store"
        require_role(actor, {"CREATOR", "CONTENT_REVIEWER", "LIVE_OPERATOR"})
        now = now_utc()
        with connect(database_path) as database:
            rows = database.execute(
                """
                SELECT * FROM live_sessions
                WHERE tenant_id = ? AND family_id = ?
                ORDER BY updated_at DESC, session_ref ASC
                """,
                (actor.tenant_id, actor.family_id),
            ).fetchall()
        return [session_view(row, now) for row in rows]

    @app.get(
        "/sandbox/live-control/families/{family_id}/sessions/{session_ref}",
        response_model=SessionView,
    )
    def session_detail(
        family_id: str,
        response: Response,
        session_ref: str,
        actor: Annotated[SyntheticActor, Depends(actor_headers())],
    ) -> SessionView:
        response.headers["Cache-Control"] = "no-store"
        require_role(actor, {"ADULT_VIEWER"})
        require_scope(actor, actor.tenant_id, family_id)
        now = now_utc()
        with connect(database_path) as database:
            row = database.execute(
                """
                SELECT * FROM live_sessions
                WHERE session_ref = ? AND tenant_id = ? AND family_id = ?
                  AND audience_scope = 'FAMILY' AND review_status = 'APPROVED'
                  AND lifecycle_status IN ('SCHEDULED', 'LIVE') AND ends_at > ?
                """,
                (session_ref, actor.tenant_id, actor.family_id, iso_utc(now)),
            ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="live session unavailable")
        return session_view(row, now)

    @app.post(
        "/sandbox/live-control/sessions/{session_ref}/registrations",
        response_model=RegistrationView,
        status_code=201,
    )
    def register_session(
        session_ref: str,
        request: RegistrationRequest,
        actor: Annotated[SyntheticActor, Depends(actor_headers())],
    ) -> RegistrationView:
        require_role(actor, {"ADULT_VIEWER"})
        fingerprint = registration_fingerprint("register", session_ref, request, actor)
        with connect(database_path) as database:
            replay = registration_command_replay(database, request.idempotency_key, fingerprint)
            if replay is not None:
                registration, receipt_ref = replay
                return registration_view(registration, replayed=True, receipt_ref=receipt_ref)

            session = require_session(database, session_ref)
            require_scope(actor, session["tenant_id"], session["family_id"])
            require_registrable_session(session, now_utc())
            decision = require_canonical_consent(
                consent,
                actor=actor,
                session_ref=session_ref,
                now=now_utc(),
            )
            duplicate = database.execute(
                "SELECT * FROM live_registrations "
                "WHERE session_ref = ? AND tenant_id = ? AND family_id = ? "
                "AND guardian_id = ?",
                (session_ref, actor.tenant_id, actor.family_id, actor.actor_id),
            ).fetchone()
            if duplicate is not None:
                raise HTTPException(status_code=409, detail="registration already exists")

            registration_ref = (
                "registration.synthetic." + sha256(fingerprint.encode()).hexdigest()[:24]
            )
            receipt_ref = f"registration:{request.idempotency_key}"
            timestamp = now_iso()
            database.execute(
                """
                INSERT INTO live_registrations (
                    registration_ref, session_ref, tenant_id, family_id, guardian_id,
                    consent_ref, status, created_at, updated_at, source, fixture_only
                ) VALUES (?, ?, ?, ?, ?, ?, 'CONFIRMED', ?, ?, ?, 1)
                """,
                (
                    registration_ref,
                    session_ref,
                    actor.tenant_id,
                    actor.family_id,
                    actor.actor_id,
                    decision.consent_ref,
                    timestamp,
                    timestamp,
                    SANDBOX_SOURCE,
                ),
            )
            append_registration_command(
                database,
                request=request,
                command_type="REGISTER",
                fingerprint=fingerprint,
                registration_ref=registration_ref,
                receipt_ref=receipt_ref,
            )
            append_receipt(
                database,
                receipt_key=receipt_ref,
                session_ref=session_ref,
                actor=actor,
                action="REGISTRATION_CONFIRMED",
                reason="canonical Consent projection granted",
            )
            database.commit()
            registration = require_registration(database, registration_ref)
        return registration_view(registration, replayed=False, receipt_ref=receipt_ref)

    @app.post(
        "/sandbox/live-control/registrations/{registration_ref}/cancel",
        response_model=RegistrationView,
    )
    def cancel_registration(
        registration_ref: str,
        request: RegistrationRequest,
        actor: Annotated[SyntheticActor, Depends(actor_headers())],
    ) -> RegistrationView:
        require_role(actor, {"ADULT_VIEWER"})
        fingerprint = registration_fingerprint("cancel", registration_ref, request, actor)
        with connect(database_path) as database:
            replay = registration_command_replay(database, request.idempotency_key, fingerprint)
            if replay is not None:
                registration, receipt_ref = replay
                return registration_view(registration, replayed=True, receipt_ref=receipt_ref)

            registration = require_registration(database, registration_ref)
            require_scope(actor, registration["tenant_id"], registration["family_id"])
            if registration["guardian_id"] != actor.actor_id:
                raise HTTPException(
                    status_code=403, detail="registration belongs to another guardian"
                )
            if registration["status"] != "CONFIRMED":
                raise HTTPException(status_code=409, detail="registration cannot be cancelled")

            receipt_ref = f"registration:{request.idempotency_key}"
            database.execute(
                "UPDATE live_registrations SET status = 'CANCELLED', updated_at = ? "
                "WHERE registration_ref = ?",
                (now_iso(), registration_ref),
            )
            append_registration_command(
                database,
                request=request,
                command_type="CANCEL",
                fingerprint=fingerprint,
                registration_ref=registration_ref,
                receipt_ref=receipt_ref,
            )
            append_receipt(
                database,
                receipt_key=receipt_ref,
                session_ref=registration["session_ref"],
                actor=actor,
                action="REGISTRATION_CANCELLED",
                reason="adult cancelled synthetic registration",
            )
            database.commit()
            cancelled = require_registration(database, registration_ref)
        return registration_view(cancelled, replayed=False, receipt_ref=receipt_ref)

    @app.get("/sandbox/live-control/sessions/{session_ref}/receipts")
    def receipts(
        session_ref: str,
        actor: Annotated[SyntheticActor, Depends(actor_headers())],
    ) -> dict[str, object]:
        require_role(actor, {"CREATOR", "CONTENT_REVIEWER", "LIVE_OPERATOR"})
        with connect(database_path) as database:
            session = require_session(database, session_ref)
            require_scope(actor, session["tenant_id"], session["family_id"])
            rows = database.execute(
                "SELECT action, actor_id, reason, created_at FROM live_operation_receipts "
                "WHERE session_ref = ? ORDER BY sequence ASC",
                (session_ref,),
            ).fetchall()
        return {
            "session_ref": session_ref,
            "receipts": [dict(row) for row in rows],
            "audit_mode": "SANDBOX_RECEIPT_ONLY",
            "source": SANDBOX_SOURCE,
            "fixture_only": True,
            "external_effect": False,
        }

    return app


def lifecycle_transition(row: sqlite3.Row, action: str, now: datetime) -> str:
    current = row["lifecycle_status"]
    if action == "GO_LIVE":
        if row["review_status"] != "APPROVED" or current != "SCHEDULED":
            raise HTTPException(status_code=409, detail="session cannot go live")
        if datetime.fromisoformat(row["ends_at"]) <= now:
            raise HTTPException(status_code=409, detail="session is expired")
        if datetime.fromisoformat(row["starts_at"]) > now:
            raise HTTPException(status_code=409, detail="session has not started")
        return "LIVE"
    if action == "END" and current == "LIVE":
        return "ENDED"
    if action == "WITHDRAW" and current in {"SCHEDULED", "LIVE"}:
        return "WITHDRAWN"
    raise HTTPException(status_code=409, detail="lifecycle transition rejected")


def session_view(row: sqlite3.Row, now: datetime) -> SessionView:
    ends_at = datetime.fromisoformat(row["ends_at"])
    expired = ends_at <= now or row["lifecycle_status"] == "ENDED"
    section = (
        "ended" if expired else "live-now" if row["lifecycle_status"] == "LIVE" else "upcoming"
    )
    return SessionView(
        session_ref=row["session_ref"],
        title=row["title"],
        speaker=row["speaker"],
        problem_tags=json.loads(row["problem_tags"]),
        expert_summary=row["expert_summary"],
        applicable_scope=row["applicable_scope"],
        starts_at=row["starts_at"],
        ends_at=row["ends_at"],
        review_ref=row["review_ref"],
        version=f"live-session.v{row['version']}",
        status=row["lifecycle_status"],
        approval_status=row["review_status"],
        expiry_state="EXPIRED" if expired else "UNEXPIRED",
        audience_scope=row["audience_scope"],
        capabilities={"favorite": "LOCKED", "replay": "LOCKED"},
        section=section,
        as_of=row["updated_at"],
    )


def create_fingerprint(request: CreateSessionRequest, actor: SyntheticActor) -> str:
    return json.dumps(
        {
            "tenant_id": actor.tenant_id,
            "family_id": actor.family_id,
            "actor_id": actor.actor_id,
            "session_ref": request.session_ref,
            "title": request.title,
            "speaker": request.speaker,
            "expert_summary": request.expert_summary,
            "applicable_scope": request.applicable_scope,
            "problem_tags": request.problem_tags,
            "audience_scope": request.audience_scope,
            "starts_at": iso_utc(request.starts_at),
            "ends_at": iso_utc(request.ends_at),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def registration_fingerprint(
    command: str,
    resource_ref: str,
    request: RegistrationRequest,
    actor: SyntheticActor,
) -> str:
    payload = json.dumps(
        {
            "command": command,
            "resource_ref": resource_ref,
            "tenant_id": actor.tenant_id,
            "family_id": actor.family_id,
            "guardian_id": actor.actor_id,
            "correlation_id": request.correlation_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(payload.encode()).hexdigest()


def require_registrable_session(row: sqlite3.Row, now: datetime) -> None:
    if row["review_status"] != "APPROVED":
        raise HTTPException(status_code=409, detail="session is not approved")
    if row["lifecycle_status"] != "SCHEDULED":
        raise HTTPException(status_code=409, detail="session is not scheduled")
    if row["audience_scope"] != "FAMILY":
        raise HTTPException(status_code=409, detail="session audience is unavailable")
    if datetime.fromisoformat(row["ends_at"]) <= now:
        raise HTTPException(status_code=409, detail="session is expired")


def require_canonical_consent(
    consent: CanonicalConsentPort | None,
    *,
    actor: SyntheticActor,
    session_ref: str,
    now: datetime,
) -> CanonicalConsentDecision:
    if consent is None:
        raise HTTPException(status_code=503, detail="canonical Consent projection unavailable")
    try:
        decision = consent.require_grant(
            tenant_id=actor.tenant_id,
            family_id=actor.family_id,
            guardian_id=actor.actor_id,
            purpose=LIVE_ATTENDANCE_PURPOSE,
            session_ref=session_ref,
            now=now,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="canonical Consent projection unavailable"
        ) from exc
    expires_at = decision.expires_at
    valid = (
        bool(decision.consent_ref)
        and decision.granted
        and decision.purpose == LIVE_ATTENDANCE_PURPOSE
        and decision.tenant_id == actor.tenant_id
        and decision.family_id == actor.family_id
        and decision.guardian_id == actor.actor_id
        and (expires_at is None or (expires_at.tzinfo is not None and expires_at > now))
    )
    if not valid:
        raise HTTPException(status_code=403, detail="active canonical Consent required")
    return decision


def registration_command_replay(
    database: sqlite3.Connection, idempotency_key: str, fingerprint: str
) -> tuple[sqlite3.Row, str] | None:
    command = database.execute(
        "SELECT fingerprint, registration_ref, receipt_ref "
        "FROM live_registration_commands "
        "WHERE idempotency_key = ?",
        (idempotency_key,),
    ).fetchone()
    if command is None:
        return None
    if command["fingerprint"] != fingerprint:
        raise HTTPException(status_code=409, detail="idempotency key conflict")
    return (
        require_registration(database, command["registration_ref"]),
        command["receipt_ref"],
    )


def append_registration_command(
    database: sqlite3.Connection,
    *,
    request: RegistrationRequest,
    command_type: str,
    fingerprint: str,
    registration_ref: str,
    receipt_ref: str,
) -> None:
    database.execute(
        """
        INSERT INTO live_registration_commands (
            idempotency_key, command_type, fingerprint, correlation_id,
            registration_ref, receipt_ref, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            request.idempotency_key,
            command_type,
            fingerprint,
            request.correlation_id,
            registration_ref,
            receipt_ref,
            now_iso(),
        ),
    )


def require_registration(database: sqlite3.Connection, registration_ref: str) -> sqlite3.Row:
    row = database.execute(
        "SELECT * FROM live_registrations WHERE registration_ref = ?",
        (registration_ref,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="registration not found")
    return row


def registration_view(row: sqlite3.Row, *, replayed: bool, receipt_ref: str) -> RegistrationView:
    return RegistrationView(
        registration_ref=row["registration_ref"],
        session_ref=row["session_ref"],
        tenant_id=row["tenant_id"],
        family_id=row["family_id"],
        guardian_id=row["guardian_id"],
        consent_ref=row["consent_ref"],
        status=row["status"],
        replayed=replayed,
        receipt_ref=receipt_ref,
    )


def require_session(database: sqlite3.Connection, session_ref: str) -> sqlite3.Row:
    row = database.execute(
        "SELECT * FROM live_sessions WHERE session_ref = ?", (session_ref,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="live session not found")
    return row


def append_receipt(
    database: sqlite3.Connection,
    *,
    receipt_key: str,
    session_ref: str,
    actor: SyntheticActor,
    action: str,
    reason: str,
) -> None:
    database.execute(
        """
        INSERT INTO live_operation_receipts (
            receipt_key, session_ref, tenant_id, family_id, actor_id,
            action, reason, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            receipt_key,
            session_ref,
            actor.tenant_id,
            actor.family_id,
            actor.actor_id,
            action,
            reason,
            now_iso(),
        ),
    )


def connect(database_path: Path) -> sqlite3.Connection:
    database = sqlite3.connect(database_path)
    database.row_factory = sqlite3.Row
    return database


def initialise(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(database_path) as database:
        database.executescript(
            """
            CREATE TABLE IF NOT EXISTS live_sessions (
                session_ref TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                family_id TEXT NOT NULL,
                creator_id TEXT NOT NULL,
                title TEXT NOT NULL,
                speaker TEXT NOT NULL,
                expert_summary TEXT NOT NULL,
                applicable_scope TEXT NOT NULL,
                problem_tags TEXT NOT NULL,
                audience_scope TEXT NOT NULL CHECK (audience_scope = 'FAMILY'),
                starts_at TEXT NOT NULL,
                ends_at TEXT NOT NULL,
                review_status TEXT NOT NULL,
                lifecycle_status TEXT NOT NULL,
                review_ref TEXT,
                version INTEGER NOT NULL,
                create_idempotency_key TEXT NOT NULL UNIQUE,
                create_fingerprint TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                source TEXT NOT NULL CHECK (source = 'SANDBOX_SYNTHETIC'),
                fixture_only INTEGER NOT NULL CHECK (fixture_only = 1)
            );
            CREATE TABLE IF NOT EXISTS live_review_decisions (
                decision_key TEXT PRIMARY KEY,
                session_ref TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                family_id TEXT NOT NULL,
                reviewer_id TEXT NOT NULL,
                action TEXT NOT NULL,
                reason TEXT NOT NULL,
                review_ref TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS live_lifecycle_actions (
                action_key TEXT PRIMARY KEY,
                session_ref TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                family_id TEXT NOT NULL,
                operator_id TEXT NOT NULL,
                action TEXT NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS live_operation_receipts (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                receipt_key TEXT NOT NULL UNIQUE,
                session_ref TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                family_id TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                action TEXT NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS live_registrations (
                registration_ref TEXT PRIMARY KEY,
                session_ref TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                family_id TEXT NOT NULL,
                guardian_id TEXT NOT NULL,
                consent_ref TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('CONFIRMED', 'CANCELLED')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                source TEXT NOT NULL CHECK (source = 'SANDBOX_SYNTHETIC'),
                fixture_only INTEGER NOT NULL CHECK (fixture_only = 1),
                UNIQUE (session_ref, tenant_id, family_id, guardian_id)
            );
            CREATE TABLE IF NOT EXISTS live_registration_commands (
                idempotency_key TEXT PRIMARY KEY,
                command_type TEXT NOT NULL CHECK (command_type IN ('REGISTER', 'CANCEL')),
                fingerprint TEXT NOT NULL,
                correlation_id TEXT NOT NULL,
                registration_ref TEXT NOT NULL,
                receipt_ref TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );
            """
        )


def iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat()


def now_utc() -> datetime:
    return datetime.now(UTC)


def now_iso() -> str:
    return now_utc().isoformat()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--port", type=int, default=55300)
    parser.add_argument("--enable-synthetic-consent", action="store_true")
    args = parser.parse_args()
    if not args.serve:
        raise SystemExit("use --serve")
    consent = SyntheticConsentProjection() if args.enable_synthetic_consent else None
    uvicorn.run(create_app(args.database, consent=consent), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
