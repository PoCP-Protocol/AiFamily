"""Provider admission — the compliance gate, evaluated before any network call.

## Why admission is a legal mechanism, not configuration

Calling an external LLM with family data is 委托第三方处理 under
《儿童个人信息网络保护规定》第16条. That article imposes four duties, and each maps
to a field below:

| 第16条 duty | Field |
|---|---|
| 先做安全评估 (prior security assessment) | `security_assessment_ref` |
| 签委托协议 (processing agreement) | `processing_agreement_ref` |
| 不得超出授权范围 (no scope excess) | `minor_data_allowed` / `private_text_allowed` |
| **不得转委托** (no sub-delegation) | `sub_delegates` |

The fourth is the hard one, and `docs/12_governance/COMPLIANCE_HARD_CONSTRAINTS.md`
§7 says so plainly: **most LLM vendors re-subcontract to third-party clouds.** So
`sub_delegates` is a required tri-state (`True` / `False` / `None` = not yet
established), and the admission rule is:

    a provider that sub-delegates — or whose sub-delegation status is unknown —
    may never receive minor personal data or family private text.

`None` being treated exactly as `True` for those data classes is the whole point.
"We have not asked the vendor yet" is not a defence under 第16条, and a registry
that let unknown default to permissive would be a compliance hole wearing the
shape of a config default.

## Why the registry is a Python module and not a generated YAML

`governance/FPAI_PROVIDER_REGISTRY.yaml` in the source repository declared three
providers while its generated artifact carried two, and its `--check` mode exited
1 on the baseline commit because no CI ever ran it — the drift is documented in
`tests/architecture/test_capability_registry.py`'s own docstring. Reproducing that
generator pattern would reproduce the drift.

So the admission rules live in code, the declarations are validated on
construction, and `load_provider_registry` can optionally read a YAML file for
operators — but the file is parsed into the same validated `ProviderRecord`
objects, with no generated intermediate artifact that can drift from its source.

## Fail-closed

`admit()` raises for anything it was not explicitly told to allow: unknown
provider id, wrong environment, disallowed data class, missing §16 paperwork,
non-approved status. There is no permissive branch.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from backend.intelligence.model_gateway.contracts import DataClass
from backend.intelligence.model_gateway.errors import ModelGatewayError

ProviderStatus = Literal[
    "REGISTERED",
    "TECHNICALLY_VALIDATED",
    "INTERNAL_APPROVED",
    "PRODUCTION_APPROVED",
    "SUSPENDED",
]
"""Governance lifecycle. The distinction that matters: an adapter passing a smoke
test is `TECHNICALLY_VALIDATED`, which grants **no** calling rights. Only
`INTERNAL_APPROVED` / `PRODUCTION_APPROVED` may be called, and only inside an
environment the record lists.
"""

CALLABLE_STATUSES: frozenset[str] = frozenset({"INTERNAL_APPROVED", "PRODUCTION_APPROVED"})

REGULATED_DATA_CLASSES: frozenset[str] = frozenset({"MINOR_PERSONAL_DATA", "FAMILY_PRIVATE_TEXT"})
"""Data classes for which 第16条 delegated-processing duties bite. `SYNTHETIC` and
`OPERATIONAL_TEXT` carry no personal-information subject, so the paperwork checks
do not apply to them — but the status/environment checks still do, because an
unapproved provider must not be reachable at all.
"""


@dataclass(frozen=True, slots=True)
class ProviderRecord:
    """One registered provider, with its compliance posture stated explicitly.

    Credential material is **not** here. The record carries `credential_env_var`
    — the *name* of the environment variable — so that governance can be
    reviewed, serialised and logged without ever moving a secret. Reading the
    variable happens in the adapter factory, inside this package, which is the
    only place R7 permits credential reads.
    """

    provider_id: str
    vendor: str
    model: str
    model_version: str
    status: ProviderStatus
    approved_environments: tuple[str, ...]

    # --- 《儿童个人信息网络保护规定》第16条 fields ---
    sub_delegates: bool | None
    """Does this vendor re-subcontract processing to a third party?

    `None` means "not established yet" and is treated as prohibitive for
    regulated data classes. See module docstring — this is the field the whole
    不得转委托 constraint hangs on, and optimism here is a legal defect.
    """
    minor_data_allowed: bool = False
    private_text_allowed: bool = False
    security_assessment_ref: str | None = None
    processing_agreement_ref: str | None = None
    deletion_on_termination_committed: bool = False
    processing_region: str = "unspecified"

    credential_env_var: str | None = None
    base_url_env_var: str | None = None
    timeout_seconds: float = 30.0
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.provider_id:
            raise ValueError("ProviderRecord.provider_id is required")
        if not self.approved_environments:
            raise ValueError(
                f"{self.provider_id}: approved_environments must not be empty — a provider "
                "approved nowhere is not callable anywhere, so say so explicitly"
            )
        if self.timeout_seconds <= 0:
            raise ValueError(f"{self.provider_id}: timeout_seconds must be positive")

        # A record that claims the right to process regulated data while
        # admitting (or not knowing) that it sub-delegates is internally
        # inconsistent under 第16条. Rejecting it at construction means such a
        # combination cannot even be written down, let alone reached at runtime.
        if self.sub_delegates is not False:
            claimed = [
                name
                for name, value in (
                    ("minor_data_allowed", self.minor_data_allowed),
                    ("private_text_allowed", self.private_text_allowed),
                )
                if value
            ]
            if claimed:
                state = "unknown" if self.sub_delegates is None else "true"
                raise ValueError(
                    f"{self.provider_id}: sub_delegates={state} but the record claims "
                    f"{claimed}. 《儿童个人信息网络保护规定》第16条 forbids 转委托; a "
                    "sub-delegating (or unassessed) provider cannot be authorised for "
                    "minor or family-private data. Resolve the vendor's subcontracting "
                    "structure first — see COMPLIANCE_HARD_CONSTRAINTS.md §7."
                )

    def permits_data_class(self, data_class: DataClass) -> bool:
        if data_class == "MINOR_PERSONAL_DATA":
            return self.minor_data_allowed
        if data_class == "FAMILY_PRIVATE_TEXT":
            return self.private_text_allowed
        return True


class ProviderRegistry:
    """The set of providers this runtime may reach, and the admission rule."""

    def __init__(self, records: list[ProviderRecord] | tuple[ProviderRecord, ...] = ()) -> None:
        by_id: dict[str, ProviderRecord] = {}
        for record in records:
            if record.provider_id in by_id:
                raise ValueError(
                    f"duplicate provider_id {record.provider_id!r} — one governance record "
                    "per provider (R2's one-canonical-entry rule applied to providers)"
                )
            by_id[record.provider_id] = record
        self._by_id = by_id

    def __contains__(self, provider_id: object) -> bool:
        return provider_id in self._by_id

    def __len__(self) -> int:
        return len(self._by_id)

    def provider_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._by_id))

    def get(self, provider_id: str) -> ProviderRecord:
        """Look up a record, refusing unknown ids rather than returning `None`.

        Returning `None` would put the fail-closed decision at every call site,
        and one forgetful call site is all it takes. Raising keeps the decision
        here.
        """
        record = self._by_id.get(provider_id)
        if record is None:
            raise ModelGatewayError(
                "POLICY_REJECTED",
                f"provider {provider_id!r} is not registered; registered providers are "
                f"{list(self.provider_ids())}. An unregistered provider is refused "
                "outright — 《儿童个人信息网络保护规定》第16条 requires a prior security "
                "assessment and a processing agreement, neither of which exists for a "
                "provider nobody registered.",
                provider_id=provider_id,
            )
        return record

    def admit(
        self,
        provider_id: str,
        *,
        data_class: DataClass,
        environment: str,
    ) -> ProviderRecord:
        """Return the record, or raise `POLICY_REJECTED`. No third outcome.

        Order of checks is deliberate: registration, then governance status, then
        environment, then data class, then §16 paperwork. Each rejection names the
        obligation it enforces, because a `POLICY_REJECTED` with no reason turns
        into someone widening the allowlist to make the error go away.
        """
        record = self.get(provider_id)

        if record.status not in CALLABLE_STATUSES:
            raise ModelGatewayError(
                "POLICY_REJECTED",
                f"provider {provider_id!r} has status {record.status!r}; only "
                f"{sorted(CALLABLE_STATUSES)} may be called. An adapter passing a "
                "technical smoke test is not a production approval.",
                provider_id=provider_id,
            )

        if environment not in record.approved_environments:
            raise ModelGatewayError(
                "POLICY_REJECTED",
                f"provider {provider_id!r} is not approved for environment "
                f"{environment!r} (approved: {list(record.approved_environments)})",
                provider_id=provider_id,
            )

        if not record.permits_data_class(data_class):
            raise ModelGatewayError(
                "POLICY_REJECTED",
                f"provider {provider_id!r} is not authorised for data class "
                f"{data_class!r}. 第16条 forbids the processor exceeding the scope of "
                "the delegation; sending this class would exceed it.",
                provider_id=provider_id,
            )

        if data_class in REGULATED_DATA_CLASSES:
            self._assert_delegation_paperwork(record, data_class)

        return record

    @staticmethod
    def _assert_delegation_paperwork(record: ProviderRecord, data_class: DataClass) -> None:
        """The 第16条 checklist, applied only where personal information is involved."""
        if record.sub_delegates is not False:
            state = "unknown" if record.sub_delegates is None else "true"
            raise ModelGatewayError(
                "POLICY_REJECTED",
                f"provider {record.provider_id!r} sub_delegates={state}; "
                f"{data_class} may not be sent to a provider that re-subcontracts "
                "processing, and an unestablished subcontracting structure is treated "
                "the same as one that does. 《儿童个人信息网络保护规定》第16条 "
                "不得转委托 — this is a legal question for 法务, not a runtime "
                "override (COMPLIANCE_HARD_CONSTRAINTS.md §7/§11.1).",
                provider_id=record.provider_id,
            )

        missing = [
            name
            for name, value in (
                ("security_assessment_ref", record.security_assessment_ref),
                ("processing_agreement_ref", record.processing_agreement_ref),
            )
            if not value
        ]
        if missing:
            raise ModelGatewayError(
                "POLICY_REJECTED",
                f"provider {record.provider_id!r} is missing {missing}; 第16条 requires a "
                "prior security assessment and a signed processing agreement before "
                f"delegating {data_class}",
                provider_id=record.provider_id,
            )

        if not record.deletion_on_termination_committed:
            raise ModelGatewayError(
                "POLICY_REJECTED",
                f"provider {record.provider_id!r} has not committed to deleting data on "
                "termination of the delegation, which 第16条 requires",
                provider_id=record.provider_id,
            )


# ---------------------------------------------------------------------------
# Declared providers
# ---------------------------------------------------------------------------
# This is the shipped default registry. It is short on purpose.
#
# `fake-deterministic` is the only entry approved for anything, and only for
# synthetic and operational text in test/dev environments. That is not a
# placeholder waiting to be filled in with real vendors — it is the honest state
# of provider governance in this repository: zero external vendors have a
# completed 第16条 assessment, so zero external vendors are callable.
#
# The `openai-compatible-unassessed` entry exists so the real adapter's code path
# is exercisable and reviewable, and it is registered with
# `status=TECHNICALLY_VALIDATED` + `sub_delegates=None`. Consequently every
# `admit()` for it fails. That is the correct outcome today and it is a *testable*
# correct outcome — which is better than omitting the entry and leaving the
# question undocumented.
DEFAULT_PROVIDER_RECORDS: tuple[ProviderRecord, ...] = (
    ProviderRecord(
        provider_id="fake-deterministic",
        vendor="aifamily-internal",
        model="fake-deterministic",
        model_version="1.0.0",
        status="INTERNAL_APPROVED",
        approved_environments=("test", "development"),
        sub_delegates=False,
        minor_data_allowed=False,
        private_text_allowed=False,
        security_assessment_ref="N/A: in-process, no data leaves the runtime",
        processing_agreement_ref="N/A: not a third-party processor",
        deletion_on_termination_committed=True,
        processing_region="in_process",
        notes=(
            "Deterministic in-process provider for tests. Not a third-party "
            "processor, so 第16条 does not apply — but it is still registered, "
            "because an unregistered provider must be unreachable and there is no "
            "test-only bypass of admission. R5: its output is SYNTHETIC and is "
            "never a business capability."
        ),
    ),
    ProviderRecord(
        provider_id="openai-compatible-unassessed",
        vendor="openai-compatible",
        model="unspecified",
        model_version="unspecified",
        status="TECHNICALLY_VALIDATED",
        approved_environments=("internal_livecheck",),
        sub_delegates=None,
        minor_data_allowed=False,
        private_text_allowed=False,
        processing_region="unspecified",
        credential_env_var="AIFAMILY_MODEL_API_KEY",
        base_url_env_var="AIFAMILY_MODEL_BASE_URL",
        timeout_seconds=30.0,
        notes=(
            "Real OpenAI-compatible Chat Completions adapter, deliberately NOT "
            "callable: status is TECHNICALLY_VALIDATED and sub_delegates is "
            "unknown, so admit() rejects it for every data class. Promoting it "
            "requires 法务 to establish the vendor's subcontracting structure "
            "(COMPLIANCE_HARD_CONSTRAINTS.md §7) — an engineering decision cannot "
            "supply that answer."
        ),
    ),
)


def default_provider_registry() -> ProviderRegistry:
    return ProviderRegistry(DEFAULT_PROVIDER_RECORDS)


_YAML_TRISTATE = {"true": True, "false": False, "unknown": None, "null": None, "none": None}


def load_provider_registry(path: Path) -> ProviderRegistry:
    """Build a registry from a YAML declaration.

    Provided for operators who want provider governance reviewable as a data
    file. Two properties keep it from becoming the source repository's drifting
    generated artifact: there *is* no generated artifact (the file is parsed
    straight into validated records), and every `ProviderRecord.__post_init__`
    check applies to file-declared providers exactly as to code-declared ones.

    `sub_delegates` accepts the string `unknown` in addition to booleans, so the
    honest answer is expressible. Omitting the key entirely is an error rather
    than a silent `unknown`: forgetting to state it and deciding you do not know
    are different acts, and only the latter should be quiet.
    """
    import yaml

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = raw.get("providers") or []
    records: list[ProviderRecord] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"{path}: providers[{index}] is not a mapping")
        records.append(_record_from_mapping(entry, source=f"{path}:providers[{index}]"))
    return ProviderRegistry(records)


def _record_from_mapping(entry: dict[str, Any], *, source: str) -> ProviderRecord:
    if "sub_delegates" not in entry:
        raise ValueError(
            f"{source}: 'sub_delegates' is required. Under 第16条 不得转委托 the "
            "subcontracting structure must be stated; use `unknown` if it has not been "
            "established, which the registry treats as prohibitive."
        )
    sub_delegates = entry["sub_delegates"]
    if isinstance(sub_delegates, str):
        key = sub_delegates.strip().lower()
        if key not in _YAML_TRISTATE:
            raise ValueError(
                f"{source}: sub_delegates must be true / false / unknown, got {sub_delegates!r}"
            )
        sub_delegates = _YAML_TRISTATE[key]
    elif sub_delegates is not None and not isinstance(sub_delegates, bool):
        raise ValueError(f"{source}: sub_delegates must be a boolean or 'unknown'")

    environments = entry.get("approved_environments") or ()
    if isinstance(environments, str):
        environments = (environments,)

    return ProviderRecord(
        provider_id=str(entry.get("provider_id") or ""),
        vendor=str(entry.get("vendor") or ""),
        model=str(entry.get("model") or ""),
        model_version=str(entry.get("model_version") or ""),
        status=entry.get("status") or "REGISTERED",
        approved_environments=tuple(str(item) for item in environments),
        sub_delegates=sub_delegates,
        minor_data_allowed=bool(entry.get("minor_data_allowed", False)),
        private_text_allowed=bool(entry.get("private_text_allowed", False)),
        security_assessment_ref=entry.get("security_assessment_ref"),
        processing_agreement_ref=entry.get("processing_agreement_ref"),
        deletion_on_termination_committed=bool(
            entry.get("deletion_on_termination_committed", False)
        ),
        processing_region=str(entry.get("processing_region") or "unspecified"),
        credential_env_var=entry.get("credential_env_var"),
        base_url_env_var=entry.get("base_url_env_var"),
        timeout_seconds=float(entry.get("timeout_seconds", 30.0)),
        notes=str(entry.get("notes") or ""),
    )
