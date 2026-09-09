"""Provider-neutral regression evaluation derived from guardian feedback.

This module is deliberately an evaluation boundary.  It accepts only bounded,
de-identified feedback references and versioned expected structures; it never
reads family records, calls a provider, promotes a model, or writes business
facts.  A report can be handed to the existing release gate by an operator.
"""

from __future__ import annotations

import hashlib
import inspect
import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from backend.intelligence.model_gateway.validation import SchemaValidator

FeedbackKind = Literal["GUARDIAN_ACCEPT", "GUARDIAN_EDIT", "GUARDIAN_REJECT"]


class FeedbackRegressionError(ValueError):
    """Raised when a feedback case is not safe to enter the eval boundary."""


@dataclass(frozen=True, slots=True)
class FeedbackRegressionCase:
    """A media-free, de-identified regression case from one feedback event."""

    case_ref: str
    case_version: str
    feedback_ref: str
    feedback_kind: FeedbackKind
    input_contract: Mapping[str, Any]
    expected_output: Mapping[str, Any]
    output_schema: Mapping[str, Any]
    scope_digest: str

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, str) and value.strip()
            for value in (
                self.case_ref,
                self.case_version,
                self.feedback_ref,
                self.scope_digest,
            )
        ):
            raise FeedbackRegressionError("feedback case identity is required")
        if self.feedback_kind not in {"GUARDIAN_ACCEPT", "GUARDIAN_EDIT", "GUARDIAN_REJECT"}:
            raise FeedbackRegressionError("unsupported feedback kind")
        if not self.input_contract or not self.expected_output or not self.output_schema:
            raise FeedbackRegressionError("feedback case contracts are required")
        _assert_bounded_json(self.input_contract)
        _assert_bounded_json(self.expected_output)
        _assert_bounded_json(self.output_schema)


@dataclass(frozen=True, slots=True)
class FeedbackRegressionResult:
    case_ref: str
    feedback_ref: str
    passed: bool
    failure_reason: str | None = None


@dataclass(frozen=True, slots=True)
class FeedbackRegressionReport:
    case_version: str
    total_cases: int
    passed_cases: int
    results: tuple[FeedbackRegressionResult, ...] = field(default_factory=tuple)

    @property
    def report_ref(self) -> str:
        payload = {
            "case_version": self.case_version,
            "total_cases": self.total_cases,
            "passed_cases": self.passed_cases,
            "results": [
                {
                    "case_ref": item.case_ref,
                    "feedback_ref": item.feedback_ref,
                    "passed": item.passed,
                    "failure_reason": item.failure_reason,
                }
                for item in self.results
            ],
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:24]
        return f"benchmark:feedback-regression:{self.case_version}:{digest}"

    @property
    def release_eligibility(self) -> Literal["ELIGIBLE", "BLOCKED"]:
        eligible = self.total_cases > 0 and self.passed_cases == self.total_cases
        return "ELIGIBLE" if eligible else "BLOCKED"

    def to_ledger_payload(self) -> dict[str, Any]:
        """Return only the bounded projection safe for the Experience ledger."""

        return {
            "report_ref": self.report_ref,
            "case_version": self.case_version,
            "total_cases": self.total_cases,
            "passed_cases": self.passed_cases,
            "release_eligibility": self.release_eligibility,
            "education_outcome_status": "NOT_MEASURED",
            "feedback_refs": tuple(item.feedback_ref for item in self.results),
        }


FeedbackRegressionAdapter = Callable[[FeedbackRegressionCase], Mapping[str, Any]]


class FeedbackRegressionCaseSource:
    """Port for a pre-authorized, de-identified feedback case batch."""

    async def load(self, *, case_version: str, batch_ref: str) -> Sequence[FeedbackRegressionCase]:
        raise NotImplementedError


class ExperienceFeedbackCaseSource(FeedbackRegressionCaseSource):
    """Read regression contracts from one already-authorized Experience run.

    ``batch_ref`` is a server-selected run id.  The source replays only that
    exact scope and accepts only feedback interactions carrying an explicit,
    bounded ``regression_case`` object.  It never infers expected output from
    family data or from the draft checkpoint.
    """

    def __init__(self, *, ledger: Any, scope: Any) -> None:
        if not callable(getattr(ledger, "replay", None)):
            raise TypeError("ledger must expose replay")
        self._ledger = ledger
        self._scope = scope

    async def load(self, *, case_version: str, batch_ref: str) -> Sequence[FeedbackRegressionCase]:
        replay = self._ledger.replay(scope=self._scope, run_id=batch_ref)
        snapshot = await replay if inspect.isawaitable(replay) else replay
        entries = getattr(snapshot, "entries", getattr(snapshot, "interactions", ()))
        cases: list[FeedbackRegressionCase] = []
        for entry in entries:
            interaction_type = getattr(getattr(entry, "interaction_type", None), "value", None)
            if interaction_type != "feedback":
                continue
            payload = getattr(entry, "payload", None)
            if not isinstance(payload, Mapping):
                continue
            contract = payload.get("regression_case")
            if not isinstance(contract, Mapping):
                continue
            feedback_ref = payload.get("feedback_ref") or getattr(entry, "event_id", None)
            if not isinstance(feedback_ref, str) or not feedback_ref.strip():
                raise FeedbackRegressionError("feedback reference is required")
            if contract.get("case_version") != case_version:
                raise FeedbackRegressionError("feedback regression case version mismatch")
            cases.append(
                FeedbackRegressionCase(
                    case_ref=str(contract.get("case_ref", "")),
                    case_version=case_version,
                    feedback_ref=feedback_ref,
                    feedback_kind=contract.get("feedback_kind", "GUARDIAN_EDIT"),
                    input_contract=contract.get("input_contract", {}),
                    expected_output=contract.get("expected_output", {}),
                    output_schema=contract.get("output_schema", {}),
                    scope_digest=str(contract.get("scope_digest", "")),
                )
            )
        return tuple(cases)


@dataclass(frozen=True, slots=True)
class FeedbackRegressionBatch:
    """Worker input; scope and run identity are resolved by the caller."""

    batch_ref: str
    case_version: str
    run_id: str
    scope: Any

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, str) and value.strip()
            for value in (self.batch_ref, self.case_version, self.run_id)
        ):
            raise FeedbackRegressionError("feedback regression batch identity is required")


@dataclass(frozen=True, slots=True)
class FeedbackRegressionWorkerResult:
    batch: FeedbackRegressionBatch
    report: FeedbackRegressionReport
    ledger_receipt: Any


class FeedbackRegressionWorker:
    """Run one bounded feedback batch and persist only its report projection."""

    def __init__(
        self,
        *,
        case_source: FeedbackRegressionCaseSource
        | Callable[..., Awaitable[Sequence[FeedbackRegressionCase]]],
        ledger: Any,
        adapter: FeedbackRegressionAdapter,
    ) -> None:
        if not callable(getattr(case_source, "load", None)) and not callable(case_source):
            raise TypeError("case_source must expose async load")
        if not callable(getattr(ledger, "record_evaluation", None)):
            raise TypeError("ledger must expose record_evaluation")
        if not callable(adapter):
            raise TypeError("adapter must be callable")
        self._case_source = case_source
        self._ledger = ledger
        self._adapter = adapter

    async def run_once(self, batch: FeedbackRegressionBatch) -> FeedbackRegressionWorkerResult:
        loader = getattr(self._case_source, "load", self._case_source)
        cases = loader(case_version=batch.case_version, batch_ref=batch.batch_ref)
        if not inspect.isawaitable(cases):
            raise TypeError("case_source.load must be awaitable")
        loaded = tuple(await cases)
        if not loaded:
            raise FeedbackRegressionError("feedback regression batch is empty")
        if any(case.case_version != batch.case_version for case in loaded):
            raise FeedbackRegressionError("feedback regression case version mismatch")
        report = evaluate_feedback_regression(
            loaded,
            self._adapter,
            case_version=batch.case_version,
        )
        receipt = await persist_feedback_regression_report(
            self._ledger,
            scope=batch.scope,
            run_id=batch.run_id,
            report=report,
            idempotency_key=f"feedback-regression:{batch.batch_ref}",
        )
        return FeedbackRegressionWorkerResult(batch=batch, report=report, ledger_receipt=receipt)


def evaluate_feedback_regression(
    cases: Sequence[FeedbackRegressionCase],
    adapter: FeedbackRegressionAdapter,
    *,
    case_version: str,
) -> FeedbackRegressionReport:
    """Evaluate a feedback-derived suite without contacting a model provider."""

    if not case_version.strip():
        raise FeedbackRegressionError("case_version is required")
    if not callable(adapter):
        raise TypeError("adapter must be callable")
    if not cases:
        raise FeedbackRegressionError("at least one feedback case is required")
    results: list[FeedbackRegressionResult] = []
    for case in cases:
        try:
            output = adapter(case)
            if not isinstance(output, Mapping):
                raise FeedbackRegressionError("adapter output must be an object")
            _assert_bounded_json(output)
            SchemaValidator().validate(
                output,
                dict(case.output_schema),
                provider_id="feedback-eval",
            )
            if dict(output) != dict(case.expected_output):
                raise FeedbackRegressionError("expected output mismatch")
        except Exception as error:
            results.append(
                FeedbackRegressionResult(
                    case_ref=case.case_ref,
                    feedback_ref=case.feedback_ref,
                    passed=False,
                    failure_reason=type(error).__name__ + ": " + str(error),
                )
            )
        else:
            results.append(
                FeedbackRegressionResult(
                    case_ref=case.case_ref,
                    feedback_ref=case.feedback_ref,
                    passed=True,
                )
            )
    return FeedbackRegressionReport(
        case_version=case_version,
        total_cases=len(results),
        passed_cases=sum(item.passed for item in results),
        results=tuple(results),
    )


async def persist_feedback_regression_report(
    ledger: Any,
    *,
    scope: Any,
    run_id: str,
    report: FeedbackRegressionReport,
    idempotency_key: str,
) -> Any:
    """Persist a report reference beside one durable experience run.

    The ledger is intentionally injected as a port.  This helper does not
    create a session, query a family, or archive report contents; it only
    projects the bounded report metadata through the existing evaluation
    interaction contract.
    """

    if not isinstance(run_id, str) or not run_id.strip():
        raise FeedbackRegressionError("run_id is required")
    if not isinstance(idempotency_key, str) or not idempotency_key.strip():
        raise FeedbackRegressionError("idempotency_key is required")
    method = getattr(ledger, "record_evaluation", None)
    if not callable(method):
        raise TypeError("ledger must expose record_evaluation")
    result = method(
        scope=scope,
        run_id=run_id,
        report_ref=report.report_ref,
        case_version=report.case_version,
        idempotency_key=idempotency_key,
        payload=report.to_ledger_payload(),
    )
    return await result if inspect.isawaitable(result) else result


_FORBIDDEN_KEYS = frozenset(
    {
        "raw_media",
        "media_bytes",
        "need_statement",
        "evidence_excerpt",
        "child_name",
        "guardian_name",
        "family_id",
        "tenant_id",
    }
)


def _assert_bounded_json(value: Any, *, depth: int = 0) -> None:
    if depth > 6:
        raise FeedbackRegressionError("feedback payload nesting is too deep")
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str) or key in _FORBIDDEN_KEYS:
                raise FeedbackRegressionError("feedback payload contains forbidden field")
            _assert_bounded_json(child, depth=depth + 1)
        return
    if isinstance(value, (list, tuple)):
        if len(value) > 64:
            raise FeedbackRegressionError("feedback payload list is too large")
        for child in value:
            _assert_bounded_json(child, depth=depth + 1)
        return
    if value is None or isinstance(value, (str, int, float, bool)):
        if isinstance(value, str) and len(value) > 2000:
            raise FeedbackRegressionError("feedback payload text is too large")
        return
    raise FeedbackRegressionError("feedback payload must be bounded JSON")


__all__ = [
    "FeedbackKind",
    "FeedbackRegressionAdapter",
    "FeedbackRegressionBatch",
    "FeedbackRegressionCase",
    "FeedbackRegressionCaseSource",
    "FeedbackRegressionError",
    "FeedbackRegressionReport",
    "FeedbackRegressionResult",
    "FeedbackRegressionWorker",
    "FeedbackRegressionWorkerResult",
    "ExperienceFeedbackCaseSource",
    "evaluate_feedback_regression",
    "persist_feedback_regression_report",
]
