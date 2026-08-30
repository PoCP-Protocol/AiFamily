"""Executable synthetic tests for replay lineage and deletion proof."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from poc.standalone_live_replay_sandbox.lineage import (
    SANDBOX_SOURCE,
    AssetKind,
    AssetState,
    DeletionIdempotencyConflict,
    InMemoryDeletionFixture,
    LineageBoundaryError,
    MediaAssetFixture,
    ReplayActor,
    ReplayLineageSandbox,
    ReplayRejected,
    ReplayScopeViolation,
)

NOW = datetime(2026, 8, 30, 23, 0, tzinfo=UTC)
ACTOR = ReplayActor("tenant.synthetic", "family.synthetic", "adult.1")
OTHER = ReplayActor("tenant.synthetic", "family.other", "adult.2")


def make_sandbox() -> tuple[ReplayLineageSandbox, InMemoryDeletionFixture]:
    deletion = InMemoryDeletionFixture()
    sandbox = ReplayLineageSandbox(deletion=deletion)
    sandbox.add_asset(
        MediaAssetFixture("asset.source", "tenant.synthetic", "family.synthetic", AssetKind.SOURCE)
    )
    for kind, ref in (
        (AssetKind.TRANSCODE, "asset.transcode"),
        (AssetKind.TRANSCRIPT, "asset.transcript"),
        (AssetKind.CHAPTERS, "asset.chapters"),
        (AssetKind.CACHE, "asset.cache"),
        (AssetKind.PROVIDER_COPY, "asset.provider"),
    ):
        sandbox.add_asset(
            MediaAssetFixture(
                ref,
                "tenant.synthetic",
                "family.synthetic",
                kind,
                parent_ref="asset.source",
            )
        )
    return sandbox, deletion


def test_replay_is_available_before_delete_and_lineage_is_complete() -> None:
    sandbox, _ = make_sandbox()
    assert (
        sandbox.replay(asset_ref="asset.provider", actor=ACTOR) == b"synthetic-media:asset.provider"
    )


def test_deletion_cascades_to_source_derivatives_cache_and_provider_copy() -> None:
    sandbox, deletion = make_sandbox()
    receipt = sandbox.delete_lineage(
        root_ref="asset.source",
        actor=ACTOR,
        deletion_ref="deletion.1",
        reason="purpose withdrawal",
        occurred_at=NOW,
        idempotency_key="delete.1",
    )
    assert receipt.affected_refs == (
        "asset.source",
        "asset.transcode",
        "asset.transcript",
        "asset.chapters",
        "asset.cache",
        "asset.provider",
    )
    assert len(deletion.receipts) == 1
    for asset_ref in receipt.affected_refs:
        with pytest.raises(ReplayRejected):
            sandbox.replay(asset_ref=asset_ref, actor=ACTOR)


def test_delete_replay_is_idempotent_and_different_lineage_key_fails() -> None:
    sandbox, deletion = make_sandbox()
    first = sandbox.delete_lineage(
        root_ref="asset.source",
        actor=ACTOR,
        deletion_ref="deletion.1",
        reason="withdrawal",
        occurred_at=NOW,
        idempotency_key="delete.replay",
    )
    second = sandbox.delete_lineage(
        root_ref="asset.source",
        actor=ACTOR,
        deletion_ref="deletion.other",
        reason="duplicate withdrawal",
        occurred_at=NOW,
        idempotency_key="delete.replay",
    )
    assert second == first
    assert len(deletion.receipts) == 1

    # A second root in the fixture makes a reused key a real conflict.
    other = ReplayLineageSandbox(deletion=deletion)
    other.add_asset(
        MediaAssetFixture("asset.second", "tenant.synthetic", "family.synthetic", AssetKind.SOURCE)
    )
    with pytest.raises(DeletionIdempotencyConflict):
        other.delete_lineage(
            root_ref="asset.second",
            actor=ACTOR,
            deletion_ref="deletion.second",
            reason="wrong reuse",
            occurred_at=NOW,
            idempotency_key="delete.replay",
        )


def test_scope_and_restart_never_revive_deleted_asset() -> None:
    sandbox, _ = make_sandbox()
    with pytest.raises(ReplayScopeViolation):
        sandbox.replay(asset_ref="asset.source", actor=OTHER)
    sandbox.delete_lineage(
        root_ref="asset.source",
        actor=ACTOR,
        deletion_ref="deletion.restart",
        reason="retention expiry",
        occurred_at=NOW,
        idempotency_key="delete.restart",
    )
    sandbox.restart()
    with pytest.raises(ReplayRejected):
        sandbox.replay(asset_ref="asset.source", actor=ACTOR)
    assert all(asset.state is AssetState.REVOKED for asset in sandbox._assets.values())


def test_deletion_failure_leaves_every_asset_available_for_retry() -> None:
    sandbox, deletion = make_sandbox()
    deletion.fail_next_commit = True
    with pytest.raises(RuntimeError, match="deletion commit failure"):
        sandbox.delete_lineage(
            root_ref="asset.source",
            actor=ACTOR,
            deletion_ref="deletion.failure",
            reason="simulated provider failure",
            occurred_at=NOW,
            idempotency_key="delete.failure",
        )
    assert all(asset.state is AssetState.AVAILABLE for asset in sandbox._assets.values())
    assert deletion.receipts == []


def test_fixture_boundary_is_explicit() -> None:
    with pytest.raises(LineageBoundaryError):
        MediaAssetFixture(
            "real.asset", "tenant.synthetic", "family.synthetic", AssetKind.SOURCE, source="real"
        )
    with pytest.raises(LineageBoundaryError):
        MediaAssetFixture(
            "unmarked.asset",
            "tenant.synthetic",
            "family.synthetic",
            AssetKind.SOURCE,
            fixture_only=False,
        )
    fixture = MediaAssetFixture(
        "asset.ok", "tenant.synthetic", "family.synthetic", AssetKind.SOURCE
    )
    assert fixture.source == SANDBOX_SOURCE
    assert fixture.fixture_only is True
