"""Disposable HTTP sandbox for human-reviewed live questions.

This module never mounts into ``family_api``. It accepts only explicitly
synthetic actors and persists synthetic questions to an isolated SQLite file
so browser refresh and process restart can be exercised without creating a
second production identity, consent, audit, or moderation ledger.
"""

from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

SANDBOX_SOURCE = "SANDBOX_SYNTHETIC"


class SubmitQuestion(BaseModel):
    question_ref: str = Field(min_length=3, max_length=120)
    idempotency_key: str = Field(min_length=3, max_length=120)
    text: str = Field(min_length=2, max_length=240)


class ReviewQuestion(BaseModel):
    decision_key: str = Field(min_length=3, max_length=120)
    action: Literal["APPROVE", "REJECT", "EDIT"]
    reason: str = Field(min_length=2, max_length=240)
    edited_text: str | None = Field(default=None, max_length=240)


class QuestionView(BaseModel):
    question_ref: str
    session_ref: str
    text: str
    status: Literal["PENDING", "APPROVED", "REJECTED"]
    source: Literal["SANDBOX_SYNTHETIC"] = SANDBOX_SOURCE
    fixture_only: Literal[True] = True


@dataclass(frozen=True, slots=True)
class SyntheticActor:
    tenant_id: str
    family_id: str
    actor_id: str
    role: str


def create_app(database_path: Path) -> FastAPI:
    app = FastAPI(title="Xiao Ju Deng question sandbox")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:4173", "http://127.0.0.1:4192"],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    initialise(database_path)

    @app.get("/health")
    def health() -> dict[str, object]:
        return {"status": "ok", "source": SANDBOX_SOURCE, "fixture_only": True}

    @app.get(
        "/sandbox/live/sessions/{session_ref}/questions",
        response_model=list[QuestionView],
    )
    def list_questions(
        session_ref: str,
        response: Response,
        actor: Annotated[SyntheticActor, Depends(actor_headers())],
    ) -> list[QuestionView]:
        response.headers["Cache-Control"] = "no-store"
        require_role(actor, {"ADULT_VIEWER", "HUMAN_MODERATOR"})
        with connect(database_path) as database:
            if actor.role == "HUMAN_MODERATOR":
                rows = database.execute(
                    """
                    SELECT question_ref, session_ref, text, status, actor_id
                    FROM live_questions
                    WHERE session_ref = ? AND tenant_id = ? AND family_id = ?
                    ORDER BY created_at ASC
                    """,
                    (session_ref, actor.tenant_id, actor.family_id),
                ).fetchall()
            else:
                rows = database.execute(
                    """
                    SELECT question_ref, session_ref, text, status, actor_id
                    FROM live_questions
                    WHERE session_ref = ? AND tenant_id = ? AND family_id = ?
                      AND (status = 'APPROVED' OR actor_id = ?)
                    ORDER BY created_at ASC
                    """,
                    (session_ref, actor.tenant_id, actor.family_id, actor.actor_id),
                ).fetchall()
        return [QuestionView(**dict(row)) for row in rows]

    @app.post(
        "/sandbox/live/sessions/{session_ref}/questions",
        response_model=QuestionView,
        status_code=202,
    )
    def submit_question(
        session_ref: str,
        request: SubmitQuestion,
        actor: Annotated[SyntheticActor, Depends(actor_headers())],
    ) -> QuestionView:
        require_role(actor, {"ADULT_VIEWER"})
        text = request.text.strip()
        with connect(database_path) as database:
            prior = database.execute(
                "SELECT question_ref, session_ref, text, status, actor_id "
                "FROM live_questions WHERE idempotency_key = ?",
                (request.idempotency_key,),
            ).fetchone()
            if prior is not None:
                if prior["question_ref"] != request.question_ref or prior["text"] != text:
                    raise HTTPException(status_code=409, detail="idempotency key conflict")
                return QuestionView(**dict(prior))
            try:
                database.execute(
                    """
                    INSERT INTO live_questions (
                        question_ref, session_ref, tenant_id, family_id, actor_id,
                        text, status, idempotency_key, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?, ?)
                    """,
                    (
                        request.question_ref,
                        session_ref,
                        actor.tenant_id,
                        actor.family_id,
                        actor.actor_id,
                        text,
                        request.idempotency_key,
                        now_iso(),
                    ),
                )
                database.commit()
            except sqlite3.IntegrityError as exc:
                raise HTTPException(status_code=409, detail="question reference conflict") from exc
        return QuestionView(
            question_ref=request.question_ref,
            session_ref=session_ref,
            text=text,
            status="PENDING",
        )

    @app.post(
        "/sandbox/moderation/questions/{question_ref}/decision",
        response_model=QuestionView,
    )
    def review_question(
        question_ref: str,
        request: ReviewQuestion,
        actor: Annotated[SyntheticActor, Depends(actor_headers())],
    ) -> QuestionView:
        require_role(actor, {"HUMAN_MODERATOR"})
        with connect(database_path) as database:
            row = database.execute(
                "SELECT * FROM live_questions WHERE question_ref = ?",
                (question_ref,),
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="question not found")
            require_scope(actor, row["tenant_id"], row["family_id"])
            prior = database.execute(
                "SELECT action, question_ref FROM moderation_decisions WHERE decision_key = ?",
                (request.decision_key,),
            ).fetchone()
            if prior is not None:
                if prior["action"] != request.action or prior["question_ref"] != question_ref:
                    raise HTTPException(status_code=409, detail="decision key conflict")
                current = database.execute(
                    "SELECT question_ref, session_ref, text, status, actor_id "
                    "FROM live_questions WHERE question_ref = ?",
                    (question_ref,),
                ).fetchone()
                return QuestionView(**dict(current))
            if row["status"] != "PENDING":
                raise HTTPException(status_code=409, detail="question already reviewed")
            if request.action == "EDIT" and not (request.edited_text or "").strip():
                raise HTTPException(status_code=422, detail="edited text is required")
            next_text = (request.edited_text or row["text"]).strip()
            next_status = "REJECTED" if request.action == "REJECT" else "APPROVED"
            database.execute(
                "UPDATE live_questions SET text = ?, status = ? WHERE question_ref = ?",
                (next_text, next_status, question_ref),
            )
            database.execute(
                """
                INSERT INTO moderation_decisions (
                    decision_key, question_ref, tenant_id, family_id, moderator_id,
                    action, reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request.decision_key,
                    question_ref,
                    actor.tenant_id,
                    actor.family_id,
                    actor.actor_id,
                    request.action,
                    request.reason.strip(),
                    now_iso(),
                ),
            )
            database.commit()
        return QuestionView(
            question_ref=question_ref,
            session_ref=row["session_ref"],
            text=next_text,
            status=next_status,
        )

    return app


def actor_headers():
    def dependency(
        x_sandbox_source: Annotated[str | None, Header()] = None,
        x_fixture_only: Annotated[str | None, Header()] = None,
        x_tenant_id: Annotated[str | None, Header()] = None,
        x_family_id: Annotated[str | None, Header()] = None,
        x_actor_id: Annotated[str | None, Header()] = None,
        x_actor_role: Annotated[str | None, Header()] = None,
    ) -> SyntheticActor:
        values = (x_tenant_id, x_family_id, x_actor_id, x_actor_role)
        if x_sandbox_source != SANDBOX_SOURCE or x_fixture_only != "true" or not all(values):
            raise HTTPException(status_code=401, detail="explicit synthetic actor required")
        if not all(
            str(value).startswith(("tenant.synthetic", "family.synthetic", "actor.synthetic"))
            for value in values[:3]
        ):
            raise HTTPException(status_code=403, detail="non-synthetic scope denied")
        return SyntheticActor(
            tenant_id=str(x_tenant_id),
            family_id=str(x_family_id),
            actor_id=str(x_actor_id),
            role=str(x_actor_role),
        )

    return dependency


def require_role(actor: SyntheticActor, allowed: set[str]) -> None:
    if actor.role not in allowed:
        raise HTTPException(status_code=403, detail="actor role denied")


def require_scope(actor: SyntheticActor, tenant_id: str, family_id: str) -> None:
    if actor.tenant_id != tenant_id or actor.family_id != family_id:
        raise HTTPException(status_code=403, detail="cross-scope access denied")


def connect(database_path: Path) -> sqlite3.Connection:
    database = sqlite3.connect(database_path)
    database.row_factory = sqlite3.Row
    return database


def initialise(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(database_path) as database:
        database.executescript(
            """
            CREATE TABLE IF NOT EXISTS live_questions (
                question_ref TEXT PRIMARY KEY,
                session_ref TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                family_id TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                text TEXT NOT NULL,
                status TEXT NOT NULL,
                idempotency_key TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS moderation_decisions (
                decision_key TEXT PRIMARY KEY,
                question_ref TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                family_id TEXT NOT NULL,
                moderator_id TEXT NOT NULL,
                action TEXT NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--port", type=int, default=55200)
    args = parser.parse_args()
    if not args.serve:
        raise SystemExit("use --serve")
    uvicorn.run(create_app(args.database), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
