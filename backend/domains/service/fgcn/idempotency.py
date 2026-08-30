"""Canonical request hashes for tenant-scoped FGCN mutations."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

from backend.domains.service.domain.errors import ServiceValidationError

from .contracts import GateServiceScope


def effective_mutation_key(idempotency_key: str | None, resource_id: str) -> str:
    """Return the explicit client key, with a stable direct-command fallback.

    HTTP callers must provide a key.  The resource fallback keeps existing
    application-level callers on the same durable path while preserving the
    resource-id replay behavior of the original command tests.
    """

    if idempotency_key is None:
        return f"resource:{resource_id}"
    if not isinstance(idempotency_key, str) or not idempotency_key.strip():
        raise ServiceValidationError("fgcn_mutation_idempotency_key_required")
    return idempotency_key.strip()


def mutation_request_hash(
    action_name: str,
    scope: GateServiceScope,
    payload: Mapping[str, object],
) -> str:
    """Hash the immutable request intent, including its complete FGCN scope.

    Server timestamps are deliberately excluded by callers.  The resulting
    hash is stored beside the existing platform idempotency row, so a replay
    cannot change a delivery, review, or contribution while retaining its
    client key.
    """

    if not isinstance(action_name, str) or not action_name.strip():
        raise ServiceValidationError("fgcn_idempotency_action_required")
    canonical = {
        "action": action_name.strip(),
        "scope": {
            "tenant_id": scope.tenant_id,
            "family_id": scope.family_id,
            "subject_person_id": scope.subject_person_id,
            "purpose": scope.purpose,
            "consent_version": scope.consent_version,
            "correlation_id": scope.correlation_id,
        },
        "payload": dict(payload),
    }
    try:
        encoded = json.dumps(
            canonical,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ServiceValidationError("fgcn_idempotency_payload_invalid") from exc
    return hashlib.sha256(encoded).hexdigest()


__all__ = ["effective_mutation_key", "mutation_request_hash"]
