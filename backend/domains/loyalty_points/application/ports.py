"""Repository port for the loyalty points domain.

Every family read is scoped by `(tenant_id, family_id)`. There is deliberately
**no** `top_families_by_points`, `rank_families`, `count_by_balance`,
`compare_families` or any other cross-family shape.

That absence is the enforcement mechanism for 宪章 R9(「不计算、不存储、不暴露
家庭总分与家庭排行」): a leaderboard screen is not forbidden by policy, it is
**unbuildable**, because there is no query that returns more than one family.
A guardrail test reflects over this Protocol to keep it that way.

The ledger gets `append_*` and no `update_*` / `delete_*`, for the same reason.
"""

from __future__ import annotations

from typing import Protocol

from ..domain.entities import (
    PointsAccount,
    PointsEarnRule,
    PointsLedgerEntry,
    PointsRedemption,
    RedemptionCatalogItem,
)


class LoyaltyPointsRepositoryPort(Protocol):
    async def commit(self) -> None:
        """Minimal unit of work. `save_*` / `append_*` only stage; a command
        commits once at the end so a redemption and its ledger row cannot land
        half-written."""
        ...

    # -- catalogue masters (no family scope: they hold no family facts) --
    async def save_earn_rule(self, entity: PointsEarnRule) -> None: ...
    async def load_earn_rule(self, rule_id: str) -> PointsEarnRule: ...
    async def find_earn_rule_by_ref(self, rule_ref: str) -> PointsEarnRule | None: ...
    async def list_earn_rules(self) -> list[PointsEarnRule]: ...

    async def save_redemption_item(self, entity: RedemptionCatalogItem) -> None: ...
    async def find_redemption_item_by_ref(self, item_ref: str) -> RedemptionCatalogItem | None: ...
    async def list_redemption_items(self) -> list[RedemptionCatalogItem]: ...

    # -- account --
    async def save_account(self, entity: PointsAccount) -> None: ...
    async def load_account(self, points_account_id: str) -> PointsAccount: ...
    async def find_account(self, tenant_id: str, family_id: str) -> PointsAccount | None: ...

    # -- ledger (append-only) --
    async def append_ledger_entry(self, entity: PointsLedgerEntry) -> None: ...
    async def list_ledger(self, tenant_id: str, family_id: str) -> list[PointsLedgerEntry]: ...
    async def find_ledger_entry_by_idempotency_key(
        self, tenant_id: str, family_id: str, idempotency_key: str
    ) -> PointsLedgerEntry | None: ...

    # -- redemption --
    async def save_redemption(self, entity: PointsRedemption) -> None: ...
    async def load_redemption(self, redemption_id: str) -> PointsRedemption: ...
    async def list_redemptions(self, tenant_id: str, family_id: str) -> list[PointsRedemption]: ...
    async def find_redemption_by_idempotency_key(
        self, tenant_id: str, family_id: str, idempotency_key: str
    ) -> PointsRedemption | None: ...
