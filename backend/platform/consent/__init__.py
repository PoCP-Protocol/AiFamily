"""Public consent primitives and the stateless consent gate."""

from __future__ import annotations

from backend.platform.consent.gate import ConsentGate
from backend.platform.consent.models import (
    ConsentGrant,
    ConsentPurpose,
    ConsentStatus,
    GuardianRelation,
    SubjectAge,
)

__all__ = [
    "ConsentGate",
    "ConsentGrant",
    "ConsentPurpose",
    "ConsentStatus",
    "GuardianRelation",
    "SubjectAge",
]
