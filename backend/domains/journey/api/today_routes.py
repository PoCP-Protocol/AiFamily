"""Fixture-only S01 today/action HTTP adapter.

The adapter is intentionally mounted only by the development composition root.
It delegates action facts to the canonical ``GrowthOutcomeLoop`` writer and
never exposes a production fake repository.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from backend.domains.assessment.api.dev_auth import get_state
from backend.domains.journey.application.outcome_loop import (
    ActionFactStatus,
    GrowthOutcomeLoop,
)
from backend.platform.audit import AuditEvent


class TaskStateBody(BaseModel):
    state: str


class CheckInBody(BaseModel):
    note: str = ""


@dataclass
class _TodayState:
    loop: GrowthOutcomeLoop = field(default_factory=GrowthOutcomeLoop)
    states: dict[tuple[str, str], str] = field(default_factory=dict)
    receipts: dict[tuple[str, str, str], dict] = field(default_factory=dict)


_state = _TodayState()


def reset_today_state() -> None:
    global _state
    _state = _TodayState()


def build_today_router() -> APIRouter:
    router = APIRouter(prefix="/families")

    def identity(authorization: str | None, family_id: str) -> dict[str, str]:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="authorization required")
        value = get_state().tokens.get(authorization[7:])
        if not value:
            raise HTTPException(status_code=401, detail="unknown or expired session")
        if value["family_id"] != family_id:
            raise HTTPException(status_code=403, detail="family access denied")
        return value

    def key_or_400(key: str | None) -> str:
        if not key or not key.strip():
            raise HTTPException(status_code=400, detail="invalid_idempotency_key")
        return key.strip()

    def audit(actor: dict[str, str], action: str, resource: str, reason: str) -> None:
        get_state().recorder.record(
            AuditEvent(
                actor_id=actor["account_id"],
                tenant_id=actor["family_id"],
                action=action,
                resource_type="ActionTask",
                resource_id=resource,
                reason=reason,
                correlation_id=str(uuid4()),
            )
        )

    @router.get("/{family_id}/today")
    def today(
        family_id: str,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict:
        actor = identity(authorization, family_id)
        task_id = "task:today:first-step"
        status = _state.states.get((family_id, task_id), "AVAILABLE")
        audit(actor, "journey.today.read", task_id, "read today action projection")
        return {
            "family_id": family_id,
            "tenant_id": actor["family_id"],
            "tasks": [{"task_id": task_id, "state": status, "title": "今天的一件小行动"}],
            "data_class": "SYNTHETIC",
            "fixture_only": True,
        }

    @router.post("/{family_id}/tasks/{task_id}/state")
    def task_state(
        family_id: str,
        task_id: str,
        body: TaskStateBody,
        authorization: Annotated[str | None, Header()] = None,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> dict:
        actor = identity(authorization, family_id)
        key = key_or_400(idempotency_key)
        if body.state != "STARTED" or task_id != "task:today:first-step":
            raise HTTPException(status_code=400, detail="invalid_task_state")
        receipt_key = (family_id, task_id, key)
        if receipt_key in _state.receipts:
            return {**_state.receipts[receipt_key], "replayed": True}
        _state.states[(family_id, task_id)] = "STARTED"
        response = {"task_id": task_id, "state": "STARTED", "receipt_id": str(uuid4())}
        _state.receipts[receipt_key] = response
        audit(actor, "journey.task.started", task_id, "family started today action")
        return {**response, "replayed": False}

    @router.post("/{family_id}/tasks/{task_id}/check-in")
    def check_in(
        family_id: str,
        task_id: str,
        body: CheckInBody,
        authorization: Annotated[str | None, Header()] = None,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> dict:
        actor = identity(authorization, family_id)
        key = key_or_400(idempotency_key)
        receipt_key = (family_id, task_id, key)
        if receipt_key in _state.receipts:
            return {**_state.receipts[receipt_key], "replayed": True}
        if (
            task_id != "task:today:first-step"
            or _state.states.get((family_id, task_id)) != "STARTED"
        ):
            raise HTTPException(status_code=400, detail="task_must_be_started")
        action = _state.loop.record_action(
            tenant_id=family_id,
            family_id=family_id,
            plan_id="plan:today",
            task_id=task_id,
            day_number=1,
            status=ActionFactStatus.COMPLETED,
            actor_id=actor["account_id"],
            idempotency_key=key,
            evidence_refs=("fixture_only:check-in",),
        )
        _state.states[(family_id, task_id)] = "CHECKED_IN"
        response = {
            "task_id": task_id,
            "state": "CHECKED_IN",
            "action_id": action.action_id,
            "receipt_id": str(uuid4()),
        }
        _state.receipts[receipt_key] = response
        audit(actor, "journey.task.checked_in", task_id, body.note or "family checked in")
        return {**response, "replayed": False}

    return router


__all__ = ["build_today_router", "reset_today_state"]
