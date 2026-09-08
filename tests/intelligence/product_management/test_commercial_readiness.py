from backend.intelligence.product_management.commercial_readiness import (
    evaluate_commercial_readiness,
)


def test_24_lesson_release_is_blocked_without_real_commerce_evidence() -> None:
    result = evaluate_commercial_readiness(
        lesson_count=24,
        courseware_approved=True,
        product_package_released=True,
        evidence_verified=True,
        payment_sandbox_verified=False,
        entitlement_grant_verified=False,
        delivery_readback_verified=False,
        refund_recovery_verified=False,
        human_gate_accepted=True,
    )

    assert result.ready is False
    assert result.blockers == (
        "payment_sandbox_verified",
        "entitlement_grant_verified",
        "delivery_readback_verified",
        "refund_recovery_verified",
    )


def test_four_lesson_pilot_can_pass_scope_gate_when_commerce_evidence_is_ready() -> None:
    result = evaluate_commercial_readiness(
        lesson_count=4,
        courseware_approved=True,
        product_package_released=True,
        evidence_verified=True,
        payment_sandbox_verified=True,
        entitlement_grant_verified=True,
        delivery_readback_verified=True,
        refund_recovery_verified=True,
        human_gate_accepted=True,
    )

    assert result.ready is True
    assert result.checks["lesson_scope_valid"] is True


def test_readiness_requires_all_checks() -> None:
    result = evaluate_commercial_readiness(
        lesson_count=24,
        courseware_approved=True,
        product_package_released=True,
        evidence_verified=True,
        payment_sandbox_verified=True,
        entitlement_grant_verified=True,
        delivery_readback_verified=True,
        refund_recovery_verified=True,
        human_gate_accepted=True,
    )

    assert result.ready is True
    assert result.blockers == ()
