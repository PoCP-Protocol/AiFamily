"""In-memory `LoyaltyPointsRepositoryPort` implementation.

Exists so the application layer can be tested without SQLAlchemy, and so the
acceptance chain runs twice — once here, once against the real ORM — proving the
commands depend on the port rather than on a persistence quirk.

`commit()` is a no-op: there is no transaction to close. That is a real
difference from the SQLAlchemy repository, and the reason the SQLite pass exists
alongside this one.
"""

from __future__ import annotations

from ..domain.entities import (
    PointsAccount,
    PointsEarnRule,
    PointsLedgerEntry,
    PointsRedemption,
    RedemptionCatalogItem,
)
from ..domain.errors import LoyaltyPointsNotFoundError


class FakeLoyaltyPointsRepository:
    def __init__(self) -> None:
        self.earn_rules: dict[str, PointsEarnRule] = {}
        self.redemption_items: dict[str, RedemptionCatalogItem] = {}
        self.accounts: dict[str, PointsAccount] = {}
        self.ledger: dict[str, PointsLedgerEntry] = {}
        self.redemptions: dict[str, PointsRedemption] = {}

    async def commit(self) -> None:
        return None

    @staticmethod
    def _scoped(store: dict, tenant_id: str, family_id: str) -> list:
        return [e for e in store.values() if e.tenant_id == tenant_id and e.family_id == family_id]

    @staticmethod
    def _by_key(store: dict, tenant_id: str, family_id: str, key: str):
        for entity in store.values():
            if (
                entity.tenant_id == tenant_id
                and entity.family_id == family_id
                and entity.idempotency_key == key
            ):
                return entity
        return None

    # -- catalogue masters --
    async def save_earn_rule(self, entity: PointsEarnRule) -> None:
        self.earn_rules[entity.rule_id] = entity

    async def load_earn_rule(self, rule_id: str) -> PointsEarnRule:
        if rule_id not in self.earn_rules:
            raise LoyaltyPointsNotFoundError("earn_rule_not_found")
        return self.earn_rules[rule_id]

    async def find_earn_rule_by_ref(self, rule_ref: str) -> PointsEarnRule | None:
        matches = [r for r in self.earn_rules.values() if r.rule_ref == rule_ref]
        return max(matches, key=lambda r: r.version_no) if matches else None

    async def list_earn_rules(self) -> list[PointsEarnRule]:
        return list(self.earn_rules.values())

    async def save_redemption_item(self, entity: RedemptionCatalogItem) -> None:
        self.redemption_items[entity.item_id] = entity

    async def find_redemption_item_by_ref(self, item_ref: str) -> RedemptionCatalogItem | None:
        matches = [i for i in self.redemption_items.values() if i.item_ref == item_ref]
        return max(matches, key=lambda i: i.version_no) if matches else None

    async def list_redemption_items(self) -> list[RedemptionCatalogItem]:
        return list(self.redemption_items.values())

    # -- account --
    async def save_account(self, entity: PointsAccount) -> None:
        self.accounts[entity.points_account_id] = entity

    async def load_account(self, points_account_id: str) -> PointsAccount:
        if points_account_id not in self.accounts:
            raise LoyaltyPointsNotFoundError("points_account_not_found")
        return self.accounts[points_account_id]

    async def find_account(self, tenant_id: str, family_id: str) -> PointsAccount | None:
        scoped = self._scoped(self.accounts, tenant_id, family_id)
        return scoped[0] if scoped else None

    # -- ledger (append-only) --
    async def append_ledger_entry(self, entity: PointsLedgerEntry) -> None:
        self.ledger[entity.ledger_id] = entity

    async def list_ledger(self, tenant_id: str, family_id: str) -> list[PointsLedgerEntry]:
        return self._scoped(self.ledger, tenant_id, family_id)

    async def find_ledger_entry_by_idempotency_key(
        self, tenant_id: str, family_id: str, idempotency_key: str
    ) -> PointsLedgerEntry | None:
        return self._by_key(self.ledger, tenant_id, family_id, idempotency_key)

    # -- redemption --
    async def save_redemption(self, entity: PointsRedemption) -> None:
        self.redemptions[entity.redemption_id] = entity

    async def load_redemption(self, redemption_id: str) -> PointsRedemption:
        if redemption_id not in self.redemptions:
            raise LoyaltyPointsNotFoundError("redemption_not_found")
        return self.redemptions[redemption_id]

    async def list_redemptions(self, tenant_id: str, family_id: str) -> list[PointsRedemption]:
        return self._scoped(self.redemptions, tenant_id, family_id)

    async def find_redemption_by_idempotency_key(
        self, tenant_id: str, family_id: str, idempotency_key: str
    ) -> PointsRedemption | None:
        return self._by_key(self.redemptions, tenant_id, family_id, idempotency_key)
