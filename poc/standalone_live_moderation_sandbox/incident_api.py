"""Synthetic-only trust incident workflow for the standalone live sandbox.

The module owns only incident workflow state. Identity/scope checks are reused
from the existing moderation sandbox, while control, interaction, and media
effects are represented by injected, reversible sandbox ports.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal, Protocol

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from poc.standalone_live_moderation_sandbox.question_api import (
    SANDBOX_SOURCE,
    SyntheticActor,
    actor_headers,
    require_role,
    require_scope,
)

IncidentState = Literal["PENDING", "CONTINUED", "HIDDEN", "STOPPED"]
DecisionAction = Literal["CONTINUE", "HIDE", "STOP"]


class SubmitIncident(BaseModel):
    report_ref: str = Field(min_length=3, max_length=120)
    idempotency_key: str = Field(min_length=3, max_length=120)
    reason: str = Field(min_length=2, max_length=500)


class DecideIncident(BaseModel):
    decision_key: str = Field(min_length=3, max_length=120)
    action: DecisionAction
    reason: str = Field(min_length=2, max_length=500)


class SandboxReceipt(BaseModel):
    receipt_ref: str
    action: DecisionAction
    completed_components: list[str]
    audit_mode: Literal["SANDBOX_RECEIPT_ONLY"] = "SANDBOX_RECEIPT_ONLY"
    source: Literal["SANDBOX_SYNTHETIC"] = SANDBOX_SOURCE
    fixture_only: Literal[True] = True
    external_effect: Literal[False] = False


class IncidentView(BaseModel):
    report_ref: str
    session_ref: str
    reporter_id: str
    reason: str
    state: IncidentState
    created_at: str
    updated_at: str
    decision_reason: str | None = None
    decided_by: str | None = None
    receipt: SandboxReceipt | None = None
    source: Literal["SANDBOX_SYNTHETIC"] = SANDBOX_SOURCE
    fixture_only: Literal[True] = True
    external_effect: Literal[False] = False


@dataclass(frozen=True, slots=True)
class IncidentContext:
    report_ref: str
    session_ref: str
    tenant_id: str
    family_id: str
    action: DecisionAction


class ReversibleIncidentPort(Protocol):
    """A sandbox operation that can be prepared, committed, and compensated."""

    def prepare(self, context: IncidentContext) -> object: ...

    def commit(self, prepared: object) -> None: ...

    def rollback(self, prepared: object) -> None: ...


class NoOpSandboxPort:
    """Default port keeps the API runnable without claiming external effects."""

    def prepare(self, context: IncidentContext) -> object:
        return context

    def commit(self, prepared: object) -> None:
        return None

    def rollback(self, prepared: object) -> None:
        return None


@dataclass(frozen=True, slots=True)
class NamedPort:
    name: str
    port: ReversibleIncidentPort


def create_app(
    database_path: Path,
    *,
    control_port: ReversibleIncidentPort | None = None,
    interaction_port: ReversibleIncidentPort | None = None,
    media_port: ReversibleIncidentPort | None = None,
) -> FastAPI:
    app = FastAPI(title="Xiao Ju Deng trust incident sandbox")
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^http://(127\.0\.0\.1|localhost)(:\d+)?$",
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
        allow_credentials=False,
    )
    initialise(database_path)
    ports = {
        "control": control_port or NoOpSandboxPort(),
        "interaction": interaction_port or NoOpSandboxPort(),
        "media": media_port or NoOpSandboxPort(),
    }

    @app.get("/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "source": SANDBOX_SOURCE,
            "fixture_only": True,
            "external_effect": False,
        }

    @app.post(
        "/sandbox/live-incidents/sessions/{session_ref}/reports",
        response_model=IncidentView,
        status_code=202,
    )
    def submit_report(
        session_ref: str,
        request: SubmitIncident,
        actor: Annotated[SyntheticActor, Depends(actor_headers())],
    ) -> IncidentView:
        require_role(actor, {"ADULT_VIEWER"})
        reason = require_text(request.reason, "report reason is required")
        with connect(database_path) as database:
            prior = database.execute(
                "SELECT * FROM live_incidents WHERE idempotency_key = ?",
                (request.idempotency_key,),
            ).fetchone()
            if prior is not None:
                if not same_report(prior, request.report_ref, session_ref, actor, reason):
                    raise HTTPException(status_code=409, detail="report idempotency key conflict")
                return incident_view(prior)
            try:
                timestamp = now_iso()
                database.execute(
                    """
                    INSERT INTO live_incidents (
                        report_ref, session_ref, tenant_id, family_id, reporter_id,
                        reason, state, idempotency_key, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?, ?, ?)
                    """,
                    (
                        request.report_ref,
                        session_ref,
                        actor.tenant_id,
                        actor.family_id,
                        actor.actor_id,
                        reason,
                        request.idempotency_key,
                        timestamp,
                        timestamp,
                    ),
                )
                database.commit()
            except sqlite3.IntegrityError as exc:
                raise HTTPException(status_code=409, detail="report reference conflict") from exc
            row = database.execute(
                "SELECT * FROM live_incidents WHERE report_ref = ?", (request.report_ref,)
            ).fetchone()
        return incident_view(row)

    @app.get("/sandbox/live-incidents/reports", response_model=list[IncidentView])
    def list_reports(
        response: Response,
        actor: Annotated[SyntheticActor, Depends(actor_headers())],
    ) -> list[IncidentView]:
        response.headers["Cache-Control"] = "no-store"
        require_role(actor, {"ADULT_VIEWER", "HUMAN_MODERATOR"})
        query = """
            SELECT * FROM live_incidents
            WHERE tenant_id = ? AND family_id = ?
        """
        parameters: list[str] = [actor.tenant_id, actor.family_id]
        if actor.role == "ADULT_VIEWER":
            query += " AND reporter_id = ?"
            parameters.append(actor.actor_id)
        query += " ORDER BY created_at ASC"
        with connect(database_path) as database:
            rows = database.execute(query, parameters).fetchall()
        return [incident_view(row) for row in rows]

    @app.post(
        "/sandbox/live-incidents/reports/{report_ref}/decisions",
        response_model=IncidentView,
    )
    def decide_report(
        report_ref: str,
        request: DecideIncident,
        actor: Annotated[SyntheticActor, Depends(actor_headers())],
    ) -> IncidentView:
        require_role(actor, {"HUMAN_MODERATOR"})
        reason = require_text(request.reason, "decision reason is required")
        database = connect(database_path)
        prepared: list[tuple[NamedPort, object]] = []
        try:
            database.execute("BEGIN IMMEDIATE")
            row = database.execute(
                "SELECT * FROM live_incidents WHERE report_ref = ?", (report_ref,)
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="incident not found")
            require_scope(actor, row["tenant_id"], row["family_id"])

            prior = database.execute(
                "SELECT * FROM incident_decisions WHERE decision_key = ?",
                (request.decision_key,),
            ).fetchone()
            if prior is not None:
                if (
                    prior["report_ref"] != report_ref
                    or prior["action"] != request.action
                    or prior["reason"] != reason
                ):
                    raise HTTPException(status_code=409, detail="decision key conflict")
                return incident_view(row)
            if row["state"] != "PENDING":
                raise HTTPException(status_code=409, detail="incident already decided")

            context = IncidentContext(
                report_ref=report_ref,
                session_ref=row["session_ref"],
                tenant_id=row["tenant_id"],
                family_id=row["family_id"],
                action=request.action,
            )
            selected = select_ports(request.action, ports)
            prepared = prepare_and_commit(selected, context)
            next_state = state_for(request.action)
            timestamp = now_iso()
            receipt = SandboxReceipt(
                receipt_ref=f"sandbox-receipt:{request.decision_key}",
                action=request.action,
                completed_components=[item.name for item, _ in prepared],
            )
            receipt_json = receipt.model_dump_json()
            database.execute(
                """
                UPDATE live_incidents
                SET state = ?, decision_reason = ?, decided_by = ?, receipt_json = ?,
                    updated_at = ?
                WHERE report_ref = ? AND state = 'PENDING'
                """,
                (next_state, reason, actor.actor_id, receipt_json, timestamp, report_ref),
            )
            database.execute(
                """
                INSERT INTO incident_decisions (
                    decision_key, report_ref, action, reason, decided_by, receipt_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request.decision_key,
                    report_ref,
                    request.action,
                    reason,
                    actor.actor_id,
                    receipt_json,
                    timestamp,
                ),
            )
            database.commit()
            current = database.execute(
                "SELECT * FROM live_incidents WHERE report_ref = ?", (report_ref,)
            ).fetchone()
            return incident_view(current)
        except HTTPException:
            database.rollback()
            raise
        except Exception as exc:
            database.rollback()
            rollback_ports(prepared)
            raise HTTPException(status_code=503, detail="incident orchestration failed") from exc
        finally:
            database.close()

    return app


def select_ports(
    action: DecisionAction, ports: dict[str, ReversibleIncidentPort]
) -> list[NamedPort]:
    if action == "CONTINUE":
        return []
    names = (
        ["control", "interaction"]
        if action == "HIDE"
        else [
            "control",
            "interaction",
            "media",
        ]
    )
    return [NamedPort(name=name, port=ports[name]) for name in names]


def prepare_and_commit(
    selected: list[NamedPort], context: IncidentContext
) -> list[tuple[NamedPort, object]]:
    prepared: list[tuple[NamedPort, object]] = []
    try:
        for item in selected:
            prepared.append((item, item.port.prepare(context)))
        for item, operation in prepared:
            item.port.commit(operation)
    except Exception:
        rollback_ports(prepared)
        raise
    return prepared


def rollback_ports(prepared: list[tuple[NamedPort, object]]) -> None:
    for item, operation in reversed(prepared):
        with suppress(Exception):
            item.port.rollback(operation)


def state_for(action: DecisionAction) -> IncidentState:
    return {"CONTINUE": "CONTINUED", "HIDE": "HIDDEN", "STOP": "STOPPED"}[action]


def same_report(
    row: sqlite3.Row,
    report_ref: str,
    session_ref: str,
    actor: SyntheticActor,
    reason: str,
) -> bool:
    return (
        row["report_ref"] == report_ref
        and row["session_ref"] == session_ref
        and row["tenant_id"] == actor.tenant_id
        and row["family_id"] == actor.family_id
        and row["reporter_id"] == actor.actor_id
        and row["reason"] == reason
    )


def incident_view(row: sqlite3.Row) -> IncidentView:
    receipt = json.loads(row["receipt_json"]) if row["receipt_json"] else None
    return IncidentView(
        report_ref=row["report_ref"],
        session_ref=row["session_ref"],
        reporter_id=row["reporter_id"],
        reason=row["reason"],
        state=row["state"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        decision_reason=row["decision_reason"],
        decided_by=row["decided_by"],
        receipt=receipt,
    )


def require_text(value: str, detail: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise HTTPException(status_code=422, detail=detail)
    return stripped


def connect(database_path: Path) -> sqlite3.Connection:
    database = sqlite3.connect(database_path, timeout=5)
    database.row_factory = sqlite3.Row
    return database


def initialise(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(database_path) as database:
        database.executescript(
            """
            CREATE TABLE IF NOT EXISTS live_incidents (
                report_ref TEXT PRIMARY KEY,
                session_ref TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                family_id TEXT NOT NULL,
                reporter_id TEXT NOT NULL,
                reason TEXT NOT NULL,
                state TEXT NOT NULL,
                idempotency_key TEXT NOT NULL UNIQUE,
                decision_reason TEXT,
                decided_by TEXT,
                receipt_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS incident_decisions (
                decision_key TEXT PRIMARY KEY,
                report_ref TEXT NOT NULL,
                action TEXT NOT NULL,
                reason TEXT NOT NULL,
                decided_by TEXT NOT NULL,
                receipt_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (report_ref) REFERENCES live_incidents(report_ref)
            );
            """
        )


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--port", type=int, default=55306)
    args = parser.parse_args()
    if not args.serve:
        raise SystemExit("use --serve")
    uvicorn.run(create_app(args.database), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
