"""Source Identity & Semantic Fingerprint (AIFAMILY-WM-003.6).

Fixes a P0 gap: `atom_id` is a storage identity assigned by the caller, not
a semantic identity — nothing stopped the same authoritative source from
being projected twice under two different `atom_id`s, which would let
WM-004B's Belief Engine later count one real fact as two independent
pieces of evidence and inflate `support_level`.

`projection_key` is now the semantic projection identity:

    same source_ref + same source_version + same predicate +
    same epistemic_kind + same projection_version
    => same projection_key

`semantic_fingerprint` is a second, independent hash over the actual
asserted content (value/subjects/time/evidence) — it exists to distinguish
"the same source replayed with the same meaning" (idempotent) from "the
same source replayed with a *different* meaning" (a data-consistency bug,
must fail closed, never silently overwritten).

Neither hash may include `atom_id`, `recorded_at`, `generated_at`,
`correlation_id`, `request_id`, or any random value — see
`tests/architecture/test_projection_identity_determinism.py` for the
structural check that keeps this true.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import datetime


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _canonical_subject_refs(subject_ids: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted(subject_ids))


def _iso(moment: datetime | None) -> str | None:
    return moment.isoformat() if moment is not None else None


def build_projection_key(
    *,
    tenant_id: str,
    family_id: str,
    subject_ids: Sequence[str],
    predicate: str,
    epistemic_kind: str,
    source_ref: str,
    source_version: str,
    projection_version: str,
) -> str:
    """Semantic projection identity — deliberately excludes `atom_id` and
    every timestamp. Two calls with the same authoritative source (same
    `source_ref`/`source_version`) and the same adapter contract (same
    `projection_version`) always produce the same key, regardless of how
    many times the source is replayed or what storage id the caller picks.
    """

    payload = {
        "tenant_id": tenant_id,
        "family_id": family_id,
        "subject_refs": list(_canonical_subject_refs(subject_ids)),
        "predicate": predicate,
        "epistemic_kind": epistemic_kind,
        "source_ref": source_ref,
        "source_version": source_version,
        "projection_version": projection_version,
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def build_semantic_fingerprint(
    *,
    family_id: str,
    subject_ids: Sequence[str],
    predicate: str,
    epistemic_kind: str,
    value_ref: str,
    asserted_by: str,
    valid_from: datetime,
    valid_until: datetime | None,
    source_refs: Sequence[str],
    evidence_refs: Sequence[str],
    data_class: str,
    projection_version: str,
) -> str:
    """What this projection identity currently claims. Two projections of
    the same source at two points in time must produce the same fingerprint
    if and only if the asserted content is unchanged — this is what lets
    `append_atom` distinguish IDEMPOTENT_REPLAY from
    PROJECTION_IDENTITY_CONFLICT (see `postgres_world_state_repository.py`).
    """

    payload = {
        "family_id": family_id,
        "subject_refs": list(_canonical_subject_refs(subject_ids)),
        "predicate": predicate,
        "epistemic_kind": epistemic_kind,
        "value_ref": value_ref,
        "asserted_by": asserted_by,
        "valid_from": _iso(valid_from),
        "valid_until": _iso(valid_until),
        "source_refs": sorted(source_refs),
        "evidence_refs": sorted(evidence_refs),
        "data_class": data_class,
        "projection_version": projection_version,
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


__all__ = ["build_projection_key", "build_semantic_fingerprint"]
