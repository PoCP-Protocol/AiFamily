"""Family manage-permission policy constants.

Byte-for-byte port of the constant declared in
`apps/api/src/modules/family/family-permission.ts`
(`assertFamilyManagePermission`). The actual check is two SQL lookups
(legacy `CreateFamily` audit success, or an ACTIVE `OWNER_GUARDIAN`/
`GUARDIAN` `family_memberships` row) — those live in the repository
implementations (`infrastructure/sqlalchemy_repository.py` for the real
Postgres-backed OR, `infrastructure/fake_repository.py` for the in-memory
test double), same as every other repository-port method in this domain.
This module only holds the policy's fixed vocabulary, so both
implementations reference the same literals instead of re-typing them.
"""
from __future__ import annotations

# Port of `CREATE_FAMILY_ACTION` in family-permission.ts — the legacy
# audit_logs.action_name value that, on a SUCCESS row for (family_id,
# actor_id), is treated as proof the actor is the family's creator.
CREATE_FAMILY_ACTION = "CreateFamily"

# Port of the `role in ('OWNER_GUARDIAN','GUARDIAN')` clause in
# assertFamilyManagePermission's family_memberships lookup.
FAMILY_MANAGE_ROLES = ("OWNER_GUARDIAN", "GUARDIAN")
