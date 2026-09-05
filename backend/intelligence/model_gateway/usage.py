"""Provider-neutral token and cost aggregation for AI operations.

The Model Gateway records provider-reported usage; this module turns those
records into an auditable summary without including vendor prices in runtime
code.  A rate card is explicit input, so an unknown or stale price never turns
into a fabricated cost number.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from .attempt_persistence import ModelAttemptRow


@dataclass(frozen=True, slots=True)
class CostRate:
    """Price in micro-USD per 1K prompt/completion tokens."""

    provider_id: str
    model: str
    prompt_microusd_per_1k: int
    completion_microusd_per_1k: int

    def __post_init__(self) -> None:
        if not self.provider_id or not self.model:
            raise ValueError("CostRate provider_id and model are required")
        if self.prompt_microusd_per_1k < 0 or self.completion_microusd_per_1k < 0:
            raise ValueError("CostRate values must be non-negative")

    def estimate(self, prompt_tokens: int, completion_tokens: int) -> int:
        """Estimate with integer ceiling arithmetic (never fractional micros)."""

        if prompt_tokens < 0 or completion_tokens < 0:
            raise ValueError("token counts must be non-negative")
        prompt_cost = (self.prompt_microusd_per_1k * prompt_tokens + 999) // 1000
        completion_cost = (self.completion_microusd_per_1k * completion_tokens + 999) // 1000
        return prompt_cost + completion_cost


@dataclass(frozen=True, slots=True)
class UsageSummary:
    attempt_count: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_microusd: int | None
    unpriced_attempts: int


def aggregate_attempts(
    attempts: Iterable[ModelAttemptRow],
    *,
    rates: Mapping[tuple[str, str], CostRate] | None = None,
) -> UsageSummary:
    """Aggregate durable attempts for trace/cost reporting.

    Missing usage is treated as zero for token totals but is not silently
    priced.  If any attempt has usage but no matching rate, cost is ``None`` and
    ``unpriced_attempts`` identifies the gap for operations to resolve.
    """

    prompt = completion = total = 0
    cost = 0
    unpriced = 0
    count = 0
    for attempt in attempts:
        count += 1
        prompt_value = attempt.prompt_tokens or 0
        completion_value = attempt.completion_tokens or 0
        total_value = attempt.total_tokens
        prompt += prompt_value
        completion += completion_value
        total += total_value if total_value is not None else prompt_value + completion_value
        if prompt_value or completion_value:
            rate = rates.get((attempt.provider_id, attempt.model or "")) if rates else None
            if rate is None:
                unpriced += 1
            else:
                cost += rate.estimate(prompt_value, completion_value)
    return UsageSummary(
        attempt_count=count,
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=total,
        estimated_cost_microusd=None if unpriced else cost,
        unpriced_attempts=unpriced,
    )


__all__ = ["CostRate", "UsageSummary", "aggregate_attempts"]
