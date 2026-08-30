"""Deterministic fault injection for the synthetic MediaAdapter PoC."""

from __future__ import annotations

from dataclasses import dataclass, field

from poc.media_adapter_sandbox.contract import FaultKind


@dataclass(slots=True)
class FaultInjector:
    active: set[FaultKind] = field(default_factory=set)

    def inject(self, fault: FaultKind) -> None:
        self.active.add(fault)

    def clear(self, fault: FaultKind | None = None) -> None:
        if fault is None:
            self.active.clear()
        else:
            self.active.discard(fault)

    def enabled(self, fault: FaultKind) -> bool:
        return fault in self.active
