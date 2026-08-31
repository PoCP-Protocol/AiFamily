from fastapi.testclient import TestClient

from backend.domains.service.sandbox import build_sandbox_app


def test_s4_sandbox_offering_booking_and_delivery_record() -> None:
    with TestClient(build_sandbox_app()) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert "演示环境 · 不会联系真实服务人员" in page.text

        scene = client.get("/api/scene")
        assert scene.status_code == 200
        assert scene.json()["external_effect"] is False
        assert scene.json()["offerings"][0]["service_offering_ref"] == "EVENING_START_SUPPORT_45"
        assert scene.json()["slots"][0]["remaining_capacity"] == 1

        confirmed = client.post("/api/confirm-booking")
        assert confirmed.status_code == 200
        assert confirmed.json()["booking"]["status"] == "CONFIRMED"
        assert confirmed.json()["delivery_record"]["status"] == "PENDING"
        assert confirmed.json()["external_effect"] is False
        assert "confirm_booking_request" in confirmed.json()["audit_actions"]

        replay = client.post("/api/confirm-booking")
        assert replay.status_code == 200
        assert replay.json()["booking"] == confirmed.json()["booking"]
        assert replay.json()["delivery_record"] == confirmed.json()["delivery_record"]

        feedback = client.post("/api/complete-delivery?feedback=POSITIVE")
        assert feedback.status_code == 200
        assert feedback.json()["delivery_record"]["status"] == "COMPLETED"
        assert feedback.json()["delivery_record"]["service_quality_rating"] == "POSITIVE"
        assert feedback.json()["feedback_scope"] == "PROVIDER_SERVICE_ONLY"

        readback = client.get("/api/scene").json()["customer_projection"]["bookings"][0]
        assert readback["service_record_status"] == "COMPLETED"
        assert readback["service_quality_rating"] == "POSITIVE"

        duplicate_feedback = client.post("/api/complete-delivery?feedback=POSITIVE")
        assert duplicate_feedback.status_code == 409
        assert duplicate_feedback.json()["detail"] == "record_not_completable:COMPLETED"


def test_s4_sandbox_refuses_production(monkeypatch) -> None:
    monkeypatch.setenv("AIFAMILY_ENV", "PRODUCTION")
    try:
        build_sandbox_app()
    except RuntimeError as exc:
        assert str(exc) == "s4_service_sandbox_refuses_non_dev_environment"
    else:
        raise AssertionError("sandbox must refuse production")
