from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.intelligence.model_gateway.attempt_persistence import ModelAttemptRow
from backend.intelligence.model_gateway.contracts import TokenUsage
from backend.intelligence.model_gateway.usage import CostRate, aggregate_attempts


def _attempt(
    *,
    provider_id: str = "provider-1",
    model: str | None = "model-1",
    prompt: int | None = 100,
    completion: int | None = 25,
    total: int | None = 125,
) -> ModelAttemptRow:
    return ModelAttemptRow(
        attempt_id="a",
        provider_id=provider_id,
        use_case="demo",
        data_class="SYNTHETIC",
        environment="test",
        route_sequence=0,
        status="SUCCESS",
        started_at=datetime.now(UTC),
        model=model,
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=total,
    )


def test_aggregate_attempts_reports_tokens_and_explicit_cost() -> None:
    summary = aggregate_attempts(
        [_attempt()],
        rates={
            ("provider-1", "model-1"): CostRate(
                "provider-1", "model-1", prompt_microusd_per_1k=100, completion_microusd_per_1k=200
            )
        },
    )
    assert summary.attempt_count == 1
    assert summary.total_tokens == 125
    assert summary.estimated_cost_microusd == 15
    assert summary.unpriced_attempts == 0


def test_aggregate_attempts_fails_closed_on_unknown_price() -> None:
    summary = aggregate_attempts([_attempt()])
    assert summary.total_tokens == 125
    assert summary.estimated_cost_microusd is None
    assert summary.unpriced_attempts == 1


def test_aggregate_attempts_reconstructs_total_when_provider_omits_it() -> None:
    summary = aggregate_attempts([_attempt(total=None, completion=7, prompt=11)])
    assert summary.total_tokens == 18


def test_token_usage_rejects_negative_or_inconsistent_provider_values() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        TokenUsage(prompt_tokens=-1)
    with pytest.raises(ValueError, match="below prompt"):
        TokenUsage(prompt_tokens=5, completion_tokens=5, total_tokens=9)
