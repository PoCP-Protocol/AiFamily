"""Synthetic H-LIVE-05 replay lineage and deletion contract.

This is a disposable contract/mock for proving deletion propagation before a
real Platform Deletion adapter is available.  It never stores real media and
does not create a second deletion ledger.  The canonical deletion boundary is
represented by a port; the in-memory implementation exists only for replayable
tests.

The covered behavior is: after a purpose withdrawal or deletion request, an
adult can no longer access the source asset or any derived/provider copy, and
the result is idempotently receipted.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

SANDBOX_SOURCE = "SANDBOX_SYNTHETIC"


class LineageBoundaryError(ValueError):
    """A synthetic asset violates its explicit sandbox boundary."""


class ReplayRejected(RuntimeError):
    """The requested replay operation is not allowed."""


class ReplayScopeViolation(ReplayRejected):
    """A replay request crossed its tenant/family scope."""


class DeletionIdempotencyConflict(ReplayRejected):
    """A deletion key was reused for a different lineage."""


class AssetKind(StrEnum):
    SOURCE = "SOURCE"
    TRANSCODE = "TRANSCODE"
    TRANSCRIPT = "TRANSCRIPT"
    CHAPTERS = "CHAPTERS"
    CACHE = "CACHE"
    PROVIDER_COPY = "PROVIDER_COPY"


class AssetState(StrEnum):
    AVAILABLE = "AVAILABLE"
    REVOKED = "REVOKED"
    DELETED = "DELETED"


@dataclass(frozen=True, slots=True)
class ReplayActor:
    tenant_id: str
    family_id: str
    actor_id: str

    def __post_init__(self) -> None:
        if not all((self.tenant_id, self.family_id, self.actor_id)):
            raise ValueError("replay actor scope fields must not be empty")


@dataclass(slots=True)
class MediaAssetFixture:
    asset_ref: str
    tenant_id: str
    family_id: str
    kind: AssetKind
    state: AssetState = AssetState.AVAILABLE
    parent_ref: str | None = None
    source: str = SANDBOX_SOURCE
    fixture_only: bool = True

    def __post_init__(self) -> None:
        if not self.fixture_only or self.source != SANDBOX_SOURCE:
            raise LineageBoundaryError("media fixture must be explicitly synthetic")
        if not all((self.asset_ref, self.tenant_id, self.family_id)):
            raise ValueError("media asset identity and scope must not be empty")
        if self.kind is AssetKind.SOURCE and self.parent_ref is not None:
            raise ValueError("source asset cannot have a parent")
        if self.kind is not AssetKind.SOURCE and not self.parent_ref:
            raise ValueError("derived asset must identify its parent")


@dataclass(frozen=True, slots=True)
class DeletionReceipt:
    deletion_ref: str
    root_ref: str
    affected_refs: tuple[str, ...]
    reason: str
    occurred_at: datetime
    source: str = SANDBOX_SOURCE
    fixture_only: bool = True


class CanonicalDeletionPort(Protocol):
    """Production-owned deletion/retention cascade boundary."""

    def commit_deletion(
        self,
        *,
        asset_refs: tuple[str, ...],
        deletion_ref: str,
        tenant_id: str,
        family_id: str,
        reason: str,
        occurred_at: datetime,
        idempotency_key: str,
    ) -> DeletionReceipt: ...


class InMemoryDeletionFixture:
    """Sandbox test double; it is not a canonical deletion ledger."""

    def __init__(self) -> None:
        self.receipts: list[DeletionReceipt] = []
        self._by_key: dict[str, tuple[tuple[str, ...], DeletionReceipt]] = {}
        self.fail_next_commit = False

    def commit_deletion(
        self,
        *,
        asset_refs: tuple[str, ...],
        deletion_ref: str,
        tenant_id: str,
        family_id: str,
        reason: str,
        occurred_at: datetime,
        idempotency_key: str,
    ) -> DeletionReceipt:
        if self.fail_next_commit:
            self.fail_next_commit = False
            raise RuntimeError("synthetic deletion commit failure")
        previous = self._by_key.get(idempotency_key)
        if previous is not None:
            if previous[0] != asset_refs:
                raise DeletionIdempotencyConflict("deletion key was reused for another lineage")
            return previous[1]
        receipt = DeletionReceipt(
            deletion_ref=deletion_ref,
            root_ref=asset_refs[0],
            affected_refs=asset_refs,
            reason=reason,
            occurred_at=occurred_at,
        )
        self._by_key[idempotency_key] = (asset_refs, receipt)
        self.receipts.append(receipt)
        return receipt


class ReplayLineageSandbox:
    """A synthetic lineage graph with canonical deletion delegation."""

    def __init__(self, *, deletion: CanonicalDeletionPort) -> None:
        self._deletion = deletion
        self._assets: dict[str, MediaAssetFixture] = {}
        self._deletion_keys: dict[str, DeletionReceipt] = {}

    def add_asset(self, asset: MediaAssetFixture) -> None:
        if asset.asset_ref in self._assets:
            raise ValueError("asset already exists")
        if asset.parent_ref is not None:
            parent = self._assets.get(asset.parent_ref)
            if parent is None:
                raise ReplayRejected("parent asset is not registered")
            if parent.tenant_id != asset.tenant_id or parent.family_id != asset.family_id:
                raise ReplayScopeViolation("lineage parent crossed tenant/family scope")
        self._assets[asset.asset_ref] = asset

    def replay(self, *, asset_ref: str, actor: ReplayActor) -> bytes:
        """Return synthetic bytes only while every lineage node is available."""

        asset = self._asset(asset_ref)
        self._assert_scope(asset, actor)
        lineage = self._lineage(asset_ref)
        if any(node.state is not AssetState.AVAILABLE for node in lineage):
            raise ReplayRejected("replay unavailable after revocation or deletion")
        return f"synthetic-media:{asset_ref}".encode()

    def delete_lineage(
        self,
        *,
        root_ref: str,
        actor: ReplayActor,
        deletion_ref: str,
        reason: str,
        occurred_at: datetime,
        idempotency_key: str,
    ) -> DeletionReceipt:
        """Cascade deletion through all derived and provider-copy nodes."""

        root = self._asset(root_ref)
        self._assert_scope(root, actor)
        if not reason.strip() or not deletion_ref or not idempotency_key:
            raise ValueError("deletion reference, reason and idempotency key are required")
        previous = self._deletion_keys.get(idempotency_key)
        if previous is not None:
            return previous
        affected = tuple(
            asset.asset_ref
            for asset in self._assets.values()
            if self._belongs_to_root(asset, root_ref)
        )
        receipt = self._deletion.commit_deletion(
            asset_refs=affected,
            deletion_ref=deletion_ref,
            tenant_id=actor.tenant_id,
            family_id=actor.family_id,
            reason=reason.strip(),
            occurred_at=occurred_at,
            idempotency_key=idempotency_key,
        )
        for asset_ref in affected:
            self._assets[asset_ref].state = AssetState.DELETED
        self._deletion_keys[idempotency_key] = receipt
        return receipt

    def restart(self) -> None:
        """Reconcile from the deletion boundary; revoked assets stay unavailable."""

        for asset in self._assets.values():
            if asset.state is AssetState.DELETED:
                asset.state = AssetState.REVOKED

    def _asset(self, asset_ref: str) -> MediaAssetFixture:
        try:
            return self._assets[asset_ref]
        except KeyError as exc:
            raise ReplayRejected("media asset not found") from exc

    def _lineage(self, asset_ref: str) -> tuple[MediaAssetFixture, ...]:
        lineage: list[MediaAssetFixture] = []
        current = self._asset(asset_ref)
        while True:
            lineage.append(current)
            if current.parent_ref is None:
                return tuple(lineage)
            current = self._asset(current.parent_ref)

    def _belongs_to_root(self, asset: MediaAssetFixture, root_ref: str) -> bool:
        current = asset
        while current.parent_ref is not None:
            if current.parent_ref == root_ref:
                return True
            current = self._asset(current.parent_ref)
        return current.asset_ref == root_ref

    @staticmethod
    def _assert_scope(asset: MediaAssetFixture, actor: ReplayActor) -> None:
        if asset.tenant_id != actor.tenant_id or asset.family_id != actor.family_id:
            raise ReplayScopeViolation("replay request crossed tenant/family scope")
