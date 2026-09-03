"""Consent primitives — purpose enum, ConsentGrant, ConsentGate.

See governance/MIGRATION_MANIFEST.yaml capability `platform_consent`
(disposition REIMPLEMENT). Purpose taxonomy is derived from the source
repository's `specs/ontology/consent.schema.yaml`; the "withdrawn consent
must take effect immediately, no caching" requirement is preserved verbatim
per `FAMILY_AI_PYTHON_ONLY_MIGRATION_PLAN_V1.md` section 10, which
REPOSITORY_CONSTITUTION.md's disposition explicitly keeps in force.
"""

from __future__ import annotations

from backend.platform.consent.gate import ConsentGate
from backend.platform.consent.models import (
    GUARDIAN_CONSENT_AGE_THRESHOLD,
    ConsentGrant,
    ConsentPurpose,
    ConsentStatus,
    GuardianRelation,
    SubjectAge,
)

__all__ = [
    "GUARDIAN_CONSENT_AGE_THRESHOLD",
    "ConsentGate",
    "ConsentGrant",
    "ConsentPurpose",
    "ConsentStatus",
    "GuardianRelation",
    "SubjectAge",
]
