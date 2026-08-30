from typing import Any

import pytest

from backend.intelligence.experience.async_ledger_bridge import (
    AsyncExperienceRunLedgerBridge,
    dispatch_ledger_call,
)
from backend.intelligence.experience.run_http import (
    InMemoryExperienceRunLedger,
    InteractionType,
    RunHttpConflictError,
    RunScope,
)


class AsyncFacade:
    def __init__(self) -> None:
        self.inner = InMemoryExperienceRunLedger()

    async def create_draft(self, **kwargs: Any):
        return self.inner.create_draft(**kwargs)

    async def append_interaction(self, **kwargs: Any):
        return self.inner.append_interaction(**kwargs)

    async def replay(self, **kwargs: Any):
        return self.inner.replay(**kwargs)


def scope() -> RunScope:
    return RunScope(tenant_id="tenant-1", family_id="family-1", subject_ids=("child-1",))


@pytest.mark.asyncio
async def test_dispatch_supports_sync_and_async_without_blocking() -> None:
    class Sync:
        def ping(self, *, value: int) -> int:
            return value + 1

    class Async:
        async def ping(self, *, value: int) -> int:
            return value + 2

    assert await dispatch_ledger_call(Sync(), "ping", value=1) == 2
    assert await dispatch_ledger_call(Async(), "ping", value=1) == 3


@pytest.mark.asyncio
async def test_async_bridge_preserves_preflight_finalize_and_interaction_contract() -> None:
    bridge = AsyncExperienceRunLedgerBridge(AsyncFacade())
    reservation = await bridge.preflight_create(
        scope=scope(),
        run_id="run-1",
        request_ref="request-1",
        request_fingerprint="fp-1",
        idempotency_key="idem-1",
    )
    assert reservation.status == "reserved"

    snapshot = await bridge.finalize_create(
        reservation,
        draft_payload={"status": "DRAFT", "text": "hello"},
        response_payload={"run_id": "run-1", "status": "DRAFT"},
    )
    assert snapshot.draft_payload == {"status": "DRAFT", "text": "hello"}

    replay = await bridge.preflight_create(
        scope=scope(),
        run_id="run-1",
        request_ref="request-1",
        request_fingerprint="fp-1",
        idempotency_key="idem-1",
    )
    assert replay.status == "replay"
    assert replay.response_payload == {"run_id": "run-1", "status": "DRAFT"}

    receipt = await bridge.append_interaction(
        scope=scope(),
        run_id="run-1",
        interaction_type=InteractionType.FEEDBACK,
        payload={"signal": "helpful"},
        idempotency_key="feedback-1",
    )
    assert receipt.status == "recorded"


@pytest.mark.asyncio
async def test_async_bridge_rejects_replay_fingerprint_mismatch() -> None:
    bridge = AsyncExperienceRunLedgerBridge(AsyncFacade())
    reservation = await bridge.preflight_create(
        scope=scope(),
        run_id="run-2",
        request_ref="request-2",
        request_fingerprint="fp-2",
        idempotency_key="idem-2",
    )
    await bridge.finalize_create(reservation, draft_payload={"status": "DRAFT"})

    with pytest.raises(RunHttpConflictError, match="IDEMPOTENCY_REPLAY_MISMATCH"):
        await bridge.preflight_create(
            scope=scope(),
            run_id="run-2",
            request_ref="request-2",
            request_fingerprint="different",
            idempotency_key="idem-2",
        )


@pytest.mark.asyncio
async def test_async_bridge_rejects_a_second_create_key_for_existing_run() -> None:
    bridge = AsyncExperienceRunLedgerBridge(AsyncFacade())
    reservation = await bridge.preflight_create(
        scope=scope(),
        run_id="run-3",
        request_ref="request-3",
        request_fingerprint="fp-3",
        idempotency_key="idem-3",
    )
    await bridge.finalize_create(reservation, draft_payload={"status": "DRAFT"})

    with pytest.raises(RunHttpConflictError, match="RUN_ALREADY_EXISTS"):
        await bridge.preflight_create(
            scope=scope(),
            run_id="run-3",
            request_ref="request-3",
            request_fingerprint="fp-3",
            idempotency_key="different-key",
        )


@pytest.mark.asyncio
async def test_async_bridge_scrubs_cached_response_after_delete() -> None:
    bridge = AsyncExperienceRunLedgerBridge(AsyncFacade())
    reservation = await bridge.preflight_create(
        scope=scope(),
        run_id="run-4",
        request_ref="request-4",
        request_fingerprint="fp-4",
        idempotency_key="idem-4",
    )
    await bridge.finalize_create(
        reservation,
        draft_payload={"status": "DRAFT"},
        response_payload={"run_id": "run-4", "status": "DRAFT"},
    )
    await bridge.append_interaction(
        scope=scope(),
        run_id="run-4",
        interaction_type=InteractionType.DELETE,
        payload={"deletion_ref": "delete-4", "status": "deleted"},
        idempotency_key="delete-4",
    )

    replay = await bridge.preflight_create(
        scope=scope(),
        run_id="run-4",
        request_ref="request-4",
        request_fingerprint="fp-4",
        idempotency_key="idem-4",
    )
    assert replay.status == "replay"
    assert replay.response_payload is None
