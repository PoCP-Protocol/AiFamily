"""Contracts for governed growth capability offers.

Capabilities are supply-side candidates.  They are not family facts and may
only be returned after an explicit publication transition and scope checks.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

CapabilityStatus = Literal["INGESTED", "REVIEWED", "PUBLISHED", "RETIRED"]


@dataclass(frozen=True, slots=True)
class CapabilityOffer:
    """A versioned, human-governed capability that a path may propose."""

    capability_ref: str
    version: str
    title: str
    description: str
    purpose: str
    scope: str
    required_capability_keys: tuple[str, ...] = ()
    need_types: tuple[str, ...] = ()
    delivery_kind: str = "PRACTICE"
    status: CapabilityStatus = "INGESTED"
    owner: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        required = (
            self.capability_ref,
            self.version,
            self.title,
            self.description,
            self.purpose,
            self.scope,
            self.owner,
        )
        if any(not isinstance(value, str) or not value.strip() for value in required):
            raise ValueError("CAPABILITY_REQUIRED_FIELDS")
        if any(
            not isinstance(value, str) or not value.strip()
            for value in self.required_capability_keys
        ):
            raise ValueError("CAPABILITY_KEY_INVALID")
        if any(not isinstance(value, str) or not value.strip() for value in self.need_types):
            raise ValueError("CAPABILITY_NEED_TYPE_INVALID")
        if self.status not in {"INGESTED", "REVIEWED", "PUBLISHED", "RETIRED"}:
            raise ValueError("CAPABILITY_STATUS_INVALID")

    @property
    def identity(self) -> str:
        return f"{self.capability_ref}@{self.version}"


__all__ = ["CapabilityOffer", "CapabilityStatus"]
