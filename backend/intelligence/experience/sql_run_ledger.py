"""Durable SQL adapter for the HTTP-facing experience-run ledger.

``run_http.ExperienceRunLedger`` predates the async application stack and is a
synchronous protocol (the in-memory implementation is intentionally tiny).
This module therefore exposes a separate ``AsyncExperienceRunLedger`` port
and an async SQLAlchemy implementation.  It is *not* structurally injectable
into the current HTTP routes until the composition root awaits the calls (or
installs an explicit async bridge).  Pretending an ``AsyncSession`` is a sync
ledger would block the event loop and, worse, make transaction ownership
ambiguous.

The adapter reuses ``SqlAlchemyExperienceRunStore`` for the durable run/event/
checkpoint state machine and owns one additional append-only interaction
table.  Preflight/finalize metadata, including the validated HTTP response
projection, lives on the run envelope so a new bridge/session can replay it.
Methods only flush; callers own the transaction.  Use
``async with ledger.transaction():`` or an existing ``SqlAlchemyUnitOfWork``
when an interaction must be committed atomically with another AI-runtime
write.  No method writes a domain fact or calls a model provider.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import JSON, DateTime, Integer, String, Text, UniqueConstraint, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from backend.intelligence.experience.run_http import (
    DraftPreflight,
    InteractionReceipt,
    InteractionType,
    RunHttpConflictError,
    RunHttpError,
    RunInteractionEntry,
    RunReplaySnapshot,
    _assert_artifacts,
    _assert_draft_payload,
    _assert_safe_mapping,
    _fingerprint,
    _validate_evaluation_payload,
    _validate_feedback_payload,
)
from backend.intelligence.experience.run_http import (
    RunScope as HttpRunScope,
)
from backend.intelligence.experience.run_store import (
    ExperienceRunCheckpointRow,
    ExperienceRunPersistenceBase,
    ExperienceRunRow,
    SqlAlchemyExperienceRunStore,
)
from backend.intelligence.experience.run_store import (
    RunScope as StoreRunScope,
)
from backend.intelligence.experience.runs import RunContractError


class AsyncExperienceRunLedger(Protocol):
    """Async counterpart to the legacy sync ``ExperienceRunLedger`` port."""

    async def preflight_create(
        self,
        *,
        scope: HttpRunScope,
        run_id: str,
        request_ref: str,
        request_fingerprint: str,
        idempotency_key: str,
    ) -> DraftPreflight: ...

    async def finalize_create(
        self,
        reservation: DraftPreflight,
        *,
        draft_payload: Mapping[str, Any],
        artifact_refs: tuple[str, ...] = (),
        response_payload: Mapping[str, Any] | None = None,
    ) -> RunReplaySnapshot: ...

    async def release_create(self, reservation: DraftPreflight) -> None: ...

    async def create_draft(
        self,
        *,
        scope: HttpRunScope,
        run_id: str,
        request_ref: str,
        draft_payload: Mapping[str, Any],
        artifact_refs: tuple[str, ...] = (),
        idempotency_key: str,
    ) -> RunReplaySnapshot: ...

    async def append_interaction(
        self,
        *,
        scope: HttpRunScope,
        run_id: str,
        interaction_type: InteractionType,
        payload: Mapping[str, Any],
        idempotency_key: str,
    ) -> InteractionReceipt: ...

    async def record_evaluation(
        self,
        *,
        scope: HttpRunScope,
        run_id: str,
        report_ref: str,
        case_version: str,
        idempotency_key: str,
        payload: Mapping[str, Any] | None = None,
    ) -> InteractionReceipt: ...

    async def replay(self, *, scope: HttpRunScope, run_id: str) -> RunReplaySnapshot: ...


class ExperienceRunInteractionRow(ExperienceRunPersistenceBase):
    """ORM mapping for the 0010 append-only interaction stream."""

    __tablename__ = "experience_run_interactions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "run_id",
            "idempotency_key",
            name="uq_experience_run_interaction_idempotency",
        ),
        UniqueConstraint(
            "tenant_id",
            "run_id",
            "event_sequence",
            name="uq_experience_run_interaction_sequence",
        ),
    )

    tenant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    interaction_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    family_id: Mapped[str] = mapped_column(String(128), nullable=False)
    subject_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    interaction_type: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)
    event_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def _normalise_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _json_fingerprint(operation: str, payload: Mapping[str, Any]) -> str:
    # Keep the operation in the digest: reusing a key for feedback and a
    # decision must fail even if their payload happens to be identical.
    return _fingerprint({"operation": operation, "payload": payload})


def _store_scope(scope: HttpRunScope) -> StoreRunScope:
    return StoreRunScope(
        tenant_id=scope.tenant_id,
        family_id=scope.family_id,
        subject_ids=scope.subject_ids,
    )


def _map_store_error(error: RunContractError) -> RunHttpError:
    code = str(error)
    # RunContractError messages are stable machine-readable codes in the
    # existing run store.  Preserve the code so HTTP can map it consistently.
    return RunHttpError(code)


class SqlAlchemyExperienceRunLedger:
    """Async, append-only SQL ledger implementing ``AsyncExperienceRunLedger``.

    The constructor accepts an already-owned ``AsyncSession``.  It never
    commits or closes that session.  This is intentional: transaction
    ownership belongs to the composition root and permits a run interaction,
    outbox record and audit event to share one commit.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlAlchemyExperienceRunLedger]:
        """Begin an explicit transaction when the caller does not own one."""

        if self._session.in_transaction():
            yield self
            return
        async with self._session.begin():
            yield self

    async def preflight_create(
        self,
        *,
        scope: HttpRunScope,
        run_id: str,
        request_ref: str,
        request_fingerprint: str,
        idempotency_key: str,
    ) -> DraftPreflight:
        """Reserve a run before model invocation.

        A reservation is a runtime-owned row with ``version=0`` and
        ``create_status=RESERVED``.  It is intentionally not a run event: a
        failed provider call can release it without leaving a fake execution
        history.  The caller must commit this reservation before invoking a
        provider in another transaction.
        """

        self._assert_scope(scope)
        self._assert_ids(run_id, request_ref, idempotency_key, request_fingerprint)
        row = await self._session.get(
            ExperienceRunRow,
            {"tenant_id": scope.tenant_id, "run_id": run_id},
        )
        if row is not None:
            self._assert_row_scope(row, scope)
            if row.create_idempotency_key != idempotency_key:
                if row.create_status == "RESERVED":
                    raise RunHttpConflictError("DRAFT_CREATE_IN_PROGRESS")
                raise RunHttpConflictError("RUN_ALREADY_EXISTS")
            if (
                row.create_fingerprint != request_fingerprint
                or row.request_ref != request_ref
            ):
                raise RunHttpConflictError("IDEMPOTENCY_REPLAY_MISMATCH")
            if row.create_status == "RESERVED":
                return DraftPreflight(
                    scope=scope,
                    run_id=run_id,
                    request_ref=request_ref,
                    request_fingerprint=request_fingerprint,
                    idempotency_key=idempotency_key,
                    status="in_progress",
                )
            if row.create_status in {"FINALIZED", None}:
                # ``None`` is the compatibility state for rows created by
                # the pre-preflight SQL adapter; version>0 proves completion.
                snapshot = await self.replay(scope=scope, run_id=run_id)
                return DraftPreflight(
                    scope=scope,
                    run_id=run_id,
                    request_ref=request_ref,
                    request_fingerprint=request_fingerprint,
                    idempotency_key=idempotency_key,
                    status="replay",
                    snapshot=snapshot,
                    response_payload=(
                        None
                        if snapshot.deletion_state == "deleted"
                        else row.create_response_payload
                    ),
                )
            raise RunHttpError("CORRUPT_CREATE_STATUS")

        result = await self._session.execute(
            select(ExperienceRunRow.run_id).where(ExperienceRunRow.run_id == run_id)
        )
        if result.first() is not None:
            raise RunHttpError("RUN_SCOPE_MISMATCH")

        row = ExperienceRunRow(
            tenant_id=scope.tenant_id,
            run_id=run_id,
            family_id=scope.family_id,
            subject_ids=list(scope.subject_ids),
            request_ref=request_ref,
            state="QUEUED",
            version=0,
            latest_checkpoint_id=None,
            status="DRAFT",
            create_idempotency_key=idempotency_key,
            create_fingerprint=request_fingerprint,
            create_status="RESERVED",
            create_response_payload=None,
            deletion_state="active",
        )
        try:
            if self._uses_sqlite:
                self._session.add(row)
                await self._session.flush()
            else:
                async with self._session.begin_nested():
                    self._session.add(row)
                    await self._session.flush()
        except IntegrityError as error:
            raise RunHttpConflictError("DRAFT_CREATE_IN_PROGRESS") from error
        return DraftPreflight(
            scope=scope,
            run_id=run_id,
            request_ref=request_ref,
            request_fingerprint=request_fingerprint,
            idempotency_key=idempotency_key,
            status="reserved",
        )

    async def finalize_create(
        self,
        reservation: DraftPreflight,
        *,
        draft_payload: Mapping[str, Any],
        artifact_refs: tuple[str, ...] = (),
        response_payload: Mapping[str, Any] | None = None,
    ) -> RunReplaySnapshot:
        """Materialize a reserved run and persist its replayable HTTP response."""

        if not isinstance(reservation, DraftPreflight):
            raise RunHttpError("DRAFT_RESERVATION_INVALID")
        if reservation.status == "replay" and reservation.snapshot is not None:
            return reservation.snapshot
        if reservation.status != "reserved":
            raise RunHttpConflictError("DRAFT_CREATE_IN_PROGRESS")
        try:
            _assert_draft_payload(draft_payload)
            _assert_artifacts(artifact_refs)
            if response_payload is not None:
                _assert_safe_mapping(response_payload)
        except RunHttpError:
            # A reservation is not a durable run. Validation failures release
            # it in the same caller-owned transaction so a retry can reserve
            # the same idempotency key without leaving a stale pending row.
            await self.release_create(reservation)
            raise

        row = await self._session.get(
            ExperienceRunRow,
            {"tenant_id": reservation.scope.tenant_id, "run_id": reservation.run_id},
        )
        if row is None:
            raise RunHttpError("DRAFT_RESERVATION_NOT_FOUND")
        self._assert_row_scope(row, reservation.scope)
        if (
            row.create_status != "RESERVED"
            or row.create_idempotency_key != reservation.idempotency_key
            or row.create_fingerprint != reservation.request_fingerprint
            or row.request_ref != reservation.request_ref
        ):
            if row.create_status == "FINALIZED":
                return await self.replay(scope=reservation.scope, run_id=reservation.run_id)
            raise RunHttpConflictError("DRAFT_RESERVATION_NOT_FOUND")

        from backend.intelligence.experience.runs import DurableExperienceRun, RunState

        run = DurableExperienceRun(
            run_id=reservation.run_id,
            tenant_id=reservation.scope.tenant_id,
            family_id=reservation.scope.family_id,
            subject_ids=reservation.scope.subject_ids,
            request_ref=reservation.request_ref,
        )
        try:
            run.transition(RunState.RUNNING, event_id=f"{reservation.run_id}:started")
            run.checkpoint(
                checkpoint_id=f"{reservation.run_id}:draft",
                artifact_refs=artifact_refs,
                draft_payload=dict(draft_payload),
            )
            run.transition(RunState.SUCCEEDED, event_id=f"{reservation.run_id}:succeeded")
            if self._uses_sqlite:
                await SqlAlchemyExperienceRunStore(self._session).save(run)
            else:
                async with self._session.begin_nested():
                    await SqlAlchemyExperienceRunStore(self._session).save(run)
        except IntegrityError as error:
            await self.release_create(reservation)
            raise RunHttpConflictError("RUN_CREATE_CONFLICT") from error
        except (RunContractError, RunHttpError) as error:
            await self.release_create(reservation)
            if isinstance(error, RunHttpError):
                raise
            raise _map_store_error(error) from error

        row.create_status = "FINALIZED"
        row.create_response_payload = (
            _jsonable(response_payload) if response_payload is not None else None
        )
        row.deletion_state = "active"
        await self._session.flush()
        return await self.replay(scope=reservation.scope, run_id=reservation.run_id)

    async def release_create(self, reservation: DraftPreflight) -> None:
        """Release an unmaterialized reservation; safe to call repeatedly."""

        if not isinstance(reservation, DraftPreflight) or reservation.status != "reserved":
            return
        row = await self._session.get(
            ExperienceRunRow,
            {"tenant_id": reservation.scope.tenant_id, "run_id": reservation.run_id},
        )
        if row is None:
            return
        self._assert_row_scope(row, reservation.scope)
        if (
            row.create_status != "RESERVED"
            or row.create_idempotency_key != reservation.idempotency_key
            or row.create_fingerprint != reservation.request_fingerprint
        ):
            return
        if row.version != 0:
            # A concurrent finalizer won the reservation; never delete a real
            # run merely because a stale provider request released its token.
            return
        await self._session.delete(row)
        await self._session.flush()

    async def create_draft(
        self,
        *,
        scope: HttpRunScope,
        run_id: str,
        request_ref: str,
        draft_payload: Mapping[str, Any],
        artifact_refs: tuple[str, ...] = (),
        idempotency_key: str,
    ) -> RunReplaySnapshot:
        fingerprint = _json_fingerprint(
            "create_draft",
            {
                "request_ref": request_ref,
                "draft_payload": draft_payload,
                "artifact_refs": artifact_refs,
            },
        )
        reservation = await self.preflight_create(
            scope=scope,
            run_id=run_id,
            request_ref=request_ref,
            request_fingerprint=fingerprint,
            idempotency_key=idempotency_key,
        )
        if reservation.status == "replay" and reservation.snapshot is not None:
            return reservation.snapshot
        if reservation.status != "reserved":
            raise RunHttpConflictError("DRAFT_CREATE_IN_PROGRESS")
        return await self.finalize_create(
            reservation,
            draft_payload=draft_payload,
            artifact_refs=artifact_refs,
        )

    async def append_interaction(
        self,
        *,
        scope: HttpRunScope,
        run_id: str,
        interaction_type: InteractionType,
        payload: Mapping[str, Any],
        idempotency_key: str,
    ) -> InteractionReceipt:
        self._assert_scope(scope)
        self._assert_ids(run_id, run_id, idempotency_key)
        if not isinstance(interaction_type, InteractionType):
            raise RunHttpError("INTERACTION_TYPE_UNSUPPORTED")
        _assert_safe_mapping(payload)
        self._validate_interaction_payload(interaction_type, payload)

        row = await self._session.get(
            ExperienceRunRow,
            {"tenant_id": scope.tenant_id, "run_id": run_id},
        )
        if row is None:
            result = await self._session.execute(
                select(ExperienceRunRow.run_id).where(ExperienceRunRow.run_id == run_id)
            )
            if result.first() is not None:
                raise RunHttpError("RUN_SCOPE_MISMATCH")
            raise RunHttpError("RUN_NOT_FOUND")
        self._assert_row_scope(row, scope)
        if row.create_status == "RESERVED":
            # A preflight row is not yet a replayable run, matching the
            # in-memory ledger's pending-create behaviour.
            raise RunHttpError("RUN_NOT_FOUND")

        fingerprint = _json_fingerprint(interaction_type.value, payload)
        existing = await self._session.scalar(
            select(ExperienceRunInteractionRow).where(
                ExperienceRunInteractionRow.tenant_id == scope.tenant_id,
                ExperienceRunInteractionRow.run_id == run_id,
                ExperienceRunInteractionRow.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            self._assert_interaction_row_scope(existing, scope)
            if existing.fingerprint != fingerprint:
                raise RunHttpConflictError("IDEMPOTENCY_REPLAY_MISMATCH")
            return InteractionReceipt(
                run_id=run_id,
                interaction=self._entry_from_row(existing),
                status="replayed",
                idempotency_replayed=True,
            )

        if row.deletion_state == "deleted" and interaction_type is not InteractionType.DELETE:
            raise RunHttpError("RUN_DELETED")

        entries = await self._interaction_rows(scope.tenant_id, run_id)
        event_sequence = row.version + len(entries) + 1
        entry_id = f"{run_id}:interaction:{len(entries) + 1}"
        entry = RunInteractionEntry(
            event_id=entry_id,
            run_id=run_id,
            scope=scope,
            interaction_type=interaction_type,
            payload=dict(payload),
            idempotency_key=idempotency_key,
            sequence=event_sequence,
        )
        interaction_row = ExperienceRunInteractionRow(
            tenant_id=scope.tenant_id,
            run_id=run_id,
            interaction_id=entry.event_id,
            family_id=scope.family_id,
            subject_ids=list(scope.subject_ids),
            interaction_type=interaction_type.value,
            payload=_jsonable(payload),
            fingerprint=fingerprint,
            idempotency_key=idempotency_key,
            event_sequence=event_sequence,
            occurred_at=entry.occurred_at,
        )
        try:
            # The savepoint keeps a caller-owned outer transaction usable when
            # a concurrent request wins one of the unique constraints.
            if self._uses_sqlite:
                self._session.add(interaction_row)
                await self._session.flush()
            else:
                async with self._session.begin_nested():
                    self._session.add(interaction_row)
                    await self._session.flush()
        except IntegrityError as error:
            raise RunHttpConflictError("INTERACTION_APPEND_CONFLICT") from error

        if interaction_type is InteractionType.DELETE:
            await self._scrub_deleted_run(row, scope.tenant_id, run_id)
        receipt = InteractionReceipt(
            run_id=run_id,
            interaction=entry,
            status="deleted" if interaction_type is InteractionType.DELETE else "recorded",
        )
        return receipt

    async def record_evaluation(
        self,
        *,
        scope: HttpRunScope,
        run_id: str,
        report_ref: str,
        case_version: str,
        idempotency_key: str,
        payload: Mapping[str, Any] | None = None,
    ) -> InteractionReceipt:
        """Persist a bounded, media-free evaluation projection beside a run."""

        body = dict(payload or {})
        body["report_ref"] = report_ref
        body["case_version"] = case_version
        body.setdefault("education_outcome_status", "NOT_MEASURED")
        return await self.append_interaction(
            scope=scope,
            run_id=run_id,
            interaction_type=InteractionType.EVALUATION,
            payload=body,
            idempotency_key=idempotency_key,
        )

    async def replay(self, *, scope: HttpRunScope, run_id: str) -> RunReplaySnapshot:
        self._assert_scope(scope)
        row = await self._session.get(
            ExperienceRunRow,
            {"tenant_id": scope.tenant_id, "run_id": run_id},
        )
        if row is None:
            result = await self._session.execute(
                select(ExperienceRunRow.run_id).where(ExperienceRunRow.run_id == run_id)
            )
            if result.first() is not None:
                raise RunHttpError("RUN_SCOPE_MISMATCH")
            raise RunHttpError("RUN_NOT_FOUND")
        self._assert_row_scope(row, scope)
        if row.create_status == "RESERVED":
            raise RunHttpError("RUN_NOT_FOUND")
        # Preserve the persisted subject ordering in replay responses.  Scope
        # equality is set-like (``RunScope.key`` sorts subjects), but a stable
        # projection must not change merely because a retry supplied the same
        # IDs in another order.
        persisted_scope = HttpRunScope(
            tenant_id=row.tenant_id,
            family_id=row.family_id,
            subject_ids=tuple(row.subject_ids),
        )

        try:
            durable = await SqlAlchemyExperienceRunStore(self._session).replay(
                scope=_store_scope(persisted_scope), run_id=run_id
            )
        except RunContractError as error:
            raise _map_store_error(error) from error
        interaction_rows = await self._interaction_rows(scope.tenant_id, run_id)
        for expected, item in enumerate(
            interaction_rows, start=durable.snapshot.version + 1
        ):
            self._assert_interaction_row_scope(item, persisted_scope)
            if item.event_sequence != expected:
                raise RunHttpError("CORRUPT_INTERACTION_SEQUENCE")
        interactions = tuple(self._entry_from_row(item) for item in interaction_rows)
        deleted = row.deletion_state == "deleted" or any(
            item.interaction_type is InteractionType.DELETE for item in interactions
        )
        latest = durable.checkpoints[-1] if durable.checkpoints else None
        return RunReplaySnapshot(
            run_id=run_id,
            scope=persisted_scope,
            state=durable.snapshot.state,
            status="DRAFT",
            event_sequence=durable.snapshot.version + len(interactions),
            interactions=interactions,
            draft_payload=(
                None
                if deleted or latest is None or latest.draft_payload is None
                else dict(latest.draft_payload)
            ),
            artifact_refs=(
                ()
                if deleted or latest is None
                else tuple(latest.artifact_refs)
            ),
            deletion_state="deleted" if deleted else "active",
        )

    async def _scrub_deleted_run(
        self, row: ExperienceRunRow, tenant_id: str, run_id: str
    ) -> None:
        """Erase derived model material while retaining an audit interaction."""

        checkpoints = await self._session.execute(
            select(ExperienceRunCheckpointRow).where(
                ExperienceRunCheckpointRow.tenant_id == tenant_id,
                ExperienceRunCheckpointRow.run_id == run_id,
            )
        )
        for checkpoint in checkpoints.scalars():
            # This is the narrow privacy-erasure exception to append-only
            # history.  Keeping an empty marker makes the scrub observable
            # without retaining model text or media references.
            checkpoint.payload = {"scrubbed": True}
            checkpoint.draft_payload = None
            checkpoint.artifact_refs = []
        row.deletion_state = "deleted"
        row.create_response_payload = None
        await self._session.flush()

    async def _interaction_rows(
        self, tenant_id: str, run_id: str
    ) -> list[ExperienceRunInteractionRow]:
        result = await self._session.execute(
            select(ExperienceRunInteractionRow)
            .where(
                ExperienceRunInteractionRow.tenant_id == tenant_id,
                ExperienceRunInteractionRow.run_id == run_id,
            )
            .order_by(ExperienceRunInteractionRow.event_sequence)
        )
        return list(result.scalars())

    @staticmethod
    def _entry_from_row(row: ExperienceRunInteractionRow) -> RunInteractionEntry:
        try:
            interaction_type = InteractionType(row.interaction_type)
        except ValueError as error:
            raise RunHttpError("CORRUPT_INTERACTION_TYPE") from error
        if not isinstance(row.payload, Mapping):
            raise RunHttpError("CORRUPT_INTERACTION_PAYLOAD")
        if not isinstance(row.subject_ids, (list, tuple)):
            raise RunHttpError("CORRUPT_INTERACTION_SCOPE")
        return RunInteractionEntry(
            event_id=row.interaction_id,
            run_id=row.run_id,
            scope=HttpRunScope(
                tenant_id=row.tenant_id,
                family_id=row.family_id,
                subject_ids=tuple(row.subject_ids),
            ),
            interaction_type=interaction_type,
            payload=dict(row.payload),
            idempotency_key=row.idempotency_key,
            sequence=row.event_sequence,
            occurred_at=_normalise_datetime(row.occurred_at),
        )

    @staticmethod
    def _assert_scope(scope: HttpRunScope) -> None:
        if not isinstance(scope, HttpRunScope):
            raise RunHttpError("SCOPE_REQUIRED")

    @property
    def _uses_sqlite(self) -> bool:
        bind = self._session.sync_session.get_bind()
        return bind is not None and bind.dialect.name == "sqlite"

    @staticmethod
    def _assert_ids(*values: str) -> None:
        if any(not isinstance(value, str) or not value for value in values):
            raise RunHttpError("RUN_ID_AND_IDEMPOTENCY_REQUIRED")

    @staticmethod
    def _assert_row_scope(row: ExperienceRunRow, scope: HttpRunScope) -> None:
        if not isinstance(row.subject_ids, (list, tuple)):
            raise RunHttpError("CORRUPT_RUN_SCOPE")
        if row.family_id != scope.family_id or tuple(sorted(row.subject_ids)) != tuple(
            sorted(scope.subject_ids)
        ):
            raise RunHttpError("RUN_SCOPE_MISMATCH")

    @staticmethod
    def _assert_interaction_row_scope(
        row: ExperienceRunInteractionRow, scope: HttpRunScope
    ) -> None:
        if not isinstance(row.subject_ids, (list, tuple)):
            raise RunHttpError("CORRUPT_INTERACTION_SCOPE")
        if row.family_id != scope.family_id or tuple(sorted(row.subject_ids)) != tuple(
            sorted(scope.subject_ids)
        ):
            raise RunHttpError("RUN_SCOPE_MISMATCH")

    @staticmethod
    def _validate_interaction_payload(
        interaction_type: InteractionType, payload: Mapping[str, Any]
    ) -> None:
        if interaction_type is InteractionType.DECISION and payload.get("decision") not in {
            "pending_human_confirmation",
            "accepted",
            "rewrite",
            "rejected",
        }:
            raise RunHttpError("DECISION_STATUS_UNSUPPORTED")
        if (
            interaction_type is InteractionType.HUMAN_REVIEW
            and payload.get("status") != "human_review"
        ):
            raise RunHttpError("HUMAN_REVIEW_STATUS_INVALID")
        if interaction_type is InteractionType.DELETE and payload.get("status") != "deleted":
            raise RunHttpError("DELETION_STATUS_INVALID")
        if interaction_type is InteractionType.FEEDBACK:
            _validate_feedback_payload(payload)
        if interaction_type is InteractionType.EVALUATION:
            _validate_evaluation_payload(payload)


class CommittedExperienceRunLedger:
    """Commit the durable ledger at HTTP lifecycle boundaries.

    ``SqlAlchemyExperienceRunLedger`` deliberately owns no transaction.  That
    is the right primitive for a larger unit of work, but the draft HTTP flow
    has one boundary that must be durable before model invocation: the
    preflight reservation.  This small composition-root adapter makes that
    boundary explicit and commits after every mutating operation.  It never
    commits reads and rolls back a failed commit so the request cannot reuse a
    tainted session.

    The wrapped ledger remains provider-neutral; this class only coordinates
    the caller-owned ``AsyncSession`` and therefore is safe to use with the
    ``AsyncExperienceRunLedgerBridge``.
    """

    def __init__(self, ledger: AsyncExperienceRunLedger, session: AsyncSession) -> None:
        self._ledger = ledger
        self._session = session

    async def _commit(self) -> None:
        try:
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise

    async def preflight_create(self, **kwargs: Any) -> DraftPreflight:
        result = await self._ledger.preflight_create(**kwargs)
        await self._commit()
        return result

    async def finalize_create(self, **kwargs: Any) -> RunReplaySnapshot:
        result = await self._ledger.finalize_create(**kwargs)
        await self._commit()
        return result

    async def release_create(self, **kwargs: Any) -> None:
        await self._ledger.release_create(**kwargs)
        await self._commit()

    async def create_draft(self, **kwargs: Any) -> RunReplaySnapshot:
        result = await self._ledger.create_draft(**kwargs)
        await self._commit()
        return result

    async def append_interaction(self, **kwargs: Any) -> InteractionReceipt:
        result = await self._ledger.append_interaction(**kwargs)
        await self._commit()
        return result

    async def record_evaluation(self, **kwargs: Any) -> InteractionReceipt:
        result = await self._ledger.record_evaluation(**kwargs)
        await self._commit()
        return result

    async def replay(self, **kwargs: Any) -> RunReplaySnapshot:
        return await self._ledger.replay(**kwargs)


class SessionPerCallExperienceRunLedger:
    """Open and close one SQL session for each ledger operation.

    FastAPI's runtime resolver returns a value object and has no request
    teardown hook.  Holding an ``AsyncSession`` in that value would leak a
    connection unless every route remembered to close it.  This adapter keeps
    the resolver stateless: each operation gets a fresh session, while the
    committed adapter still makes preflight durable before model invocation.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def _run(self, operation: Any) -> Any:
        async with self._session_factory() as session:
            ledger = CommittedExperienceRunLedger(
                SqlAlchemyExperienceRunLedger(session), session
            )
            return await operation(ledger)

    async def preflight_create(self, **kwargs: Any) -> DraftPreflight:
        return await self._run(lambda ledger: ledger.preflight_create(**kwargs))

    async def finalize_create(self, **kwargs: Any) -> RunReplaySnapshot:
        return await self._run(lambda ledger: ledger.finalize_create(**kwargs))

    async def release_create(self, **kwargs: Any) -> None:
        await self._run(lambda ledger: ledger.release_create(**kwargs))

    async def create_draft(self, **kwargs: Any) -> RunReplaySnapshot:
        return await self._run(lambda ledger: ledger.create_draft(**kwargs))

    async def append_interaction(self, **kwargs: Any) -> InteractionReceipt:
        return await self._run(lambda ledger: ledger.append_interaction(**kwargs))

    async def record_evaluation(self, **kwargs: Any) -> InteractionReceipt:
        return await self._run(lambda ledger: ledger.record_evaluation(**kwargs))

    async def replay(self, **kwargs: Any) -> RunReplaySnapshot:
        async with self._session_factory() as session:
            return await SqlAlchemyExperienceRunLedger(session).replay(**kwargs)


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return json.loads(json.dumps(value, default=str))


__all__ = [
    "AsyncExperienceRunLedger",
    "CommittedExperienceRunLedger",
    "ExperienceRunInteractionRow",
    "SessionPerCallExperienceRunLedger",
    "SqlAlchemyExperienceRunLedger",
]
