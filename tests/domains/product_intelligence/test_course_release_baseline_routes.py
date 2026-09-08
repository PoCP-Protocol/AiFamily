import pytest
from fastapi.testclient import TestClient

from backend.apps.family_api.main import create_app


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
    client = TestClient(create_app())
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
    assert client.get(path, headers={**headers, "x-tenant-scope": "tenant-b"}).status_code == 404
