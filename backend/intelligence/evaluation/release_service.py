"""Application boundary for evaluating and recording an AI release decision."""

from __future__ import annotations

from dataclasses import dataclass

from backend.intelligence.evaluation.release_gate import (
    AiReleaseGate,
    BenchmarkReport,
    ReleaseDecision,
    ReleaseGateThresholds,
)
from backend.intelligence.evaluation.release_persistence import ReleaseDecisionSink
from backend.intelligence.model_gateway.contracts import DataClass
from backend.intelligence.model_gateway.provider_registry import ProviderRegistry


@dataclass(frozen=True, slots=True)
class ReleaseAdmissionService:
    """Evaluate once, then append the immutable decision to an injected sink."""

    gate: AiReleaseGate
    sink: ReleaseDecisionSink

    async def evaluate_and_record(
        self,
        *,
        report: BenchmarkReport,
        provider_registry: ProviderRegistry,
        environment: str,
        thresholds: ReleaseGateThresholds | None = None,
        candidate_id: str | None = None,
        data_class: DataClass = "SYNTHETIC",
    ) -> ReleaseDecision:
        decision = self.gate.evaluate(
            report=report,
            provider_registry=provider_registry,
            environment=environment,
            thresholds=thresholds,
            candidate_id=candidate_id,
            data_class=data_class,
        )
        return await self.sink.append(decision)


__all__ = ["ReleaseAdmissionService"]
