"""HTTP/SQLite facade for the disposable Xiao Ju Deng live AI sandbox."""

from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Literal

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from poc.standalone_live_ai_sandbox.draft_flow import (
    SANDBOX_SOURCE,
    AISandboxFlow,
    AISandboxStopped,
    DraftStatus,
    FakeModelGateway,
    HumanGateRejected,
    InMemoryHumanGateFixture,
    InMemoryProvenanceFixture,
    ReviewDecision,
    SyntheticTranscript,
)
from poc.standalone_live_ai_sandbox.multimodal_timeline import (
    MultimodalRejected,
    MultimodalTimelineDraft,
    MultimodalTimelinePipeline,
    OcrObservation,
    SpeechWindow,
    SyntheticMediaInput,
    TimelineCue,
    TranscriptSegment,
    VideoKeyframe,
)


class Actor(BaseModel):
    tenant_id: str
    family_id: str
    actor_id: str
    role: str


class GenerateRequest(BaseModel):
    session_ref: str
    transcript_ref: str
    transcript: str = Field(min_length=1, max_length=20_000)
    idempotency_key: str = Field(min_length=1, max_length=160)


class ReviewRequest(BaseModel):
    decision: Literal["APPROVE", "REJECT", "EDIT"]
    reason: str = Field(min_length=1, max_length=500)
    edited_text: str | None = Field(default=None, max_length=4_000)
    idempotency_key: str = Field(min_length=1, max_length=160)


class DraftView(BaseModel):
    draft_ref: str
    session_ref: str
    transcript_ref: str
    summary: str
    chapters: list[str]
    risk_flags: list[str]
    status: str
    provenance_ref: str
    draft_hash: str
    model: str
    model_version: str
    provider: str
    prompt_version: str
    source: Literal["SANDBOX_SYNTHETIC"] = SANDBOX_SOURCE
    fixture_only: Literal[True] = True
    external_effect: Literal[False] = False
    fact_write: Literal[False] = False
    audit_mode: Literal["SANDBOX_RECEIPT_ONLY"] = "SANDBOX_RECEIPT_ONLY"


class SpeechWindowInput(BaseModel):
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    confidence: float = Field(ge=0, le=1)


class TranscriptSegmentInput(SpeechWindowInput):
    text: str = Field(min_length=1, max_length=4_000)
    speaker_ref: str = Field(min_length=1, max_length=160)
    evidence_ref: str = Field(min_length=1, max_length=160)


class VideoKeyframeInput(BaseModel):
    at_ms: int = Field(ge=0)
    frame_ref: str = Field(min_length=1, max_length=160)
    scene_ref: str = Field(min_length=1, max_length=160)
    evidence_ref: str = Field(min_length=1, max_length=160)


class OcrObservationInput(BaseModel):
    frame_ref: str = Field(min_length=1, max_length=160)
    text: str = Field(min_length=1, max_length=4_000)
    confidence: float = Field(ge=0, le=1)
    evidence_ref: str = Field(min_length=1, max_length=160)


class MultimodalTimelineRequest(BaseModel):
    session_ref: str = Field(min_length=1, max_length=160)
    media_ref: str = Field(min_length=1, max_length=160)
    audio_ref: str = Field(min_length=1, max_length=160)
    video_ref: str = Field(min_length=1, max_length=160)
    duration_ms: int = Field(gt=0, le=14_400_000)
    speech_windows: list[SpeechWindowInput] = Field(min_length=1, max_length=2_000)
    transcript_segments: list[TranscriptSegmentInput] = Field(min_length=1, max_length=2_000)
    video_keyframes: list[VideoKeyframeInput] = Field(min_length=1, max_length=2_000)
    ocr_observations: list[OcrObservationInput] = Field(default_factory=list, max_length=4_000)
    contains_real_person: bool = False
    contains_biometric_data: bool = False
    idempotency_key: str = Field(min_length=1, max_length=160)


class TimelineCueView(BaseModel):
    start_ms: int
    end_ms: int
    speaker_ref: str
    transcript: str
    frame_ref: str | None
    scene_ref: str | None
    ocr_text: list[str]
    evidence_refs: list[str]


class MultimodalTimelineView(BaseModel):
    timeline_ref: str
    session_ref: str
    media_ref: str
    cues: list[TimelineCueView]
    evidence_digest: str
    modalities: list[str]
    risk_flags: list[str]
    status: Literal["DRAFT"] = "DRAFT"
    human_review_required: Literal[True] = True
    may_mutate_business_state: Literal[False] = False
    source: Literal["SANDBOX_SYNTHETIC"] = SANDBOX_SOURCE
    fixture_only: Literal[True] = True
    external_effect: Literal[False] = False


class StaticVad:
    def __init__(self, values: list[SpeechWindow]) -> None:
        self._values = values

    def detect(self, media: SyntheticMediaInput) -> list[SpeechWindow]:
        del media
        return self._values


class StaticAsr:
    def __init__(self, values: list[TranscriptSegment]) -> None:
        self._values = values

    def transcribe(
        self, media: SyntheticMediaInput, windows: list[SpeechWindow]
    ) -> list[TranscriptSegment]:
        del media, windows
        return self._values


class StaticFrames:
    def __init__(self, values: list[VideoKeyframe]) -> None:
        self._values = values

    def sample(self, media: SyntheticMediaInput) -> list[VideoKeyframe]:
        del media
        return self._values


class StaticOcr:
    def __init__(self, values: list[OcrObservation]) -> None:
        self._values = values

    def extract(
        self, media: SyntheticMediaInput, frames: list[VideoKeyframe]
    ) -> list[OcrObservation]:
        del media, frames
        return self._values


def actor_headers():
    def dependency(
        source: Annotated[str | None, Header(alias="X-Sandbox-Source")] = None,
        fixture_only: Annotated[str | None, Header(alias="X-Fixture-Only")] = None,
        tenant_id: Annotated[str | None, Header(alias="X-Tenant-Id")] = None,
        family_id: Annotated[str | None, Header(alias="X-Family-Id")] = None,
        actor_id: Annotated[str | None, Header(alias="X-Actor-Id")] = None,
        role: Annotated[str | None, Header(alias="X-Actor-Role")] = None,
    ) -> Actor:
        if source != SANDBOX_SOURCE or fixture_only != "true":
            raise HTTPException(status_code=403, detail="synthetic sandbox boundary required")
        if not all((tenant_id, family_id, actor_id, role)):
            raise HTTPException(status_code=401, detail="actor context required")
        return Actor(
            tenant_id=tenant_id,
            family_id=family_id,
            actor_id=actor_id,
            role=role,
        )

    return dependency


def create_app(database_path: Path) -> FastAPI:
    initialise(database_path)
    app = FastAPI(title="Xiao Ju Deng live AI sandbox")
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^http://(127\.0\.0\.1|localhost)(:\d+)?$",
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
        allow_credentials=False,
    )

    @app.get("/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "source": SANDBOX_SOURCE,
            "fixture_only": True,
            "external_effect": False,
        }

    @app.post("/sandbox/live-ai/drafts", response_model=DraftView)
    def generate_draft(
        request: GenerateRequest,
        response: Response,
        actor: Annotated[Actor, Depends(actor_headers())],
    ) -> DraftView:
        response.headers["Cache-Control"] = "no-store"
        require_role(actor, {"CREATOR", "AI_OPERATOR"})
        fingerprint = payload_fingerprint(request, actor)
        with connect(database_path) as database:
            replay = database.execute(
                "SELECT * FROM ai_drafts WHERE idempotency_key = ?",
                (request.idempotency_key,),
            ).fetchone()
            if replay is not None:
                if replay["request_fingerprint"] != fingerprint:
                    raise HTTPException(status_code=409, detail="idempotency conflict")
                return draft_view(replay)

        provenance = InMemoryProvenanceFixture()
        flow = AISandboxFlow(
            gateway=FakeModelGateway(),
            provenance=provenance,
            human_gate=InMemoryHumanGateFixture(audit=provenance),
        )
        transcript = SyntheticTranscript(
            tenant_id=actor.tenant_id,
            family_id=actor.family_id,
            session_ref=request.session_ref,
            transcript_ref=request.transcript_ref,
            text=request.transcript,
        )
        try:
            generated = flow.generate(transcript)
        except AISandboxStopped as exc:
            with connect(database_path) as database:
                database.execute(
                    "INSERT INTO ai_failure_receipts "
                    "(tenant_id, family_id, actor_id, transcript_ref, reason) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        actor.tenant_id,
                        actor.family_id,
                        actor.actor_id,
                        request.transcript_ref,
                        str(exc),
                    ),
                )
                database.commit()
            raise HTTPException(status_code=422, detail="AI generation stopped closed") from exc

        draft_ref = f"draft.synthetic.{generated.draft_hash[:16]}"
        generated = replace(generated, draft_ref=draft_ref)
        with connect(database_path) as database:
            database.execute(
                """
                INSERT INTO ai_drafts (
                    draft_ref, tenant_id, family_id, actor_id, session_ref, transcript_ref,
                    transcript, summary, chapters, risk_flags, status, provenance_ref,
                    draft_hash, model, model_version, provider, prompt_version,
                    idempotency_key, request_fingerprint
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    draft_ref,
                    actor.tenant_id,
                    actor.family_id,
                    actor.actor_id,
                    request.session_ref,
                    request.transcript_ref,
                    request.transcript,
                    generated.text,
                    json.dumps(generated.chapters, ensure_ascii=False),
                    json.dumps(generated.risk_flags, ensure_ascii=False),
                    generated.status.value,
                    generated.provenance_ref,
                    generated.draft_hash,
                    generated.model,
                    generated.model_version,
                    generated.provider,
                    generated.prompt_version,
                    request.idempotency_key,
                    fingerprint,
                ),
            )
            append_receipt(database, draft_ref, actor, "AI_DRAFT_CREATED", "synthetic transcript")
            database.commit()
            row = require_draft(database, draft_ref)
        return draft_view(row)

    @app.post(
        "/sandbox/live-ai/multimodal-timelines",
        response_model=MultimodalTimelineView,
    )
    def generate_multimodal_timeline(
        request: MultimodalTimelineRequest,
        response: Response,
        actor: Annotated[Actor, Depends(actor_headers())],
    ) -> MultimodalTimelineView:
        response.headers["Cache-Control"] = "no-store"
        require_role(actor, {"CREATOR", "AI_OPERATOR"})
        fingerprint = multimodal_fingerprint(request, actor)
        with connect(database_path) as database:
            replay = database.execute(
                "SELECT request_fingerprint, result_json FROM multimodal_timelines "
                "WHERE idempotency_key = ?",
                (request.idempotency_key,),
            ).fetchone()
            if replay is not None:
                if replay["request_fingerprint"] != fingerprint:
                    raise HTTPException(status_code=409, detail="idempotency conflict")
                return MultimodalTimelineView.model_validate_json(replay["result_json"])

        pipeline = MultimodalTimelinePipeline(
            vad=StaticVad([SpeechWindow(**item.model_dump()) for item in request.speech_windows]),
            asr=StaticAsr(
                [TranscriptSegment(**item.model_dump()) for item in request.transcript_segments]
            ),
            frames=StaticFrames(
                [VideoKeyframe(**item.model_dump()) for item in request.video_keyframes]
            ),
            ocr=StaticOcr(
                [OcrObservation(**item.model_dump()) for item in request.ocr_observations]
            ),
        )
        try:
            generated = pipeline.build(
                SyntheticMediaInput(
                    tenant_id=actor.tenant_id,
                    family_id=actor.family_id,
                    session_ref=request.session_ref,
                    media_ref=request.media_ref,
                    audio_ref=request.audio_ref,
                    video_ref=request.video_ref,
                    duration_ms=request.duration_ms,
                    contains_real_person=request.contains_real_person,
                    contains_biometric_data=request.contains_biometric_data,
                )
            )
        except MultimodalRejected as exc:
            raise HTTPException(status_code=422, detail="multimodal evidence rejected") from exc
        view = multimodal_view(generated.cues, generated)
        with connect(database_path) as database:
            database.execute(
                "INSERT INTO multimodal_timelines "
                "(idempotency_key, request_fingerprint, tenant_id, family_id, result_json) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    request.idempotency_key,
                    fingerprint,
                    actor.tenant_id,
                    actor.family_id,
                    view.model_dump_json(),
                ),
            )
            database.commit()
        return view

    @app.post("/sandbox/live-ai/drafts/{draft_ref}/review", response_model=DraftView)
    def review_draft(
        draft_ref: str,
        request: ReviewRequest,
        actor: Annotated[Actor, Depends(actor_headers())],
    ) -> DraftView:
        require_role(actor, {"HUMAN_REVIEWER"})
        with connect(database_path) as database:
            row = require_draft(database, draft_ref)
            require_scope(actor, row)
            replay = database.execute(
                "SELECT * FROM ai_reviews WHERE idempotency_key = ?",
                (request.idempotency_key,),
            ).fetchone()
            fingerprint = review_fingerprint(request, actor, draft_ref)
            if replay is not None:
                if replay["request_fingerprint"] != fingerprint:
                    raise HTTPException(status_code=409, detail="idempotency conflict")
                return draft_view(require_draft(database, draft_ref))
            if row["status"] != DraftStatus.DRAFT.value:
                raise HTTPException(status_code=409, detail="draft already reviewed")

            provenance = InMemoryProvenanceFixture()
            flow = AISandboxFlow(
                gateway=FakeModelGateway(),
                provenance=provenance,
                human_gate=InMemoryHumanGateFixture(audit=provenance),
            )
            draft = row_to_summary(row)
            try:
                reviewed = flow.review(
                    draft=draft,
                    reviewer_id=f"human:{actor.actor_id}",
                    decision=ReviewDecision(request.decision),
                    reason=request.reason,
                    edited_text=request.edited_text,
                )
            except (HumanGateRejected, ValueError) as exc:
                raise HTTPException(status_code=403, detail="human gate rejected") from exc
            database.execute(
                "UPDATE ai_drafts SET summary = ?, status = ? WHERE draft_ref = ?",
                (reviewed.text, reviewed.status.value, draft_ref),
            )
            database.execute(
                "INSERT INTO ai_reviews "
                "(idempotency_key, request_fingerprint, draft_ref, reviewer_id, decision, reason) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    request.idempotency_key,
                    fingerprint,
                    draft_ref,
                    actor.actor_id,
                    request.decision,
                    request.reason,
                ),
            )
            append_receipt(database, draft_ref, actor, f"HUMAN_{request.decision}", request.reason)
            database.commit()
            return draft_view(require_draft(database, draft_ref))

    @app.get("/sandbox/live-ai/drafts/{draft_ref}", response_model=DraftView)
    def get_draft(
        draft_ref: str,
        actor: Annotated[Actor, Depends(actor_headers())],
    ) -> DraftView:
        require_role(actor, {"CREATOR", "AI_OPERATOR", "HUMAN_REVIEWER"})
        with connect(database_path) as database:
            row = require_draft(database, draft_ref)
            require_scope(actor, row)
            return draft_view(row)

    @app.get("/sandbox/live-ai/drafts/{draft_ref}/receipts")
    def receipts(
        draft_ref: str,
        actor: Annotated[Actor, Depends(actor_headers())],
    ) -> dict[str, object]:
        require_role(actor, {"CREATOR", "AI_OPERATOR", "HUMAN_REVIEWER"})
        with connect(database_path) as database:
            row = require_draft(database, draft_ref)
            require_scope(actor, row)
            entries = database.execute(
                "SELECT action, actor_id, reason FROM ai_receipts "
                "WHERE draft_ref = ? ORDER BY sequence",
                (draft_ref,),
            ).fetchall()
        return {
            "draft_ref": draft_ref,
            "receipts": [dict(entry) for entry in entries],
            "source": SANDBOX_SOURCE,
            "fixture_only": True,
            "external_effect": False,
            "fact_write": False,
            "audit_mode": "SANDBOX_RECEIPT_ONLY",
        }

    return app


def require_role(actor: Actor, allowed: set[str]) -> None:
    if actor.role not in allowed:
        raise HTTPException(status_code=403, detail="actor role rejected")


def require_scope(actor: Actor, row: sqlite3.Row) -> None:
    if actor.tenant_id != row["tenant_id"] or actor.family_id != row["family_id"]:
        raise HTTPException(status_code=403, detail="tenant/family scope rejected")


def row_to_summary(row: sqlite3.Row):
    from poc.standalone_live_ai_sandbox.draft_flow import DraftSummary

    return DraftSummary(
        draft_ref=row["draft_ref"],
        transcript_ref=row["transcript_ref"],
        tenant_id=row["tenant_id"],
        family_id=row["family_id"],
        text=row["summary"],
        chapters=tuple(json.loads(row["chapters"])),
        risk_flags=tuple(json.loads(row["risk_flags"])),
        provenance_ref=row["provenance_ref"],
        draft_hash=row["draft_hash"],
        status=DraftStatus(row["status"]),
        model=row["model"],
        model_version=row["model_version"],
        provider=row["provider"],
        prompt_version=row["prompt_version"],
    )


def draft_view(row: sqlite3.Row) -> DraftView:
    return DraftView(
        draft_ref=row["draft_ref"],
        session_ref=row["session_ref"],
        transcript_ref=row["transcript_ref"],
        summary=row["summary"],
        chapters=json.loads(row["chapters"]),
        risk_flags=json.loads(row["risk_flags"]),
        status=row["status"],
        provenance_ref=row["provenance_ref"],
        draft_hash=row["draft_hash"],
        model=row["model"],
        model_version=row["model_version"],
        provider=row["provider"],
        prompt_version=row["prompt_version"],
    )


def payload_fingerprint(request: GenerateRequest, actor: Actor) -> str:
    return sha256(
        json.dumps(
            {"request": request.model_dump(), "actor": actor.model_dump()},
            ensure_ascii=False,
            sort_keys=True,
        ).encode()
    ).hexdigest()


def review_fingerprint(request: ReviewRequest, actor: Actor, draft_ref: str) -> str:
    return sha256(
        json.dumps(
            {"request": request.model_dump(), "actor": actor.model_dump(), "draft_ref": draft_ref},
            ensure_ascii=False,
            sort_keys=True,
        ).encode()
    ).hexdigest()


def multimodal_fingerprint(request: MultimodalTimelineRequest, actor: Actor) -> str:
    return sha256(
        json.dumps(
            {"request": request.model_dump(), "actor": actor.model_dump()},
            ensure_ascii=False,
            sort_keys=True,
        ).encode()
    ).hexdigest()


def multimodal_view(
    cues: tuple[TimelineCue, ...], generated: MultimodalTimelineDraft
) -> MultimodalTimelineView:
    return MultimodalTimelineView(
        timeline_ref=generated.timeline_ref,
        session_ref=generated.session_ref,
        media_ref=generated.media_ref,
        cues=[
            TimelineCueView(
                start_ms=cue.start_ms,
                end_ms=cue.end_ms,
                speaker_ref=cue.speaker_ref,
                transcript=cue.transcript,
                frame_ref=cue.frame_ref,
                scene_ref=cue.scene_ref,
                ocr_text=list(cue.ocr_text),
                evidence_refs=list(cue.evidence_refs),
            )
            for cue in cues
        ],
        evidence_digest=generated.evidence_digest,
        modalities=list(generated.modalities),
        risk_flags=list(generated.risk_flags),
    )


def append_receipt(
    database: sqlite3.Connection,
    draft_ref: str,
    actor: Actor,
    action: str,
    reason: str,
) -> None:
    database.execute(
        "INSERT INTO ai_receipts (draft_ref, tenant_id, family_id, actor_id, action, reason) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (draft_ref, actor.tenant_id, actor.family_id, actor.actor_id, action, reason),
    )


def require_draft(database: sqlite3.Connection, draft_ref: str) -> sqlite3.Row:
    row = database.execute("SELECT * FROM ai_drafts WHERE draft_ref = ?", (draft_ref,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="draft not found")
    return row


def connect(database_path: Path) -> sqlite3.Connection:
    database = sqlite3.connect(database_path)
    database.row_factory = sqlite3.Row
    return database


def initialise(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(database_path) as database:
        database.executescript(
            """
            CREATE TABLE IF NOT EXISTS ai_drafts (
                draft_ref TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, family_id TEXT NOT NULL,
                actor_id TEXT NOT NULL, session_ref TEXT NOT NULL, transcript_ref TEXT NOT NULL,
                transcript TEXT NOT NULL, summary TEXT NOT NULL, chapters TEXT NOT NULL,
                risk_flags TEXT NOT NULL, status TEXT NOT NULL, provenance_ref TEXT NOT NULL,
                draft_hash TEXT NOT NULL, model TEXT NOT NULL, model_version TEXT NOT NULL,
                provider TEXT NOT NULL, prompt_version TEXT NOT NULL,
                idempotency_key TEXT NOT NULL UNIQUE, request_fingerprint TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS ai_reviews (
                idempotency_key TEXT PRIMARY KEY, request_fingerprint TEXT NOT NULL,
                draft_ref TEXT NOT NULL, reviewer_id TEXT NOT NULL,
                decision TEXT NOT NULL, reason TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS ai_receipts (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT, draft_ref TEXT NOT NULL,
                tenant_id TEXT NOT NULL, family_id TEXT NOT NULL, actor_id TEXT NOT NULL,
                action TEXT NOT NULL, reason TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS ai_failure_receipts (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL,
                family_id TEXT NOT NULL, actor_id TEXT NOT NULL,
                transcript_ref TEXT NOT NULL, reason TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS multimodal_timelines (
                idempotency_key TEXT PRIMARY KEY, request_fingerprint TEXT NOT NULL,
                tenant_id TEXT NOT NULL, family_id TEXT NOT NULL,
                result_json TEXT NOT NULL
            );
            """
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--port", type=int, default=55305)
    args = parser.parse_args()
    if not args.serve:
        raise SystemExit("use --serve")
    uvicorn.run(create_app(args.database), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
