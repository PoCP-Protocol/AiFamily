"""Composition-root consumer for Tool Action -> Human Gate delivery.

The generic outbox worker calls a consumer with one durable message.  This
adapter supplies the audit recorder and flushes it through the same
``AsyncSession`` used by the outbox, while deliberately leaving commit and
rollback to the composition root.  Consequently HumanTask creation, audit,
and ``mark_published`` can be committed atomically.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from backend.intelligence.tool_runtime.action_outbox import StoredToolActionMessage
from backend.platform.audit import AuditRecorder

from .persistence import SqlAlchemyHumanGate
from .tool_action_inbox import ToolActionHumanGateInbox


class SqlAlchemyToolActionHumanGateConsumer:
    """Deliver one outbox message into a SQL Human Gate transaction."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        inbox: ToolActionHumanGateInbox | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._session = session
        self._inbox = inbox or ToolActionHumanGateInbox(SqlAlchemyHumanGate(session))
        self._clock = clock

    async def consume(self, message: StoredToolActionMessage) -> None:
        """Create/replay the OPEN task and flush its audit event.

        No commit occurs here.  The caller must wrap the worker pass in the
        same transaction as the Tool Action outbox acknowledgement.
        """

        recorder = AuditRecorder()
        await self._inbox.deliver(message, recorder=recorder, now=self._clock())
        await recorder.flush(self._session)


__all__ = ["SqlAlchemyToolActionHumanGateConsumer"]
