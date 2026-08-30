"""Application seam that routes a multimodal experience into Model Gateway.

Callers declare capability and policy requirements, not a vendor.  The router
selects an explicitly admitted profile; the generation service then performs
the authoritative Model Gateway admission, attempt ledger, schema validation,
and provenance construction.  The returned value remains a ``ModelDraft`` and
cannot mutate a domain fact.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from backend.intelligence.experience.multimodal_generation import (
    MultimodalExperienceCommand,
    MultimodalExperienceDraft,
    MultimodalExperienceService,
)
from backend.intelligence.experience.multimodal_routing import (
    MultimodalRouteDecision,
    MultimodalRouter,
    MultimodalRouteRequest,
)
from backend.intelligence.experience.runs import DurableExperienceRun


@dataclass(frozen=True, slots=True)
class RoutedMultimodalExperienceDraft:
    """A draft plus the deterministic route decision that produced it."""

    route: MultimodalRouteDecision
    experience: MultimodalExperienceDraft

    @property
    def run_id(self) -> str:
        return self.experience.run_id

    @property
    def output(self) -> dict[str, object]:
        return self.experience.output

    @property
    def requires_human_confirmation(self) -> bool:
        return self.experience.requires_human_confirmation


class RoutedMultimodalExperienceService:
    """Select a model by capability, then invoke the sole gateway seam."""

    def __init__(
        self,
        *,
        router: MultimodalRouter,
        generation: MultimodalExperienceService,
    ) -> None:
        self._router = router
        self._generation = generation

    async def generate_draft(
        self,
        command: MultimodalExperienceCommand,
        route_request: MultimodalRouteRequest,
        *,
        run: DurableExperienceRun | None = None,
    ) -> RoutedMultimodalExperienceDraft:
        self._assert_command_matches_route(command, route_request)
        route = self._router.route(route_request)
        routed_command = replace(command, provider_id=route.selected.provider_id)
        experience = await self._generation.generate_draft(routed_command, run=run)
        return RoutedMultimodalExperienceDraft(route=route, experience=experience)

    @staticmethod
    def _assert_command_matches_route(
        command: MultimodalExperienceCommand,
        route_request: MultimodalRouteRequest,
    ) -> None:
        if command.use_case != route_request.use_case:
            raise ValueError("command and route use_case must match")
        if command.data_class != route_request.data_class:
            raise ValueError("command and route data_class must match")


__all__ = [
    "RoutedMultimodalExperienceDraft",
    "RoutedMultimodalExperienceService",
]
