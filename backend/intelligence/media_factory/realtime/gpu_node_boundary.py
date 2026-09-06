"""GPU Media Compute Node boundary, as data (ADR-0019 §GPU Node Boundary).

A remote GPU node is a *media compute node* and nothing else. It may hold an
avatar engine, model weights and whatever ephemeral buffers a session needs; it
may never hold family truth. The reason is not tidiness: a rented GPU node is
outside AiFamily's consent, audit and deletion machinery, so family or minor
data landing there would put personal data somewhere the platform cannot prove
it can delete (R9, plus the delegated-processing obligations recorded in
`docs/12_governance/COMPLIANCE_HARD_CONSTRAINTS.md`).

Written as lists rather than prose so a test can assert them. Prose in a runbook
is exactly the form of "enforcement" R14 exists to distrust.
"""

from __future__ import annotations

from typing import Any

#: State a GPU media compute node may hold, all of it ephemeral and rebuildable.
GPU_NODE_ALLOWED_STATE: tuple[str, ...] = (
    "avatar_engine_binaries",
    "avatar_model_weights",
    "temporary_avatar_session_state",
    "temporary_audio_chunks",
    "temporary_frame_buffers",
    "runtime_metrics",
    "ephemeral_caches",
)

#: State that must never be canonical on a GPU node. Each of these is owned by a
#: domain inside AiFamily, and a copy on rented hardware would be a second
#: canonical location — an R2 violation with a compliance blast radius.
GPU_NODE_FORBIDDEN_CANONICAL_STATE: tuple[str, ...] = (
    "user_memory",
    "family_profile",
    "course_state",
    "assessment_state",
    "authorization_state",
    "business_truth",
    "principal_long_term_memory",
)

#: Where each forbidden item actually lives. An "it stays in AiFamily" claim with
#: no owner named is unfalsifiable.
CANONICAL_OWNER: dict[str, str] = {
    "user_memory": "AiFamily — backend/intelligence (Principal memory, not yet built)",
    "family_profile": "AiFamily — Family domain",
    "course_state": "AiFamily — Journey / Growth domain",
    "assessment_state": "AiFamily — backend/domains/assessment",
    "authorization_state": "AiFamily — backend/platform/authorization",
    "business_truth": "AiFamily — the owning business domain (R2)",
    "principal_long_term_memory": "AiFamily — Principal Runtime (not yet built)",
}

#: Data classes a GPU node may receive at all. Audio chunks and identity images
#: are the only payloads a realtime avatar turn needs, and both are transient.
GPU_NODE_ACCEPTED_PAYLOADS: tuple[str, ...] = (
    "identity_reference_image",
    "turn_audio_chunks",
)

GPU_NODE_RETENTION_POLICY = "EPHEMERAL_PER_SESSION"


def is_allowed_on_gpu_node(state_name: str) -> bool:
    return state_name in GPU_NODE_ALLOWED_STATE


def assert_not_canonical_on_gpu_node(state_name: str) -> None:
    """Fail closed when someone proposes putting business truth on a GPU node."""
    if state_name in GPU_NODE_FORBIDDEN_CANONICAL_STATE:
        owner = CANONICAL_OWNER.get(state_name, "AiFamily")
        raise ValueError(
            f"GPU_NODE_BOUNDARY_VIOLATION: {state_name!r} must stay canonical in "
            f"{owner}; a GPU media compute node holds ephemeral session state only "
            "(ADR-0019)."
        )


def gpu_node_boundary_manifest() -> dict[str, Any]:
    return {
        "boundary": "GPU_MEDIA_COMPUTE_NODE",
        "adr": "governance/ADR/ADR-0019-realtime-avatar-provider-and-gpu-node-boundary.md",
        "allowed_state": list(GPU_NODE_ALLOWED_STATE),
        "forbidden_canonical_state": list(GPU_NODE_FORBIDDEN_CANONICAL_STATE),
        "canonical_owner": dict(CANONICAL_OWNER),
        "accepted_payloads": list(GPU_NODE_ACCEPTED_PAYLOADS),
        "retention_policy": GPU_NODE_RETENTION_POLICY,
        "node_may_write_family_truth": False,
    }
