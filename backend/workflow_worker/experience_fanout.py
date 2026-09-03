"""Atomic composite consumer for the single-ack Experience outbox."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from backend.intelligence.experience.persistence import StoredExperienceMessage


class ExperienceMessageConsumer(Protocol):
    async def consume(self, message: StoredExperienceMessage) -> None: ...


@dataclass(frozen=True, slots=True)
class AtomicExperienceFanoutConsumer:
    """Run every required projection before the outer worker acknowledges once."""

    consumers: tuple[ExperienceMessageConsumer, ...]

    def __post_init__(self) -> None:
        if not self.consumers:
            raise ValueError("experience fanout requires at least one consumer")
        if any(not callable(getattr(item, "consume", None)) for item in self.consumers):
            raise TypeError("experience fanout consumers must implement consume")

    async def consume(self, message: StoredExperienceMessage) -> None:
        for consumer in self.consumers:
            await consumer.consume(message)


__all__ = ["AtomicExperienceFanoutConsumer", "ExperienceMessageConsumer"]
