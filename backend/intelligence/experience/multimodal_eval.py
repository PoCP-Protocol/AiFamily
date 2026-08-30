"""Offline, provider-neutral evaluation for multimodal model adapters.

The runner is deliberately an evaluation boundary, not a model gateway.  It
accepts versioned synthetic/anonymous cases and injected adapter callables; it
never opens a network connection and never stores media bytes.  A provider is
counted as successful only when schema, safety, provenance and refusal gates
all pass.  Any uncertainty therefore remains visible as a failed case instead
of being silently promoted to a quality score.
"""

from __future__ import annotations

import base64
import re
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from backend.intelligence.model_gateway.contracts import AiProvenance
from backend.intelligence.model_gateway.validation import SchemaValidator

FixtureKind = Literal["synthetic", "anonymous"]
SafetyAction = Literal["allow", "refuse"]
Modality = Literal["text", "image", "audio", "video"]

_MODALITIES = frozenset({"text", "image", "audio", "video"})
_RAW_MEDIA_KEYS = frozenset(
    {
        "raw_media",
        "media_bytes",
        "image_bytes",
        "audio_bytes",
        "video_bytes",
        "original_media",
        "media_content",
    }
)
_DATA_URL_RE = re.compile(r"^data:[^;]+;base64,", re.IGNORECASE)


class MultimodalEvalError(ValueError):
    """Raised when a fixture or adapter result cannot enter the eval ledger."""


@dataclass(frozen=True, slots=True)
class GoldCase:
    """A versioned, media-free benchmark case.

    ``media_refs`` are opaque fixture identifiers only.  A case may describe an
    image/audio/video without carrying its bytes, URL, or decoded content.
    ``expected_output`` is optional; when present the default quality evaluator
    uses an exact structural match after schema validation.
    """

    case_id: str
    version: str
    fixture_kind: FixtureKind
    modalities: tuple[Modality, ...]
    locale: str
    safety_labels: tuple[str, ...]
    expected_schema: dict[str, Any]
    expected_refusal: bool = False
    media_refs: tuple[str, ...] = ()
    expected_output: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if not self.case_id or not self.version or not self.locale:
            raise MultimodalEvalError("case_id, version and locale are required")
        if self.fixture_kind not in {"synthetic", "anonymous"}:
            raise MultimodalEvalError("fixture_kind must be synthetic or anonymous")
        if not self.modalities or len(set(self.modalities)) != len(self.modalities):
            raise MultimodalEvalError("modalities must contain at least one unique value")
        if not set(self.modalities).issubset(_MODALITIES):
            raise MultimodalEvalError("unsupported modality in gold case")
        if not self.expected_schema:
            raise MultimodalEvalError("expected_schema is required")
        if any(not label for label in self.safety_labels):
            raise MultimodalEvalError("safety_labels must not contain blank values")
        if any(not ref or _looks_like_raw_media(ref) for ref in self.media_refs):
            raise MultimodalEvalError("media_refs must be opaque, non-media identifiers")
        _assert_no_raw_media(self.expected_schema)
        if self.expected_output is not None:
            _assert_no_raw_media(self.expected_output)


@dataclass(frozen=True, slots=True)
class MultimodalAdapterResult:
    """The only value an injected provider adapter may return to the runner."""

    provider_id: str
    model: str
    model_version: str
    output: Mapping[str, Any] | None
    refused: bool
    safety_labels: tuple[str, ...]
    safety_passed: bool
    provenance: AiProvenance | None
    latency_ms: int
    cost_microusd: int
    refusal_reason: str | None = None

    def __post_init__(self) -> None:
        if not self.provider_id or not self.model or not self.model_version:
            raise MultimodalEvalError("provider/model/version are required")
        if isinstance(self.latency_ms, bool) or not isinstance(self.latency_ms, int):
            raise MultimodalEvalError("latency_ms must be an integer")
        if self.latency_ms < 0:
            raise MultimodalEvalError("latency_ms must be non-negative")
        if isinstance(self.cost_microusd, bool) or not isinstance(self.cost_microusd, int):
            raise MultimodalEvalError("cost_microusd must be an integer")
        if self.cost_microusd < 0:
            raise MultimodalEvalError("cost_microusd must be non-negative")
        if self.refused and not self.refusal_reason:
            raise MultimodalEvalError("a refusal must include refusal_reason")
        if self.output is not None:
            _assert_no_raw_media(self.output)


class MultimodalAdapter(Protocol):
    """Provider adapter seam; implementations may be fake and fully local."""

    def __call__(self, case: GoldCase) -> MultimodalAdapterResult: ...


QualityEvaluator = Callable[[GoldCase, MultimodalAdapterResult], float]


@dataclass(frozen=True, slots=True)
class ProviderEvaluationSummary:
    """Aggregate metrics for one provider/model/version tuple."""

    provider_id: str
    model: str
    model_version: str
    total_cases: int
    passed_cases: int
    quality_score: float
    schema_pass_rate: float
    refusal_accuracy_rate: float
    safety_pass_rate: float
    provenance_pass_rate: float
    latency_ms_p50: int | None
    latency_ms_p95: int | None
    cost_microusd_total: int
    failure_reasons: Mapping[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MultimodalEvaluationReport:
    """Media-free report; only aggregate metrics and failure reason counts."""

    case_version: str
    total_cases: int
    summaries: tuple[ProviderEvaluationSummary, ...]

    def by_provider(self) -> dict[tuple[str, str, str], ProviderEvaluationSummary]:
        return {(item.provider_id, item.model, item.model_version): item for item in self.summaries}


@dataclass(frozen=True, slots=True)
class _CaseOutcome:
    quality: float
    schema_passed: bool
    refusal_correct: bool
    safety_passed: bool
    provenance_passed: bool
    passed: bool
    latency_ms: int
    cost_microusd: int
    failures: tuple[str, ...]


class MultimodalEvalRunner:
    """Run deterministic local evals against one or more injected adapters."""

    def __init__(
        self,
        *,
        schema_validator: SchemaValidator | None = None,
        quality_evaluator: QualityEvaluator | None = None,
    ) -> None:
        self._schema_validator = schema_validator or SchemaValidator()
        self._quality_evaluator = quality_evaluator

    def run(
        self,
        cases: Sequence[GoldCase],
        adapters: Mapping[str, MultimodalAdapter],
    ) -> MultimodalEvaluationReport:
        """Evaluate every case with every adapter without invoking a network."""

        if not cases:
            raise MultimodalEvalError("at least one gold case is required")
        versions = {case.version for case in cases}
        if len(versions) != 1:
            raise MultimodalEvalError("all gold cases in one run must share one version")
        if not adapters:
            raise MultimodalEvalError("at least one adapter is required")

        grouped: dict[tuple[str, str, str], list[_CaseOutcome]] = defaultdict(list)
        for case in cases:
            for adapter_name, adapter in adapters.items():
                outcome, identity = self._evaluate_case(case, adapter_name, adapter)
                grouped[identity].append(outcome)

        summaries = tuple(
            _summarize(identity, outcomes)
            for identity, outcomes in sorted(grouped.items(), key=lambda item: item[0])
        )
        return MultimodalEvaluationReport(
            case_version=next(iter(versions)),
            total_cases=len(cases),
            summaries=summaries,
        )

    def _evaluate_case(
        self,
        case: GoldCase,
        adapter_name: str,
        adapter: MultimodalAdapter,
    ) -> tuple[_CaseOutcome, tuple[str, str, str]]:
        """Evaluate one result, failing closed on every required boundary."""

        failures: list[str] = []
        try:
            result = adapter(case)
            if not isinstance(result, MultimodalAdapterResult):
                raise MultimodalEvalError("adapter must return MultimodalAdapterResult")
            _assert_no_raw_media(result)
        except Exception as exc:  # noqa: BLE001 - an adapter failure is a failed case
            identity = (adapter_name, "unknown", "unknown")
            failures.append(f"adapter_error:{type(exc).__name__}")
            return (
                _CaseOutcome(0.0, False, False, False, False, False, 0, 0, tuple(failures)),
                identity,
            )

        identity = (result.provider_id, result.model, result.model_version)
        if result.provider_id != adapter_name:
            failures.append("provider_identity_mismatch")

        refusal_correct = result.refused is case.expected_refusal
        if not refusal_correct:
            failures.append("refusal_mismatch")
        if set(result.safety_labels) != set(case.safety_labels):
            failures.append("safety_labels_mismatch")
        safety_passed = result.safety_passed and not (
            case.expected_refusal is False and result.refused
        )
        if not safety_passed:
            failures.append("safety_failed")

        schema_passed = False
        if not result.refused and result.output is not None:
            try:
                self._schema_validator.validate(
                    dict(result.output), case.expected_schema, provider_id=result.provider_id
                )
                schema_passed = True
            except Exception:  # schema validator intentionally exposes provider-neutral errors
                failures.append("schema_invalid")
        elif not case.expected_refusal:
            failures.append("missing_output")
        if case.expected_refusal and result.output is not None:
            failures.append("refusal_contains_output")

        provenance_passed = _provenance_matches(case, result)
        if not provenance_passed:
            failures.append("provenance_invalid")

        try:
            quality = self._quality(case, result, schema_passed, safety_passed, refusal_correct)
        except Exception:  # noqa: BLE001 - evaluator uncertainty must fail closed
            quality = 0.0
            failures.append("quality_evaluator_error")
        if not 0.0 <= quality <= 1.0:
            quality = 0.0
            failures.append("quality_score_invalid")

        passed = not failures and provenance_passed and schema_passed == (not case.expected_refusal)
        return (
            _CaseOutcome(
                quality,
                schema_passed,
                refusal_correct,
                safety_passed,
                provenance_passed,
                passed,
                result.latency_ms,
                result.cost_microusd,
                tuple(failures),
            ),
            identity,
        )

    def _quality(
        self,
        case: GoldCase,
        result: MultimodalAdapterResult,
        schema_passed: bool,
        safety_passed: bool,
        refusal_correct: bool,
    ) -> float:
        if self._quality_evaluator is not None:
            return float(self._quality_evaluator(case, result))
        if case.expected_output is not None and result.output is not None:
            return float(dict(result.output) == dict(case.expected_output))
        structured_ok = case.expected_refusal or schema_passed
        return float(structured_ok and safety_passed and refusal_correct)


def _provenance_matches(case: GoldCase, result: MultimodalAdapterResult) -> bool:
    provenance = result.provenance
    if not isinstance(provenance, AiProvenance):
        return False
    return (
        provenance.provider_id == result.provider_id
        and provenance.model == result.model
        and provenance.model_version == result.model_version
        and provenance.latency_ms == result.latency_ms
        and provenance.schema_version == case.version
        and str(provenance.data_class)
        in (
            {"SYNTHETIC"} if case.fixture_kind == "synthetic" else {"SYNTHETIC", "OPERATIONAL_TEXT"}
        )
    )


def _summarize(
    identity: tuple[str, str, str], outcomes: Sequence[_CaseOutcome]
) -> ProviderEvaluationSummary:
    total = len(outcomes)
    failures = Counter(reason for outcome in outcomes for reason in outcome.failures)
    latencies = sorted(outcome.latency_ms for outcome in outcomes if outcome.latency_ms >= 0)
    return ProviderEvaluationSummary(
        provider_id=identity[0],
        model=identity[1],
        model_version=identity[2],
        total_cases=total,
        passed_cases=sum(outcome.passed for outcome in outcomes),
        quality_score=round(sum(outcome.quality for outcome in outcomes) / total, 6),
        schema_pass_rate=round(sum(outcome.schema_passed for outcome in outcomes) / total, 6),
        refusal_accuracy_rate=round(
            sum(outcome.refusal_correct for outcome in outcomes) / total, 6
        ),
        safety_pass_rate=round(sum(outcome.safety_passed for outcome in outcomes) / total, 6),
        provenance_pass_rate=round(
            sum(outcome.provenance_passed for outcome in outcomes) / total, 6
        ),
        latency_ms_p50=_percentile(latencies, 0.50),
        latency_ms_p95=_percentile(latencies, 0.95),
        cost_microusd_total=sum(outcome.cost_microusd for outcome in outcomes),
        failure_reasons=dict(sorted(failures.items())),
    )


def _percentile(values: Sequence[int], quantile: float) -> int | None:
    if not values:
        return None
    index = max(0, min(len(values) - 1, int((len(values) * quantile + 0.999999) - 1)))
    return values[index]


def _assert_no_raw_media(value: Any, *, _path: str = "$") -> None:
    if isinstance(value, (bytes, bytearray, memoryview)):
        raise MultimodalEvalError(f"raw media bytes are forbidden at {_path}")
    if isinstance(value, str) and _looks_like_raw_media(value):
        raise MultimodalEvalError(f"raw media content is forbidden at {_path}")
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if str(key).lower() in _RAW_MEDIA_KEYS:
                raise MultimodalEvalError(f"raw media field {key!r} is forbidden at {_path}")
            _assert_no_raw_media(nested, _path=f"{_path}.{key}")
    elif isinstance(value, (tuple, list, set, frozenset)):
        for index, nested in enumerate(value):
            _assert_no_raw_media(nested, _path=f"{_path}[{index}]")


def _looks_like_raw_media(value: str) -> bool:
    if _DATA_URL_RE.match(value):
        return True
    if len(value) > 512 and len(value) % 4 == 0:
        try:
            decoded = base64.b64decode(value, validate=True)
        except Exception:  # noqa: BLE001 - heuristic only
            return False
        return len(decoded) > 256
    return False


__all__ = [
    "FixtureKind",
    "GoldCase",
    "Modality",
    "MultimodalAdapter",
    "MultimodalAdapterResult",
    "MultimodalEvalError",
    "MultimodalEvalRunner",
    "MultimodalEvaluationReport",
    "ProviderEvaluationSummary",
    "SafetyAction",
]
