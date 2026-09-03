from datetime import UTC, datetime, timedelta

import pytest

from poc.standalone_live_control_sandbox.family_need_service_adapter import (
    AdultContext,
    AdultServiceChoice,
    ConfirmedNeedProjection,
    LiveNeedBridgeRejected,
    LiveNeedServiceAdapter,
    ServiceRecordReceipt,
)

NOW = datetime(2026, 9, 4, 12, tzinfo=UTC)
GUARDIAN = AdultContext("tenant.synthetic", "family.synthetic", "guardian.synthetic")
DEFAULT_NEED = object()


class Needs:
    def __init__(self, need: ConfirmedNeedProjection | None) -> None:
        self.need = need

    def get_confirmed_need(self, **_):
        return self.need


class Consent:
    def __init__(self, ref: str = "consent.synthetic.live-service") -> None:
        self.ref = ref

    def require_grant(self, **_):
        return self.ref


class Service:
    def __init__(self, receipt: ServiceRecordReceipt) -> None:
        self.receipt = receipt
        self.choices = []
        self.feedback = []

    def create_from_live_choice(self, **kwargs):
        self.choices.append(kwargs)
        return self.receipt

    def append_live_feedback(self, **kwargs):
        self.feedback.append(kwargs)
        return "need-signal.synthetic.feedback.1"


def need(**overrides):
    values = dict(
        need_id="need.synthetic.1",
        tenant_id=GUARDIAN.tenant_id,
        family_id=GUARDIAN.family_id,
        status="CONFIRMED",
        growth_theme="家庭沟通",
        consent_version="consent-v1",
        expires_at=NOW + timedelta(hours=1),
    )
    values.update(overrides)
    return ConfirmedNeedProjection(**values)


def choice(**overrides):
    values = dict(
        session_ref="live.synthetic.1",
        need_id="need.synthetic.1",
        offering_ref="offering.synthetic.1",
        choice_ref="choice.synthetic.1",
    )
    values.update(overrides)
    return AdultServiceChoice(**values)


def service_receipt(**overrides):
    values = dict(
        service_record_ref="service.synthetic.1",
        need_id="need.synthetic.1",
        tenant_id=GUARDIAN.tenant_id,
        family_id=GUARDIAN.family_id,
        status="COMPLETED",
    )
    values.update(overrides)
    return ServiceRecordReceipt(**values)


def bridge(
    *,
    projected_need: ConfirmedNeedProjection | None | object = DEFAULT_NEED,
    consent_ref="consent.synthetic.live-service",
    receipt=None,
):
    service = Service(receipt or service_receipt())
    resolved_need = need() if projected_need is DEFAULT_NEED else projected_need
    return LiveNeedServiceAdapter(
        family_needs=Needs(resolved_need),
        consent=Consent(consent_ref),
        service_records=service,
    ), service


def test_guardian_choice_consumes_confirmed_need_and_delegates_service_record():
    adapter, service = bridge()
    receipt = adapter.choose_service(choice=choice(), guardian=GUARDIAN, now=NOW)
    assert receipt.service_record_ref == "service.synthetic.1"
    assert service.choices[0]["choice"].need_id == "need.synthetic.1"
    assert service.choices[0]["consent_ref"] == "consent.synthetic.live-service"


@pytest.mark.parametrize("projected_need", [None, need(status="CAPTURED"), need(expires_at=NOW)])
def test_unconfirmed_or_expired_need_fails_before_service_mutation(projected_need):
    adapter, service = bridge(projected_need=projected_need)
    with pytest.raises(LiveNeedBridgeRejected):
        adapter.choose_service(choice=choice(), guardian=GUARDIAN, now=NOW)
    assert service.choices == []


def test_child_cross_scope_consent_and_fixture_spoofing_fail_closed():
    adapter, service = bridge(consent_ref="")
    with pytest.raises(LiveNeedBridgeRejected):
        adapter.choose_service(
            choice=choice(),
            guardian=AdultContext(
                "tenant.synthetic", "family.synthetic", "child.synthetic", "CHILD"
            ),
            now=NOW,
        )
    with pytest.raises(LiveNeedBridgeRejected):
        adapter.choose_service(choice=choice(), guardian=GUARDIAN, now=NOW)
    with pytest.raises(LiveNeedBridgeRejected):
        AdultServiceChoice(
            "live.synthetic.1",
            "need.synthetic.1",
            "offering.synthetic.1",
            "choice.bad",
            source="BASELINE_CONTENT",
        )
    assert service.choices == []


def test_feedback_requires_completed_scoped_service_and_confirmed_need():
    adapter, service = bridge()
    signal = adapter.record_feedback(
        service_record=service_receipt(),
        guardian=GUARDIAN,
        feedback_ref="feedback.synthetic.1",
        now=NOW,
    )
    assert signal == "need-signal.synthetic.feedback.1"
    assert service.feedback[0]["need_id"] == "need.synthetic.1"
    with pytest.raises(LiveNeedBridgeRejected):
        adapter.record_feedback(
            service_record=service_receipt(status="PENDING"),
            guardian=GUARDIAN,
            feedback_ref="feedback.synthetic.2",
            now=NOW,
        )
    with pytest.raises(LiveNeedBridgeRejected):
        adapter.record_feedback(
            service_record=service_receipt(family_id="family.other"),
            guardian=GUARDIAN,
            feedback_ref="feedback.synthetic.3",
            now=NOW,
        )
