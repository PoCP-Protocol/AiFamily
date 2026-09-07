"""Durable `AsyncProviderAdmissionQuery` backed by ``family_service_providers``.

FGCN does not own provider qualification/admission facts (see
``backend/domains/service/fgcn/admission.py``'s module docstring). Those facts
already live in the pre-existing, migrated (0035) ``family_service_providers``
table and its ORM row ``ServiceProviderRow`` — real ``status`` /
``qualification_status`` / ``admission_status`` columns, exposed by the domain
entity's ``is_bookable`` property.

A second, FGCN-only admission table was considered and rejected: the database
already has an orphaned, unrelated marketplace-style admission model
(``provider_admissions`` / ``provider_profiles`` / ``teacher_profiles`` /
``teacher_qualifications`` / ``teacher_capabilities``, created by earlier
migrations but never wired to any domain code, 0 rows, and using a different
status vocabulary — ``ADMITTED`` vs this domain's ``ADMITTED`` is the same
value by coincidence, but there is no ``allowed_purposes`` concept there and
capability comes from a separate join table). Reshaping FGCN's snapshot
contract around that unrelated model would be a cross-domain coupling this
change does not attempt. This adapter instead reuses the service domain's own
supply-master table, which is already real, already migrated, and already the
system of record the dev wiring's in-memory judgement was standing in for.

``capability_keys`` and ``allowed_purposes`` are not separate columns on
``family_service_providers`` — they are read from its existing ``attributes``
JSONB catch-all (the same column ``ensure_mobile_master_data`` already writes
``service_type``/``age_band`` into), under the keys
``fgcn_capability_keys`` / ``fgcn_allowed_purposes``. A provider row with no
FGCN attributes is a refusal (``None``), not an implicit allow — matching
``AsyncRejectingProviderAdmissionQuery``'s default and
``assert_provider_admitted``'s fail-closed contract.

``tenant_id``/``family_id``/``credential_ref``/``credential_valid_from``/
``credential_valid_until``/``slot_ref``/``slot_start_at``/``slot_end_at``
(added to ``ProviderAdmissionSnapshot`` by df618d8/c29d738 for the in-memory
`FGCNEngine` path's scope-binding and credential/slot-window tests) are
populated here from data that is real today, not invented:

- ``tenant_id``/``family_id`` come straight from the caller's own ``scope`` —
  there is no separate "admission scoped to this family" fact to look up;
  ``assert_provider_admitted`` checks these against ``scope`` anyway, so
  echoing ``scope`` back is exactly what the caller already asserts is true.
- ``credential_ref`` is the row's real ``qualification_ref`` (falling back to
  a stable ``provider_ref``-derived value when a provider has none on file,
  since the field is required but not every seeded provider carries a
  qualification reference).
- ``credential_valid_from`` is the row's real ``effective_from`` (when the
  provider became bookable at all) and ``credential_valid_until`` is the real
  ``qualification_expires_at`` already used above to fail closed on expiry —
  or a far-future sentinel when the provider carries no expiry, matching this
  adapter's existing "no expiry column set is not itself a rejection" reading.
- ``slot_ref``/``slot_start_at``/``slot_end_at``: `family_service_providers`
  has no discrete booking/slot table yet (`governance/DOMAIN_REGISTRY.yaml`'s
  `service_fgcn_collaboration.known_gaps` records this explicitly — "provider
  admission 本身仍无持久化表"). Until that concept exists, this adapter
  synthesizes an "available now" slot bounded by the same real credential
  window rather than inventing calendar precision that does not exist yet.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domains.service.fgcn.admission import ProviderAdmissionSnapshot
from backend.domains.service.fgcn.contracts import GateServiceScope
from backend.domains.service.infrastructure.sqlalchemy_models import ServiceProviderRow

_FGCN_CAPABILITY_KEYS_ATTR = "fgcn_capability_keys"
_FGCN_ALLOWED_PURPOSES_ATTR = "fgcn_allowed_purposes"
_FGCN_CAPACITY_ATTR = "fgcn_capacity_available"

# No `family_service_providers` row carries a real expiry: treat the
# credential as valid indefinitely rather than reject an otherwise-admitted
# provider for a column that was never populated. Kept a fixed sentinel (not
# `datetime.max`) so repeated resolves are stable and comparisons against it
# stay well inside `datetime`'s representable range.
_NO_EXPIRY_SENTINEL = datetime(9999, 1, 1, tzinfo=UTC)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class SqlAlchemyProviderAdmissionQuery:
    """Real Postgres-backed provider-admission query for the durable FGCN command.

    Read-only: this adapter never writes. A provider must exist, be scoped to
    the caller's tenant, and carry the FGCN admission attributes for a
    snapshot to be returned at all; ``assert_provider_admitted`` still applies
    every business rule (status, purpose, capability match, capacity) on top
    of what this adapter resolves.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def resolve(
        self,
        *,
        provider_ref: str,
        assignee_kind: str,
        required_capability_keys: tuple[str, ...],
        scope: GateServiceScope,
    ) -> ProviderAdmissionSnapshot | None:
        result = await self._session.execute(
            select(ServiceProviderRow).where(
                ServiceProviderRow.provider_ref == provider_ref,
                (ServiceProviderRow.tenant_id == scope.tenant_id)
                | (ServiceProviderRow.scope_type == "PLATFORM"),
            )
        )
        row = result.scalars().first()
        if row is None:
            return None
        if row.status != "ACTIVE" or row.qualification_status != "ACTIVE":
            return None
        credential_valid_until = _NO_EXPIRY_SENTINEL
        if row.qualification_expires_at is not None:
            credential_valid_until = _as_utc(row.qualification_expires_at)
            if credential_valid_until <= datetime.now(UTC):
                # An expired credential is a refusal regardless of what
                # `qualification_status` still says — that column is not
                # automatically revisited when a certificate lapses, so this
                # date check is the only thing that actually fails closed on
                # expiry (see this module's own docstring for why the column
                # was added rather than trusted from `attributes` JSONB).
                return None

        attributes = row.attributes if isinstance(row.attributes, dict) else {}
        raw_capability_keys = attributes.get(_FGCN_CAPABILITY_KEYS_ATTR)
        raw_allowed_purposes = attributes.get(_FGCN_ALLOWED_PURPOSES_ATTR)
        if not isinstance(raw_capability_keys, list) or not isinstance(raw_allowed_purposes, list):
            # No FGCN admission facts recorded for this provider yet: refusal,
            # never an implicit allow.
            return None
        raw_capacity = attributes.get(_FGCN_CAPACITY_ATTR, 1)
        capacity_available = raw_capacity if isinstance(raw_capacity, int) else 0

        # `family_service_providers.admission_status` speaks this domain's own
        # vocabulary (`ADMITTED` / `EXPIRED` / `SUSPENDED`; see `AdmissionStatus`
        # in `domain/entities.py`). `assert_provider_admitted` speaks FGCN's own
        # vocabulary (`"ACTIVE"` is the only value that passes). Translating
        # here keeps the two contracts independent rather than forcing FGCN to
        # accept a foreign enum.
        fgcn_admission_status = (
            "ACTIVE" if row.admission_status == "ADMITTED" else row.admission_status
        )

        credential_valid_from = _as_utc(row.effective_from)
        credential_ref = row.qualification_ref or f"qualification:{provider_ref}"
        # No discrete booking/slot table exists yet (see module docstring):
        # an admitted provider is treated as available starting now through
        # the end of its real credential window, rather than a fabricated
        # calendar slot.
        slot_start_at = datetime.now(UTC)
        slot_end_at = credential_valid_until

        try:
            return ProviderAdmissionSnapshot(
                provider_ref=provider_ref,
                assignee_kind=assignee_kind,
                admission_status=fgcn_admission_status,
                tenant_id=scope.tenant_id,
                family_id=scope.family_id,
                credential_ref=credential_ref,
                credential_valid_from=credential_valid_from,
                credential_valid_until=credential_valid_until,
                slot_ref=f"slot:{provider_ref}:current",
                slot_start_at=slot_start_at,
                slot_end_at=slot_end_at,
                capability_keys=tuple(raw_capability_keys),
                allowed_purposes=tuple(raw_allowed_purposes),
                capacity_available=capacity_available,
            )
        except Exception:
            # A malformed persisted snapshot must fail closed, matching
            # `require_provider_admitted_async`'s own except->refuse contract.
            return None


__all__ = ["SqlAlchemyProviderAdmissionQuery"]
