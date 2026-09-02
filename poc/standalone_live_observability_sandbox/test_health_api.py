import importlib
import sys
import threading

from fastapi.testclient import TestClient

from poc.standalone_live_observability_sandbox.health_api import (
    COMPONENTS,
    ProbeResult,
    create_app,
)


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
