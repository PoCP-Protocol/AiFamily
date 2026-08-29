"""Immutable versioned-object base pattern.

No TS predecessor for this exact shape — the closest analogue is the TS
`ServiceBlueprintVersion` concept referenced in
`architecture/FAMILY_PRODUCT_INTELLIGENCE_PLATFORM_TARGET_ARCHITECTURE_DRAFT_001.md`
§4, but that type has no real implementation on either side (TS or Python)
as of this skeleton — see the DRAFT doc's exploration notes. This base class
is written directly against the DRAFT doc, not ported from existing code.

Any future real `ServiceBlueprintVersion` (Python-side) should extend this
base rather than re-invent version/status handling.
"""

from __future__ import annotations

from typing import Literal, TypeVar

from pydantic import BaseModel

VersionStatus = Literal["DRAFT", "COMPILED", "SIMULATED", "REVIEWED", "PILOT", "PUBLISHED"]

T = TypeVar("T", bound="VersionedObject")


class VersionedObject(BaseModel):
    """Frozen (immutable) versioned object. Mutation always produces a new
    instance via `next_version()` — never mutate fields in place, matching
    the DRAFT doc's "发布之后形成不可变版本" rule.
    """

    model_config = {"frozen": True}

    id: str
    version: int
    status: VersionStatus

    def next_version(self: T, **changes: object) -> T:
        """Return a new instance with `version + 1` and the given field
        changes applied. Does not mutate `self`.
        """
        return self.model_copy(update={**changes, "version": self.version + 1})
