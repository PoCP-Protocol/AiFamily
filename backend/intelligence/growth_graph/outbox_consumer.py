"""Experience Outbox consumer for the Growth Graph read projection.

The consumer reconstructs only the governed ``ExperienceEvent`` contract and
projects an edge made of node/event/evidence references.  It never forwards an
arbitrary payload to the graph and never mutates a business aggregate.
"""

from __future__ import annotations

from typing import Protocol

from backend.intelligence.experience.achievement_consumer import decode_experience_event
from backend.intelligence.experience.outbox_worker import PermanentExperienceDeliveryError
from backend.intelligence.experience.persistence import StoredExperienceMessage

from .store import GrowthGraphEdge


class GrowthGraphProjectionPort(Protocol):
    async def project(self, edge: GrowthGraphEdge) -> GrowthGraphEdge: ...


class GrowthGraphEnvelopeError(PermanentExperienceDeliveryError):
    """Malformed event envelopes are not made valid by retrying."""


class GrowthGraphOutboxConsumer:
    """Idempotent outbox consumer that feeds a graph projection adapter."""

    def __init__(self, projection: GrowthGraphProjectionPort) -> None:
        if not callable(getattr(projection, "project", None)):
            raise TypeError("projection must expose async project(edge)")
        self._projection = projection
        self._processed: set[str] = set()

    async def consume(self, message: StoredExperienceMessage) -> None:
        if not isinstance(message, StoredExperienceMessage):
            raise GrowthGraphEnvelopeError("GRAPH_MESSAGE_REQUIRED")
        if message.message_id in self._processed:
            return
        try:
            event = decode_experience_event(message)
        except Exception as error:  # noqa: BLE001 - convert untrusted envelope to DLQ error
            raise GrowthGraphEnvelopeError("GRAPH_EVENT_INVALID") from error
        edge = GrowthGraphEdge(
            edge_id=f"graph:{event.event_id}",
            scope=event.scope,
            source_node=f"event:{event.event_id}",
            target_node=f"node:{event.node.value}",
            relation=f"experience.{event.event_type.value}",
            event_ref=event.event_id,
            evidence_refs=event.provenance.source_refs,
            provenance=event.provenance,
            observed_at=event.occurred_at,
        )
        await self._projection.project(edge)
        self._processed.add(message.message_id)


__all__ = [
    "GrowthGraphEnvelopeError",
    "GrowthGraphOutboxConsumer",
    "GrowthGraphProjectionPort",
]
