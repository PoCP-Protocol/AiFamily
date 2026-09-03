"""Durable pre-call budget reservation and post-call cost reconciliation."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol
from uuid import uuid4

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Integer, String, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .contracts import StructuredRequest, TokenUsage


class ModelBudgetError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class BudgetReservationStatus(StrEnum):
    RESERVED = "RESERVED"
    SETTLED = "SETTLED"
    CONSUMED_UNCERTAIN = "CONSUMED_UNCERTAIN"
    RELEASED = "RELEASED"


class ModelBudgetBase(DeclarativeBase):
    """Metadata-only budget persistence boundary."""


class ModelBudgetAccountRow(ModelBudgetBase):
    __tablename__ = "ai_model_budget_accounts"

    tenant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    environment: Mapped[str] = mapped_column(String(64), primary_key=True)
    period_key: Mapped[str] = mapped_column(String(32), primary_key=True)
    policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    limit_microusd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reserved_microusd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    spent_microusd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ModelBudgetReservationRow(ModelBudgetBase):
    __tablename__ = "ai_model_budget_reservations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('RESERVED', 'SETTLED', 'CONSUMED_UNCERTAIN', 'RELEASED')",
            name="ck_ai_model_budget_reservation_status",
        ),
    )

    reservation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    reservation_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    environment: Mapped[str] = mapped_column(String(64), nullable=False)
    period_key: Mapped[str] = mapped_column(String(32), nullable=False)
    request_ref: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provider_id: Mapped[str] = mapped_column(String(128), nullable=False)
    model: Mapped[str] = mapped_column(String(256), nullable=False)
    route_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    rate_card_version: Mapped[str] = mapped_column(String(128), nullable=False)
    release_set_id: Mapped[str | None] = mapped_column(String(64), index=True)
    bundle_id: Mapped[str | None] = mapped_column(String(64))
    deployment_receipt_id: Mapped[str | None] = mapped_column(String(64))
    runtime_config_digest: Mapped[str | None] = mapped_column(String(64))
    deployment_sequence: Mapped[int | None] = mapped_column(Integer)
    control_id: Mapped[str | None] = mapped_column(String(128))
    reserved_microusd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    actual_microusd: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    outcome_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


@dataclass(frozen=True, slots=True)
class ModelRate:
    provider_id: str
    model: str
    prompt_microusd_per_1k: int
    completion_microusd_per_1k: int
    media_item_microusd: int = 0

    def __post_init__(self) -> None:
        if not self.provider_id or not self.model:
            raise ModelBudgetError("MODEL_RATE_IDENTITY_REQUIRED")
        values = (
            self.prompt_microusd_per_1k,
            self.completion_microusd_per_1k,
            self.media_item_microusd,
        )
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in values
        ):
            raise ModelBudgetError("MODEL_RATE_VALUE_INVALID")

    def price(self, prompt_tokens: int, completion_tokens: int, media_items: int) -> int:
        values = (prompt_tokens, completion_tokens, media_items)
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in values
        ):
            raise ModelBudgetError("MODEL_USAGE_VALUE_INVALID")
        prompt = (self.prompt_microusd_per_1k * prompt_tokens + 999) // 1000
        completion = (self.completion_microusd_per_1k * completion_tokens + 999) // 1000
        return prompt + completion + self.media_item_microusd * media_items


@dataclass(frozen=True, slots=True)
class ModelRateCard:
    version: str
    rates: tuple[ModelRate, ...]
    effective_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        if not self.version or not self.rates:
            raise ModelBudgetError("MODEL_RATE_CARD_REQUIRED")
        _aware(self.effective_at)
        _aware(self.expires_at)
        if self.expires_at <= self.effective_at:
            raise ModelBudgetError("MODEL_RATE_CARD_WINDOW_INVALID")
        identities = [(rate.provider_id, rate.model) for rate in self.rates]
        if len(set(identities)) != len(identities):
            raise ModelBudgetError("MODEL_RATE_CARD_DUPLICATE_RATE")

    def resolve(self, provider_id: str, model: str, *, now: datetime) -> ModelRate:
        _aware(now)
        if not self.effective_at <= now < self.expires_at:
            raise ModelBudgetError("MODEL_RATE_CARD_INACTIVE")
        for rate in self.rates:
            if (rate.provider_id, rate.model) == (provider_id, model):
                return rate
        raise ModelBudgetError("MODEL_RATE_MISSING")

    @property
    def configuration_digest(self) -> str:
        return _digest(
            {
                "version": self.version,
                "effective_at": self.effective_at.isoformat(),
                "expires_at": self.expires_at.isoformat(),
                "rates": [
                    {
                        "provider_id": rate.provider_id,
                        "model": rate.model,
                        "prompt_microusd_per_1k": rate.prompt_microusd_per_1k,
                        "completion_microusd_per_1k": rate.completion_microusd_per_1k,
                        "media_item_microusd": rate.media_item_microusd,
                    }
                    for rate in sorted(
                        self.rates,
                        key=lambda item: (item.provider_id, item.model),
                    )
                ],
            }
        )


@dataclass(frozen=True, slots=True)
class ModelBudgetPolicy:
    version: str
    rate_card_version: str
    per_request_limit_microusd: int
    period_limit_microusd: int
    max_completion_tokens: int
    prompt_overhead_tokens: int = 256

    def __post_init__(self) -> None:
        if not self.version or not self.rate_card_version:
            raise ModelBudgetError("MODEL_BUDGET_POLICY_REQUIRED")
        values = (
            self.per_request_limit_microusd,
            self.period_limit_microusd,
            self.max_completion_tokens,
            self.prompt_overhead_tokens,
        )
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value <= 0
            for value in values
        ):
            raise ModelBudgetError("MODEL_BUDGET_POLICY_VALUE_INVALID")
        if self.per_request_limit_microusd > self.period_limit_microusd:
            raise ModelBudgetError("MODEL_REQUEST_BUDGET_EXCEEDS_PERIOD")

    @property
    def configuration_digest(self) -> str:
        return _digest(
            {
                "version": self.version,
                "rate_card_version": self.rate_card_version,
                "per_request_limit_microusd": self.per_request_limit_microusd,
                "period_limit_microusd": self.period_limit_microusd,
                "max_completion_tokens": self.max_completion_tokens,
                "prompt_overhead_tokens": self.prompt_overhead_tokens,
            }
        )


@dataclass(frozen=True, slots=True)
class ModelBudgetAccount:
    tenant_id: str
    environment: str
    period_key: str
    policy_version: str
    limit_microusd: int
    reserved_microusd: int
    spent_microusd: int
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ModelBudgetReservation:
    reservation_id: str
    reservation_key: str
    tenant_id: str
    environment: str
    period_key: str
    request_ref: str
    provider_id: str
    model: str
    route_sequence: int
    policy_version: str
    rate_card_version: str
    reserved_microusd: int
    actual_microusd: int | None
    status: BudgetReservationStatus
    outcome_code: str | None
    created_at: datetime
    updated_at: datetime
    release_set_id: str | None = None
    bundle_id: str | None = None
    deployment_receipt_id: str | None = None
    runtime_config_digest: str | None = None
    deployment_sequence: int | None = None
    control_id: str | None = None


class ModelBudgetStore(Protocol):
    durability_mode: str

    async def provision_account(self, account: ModelBudgetAccount) -> ModelBudgetAccount: ...

    async def reserve(self, reservation: ModelBudgetReservation) -> ModelBudgetReservation: ...

    async def settle(
        self, reservation_id: str, *, actual_microusd: int, now: datetime
    ) -> ModelBudgetReservation: ...

    async def consume_uncertain(
        self, reservation_id: str, *, outcome_code: str, now: datetime
    ) -> ModelBudgetReservation: ...

    async def release(
        self, reservation_id: str, *, outcome_code: str, now: datetime
    ) -> ModelBudgetReservation: ...

    async def get(self, reservation_id: str) -> ModelBudgetReservation | None: ...

    async def get_account(
        self, tenant_id: str, environment: str, period_key: str
    ) -> ModelBudgetAccount | None: ...


class InMemoryModelBudgetStore:
    durability_mode = "IN_MEMORY"

    def __init__(self, accounts: tuple[ModelBudgetAccount, ...] = ()) -> None:
        self.accounts: dict[tuple[str, str, str], ModelBudgetAccount] = {}
        self.reservations: dict[str, ModelBudgetReservation] = {}
        self._by_key: dict[str, str] = {}
        self._lock = asyncio.Lock()
        for account in accounts:
            _validate_account(account)
            key = _account_key(account)
            if key in self.accounts:
                raise ModelBudgetError("MODEL_BUDGET_ACCOUNT_CONFLICT")
            self.accounts[key] = account

    async def provision_account(self, account: ModelBudgetAccount) -> ModelBudgetAccount:
        _validate_account(account)
        async with self._lock:
            key = _account_key(account)
            existing = self.accounts.get(key)
            if existing is not None and existing != account:
                raise ModelBudgetError("MODEL_BUDGET_ACCOUNT_CONFLICT")
            self.accounts[key] = existing or account
            return existing or account

    async def reserve(self, reservation: ModelBudgetReservation) -> ModelBudgetReservation:
        _validate_reservation(reservation)
        async with self._lock:
            existing_id = self._by_key.get(reservation.reservation_key)
            if existing_id is not None:
                existing = self.reservations[existing_id]
                if not _same_reservation_request(existing, reservation):
                    raise ModelBudgetError("MODEL_BUDGET_RESERVATION_CONFLICT")
                return existing
            key = _reservation_account_key(reservation)
            account = self.accounts.get(key)
            if account is None:
                raise ModelBudgetError("MODEL_BUDGET_ACCOUNT_NOT_PROVISIONED")
            _assert_account_policy(account, reservation)
            if (
                account.reserved_microusd
                + account.spent_microusd
                + reservation.reserved_microusd
                > account.limit_microusd
            ):
                raise ModelBudgetError("MODEL_BUDGET_EXHAUSTED")
            self.accounts[key] = replace(
                account,
                reserved_microusd=(
                    account.reserved_microusd + reservation.reserved_microusd
                ),
                updated_at=reservation.updated_at,
            )
            self.reservations[reservation.reservation_id] = reservation
            self._by_key[reservation.reservation_key] = reservation.reservation_id
            return reservation

    async def settle(
        self, reservation_id: str, *, actual_microusd: int, now: datetime
    ) -> ModelBudgetReservation:
        return await self._finish(
            reservation_id,
            actual_microusd=actual_microusd,
            status=BudgetReservationStatus.SETTLED,
            outcome_code=None,
            now=now,
        )

    async def consume_uncertain(
        self, reservation_id: str, *, outcome_code: str, now: datetime
    ) -> ModelBudgetReservation:
        reservation = self.reservations.get(reservation_id)
        if reservation is None:
            raise ModelBudgetError("MODEL_BUDGET_RESERVATION_NOT_FOUND")
        return await self._finish(
            reservation_id,
            actual_microusd=reservation.reserved_microusd,
            status=BudgetReservationStatus.CONSUMED_UNCERTAIN,
            outcome_code=outcome_code,
            now=now,
        )

    async def release(
        self, reservation_id: str, *, outcome_code: str, now: datetime
    ) -> ModelBudgetReservation:
        return await self._finish(
            reservation_id,
            actual_microusd=0,
            status=BudgetReservationStatus.RELEASED,
            outcome_code=outcome_code,
            now=now,
        )

    async def get(self, reservation_id: str) -> ModelBudgetReservation | None:
        return self.reservations.get(reservation_id)

    async def get_account(
        self, tenant_id: str, environment: str, period_key: str
    ) -> ModelBudgetAccount | None:
        return self.accounts.get((tenant_id, environment, period_key))

    async def _finish(
        self,
        reservation_id: str,
        *,
        actual_microusd: int,
        status: BudgetReservationStatus,
        outcome_code: str | None,
        now: datetime,
    ) -> ModelBudgetReservation:
        _validate_actual(actual_microusd, now)
        async with self._lock:
            reservation = self.reservations.get(reservation_id)
            if reservation is None:
                raise ModelBudgetError("MODEL_BUDGET_RESERVATION_NOT_FOUND")
            if reservation.status is not BudgetReservationStatus.RESERVED:
                if (
                    reservation.status is status
                    and reservation.actual_microusd == actual_microusd
                    and reservation.outcome_code == outcome_code
                ):
                    return reservation
                raise ModelBudgetError("MODEL_BUDGET_SETTLEMENT_CONFLICT")
            if actual_microusd > reservation.reserved_microusd:
                raise ModelBudgetError("MODEL_BUDGET_ACTUAL_EXCEEDS_RESERVATION")
            key = _reservation_account_key(reservation)
            account = self.accounts[key]
            updated = replace(
                reservation,
                actual_microusd=actual_microusd,
                status=status,
                outcome_code=outcome_code,
                updated_at=now,
            )
            self.reservations[reservation_id] = updated
            self.accounts[key] = replace(
                account,
                reserved_microusd=(
                    account.reserved_microusd - reservation.reserved_microusd
                ),
                spent_microusd=account.spent_microusd + actual_microusd,
                updated_at=now,
            )
            return updated


class SqlAlchemyModelBudgetStore:
    durability_mode = "DURABLE"

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        if not isinstance(session_factory, async_sessionmaker):
            raise TypeError("session_factory must be an async_sessionmaker")
        self._session_factory = session_factory

    async def provision_account(self, account: ModelBudgetAccount) -> ModelBudgetAccount:
        _validate_account(account)
        async with self._session_factory() as session, session.begin():
            row = await session.get(
                ModelBudgetAccountRow,
                (account.tenant_id, account.environment, account.period_key),
            )
            if row is not None:
                existing = _stored_account(row)
                if existing != account:
                    raise ModelBudgetError("MODEL_BUDGET_ACCOUNT_CONFLICT")
                return existing
            session.add(_account_row(account))
        return account

    async def reserve(self, reservation: ModelBudgetReservation) -> ModelBudgetReservation:
        _validate_reservation(reservation)
        async with self._session_factory() as session, session.begin():
            existing_row = await session.scalar(
                select(ModelBudgetReservationRow).where(
                    ModelBudgetReservationRow.reservation_key
                    == reservation.reservation_key
                )
            )
            if existing_row is not None:
                existing = _stored_reservation(existing_row)
                if not _same_reservation_request(existing, reservation):
                    raise ModelBudgetError("MODEL_BUDGET_RESERVATION_CONFLICT")
                return existing
            account_row = await session.scalar(
                select(ModelBudgetAccountRow)
                .where(
                    ModelBudgetAccountRow.tenant_id == reservation.tenant_id,
                    ModelBudgetAccountRow.environment == reservation.environment,
                    ModelBudgetAccountRow.period_key == reservation.period_key,
                )
                .with_for_update()
            )
            if account_row is None:
                raise ModelBudgetError("MODEL_BUDGET_ACCOUNT_NOT_PROVISIONED")
            account = _stored_account(account_row)
            _assert_account_policy(account, reservation)
            if (
                account.reserved_microusd
                + account.spent_microusd
                + reservation.reserved_microusd
                > account.limit_microusd
            ):
                raise ModelBudgetError("MODEL_BUDGET_EXHAUSTED")
            account_row.reserved_microusd += reservation.reserved_microusd
            account_row.updated_at = reservation.updated_at
            session.add(_reservation_row(reservation))
            await session.flush()
        return reservation

    async def settle(
        self, reservation_id: str, *, actual_microusd: int, now: datetime
    ) -> ModelBudgetReservation:
        return await self._finish(
            reservation_id,
            actual_microusd=actual_microusd,
            status=BudgetReservationStatus.SETTLED,
            outcome_code=None,
            now=now,
        )

    async def consume_uncertain(
        self, reservation_id: str, *, outcome_code: str, now: datetime
    ) -> ModelBudgetReservation:
        async with self._session_factory() as session:
            row = await session.get(ModelBudgetReservationRow, reservation_id)
            if row is None:
                raise ModelBudgetError("MODEL_BUDGET_RESERVATION_NOT_FOUND")
            reserved = row.reserved_microusd
        return await self._finish(
            reservation_id,
            actual_microusd=reserved,
            status=BudgetReservationStatus.CONSUMED_UNCERTAIN,
            outcome_code=outcome_code,
            now=now,
        )

    async def release(
        self, reservation_id: str, *, outcome_code: str, now: datetime
    ) -> ModelBudgetReservation:
        return await self._finish(
            reservation_id,
            actual_microusd=0,
            status=BudgetReservationStatus.RELEASED,
            outcome_code=outcome_code,
            now=now,
        )

    async def get(self, reservation_id: str) -> ModelBudgetReservation | None:
        async with self._session_factory() as session:
            row = await session.get(ModelBudgetReservationRow, reservation_id)
            return None if row is None else _stored_reservation(row)

    async def get_account(
        self, tenant_id: str, environment: str, period_key: str
    ) -> ModelBudgetAccount | None:
        async with self._session_factory() as session:
            row = await session.get(
                ModelBudgetAccountRow,
                (tenant_id, environment, period_key),
            )
            return None if row is None else _stored_account(row)

    async def _finish(
        self,
        reservation_id: str,
        *,
        actual_microusd: int,
        status: BudgetReservationStatus,
        outcome_code: str | None,
        now: datetime,
    ) -> ModelBudgetReservation:
        _validate_actual(actual_microusd, now)
        async with self._session_factory() as session, session.begin():
            row = await session.scalar(
                select(ModelBudgetReservationRow)
                .where(ModelBudgetReservationRow.reservation_id == reservation_id)
                .with_for_update()
            )
            if row is None:
                raise ModelBudgetError("MODEL_BUDGET_RESERVATION_NOT_FOUND")
            reservation = _stored_reservation(row)
            if reservation.status is not BudgetReservationStatus.RESERVED:
                if (
                    reservation.status is status
                    and reservation.actual_microusd == actual_microusd
                    and reservation.outcome_code == outcome_code
                ):
                    return reservation
                raise ModelBudgetError("MODEL_BUDGET_SETTLEMENT_CONFLICT")
            if actual_microusd > reservation.reserved_microusd:
                raise ModelBudgetError("MODEL_BUDGET_ACTUAL_EXCEEDS_RESERVATION")
            account_row = await session.scalar(
                select(ModelBudgetAccountRow)
                .where(
                    ModelBudgetAccountRow.tenant_id == reservation.tenant_id,
                    ModelBudgetAccountRow.environment == reservation.environment,
                    ModelBudgetAccountRow.period_key == reservation.period_key,
                )
                .with_for_update()
            )
            if account_row is None:  # pragma: no cover - FK-less corruption guard
                raise ModelBudgetError("MODEL_BUDGET_ACCOUNT_NOT_PROVISIONED")
            account_row.reserved_microusd -= reservation.reserved_microusd
            account_row.spent_microusd += actual_microusd
            account_row.updated_at = now
            row.actual_microusd = actual_microusd
            row.status = status.value
            row.outcome_code = outcome_code
            row.updated_at = now
            await session.flush()
            return _stored_reservation(row)


@dataclass(frozen=True, slots=True)
class ModelBudgetRuntime:
    store: ModelBudgetStore
    rate_card: ModelRateCard
    policy: ModelBudgetPolicy
    environment: str
    clock: Callable[[], datetime] | None = None

    def __post_init__(self) -> None:
        if not self.environment:
            raise ModelBudgetError("MODEL_BUDGET_ENVIRONMENT_REQUIRED")
        if self.policy.rate_card_version != self.rate_card.version:
            raise ModelBudgetError("MODEL_BUDGET_RATE_CARD_MISMATCH")

    async def reserve(
        self,
        request: StructuredRequest,
        *,
        provider_id: str,
        model: str,
        route_sequence: int,
    ) -> ModelBudgetReservation:
        if not request.request_id or not request.tenant_id or not request.family_id:
            raise ModelBudgetError("MODEL_BUDGET_REQUEST_SCOPE_REQUIRED")
        now = self._now()
        rate = self.rate_card.resolve(provider_id, model, now=now)
        estimated_prompt = _estimate_prompt_tokens(
            request, overhead=self.policy.prompt_overhead_tokens
        )
        estimated_cost = rate.price(
            estimated_prompt,
            self.policy.max_completion_tokens,
            len(request.media_inputs),
        )
        if estimated_cost > self.policy.per_request_limit_microusd:
            raise ModelBudgetError("MODEL_REQUEST_BUDGET_EXCEEDED")
        key_payload = {
            "tenant_id": request.tenant_id,
            "request_id": request.request_id,
            "provider_id": provider_id,
            "route_sequence": route_sequence,
            "policy_version": self.policy.version,
            # A failed external attempt may be retried under the same request id.
            # Each actual provider attempt needs a separate hold and charge;
            # request-level replay prevention remains owned by the run ledger.
            "attempt_nonce": uuid4().hex,
        }
        reservation_key = _digest(key_payload)
        request_ref = hashlib.sha256(request.request_id.encode()).hexdigest()
        reservation = ModelBudgetReservation(
            reservation_id=reservation_key,
            reservation_key=reservation_key,
            tenant_id=request.tenant_id,
            environment=self.environment,
            period_key=now.date().isoformat(),
            request_ref=request_ref,
            provider_id=provider_id,
            model=model,
            route_sequence=route_sequence,
            policy_version=self.policy.version,
            rate_card_version=self.rate_card.version,
            reserved_microusd=self.policy.per_request_limit_microusd,
            actual_microusd=None,
            status=BudgetReservationStatus.RESERVED,
            outcome_code=None,
            created_at=now,
            updated_at=now,
            release_set_id=(
                request.release_binding.release_set_id
                if request.release_binding is not None
                else None
            ),
            bundle_id=(
                request.release_binding.bundle_id_for(provider_id)
                if request.release_binding is not None
                else None
            ),
            deployment_receipt_id=(
                request.release_binding.deployment_receipt_id
                if request.release_binding is not None
                else None
            ),
            runtime_config_digest=(
                request.release_binding.runtime_config_digest
                if request.release_binding is not None
                else None
            ),
            deployment_sequence=(
                request.release_binding.deployment_sequence
                if request.release_binding is not None
                else None
            ),
            control_id=(
                request.release_binding.control_id
                if request.release_binding is not None
                else None
            ),
        )
        return await self.store.reserve(reservation)

    async def settle(
        self,
        reservation: ModelBudgetReservation,
        *,
        usage: TokenUsage | None,
        media_item_count: int,
    ) -> ModelBudgetReservation:
        now = self._now()
        if usage is None:
            return await self.store.consume_uncertain(
                reservation.reservation_id,
                outcome_code="MODEL_USAGE_MISSING",
                now=now,
            )
        rate = self.rate_card.resolve(
            reservation.provider_id, reservation.model, now=now
        )
        actual = rate.price(
            usage.prompt_tokens,
            usage.completion_tokens,
            media_item_count,
        )
        return await self.store.settle(
            reservation.reservation_id,
            actual_microusd=actual,
            now=now,
        )

    async def consume_uncertain(
        self, reservation: ModelBudgetReservation, *, outcome_code: str
    ) -> ModelBudgetReservation:
        return await self.store.consume_uncertain(
            reservation.reservation_id,
            outcome_code=outcome_code,
            now=self._now(),
        )

    async def release(
        self, reservation: ModelBudgetReservation, *, outcome_code: str
    ) -> ModelBudgetReservation:
        return await self.store.release(
            reservation.reservation_id,
            outcome_code=outcome_code,
            now=self._now(),
        )

    def _now(self) -> datetime:
        return _aware(self.clock() if self.clock is not None else datetime.now(UTC))


def build_budget_account(
    *,
    tenant_id: str,
    environment: str,
    policy: ModelBudgetPolicy,
    now: datetime,
) -> ModelBudgetAccount:
    _aware(now)
    return ModelBudgetAccount(
        tenant_id=tenant_id,
        environment=environment,
        period_key=now.date().isoformat(),
        policy_version=policy.version,
        limit_microusd=policy.period_limit_microusd,
        reserved_microusd=0,
        spent_microusd=0,
        updated_at=now,
    )


def _estimate_prompt_tokens(request: StructuredRequest, *, overhead: int) -> int:
    return estimate_prompt_tokens(
        use_case=request.use_case,
        payload=request.payload,
        output_schema=request.output_schema,
        input_refs=request.input_refs,
        overhead=overhead,
    )


def estimate_prompt_tokens(
    *,
    use_case: str,
    payload: object,
    output_schema: object,
    input_refs: object,
    overhead: int = 256,
) -> int:
    """Return a conservative server-owned estimate for routing and reservation."""

    if not isinstance(overhead, int) or isinstance(overhead, bool) or overhead <= 0:
        raise ModelBudgetError("MODEL_BUDGET_ESTIMATE_OVERHEAD_INVALID")
    canonical_input = {
        "use_case": use_case,
        "payload": payload,
        "output_schema": output_schema,
        "input_refs": input_refs,
    }
    try:
        encoded = json.dumps(
            canonical_input,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    except (TypeError, ValueError) as exc:
        raise ModelBudgetError("MODEL_BUDGET_INPUT_NOT_JSON") from exc
    # One token can be as small as one byte. Byte length is deliberately a
    # conservative provider-neutral upper estimate; media has a separate rate.
    return len(encoded) + overhead


def _validate_account(account: ModelBudgetAccount) -> None:
    identity = (
        account.tenant_id,
        account.environment,
        account.period_key,
        account.policy_version,
    )
    if not all(identity):
        raise ModelBudgetError("MODEL_BUDGET_ACCOUNT_IDENTITY_REQUIRED")
    _aware(account.updated_at)
    values = (account.limit_microusd, account.reserved_microusd, account.spent_microusd)
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in values):
        raise ModelBudgetError("MODEL_BUDGET_ACCOUNT_VALUE_INVALID")
    if account.reserved_microusd + account.spent_microusd > account.limit_microusd:
        raise ModelBudgetError("MODEL_BUDGET_ACCOUNT_OVER_LIMIT")


def _validate_reservation(reservation: ModelBudgetReservation) -> None:
    required = (
        reservation.reservation_id,
        reservation.reservation_key,
        reservation.tenant_id,
        reservation.environment,
        reservation.period_key,
        reservation.request_ref,
        reservation.provider_id,
        reservation.model,
        reservation.policy_version,
        reservation.rate_card_version,
    )
    if not all(required):
        raise ModelBudgetError("MODEL_BUDGET_RESERVATION_IDENTITY_REQUIRED")
    if reservation.status is not BudgetReservationStatus.RESERVED:
        raise ModelBudgetError("MODEL_BUDGET_NEW_RESERVATION_STATUS_INVALID")
    if reservation.actual_microusd is not None or reservation.outcome_code is not None:
        raise ModelBudgetError("MODEL_BUDGET_NEW_RESERVATION_OUTCOME_INVALID")
    if reservation.route_sequence < 0 or reservation.reserved_microusd <= 0:
        raise ModelBudgetError("MODEL_BUDGET_RESERVATION_VALUE_INVALID")
    _aware(reservation.created_at)
    _aware(reservation.updated_at)
    release_refs = (
        reservation.release_set_id,
        reservation.bundle_id,
        reservation.deployment_receipt_id,
        reservation.runtime_config_digest,
        reservation.control_id,
    )
    has_release_evidence = any(release_refs) or reservation.deployment_sequence is not None
    if has_release_evidence and (
        reservation.deployment_sequence is None
        or reservation.deployment_sequence <= 0
        or not all(isinstance(value, str) and value.strip() for value in release_refs)
    ):
        raise ModelBudgetError("MODEL_BUDGET_RELEASE_BINDING_INCOMPLETE")


def _validate_actual(actual_microusd: int, now: datetime) -> None:
    if (
        not isinstance(actual_microusd, int)
        or isinstance(actual_microusd, bool)
        or actual_microusd < 0
    ):
        raise ModelBudgetError("MODEL_BUDGET_ACTUAL_INVALID")
    _aware(now)


def _assert_account_policy(
    account: ModelBudgetAccount, reservation: ModelBudgetReservation
) -> None:
    if account.policy_version != reservation.policy_version:
        raise ModelBudgetError("MODEL_BUDGET_ACCOUNT_POLICY_MISMATCH")


def _same_reservation_request(
    left: ModelBudgetReservation, right: ModelBudgetReservation
) -> bool:
    return (
        left.reservation_id == right.reservation_id
        and left.reservation_key == right.reservation_key
        and left.tenant_id == right.tenant_id
        and left.environment == right.environment
        and left.period_key == right.period_key
        and left.request_ref == right.request_ref
        and left.provider_id == right.provider_id
        and left.model == right.model
        and left.route_sequence == right.route_sequence
        and left.policy_version == right.policy_version
        and left.rate_card_version == right.rate_card_version
        and left.release_set_id == right.release_set_id
        and left.bundle_id == right.bundle_id
        and left.deployment_receipt_id == right.deployment_receipt_id
        and left.runtime_config_digest == right.runtime_config_digest
        and left.deployment_sequence == right.deployment_sequence
        and left.control_id == right.control_id
        and left.reserved_microusd == right.reserved_microusd
    )


def _account_key(account: ModelBudgetAccount) -> tuple[str, str, str]:
    return account.tenant_id, account.environment, account.period_key


def _reservation_account_key(
    reservation: ModelBudgetReservation,
) -> tuple[str, str, str]:
    return reservation.tenant_id, reservation.environment, reservation.period_key


def _account_row(account: ModelBudgetAccount) -> ModelBudgetAccountRow:
    return ModelBudgetAccountRow(**{
        "tenant_id": account.tenant_id,
        "environment": account.environment,
        "period_key": account.period_key,
        "policy_version": account.policy_version,
        "limit_microusd": account.limit_microusd,
        "reserved_microusd": account.reserved_microusd,
        "spent_microusd": account.spent_microusd,
        "updated_at": account.updated_at,
    })


def _reservation_row(reservation: ModelBudgetReservation) -> ModelBudgetReservationRow:
    return ModelBudgetReservationRow(**{
        "reservation_id": reservation.reservation_id,
        "reservation_key": reservation.reservation_key,
        "tenant_id": reservation.tenant_id,
        "environment": reservation.environment,
        "period_key": reservation.period_key,
        "request_ref": reservation.request_ref,
        "provider_id": reservation.provider_id,
        "model": reservation.model,
        "route_sequence": reservation.route_sequence,
        "policy_version": reservation.policy_version,
        "rate_card_version": reservation.rate_card_version,
        "release_set_id": reservation.release_set_id,
        "bundle_id": reservation.bundle_id,
        "deployment_receipt_id": reservation.deployment_receipt_id,
        "runtime_config_digest": reservation.runtime_config_digest,
        "deployment_sequence": reservation.deployment_sequence,
        "control_id": reservation.control_id,
        "reserved_microusd": reservation.reserved_microusd,
        "actual_microusd": reservation.actual_microusd,
        "status": reservation.status.value,
        "outcome_code": reservation.outcome_code,
        "created_at": reservation.created_at,
        "updated_at": reservation.updated_at,
    })


def _stored_account(row: ModelBudgetAccountRow) -> ModelBudgetAccount:
    return ModelBudgetAccount(
        tenant_id=row.tenant_id,
        environment=row.environment,
        period_key=row.period_key,
        policy_version=row.policy_version,
        limit_microusd=row.limit_microusd,
        reserved_microusd=row.reserved_microusd,
        spent_microusd=row.spent_microusd,
        updated_at=_db_time(row.updated_at),
    )


def _stored_reservation(row: ModelBudgetReservationRow) -> ModelBudgetReservation:
    try:
        status = BudgetReservationStatus(row.status)
    except ValueError as exc:
        raise ModelBudgetError("PERSISTED_MODEL_BUDGET_STATUS_INVALID") from exc
    return ModelBudgetReservation(
        reservation_id=row.reservation_id,
        reservation_key=row.reservation_key,
        tenant_id=row.tenant_id,
        environment=row.environment,
        period_key=row.period_key,
        request_ref=row.request_ref,
        provider_id=row.provider_id,
        model=row.model,
        route_sequence=row.route_sequence,
        policy_version=row.policy_version,
        rate_card_version=row.rate_card_version,
        reserved_microusd=row.reserved_microusd,
        actual_microusd=row.actual_microusd,
        status=status,
        outcome_code=row.outcome_code,
        created_at=_db_time(row.created_at),
        updated_at=_db_time(row.updated_at),
        release_set_id=row.release_set_id,
        bundle_id=row.bundle_id,
        deployment_receipt_id=row.deployment_receipt_id,
        runtime_config_digest=row.runtime_config_digest,
        deployment_sequence=row.deployment_sequence,
        control_id=row.control_id,
    )


def _digest(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ModelBudgetError("MODEL_BUDGET_TIME_MUST_BE_AWARE")
    return value


def _db_time(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


__all__ = [
    "BudgetReservationStatus",
    "InMemoryModelBudgetStore",
    "ModelBudgetAccount",
    "ModelBudgetBase",
    "ModelBudgetError",
    "ModelBudgetPolicy",
    "ModelBudgetReservation",
    "ModelBudgetRuntime",
    "ModelBudgetStore",
    "ModelRate",
    "ModelRateCard",
    "SqlAlchemyModelBudgetStore",
    "build_budget_account",
    "estimate_prompt_tokens",
]
