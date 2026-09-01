"""Persistent synthetic replay and deletion HTTP sandbox.

The service is intentionally isolated from ``family_api`` and production
storage. It serves only a local synthetic media file, while preserving the
important product invariant: after deletion, every old replay capability is
immediately invalid and remains invalid after process restart.
"""

from __future__ import annotations

import argparse
import json
import secrets
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from poc.standalone_live_moderation_sandbox.question_api import (
    SANDBOX_SOURCE,
    SyntheticActor,
    actor_headers,
    require_role,
    require_scope,
)

SESSION_REF = "media.synthetic.1"
LINEAGE_REFS = (
    "asset.source",
    "asset.transcode",
    "asset.transcript",
    "asset.chapters",
    "asset.cache",
    "asset.provider",
)


class DeleteReplay(BaseModel):
    deletion_ref: str = Field(min_length=3, max_length=120)
    idempotency_key: str = Field(min_length=3, max_length=120)
    reason: str = Field(min_length=2, max_length=240)


class ReplayView(BaseModel):
    session_ref: str
    state: str
    playback_url: str | None
    source: str = SANDBOX_SOURCE
    fixture_only: bool = True


class DeletionView(BaseModel):
    deletion_ref: str
    session_ref: str
    affected_refs: list[str]
    state: str = "DELETED"
    source: str = SANDBOX_SOURCE
    fixture_only: bool = True


def create_app(database_path: Path, media_path: Path) -> FastAPI:
    app = FastAPI(title="Xiao Ju Deng replay deletion sandbox")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:4173", "http://127.0.0.1:4193"],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    initialise(database_path, media_path)

    @app.get("/health")
    def health() -> dict[str, object]:
        return {"status": "ok", "source": SANDBOX_SOURCE, "fixture_only": True}

    @app.get("/sandbox/replays/{session_ref}", response_model=ReplayView)
    def get_replay(
        session_ref: str,
        request: Request,
        response: Response,
        actor: Annotated[SyntheticActor, Depends(actor_headers())],
    ) -> ReplayView:
        require_role(actor, {"ADULT_VIEWER"})
        response.headers["Cache-Control"] = "no-store"
        with connect(database_path) as database:
            row = database.execute(
                "SELECT * FROM replay_assets WHERE session_ref = ?",
                (session_ref,),
            ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="replay not found")
        require_scope(actor, row["tenant_id"], row["family_id"])
        if row["state"] != "AVAILABLE":
            return ReplayView(session_ref=session_ref, state="DELETED", playback_url=None)
        media_url = str(request.url_for("play_replay", session_ref=session_ref)).replace(
            "http://testserver", str(request.base_url).rstrip("/")
        )
        return ReplayView(
            session_ref=session_ref,
            state="AVAILABLE",
            playback_url=f"{media_url}?capability={row['capability']}",
        )

    @app.get("/sandbox/replays/{session_ref}/media", name="play_replay")
    def play_replay(session_ref: str, capability: Annotated[str, Query()]) -> FileResponse:
        with connect(database_path) as database:
            row = database.execute(
                "SELECT * FROM replay_assets WHERE session_ref = ?",
                (session_ref,),
            ).fetchone()
        if row is None or not secrets.compare_digest(row["capability"], capability):
            raise HTTPException(status_code=403, detail="replay capability denied")
        if row["state"] != "AVAILABLE":
            raise HTTPException(status_code=410, detail="replay deleted")
        path = Path(row["media_path"])
        if not path.is_file():
            raise HTTPException(status_code=503, detail="replay media unavailable")
        return FileResponse(path, media_type="video/mp4", headers={"Cache-Control": "no-store"})

    @app.post("/sandbox/replays/{session_ref}/delete", response_model=DeletionView)
    def delete_replay(
        session_ref: str,
        command: DeleteReplay,
        actor: Annotated[SyntheticActor, Depends(actor_headers())],
    ) -> DeletionView:
        require_role(actor, {"ADULT_VIEWER"})
        with connect(database_path) as database:
            asset = database.execute(
                "SELECT * FROM replay_assets WHERE session_ref = ?",
                (session_ref,),
            ).fetchone()
            if asset is None:
                raise HTTPException(status_code=404, detail="replay not found")
            require_scope(actor, asset["tenant_id"], asset["family_id"])
            previous = database.execute(
                "SELECT * FROM replay_deletions WHERE idempotency_key = ?",
                (command.idempotency_key,),
            ).fetchone()
            if previous is not None:
                if previous["session_ref"] != session_ref:
                    raise HTTPException(status_code=409, detail="deletion key conflict")
                return deletion_view(previous)
            database.execute(
                "UPDATE replay_assets SET state = 'DELETED' WHERE session_ref = ?",
                (session_ref,),
            )
            database.execute(
                """
                INSERT INTO replay_deletions (
                    deletion_ref, session_ref, tenant_id, family_id,
                    affected_refs, reason, idempotency_key, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    command.deletion_ref,
                    session_ref,
                    actor.tenant_id,
                    actor.family_id,
                    json.dumps(LINEAGE_REFS),
                    command.reason.strip(),
                    command.idempotency_key,
                    datetime.now(UTC).isoformat(),
                ),
            )
            database.commit()
            receipt = database.execute(
                "SELECT * FROM replay_deletions WHERE idempotency_key = ?",
                (command.idempotency_key,),
            ).fetchone()
        return deletion_view(receipt)

    return app


def deletion_view(row: sqlite3.Row) -> DeletionView:
    return DeletionView(
        deletion_ref=row["deletion_ref"],
        session_ref=row["session_ref"],
        affected_refs=json.loads(row["affected_refs"]),
    )


def connect(database_path: Path) -> sqlite3.Connection:
    database = sqlite3.connect(database_path)
    database.row_factory = sqlite3.Row
    return database


def initialise(database_path: Path, media_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(database_path) as database:
        database.executescript(
            """
            CREATE TABLE IF NOT EXISTS replay_assets (
                session_ref TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                family_id TEXT NOT NULL,
                media_path TEXT NOT NULL,
                capability TEXT NOT NULL UNIQUE,
                state TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS replay_deletions (
                deletion_ref TEXT PRIMARY KEY,
                session_ref TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                family_id TEXT NOT NULL,
                affected_refs TEXT NOT NULL,
                reason TEXT NOT NULL,
                idempotency_key TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );
            """
        )
        database.execute(
            """
            INSERT OR IGNORE INTO replay_assets (
                session_ref, tenant_id, family_id, media_path, capability, state
            ) VALUES (?, 'tenant.synthetic.alpha', 'family.synthetic.alpha', ?, ?, 'AVAILABLE')
            """,
            (SESSION_REF, str(media_path.resolve()), secrets.token_urlsafe(24)),
        )
        database.commit()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--media", type=Path, required=True)
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    if not args.serve:
        raise SystemExit("use --serve")
    uvicorn.run(create_app(args.database, args.media), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
