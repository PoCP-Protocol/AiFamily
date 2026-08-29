"""Provider admission — the 第16条 compliance gate.

These tests are the reason `ProviderRegistry` can be described as an enforcement
mechanism rather than a documented intention (R14). Each one names the obligation
it protects.
"""

from __future__ import annotations

import pytest

from backend.intelligence.model_gateway.errors import ModelGatewayError
from backend.intelligence.model_gateway.provider_registry import (
    DEFAULT_PROVIDER_RECORDS,
    ProviderRecord,
    ProviderRegistry,
    default_provider_registry,
    load_provider_registry,
)


def _compliant_record(**overrides: object) -> ProviderRecord:
    """A record that clears every §16 check, so each test can break exactly one."""
    base: dict[str, object] = {
        "provider_id": "vendor-fully-assessed",
        "vendor": "hypothetical",
        "model": "m",
        "model_version": "1",
        "status": "PRODUCTION_APPROVED",
        "approved_environments": ("production",),
        "sub_delegates": False,
        "minor_data_allowed": True,
        "private_text_allowed": True,
        "security_assessment_ref": "DPIA-2026-001",
        "processing_agreement_ref": "AGREEMENT-2026-001",
        "deletion_on_termination_committed": True,
    }
    base.update(overrides)
    return ProviderRecord(**base)  # type: ignore[arg-type]


class TestUnregisteredProviderIsRefused:
    def test_lookup_of_unknown_provider_raises_policy_rejected(self) -> None:
        registry = default_provider_registry()
        with pytest.raises(ModelGatewayError) as excinfo:
            registry.get("some-vendor-nobody-registered")
        assert excinfo.value.kind == "POLICY_REJECTED"

    def test_admission_of_unknown_provider_raises_before_any_data_class_check(self) -> None:
        """Even the most innocuous data class does not create an implicit allowance."""
        registry = default_provider_registry()
        with pytest.raises(ModelGatewayError) as excinfo:
            registry.admit("unknown", data_class="SYNTHETIC", environment="test")
        assert excinfo.value.kind == "POLICY_REJECTED"


class TestNoSubDelegation:
    """《儿童个人信息网络保护规定》第16条 — 不得转委托.

    The constraint that `COMPLIANCE_HARD_CONSTRAINTS.md` §7 calls possibly the
    hardest to satisfy, because most vendors re-subcontract.
    """

    @pytest.mark.parametrize("data_class", ["MINOR_PERSONAL_DATA", "FAMILY_PRIVATE_TEXT"])
    def test_sub_delegating_provider_is_refused_for_regulated_data(
        self, data_class: str
    ) -> None:
        # The record cannot even *claim* the right, so admission is reached via a
        # record that permits the class while sub-delegating — which construction
        # forbids. Hence the two-step: construct compliant, then verify the
        # forbidden combination is unconstructable.
        with pytest.raises(ValueError, match="不得转委托|sub_delegates"):
            _compliant_record(provider_id="v-subdelegates", sub_delegates=True)

    def test_unknown_sub_delegation_status_is_treated_as_prohibitive(self) -> None:
        """`None` must behave exactly like `True`.

        "We have not asked the vendor yet" is not a defence under 第16条, so an
        unestablished subcontracting structure cannot be permissive.
        """
        with pytest.raises(ValueError, match="unknown"):
            _compliant_record(provider_id="v-unknown", sub_delegates=None)

    @pytest.mark.parametrize("data_class", ["MINOR_PERSONAL_DATA", "FAMILY_PRIVATE_TEXT"])
    def test_unassessed_provider_is_refused_for_regulated_data_at_admission(
        self, data_class: str
    ) -> None:
        """Defence in depth: an unassessed provider is refused at call time too.

        A record may legitimately carry `sub_delegates=None` while claiming no
        regulated-data rights — that is exactly the shipped
        `openai-compatible-unassessed` entry, which exists so the real adapter is
        reviewable. `admit()` must refuse it for regulated classes even though the
        constructor already blocked the *other* way of expressing the same thing
        (`sub_delegates != False` together with a data-class claim).

        Note which message fires: the scope check (`不得超出授权范围`) precedes the
        subcontracting check, because a provider that never claimed the right is
        refused on scope before the 不得转委托 question is reached. Both are §16
        duties and either rejection is correct; asserting on the kind rather than
        the wording keeps the test from pinning an incidental check order.
        """
        registry = ProviderRegistry(
            [
                ProviderRecord(
                    provider_id="v-unassessed-but-approved",
                    vendor="hypothetical",
                    model="m",
                    model_version="1",
                    status="PRODUCTION_APPROVED",
                    approved_environments=("production",),
                    sub_delegates=None,
                    minor_data_allowed=False,
                    private_text_allowed=False,
                )
            ]
        )
        with pytest.raises(ModelGatewayError) as excinfo:
            registry.admit(
                "v-unassessed-but-approved",
                data_class=data_class,  # type: ignore[arg-type]
                environment="production",
            )
        assert excinfo.value.kind == "POLICY_REJECTED"
        assert "第16条" in excinfo.value.message

    def test_sub_delegation_check_fires_when_scope_alone_would_have_passed(self) -> None:
        """The `_assert_delegation_paperwork` branch, reached directly.

        Construction refuses `sub_delegates != False` combined with a data-class
        claim, so no *constructible* record reaches the subcontracting check
        through `admit()`. That makes the check unreachable-by-construction rather
        than dead — but "unreachable" is a property of today's validation rules,
        and a future relaxation of those rules must not silently remove the
        backstop. This test pins the backstop itself.
        """
        record = _compliant_record()
        object.__setattr__(record, "sub_delegates", True)
        with pytest.raises(ModelGatewayError) as excinfo:
            ProviderRegistry._assert_delegation_paperwork(record, "MINOR_PERSONAL_DATA")
        assert "不得转委托" in excinfo.value.message

    def test_non_delegating_fully_assessed_provider_is_admitted(self) -> None:
        """The gate must be passable, or it is a ban rather than a gate."""
        registry = ProviderRegistry([_compliant_record()])
        record = registry.admit(
            "vendor-fully-assessed",
            data_class="MINOR_PERSONAL_DATA",
            environment="production",
        )
        assert record.provider_id == "vendor-fully-assessed"


class TestDelegationPaperwork:
    @pytest.mark.parametrize(
        "field_name",
        ["security_assessment_ref", "processing_agreement_ref"],
    )
    def test_missing_paperwork_refuses_regulated_data(self, field_name: str) -> None:
        registry = ProviderRegistry([_compliant_record(**{field_name: None})])
        with pytest.raises(ModelGatewayError) as excinfo:
            registry.admit(
                "vendor-fully-assessed",
                data_class="FAMILY_PRIVATE_TEXT",
                environment="production",
            )
        assert excinfo.value.kind == "POLICY_REJECTED"
        assert field_name in excinfo.value.message

    def test_missing_deletion_commitment_refuses_regulated_data(self) -> None:
        registry = ProviderRegistry(
            [_compliant_record(deletion_on_termination_committed=False)]
        )
        with pytest.raises(ModelGatewayError):
            registry.admit(
                "vendor-fully-assessed",
                data_class="MINOR_PERSONAL_DATA",
                environment="production",
            )

    def test_paperwork_checks_do_not_apply_to_synthetic_data(self) -> None:
        """§16 governs personal information; a synthetic fixture has no subject.

        Scoping matters: applying the paperwork checks to `SYNTHETIC` would make
        the deterministic test provider unusable and invite a test-only bypass of
        admission — which is worse than the over-strictness it came from.
        """
        registry = ProviderRegistry(
            [
                _compliant_record(
                    security_assessment_ref=None,
                    processing_agreement_ref=None,
                    deletion_on_termination_committed=False,
                    minor_data_allowed=False,
                    private_text_allowed=False,
                )
            ]
        )
        record = registry.admit(
            "vendor-fully-assessed", data_class="SYNTHETIC", environment="production"
        )
        assert record.provider_id == "vendor-fully-assessed"


class TestStatusAndEnvironmentGating:
    def test_technically_validated_status_is_not_callable(self) -> None:
        """An adapter passing a smoke test is not a production approval."""
        registry = ProviderRegistry([_compliant_record(status="TECHNICALLY_VALIDATED")])
        with pytest.raises(ModelGatewayError) as excinfo:
            registry.admit(
                "vendor-fully-assessed", data_class="SYNTHETIC", environment="production"
            )
        assert "TECHNICALLY_VALIDATED" in excinfo.value.message

    def test_suspended_provider_is_not_callable(self) -> None:
        registry = ProviderRegistry([_compliant_record(status="SUSPENDED")])
        with pytest.raises(ModelGatewayError):
            registry.admit(
                "vendor-fully-assessed", data_class="SYNTHETIC", environment="production"
            )

    def test_provider_not_approved_for_environment_is_refused(self) -> None:
        registry = ProviderRegistry([_compliant_record(approved_environments=("staging",))])
        with pytest.raises(ModelGatewayError) as excinfo:
            registry.admit(
                "vendor-fully-assessed", data_class="SYNTHETIC", environment="production"
            )
        assert "environment" in excinfo.value.message

    def test_record_with_no_approved_environment_cannot_be_constructed(self) -> None:
        with pytest.raises(ValueError, match="approved_environments"):
            _compliant_record(approved_environments=())


class TestShippedRegistryIsHonest:
    def test_no_external_vendor_is_callable_for_regulated_data(self) -> None:
        """The state of provider governance in this repository, asserted.

        Zero external vendors have completed a §16 assessment, therefore zero are
        reachable with family or minor data. If someone later adds a vendor
        without doing the legal work, this test is what fails.
        """
        registry = default_provider_registry()
        for provider_id in registry.provider_ids():
            record = registry.get(provider_id)
            if record.vendor == "aifamily-internal":
                continue
            for data_class in ("MINOR_PERSONAL_DATA", "FAMILY_PRIVATE_TEXT"):
                for environment in ("test", "development", "internal_livecheck", "production"):
                    with pytest.raises(ModelGatewayError):
                        registry.admit(
                            provider_id,
                            data_class=data_class,  # type: ignore[arg-type]
                            environment=environment,
                        )

    def test_real_adapter_entry_is_registered_but_not_callable(self) -> None:
        """The real adapter's governance entry exists precisely so its
        non-callability is a tested fact rather than an undocumented gap."""
        registry = default_provider_registry()
        record = registry.get("openai-compatible-unassessed")
        assert record.sub_delegates is None
        assert record.status == "TECHNICALLY_VALIDATED"
        with pytest.raises(ModelGatewayError):
            registry.admit(
                "openai-compatible-unassessed",
                data_class="OPERATIONAL_TEXT",
                environment="internal_livecheck",
            )

    def test_every_shipped_record_names_its_credential_source_not_a_secret(self) -> None:
        """R7: the registry carries variable *names*, never key material."""
        for record in DEFAULT_PROVIDER_RECORDS:
            for value in (record.credential_env_var, record.base_url_env_var):
                if value is not None:
                    assert value.isupper() or "_" in value

    def test_duplicate_provider_ids_are_refused(self) -> None:
        with pytest.raises(ValueError, match="duplicate provider_id"):
            ProviderRegistry([_compliant_record(), _compliant_record()])


class TestYamlDeclaration:
    def test_omitting_sub_delegates_is_an_error_not_a_silent_unknown(self, tmp_path) -> None:
        """Forgetting to state it and knowing you do not know are different acts."""
        path = tmp_path / "providers.yaml"
        path.write_text(
            "providers:\n"
            "  - provider_id: v1\n"
            "    vendor: x\n"
            "    approved_environments: [test]\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="sub_delegates"):
            load_provider_registry(path)

    def test_unknown_string_parses_to_none_and_stays_prohibitive(self, tmp_path) -> None:
        path = tmp_path / "providers.yaml"
        path.write_text(
            "providers:\n"
            "  - provider_id: v1\n"
            "    vendor: x\n"
            "    model: m\n"
            "    model_version: '1'\n"
            "    status: PRODUCTION_APPROVED\n"
            "    approved_environments: [test]\n"
            "    sub_delegates: unknown\n",
            encoding="utf-8",
        )
        registry = load_provider_registry(path)
        assert registry.get("v1").sub_delegates is None
        with pytest.raises(ModelGatewayError):
            registry.admit("v1", data_class="FAMILY_PRIVATE_TEXT", environment="test")

    def test_file_declared_records_get_the_same_construction_checks(self, tmp_path) -> None:
        """A YAML-declared provider must not be able to state a combination that
        code-declared providers are forbidden from stating."""
        path = tmp_path / "providers.yaml"
        path.write_text(
            "providers:\n"
            "  - provider_id: v1\n"
            "    vendor: x\n"
            "    model: m\n"
            "    model_version: '1'\n"
            "    status: PRODUCTION_APPROVED\n"
            "    approved_environments: [test]\n"
            "    sub_delegates: true\n"
            "    minor_data_allowed: true\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="不得转委托|sub_delegates"):
            load_provider_registry(path)
