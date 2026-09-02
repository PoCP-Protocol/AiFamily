"""Synthetic replay knowledge and collection HTTP sandbox.

AI-created chapters and knowledge cards remain drafts until a human reviewer
approves or edits them. Replay existence, approval, and deletion come from
injected canonical projections; this module does not create AI or deletion
ledgers. A locally persisted tombstone is only an irreversible deletion cache
that prevents derived knowledge from reappearing after restart.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
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

KnowledgeState = Literal["DRAFT", "APPROVED", "REJECTED"]
ReviewAction = Literal["APPROVE", "EDIT", "REJECT"]


@dataclass(frozen=True, slots=True)
class ReplayProjection:
    replay_ref: str
    tenant_id: str
    family_id: str
    review_state: str


class ReplayCatalogProjection(Protocol):
    def get(self, replay_ref: str) -> ReplayProjection | None: ...


class CanonicalDeletionProjection(Protocol):
    def is_deleted(self, replay_ref: str, tenant_id: str, family_id: str) -> bool: ...


class SyntheticReplayDatabaseProjection:
    """Read the sandbox replay database as an external, read-only projection."""

    def __init__(self, replay_database_path: Path) -> None:
        self.replay_database_path = replay_database_path

    def get(self, replay_ref: str) -> ReplayProjection | None:
        row = self._read(replay_ref)
        if row is None:
            return None
        return ReplayProjection(
            replay_ref=row["session_ref"],
            tenant_id=row["tenant_id"],
            family_id=row["family_id"],
            review_state="APPROVED",
        )

    def is_deleted(self, replay_ref: str, tenant_id: str, family_id: str) -> bool:
        row = self._read(replay_ref)
        if row is None:
            return True
        if row["tenant_id"] != tenant_id or row["family_id"] != family_id:
            return True
        return row["state"] != "AVAILABLE"

    def _read(self, replay_ref: str) -> sqlite3.Row | None:
        if not self.replay_database_path.is_file():
            raise RuntimeError("synthetic replay projection unavailable")
        with sqlite3.connect(self.replay_database_path) as database:
            database.row_factory = sqlite3.Row
            return database.execute(
                """
                SELECT session_ref, tenant_id, family_id, state
                FROM replay_assets WHERE session_ref = ?
                """,
                (replay_ref,),
            ).fetchone()


class ChapterInput(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=2_000)


class CreateKnowledgeDraft(BaseModel):
    knowledge_ref: str = Field(min_length=3, max_length=120)
    idempotency_key: str = Field(min_length=3, max_length=120)
    card_title: str = Field(min_length=1, max_length=160)
    card_body: str = Field(min_length=1, max_length=4_000)
    chapters: list[ChapterInput] = Field(min_length=1, max_length=30)


class ReviewKnowledge(BaseModel):
    decision_key: str = Field(min_length=3, max_length=120)
    action: ReviewAction
    reason: str = Field(min_length=1, max_length=500)
    edited_card_title: str | None = Field(default=None, max_length=160)
    edited_card_body: str | None = Field(default=None, max_length=4_000)
    edited_chapters: list[ChapterInput] | None = Field(default=None, max_length=30)


class CreateBookmark(BaseModel):
    bookmark_ref: str = Field(min_length=3, max_length=120)
    idempotency_key: str = Field(min_length=3, max_length=120)


class KnowledgeView(BaseModel):
    knowledge_ref: str
    replay_ref: str
    card_title: str
    card_body: str
    chapters: list[ChapterInput]
    state: KnowledgeState
    created_at: str
    updated_at: str
    reviewed_by: str | None = None
    review_reason: str | None = None
    source: Literal["SANDBOX_SYNTHETIC"] = SANDBOX_SOURCE
    fixture_only: Literal[True] = True
    external_effect: Literal[False] = False
    fact_write: Literal[False] = False


class BookmarkView(BaseModel):
    bookmark_ref: str
    knowledge_ref: str
    replay_ref: str
    actor_id: str
    created_at: str
    source: Literal["SANDBOX_SYNTHETIC"] = SANDBOX_SOURCE
    fixture_only: Literal[True] = True
    external_effect: Literal[False] = False


def create_app(
    database_path: Path,
    *,
    replay_catalog: ReplayCatalogProjection,
    deletion_projection: CanonicalDeletionProjection,
) -> FastAPI:
    initialise(database_path)
    app = FastAPI(title="Xiao Ju Deng replay knowledge sandbox")
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"https?://(?:localhost|127\.0\.0\.1)(?::\d+)?",
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "source": SANDBOX_SOURCE,
            "fixture_only": True,
            "external_effect": False,
        }

    @app.post(
        "/sandbox/replay-knowledge/replays/{replay_ref}/drafts",
        response_model=KnowledgeView,
        status_code=202,
    )
    def create_draft(
        replay_ref: str,
        request: CreateKnowledgeDraft,
        actor: Annotated[SyntheticActor, Depends(actor_headers())],
    ) -> KnowledgeView:
        require_role(actor, {"AI_OPERATOR"})
        replay = require_available_replay(
            database_path, replay_catalog, deletion_projection, replay_ref, actor
        )
        card_title = require_text(request.card_title, "card title is required")
        card_body = require_text(request.card_body, "card body is required")
        chapters = normalise_chapters(request.chapters)
        with connect(database_path) as database:
            prior = database.execute(
                "SELECT * FROM replay_knowledge WHERE idempotency_key = ?",
                (request.idempotency_key,),
            ).fetchone()
            if prior is not None:
                if not same_draft(
                    prior,
                    request.knowledge_ref,
                    replay_ref,
                    actor,
                    card_title,
                    card_body,
                    chapters,
                ):
                    raise HTTPException(status_code=409, detail="draft idempotency conflict")
                return knowledge_view(prior)
            timestamp = now_iso()
            try:
                database.execute(
                    """
                    INSERT INTO replay_knowledge (
                        knowledge_ref, replay_ref, tenant_id, family_id, generated_by,
                        card_title, card_body, chapters_json, state, idempotency_key,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'DRAFT', ?, ?, ?)
                    """,
                    (
                        request.knowledge_ref,
                        replay.replay_ref,
                        actor.tenant_id,
                        actor.family_id,
                        actor.actor_id,
                        card_title,
                        card_body,
                        encode_chapters(chapters),
                        request.idempotency_key,
                        timestamp,
                        timestamp,
                    ),
                )
                database.commit()
            except sqlite3.IntegrityError as exc:
                raise HTTPException(status_code=409, detail="knowledge reference conflict") from exc
            row = require_knowledge(database, request.knowledge_ref)
        return knowledge_view(row)

    @app.post(
        "/sandbox/replay-knowledge/items/{knowledge_ref}/review",
        response_model=KnowledgeView,
    )
    def review_draft(
        knowledge_ref: str,
        request: ReviewKnowledge,
        actor: Annotated[SyntheticActor, Depends(actor_headers())],
    ) -> KnowledgeView:
        require_role(actor, {"HUMAN_REVIEWER"})
        reason = require_text(request.reason, "review reason is required")
        with connect(database_path) as database:
            row = require_knowledge(database, knowledge_ref)
            require_scope(actor, row["tenant_id"], row["family_id"])
        require_available_replay(
            database_path,
            replay_catalog,
            deletion_projection,
            row["replay_ref"],
            actor,
        )
        with connect(database_path) as database:
            row = require_knowledge(database, knowledge_ref)
            prior = database.execute(
                "SELECT * FROM knowledge_reviews WHERE decision_key = ?",
                (request.decision_key,),
            ).fetchone()
            fingerprint = review_fingerprint(request, knowledge_ref, actor, reason)
            if prior is not None:
                if prior["request_fingerprint"] != fingerprint:
                    raise HTTPException(status_code=409, detail="decision key conflict")
                return knowledge_view(row)
            if row["state"] != "DRAFT":
                raise HTTPException(status_code=409, detail="knowledge already reviewed")

            title, body, chapters = reviewed_content(row, request)
            next_state: KnowledgeState = "REJECTED" if request.action == "REJECT" else "APPROVED"
            timestamp = now_iso()
            database.execute(
                """
                UPDATE replay_knowledge
                SET card_title = ?, card_body = ?, chapters_json = ?, state = ?,
                    reviewed_by = ?, review_reason = ?, updated_at = ?
                WHERE knowledge_ref = ? AND state = 'DRAFT'
                """,
                (
                    title,
                    body,
                    encode_chapters(chapters),
                    next_state,
                    actor.actor_id,
                    reason,
                    timestamp,
                    knowledge_ref,
                ),
            )
            database.execute(
                """
                INSERT INTO knowledge_reviews (
                    decision_key, knowledge_ref, request_fingerprint, action,
                    reviewer_id, reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request.decision_key,
                    knowledge_ref,
                    fingerprint,
                    request.action,
                    actor.actor_id,
                    reason,
                    timestamp,
                ),
            )
            database.commit()
            current = require_knowledge(database, knowledge_ref)
        return knowledge_view(current)

    @app.get(
        "/sandbox/replay-knowledge/replays/{replay_ref}/knowledge",
        response_model=list[KnowledgeView],
    )
    def approved_knowledge(
        replay_ref: str,
        response: Response,
        actor: Annotated[SyntheticActor, Depends(actor_headers())],
    ) -> list[KnowledgeView]:
        require_role(actor, {"ADULT_VIEWER"})
        response.headers["Cache-Control"] = "no-store"
        require_available_replay(
            database_path, replay_catalog, deletion_projection, replay_ref, actor
        )
        with connect(database_path) as database:
            rows = database.execute(
                """
                SELECT * FROM replay_knowledge
                WHERE replay_ref = ? AND tenant_id = ? AND family_id = ? AND state = 'APPROVED'
                ORDER BY created_at ASC
                """,
                (replay_ref, actor.tenant_id, actor.family_id),
            ).fetchall()
        return [knowledge_view(row) for row in rows]

    @app.post(
        "/sandbox/replay-knowledge/items/{knowledge_ref}/bookmarks",
        response_model=BookmarkView,
        status_code=201,
    )
    def create_bookmark(
        knowledge_ref: str,
        request: CreateBookmark,
        actor: Annotated[SyntheticActor, Depends(actor_headers())],
    ) -> BookmarkView:
        require_role(actor, {"ADULT_VIEWER"})
        with connect(database_path) as database:
            item = require_knowledge(database, knowledge_ref)
            require_scope(actor, item["tenant_id"], item["family_id"])
        require_available_replay(
            database_path,
            replay_catalog,
            deletion_projection,
            item["replay_ref"],
            actor,
        )
        if item["state"] != "APPROVED":
            raise HTTPException(status_code=404, detail="approved knowledge not found")
        with connect(database_path) as database:
            prior = database.execute(
                "SELECT * FROM knowledge_bookmarks WHERE idempotency_key = ?",
                (request.idempotency_key,),
            ).fetchone()
            if prior is not None:
                if not same_bookmark(prior, request.bookmark_ref, knowledge_ref, actor):
                    raise HTTPException(status_code=409, detail="bookmark idempotency conflict")
                return bookmark_view(prior)
            try:
                database.execute(
                    """
                    INSERT INTO knowledge_bookmarks (
                        bookmark_ref, knowledge_ref, replay_ref, tenant_id, family_id,
                        actor_id, idempotency_key, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        request.bookmark_ref,
                        knowledge_ref,
                        item["replay_ref"],
                        actor.tenant_id,
                        actor.family_id,
                        actor.actor_id,
                        request.idempotency_key,
                        now_iso(),
                    ),
                )
                database.commit()
            except sqlite3.IntegrityError as exc:
                raise HTTPException(status_code=409, detail="bookmark conflict") from exc
            bookmark = database.execute(
                "SELECT * FROM knowledge_bookmarks WHERE bookmark_ref = ?",
                (request.bookmark_ref,),
            ).fetchone()
        return bookmark_view(bookmark)

    @app.get("/sandbox/replay-knowledge/bookmarks", response_model=list[BookmarkView])
    def list_bookmarks(
        response: Response,
        actor: Annotated[SyntheticActor, Depends(actor_headers())],
    ) -> list[BookmarkView]:
        require_role(actor, {"ADULT_VIEWER"})
        response.headers["Cache-Control"] = "no-store"
        with connect(database_path) as database:
            rows = database.execute(
                """
                SELECT * FROM knowledge_bookmarks
                WHERE tenant_id = ? AND family_id = ? AND actor_id = ?
                ORDER BY created_at ASC
                """,
                (actor.tenant_id, actor.family_id, actor.actor_id),
            ).fetchall()
        visible = []
        for row in rows:
            if replay_is_available(
                database_path,
                replay_catalog,
                deletion_projection,
                row["replay_ref"],
                actor,
            ):
                visible.append(bookmark_view(row))
        return visible

    return app


def require_available_replay(
    database_path: Path,
    replay_catalog: ReplayCatalogProjection,
    deletion_projection: CanonicalDeletionProjection,
    replay_ref: str,
    actor: SyntheticActor,
) -> ReplayProjection:
    try:
        replay = replay_catalog.get(replay_ref)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="replay projection unavailable") from exc
    if replay is None:
        raise HTTPException(status_code=404, detail="replay not found")
    require_scope(actor, replay.tenant_id, replay.family_id)
    if replay_deleted(database_path, deletion_projection, replay):
        raise HTTPException(status_code=410, detail="replay deleted")
    if replay.review_state != "APPROVED":
        raise HTTPException(status_code=404, detail="approved replay not found")
    return replay


def replay_is_available(
    database_path: Path,
    replay_catalog: ReplayCatalogProjection,
    deletion_projection: CanonicalDeletionProjection,
    replay_ref: str,
    actor: SyntheticActor,
) -> bool:
    try:
        require_available_replay(
            database_path, replay_catalog, deletion_projection, replay_ref, actor
        )
    except HTTPException as exc:
        if exc.status_code in {404, 410}:
            return False
        raise
    return True


def replay_deleted(
    database_path: Path,
    deletion_projection: CanonicalDeletionProjection,
    replay: ReplayProjection,
) -> bool:
    with connect(database_path) as database:
        tombstone = database.execute(
            "SELECT 1 FROM replay_deletion_tombstones WHERE replay_ref = ?",
            (replay.replay_ref,),
        ).fetchone()
        if tombstone is not None:
            return True
    try:
        deleted = deletion_projection.is_deleted(
            replay.replay_ref, replay.tenant_id, replay.family_id
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="deletion projection unavailable") from exc
    if not deleted:
        return False
    with connect(database_path) as database:
        database.execute(
            """
            INSERT OR IGNORE INTO replay_deletion_tombstones (
                replay_ref, tenant_id, family_id, observed_at
            ) VALUES (?, ?, ?, ?)
            """,
            (replay.replay_ref, replay.tenant_id, replay.family_id, now_iso()),
        )
        database.commit()
    return True


def reviewed_content(
    row: sqlite3.Row, request: ReviewKnowledge
) -> tuple[str, str, list[ChapterInput]]:
    current_chapters = decode_chapters(row["chapters_json"])
    if request.action != "EDIT":
        return row["card_title"], row["card_body"], current_chapters
    if not any(
        value is not None
        for value in (
            request.edited_card_title,
            request.edited_card_body,
            request.edited_chapters,
        )
    ):
        raise HTTPException(status_code=422, detail="edited content is required")
    title = require_text(
        request.edited_card_title if request.edited_card_title is not None else row["card_title"],
        "edited card title is required",
    )
    body = require_text(
        request.edited_card_body if request.edited_card_body is not None else row["card_body"],
        "edited card body is required",
    )
    chapters = (
        normalise_chapters(request.edited_chapters)
        if request.edited_chapters is not None
        else current_chapters
    )
    return title, body, chapters


def review_fingerprint(
    request: ReviewKnowledge,
    knowledge_ref: str,
    actor: SyntheticActor,
    reason: str,
) -> str:
    content = {
        "knowledge_ref": knowledge_ref,
        "tenant_id": actor.tenant_id,
        "family_id": actor.family_id,
        "actor_id": actor.actor_id,
        "action": request.action,
        "reason": reason,
        "edited_card_title": request.edited_card_title,
        "edited_card_body": request.edited_card_body,
        "edited_chapters": [item.model_dump() for item in request.edited_chapters or []],
    }
    return json.dumps(content, ensure_ascii=False, sort_keys=True)


def same_draft(
    row: sqlite3.Row,
    knowledge_ref: str,
    replay_ref: str,
    actor: SyntheticActor,
    title: str,
    body: str,
    chapters: list[ChapterInput],
) -> bool:
    return (
        row["knowledge_ref"] == knowledge_ref
        and row["replay_ref"] == replay_ref
        and row["tenant_id"] == actor.tenant_id
        and row["family_id"] == actor.family_id
        and row["generated_by"] == actor.actor_id
        and row["card_title"] == title
        and row["card_body"] == body
        and row["chapters_json"] == encode_chapters(chapters)
    )


def same_bookmark(
    row: sqlite3.Row,
    bookmark_ref: str,
    knowledge_ref: str,
    actor: SyntheticActor,
) -> bool:
    return (
        row["bookmark_ref"] == bookmark_ref
        and row["knowledge_ref"] == knowledge_ref
        and row["tenant_id"] == actor.tenant_id
        and row["family_id"] == actor.family_id
        and row["actor_id"] == actor.actor_id
    )


def knowledge_view(row: sqlite3.Row) -> KnowledgeView:
    return KnowledgeView(
        knowledge_ref=row["knowledge_ref"],
        replay_ref=row["replay_ref"],
        card_title=row["card_title"],
        card_body=row["card_body"],
        chapters=decode_chapters(row["chapters_json"]),
        state=row["state"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        reviewed_by=row["reviewed_by"],
        review_reason=row["review_reason"],
    )


def bookmark_view(row: sqlite3.Row) -> BookmarkView:
    return BookmarkView(
        bookmark_ref=row["bookmark_ref"],
        knowledge_ref=row["knowledge_ref"],
        replay_ref=row["replay_ref"],
        actor_id=row["actor_id"],
        created_at=row["created_at"],
    )


def normalise_chapters(chapters: list[ChapterInput]) -> list[ChapterInput]:
    normalised = [
        ChapterInput(
            title=require_text(chapter.title, "chapter title is required"),
            body=require_text(chapter.body, "chapter body is required"),
        )
        for chapter in chapters
    ]
    if not normalised:
        raise HTTPException(status_code=422, detail="at least one chapter is required")
    return normalised


def encode_chapters(chapters: list[ChapterInput]) -> str:
    return json.dumps([chapter.model_dump() for chapter in chapters], ensure_ascii=False)


def decode_chapters(value: str) -> list[ChapterInput]:
    return [ChapterInput(**chapter) for chapter in json.loads(value)]


def require_knowledge(database: sqlite3.Connection, knowledge_ref: str) -> sqlite3.Row:
    row = database.execute(
        "SELECT * FROM replay_knowledge WHERE knowledge_ref = ?", (knowledge_ref,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="knowledge not found")
    return row


def require_text(value: str, detail: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise HTTPException(status_code=422, detail=detail)
    return stripped


def connect(database_path: Path) -> sqlite3.Connection:
    database = sqlite3.connect(database_path)
    database.row_factory = sqlite3.Row
    return database


def initialise(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(database_path) as database:
        database.executescript(
            """
            CREATE TABLE IF NOT EXISTS replay_knowledge (
                knowledge_ref TEXT PRIMARY KEY,
                replay_ref TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                family_id TEXT NOT NULL,
                generated_by TEXT NOT NULL,
                card_title TEXT NOT NULL,
                card_body TEXT NOT NULL,
                chapters_json TEXT NOT NULL,
                state TEXT NOT NULL,
                idempotency_key TEXT NOT NULL UNIQUE,
                reviewed_by TEXT,
                review_reason TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS knowledge_reviews (
                decision_key TEXT PRIMARY KEY,
                knowledge_ref TEXT NOT NULL,
                request_fingerprint TEXT NOT NULL,
                action TEXT NOT NULL,
                reviewer_id TEXT NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS knowledge_bookmarks (
                bookmark_ref TEXT PRIMARY KEY,
                knowledge_ref TEXT NOT NULL,
                replay_ref TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                family_id TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                idempotency_key TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                UNIQUE (knowledge_ref, tenant_id, family_id, actor_id)
            );
            CREATE TABLE IF NOT EXISTS replay_deletion_tombstones (
                replay_ref TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                family_id TEXT NOT NULL,
                observed_at TEXT NOT NULL
            );
            """
        )


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def seed_approved_fixture(database_path: Path, replay_ref: str) -> None:
    """Seed a replay note that carries explicit synthetic human-review evidence."""

    initialise(database_path)
    timestamp = now_iso()
    chapters = [
        ChapterInput(title="先听懂情绪", body="先复述听到的感受，不急着给答案。"),
        ChapterInput(title="再确认需要", body="用一个开放问题确认对方真正需要什么。"),
        ChapterInput(title="最后约定一步", body="只约定一个今天能完成的小行动。"),
    ]
    with connect(database_path) as database:
        database.execute(
            """
            INSERT OR IGNORE INTO replay_knowledge (
                knowledge_ref, replay_ref, tenant_id, family_id, generated_by,
                card_title, card_body, chapters_json, state, idempotency_key,
                reviewed_by, review_reason, created_at, updated_at
            ) VALUES (?, ?, 'tenant.synthetic.alpha', 'family.synthetic.alpha',
                      'actor.synthetic.ai', ?, ?, ?, 'APPROVED', ?,
                      'actor.synthetic.reviewer', ?, ?, ?)
            """,
            (
                "knowledge.synthetic.replay.summary",
                replay_ref,
                "把冲突变成一次共同练习",
                "人工复核后的回放要点：先听懂，再确认，最后只约定一个小行动。",
                encode_chapters(chapters),
                "seed.synthetic.replay.summary",
                "人工编辑并确认合成章节适合成年家庭成员阅读",
                timestamp,
                timestamp,
            ),
        )
        database.execute(
            """
            INSERT OR IGNORE INTO knowledge_reviews (
                decision_key, knowledge_ref, request_fingerprint, action,
                reviewer_id, reason, created_at
            ) VALUES (?, ?, ?, 'EDIT', 'actor.synthetic.reviewer', ?, ?)
            """,
            (
                "seed-review.synthetic.replay.summary",
                "knowledge.synthetic.replay.summary",
                "SANDBOX_SYNTHETIC:human-edited-fixture",
                "人工编辑并确认合成章节适合成年家庭成员阅读",
                timestamp,
            ),
        )
        database.commit()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--replay-database", type=Path, required=True)
    parser.add_argument("--replay-ref", default="media.synthetic.1")
    parser.add_argument("--seed-approved-fixture", action="store_true")
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    if not args.serve:
        raise SystemExit("use --serve")
    if args.seed_approved_fixture:
        seed_approved_fixture(args.database, args.replay_ref)
    projection = SyntheticReplayDatabaseProjection(args.replay_database)
    uvicorn.run(
        create_app(
            args.database,
            replay_catalog=projection,
            deletion_projection=projection,
        ),
        host="127.0.0.1",
        port=args.port,
    )


if __name__ == "__main__":
    main()
