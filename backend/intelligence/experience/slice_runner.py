"""Provider-neutral evaluation slices for multimodal benchmark reports."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from backend.intelligence.experience.multimodal_eval import (
    GoldCase,
    MultimodalAdapter,
    MultimodalEvalError,
    MultimodalEvalRunner,
    MultimodalEvaluationReport,
)

SliceDimension = Literal["modality", "locale", "age_band"]


@dataclass(frozen=True, slots=True)
class EvaluationSlice:
    dimension: SliceDimension
    value: str
    case_ids: tuple[str, ...]
    report: MultimodalEvaluationReport


class MultimodalSliceRunner:
    """Run the same evaluation contract independently for each requested slice."""

    def __init__(self, *, runner: MultimodalEvalRunner | None = None) -> None:
        self._runner = runner or MultimodalEvalRunner()

    def run(
        self,
        cases: Sequence[GoldCase],
        adapters: Mapping[str, MultimodalAdapter],
        *,
        dimensions: Sequence[SliceDimension] = ("modality", "locale", "age_band"),
    ) -> tuple[EvaluationSlice, ...]:
        if not cases:
            raise MultimodalEvalError("at least one gold case is required")
        if not adapters:
            raise MultimodalEvalError("at least one adapter is required")
        if not dimensions or len(set(dimensions)) != len(dimensions):
            raise MultimodalEvalError("slice dimensions must be non-empty and unique")
        unsupported = set(dimensions).difference({"modality", "locale", "age_band"})
        if unsupported:
            raise MultimodalEvalError("unsupported evaluation slice dimension")

        slices: list[EvaluationSlice] = []
        for dimension in dimensions:
            groups: dict[str, list[GoldCase]] = defaultdict(list)
            for case in cases:
                for value in _values_for(case, dimension):
                    groups[value].append(case)
            for value in sorted(groups):
                grouped_cases = tuple(sorted(groups[value], key=lambda item: item.case_id))
                slices.append(
                    EvaluationSlice(
                        dimension=dimension,
                        value=value,
                        case_ids=tuple(case.case_id for case in grouped_cases),
                        report=self._runner.run(grouped_cases, adapters),
                    )
                )
        return tuple(slices)


def _values_for(case: GoldCase, dimension: SliceDimension) -> tuple[str, ...]:
    if dimension == "modality":
        return tuple(sorted(case.modalities))
    if dimension == "locale":
        return (case.locale,)
    return (case.age_band,)


__all__ = ["EvaluationSlice", "MultimodalSliceRunner", "SliceDimension"]
