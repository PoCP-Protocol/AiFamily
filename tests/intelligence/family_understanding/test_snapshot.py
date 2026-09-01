from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from backend.intelligence.family_understanding.application import (
    FamilyUnderstandingApplication,
)
from backend.intelligence.family_understanding.snapshot import (
    ImmutableUnderstandingDraftReader,
    InMemoryUnderstandingDraftSnapshotStore,
    ReadUnderstandingDraftQuery,
    UnderstandingSnapshotRejected,
    problem_understanding_scope,
)
from tests.intelligence.family_understanding.test_application import (
    application_with,
    command,
    semantic_provider,
)


async def generated() -> tuple[FamilyUnderstandingApplication, object, ReadUnderstandingDraftQuery]:
    application = application_with(semantic_provider())
    view = await application.generate(command("一写作业就要反复提醒。", 1))
    query = ReadUnderstandingDraftQuery(
        understanding_run_ref=view.run_id,
        tenant_id="tenant-1",
        family_id="family-1",
        scope=problem_understanding_scope(tenant_id="tenant-1", family_id="family-1"),
        artifact_hash=view.artifact_hash,
        draft_version=view.version,
        provenance_ref=view.provenance_ref,
    )
    return application, view, query


async def test_generation_writes_server_owned_immutable_snapshot() -> None:
    application, view, query = await generated()

    snapshot = await application.read_immutable_snapshot(query)

    assert snapshot.understanding_run_ref == view.run_id
    assert snapshot.subject_ref == "guardian-1"
    assert snapshot.artifact_hash == view.artifact_hash
    assert snapshot.provenance_ref == view.provenance_ref
    assert snapshot.evidence_refs == ("guardian-input-1", "knowledge-reviewed-001")
    assert snapshot.draft.perspective.summary == view.summary
    assert snapshot.draft.status == "DRAFT"
    assert snapshot.may_mutate_business_state is False


@pytest.mark.parametrize(
    "change",
    [
        {"tenant_id": "other-tenant"},
        {"family_id": "other-family"},
        {"scope": "family://tenant-1/family-1/assessment"},
        {"scope": "family://tenant-1/family-1/problem-understanding/extra"},
    ],
)
async def test_cross_scope_and_non_exact_scope_fail_closed(change: dict[str, object]) -> None:
    application, _, query = await generated()

    with pytest.raises(UnderstandingSnapshotRejected) as error:
        await application.read_immutable_snapshot(replace(query, **change))

    assert error.value.reason == "SCOPE_MISMATCH"


@pytest.mark.parametrize(
    "change",
    [
        {"artifact_hash": "wrong-artifact"},
        {"draft_version": 2},
        {"provenance_ref": "air-provenance:v1:sha256:wrong"},
    ],
)
async def test_artifact_version_and_provenance_must_match_exactly(
    change: dict[str, object],
) -> None:
    application, _, query = await generated()

    with pytest.raises(UnderstandingSnapshotRejected) as error:
        await application.read_immutable_snapshot(replace(query, **change))

    assert error.value.reason == "BINDING_MISMATCH"


async def test_unknown_and_revoked_snapshots_fail_closed() -> None:
    application, _, query = await generated()

    with pytest.raises(UnderstandingSnapshotRejected) as missing:
        await application.read_immutable_snapshot(
            replace(query, understanding_run_ref="missing-run")
        )
    assert missing.value.reason == "SNAPSHOT_NOT_FOUND"

    await application.revoke_snapshot(query.understanding_run_ref)
    with pytest.raises(UnderstandingSnapshotRejected) as revoked:
        await application.read_immutable_snapshot(query)
    assert revoked.value.reason == "SNAPSHOT_REVOKED"


async def test_expired_snapshot_is_rejected_by_injected_reader_clock() -> None:
    application, _, query = await generated()
    snapshot = await application.read_immutable_snapshot(query)
    store = InMemoryUnderstandingDraftSnapshotStore()
    await store.put(snapshot)
    reader = ImmutableUnderstandingDraftReader(
        store, clock=lambda: datetime(2100, 1, 1, tzinfo=UTC)
    )

    with pytest.raises(UnderstandingSnapshotRejected) as expired:
        await reader.read(query)

    assert expired.value.reason == "SNAPSHOT_EXPIRED"


async def test_run_ref_cannot_be_rebound_to_different_snapshot() -> None:
    application, _, query = await generated()
    snapshot = await application.read_immutable_snapshot(query)
    store = InMemoryUnderstandingDraftSnapshotStore()
    await store.put(snapshot)

    with pytest.raises(UnderstandingSnapshotRejected) as conflict:
        await store.put(replace(snapshot, request_hash="different-request"))

    assert conflict.value.reason == "RUN_REF_CONFLICT"
