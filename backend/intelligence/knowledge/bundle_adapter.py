"""Read-only adapter for compiled research knowledge bundles."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from backend.packages.contracts.evidence import Provenance

from .contracts import KnowledgeClaim, KnowledgeSource, KnowledgeStatus

_SECTIONS = ("theories", "constructs", "methods", "modalities")
_CARD_TYPES = {
    "theories": "THEORY",
    "constructs": "CONSTRUCT",
    "methods": "METHOD",
    "modalities": "MODALITY",
}
_VALID_LEVELS = {f"E{i}" for i in range(8)} | {
    "simulated",
    "inferred",
    "unverified",
    "unknown",
}


def _required_text(bundle: Mapping[str, Any], key: str) -> str:
    value = bundle.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"BUNDLE_FIELD_REQUIRED:{key}")
    return value


def adapt_compiled_bundle(
    bundle: Mapping[str, Any],
    *,
    source: KnowledgeSource,
    status: KnowledgeStatus = "REVIEWED",
) -> tuple[KnowledgeClaim, ...]:
    """Convert a compiled snapshot into reviewable claims.

    Claims intentionally start at ``REVIEWED`` at most; the registry still
    requires an explicit publish transition before runtime retrieval.  The
    adapter never treats the bundle's own ``source_registry_gate`` as proof of
    current publication or efficacy.
    """

    schema_version = _required_text(bundle, "schema_version")
    if schema_version != "KNOWLEDGE_CHAIN_V2":
        raise ValueError(f"BUNDLE_SCHEMA_UNSUPPORTED:{schema_version}")
    intervention_id = _required_text(bundle, "intervention_id")
    _required_text(bundle, "bundle_version")
    claims: list[KnowledgeClaim] = []
    for section in _SECTIONS:
        cards = bundle.get(section, [])
        if not isinstance(cards, list):
            raise ValueError(f"BUNDLE_SECTION_INVALID:{section}")
        for card in cards:
            if not isinstance(card, Mapping):
                raise ValueError(f"BUNDLE_CARD_INVALID:{section}")
            card_id = _required_text(card, "id")
            text = str(card.get("core_claim") or card.get("summary") or card.get("title") or "")
            if not text.strip():
                raise ValueError(f"BUNDLE_CARD_TEXT_REQUIRED:{card_id}")
            level = card.get("evidence_grade")
            if level not in _VALID_LEVELS:
                raise ValueError(f"BUNDLE_EVIDENCE_LEVEL_INVALID:{card_id}")
            claim_id = f"{intervention_id}:{_CARD_TYPES[section]}:{card_id}"
            claims.append(
                KnowledgeClaim(
                    claim_id=claim_id,
                    text=text,
                    source_id=source.source_id,
                    provenance=Provenance(
                        level=level,  # type: ignore[arg-type]
                        source_ref=source.source_id,
                    ),
                    scope="*",
                    status=status,
                    allowed_purposes=("principal_knowledge_answer", "service_product_design"),
                    metadata={
                        "card_type": _CARD_TYPES[section],
                        "card_id": card_id,
                        "source_refs": tuple(card.get("source_refs") or ()),
                        "family_decision_non_decisive": bool(
                            card.get("family_decision_non_decisive", True)
                        ),
                    },
                )
            )
    return tuple(claims)


def load_compiled_bundle(
    path: Path,
    *,
    source: KnowledgeSource,
    status: KnowledgeStatus = "REVIEWED",
) -> tuple[KnowledgeClaim, ...]:
    """Load one explicit path; missing or malformed input fails closed."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"BUNDLE_LOAD_FAILED:{path.name}") from exc
    if not isinstance(payload, Mapping):
        raise ValueError("BUNDLE_ROOT_INVALID")
    return adapt_compiled_bundle(payload, source=source, status=status)
