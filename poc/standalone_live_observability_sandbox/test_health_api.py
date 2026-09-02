import importlib
import sys
import threading
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from poc.standalone_live_observability_sandbox.health_api import (
    COMPONENTS,
    ProbeResult,
    create_app,
)
from poc.standalone_live_observability_sandbox.slo import MetricSample

NOW = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
SESSION = "live.synthetic.mili-001"


def targets() -> dict[str, str]:
    return {
        "media": "http://user:media-secret@media.synthetic:9101?token=hidden",
        "interaction": "http://interaction.synthetic:9102",
        "replay": "http://replay.synthetic:9103/base/",
        "commerce": "http://commerce.synthetic:9104/health",
    }


def headers(
    *,
    role: str = "LIVE_OPERATOR",
    tenant: str = "tenant.synthetic.alpha",
    family: str = "family.synthetic.alpha",
) -> dict[str, str]:
    return {
        "X-Sandbox-Source": "SANDBOX_SYNTHETIC",
        "X-Fixture-Only": "true",
        "X-Tenant-Id": tenant,
        "X-Family-Id": family,
        "X-Actor-Id": "actor.synthetic.live-operator",
        "X-Actor-Role": role,
    }


def healthy_probe(url: str, timeout_seconds: float) -> ProbeResult:
    del timeout_seconds
    if "media" in url:
        payload = {"source": "synthetic", "fixture_only": True}
    else:
        payload = {
            "status": "ok",
            "source": "SANDBOX_SYNTHETIC",
            "fixture_only": True,
        }
    return ProbeResult(200, payload, 2.5, True)


def healthy_slo_samples(
    tenant_id: str = "tenant.synthetic.alpha",
    family_id: str = "family.synthetic.alpha",
    session_ref: str = SESSION,
) -> list[MetricSample]:
    observed_at = NOW - timedelta(seconds=5)
    common = {
        "observed_at": observed_at,
        "tenant_id": tenant_id,
        "family_id": family_id,
        "session_ref": session_ref,
    }
    return [
        MetricSample(component="media", metric="startup_success", value=1, **common),
        MetricSample(component="media", metric="first_frame_ms", value=420, **common),
        MetricSample(component="media", metric="stall_ratio", value=0.004, **common),
        MetricSample(component="media", metric="recovery_ms", value=850, **common),
        MetricSample(
            component="interaction",
            metric="interaction_latency_ms",
            value=75,
            **common,
        ),
        MetricSample(component="control", metric="request_success", value=1, **common),
        MetricSample(component="replay", metric="request_success", value=1, **common),
    ]


def test_four_components_are_probed_concurrently_and_ready_without_secret_leak() -> None:
    barrier = threading.Barrier(len(COMPONENTS))

    def concurrent_probe(url: str, timeout_seconds: float) -> ProbeResult:
        del timeout_seconds
        barrier.wait(timeout=1)
        return healthy_probe(url, 0)

    client = TestClient(create_app(targets(), probe=concurrent_probe))
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    snapshot = client.get("/sandbox/live-ops/runtime-snapshot", headers=headers())
    assert snapshot.status_code == 200
    body = snapshot.json()
    assert body["overall"] == "READY"
    assert body["external_effect"] is False
    assert body["checked_at"]
    assert body["latency_ms"] >= 0
    assert [item["component"] for item in body["components"]] == list(COMPONENTS)
    assert all(item["state"] == "UP" for item in body["components"])
    assert all(item["external_effect"] is False for item in body["components"])
    rendered_urls = " ".join(item["url"] for item in body["components"])
    assert "media-secret" not in rendered_urls
    assert "token" not in rendered_urls
    assert "user@" not in rendered_urls


def test_unsafe_component_response_degrades_without_becoming_ready() -> None:
    def unsafe_probe(url: str, timeout_seconds: float) -> ProbeResult:
        result = healthy_probe(url, timeout_seconds)
        if "interaction" in url:
            return ProbeResult(
                200,
                {"status": "ok", "source": "PRODUCTION", "fixture_only": False},
                1.0,
                True,
            )
        return result

    response = TestClient(create_app(targets(), probe=unsafe_probe)).get(
        "/sandbox/live-ops/runtime-snapshot", headers=headers(role="HUMAN_MODERATOR")
    )
    assert response.status_code == 200
    body = response.json()
    assert body["overall"] == "DEGRADED"
    states = {item["component"]: item["state"] for item in body["components"]}
    assert states["interaction"] == "UNSAFE"
    assert sum(state == "UP" for state in states.values()) == 3


def test_media_health_requires_exact_adapter_contract() -> None:
    def unsafe_media_probe(url: str, timeout_seconds: float) -> ProbeResult:
        result = healthy_probe(url, timeout_seconds)
        if "media" in url:
            return ProbeResult(
                200,
                {
                    "status": "ok",
                    "source": "synthetic",
                    "fixture_only": True,
                },
                1.0,
                True,
            )
        return result

    response = TestClient(create_app(targets(), probe=unsafe_media_probe)).get(
        "/sandbox/live-ops/runtime-snapshot", headers=headers()
    )
    assert response.status_code == 200
    body = response.json()
    assert body["overall"] == "DEGRADED"
    states = {item["component"]: item["state"] for item in body["components"]}
    assert states["media"] == "UNSAFE"


def test_timeout_and_connection_failure_return_200_degraded_snapshot() -> None:
    def failing_probe(url: str, timeout_seconds: float) -> ProbeResult:
        del timeout_seconds
        if "replay" in url:
            raise TimeoutError("synthetic timeout")
        if "commerce" in url:
            return ProbeResult(None, None, 12.0, False)
        return healthy_probe(url, 0)

    response = TestClient(create_app(targets(), probe=failing_probe)).get(
        "/sandbox/live-ops/runtime-snapshot", headers=headers()
    )
    assert response.status_code == 200
    body = response.json()
    assert body["overall"] == "DEGRADED"
    states = {item["component"]: item["state"] for item in body["components"]}
    assert states == {
        "media": "UP",
        "interaction": "UP",
        "replay": "DOWN",
        "commerce": "DOWN",
    }


def test_snapshot_requires_safe_operator_role_and_exact_synthetic_scope() -> None:
    client = TestClient(create_app(targets(), probe=healthy_probe))
    url = "/sandbox/live-ops/runtime-snapshot"
    assert client.get(url).status_code == 401
    assert client.get(url, headers=headers(role="CHILD")).status_code == 403
    assert client.get(url, headers=headers(role="ADULT_VIEWER")).status_code == 403
    assert client.get(url, headers=headers(family="family.synthetic.other")).status_code == 403
    assert client.get(url, headers=headers(tenant="tenant.synthetic.other")).status_code == 403
    assert client.get(url, headers=headers(tenant="tenant.real")).status_code == 403


def test_operator_can_read_scoped_green_slo_without_external_effect() -> None:
    requested: list[tuple[str, str, str]] = []

    def samples(tenant_id: str, family_id: str, session_ref: str):
        requested.append((tenant_id, family_id, session_ref))
        return healthy_slo_samples(tenant_id, family_id, session_ref)

    client = TestClient(
        create_app(targets(), probe=healthy_probe, slo_samples=samples, clock=lambda: NOW)
    )
    response = client.get(f"/sandbox/live-ops/sessions/{SESSION}/slo", headers=headers())

    assert response.status_code == 200
    body = response.json()
    assert requested == [("tenant.synthetic.alpha", "family.synthetic.alpha", SESSION)]
    assert body == {
        "session_ref": SESSION,
        "window_start": (NOW - timedelta(minutes=5)).isoformat(),
        "window_end": NOW.isoformat(),
        "sample_count": 7,
        "startup_success": 1.0,
        "first_frame_p95_ms": 420.0,
        "stall_ratio": 0.004,
        "interaction_latency_p95_ms": 75.0,
        "recovery_p95_ms": 850.0,
        "error_budget": 1.0,
        "recommendation": "GREEN",
        "reasons": [],
        "human_review_required": False,
        "automatic_stop_issued": False,
        "source": "SANDBOX_SYNTHETIC",
        "fixture_only": True,
        "external_effect": False,
    }


def test_slo_threshold_breach_returns_degraded_shape() -> None:
    def samples(tenant_id: str, family_id: str, session_ref: str):
        items = healthy_slo_samples(tenant_id, family_id, session_ref)
        items[1] = replace(items[1], value=1_900)
        return items

    response = TestClient(create_app(targets(), slo_samples=samples, clock=lambda: NOW)).get(
        f"/sandbox/live-ops/sessions/{SESSION}/slo", headers=headers()
    )

    assert response.status_code == 200
    body = response.json()
    assert body["recommendation"] == "DEGRADED"
    assert body["first_frame_p95_ms"] == 1_900
    assert body["error_budget"] == 1
    assert body["reasons"] == ["first-frame latency above target"]
    assert body["human_review_required"] is False
    assert body["external_effect"] is False


def test_missing_metrics_return_stable_fail_closed_stop_shape() -> None:
    client = TestClient(create_app(targets(), clock=lambda: NOW))
    response = client.get(f"/sandbox/live-ops/sessions/{SESSION}/slo", headers=headers())

    assert response.status_code == 200
    body = response.json()
    assert body["recommendation"] == "STOP"
    assert body["startup_success"] is None
    assert body["first_frame_p95_ms"] is None
    assert body["error_budget"] == 0
    assert body["reasons"] == ["missing metrics"]
    assert body["human_review_required"] is True
    assert body["automatic_stop_issued"] is False
    assert body["external_effect"] is False


def test_stale_cross_scope_and_provider_failure_all_fail_closed() -> None:
    unsafe_sets = []
    stale = healthy_slo_samples()
    unsafe_sets.append([replace(item, observed_at=NOW - timedelta(seconds=46)) for item in stale])
    cross_scope = healthy_slo_samples()
    cross_scope[0] = replace(cross_scope[0], family_id="family.synthetic.other")
    unsafe_sets.append(cross_scope)
    provider_failed = healthy_slo_samples()
    provider_failed[0] = replace(provider_failed[0], provider_ok=False)
    unsafe_sets.append(provider_failed)

    for supplied in unsafe_sets:
        client = TestClient(
            create_app(
                targets(),
                slo_samples=lambda tenant, family, session, items=supplied: items,
                clock=lambda: NOW,
            )
        )
        body = client.get(f"/sandbox/live-ops/sessions/{SESSION}/slo", headers=headers()).json()
        assert body["recommendation"] == "STOP"
        assert body["human_review_required"] is True
        assert body["automatic_stop_issued"] is False
        assert body["external_effect"] is False
        assert body["reasons"]


def test_metrics_provider_exception_is_hidden_behind_safe_stop_shape() -> None:
    def failing_provider(tenant_id: str, family_id: str, session_ref: str):
        del tenant_id, family_id, session_ref
        raise RuntimeError("synthetic provider secret must not escape")

    response = TestClient(
        create_app(targets(), slo_samples=failing_provider, clock=lambda: NOW)
    ).get(f"/sandbox/live-ops/sessions/{SESSION}/slo", headers=headers())

    assert response.status_code == 200
    body = response.json()
    assert body["recommendation"] == "STOP"
    assert body["reasons"] == ["metrics provider failure"]
    assert "secret" not in response.text
    assert body["human_review_required"] is True
    assert body["external_effect"] is False


def test_slo_endpoint_requires_operator_role_and_exact_scope() -> None:
    client = TestClient(
        create_app(
            targets(),
            slo_samples=lambda tenant, family, session: healthy_slo_samples(
                tenant, family, session
            ),
            clock=lambda: NOW,
        )
    )
    url = f"/sandbox/live-ops/sessions/{SESSION}/slo"

    assert client.get(url).status_code == 401
    assert client.get(url, headers=headers(role="CHILD")).status_code == 403
    assert client.get(url, headers=headers(role="ADULT_VIEWER")).status_code == 403
    assert client.get(url, headers=headers(family="family.synthetic.other")).status_code == 403
    assert client.get(url, headers=headers(tenant="tenant.synthetic.other")).status_code == 403


def test_module_import_and_cli_wire_all_component_targets(monkeypatch) -> None:
    module = importlib.import_module("poc.standalone_live_observability_sandbox.health_api")
    captured: dict[str, object] = {}

    def fake_run(app, *, host: str, port: int) -> None:
        captured.update(app=app, host=host, port=port)

    monkeypatch.setattr(module.uvicorn, "run", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "health_api.py",
            "--media-url",
            "http://media.synthetic:9101",
            "--interaction-url",
            "http://interaction.synthetic:9102",
            "--replay-url",
            "http://replay.synthetic:9103",
            "--commerce-url",
            "http://commerce.synthetic:9104",
            "--port",
            "9200",
        ],
    )
    module.main()
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 9200
    assert TestClient(captured["app"]).get("/health").status_code == 200
