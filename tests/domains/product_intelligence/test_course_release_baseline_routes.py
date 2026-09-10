import pytest
from fastapi.testclient import TestClient

from backend.apps.family_api.main import create_app
from backend.domains.product_intelligence.api.course_routes import get_actor_context
from backend.domains.product_intelligence.application.context import ActorContext


def _payload() -> dict:
    return {
        "schema_version": "1.0",
        "course_system_version_ref": "course-system:family@v1",
        "product_package_version_ref": "product-package:family@v1",
        "product_definition_version_ref": "product-definition:family@v1",
        "course_content_version_ref": "course-content:family@v1",
        "safety_policy_version_ref": "safety:family@v1",
        "prompt_bundle_version_ref": "prompts:family@v1",
        "evidence_receipt_refs": ["receipt:course"],
        "delivery_channel": "WEB",
        "lessons": [
            {
                "lesson_version_ref": f"lesson:{i}@v1",
                "asset_bundle_version_ref": f"asset:{i}@v1",
                "skill_version_refs": [f"skill:{i}@v1"],
            }
            for i in range(1, 25)
        ],
    }


def test_release_baseline_route_persists_approves_and_restores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIFAMILY_ENV", "test")
    with TestClient(create_app()) as client:
        headers = {"x-tenant-scope": "tenant-a", "x-actor-id": "operator-a"}
        created = client.post(
            "/product-intelligence/courses/release-baselines",
            json={"payload": _payload()},
            headers=headers,
        )
        assert created.status_code == 200
        release_id = created.json()["release_id"]
        path = f"/product-intelligence/courses/release-baselines/{release_id}"
        assert client.get(path, headers=headers).json()["status"] == "DRAFT"
        decided = client.post(
            path + "/lifecycle",
            json={
                "action": "APPROVE",
                "decision_id": "decision:1",
                "task_id": "task:1",
                "evidence": [{
                    "evidence_id": "receipt:course",
                    "kind": "QA",
                    "reference": "qa://course",
                    "summary": "通过",
                }],
            },
            headers=headers,
        )
        assert decided.status_code == 200
        assert decided.json()["baseline"]["status"] == "REVIEWED"
        assert client.get(path, headers=headers).json()["status"] == "REVIEWED"
        assert (
            client.get(path, headers={**headers, "x-tenant-scope": "tenant-b"}).status_code == 404
        )


def test_release_baseline_lifecycle_requires_release_review_permission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIFAMILY_ENV", "test")
    app = create_app()
    from backend.domains.product_intelligence.api.course_routes import get_actor_context
    app.dependency_overrides[get_actor_context] = lambda: ActorContext(
        actor_id="human-author",
        actor_type="HUMAN",
        tenant_scope="tenant-no-permission",
        permissions=frozenset(),
    )
    with TestClient(app) as client:
        created = client.post(
            "/product-intelligence/courses/release-baselines",
            json={"payload": _payload()},
        )
        response = client.post(
            f"/product-intelligence/courses/release-baselines/{created.json()['release_id']}/lifecycle",
            json={
                "action": "APPROVE",
                "decision_id": "decision:1",
                "task_id": "task:1",
                "evidence": [{
                    "evidence_id": "receipt:course",
                    "kind": "QA",
                    "reference": "qa://course",
                    "summary": "通过",
                }],
            },
        )
    assert response.status_code == 403


def test_release_baseline_lifecycle_rejects_unknown_action_at_http_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIFAMILY_ENV", "test")
    with TestClient(create_app()) as client:
        headers = {"x-tenant-scope": "tenant-contract", "x-actor-id": "operator-contract"}
        created = client.post(
            "/product-intelligence/courses/release-baselines",
            json={"payload": _payload()},
            headers=headers,
        )
        response = client.post(
            f"/product-intelligence/courses/release-baselines/{created.json()['release_id']}/lifecycle",
            json={
                "action": "PUBLISH_NOW",
                "decision_id": "decision:invalid",
                "task_id": "task:invalid",
                "evidence": [{
                    "evidence_id": "receipt:course",
                    "kind": "QA",
                    "reference": "qa://course",
                    "summary": "通过",
                }],
            },
            headers=headers,
        )
    assert response.status_code == 422


def test_release_baseline_lifecycle_rejects_ai_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIFAMILY_ENV", "test")
    app = create_app()
    app.dependency_overrides[get_actor_context] = lambda: ActorContext(
        actor_id="agent-1",
        actor_type="AI",
        tenant_scope="tenant-ai",
    )
    with TestClient(app) as client:
        created = client.post(
            "/product-intelligence/courses/release-baselines",
            json={"payload": _payload()},
        )
        release_id = created.json()["release_id"]
        response = client.post(
            f"/product-intelligence/courses/release-baselines/{release_id}/lifecycle",
            json={
                "action": "APPROVE",
                "decision_id": "decision:ai",
                "task_id": "task:ai",
                "evidence": [{
                    "evidence_id": "receipt:course",
                    "kind": "QA",
                    "reference": "qa://course",
                    "summary": "通过",
                }],
            },
        )
    assert response.status_code == 403
