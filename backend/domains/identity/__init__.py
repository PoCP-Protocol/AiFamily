"""``auth_identity`` business domain — Account / IdentitySession / OtpChallenge.

Per ADR-0011 (`governance/ADR/ADR-0011-platform-identity-versus-business-identity-boundary.md`),
this is the canonical home for the business identity lifecycle: registration,
login/session issuance, introspection and revocation. It is deliberately
separate from `backend/platform/identity`, which stays limited to immutable
context value objects (`ActorContext`, `TenantContext`) with no repository and
no four-layer structure — see the ADR's decision §1 for the judgment call that
draws that line.
"""

from __future__ import annotations
