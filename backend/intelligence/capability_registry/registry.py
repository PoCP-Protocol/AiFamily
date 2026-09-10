"""Fail-closed registry for published growth capability offers."""

from __future__ import annotations

from dataclasses import replace

from .contracts import CapabilityOffer, CapabilityStatus


class CapabilityRegistry:
    """In-memory adapter preserving the semantics of a durable catalogue.

    The adapter is intentionally supply-side only: retrieval emits candidates
    for a path draft and never books, assigns, or activates an offer.
    """

    def __init__(self, offers: tuple[CapabilityOffer, ...] = ()) -> None:
        self._offers: dict[str, CapabilityOffer] = {}
        for offer in offers:
            self.register(offer)

    def register(self, offer: CapabilityOffer) -> None:
        if offer.identity in self._offers:
            raise ValueError(f"CAPABILITY_ALREADY_REGISTERED:{offer.identity}")
        self._offers[offer.identity] = offer

    def get(self, capability_ref: str, version: str) -> CapabilityOffer | None:
        return self._offers.get(f"{capability_ref}@{version}")

    def transition(
        self, capability_ref: str, version: str, status: CapabilityStatus
    ) -> CapabilityOffer:
        identity = f"{capability_ref}@{version}"
        current = self._offers.get(identity)
        if current is None:
            raise ValueError(f"CAPABILITY_NOT_FOUND:{identity}")
        allowed: dict[CapabilityStatus, set[CapabilityStatus]] = {
            "INGESTED": {"REVIEWED", "RETIRED"},
            "REVIEWED": {"PUBLISHED", "RETIRED"},
            "PUBLISHED": {"RETIRED"},
            "RETIRED": set(),
        }
        if status not in allowed[current.status]:
            raise ValueError(f"INVALID_CAPABILITY_TRANSITION:{current.status}->{status}")
        updated = replace(current, status=status)
        self._offers[identity] = updated
        return updated

    def retrieve_published(
        self,
        *,
        purpose: str,
        scope: str,
        need_type: str | None = None,
        required_keys: tuple[str, ...] = (),
    ) -> tuple[CapabilityOffer, ...]:
        """Return only published, in-scope offers satisfying all requested keys."""

        requested = frozenset(key for key in required_keys if key)
        results = []
        for offer in self._offers.values():
            if offer.status != "PUBLISHED" or offer.purpose != purpose:
                continue
            if offer.scope not in {scope, "*"}:
                continue
            if need_type is not None and offer.need_types and need_type not in offer.need_types:
                continue
            if not requested.issubset(frozenset(offer.required_capability_keys)):
                continue
            results.append(offer)
        return tuple(sorted(results, key=lambda item: item.identity))


__all__ = ["CapabilityRegistry"]
