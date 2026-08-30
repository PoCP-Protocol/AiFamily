"""Immutable, evidence-bound inputs for the product factory.

The product factory consumes proposals from AI or research tooling.  These
records intentionally stop at ``DRAFT``: they are not a repository command,
cannot publish a product, and cannot write family, growth, service, or
commerce facts.  A later application layer may persist them after applying
tenant authorization and a human gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal


class ProductFactoryInputError(ValueError):
    """Raised when a product-factory input is incomplete or unsafe."""


class DraftStatus(StrEnum):
    DRAFT = "DRAFT"


class EvidenceStatus(StrEnum):
    """Epistemic state of a cited source, not a product lifecycle state."""

    VERIFIED = "VERIFIED"
    UNKNOWN = "UNKNOWN"
    STALE = "STALE"
    CONTRADICTED = "CONTRADICTED"


def _text(value: str | None, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProductFactoryInputError(code)
    return value.strip()


def _refs(values: tuple[str, ...], code: str) -> tuple[str, ...]:
    try:
        if not isinstance(values, tuple):
            values = tuple(values)
    except TypeError as exc:
        raise ProductFactoryInputError(code) from exc
    normalised = tuple(_text(value, code) for value in values)
    if not normalised:
        raise ProductFactoryInputError(code)
    if len(set(normalised)) != len(normalised):
        raise ProductFactoryInputError(f"{code}_MUST_BE_UNIQUE")
    return normalised


def _notes(values: tuple[str, ...], code: str) -> tuple[str, ...]:
    try:
        if not isinstance(values, tuple):
            values = tuple(values)
    except TypeError as exc:
        raise ProductFactoryInputError(code) from exc
    return tuple(_text(value, code) for value in values)


def _expiry(*, expires_at: datetime | None, expiry: datetime | None) -> datetime:
    if expires_at is not None and expiry is not None and expires_at != expiry:
        raise ProductFactoryInputError("EXPIRY_ALIASES_MUST_MATCH")
    value = expires_at or expiry
    if value is None or value.tzinfo is None or value.utcoffset() is None:
        raise ProductFactoryInputError("EXPIRY_MUST_BE_TIMEZONE_AWARE")
    value = value.astimezone(UTC)
    if value <= datetime.now(UTC):
        raise ProductFactoryInputError("EXPIRY_MUST_BE_IN_THE_FUTURE")
    return value


def _draft(status: DraftStatus | str, code: str) -> None:
    try:
        value = DraftStatus(status)
    except (TypeError, ValueError) as exc:
        if isinstance(status, str) and status.strip():
            raise ProductFactoryInputError("PRODUCT_FACTORY_INPUT_MUST_REMAIN_DRAFT") from exc
        raise ProductFactoryInputError(code) from exc
    if value is not DraftStatus.DRAFT:
        raise ProductFactoryInputError("PRODUCT_FACTORY_INPUT_MUST_REMAIN_DRAFT")


def _evidence_status(value: EvidenceStatus | str) -> EvidenceStatus:
    try:
        return EvidenceStatus(value)
    except (TypeError, ValueError) as exc:
        raise ProductFactoryInputError("EVIDENCE_STATUS_UNSUPPORTED") from exc


@dataclass(frozen=True, slots=True, kw_only=True)
class _DraftEnvelope:
    """Shared audit fields for non-publishing product-factory proposals."""

    evidence_refs: tuple[str, ...]
    assumptions: tuple[str, ...]
    unknowns: tuple[str, ...]
    next_validation: str
    version: str = "1.0.0"
    provenance_ref: str | None = None
    expires_at: datetime | None = None
    expiry: datetime | None = None
    status: DraftStatus | str = DraftStatus.DRAFT

    def _validate_envelope(self, prefix: str) -> None:
        _draft(self.status, f"{prefix}_STATUS_UNSUPPORTED")
        object.__setattr__(self, "status", DraftStatus.DRAFT)
        object.__setattr__(
            self,
            "evidence_refs",
            _refs(self.evidence_refs, f"{prefix}_EVIDENCE_REQUIRED"),
        )
        object.__setattr__(
            self,
            "assumptions",
            _notes(self.assumptions, f"{prefix}_ASSUMPTION_INVALID"),
        )
        object.__setattr__(self, "unknowns", _notes(self.unknowns, f"{prefix}_UNKNOWN_INVALID"))
        object.__setattr__(
            self,
            "next_validation",
            _text(self.next_validation, f"{prefix}_NEXT_VALIDATION_REQUIRED"),
        )
        object.__setattr__(self, "version", _text(self.version, f"{prefix}_VERSION_REQUIRED"))
        if self.provenance_ref is not None:
            object.__setattr__(
                self,
                "provenance_ref",
                _text(self.provenance_ref, f"{prefix}_PROVENANCE_REF_INVALID"),
            )
        resolved_expiry = _expiry(expires_at=self.expires_at, expiry=self.expiry)
        object.__setattr__(self, "expires_at", resolved_expiry)
        object.__setattr__(self, "expiry", resolved_expiry)

    @property
    def requires_human_confirmation(self) -> Literal[True]:
        return True

    @property
    def may_mutate_business_state(self) -> Literal[False]:
        return False

    @property
    def human_confirmation_required(self) -> Literal[True]:
        """Alias used by API envelopes that spell the flag explicitly."""

        return True


@dataclass(frozen=True, slots=True, kw_only=True)
class DemandFrame(_DraftEnvelope):
    """A bounded demand hypothesis, not a family or child fact."""

    demand_id: str
    statement: str
    scenario: str
    source_refs: tuple[str, ...]
    target_segment: str
    locale: str = "zh-CN"
    purpose: str = "product_discovery"

    def __post_init__(self) -> None:
        self._validate_envelope("DEMAND_FRAME")
        for value, code in (
            (self.demand_id, "DEMAND_FRAME_ID_REQUIRED"),
            (self.statement, "DEMAND_FRAME_STATEMENT_REQUIRED"),
            (self.scenario, "DEMAND_FRAME_SCENARIO_REQUIRED"),
            (self.target_segment, "DEMAND_FRAME_SEGMENT_REQUIRED"),
            (self.locale, "DEMAND_FRAME_LOCALE_REQUIRED"),
            (self.purpose, "DEMAND_FRAME_PURPOSE_REQUIRED"),
        ):
            _text(value, code)
        object.__setattr__(
            self,
            "source_refs",
            _refs(self.source_refs, "DEMAND_FRAME_SOURCE_REQUIRED"),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class MarketInsightDraft(_DraftEnvelope):
    """An evidence-bound market insight proposal linked to a demand frame."""

    insight_id: str
    demand_ref: str
    statement: str
    source_refs: tuple[str, ...]
    competitor_evidence_refs: tuple[str, ...] = ()
    segment_ref: str | None = None

    def __post_init__(self) -> None:
        self._validate_envelope("MARKET_INSIGHT")
        for value, code in (
            (self.insight_id, "MARKET_INSIGHT_ID_REQUIRED"),
            (self.demand_ref, "MARKET_INSIGHT_DEMAND_REF_REQUIRED"),
            (self.statement, "MARKET_INSIGHT_STATEMENT_REQUIRED"),
        ):
            _text(value, code)
        object.__setattr__(
            self,
            "source_refs",
            _refs(self.source_refs, "MARKET_INSIGHT_SOURCE_REQUIRED"),
        )
        if self.competitor_evidence_refs:
            object.__setattr__(
                self,
                "competitor_evidence_refs",
                _refs(self.competitor_evidence_refs, "MARKET_INSIGHT_COMPETITOR_REF_INVALID"),
            )
        if self.segment_ref is not None:
            object.__setattr__(
                self,
                "segment_ref",
                _text(self.segment_ref, "MARKET_INSIGHT_SEGMENT_REF_INVALID"),
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class CompetitorEvidenceCard(_DraftEnvelope):
    """A source card for competitor analysis; it never ranks competitors."""

    evidence_id: str
    competitor_ref: str
    claim: str
    source_refs: tuple[str, ...]
    evidence_status: EvidenceStatus | str = EvidenceStatus.UNKNOWN
    demand_ref: str | None = None
    market_insight_ref: str | None = None
    source_type: str = "PUBLIC"

    def __post_init__(self) -> None:
        self._validate_envelope("COMPETITOR_EVIDENCE")
        for value, code in (
            (self.evidence_id, "COMPETITOR_EVIDENCE_ID_REQUIRED"),
            (self.competitor_ref, "COMPETITOR_EVIDENCE_COMPETITOR_REF_REQUIRED"),
            (self.claim, "COMPETITOR_EVIDENCE_CLAIM_REQUIRED"),
            (self.source_type, "COMPETITOR_EVIDENCE_SOURCE_TYPE_REQUIRED"),
        ):
            _text(value, code)
        object.__setattr__(
            self,
            "source_refs",
            _refs(self.source_refs, "COMPETITOR_EVIDENCE_SOURCE_REQUIRED"),
        )
        object.__setattr__(self, "evidence_status", _evidence_status(self.evidence_status))
        if self.demand_ref is None and self.market_insight_ref is None:
            raise ProductFactoryInputError("COMPETITOR_EVIDENCE_PARENT_REF_REQUIRED")
        if self.demand_ref is not None:
            object.__setattr__(
                self,
                "demand_ref",
                _text(self.demand_ref, "COMPETITOR_EVIDENCE_DEMAND_REF_INVALID"),
            )
        if self.market_insight_ref is not None:
            object.__setattr__(
                self,
                "market_insight_ref",
                _text(self.market_insight_ref, "COMPETITOR_EVIDENCE_INSIGHT_REF_INVALID"),
            )


__all__ = [
    "CompetitorEvidenceCard",
    "DemandFrame",
    "DraftStatus",
    "EvidenceStatus",
    "MarketInsightDraft",
    "ProductFactoryInputError",
]
