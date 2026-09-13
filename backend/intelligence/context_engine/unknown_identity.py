"""Unknown canonical identity (AIFAMILY-WM-004C, B9).

`unknown_key` is deliberately NOT a hash of the question's wording — the
same underlying cognitive gap phrased two different ways by two different
model calls (or two calls racing each other) must collapse to the same row.
What makes two Unknowns "the same ignorance" is:

    same tenant_id + same family_id + same canonical subject_ids +
    same target_predicate + same canonical blocking_refs +
    same unknown_contract_version
    => same unknown_key

`unknown_contract_version` exists for the same reason `projection_version`
exists in `projection_identity.py`: a future change to what "the same
Unknown" means (e.g. adding a new dimension to the identity) must not
silently collide with V1 identities.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _canonical_refs(refs: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted(set(refs)))


def build_unknown_key(
    *,
    tenant_id: str,
    family_id: str,
    subject_ids: Sequence[str],
    target_predicate: str,
    blocking_refs: Sequence[str],
    unknown_contract_version: str,
) -> str:
    payload = {
        "tenant_id": tenant_id,
        "family_id": family_id,
        "subject_refs": _canonical_refs(subject_ids),
        "target_predicate": target_predicate,
        "blocking_refs": _canonical_refs(blocking_refs),
        "unknown_contract_version": unknown_contract_version,
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


__all__ = ["build_unknown_key"]
