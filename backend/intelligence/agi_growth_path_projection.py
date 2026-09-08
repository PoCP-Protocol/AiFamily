"""Read-only projection of a vertical AGI run into a next-round growth path."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.intelligence.experience.run_http import RunReplaySnapshot


@dataclass(frozen=True, slots=True)
class GrowthPathProjection:
    family_need_id: str
    path_id: str
    run_id: str
    context_snapshot_ref: str
    decision_ref: str | None
    decision_state: str | None
    next_step: str | None
    path: tuple[Any, ...]
    status: str
    observations: tuple[Any, ...] = ()
    evidence: tuple[Any, ...] = ()
    unknowns: tuple[Any, ...] = ()
    contradictions: tuple[Any, ...] = ()
    requires_human_confirmation: bool = True
    feedback_refs: tuple[str, ...] = ()


def project_next_growth_path(snapshot: RunReplaySnapshot) -> GrowthPathProjection:
    """Project a replay snapshot without model calls or state mutation.

    The draft payload is the only source for path content; interactions only
    provide Guardian decision metadata. Deleted runs intentionally fail closed.
    """

    if snapshot.deletion_state == "deleted" or snapshot.draft_payload is None:
        raise ValueError("DELETED_RUN_NOT_READABLE")
    payload = dict(snapshot.draft_payload)
    family_need_id = str(payload.get("family_need_id", "")).strip()
    path_id = str(payload.get("path_id", "")).strip()
    payload_run_id = str(payload.get("run_id", snapshot.run_id)).strip()
    context_ref = str(payload.get("context_snapshot_ref", "")).strip()
    if not all((family_need_id, path_id, snapshot.run_id, context_ref)):
        raise ValueError("GROWTH_PATH_CORRELATION_REQUIRED")
    if payload_run_id != snapshot.run_id:
        raise ValueError("GROWTH_PATH_RUN_ID_MISMATCH")
    decision_ref: str | None = None
    decision_state: str | None = None
    decision_edit: dict[str, Any] = {}
    feedback_refs: list[str] = []
    for entry in snapshot.interactions:
        if entry.interaction_type.value == "feedback":
            if entry.event_id:
                feedback_refs.append(entry.event_id)
            continue
        if entry.interaction_type.value != "decision":
            continue
        if entry.payload.get("decision_ref"):
            decision_ref = str(entry.payload["decision_ref"])
        if entry.payload.get("state"):
            decision_state = str(entry.payload["state"])
        elif entry.payload.get("decision"):
            decision_state = str(entry.payload["decision"])
        if isinstance(entry.payload.get("edits"), dict):
            decision_edit = dict(entry.payload["edits"])
        if entry.payload.get("replacement_text"):
            decision_edit["next_step"] = entry.payload["replacement_text"]
    output = payload.get("output")
    if not isinstance(output, dict):
        output = payload
    path = output.get("path", ())
    if not isinstance(path, (list, tuple)):
        path = ()
    next_step = output.get("next_step")

    def _tuple_field(name: str) -> tuple[Any, ...]:
        value = output.get(name, ())
        return tuple(value) if isinstance(value, (list, tuple)) else ()

    if decision_state == "EDIT":
        if "next_step" in decision_edit:
            next_step = decision_edit["next_step"]
        if isinstance(decision_edit.get("path"), (list, tuple)):
            path = decision_edit["path"]
    if decision_state == "REJECT":
        next_step = None
        path = ()
    status = "DRAFT"
    if decision_state == "DEFER":
        status = "REVIEW_REQUIRED"
    elif decision_state == "REJECT":
        status = "REJECTED"
    return GrowthPathProjection(
        family_need_id=family_need_id,
        path_id=path_id,
        run_id=snapshot.run_id,
        context_snapshot_ref=context_ref,
        decision_ref=decision_ref,
        decision_state=decision_state,
        next_step=str(next_step) if next_step is not None else None,
        path=tuple(path),
        observations=_tuple_field("observations"),
        evidence=_tuple_field("evidence"),
        unknowns=_tuple_field("unknowns"),
        contradictions=_tuple_field("contradictions"),
        status=status,
        feedback_refs=tuple(feedback_refs),
    )


__all__ = ["GrowthPathProjection", "project_next_growth_path"]
