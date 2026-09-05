"""Provider-neutral multimodal route planning.

This module describes *which* approved model should handle a multimodal request;
it does not invoke a provider.  Invocation remains behind
``backend.intelligence.model_gateway`` (R7).  Profiles for Qwen and Doubao are
therefore declarations, not credentials or network clients.  Until compliance
and supplier review promotes a profile, the router refuses it (fail closed).

The route decision is deliberately small and explainable: data class, requested
modalities, budget/latency policy, selected provider and fallback order.  The
``MultimodalProvenanceInput`` can be copied into ``AiProvenance`` by the gateway;
it never contains prompts, media bytes, URLs or family content.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal

from backend.intelligence.model_gateway.contracts import DataClass
from backend.intelligence.model_gateway.provider_registry import (
    CALLABLE_STATUSES,
    ProviderStatus,
)

Modality = Literal["TEXT", "IMAGE", "AUDIO", "VIDEO"]
RouteStrategy = Literal["latency", "cost", "balanced"]
RouteFailure = Literal["NO_CAPABLE_PROVIDER", "INVALID_REQUEST"]


class MultimodalRouteError(RuntimeError):
    """A route cannot be selected without weakening policy."""

    def __init__(self, reason: RouteFailure, message: str) -> None:
        super().__init__(f"[{reason}] {message}")
        self.reason = reason
        self.message = message


@dataclass(frozen=True, slots=True)
class ProviderCapabilityProfile:
    """Capability and governance metadata for one multimodal model.

    ``status`` and the delegation fields intentionally mirror the model gateway
    registry.  Keeping them on the profile lets route planning fail closed before
    a call; the gateway still performs the authoritative admission immediately
    before invocation.
    """

    provider_id: str
    vendor: str
    model: str
    model_version: str
    modalities: frozenset[Modality]
    status: ProviderStatus
    approved_environments: tuple[str, ...]
    approved_data_classes: frozenset[DataClass]
    sub_delegates: bool | None
    supports_structured_output: bool
    estimated_input_cost_microusd_per_1k_tokens: int
    estimated_latency_ms_p50: int
    max_media_items: int = 8
    security_assessment_ref: str | None = None
    processing_agreement_ref: str | None = None
    deletion_on_termination_committed: bool = False

    def __post_init__(self) -> None:
        if not all(
            (
                self.provider_id,
                self.vendor,
                self.model,
                self.model_version,
                self.approved_environments,
            )
        ):
            raise ValueError("provider identity and approved environments are required")
        if not self.modalities:
            raise ValueError("a capability profile must declare at least one modality")
        if self.estimated_input_cost_microusd_per_1k_tokens < 0:
            raise ValueError("estimated_input_cost_microusd_per_1k_tokens must be non-negative")
        if self.estimated_latency_ms_p50 <= 0:
            raise ValueError("estimated_latency_ms_p50 must be positive")
        if self.max_media_items <= 0:
            raise ValueError("max_media_items must be positive")

    def estimated_cost_microusd(self, input_tokens: int) -> int:
        """Estimate input cost using integer arithmetic (no fake precision)."""
        if input_tokens <= 0:
            raise ValueError("input_tokens must be positive")
        rate = self.estimated_input_cost_microusd_per_1k_tokens
        return (rate * input_tokens + 999) // 1000

    def can_serve(self, request: MultimodalRouteRequest) -> bool:
        """Return whether this profile is explicitly admitted for ``request``."""
        if self.status not in CALLABLE_STATUSES:
            return False
        if request.environment not in self.approved_environments:
            return False
        if not set(request.modalities).issubset(self.modalities):
            return False
        if request.media_item_count > self.max_media_items:
            return False
        if request.data_class not in self.approved_data_classes:
            return False
        if request.require_structured_output and not self.supports_structured_output:
            return False
        if request.data_class in {"MINOR_PERSONAL_DATA", "FAMILY_PRIVATE_TEXT"}:
            if self.sub_delegates is not False:
                return False
            if not self.security_assessment_ref or not self.processing_agreement_ref:
                return False
            if not self.deletion_on_termination_committed:
                return False
        return True


@dataclass(frozen=True, slots=True)
class MultimodalRouteRequest:
    """A policy-bound route request; no media payload is carried here."""

    use_case: str
    data_class: DataClass
    modalities: tuple[Modality, ...]
    environment: str
    estimated_input_tokens: int
    media_item_count: int = 0
    strategy: RouteStrategy = "balanced"
    max_latency_ms: int | None = None
    max_cost_microusd: int | None = None
    require_structured_output: bool = True

    def __post_init__(self) -> None:
        if not self.use_case or not self.environment:
            raise MultimodalRouteError("INVALID_REQUEST", "use_case and environment are required")
        if not self.modalities or len(set(self.modalities)) != len(self.modalities):
            raise MultimodalRouteError(
                "INVALID_REQUEST", "at least one unique modality is required"
            )
        known = {"TEXT", "IMAGE", "AUDIO", "VIDEO"}
        if not set(self.modalities).issubset(known):
            raise MultimodalRouteError("INVALID_REQUEST", "unsupported modality requested")
        if self.estimated_input_tokens <= 0:
            raise MultimodalRouteError("INVALID_REQUEST", "estimated_input_tokens must be positive")
        if (
            not isinstance(self.media_item_count, int)
            or isinstance(self.media_item_count, bool)
            or self.media_item_count < 0
        ):
            raise MultimodalRouteError(
                "INVALID_REQUEST", "media_item_count must be a non-negative integer"
            )
        if self.strategy not in {"latency", "cost", "balanced"}:
            raise MultimodalRouteError("INVALID_REQUEST", "unknown route strategy")
        if self.max_latency_ms is not None and self.max_latency_ms <= 0:
            raise MultimodalRouteError("INVALID_REQUEST", "max_latency_ms must be positive")
        if self.max_cost_microusd is not None and self.max_cost_microusd < 0:
            raise MultimodalRouteError("INVALID_REQUEST", "max_cost_microusd must be non-negative")


@dataclass(frozen=True, slots=True)
class MultimodalProvenanceInput:
    """Safe, explainable inputs for the gateway's full ``AiProvenance`` record."""

    policy_version: str
    provider_id: str
    vendor: str
    model: str
    model_version: str
    use_case: str
    data_class: DataClass
    modalities: tuple[Modality, ...]
    strategy: RouteStrategy
    estimated_latency_ms_p50: int
    estimated_cost_microusd: int
    fallback_provider_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MultimodalRouteDecision:
    """One deterministic route plus an audit-safe explanation."""

    selected: ProviderCapabilityProfile
    fallback_provider_ids: tuple[str, ...]
    estimated_latency_ms: int
    estimated_cost_microusd: int
    provenance_input: MultimodalProvenanceInput


class MultimodalRouter:
    """Select an admitted provider without making any network call."""

    def __init__(
        self,
        profiles: tuple[ProviderCapabilityProfile, ...],
        *,
        policy_version: str = "multimodal-routing.v1",
    ) -> None:
        if not policy_version.strip():
            raise ValueError("routing policy version is required")
        by_id: dict[str, ProviderCapabilityProfile] = {}
        for profile in profiles:
            if profile.provider_id in by_id:
                raise ValueError(f"duplicate provider_id {profile.provider_id!r}")
            by_id[profile.provider_id] = profile
        self._profiles = tuple(by_id.values())
        self._policy_version = policy_version

    @property
    def policy_version(self) -> str:
        return self._policy_version

    @property
    def configuration_digest(self) -> str:
        """Hash every route input that can change selection or admission."""

        profiles = []
        for profile in sorted(self._profiles, key=lambda item: item.provider_id):
            profiles.append(
                {
                    "provider_id": profile.provider_id,
                    "vendor": profile.vendor,
                    "model": profile.model,
                    "model_version": profile.model_version,
                    "modalities": sorted(profile.modalities),
                    "status": str(profile.status),
                    "approved_environments": sorted(profile.approved_environments),
                    "approved_data_classes": sorted(profile.approved_data_classes),
                    "sub_delegates": profile.sub_delegates,
                    "supports_structured_output": profile.supports_structured_output,
                    "estimated_input_cost_microusd_per_1k_tokens": (
                        profile.estimated_input_cost_microusd_per_1k_tokens
                    ),
                    "estimated_latency_ms_p50": profile.estimated_latency_ms_p50,
                    "max_media_items": profile.max_media_items,
                    "security_assessment_ref": profile.security_assessment_ref,
                    "processing_agreement_ref": profile.processing_agreement_ref,
                    "deletion_on_termination_committed": (
                        profile.deletion_on_termination_committed
                    ),
                }
            )
        return _configuration_digest(
            {"policy_version": self._policy_version, "profiles": profiles}
        )

    @property
    def provider_ids(self) -> tuple[str, ...]:
        """Provider ids declared by this route catalog, in stable order."""

        return tuple(sorted(self._profiles_by_id()))

    def profile(self, provider_id: str) -> ProviderCapabilityProfile:
        """Return one route profile without exposing mutable catalog state."""

        try:
            return self._profiles_by_id()[provider_id]
        except KeyError as exc:
            raise KeyError(f"unknown multimodal provider {provider_id!r}") from exc

    def _profiles_by_id(self) -> dict[str, ProviderCapabilityProfile]:
        return {profile.provider_id: profile for profile in self._profiles}

    def route(
        self,
        request: MultimodalRouteRequest,
        *,
        policy_version: str | None = None,
    ) -> MultimodalRouteDecision:
        if policy_version is not None and policy_version != self._policy_version:
            raise MultimodalRouteError(
                "INVALID_REQUEST",
                "routing policy version override differs from the configured catalog",
            )
        effective_policy_version = policy_version or self._policy_version
        eligible: list[tuple[ProviderCapabilityProfile, int]] = []
        for profile in self._profiles:
            if not profile.can_serve(request):
                continue
            estimated_cost = profile.estimated_cost_microusd(request.estimated_input_tokens)
            if (
                request.max_latency_ms is not None
                and profile.estimated_latency_ms_p50 > request.max_latency_ms
            ):
                continue
            if request.max_cost_microusd is not None and estimated_cost > request.max_cost_microusd:
                continue
            eligible.append((profile, estimated_cost))

        if not eligible:
            raise MultimodalRouteError(
                "NO_CAPABLE_PROVIDER",
                "no explicitly approved provider satisfies modality, data-class, "
                "environment and budget policy; refusing to guess or downgrade",
            )

        latency_weight, cost_weight = {
            "latency": (10, 1),
            "cost": (1, 10),
            "balanced": (5, 5),
        }[request.strategy]
        ordered = sorted(
            eligible,
            key=lambda item: (
                item[0].estimated_latency_ms_p50 * latency_weight + item[1] * cost_weight,
                item[0].estimated_latency_ms_p50,
                item[1],
                item[0].provider_id,
            ),
        )
        selected, selected_cost = ordered[0]
        fallbacks = tuple(profile.provider_id for profile, _ in ordered[1:])
        provenance = MultimodalProvenanceInput(
            policy_version=effective_policy_version,
            provider_id=selected.provider_id,
            vendor=selected.vendor,
            model=selected.model,
            model_version=selected.model_version,
            use_case=request.use_case,
            data_class=request.data_class,
            modalities=request.modalities,
            strategy=request.strategy,
            estimated_latency_ms_p50=selected.estimated_latency_ms_p50,
            estimated_cost_microusd=selected_cost,
            fallback_provider_ids=fallbacks,
        )
        return MultimodalRouteDecision(
            selected=selected,
            fallback_provider_ids=fallbacks,
            estimated_latency_ms=selected.estimated_latency_ms_p50,
            estimated_cost_microusd=selected_cost,
            provenance_input=provenance,
        )


def _configuration_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


# Candidate declarations only.  Their status is deliberately non-callable until
# legal, security and data-processing reviews are recorded in the provider
# registry.  They document the intended Qwen/Doubao capability comparison while
# ensuring an unreviewed vendor cannot receive family data by configuration drift.
QWEN_MULTIMODAL_CANDIDATE = ProviderCapabilityProfile(
    provider_id="qwen-multimodal-candidate",
    vendor="qwen",
    model="qwen-multimodal",
    model_version="declared-v1",
    modalities=frozenset({"TEXT", "IMAGE", "AUDIO", "VIDEO"}),
    status="TECHNICALLY_VALIDATED",
    approved_environments=("internal_livecheck",),
    approved_data_classes=frozenset({"SYNTHETIC", "OPERATIONAL_TEXT"}),
    sub_delegates=None,
    supports_structured_output=True,
    estimated_input_cost_microusd_per_1k_tokens=80,
    estimated_latency_ms_p50=900,
    deletion_on_termination_committed=False,
)

DOUBAO_MULTIMODAL_CANDIDATE = ProviderCapabilityProfile(
    provider_id="doubao-multimodal-candidate",
    vendor="doubao",
    model="doubao-multimodal",
    model_version="declared-v1",
    modalities=frozenset({"TEXT", "IMAGE", "AUDIO", "VIDEO"}),
    status="TECHNICALLY_VALIDATED",
    approved_environments=("internal_livecheck",),
    approved_data_classes=frozenset({"SYNTHETIC", "OPERATIONAL_TEXT"}),
    sub_delegates=None,
    supports_structured_output=True,
    estimated_input_cost_microusd_per_1k_tokens=60,
    estimated_latency_ms_p50=700,
    deletion_on_termination_committed=False,
)

DEFAULT_MULTIMODAL_CANDIDATES: tuple[ProviderCapabilityProfile, ...] = (
    QWEN_MULTIMODAL_CANDIDATE,
    DOUBAO_MULTIMODAL_CANDIDATE,
)
