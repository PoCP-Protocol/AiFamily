"""One-shot durable consumer for accepted Human Gate requests.

The worker is intentionally a narrow command handler rather than a second
business orchestrator.  It loads a decision from the durable Human Gate,
rejects anything that is not an accepted request, and delegates execution to
the FGCN application command.  That command owns scope checks, the transaction,
and request-id idempotency.

There is no process loop or scheduler here yet.  A queue adapter can call this
handler from a future ``workflow_worker`` process; the handler is already
safe to retry after a crash because the owning command replays by the durable
``NamedActionRequest.request_id``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from backend.domains.service.domain.errors import ServiceConflictError
from backend.intelligence.human_gate import GateStatus, HumanTask
from backend.platform.audit import AuditRecorder

from .application import FGCNAssignmentRepository, execute_task_assignment_named_action
from .contracts import TaskAssignment


class HumanTaskReader(Protocol):
    """The only Human Gate capability the FGCN worker needs."""

    async def get(self, task_id: str) -> HumanTask: ...


async def consume_accepted_human_task(
    gate: HumanTaskReader,
    repo: FGCNAssignmentRepository,
    task_id: str,
    *,
    recorder: AuditRecorder,
    accepted_at: datetime | None = None,
) -> TaskAssignment:
    """Consume one accepted HumanTask and execute its FGCN Named Action.

    A rejected, escalated, open, or expired task has no executable business
    command and is refused.  If the process dies after the FGCN command has
    committed, calling this function again returns the same assignment without
    another assignment or audit event.
    """

    task = await gate.get(task_id)
    if task.status is not GateStatus.DECIDED or task.action_request is None:
        raise ServiceConflictError("fgcn_human_task_has_no_accepted_action")
    return await execute_task_assignment_named_action(
        repo,
        task.action_request,
        recorder=recorder,
        accepted_at=accepted_at,
    )


__all__ = ["HumanTaskReader", "consume_accepted_human_task"]
